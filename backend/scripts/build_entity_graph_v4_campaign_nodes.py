from __future__ import annotations

import json
from scamshield.intelligence.postgres_intelligence import connect


with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT metadata->>'brand' AS brand
            FROM entity_edges
            WHERE edge_type = 'shared_impersonated_brand'
              AND metadata->>'brand' IS NOT NULL
        """)
        brands = [r["brand"] for r in cur.fetchall()]

        campaigns_created = 0
        campaign_edges = 0
        domains_updated = 0

        for brand in brands:
            campaign_id = f"campaign:brand_impersonation:{brand}"
            campaign_entity = campaign_id

            cur.execute("""
                INSERT INTO entities (
                    entity,
                    normalized_entity,
                    entity_type,
                    status,
                    risk_score,
                    confidence,
                    first_seen_at,
                    last_seen_at,
                    seen_count,
                    source_count,
                    roles,
                    metadata
                )
                VALUES (
                    %s, %s, 'campaign',
                    'malicious',
                    85,
                    80,
                    now(),
                    now(),
                    1,
                    1,
                    '["campaign"]'::jsonb,
                    jsonb_build_object(
                        'created_by', 'entity_graph_v4_campaign_nodes',
                        'campaign_type', 'brand_impersonation',
                        'brand', %s::text
                    )
                )
                ON CONFLICT (normalized_entity)
                DO UPDATE SET
                    last_seen_at = now(),
                    status = 'malicious',
                    risk_score = GREATEST(entities.risk_score, 85),
                    confidence = GREATEST(entities.confidence, 80),
                    metadata = entities.metadata || EXCLUDED.metadata
                RETURNING id
            """, (campaign_entity, campaign_entity, brand))

            campaign_row = cur.fetchone()
            campaign_db_id = campaign_row["id"]
            campaigns_created += 1

            cur.execute("""
                WITH brand_domains AS (
                    SELECT DISTINCT e.id, e.normalized_entity
                    FROM entities e
                    JOIN entity_edges ed
                      ON ed.source_entity_id = e.id OR ed.target_entity_id = e.id
                    WHERE ed.edge_type = 'shared_impersonated_brand'
                      AND ed.metadata->>'brand' = %s
                      AND e.entity_type = 'domain'
                      AND e.status = 'malicious'
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
                    id,
                    %s,
                    'domain_part_of_campaign',
                    85,
                    85,
                    '["entity_graph_v4_campaign_nodes"]'::jsonb,
                    jsonb_build_object(
                        'campaign_id', %s::text,
                        'brand', %s::text,
                        'domain', normalized_entity
                    )
                FROM brand_domains
                ON CONFLICT (source_entity_id, target_entity_id, edge_type)
                DO UPDATE SET
                    last_seen_at = now(),
                    seen_count = entity_edges.seen_count + 1,
                    weight = GREATEST(entity_edges.weight, EXCLUDED.weight),
                    confidence = GREATEST(entity_edges.confidence, EXCLUDED.confidence)
            """, (brand, campaign_db_id, campaign_id, brand))
            campaign_edges += cur.rowcount

            cur.execute("""
                UPDATE entities e
                SET campaign_id = %s,
                    metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object(
                        'campaign_assignment',
                        jsonb_build_object(
                            'campaign_id', %s::text,
                            'brand', %s::text,
                            'assigned_by', 'entity_graph_v4_campaign_nodes',
                            'assigned_at', now()
                        )
                    )
                WHERE e.id IN (
                    SELECT DISTINCT e2.id
                    FROM entities e2
                    JOIN entity_edges ed
                      ON ed.source_entity_id = e2.id OR ed.target_entity_id = e2.id
                    WHERE ed.edge_type = 'shared_impersonated_brand'
                      AND ed.metadata->>'brand' = %s
                      AND e2.entity_type = 'domain'
                      AND e2.status = 'malicious'
                )
            """, (campaign_id, campaign_id, brand, brand))
            domains_updated += cur.rowcount

        conn.commit()

        print(json.dumps({
            "brands_processed": len(brands),
            "campaign_nodes_upserted": campaigns_created,
            "domain_campaign_edges_upserted": campaign_edges,
            "domains_assigned_campaign_id": domains_updated
        }, indent=2))
