from __future__ import annotations

import json
import re

from scamshield.intelligence.postgres_intelligence import connect


BRANDS = [
    "aave",
    "binance",
    "uniswap",
    "metamask",
    "opensea",
    "ledger",
    "trezor",
    "walletconnect",
    "pancakeswap",
    "coinbase",
    "phantom",
    "trustwallet",
    "chainlink",
    "1inch",
]


def brand_for_domain(domain: str) -> str | None:
    d = (domain or "").lower()
    compact = re.sub(r"[^a-z0-9]", "", d)

    for b in BRANDS:
        if b.replace(" ", "") in compact:
            return b

    return None


with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, normalized_entity
            FROM entities
            WHERE entity_type = 'domain'
              AND status = 'malicious'
        """)
        rows = cur.fetchall()

        by_brand = {}
        for r in rows:
            brand = brand_for_domain(r["normalized_entity"])
            if not brand:
                continue
            by_brand.setdefault(brand, []).append(r)

        upserted = 0

        for brand, items in by_brand.items():
            items = items[:300]

            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    a = items[i]
                    b = items[j]

                    cur.execute("""
                        INSERT INTO entity_edges (
                            source_entity_id,
                            target_entity_id,
                            edge_type,
                            weight,
                            confidence,
                            sources,
                            metadata
                        )
                        VALUES (
                            %s,
                            %s,
                            'shared_impersonated_brand',
                            65,
                            80,
                            '["entity_graph_v3_brand_clusters"]'::jsonb,
                            jsonb_build_object(
                                'brand', %s::text,
                                'source_domain', %s::text,
                                'target_domain', %s::text,
                                'reason', 'malicious domains impersonate the same brand'
                            )
                        )
                        ON CONFLICT (source_entity_id, target_entity_id, edge_type)
                        DO UPDATE SET
                            last_seen_at = now(),
                            seen_count = entity_edges.seen_count + 1,
                            weight = GREATEST(entity_edges.weight, EXCLUDED.weight),
                            confidence = GREATEST(entity_edges.confidence, EXCLUDED.confidence)
                    """, (
                        a["id"],
                        b["id"],
                        brand,
                        a["normalized_entity"],
                        b["normalized_entity"],
                    ))
                    upserted += 1

        conn.commit()

        print(json.dumps({
            "brands_found": {k: len(v) for k, v in by_brand.items()},
            "brand_cluster_edges_upserted": upserted
        }, indent=2))
