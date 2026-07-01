from __future__ import annotations

import json
from scamshield.intelligence.postgres_intelligence import connect


ALLOWED_EDGE_TYPES = (
    "domain_part_of_campaign",
    "shared_impersonated_brand",
)


with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("""
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
                    COUNT(n.id) FILTER (WHERE n.status = 'malicious') AS malicious_neighbors
                FROM entities e
                JOIN entity_edges ed
                  ON ed.source_entity_id = e.id OR ed.target_entity_id = e.id
                JOIN entities n
                  ON n.id = CASE
                    WHEN ed.source_entity_id = e.id THEN ed.target_entity_id
                    ELSE ed.source_entity_id
                  END
                WHERE n.status = 'malicious'
                  AND ed.edge_type = ANY(%s)
                  AND COALESCE(ed.weight, 0) >= 80
                  AND COALESCE(ed.confidence, 0) >= 80

                  -- Trust Engine protection:
                  AND e.status NOT IN ('safe','trusted')
                  AND COALESCE(e.reputation_score, 0) < 90
                  AND NOT (COALESCE(e.metadata, '{}'::jsonb) ? 'trust_override')
                GROUP BY e.id
            )
            UPDATE entities e
            SET
                risk_score = GREATEST(COALESCE(e.risk_score, 0), COALESCE(nr.propagated_risk, 0)),
                status = CASE
                    WHEN COALESCE(nr.propagated_risk, 0) >= 85 THEN 'malicious'
                    WHEN COALESCE(nr.propagated_risk, 0) >= 70 THEN 'danger'
                    WHEN COALESCE(nr.propagated_risk, 0) >= 45 THEN 'suspicious'
                    ELSE e.status
                END,
                reputation_score = LEAST(
                    COALESCE(e.reputation_score, 50),
                    CASE
                        WHEN COALESCE(nr.propagated_risk, 0) >= 85 THEN 0
                        WHEN COALESCE(nr.propagated_risk, 0) >= 70 THEN 15
                        WHEN COALESCE(nr.propagated_risk, 0) >= 45 THEN 30
                        ELSE COALESCE(e.reputation_score, 50)
                    END
                ),
                metadata = COALESCE(e.metadata, '{}'::jsonb) || jsonb_build_object(
                    'risk_propagation',
                    jsonb_build_object(
                        'version', 'v3',
                        'propagated_risk', nr.propagated_risk,
                        'malicious_neighbors', nr.malicious_neighbors,
                        'allowed_edge_types', %s::jsonb,
                        'trust_protected', false,
                        'updated_at', now()
                    )
                )
            FROM neighbor_risk nr
            WHERE e.id = nr.entity_id
        """, (list(ALLOWED_EDGE_TYPES), json.dumps(list(ALLOWED_EDGE_TYPES))))

        updated = cur.rowcount
        conn.commit()

        print(json.dumps({
            "risk_propagation_v3_updated": updated,
            "allowed_edge_types": list(ALLOWED_EDGE_TYPES),
            "trust_protection": True
        }, indent=2))
