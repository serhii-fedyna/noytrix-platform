from __future__ import annotations

import os
import json
import time
import re
from urllib.parse import urlparse
from typing import Any, Dict, Optional

import psycopg
from psycopg.rows import dict_row


DEFAULT_DB_URL = "postgresql://noytrix_intel:{}@127.0.0.1:5432/noytrix_intelligence"


def _load_db_url() -> str:
    url = os.getenv("NOYTRIX_INTELLIGENCE_DATABASE_URL")
    if url:
        return url

    password_file = "/root/backend/.noytrix_pg_password"
    if os.path.exists(password_file):
        password = open(password_file, "r", encoding="utf-8").read().strip()
        return DEFAULT_DB_URL.format(password)

    raise RuntimeError("NOYTRIX_INTELLIGENCE_DATABASE_URL is not set and password file not found")


def connect():
    return psycopg.connect(_load_db_url(), row_factory=dict_row)


def now_ts() -> int:
    return int(time.time())


def normalize_entity(value: str) -> str:
    v = (value or "").strip().lower()
    v = v.replace("\u200b", "").replace("\ufeff", "")
    v = v.split("#")[0].strip()

    if v.startswith("http://") or v.startswith("https://"):
        try:
            p = urlparse(v)
            host = (p.netloc or "").lower()
            path = (p.path or "").rstrip("/")
            query = f"?{p.query}" if p.query else ""
            return f"{host}{path}{query}".strip("/")
        except Exception:
            pass

    v = re.sub(r"^www\.", "", v)
    v = v.rstrip("/")
    return v


