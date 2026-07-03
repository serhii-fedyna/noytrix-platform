from __future__ import annotations

import json
import re
from typing import Any, Dict
from urllib.parse import urlparse

from scamshield.intelligence.postgres_intelligence import connect, guess_entity_type, init_schema, normalize_entity
from scamshield.intelligence.source_reputation import source_trust_from_stats


MALICIOUS_STATUSES = {"malicious", "scam", "danger", "critical", "high", "blocked"}
SAFE_STATUSES = {"safe", "trusted", "allowlisted", "allowlist"}


def canonical_indicator(value: str, indicator_type: str | None = None) -> Dict[str, str]:
    raw = (value or "").strip()
    typ = (indicator_type or guess_entity_type(raw) or "unknown").strip().lower()
    normalized = normalize_entity(raw)

    if typ in {"url", "domain"} and raw:
        url_value = raw if raw.startswith(("http://", "https://")) else f"https://{raw}"
        try:
            parsed = urlparse(url_value)
            host = (parsed.netloc or "").lower().strip()
            if host.startswith("www."):
                host = host[4:]
            path = (parsed.path or "").rstrip("/")
            query = f"?{parsed.query}" if parsed.query else ""
            if typ == "domain":
                normalized = host or normalized
            elif host:
                normalized = f"{host}{path}{query}".strip("/")
        except Exception:
            pass

    if typ in {"evm_address", "wallet", "contract"}:
        normalized = normalized.lower()

    if not typ or typ == "unknown":
        typ = guess_entity_type(normalized)

    return {
        "raw": raw,
        "normalized": normalized,
        "entity_type": typ,
        "dedupe_key": f"{typ}:{normalized}" if normalized else "",
    }


