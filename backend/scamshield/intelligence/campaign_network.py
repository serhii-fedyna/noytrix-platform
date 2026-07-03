from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Tuple

from scamshield.intelligence.postgres_intelligence import connect
from scamshield.intelligence.reputation_graph import install_graph_schema


CAMPAIGN_CLUSTER_VERSION = "v1"
MIN_CLUSTER_SIZE = 3
MAX_CLUSTER_MEMBERS = 500

CLUSTER_EDGE_TYPES = {
    "domain_part_of_campaign",
    "shared_impersonated_brand",
    "shared_threat_sources",
    "shared_wallet_threat_source",
    "url_belongs_to_domain",
    "network_part_of_campaign",
}

BRAND_HINTS = [
    "aave",
    "binance",
    "coinbase",
    "ledger",
    "metamask",
    "opensea",
    "pancake",
    "phantom",
    "trustwallet",
    "uniswap",
    "walletconnect",
]


class DisjointSet:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def add(self, item: int) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: int) -> int:
        self.add(item)
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left != root_right:
            self.parent[root_right] = root_left


def _brand_for_text(value: str) -> str | None:
    compact = re.sub(r"[^a-z0-9]", "", (value or "").lower())
    for brand in BRAND_HINTS:
        if brand in compact:
            return brand
    return None


def _cluster_id(members: Iterable[dict]) -> str:
    seed = "|".join(sorted(str(x.get("normalized_entity") or "") for x in members)[:50])
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"campaign:network:{digest}"


def _cluster_name(members: List[dict]) -> Tuple[str, str]:
    brands = Counter(
        brand
        for brand in (_brand_for_text(str(x.get("normalized_entity") or "")) for x in members)
        if brand
    )
    if brands:
        brand = brands.most_common(1)[0][0]
        return f"{brand.title()} impersonation network", brand
    types = Counter(str(x.get("entity_type") or "entity") for x in members)
    label = types.most_common(1)[0][0] if types else "entity"
    return f"Linked {label} scam network", ""


def _risk_metrics(members: List[dict], edge_count: int) -> dict:
    risks = [int(x.get("risk_score") or 0) for x in members]
    confidences = [int(x.get("confidence") or 0) for x in members]
    types = Counter(str(x.get("entity_type") or "unknown") for x in members)
    statuses = Counter(str(x.get("status") or "unknown").lower() for x in members)
    return {
        "member_count": len(members),
        "edge_count": edge_count,
        "max_member_risk": max(risks or [0]),
        "avg_member_risk": int(sum(risks) / max(1, len(risks))),
        "avg_confidence": int(sum(confidences) / max(1, len(confidences))),
        "entity_types": dict(types),
        "status_counts": dict(statuses),
    }