def guess_entity_type(value: str) -> str:
    v = (value or "").strip().lower()

    if re.fullmatch(r"0x[a-f0-9]{40}", v):
        return "evm_address"

    if v.startswith("http://") or v.startswith("https://"):
        return "url"

    if "." in v and " " not in v and len(v) <= 253:
        return "domain"

    return "text"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sources (
    id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL DEFAULT 'feed',
    trust_level INTEGER NOT NULL DEFAULT 50,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_imported_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS entities (
    id BIGSERIAL PRIMARY KEY,
    entity TEXT NOT NULL,
    normalized_entity TEXT NOT NULL UNIQUE,
    entity_type TEXT NOT NULL,
    chain TEXT,
    status TEXT NOT NULL DEFAULT 'unknown',
    risk_score INTEGER NOT NULL DEFAULT 0,
    confidence INTEGER NOT NULL DEFAULT 0,
    reputation_score INTEGER NOT NULL DEFAULT 0,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    seen_count BIGINT NOT NULL DEFAULT 1,
    source_count INTEGER NOT NULL DEFAULT 0,
    campaign_id TEXT,
    scam_family TEXT,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS entity_observations (
    id BIGSERIAL PRIMARY KEY,
    entity_id BIGINT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    raw_value TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    risk_score INTEGER NOT NULL DEFAULT 0,
    confidence INTEGER NOT NULL DEFAULT 0,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(entity_id, source_name, raw_value)
);

CREATE TABLE IF NOT EXISTS relations (
    id BIGSERIAL PRIMARY KEY,
    from_entity_id BIGINT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    to_entity_id BIGINT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    confidence INTEGER NOT NULL DEFAULT 50,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(from_entity_id, to_entity_id, relation_type)
);

CREATE TABLE IF NOT EXISTS campaigns (
    id BIGSERIAL PRIMARY KEY,
    campaign_id TEXT NOT NULL UNIQUE,
    name TEXT,
    scam_family TEXT,
    risk_score INTEGER NOT NULL DEFAULT 0,
    confidence INTEGER NOT NULL DEFAULT 0,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    entity_count BIGINT NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS reputation_history (
    id BIGSERIAL PRIMARY KEY,
    entity_id BIGINT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    old_score INTEGER,
    new_score INTEGER NOT NULL,
    reason TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS import_runs (
    id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    imported_count BIGINT NOT NULL DEFAULT 0,
    skipped_count BIGINT NOT NULL DEFAULT 0,
    duplicate_count BIGINT NOT NULL DEFAULT 0,
    error_count BIGINT NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_risk ON entities(risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_entities_status ON entities(status);
CREATE INDEX IF NOT EXISTS idx_entities_campaign ON entities(campaign_id);
CREATE INDEX IF NOT EXISTS idx_entities_family ON entities(scam_family);
CREATE INDEX IF NOT EXISTS idx_entities_last_seen ON entities(last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_observations_source ON entity_observations(source_name);
CREATE INDEX IF NOT EXISTS idx_observations_seen ON entity_observations(observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_relations_from ON relations(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_to ON relations(to_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);
"""


def init_schema() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()


def upsert_source(source_name: str, source_type: str = "feed", trust_level: int = 50, metadata: Optional[Dict[str, Any]] = None) -> None:
    metadata = metadata or {}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sources (source_name, source_type, trust_level, metadata, last_imported_at)
                VALUES (%s, %s, %s, %s::jsonb, now())
                ON CONFLICT (source_name)
                DO UPDATE SET
                    source_type = EXCLUDED.source_type,
                    trust_level = GREATEST(sources.trust_level, EXCLUDED.trust_level),
                    metadata = sources.metadata || EXCLUDED.metadata,
                    last_imported_at = now()
                """,
                (source_name, source_type, int(trust_level), json.dumps(metadata, ensure_ascii=False)),
            )
        conn.commit()


def upsert_entity(
    entity: str,
    entity_type: Optional[str] = None,
    source_name: str = "noytrix",
    chain: Optional[str] = None,
    status: str = "unknown",
    risk_score: int = 0,
    confidence: int = 0,
    evidence: Optional[list] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    init_schema()

    raw = (entity or "").strip()
    normalized = normalize_entity(raw)
    etype = entity_type or guess_entity_type(raw)
    evidence = evidence or []
    metadata = metadata or {}

    if not normalized:
        raise ValueError("empty entity")

    upsert_source(source_name)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO entities (
                    entity, normalized_entity, entity_type, chain, status,
                    risk_score, confidence, first_seen_at, last_seen_at,
                    seen_count, source_count, roles, cache_verdict, last_verdict_at, metadata
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    now(), now(), 1, 1,
                    to_jsonb(ARRAY[%s]),
                    CASE
                        WHEN %s::jsonb ? 'cache_verdict' THEN %s::jsonb -> 'cache_verdict'
                        ELSE '{}'::jsonb
                    END,
                    CASE
                        WHEN %s::jsonb ? 'cache_verdict' THEN now()
                        ELSE NULL
                    END,
                    %s::jsonb
                )
                ON CONFLICT (normalized_entity)
                DO UPDATE SET
                    last_seen_at = now(),
                    seen_count = entities.seen_count + 1,
                    risk_score = CASE
                        WHEN EXCLUDED.metadata ? 'cache_verdict'
                             AND lower(COALESCE(EXCLUDED.metadata->'cache_verdict'->>'level','')) IN ('safe','low')
                        THEN LEAST(EXCLUDED.risk_score, 20)
                        WHEN EXCLUDED.metadata ? 'cache_verdict'
                             AND lower(COALESCE(EXCLUDED.metadata->'cache_verdict'->>'level','')) IN ('medium','suspicious')
                        THEN LEAST(GREATEST(EXCLUDED.risk_score, 30), 65)
                        WHEN EXCLUDED.metadata ? 'cache_verdict'
                        THEN EXCLUDED.risk_score
                        ELSE GREATEST(entities.risk_score, EXCLUDED.risk_score)
                    END,
                    confidence = CASE
                        WHEN EXCLUDED.metadata ? 'cache_verdict'
                        THEN EXCLUDED.confidence
                        ELSE GREATEST(entities.confidence, EXCLUDED.confidence)
                    END,
                    status = CASE
                        WHEN EXCLUDED.metadata ? 'cache_verdict'
                             AND lower(COALESCE(EXCLUDED.metadata->'cache_verdict'->>'level','')) IN ('safe','low')
                        THEN 'safe'
                        WHEN EXCLUDED.metadata ? 'cache_verdict'
                             AND lower(COALESCE(EXCLUDED.metadata->'cache_verdict'->>'level','')) IN ('medium','suspicious')
                        THEN 'suspicious'
                        WHEN EXCLUDED.metadata ? 'cache_verdict'
                             AND lower(COALESCE(EXCLUDED.metadata->'cache_verdict'->>'level','')) IN ('critical','danger','high','malicious','scam')
                        THEN 'malicious'
                        WHEN EXCLUDED.status IN ('malicious','scam','danger','critical','high')
                        THEN EXCLUDED.status
                        ELSE entities.status
                    END,
                    metadata = entities.metadata || EXCLUDED.metadata,
                    roles = CASE
                        WHEN entities.roles ? EXCLUDED.entity_type THEN entities.roles
                        ELSE entities.roles || to_jsonb(EXCLUDED.entity_type)
                    END,
                    cache_verdict = CASE
                        WHEN EXCLUDED.metadata ? 'cache_verdict' THEN EXCLUDED.metadata -> 'cache_verdict'
                        ELSE entities.cache_verdict
                    END,
                    last_verdict_at = CASE
                        WHEN EXCLUDED.metadata ? 'cache_verdict' THEN now()
                        ELSE entities.last_verdict_at
                    END
                RETURNING id, normalized_entity, entity_type, roles, risk_score, confidence, status
                """,
                (
                    raw,
                    normalized,
                    etype,
                    chain,
                    status,
                    int(risk_score or 0),
                    int(confidence or 0),
                    etype,
                    json.dumps(metadata, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            row = cur.fetchone()
            entity_id = row["id"]

            cur.execute(
                """
                INSERT INTO entity_observations (
                    entity_id, source_name, raw_value, risk_score, confidence, evidence, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                ON CONFLICT (entity_id, source_name, raw_value)
                DO NOTHING
                """,
                (
                    entity_id,
                    source_name,
                    raw,
                    int(risk_score or 0),
                    int(confidence or 0),
                    json.dumps(evidence, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )

            cur.execute(
                """
                UPDATE entities
                SET source_count = (
                    SELECT COUNT(DISTINCT source_name)
                    FROM entity_observations
                    WHERE entity_id = %s
                )
                WHERE id = %s
                """,
                (entity_id, entity_id),
            )

        conn.commit()

    return dict(row)


if __name__ == "__main__":
    init_schema()
    upsert_entity(
        "https://example-scam.test/claim",
        source_name="self_test",
        status="malicious",
        risk_score=90,
        confidence=80,
        evidence=[{"code": "self_test", "severity": 90}],
    )
    print("POSTGRES_INTELLIGENCE_OK")


def get_cached_verdict(entity: str, max_age_seconds: int = 86400) -> Optional[Dict[str, Any]]:
    normalized = normalize_entity(entity)
    if not normalized:
        return None

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    normalized_entity,
                    entity_type,
                    status,
                    risk_score,
                    confidence,
                    roles,
                    cache_verdict,
                    EXTRACT(EPOCH FROM (now() - last_verdict_at))::BIGINT AS age_seconds
                FROM entities
                WHERE normalized_entity = %s
                  AND last_verdict_at IS NOT NULL
                  AND cache_verdict <> '{}'::jsonb
                LIMIT 1
                """,
                (normalized,),
            )
            row = cur.fetchone()

    if not row:
        return None

    age = int(row.get("age_seconds") or 0)
    if age > int(max_age_seconds or 0):
        return None

    verdict = row.get("cache_verdict") or {}
    if not isinstance(verdict, dict):
        return None

    return {
        "normalized_entity": row.get("normalized_entity"),
        "entity_type": row.get("entity_type"),
        "status": row.get("status"),
        "risk_score": row.get("risk_score"),
        "confidence": row.get("confidence"),
        "roles": row.get("roles") or [],
        "age_seconds": age,
        "verdict": verdict,
    }


def save_cached_verdict(entity: str, verdict: Dict[str, Any], entity_type: Optional[str] = None, source_name: str = "noytrix_runtime_scan") -> None:
    normalized = normalize_entity(entity)
    if not normalized:
        return

    etype = entity_type or str((verdict or {}).get("kind") or guess_entity_type(entity))
    level = str((verdict or {}).get("level") or "unknown").lower()
    score = int((verdict or {}).get("score") or (verdict or {}).get("internal_score") or 0)
    confidence = int((verdict or {}).get("confidence") or (verdict or {}).get("confidence_score") or 0)

    if level in {"critical", "danger", "high", "malicious", "scam"}:
        status = "malicious"
    elif level in {"safe", "low"} and score <= 20:
        status = "safe"
    elif level in {"medium", "suspicious"}:
        status = "suspicious"
    else:
        status = "observed"

    upsert_entity(
        entity=entity,
        entity_type=etype,
        source_name=source_name,
        status=status,
        risk_score=score,
        confidence=confidence,
        evidence=(verdict or {}).get("evidence") or [],
        metadata={"cache_verdict": verdict or {}},
    )

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE entities
                SET cache_verdict = %s::jsonb,
                    last_verdict_at = now(),
                    roles = CASE
                        WHEN roles ? %s THEN roles
                        ELSE roles || to_jsonb(%s::text)
                    END
                WHERE normalized_entity = %s
                """,
                (json.dumps(verdict or {}, ensure_ascii=False), etype, etype, normalized),
            )
        conn.commit()

def get_entity_graph_context(entity: str) -> Optional[Dict[str, Any]]:
    normalized = normalize_entity(entity)
    if not normalized:
        return None

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, normalized_entity, entity_type, status, risk_score, confidence,
                       reputation_score, campaign_id, metadata
                FROM entities
                WHERE normalized_entity = %s
                LIMIT 1
            """, (normalized,))
            row = cur.fetchone()

            if not row and ("/" in normalized or "?" in normalized):
                from urllib.parse import urlparse
                v = normalized
                if "://" not in v:
                    v = "https://" + v
                host = (urlparse(v).netloc or "").lower().strip()
                if host.startswith("www."):
                    host = host[4:]
                if host:
                    cur.execute("""
                        SELECT id, normalized_entity, entity_type, status, risk_score, confidence,
                               campaign_id, metadata
                        FROM entities
                        WHERE normalized_entity = %s
                        LIMIT 1
                    """, (host,))
                    row = cur.fetchone()

            if not row:
                return None

            entity_id = row["id"]
            metadata = row.get("metadata") or {}
            graph = metadata.get("graph") or {}

            cur.execute("""
                SELECT
                    e.edge_type,
                    n.normalized_entity,
                    n.entity_type,
                    n.status,
                    n.risk_score,
                    e.weight,
                    e.confidence,
                    e.metadata
                FROM entity_edges e
                JOIN entities n
                  ON n.id = CASE
                    WHEN e.source_entity_id = %s THEN e.target_entity_id
                    ELSE e.source_entity_id
                  END
                WHERE e.source_entity_id = %s OR e.target_entity_id = %s
                ORDER BY e.confidence DESC, e.weight DESC, n.risk_score DESC
                LIMIT 25
            """, (entity_id, entity_id, entity_id))
            neighbors = cur.fetchall()

            campaign = None
            campaign_id = row.get("campaign_id")
            if campaign_id:
                cur.execute("""
                    SELECT normalized_entity, status, risk_score, confidence, metadata
                    FROM entities
                    WHERE normalized_entity = %s
                      AND entity_type = 'campaign'
                    LIMIT 1
                """, (campaign_id,))
                campaign = cur.fetchone()

    return {
        "entity": row["normalized_entity"],
        "entity_type": row["entity_type"],
        "status": row["status"],
        "risk_score": row["risk_score"],
        "confidence": row["confidence"],
        "reputation_score": row.get("reputation_score"),
        "campaign_id": row.get("campaign_id"),
        "metadata": metadata,
        "graph": graph,
        "neighbors": [dict(x) for x in neighbors],
        "campaign": dict(campaign) if campaign else None,
    }
