from __future__ import annotations

import json
from scamshield.intelligence.postgres_intelligence import connect


with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            WITH pairs AS (
                SELECT
                    a.id AS source_id,
                    b.id AS target_id,
                    a.normalized_entity AS source_domain,
                    b.normalized_entity AS target_domain,
                    a.metadata->'correlation'->'sources' AS sources,
                    a.source_count AS source_count
                FROM entities a
                JOIN entities b
                  ON a.id < b.id
                 AND a.entity_type = 'domain'
                 AND b.entity_type = 'domain'
                 AND a.status = 'malicious'
                 AND b.status = 'malicious'
                 AND COALESCE(a.metadata->'correlation'->'sources', '[]'::jsonb)
                     = COALESCE(b.metadata->'correlation'->'sources', '[]'::jsonb)
                 AND COALESCE(a.source_count, 0) >= 2
                 AND COALESCE(b.source_count, 0) >= 2
                LIMIT 5000
            )
            INSERT INTO entity_edges (
                source_entity_id,
                target_entity_id,
                edge_type,
                weight,
                confidence,
                sources,
                metadata
            )
            SELECT
                source_id,
                target_id,
                'shared_threat_sources',
                40,
                70,
                sources,
                jsonb_build_object(
                    'builder', 'entity_graph_v2_source_clusters',
                    'source_domain', source_domain,
                    'target_domain', target_domain,
                    'reason', 'domains confirmed by same threat intelligence sources',
                    'source_count', source_count
                )
            FROM pairs
            ON CONFLICT (source_entity_id, target_entity_id, edge_type)
            DO UPDATE SET
                last_seen_at = now(),
                seen_count = entity_edges.seen_count + 1,
                weight = GREATEST(entity_edges.weight, EXCLUDED.weight),
                confidence = GREATEST(entity_edges.confidence, EXCLUDED.confidence)
        """)
        created = cur.rowcount
        conn.commit()

        print(json.dumps({
            "shared_threat_source_edges_upserted": created
        }, indent=2))
