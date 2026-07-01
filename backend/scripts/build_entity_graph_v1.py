from __future__ import annotations

from urllib.parse import urlparse
import json

from scamshield.intelligence.postgres_intelligence import connect


def extract_host(value: str) -> str:
    v = (value or "").strip().lower()
    if not v:
        return ""

    if "://" not in v:
        v = "https://" + v

    p = urlparse(v)
    host = (p.netloc or "").lower().strip()

    if "@" in host:
        host = host.rsplit("@", 1)[-1]

    if ":" in host:
        host = host.split(":", 1)[0]

    if host.startswith("www."):
        host = host[4:]

    return host


with connect() as conn:
    with conn.cursor() as cur:
        created_domains = 0
        created_edges = 0

        cur.execute("""
            SELECT id, entity, normalized_entity, status, risk_score, confidence
            FROM entities
            WHERE entity_type = 'url'
        """)

        urls = cur.fetchall()

        for u in urls:
            host = extract_host(u["normalized_entity"] or u["entity"])
            if not host:
                continue

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
                    %s, %s, 'domain',
                    'observed',
                    0,
                    0,
                    now(),
                    now(),
                    1,
                    1,
                    '["domain"]'::jsonb,
                    jsonb_build_object(
                        'created_by', 'entity_graph_v1',
                        'reason', 'domain_extracted_from_url'
                    )
                )
                ON CONFLICT (normalized_entity)
                DO NOTHING
                RETURNING id
            """, (host, host))

            inserted = cur.fetchone()
            if inserted:
                domain_id = inserted["id"]
                created_domains += 1
            else:
                cur.execute("""
                    SELECT id
                    FROM entities
                    WHERE normalized_entity = %s
                    LIMIT 1
                """, (host,))
                row = cur.fetchone()
                if not row:
                    continue
                domain_id = row["id"]

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
                    'url_belongs_to_domain',
                    100,
                    95,
                    '["entity_graph_v1"]'::jsonb,
                    jsonb_build_object(
                        'url', %s::text,
                        'domain', %s::text
                    )
                )
                ON CONFLICT (source_entity_id, target_entity_id, edge_type)
                DO UPDATE SET
                    last_seen_at = now(),
                    seen_count = entity_edges.seen_count + 1,
                    weight = GREATEST(entity_edges.weight, EXCLUDED.weight),
                    confidence = GREATEST(entity_edges.confidence, EXCLUDED.confidence)
            """, (
                u["id"],
                domain_id,
                u["normalized_entity"],
                host,
            ))
            created_edges += 1

        conn.commit()

        print(json.dumps({
            "urls_scanned": len(urls),
            "domains_created": created_domains,
            "url_domain_edges_upserted": created_edges
        }, indent=2))
