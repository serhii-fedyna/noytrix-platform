from __future__ import annotations

import json
from urllib.parse import urlparse

from scamshield.intelligence.postgres_intelligence import connect


def normalize_domain_from_url(value: str) -> str | None:
    v = (value or "").strip().lower()
    if not v:
        return None

    if "://" not in v:
        parsed = urlparse("https://" + v)
    else:
        parsed = urlparse(v)

    host = parsed.netloc.lower().strip()
    if not host:
        return None

    if "@" in host:
        host = host.rsplit("@", 1)[-1]

    if ":" in host:
        host = host.split(":", 1)[0]

    if host.startswith("www."):
        host = host[4:]

    return host or None


def main() -> None:
    created = 0
    scanned = 0

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, normalized_entity
                FROM entities
                WHERE entity_type = 'url'
                  AND normalized_entity IS NOT NULL
                  AND normalized_entity <> ''
            """)
            urls = cur.fetchall()

            for url_entity in urls:
                scanned += 1
                domain = normalize_domain_from_url(url_entity["normalized_entity"])
                if not domain:
                    continue

                cur.execute("""
                    SELECT id
                    FROM entities
                    WHERE entity_type = 'domain'
                      AND normalized_entity = %s
                    LIMIT 1
                """, (domain,))
                domain_entity = cur.fetchone()

                if not domain_entity:
                    continue

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
                        80,
                        95,
                        '["internal_graph_builder"]'::jsonb,
                        jsonb_build_object(
                            'builder', 'build_entity_edges_v1',
                            'url', %s,
                            'domain', %s
                        )
                    )
                    ON CONFLICT (source_entity_id, target_entity_id, edge_type)
                    DO UPDATE SET
                        weight = GREATEST(entity_edges.weight, EXCLUDED.weight),
                        confidence = GREATEST(entity_edges.confidence, EXCLUDED.confidence),
                        last_seen_at = now(),
                        seen_count = entity_edges.seen_count + 1
                """, (
                    url_entity["id"],
                    domain_entity["id"],
                    url_entity["normalized_entity"],
                    domain,
                ))
                created += 1

        conn.commit()

    print(json.dumps({
        "scanned_urls": scanned,
        "domain_url_edges_upserted": created
    }, indent=2))


if __name__ == "__main__":
    main()
