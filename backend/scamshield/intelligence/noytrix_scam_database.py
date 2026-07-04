from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

try:
    from scamshield.intelligence.postgres_intelligence import (
        connect,
        guess_entity_type,
        normalize_entity,
    )
    from scamshield.intelligence.source_reputation import build_reputation_context
except Exception:  # pragma: no cover - optional production dependency
    connect = None

    def normalize_entity(value: str) -> str:
        return (value or "").strip().lower().rstrip("/")

    def guess_entity_type(value: str) -> str:
        return "evm_address" if re.fullmatch(r"0x[a-f0-9]{40}", (value or "").lower()) else "domain"

    def build_reputation_context(**kwargs) -> dict:
        return {
            "version": "1.0",
            "base_confidence": int(kwargs.get("base_confidence") or 0),
            "adjusted_confidence": int(kwargs.get("base_confidence") or 0),
            "source_count": 0,
            "avg_source_trust": 0,
            "max_source_trust": 0,
            "aligned_observations": 0,
            "conflicting_observations": 0,
            "status_counts": {},
            "top_sources": [],
            "signals": {},
        }


DATABASE_NAME = "Noytrix Scam Database"
MALICIOUS_STATUSES = {"malicious", "scam", "danger", "critical", "high", "blocked"}
SAFE_STATUSES = {"safe", "trusted", "allowlisted", "allowlist"}
FORCEABLE_RAW_STATUSES = MALICIOUS_STATUSES | SAFE_STATUSES