def run_campaign_network_clustering() -> Dict[str, Any]:
    install_graph_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, normalized_entity, entity_type, status, risk_score, confidence, metadata
                FROM entities
                WHERE lower(COALESCE(status, '')) IN ('malicious','scam','danger','critical','high','blocked')
                  AND entity_type IN ('domain','url','evm_address','wallet','contract')
                """
            )
            entities = {int(row["id"]): dict(row) for row in cur.fetchall()}

            dsu = DisjointSet()
            for entity_id in entities:
                dsu.add(entity_id)

            cur.execute(
                """
                SELECT source_entity_id, target_entity_id, edge_type, weight, confidence
                FROM entity_edges
                WHERE edge_type = ANY(%s)
                  AND COALESCE(weight, 0) >= 40
                  AND COALESCE(confidence, 0) >= 60
                """,
                (sorted(CLUSTER_EDGE_TYPES),),
            )
            edges = []
            for row in cur.fetchall():
                source_id = int(row["source_entity_id"])
                target_id = int(row["target_entity_id"])
                if source_id in entities and target_id in entities:
                    dsu.union(source_id, target_id)
                    edges.append((source_id, target_id, dict(row)))

            clusters: dict[int, list[int]] = defaultdict(list)
            for entity_id in entities:
                clusters[dsu.find(entity_id)].append(entity_id)

            created = 0
            members_updated = 0
            campaign_edges = 0
            skipped = 0

            for member_ids in clusters.values():
                if len(member_ids) < MIN_CLUSTER_SIZE:
                    skipped += 1
                    continue

                members = [entities[x] for x in member_ids[:MAX_CLUSTER_MEMBERS]]
                campaign_id = _cluster_id(members)
                name, brand = _cluster_name(members)
                cluster_edge_count = sum(1 for a, b, _ in edges if a in member_ids and b in member_ids)
                metrics = _risk_metrics(members, cluster_edge_count)
                risk = max(75, metrics["max_member_risk"], min(95, metrics["avg_member_risk"] + 15))
                confidence = max(70, min(95, metrics["avg_confidence"] + min(20, len(members))))

                metadata = {
                    "created_by": "campaign_network_clustering",
                    "version": CAMPAIGN_CLUSTER_VERSION,
                    "campaign_type": "network_cluster",
                    "brand": brand,
                    "cluster_metrics": metrics,
                    "sample_members": [
                        {
                            "entity": m.get("normalized_entity"),
                            "entity_type": m.get("entity_type"),
                            "risk_score": m.get("risk_score"),
                        }
                        for m in members[:20]
                    ],
                }

                cur.execute(
                    """
                    INSERT INTO entities (
                        entity, normalized_entity, entity_type, status,
                        risk_score, confidence, first_seen_at, last_seen_at,
                        seen_count, source_count, roles, metadata
                    )
                    VALUES (
                        %s, %s, 'campaign', 'malicious',
                        %s, %s, now(), now(),
                        1, 1, '["campaign","network_cluster"]'::jsonb, %s::jsonb
                    )
                    ON CONFLICT (normalized_entity)
                    DO UPDATE SET
                        last_seen_at = now(),
                        status = 'malicious',
                        risk_score = GREATEST(entities.risk_score, EXCLUDED.risk_score),
                        confidence = GREATEST(entities.confidence, EXCLUDED.confidence),
                        metadata = entities.metadata || EXCLUDED.metadata
                    RETURNING id
                    """,
                    (
                        name,
                        campaign_id,
                        int(risk),
                        int(confidence),
                        json.dumps(metadata, ensure_ascii=False),
                    ),
                )
                campaign_db_id = int(cur.fetchone()["id"])
                created += 1

                cur.execute(
                    """
                    UPDATE entities
                    SET campaign_id = %s,
                        metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object(
                            'network_cluster',
                            jsonb_build_object(
                                'campaign_id', %s::text,
                                'version', %s::text,
                                'member_count', %s::int,
                                'assigned_by', 'campaign_network_clustering',
                                'assigned_at', now()
                            )
                        )
                    WHERE id = ANY(%s)
                    """,
                    (campaign_id, campaign_id, CAMPAIGN_CLUSTER_VERSION, len(members), member_ids),
                )
                members_updated += cur.rowcount

                cur.execute(
                    """
                    INSERT INTO entity_edges (
                        source_entity_id, target_entity_id, edge_type,
                        weight, confidence, sources, metadata
                    )
                    SELECT
                        unnest(%s::bigint[]),
                        %s,
                        'network_part_of_campaign',
                        88,
                        88,
                        '["campaign_network_clustering"]'::jsonb,
                        jsonb_build_object(
                            'campaign_id', %s::text,
                            'version', %s::text,
                            'reason', 'entity belongs to a connected scam network cluster'
                        )
                    ON CONFLICT (source_entity_id, target_entity_id, edge_type)
                    DO UPDATE SET
                        last_seen_at = now(),
                        seen_count = entity_edges.seen_count + 1,
                        weight = GREATEST(entity_edges.weight, EXCLUDED.weight),
                        confidence = GREATEST(entity_edges.confidence, EXCLUDED.confidence),
                        metadata = entity_edges.metadata || EXCLUDED.metadata
                    """,
                    (member_ids, campaign_db_id, campaign_id, CAMPAIGN_CLUSTER_VERSION),
                )
                campaign_edges += cur.rowcount

            conn.commit()

    return {
        "campaign_clusters_upserted": created,
        "cluster_members_updated": members_updated,
        "network_campaign_edges_upserted": campaign_edges,
        "small_clusters_skipped": skipped,
        "version": CAMPAIGN_CLUSTER_VERSION,
    }


if __name__ == "__main__":
    print(json.dumps(run_campaign_network_clustering(), ensure_ascii=False, indent=2))
