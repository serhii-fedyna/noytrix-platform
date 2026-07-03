from __future__ import annotations

import json
from typing import Any, Dict

from scamshield.intelligence.postgres_intelligence import connect, init_schema


GRAPH_REPUTATION_VERSION = "v4"

PROPAGATION_EDGE_TYPES = (
    "domain_part_of_campaign",
    "shared_impersonated_brand",
    "shared_threat_sources",
    "url_belongs_to_domain",
    "shared_wallet_cluster",
    "shared_wallet_threat_source",
    "network_part_of_campaign",
)


GRAPH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entity_edges (
    id BIGSERIAL PRIMARY KEY,
    source_entity_id BIGINT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_entity_id BIGINT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    edge_type TEXT NOT NULL,
    weight INTEGER NOT NULL DEFAULT 50,
    confidence INTEGER NOT NULL DEFAULT 50,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    seen_count BIGINT NOT NULL DEFAULT 1,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(source_entity_id, target_entity_id, edge_type)
);

CREATE INDEX IF NOT EXISTS idx_entity_edges_source ON entity_edges(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_edges_target ON entity_edges(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_edges_type ON entity_edges(edge_type);
CREATE INDEX IF NOT EXISTS idx_entity_edges_strength ON entity_edges(weight DESC, confidence DESC);
"""


def install_graph_schema() -> None:
    init_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(GRAPH_SCHEMA_SQL)
        conn.commit()


def update_graph_metrics() -> Dict[str, Any]:
    install_graph_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH metrics AS (
                    SELECT
                        e.id,
                        COUNT(ed.id)::int AS edge_count,
                        COUNT(neighbor.id) FILTER (
                            WHERE lower(COALESCE(neighbor.status, '')) IN ('malicious','scam','danger','critical','high','blocked')
                        )::int AS malicious_neighbors,
                        COALESCE(MAX(ed.weight), 0)::int AS max_edge_weight,
                        COALESCE(MAX(ed.confidence), 0)::int AS max_edge_confidence
                    FROM entities e
                    LEFT JOIN entity_edges ed
                      ON ed.source_entity_id = e.id OR ed.target_entity_id = e.id
                    LEFT JOIN entities neighbor
                      ON neighbor.id = CASE
                        WHEN ed.source_entity_id = e.id THEN ed.target_entity_id
                        ELSE ed.source_entity_id
                      END
                    GROUP BY e.id
                )
                UPDATE entities e
                SET metadata = COALESCE(e.metadata, '{}'::jsonb) || jsonb_build_object(
                    'graph',
                    jsonb_build_object(
                        'version', %s::text,
                        'edge_count', m.edge_count,
                        'malicious_neighbors', m.malicious_neighbors,
                        'max_edge_weight', m.max_edge_weight,
                        'max_edge_confidence', m.max_edge_confidence,
                        'updated_at', now()
                    )
                )
                FROM metrics m
                WHERE e.id = m.id
                """,
                (GRAPH_REPUTATION_VERSION,),
            )
            rows = cur.rowcount
            conn.commit()
    return {"graph_metrics_updated": rows}


def update_reputation_with_time_decay() -> Dict[str, Any]:
    install_graph_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH features AS (
                    SELECT
                        e.id,
                        COALESCE(e.reputation_score, 50)::int AS old_reputation,
                        lower(COALESCE(e.status, 'unknown')) AS status_l,
                        COALESCE(e.risk_score, 0)::int AS risk_score,
                        COALESCE(e.confidence, 0)::int AS confidence,
                        COALESCE(e.source_count, 0)::int AS source_count,
                        COALESCE(e.seen_count, 0)::bigint AS seen_count,
                        COALESCE(NULLIF(e.metadata->'graph'->>'malicious_neighbors', '')::int, 0) AS malicious_neighbors,
                        COALESCE(NULLIF(e.metadata->'risk_propagation'->>'propagated_risk', '')::int, 0) AS propagated_risk,
                        CASE
                            WHEN e.last_seen_at IS NULL THEN 365
                            ELSE GREATEST(0, EXTRACT(DAY FROM (now() - e.last_seen_at))::int)
                        END AS age_days,
                        CASE WHEN COALESCE(e.metadata, '{}'::jsonb) ? 'trust_override' THEN true ELSE false END AS trust_override
                    FROM entities e
                ),
                scored AS (
                    SELECT
                        id,
                        old_reputation,
                        GREATEST(
                            0,
                            LEAST(
                                100,
                                CASE
                                    WHEN trust_override THEN 95
                                    WHEN status_l IN ('trusted','allowlisted','allowlist') THEN 96
                                    WHEN status_l = 'safe' THEN 82
                                    WHEN status_l IN ('malicious','scam','critical','blocked') THEN 4
                                    WHEN status_l IN ('danger','high') THEN 12
                                    WHEN status_l = 'suspicious' THEN 32
                                    WHEN status_l IN ('observed','quarantine') THEN 50
                                    ELSE 50
                                END
                                + CASE
                                    WHEN status_l IN ('safe','trusted','allowlisted','allowlist') THEN LEAST(8, confidence / 15)
                                    ELSE 0
                                  END
                                + LEAST(8, source_count * 2)
                                + LEAST(5, seen_count / 10)
                                - CASE
                                    WHEN status_l IN ('malicious','scam','critical','blocked','danger','high') THEN LEAST(18, confidence / 6)
                                    ELSE 0
                                  END
                                - CASE
                                    WHEN malicious_neighbors >= 10 THEN 25
                                    WHEN malicious_neighbors >= 3 THEN 12
                                    WHEN malicious_neighbors >= 1 THEN 5
                                    ELSE 0
                                  END
                                - CASE
                                    WHEN propagated_risk >= 85 THEN 24
                                    WHEN propagated_risk >= 70 THEN 16
                                    WHEN propagated_risk >= 45 THEN 8
                                    ELSE 0
                                  END
                                + CASE
                                    WHEN status_l IN ('observed','quarantine','unknown') AND age_days >= 180 THEN 8
                                    WHEN status_l = 'suspicious' AND age_days >= 180 THEN 5
                                    ELSE 0
                                  END
                                - CASE
                                    WHEN status_l IN ('malicious','scam','critical','blocked','danger','high') AND age_days <= 30 THEN 6
                                    ELSE 0
                                  END
                            )
                        )::int AS new_reputation,
                        jsonb_build_object(
                            'version', %s::text,
                            'basis', 'status_confidence_sources_graph_time_decay',
                            'age_days', age_days,
                            'source_count', source_count,
                            'seen_count', seen_count,
                            'malicious_neighbors', malicious_neighbors,
                            'propagated_risk', propagated_risk,
                            'trust_override', trust_override,
                            'updated_at', now()
                        ) AS reputation_meta
                    FROM features
                ),
                updated AS (
                    UPDATE entities e
                    SET reputation_score = s.new_reputation,
                        metadata = COALESCE(e.metadata, '{}'::jsonb) || jsonb_build_object(
                            'reputation',
                            s.reputation_meta || jsonb_build_object('score', s.new_reputation)
                        )
                    FROM scored s
                    WHERE e.id = s.id
                    RETURNING e.id, s.old_reputation, s.new_reputation, s.reputation_meta
                )
                INSERT INTO reputation_history (entity_id, old_score, new_score, reason, metadata)
                SELECT
                    id,
                    old_reputation,
                    new_reputation,
                    'self_learning_time_decay_v4',
                    reputation_meta
                FROM updated
                WHERE old_reputation IS DISTINCT FROM new_reputation
                """,
                (GRAPH_REPUTATION_VERSION,),
            )
            history_rows = cur.rowcount
            conn.commit()
    return {"reputation_history_inserted": history_rows}


def run_graph_risk_propagation() -> Dict[str, Any]:
    install_graph_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH neighbor_risk AS (
                    SELECT
                        e.id AS entity_id,
                        MAX(
                            LEAST(
                                100,
                                COALESCE(n.risk_score, 0)
                                * COALESCE(ed.weight, 0)
                                * COALESCE(ed.confidence, 0)
                                / 10000
                            )
                        )::int AS propagated_risk,
                        COUNT(n.id) FILTER (
                            WHERE lower(COALESCE(n.status, '')) IN ('malicious','scam','danger','critical','high','blocked')
                        )::int AS malicious_neighbors,
                        jsonb_agg(
                            jsonb_build_object(
                                'neighbor', n.normalized_entity,
                                'neighbor_type', n.entity_type,
                                'neighbor_status', n.status,
                                'neighbor_risk', n.risk_score,
                                'edge_type', ed.edge_type,
                                'weight', ed.weight,
                                'confidence', ed.confidence
                            )
                            ORDER BY
                                (COALESCE(n.risk_score, 0) * COALESCE(ed.weight, 0) * COALESCE(ed.confidence, 0)) DESC
                        ) FILTER (WHERE n.id IS NOT NULL) AS top_paths
                    FROM entities e
                    JOIN entity_edges ed
                      ON ed.source_entity_id = e.id OR ed.target_entity_id = e.id
                    JOIN entities n
                      ON n.id = CASE
                        WHEN ed.source_entity_id = e.id THEN ed.target_entity_id
                        ELSE ed.source_entity_id
                      END
                    WHERE lower(COALESCE(n.status, '')) IN ('malicious','scam','danger','critical','high','blocked')
                      AND ed.edge_type = ANY(%s)
                      AND COALESCE(ed.weight, 0) >= 40
                      AND COALESCE(ed.confidence, 0) >= 60
                      AND lower(COALESCE(e.status, '')) NOT IN ('safe','trusted','allowlisted','allowlist')
                      AND COALESCE(e.reputation_score, 50) < 90
                      AND NOT (COALESCE(e.metadata, '{}'::jsonb) ? 'trust_override')
                    GROUP BY e.id
                ),
                updated AS (
                    UPDATE entities e
                    SET
                        risk_score = GREATEST(COALESCE(e.risk_score, 0), COALESCE(nr.propagated_risk, 0)),
                        status = CASE
                            WHEN COALESCE(nr.propagated_risk, 0) >= 85 THEN 'malicious'
                            WHEN COALESCE(nr.propagated_risk, 0) >= 70 THEN 'danger'
                            WHEN COALESCE(nr.propagated_risk, 0) >= 45
                                 AND lower(COALESCE(e.status, '')) IN ('unknown','observed','quarantine','suspicious')
                            THEN 'suspicious'
                            ELSE e.status
                        END,
                        reputation_score = LEAST(
                            COALESCE(e.reputation_score, 50),
                            CASE
                                WHEN COALESCE(nr.propagated_risk, 0) >= 85 THEN 4
                                WHEN COALESCE(nr.propagated_risk, 0) >= 70 THEN 15
                                WHEN COALESCE(nr.propagated_risk, 0) >= 45 THEN 32
                                ELSE COALESCE(e.reputation_score, 50)
                            END
                        ),
                        metadata = COALESCE(e.metadata, '{}'::jsonb) || jsonb_build_object(
                            'risk_propagation',
                            jsonb_build_object(
                                'version', %s::text,
                                'propagated_risk', nr.propagated_risk,
                                'malicious_neighbors', nr.malicious_neighbors,
                                'edge_types', %s::jsonb,
                                'top_paths', COALESCE(nr.top_paths, '[]'::jsonb),
                                'trust_protected', false,
                                'updated_at', now()
                            )
                        )
                    FROM neighbor_risk nr
                    WHERE e.id = nr.entity_id
                    RETURNING e.id
                )
                SELECT COUNT(*) AS updated_count FROM updated
                """,
                (
                    list(PROPAGATION_EDGE_TYPES),
                    GRAPH_REPUTATION_VERSION,
                    json.dumps(list(PROPAGATION_EDGE_TYPES)),
                ),
            )
            row = cur.fetchone()
            updated = int((row or {}).get("updated_count") or 0)
            conn.commit()
    return {
        "risk_propagation_updated": updated,
        "edge_types": list(PROPAGATION_EDGE_TYPES),
    }


def run_reputation_graph_cycle() -> Dict[str, Any]:
    return {
        "schema": "ok" if not install_graph_schema() else "ok",
        "graph_metrics_before": update_graph_metrics(),
        "reputation_before_propagation": update_reputation_with_time_decay(),
        "risk_propagation": run_graph_risk_propagation(),
        "graph_metrics_after": update_graph_metrics(),
        "reputation_after_propagation": update_reputation_with_time_decay(),
    }


if __name__ == "__main__":
    print(json.dumps(run_reputation_graph_cycle(), ensure_ascii=False, indent=2, default=str))