def status_rank(status: str) -> int:
    s = str(status or "").lower()
    if s in MALICIOUS_STATUSES:
        return 100
    if s in {"suspicious", "observed", "quarantine"}:
        return 50
    if s in SAFE_STATUSES:
        return 10
    return 0


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS source_feeds (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL DEFAULT 'public_database',
    url TEXT,
    trust_level INTEGER NOT NULL DEFAULT 50,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_import_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS raw_indicators (
    id BIGSERIAL PRIMARY KEY,
    feed_id BIGINT REFERENCES source_feeds(id) ON DELETE SET NULL,
    source_name TEXT NOT NULL,
    raw_value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    indicator_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'quarantine',
    confidence INTEGER NOT NULL DEFAULT 50,
    risk_score INTEGER NOT NULL DEFAULT 0,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    seen_count INTEGER NOT NULL DEFAULT 1,
    raw_record JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(source_name, normalized_value, indicator_type)
);

ALTER TABLE entities ADD COLUMN IF NOT EXISTS dedupe_key TEXT;
ALTER TABLE raw_indicators ADD COLUMN IF NOT EXISTS dedupe_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_dedupe_key
ON entities(dedupe_key)
WHERE dedupe_key IS NOT NULL AND dedupe_key <> '';

CREATE INDEX IF NOT EXISTS idx_raw_indicators_dedupe_key
ON raw_indicators(dedupe_key);

CREATE TABLE IF NOT EXISTS entity_aliases (
    id BIGSERIAL PRIMARY KEY,
    entity_id BIGINT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    alias_value TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    source_name TEXT NOT NULL DEFAULT 'unknown',
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    seen_count BIGINT NOT NULL DEFAULT 1,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(normalized_alias, alias_type)
);

CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity_id ON entity_aliases(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_source ON entity_aliases(source_name);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_norm ON entity_aliases(normalized_alias, alias_type);

CREATE TABLE IF NOT EXISTS indicator_observations (
    id BIGSERIAL PRIMARY KEY,
    raw_indicator_id BIGINT REFERENCES raw_indicators(id) ON DELETE SET NULL,
    entity_id BIGINT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    indicator_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'observed',
    risk_score INTEGER NOT NULL DEFAULT 0,
    confidence INTEGER NOT NULL DEFAULT 0,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(raw_indicator_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_indicator_observations_entity ON indicator_observations(entity_id);
CREATE INDEX IF NOT EXISTS idx_indicator_observations_source ON indicator_observations(source_name);
CREATE INDEX IF NOT EXISTS idx_indicator_observations_norm ON indicator_observations(normalized_value, indicator_type);

CREATE TABLE IF NOT EXISTS source_reputation (
    source_name TEXT PRIMARY KEY,
    trust_score INTEGER NOT NULL DEFAULT 50,
    true_positive_count BIGINT NOT NULL DEFAULT 0,
    false_positive_count BIGINT NOT NULL DEFAULT 0,
    raw_indicator_count BIGINT NOT NULL DEFAULT 0,
    promoted_entity_count BIGINT NOT NULL DEFAULT 0,
    last_seen_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
"""


def install_schema() -> None:
    init_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()


def backfill_dedupe_keys(batch_limit: int = 250000) -> Dict[str, Any]:
    install_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH batch AS (
                    SELECT id
                    FROM raw_indicators
                    WHERE COALESCE(dedupe_key, '') = ''
                      AND COALESCE(normalized_value, '') <> ''
                      AND COALESCE(indicator_type, '') <> ''
                    LIMIT %s
                )
                UPDATE raw_indicators r
                SET dedupe_key = lower(r.indicator_type) || ':' || lower(r.normalized_value)
                FROM batch
                WHERE r.id = batch.id
                """,
                (int(batch_limit),),
            )
            raw_count = cur.rowcount

            cur.execute(
                """
                WITH batch AS (
                    SELECT id
                    FROM entities
                    WHERE COALESCE(dedupe_key, '') = ''
                      AND COALESCE(normalized_entity, '') <> ''
                      AND COALESCE(entity_type, '') <> ''
                    LIMIT %s
                )
                UPDATE entities e
                SET dedupe_key = lower(e.entity_type) || ':' || lower(e.normalized_entity)
                FROM batch
                WHERE e.id = batch.id
                """,
                (int(batch_limit),),
            )
            entity_count = cur.rowcount

            conn.commit()

    return {
        "raw_indicators_backfilled": raw_count,
        "entities_backfilled": entity_count,
    }


def link_aliases_and_observations(batch_limit: int = 250000) -> Dict[str, Any]:
    install_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO entity_aliases (
                    entity_id, alias_value, normalized_alias, alias_type, source_name, metadata
                )
                SELECT
                    x.entity_id,
                    x.raw_value,
                    x.normalized_value,
                    x.indicator_type,
                    x.source_name,
                    x.metadata
                FROM (
                    SELECT DISTINCT ON (r.normalized_value, r.indicator_type)
                        e.id AS entity_id,
                        r.raw_value,
                        r.normalized_value,
                        r.indicator_type,
                        r.source_name,
                        jsonb_build_object(
                            'raw_indicator_id', r.id,
                            'dedupe_key', r.dedupe_key,
                            'status', r.status,
                            'risk_score', r.risk_score,
                            'confidence', r.confidence
                        ) AS metadata
                    FROM raw_indicators r
                    JOIN entities e
                      ON e.dedupe_key = r.dedupe_key
                    WHERE COALESCE(r.dedupe_key, '') <> ''
                    ORDER BY r.normalized_value, r.indicator_type, r.risk_score DESC, r.confidence DESC, r.seen_count DESC
                    LIMIT %s
                ) x
                ON CONFLICT (normalized_alias, alias_type)
                DO UPDATE SET
                    last_seen_at = now(),
                    seen_count = entity_aliases.seen_count + 1,
                    metadata = entity_aliases.metadata || EXCLUDED.metadata
                """,
                (int(batch_limit),),
            )
            alias_rows = cur.rowcount

            cur.execute(
                """
                INSERT INTO indicator_observations (
                    raw_indicator_id, entity_id, source_name, normalized_value,
                    indicator_type, status, risk_score, confidence, metadata
                )
                SELECT
                    r.id,
                    e.id,
                    r.source_name,
                    r.normalized_value,
                    r.indicator_type,
                    r.status,
                    r.risk_score,
                    r.confidence,
                    jsonb_build_object(
                        'dedupe_key', r.dedupe_key,
                        'raw_record', r.raw_record,
                        'metadata', r.metadata
                    )
                FROM raw_indicators r
                JOIN entities e
                  ON e.dedupe_key = r.dedupe_key
                WHERE COALESCE(r.dedupe_key, '') <> ''
                LIMIT %s
                ON CONFLICT (raw_indicator_id, entity_id)
                DO UPDATE SET
                    observed_at = now(),
                    status = EXCLUDED.status,
                    risk_score = GREATEST(indicator_observations.risk_score, EXCLUDED.risk_score),
                    confidence = GREATEST(indicator_observations.confidence, EXCLUDED.confidence),
                    metadata = indicator_observations.metadata || EXCLUDED.metadata
                """,
                (int(batch_limit),),
            )
            observation_rows = cur.rowcount
            conn.commit()

    return {
        "aliases_linked": alias_rows,
        "observations_linked": observation_rows,
    }


def refresh_source_reputation() -> Dict[str, Any]:
    install_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH source_stats AS (
                    SELECT
                        r.source_name,
                        COUNT(*)::bigint AS raw_indicator_count,
                        COUNT(DISTINCT io.entity_id)::bigint AS promoted_entity_count,
                        AVG(r.confidence)::float AS avg_confidence,
                        AVG(r.risk_score)::float AS avg_risk_score,
                        MAX(r.last_seen_at) AS last_seen_at
                    FROM raw_indicators r
                    LEFT JOIN indicator_observations io
                      ON io.raw_indicator_id = r.id
                    GROUP BY r.source_name
                ),
                status_meta AS (
                    SELECT
                        source_name,
                        jsonb_object_agg(status, cnt) AS status_counts
                    FROM (
                        SELECT source_name, status, COUNT(*) AS cnt
                        FROM raw_indicators
                        GROUP BY source_name, status
                    ) x
                    GROUP BY source_name
                )
                INSERT INTO source_reputation (
                    source_name, trust_score, raw_indicator_count,
                    promoted_entity_count, last_seen_at, metadata
                )
                SELECT
                    s.source_name,
                    LEAST(
                        98,
                        GREATEST(
                            20,
                            35
                            + LEAST(20, (s.raw_indicator_count / 100000)::int)
                            + LEAST(15, (s.promoted_entity_count / 250)::int)
                            + LEAST(15, (COALESCE(s.avg_confidence, 0) / 8)::int)
                            + CASE
                                WHEN COALESCE(s.avg_risk_score, 0) >= 70 THEN 8
                                WHEN COALESCE(s.avg_risk_score, 0) >= 40 THEN 4
                                ELSE 0
                              END
                        )
                    ),
                    s.raw_indicator_count,
                    s.promoted_entity_count,
                    s.last_seen_at,
                    jsonb_build_object(
                        'status_counts', COALESCE(m.status_counts, '{}'::jsonb),
                        'avg_confidence', COALESCE(s.avg_confidence, 0),
                        'avg_risk_score', COALESCE(s.avg_risk_score, 0),
                        'scoring_version', 'source_reputation_v1'
                    )
                FROM source_stats s
                LEFT JOIN status_meta m
                  ON m.source_name = s.source_name
                ON CONFLICT (source_name)
                DO UPDATE SET
                    trust_score = EXCLUDED.trust_score,
                    raw_indicator_count = EXCLUDED.raw_indicator_count,
                    promoted_entity_count = EXCLUDED.promoted_entity_count,
                    last_seen_at = EXCLUDED.last_seen_at,
                    metadata = source_reputation.metadata || EXCLUDED.metadata
                """
            )
            rows = cur.rowcount
            conn.commit()

    return {"source_reputation_refreshed": rows}


def preview_source_trust(stats: Dict[str, Any]) -> Dict[str, Any]:
    return source_trust_from_stats(stats)


def run_upgrade(batch_limit: int = 250000) -> Dict[str, Any]:
    install_schema()
    result = {
        "schema": "ok",
        "dedupe": backfill_dedupe_keys(batch_limit),
        "links": link_aliases_and_observations(batch_limit),
        "source_reputation": refresh_source_reputation(),
    }
    return result


if __name__ == "__main__":
    print(json.dumps(run_upgrade(), ensure_ascii=False, indent=2))
