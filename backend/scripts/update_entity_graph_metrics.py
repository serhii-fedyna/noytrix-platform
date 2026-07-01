from __future__ import annotations

import json
from scamshield.intelligence.postgres_intelligence import connect


with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            WITH graph_stats AS (
                SELECT
                    e.id,
                    COUNT(ed.id) AS edge_count,
                    COUNT(neighbor.id) FILTER (WHERE neighbor.status = 'malicious') AS malicious_neighbors,
                    MAX(ed.weight) AS max_edge_weight,
                    MAX(ed.confidence) AS max_edge_confidence
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
                    'edge_count', COALESCE(gs.edge_count, 0),
                    'malicious_neighbors', COALESCE(gs.malicious_neighbors, 0),
                    'max_edge_weight', COALESCE(gs.max_edge_weight, 0),
                    'max_edge_confidence', COALESCE(gs.max_edge_confidence, 0),
                    'updated_at', now()
                )
            )
            FROM graph_stats gs
            WHERE e.id = gs.id
        """)
        updated = cur.rowcount
        conn.commit()

        print(json.dumps({"graph_metrics_updated": updated}, indent=2))
