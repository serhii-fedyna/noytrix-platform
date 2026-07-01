from __future__ import annotations

import json
from scamshield.intelligence.postgres_intelligence import connect


with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE entities
            SET
                reputation_score = CASE
                    WHEN status IN ('trusted') THEN 100
                    WHEN status IN ('safe') THEN 80
                    WHEN status IN ('observed') THEN 50
                    WHEN status IN ('suspicious') THEN 30
                    WHEN status IN ('danger') THEN 15
                    WHEN status IN ('malicious') THEN 0
                    ELSE 50
                END,
                metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object(
                    'reputation',
                    jsonb_build_object(
                        'version', 'v1',
                        'score', CASE
                            WHEN status IN ('trusted') THEN 100
                            WHEN status IN ('safe') THEN 80
                            WHEN status IN ('observed') THEN 50
                            WHEN status IN ('suspicious') THEN 30
                            WHEN status IN ('danger') THEN 15
                            WHEN status IN ('malicious') THEN 0
                            ELSE 50
                        END,
                        'basis', 'status_based_initial_reputation',
                        'updated_at', now()
                    )
                )
        """)
        updated = cur.rowcount
        conn.commit()

        print(json.dumps({"reputation_updated": updated}, indent=2))