VERIFIED_OFFICIAL_CRYPTO_DOMAINS = {
    "bitcoin.org",
    "ethereum.org",
    "coinbase.com",
    "binance.com",
    "kraken.com",
    "crypto.com",
    "ledger.com",
    "trezor.io",
    "metamask.io",
    "trustwallet.com",
    "phantom.app",
    "uniswap.org",
    "app.uniswap.org",
    "pancakeswap.finance",
    "opensea.io",
    "aave.com",
    "curve.fi",
    "lido.fi",
    "jup.ag",
    "raydium.io",
    "1inch.io",
    "compound.finance",
    "balancer.fi",
    "chain.link",
    "solana.com",
    "polygon.technology",
    "arbitrum.io",
    "optimism.io",
    "base.org",
    "avalanche.network",
    "near.org",
    "cosmos.network",
    "ton.org",
    "sui.io",
    "aptosfoundation.org",
    "etherscan.io",
    "bscscan.com",
    "polygonscan.com",
    "arbiscan.io",
    "basescan.org",
    "coingecko.com",
    "coinmarketcap.com",
    "defillama.com",
    "dune.com",
    "zapper.xyz",
    "zerion.io",
    "safe.global",
    "revoke.cash",
    "walletconnect.com",
    "rainbow.me",
}


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def candidate_entities(value: str) -> list[str]:
    raw = (value or "").strip()
    normalized = normalize_entity(raw)
    candidates: list[str] = []

    def add(item: str) -> None:
        item = normalize_entity(item)
        if item and item not in candidates:
            candidates.append(item)

    add(raw)
    add(normalized)

    url_value = raw if "://" in raw else f"https://{raw}" if "." in raw and " " not in raw else ""
    if url_value:
        parsed = urlparse(url_value)
        host = (parsed.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        path = (parsed.path or "").rstrip("/")
        if host:
            add(host)
            if path:
                add(f"{host}{path}")

    return candidates


def _status_to_level(status: str, score: int = 0) -> str:
    s = str(status or "").lower()
    if s in SAFE_STATUSES:
        return "safe"
    if s in MALICIOUS_STATUSES:
        return "critical" if int(score or 0) >= 85 else "danger"
    if s in {"suspicious", "observed", "quarantine"}:
        return "suspicious"
    return "unknown"


def _row_to_match(row: dict, source: str, matched_value: str) -> dict:
    status = str(row.get("status") or "unknown").lower()
    risk_score = int(row.get("risk_score") or 0)
    confidence = int(row.get("confidence") or 0)
    reputation_context = row.get("source_reputation") or {}
    adjusted_confidence = int(reputation_context.get("adjusted_confidence") or confidence)
    avg_source_trust = int(reputation_context.get("avg_source_trust") or 0)
    max_source_trust = int(reputation_context.get("max_source_trust") or 0)
    level = _status_to_level(status, risk_score)
    trusted_match = (
        status in SAFE_STATUSES
        or adjusted_confidence >= 50
        or avg_source_trust >= 35
        or max_source_trust >= 50
        or (adjusted_confidence >= 30 and risk_score >= 90)
    )
    force_verdict = (status in MALICIOUS_STATUSES or status in SAFE_STATUSES) and trusted_match
    return {
        "available": True,
        "matched": True,
        "database": DATABASE_NAME,
        "source": source,
        "entity": row.get("entity") or row.get("raw_value") or matched_value,
        "matched_value": matched_value,
        "normalized_entity": row.get("normalized_entity") or row.get("normalized_value") or matched_value,
        "entity_type": row.get("entity_type") or row.get("indicator_type") or guess_entity_type(matched_value),
        "status": status,
        "level": level,
        "risk_score": risk_score,
        "confidence": adjusted_confidence,
        "base_confidence": confidence,
        "force_verdict": force_verdict,
        "source_reputation": reputation_context,
        "metadata": row.get("metadata") or row.get("raw_record") or {},
    }


def _entity_reputation_context(cur, entity_id: int, status: str, base_confidence: int) -> dict:
    cur.execute(
        """
        SELECT
            io.source_name,
            io.status,
            io.risk_score,
            io.confidence,
            io.observed_at AS last_seen_at,
            COALESCE(sr.trust_score, 50) AS trust_score
        FROM indicator_observations io
        LEFT JOIN source_reputation sr
          ON sr.source_name = io.source_name
        WHERE io.entity_id = %s
        ORDER BY COALESCE(sr.trust_score, 50) DESC, io.confidence DESC, io.risk_score DESC
        LIMIT 25
        """,
        (entity_id,),
    )
    return build_reputation_context(
        status=status,
        base_confidence=int(base_confidence or 0),
        observations=[dict(x) for x in cur.fetchall()],
    )


def _raw_reputation_context(cur, source_name: str, status: str, base_confidence: int, risk_score: int, last_seen_at: Any = None) -> dict:
    cur.execute(
        """
        SELECT source_name, trust_score, last_seen_at
        FROM source_reputation
        WHERE source_name = %s
        LIMIT 1
        """,
        (source_name,),
    )
    row = cur.fetchone()
    source_reputation = dict(row) if row else {"source_name": source_name, "trust_score": 50, "last_seen_at": last_seen_at}
    return build_reputation_context(
        status=status,
        base_confidence=int(base_confidence or 0),
        observations=[{
            "source_name": source_name,
            "status": status,
            "risk_score": risk_score,
            "confidence": base_confidence,
            "trust_score": source_reputation.get("trust_score") or 50,
            "last_seen_at": source_reputation.get("last_seen_at") or last_seen_at,
        }],
        source_reputation=source_reputation,
    )


def _lookup_postgres(value: str) -> Optional[dict]:
    if not connect:
        return None
    candidates = candidate_entities(value)
    if not candidates:
        return None

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, entity, normalized_entity, entity_type, status, risk_score,
                           confidence, metadata
                    FROM entities
                    WHERE normalized_entity = ANY(%s)
                    ORDER BY
                        CASE
                            WHEN lower(status) IN ('malicious','scam','danger','critical','high','blocked') THEN 0
                            WHEN lower(status) IN ('safe','trusted','allowlisted','allowlist') THEN 1
                            ELSE 2
                        END,
                        risk_score DESC,
                        confidence DESC
                    LIMIT 1
                    """,
                    (candidates,),
                )
                row = cur.fetchone()
                if row:
                    row = dict(row)
                    row["source_reputation"] = _entity_reputation_context(
                        cur,
                        int(row.get("id") or 0),
                        str(row.get("status") or "unknown"),
                        int(row.get("confidence") or 0),
                    )
                    return _row_to_match(row, "postgres_entities", str(row.get("normalized_entity")))

                cur.execute(
                    """
                    SELECT e.id, e.entity, e.normalized_entity, e.entity_type, e.status,
                           e.risk_score, e.confidence,
                           e.metadata || jsonb_build_object(
                               'alias_match',
                               jsonb_build_object(
                                   'normalized_alias', a.normalized_alias,
                                   'alias_type', a.alias_type,
                                   'source_name', a.source_name
                               )
                           ) AS metadata
                    FROM entity_aliases a
                    JOIN entities e ON e.id = a.entity_id
                    WHERE a.normalized_alias = ANY(%s)
                    ORDER BY
                        CASE
                            WHEN lower(e.status) IN ('malicious','scam','danger','critical','high','blocked') THEN 0
                            WHEN lower(e.status) IN ('safe','trusted','allowlisted','allowlist') THEN 1
                            ELSE 2
                        END,
                        e.risk_score DESC,
                        e.confidence DESC,
                        a.seen_count DESC
                    LIMIT 1
                    """,
                    (candidates,),
                )
                row = cur.fetchone()
                if row:
                    row = dict(row)
                    row["source_reputation"] = _entity_reputation_context(
                        cur,
                        int(row.get("id") or 0),
                        str(row.get("status") or "unknown"),
                        int(row.get("confidence") or 0),
                    )
                    return _row_to_match(row, "postgres_entity_aliases", str(row.get("normalized_entity")))

                cur.execute(
                    """
                    SELECT raw_value, normalized_value, indicator_type, status,
                           risk_score, confidence, metadata, raw_record,
                           source_name, last_seen_at
                    FROM raw_indicators
                    WHERE normalized_value = ANY(%s)
                      AND lower(status) = ANY(%s)
                    ORDER BY risk_score DESC, confidence DESC, seen_count DESC
                    LIMIT 1
                    """,
                    (candidates, sorted(FORCEABLE_RAW_STATUSES)),
                )
                row = cur.fetchone()
                if row:
                    row = dict(row)
                    row["source_reputation"] = _raw_reputation_context(
                        cur,
                        str(row.get("source_name") or "unknown"),
                        str(row.get("status") or "unknown"),
                        int(row.get("confidence") or 0),
                        int(row.get("risk_score") or 0),
                        row.get("last_seen_at"),
                    )
                    return _row_to_match(row, "postgres_raw_indicators", str(row.get("normalized_value")))
    except Exception as exc:
        return {
            "available": False,
            "matched": False,
            "database": DATABASE_NAME,
            "source": "postgres",
            "error": str(exc),
        }

    return None


def _walk_values(data: Any):
    if isinstance(data, str):
        yield data
    elif isinstance(data, list):
        for item in data:
            yield from _walk_values(item)
    elif isinstance(data, dict):
        for key in ("url", "domain", "address", "target", "value", "site"):
            if data.get(key):
                yield str(data[key])


@lru_cache(maxsize=1)
def _load_local_public_feed_index() -> dict:
    root = _backend_root() / "data" / "public_feeds" / "scamsniffer_scam_database" / "blacklist"
    files = ["domains.json", "address.json", "combined.json", "all.json"]
    values: dict[str, dict] = {}
    for filename in files:
        path = root / filename
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for raw in _walk_values(data):
            normalized = normalize_entity(str(raw))
            if not normalized:
                continue
            values.setdefault(normalized, {"source_file": filename})
    return values


def _lookup_local_public_feeds(value: str) -> Optional[dict]:
    index = _load_local_public_feed_index()
    for candidate in candidate_entities(value):
        if candidate in index:
            return {
                "available": True,
                "matched": True,
                "database": DATABASE_NAME,
                "source": "local_public_feed_scamsniffer",
                "entity": candidate,
                "matched_value": candidate,
                "normalized_entity": candidate,
                "entity_type": guess_entity_type(candidate),
                "status": "malicious",
                "level": "critical",
                "risk_score": 90,
                "confidence": 80,
                "force_verdict": True,
                "source_reputation": build_reputation_context(
                    status="malicious",
                    base_confidence=80,
                    observations=[{
                        "source_name": "local_public_feed_scamsniffer",
                        "status": "malicious",
                        "risk_score": 90,
                        "confidence": 80,
                        "trust_score": 75,
                    }],
                ),
                "metadata": index[candidate],
            }
    return None


def _lookup_verified_official_domains(value: str) -> Optional[dict]:
    for candidate in candidate_entities(value):
        host = candidate.split("/", 1)[0].lower()
        if host.startswith("www."):
            host = host[4:]
        if host in VERIFIED_OFFICIAL_CRYPTO_DOMAINS:
            return {
                "available": True,
                "matched": True,
                "database": DATABASE_NAME,
                "source": "local_verified_official_crypto_domains",
                "entity": host,
                "matched_value": host,
                "normalized_entity": host,
                "entity_type": "domain",
                "status": "trusted",
                "level": "safe",
                "risk_score": 0,
                "confidence": 95,
                "force_verdict": True,
                "source_reputation": build_reputation_context(
                    status="trusted",
                    base_confidence=95,
                    observations=[{
                        "source_name": "local_verified_official_crypto_domains",
                        "status": "trusted",
                        "risk_score": 0,
                        "confidence": 95,
                        "trust_score": 98,
                    }],
                ),
                "metadata": {"verified_official_domain": True},
            }
    return None


def lookup_noytrix_scam_database(value: str) -> dict:
    pg_match = _lookup_postgres(value)
    pg_error = pg_match if pg_match and not pg_match.get("available", True) else None
    if pg_match and pg_match.get("matched"):
        return pg_match

    verified_match = _lookup_verified_official_domains(value)
    if verified_match:
        if pg_error:
            verified_match["postgres_lookup"] = pg_error
        return verified_match

    local_match = _lookup_local_public_feeds(value)
    if local_match:
        if pg_error:
            local_match["postgres_lookup"] = pg_error
        return local_match

    return {
        "available": True,
        "matched": False,
        "database": DATABASE_NAME,
        "postgres_lookup": pg_error,
        "checked_candidates": candidate_entities(value)[:8],
    }
