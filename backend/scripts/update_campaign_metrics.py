from __future__ import annotations

import json
from scamshield.intelligence.postgres_intelligence import connect


with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            WITH campaign_stats AS (
                SELECT
                    c.id AS campaign_id,
                    COUNT(d.id) AS domains_count,
                    AVG(d.risk_score)::int AS avg_domain_risk,
                    MAX(d.risk_score) AS max_domain_risk,
                    COUNT(ed.id) AS edge_count
                FROM entities c
                JOIN entity_edges ed ON ed.target_entity_id = c.id
                JOIN entities d ON d.id = ed.source_entity_id
                WHERE c.entity_type = 'campaign'
                  AND ed.edge_type = 'domain_part_of_campaign'
                GROUP BY c.id
            )
            UPDATE entities c
            SET
                risk_score = GREATEST(c.risk_score, cs.max_domain_risk),
                confidence = GREATEST(c.confidence, 85),
                metadata = COALESCE(c.metadata, '{}'::jsonb) || jsonb_build_object(
                    'campaign_metrics',
                    jsonb_build_object(
                        'domains_count', cs.domains_count,
                        'avg_domain_risk', cs.avg_domain_risk,
                        'max_domain_risk', cs.max_domain_risk,
                        'edge_count', cs.edge_count,
                        'updated_at', now()
                    )
                )
            FROM campaign_stats cs
            WHERE c.id = cs.campaign_id
        """)
        updated = cur.rowcount
        conn.commit()

        print(json.dumps({"campaign_metrics_updated": updated}, indent=2))
