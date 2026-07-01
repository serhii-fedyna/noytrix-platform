from __future__ import annotations

import json
from scamshield.intelligence.postgres_intelligence import connect


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
                  AND ed.edge_type IN (
                      'shared_impersonated_brand',
                      'domain_part_of_campaign'
                  )
                  AND COALESCE(ed.weight, 0) >= 80
                  AND COALESCE(ed.confidence, 0) >= 80
                GROUP BY e.id
            )
            UPDATE entities e
            SET
                risk_score = CASE
                    WHEN e.status IN ('safe','trusted') THEN e.risk_score
                    ELSE GREATEST(COALESCE(e.risk_score, 0), COALESCE(nr.propagated_risk, 0))
                END,
                status = CASE
                    WHEN e.status IN ('safe','trusted') THEN e.status
                    WHEN COALESCE(e.risk_score, 0) >= 85 THEN e.status
                    WHEN COALESCE(nr.propagated_risk, 0) >= 75 THEN 'danger'
                    WHEN COALESCE(nr.propagated_risk, 0) >= 45 THEN 'suspicious'
                    ELSE e.status
                END,
                metadata = COALESCE(e.metadata, '{}'::jsonb) || jsonb_build_object(
                    'risk_propagation',
                    jsonb_build_object(
                        'version', 'v2',
                        'propagated_risk', nr.propagated_risk,
                        'malicious_neighbors', nr.malicious_neighbors,
                        'updated_at', now()
                    )
                )
            FROM neighbor_risk nr
            WHERE e.id = nr.entity_id
        """)
        updated = cur.rowcount
        conn.commit()

        print(json.dumps({
            "risk_propagation_updated": updated
        }, indent=2))
