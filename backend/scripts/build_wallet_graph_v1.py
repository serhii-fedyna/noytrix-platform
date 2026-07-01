from __future__ import annotations

import json
from scamshield.intelligence.postgres_intelligence import connect


MAX_EDGES_PER_SOURCE = 5000


with connect() as conn:
    with conn.cursor() as cur:
        total_edges = 0

        cur.execute("""
            SELECT source_name, COUNT(DISTINCT e.id) AS cnt
            FROM entity_observations eo
            JOIN entities e ON e.id = eo.entity_id
            WHERE e.entity_type='evm_address'
              AND e.status='malicious'
            GROUP BY source_name
            HAVING COUNT(DISTINCT e.id) >= 2
            ORDER BY cnt DESC
        """)

        sources = cur.fetchall()

        for src in sources:
            source_name = src["source_name"]

            cur.execute("""
                WITH ranked AS (
                    SELECT DISTINCT e.id, e.normalized_entity
                    FROM entity_observations eo
                    JOIN entities e ON e.id = eo.entity_id
                    WHERE e.entity_type='evm_address'
                      AND e.status='malicious'
                      AND eo.source_name = %s
                    ORDER BY e.normalized_entity
                    LIMIT 100
                ),
                pairs AS (
                    SELECT
                        a.id AS source_id,
                        b.id AS target_id,
                        a.normalized_entity AS source_address,
                        b.normalized_entity AS target_address
                    FROM ranked a
                    JOIN ranked b ON a.id < b.id
                    LIMIT %s
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
                    'shared_wallet_threat_source',
                    60,
                    75,
                    jsonb_build_array(%s::text),
                    jsonb_build_object(
                        'reason', 'malicious wallets appear in same threat source',
                        'source_name', %s::text,
                        'source_address', source_address,
                        'target_address', target_address
                    )
                FROM pairs
                ON CONFLICT (source_entity_id, target_entity_id, edge_type)
                DO UPDATE SET
                    last_seen_at = now(),
                    seen_count = entity_edges.seen_count + 1,
                    weight = GREATEST(entity_edges.weight, EXCLUDED.weight),
                    confidence = GREATEST(entity_edges.confidence, EXCLUDED.confidence),
                    metadata = entity_edges.metadata || EXCLUDED.metadata
            """, (source_name, MAX_EDGES_PER_SOURCE, source_name, source_name))

            total_edges += cur.rowcount

        conn.commit()

        print(json.dumps({
            "wallet_graph_sources": len(sources),
            "wallet_edges_upserted": total_edges
        }, indent=2))
