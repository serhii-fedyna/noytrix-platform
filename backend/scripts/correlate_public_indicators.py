from __future__ import annotations

import json
from scamshield.intelligence.postgres_intelligence import connect


def main() -> None:
    sql = """
    WITH grouped AS (
        SELECT
            normalized_value,
            indicator_type,
            COUNT(DISTINCT source_name) AS source_count,
            COUNT(*) AS raw_count,
            MAX(risk_score) AS max_risk_score,
            MAX(confidence) AS max_confidence,
            MIN(first_seen_at) AS first_seen_at,
            MAX(last_seen_at) AS last_seen_at,
            jsonb_agg(DISTINCT source_name) AS sources
        FROM raw_indicators
        WHERE normalized_value IS NOT NULL
          AND normalized_value <> ''
          AND indicator_type IS NOT NULL
        GROUP BY normalized_value, indicator_type
    ),
    scored AS (
        SELECT
            *,
            LEAST(100, COALESCE(max_risk_score, 0) + GREATEST(0, source_count - 1) * 10) AS correlated_risk,
            LEAST(100, COALESCE(max_confidence, 50) + GREATEST(0, source_count - 1) * 8) AS correlated_confidence,
            CASE
                WHEN source_count >= 3 THEN 'multi_source_confirmed'
                WHEN source_count = 2 THEN 'dual_source_confirmed'
                ELSE 'single_source_observed'
            END AS correlation_level
        FROM grouped
    )
    UPDATE entities e
    SET
        source_count = GREATEST(COALESCE(e.source_count, 0), s.source_count),
        seen_count = GREATEST(COALESCE(e.seen_count, 0), s.raw_count),
        risk_score = GREATEST(COALESCE(e.risk_score, 0), s.correlated_risk),
        confidence = GREATEST(COALESCE(e.confidence, 0), s.correlated_confidence),
        first_seen_at = LEAST(COALESCE(e.first_seen_at, s.first_seen_at), s.first_seen_at),
        last_seen_at = GREATEST(COALESCE(e.last_seen_at, s.last_seen_at), s.last_seen_at),
        tags = COALESCE(e.tags, '[]'::jsonb) || to_jsonb(s.correlation_level),
        metadata = COALESCE(e.metadata, '{}'::jsonb) || jsonb_build_object(
            'correlation',
            jsonb_build_object(
                'source_count', s.source_count,
                'raw_count', s.raw_count,
                'sources', s.sources,
                'level', s.correlation_level,
                'correlated_at', now()
            )
        )
    FROM scored s
    WHERE e.normalized_entity = s.normalized_value
      AND e.entity_type = s.indicator_type;
    """

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            updated = cur.rowcount
        conn.commit()

    print(json.dumps({"correlated_entities": updated}, indent=2))


if __name__ == "__main__":
    main()
