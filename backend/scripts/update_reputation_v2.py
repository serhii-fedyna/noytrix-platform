from __future__ import annotations

import json
from scamshield.intelligence.postgres_intelligence import connect


with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE entities
            SET
                reputation_score = GREATEST(
                    0,
                    LEAST(
                        100,
                        CASE
                            WHEN status = 'trusted' THEN 100
                            WHEN status = 'safe' THEN 80
                            WHEN status = 'observed' THEN 50
                            WHEN status = 'suspicious' THEN 30
                            WHEN status = 'danger' THEN 15
                            WHEN status = 'malicious' THEN 0
                            ELSE 50
                        END
                        - CASE WHEN COALESCE(source_count, 0) >= 2 AND status = 'malicious' THEN 20 ELSE 0 END
                        - CASE WHEN campaign_id IS NOT NULL AND campaign_id <> '' THEN 25 ELSE 0 END
                        - CASE
                            WHEN (metadata->'graph'->>'malicious_neighbors')::int >= 10 THEN 20
                            WHEN (metadata->'graph'->>'malicious_neighbors')::int >= 3 THEN 10
                            ELSE 0
                          END
                        - CASE
                            WHEN (metadata->'risk_propagation'->>'propagated_risk')::int >= 75 THEN 20
                            WHEN (metadata->'risk_propagation'->>'propagated_risk')::int >= 45 THEN 10
                            ELSE 0
                          END
                    )
                ),
                metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object(
                    'reputation',
                    jsonb_build_object(
                        'version', 'v2',
                        'score', GREATEST(
                            0,
                            LEAST(
                                100,
                                CASE
                                    WHEN status = 'trusted' THEN 100
                                    WHEN status = 'safe' THEN 80
                                    WHEN status = 'observed' THEN 50
                                    WHEN status = 'suspicious' THEN 30
                                    WHEN status = 'danger' THEN 15
                                    WHEN status = 'malicious' THEN 0
                                    ELSE 50
                                END
                                - CASE WHEN COALESCE(source_count, 0) >= 2 AND status = 'malicious' THEN 20 ELSE 0 END
                                - CASE WHEN campaign_id IS NOT NULL AND campaign_id <> '' THEN 25 ELSE 0 END
                                - CASE
                                    WHEN (metadata->'graph'->>'malicious_neighbors')::int >= 10 THEN 20
                                    WHEN (metadata->'graph'->>'malicious_neighbors')::int >= 3 THEN 10
                                    ELSE 0
                                  END
                                - CASE
                                    WHEN (metadata->'risk_propagation'->>'propagated_risk')::int >= 75 THEN 20
                                    WHEN (metadata->'risk_propagation'->>'propagated_risk')::int >= 45 THEN 10
                                    ELSE 0
                                  END
                            )
                        ),
                        'basis', 'status_plus_sources_campaign_graph_propagation',
                        'updated_at', now()
                    )
                )
        """)
        updated = cur.rowcount
        conn.commit()

        print(json.dumps({"reputation_v2_updated": updated}, indent=2))
