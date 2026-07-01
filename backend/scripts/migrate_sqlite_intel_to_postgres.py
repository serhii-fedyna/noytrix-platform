from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from scamshield.intelligence.postgres_intelligence import init_schema, upsert_entity, connect


def _sqlite_rows(path: str, query: str):
    if not Path(path).exists():
        return []
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(query).fetchall()]
    finally:
        conn.close()


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v or default)
    except Exception:
        return default


def migrate_threat_memory() -> int:
    rows = _sqlite_rows(
        "data/threat_memory.db",
        "SELECT entity, entity_type, level, score, confidence, source, risk_type, seen_count FROM threat_memory",
    )
    count = 0
    for r in rows:
        entity = str(r.get("entity") or "").strip()
        if not entity:
            continue
        level = str(r.get("level") or "unknown").lower()
        status = "malicious" if level in {"critical", "danger", "high", "malicious", "scam"} else level
        upsert_entity(
            entity=entity,
            entity_type=str(r.get("entity_type") or r.get("risk_type") or "unknown"),
            source_name=str(r.get("source") or "legacy_threat_memory"),
            status=status,
            risk_score=_safe_int(r.get("score")),
            confidence=_safe_int(r.get("confidence")),
            metadata={"legacy_db": "threat_memory.db", "risk_type": r.get("risk_type"), "seen_count": r.get("seen_count")},
        )
        count += 1
    return count


def migrate_url_fingerprints() -> int:
    rows = _sqlite_rows(
        "data/url_intelligence.sqlite3",
        """
        SELECT host, root_domain, title, text_hash, script_hash, ui_hash,
               infra_hash, behavior_hash, brands, seen_count
        FROM url_fingerprints
        """,
    )
    count = 0
    for r in rows:
        host = str(r.get("host") or "").strip()
        if not host:
            continue
        upsert_entity(
            entity=host,
            entity_type="domain",
            source_name="legacy_url_fingerprints",
            status="observed",
            risk_score=0,
            confidence=40,
            metadata={
                "legacy_db": "url_intelligence.sqlite3",
                "root_domain": r.get("root_domain"),
                "title": r.get("title"),
                "text_hash": r.get("text_hash"),
                "script_hash": r.get("script_hash"),
                "ui_hash": r.get("ui_hash"),
                "infra_hash": r.get("infra_hash"),
                "behavior_hash": r.get("behavior_hash"),
                "brands": r.get("brands"),
                "seen_count": r.get("seen_count"),
            },
        )
        count += 1
    return count


def migrate_spender_reputation() -> int:
    rows = _sqlite_rows(
        "data/spender_reputation.sqlite3",
        "SELECT address, label, category, trust, risk, reasons, source FROM spender_reputation",
    )
    count = 0
    for r in rows:
        address = str(r.get("address") or "").strip()
        if not address:
            continue

        risk = str(r.get("risk") or "unknown").lower()
        trust = str(r.get("trust") or "unknown").lower()

        if risk in {"high", "critical", "danger", "malicious"}:
            score, status = 85, "malicious"
        elif trust == "trusted":
            score, status = 0, "trusted"
        else:
            score, status = 30, "unknown"

        upsert_entity(
            entity=address,
            entity_type="evm_address",
            source_name=str(r.get("source") or "legacy_spender_reputation"),
            status=status,
            risk_score=score,
            confidence=70,
            metadata={
                "legacy_db": "spender_reputation.sqlite3",
                "label": r.get("label"),
                "category": r.get("category"),
                "trust": trust,
                "risk": risk,
                "reasons": r.get("reasons"),
            },
        )
        count += 1
    return count


def migrate_wallet_profiles() -> int:
    rows = _sqlite_rows(
        "data/spender_reputation.sqlite3",
        """
        SELECT wallet, chain, risk_score, unlimited_approvals, risky_spenders,
               estimated_exposure_usd, nft_exposure
        FROM wallet_risk_profiles
        """,
    )
    count = 0
    for r in rows:
        wallet = str(r.get("wallet") or "").strip()
        if not wallet:
            continue

        score = _safe_int(r.get("risk_score"))
        upsert_entity(
            entity=wallet,
            entity_type="wallet",
            chain=r.get("chain"),
            source_name="legacy_wallet_risk_profiles",
            status="danger" if score >= 60 else "observed",
            risk_score=score,
            confidence=65,
            metadata={
                "legacy_db": "spender_reputation.sqlite3",
                "unlimited_approvals": r.get("unlimited_approvals"),
                "risky_spenders": r.get("risky_spenders"),
                "estimated_exposure_usd": r.get("estimated_exposure_usd"),
                "nft_exposure": r.get("nft_exposure"),
            },
        )
        count += 1
    return count


def migrate_relations() -> int:
    rows = _sqlite_rows(
        "data/threat_memory.db",
        """
        SELECT source_entity, source_type, target_entity, target_type,
               relation_type, confidence, source
        FROM threat_graph_edges
        """,
    )

    count = 0
    init_schema()

    with connect() as conn:
        with conn.cursor() as cur:
            for r in rows:
                source_entity = str(r.get("source_entity") or "").strip()
                target_entity = str(r.get("target_entity") or "").strip()
                if not source_entity or not target_entity:
                    continue

                from_row = upsert_entity(
                    entity=source_entity,
                    entity_type=str(r.get("source_type") or "unknown"),
                    source_name=str(r.get("source") or "legacy_threat_graph"),
                    status="observed",
                    risk_score=0,
                    confidence=_safe_int(r.get("confidence"), 50),
                )

                to_row = upsert_entity(
                    entity=target_entity,
                    entity_type=str(r.get("target_type") or "unknown"),
                    source_name=str(r.get("source") or "legacy_threat_graph"),
                    status="observed",
                    risk_score=0,
                    confidence=_safe_int(r.get("confidence"), 50),
                )

                cur.execute(
                    """
                    INSERT INTO relations (
                        from_entity_id, to_entity_id, relation_type, confidence, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (from_entity_id, to_entity_id, relation_type)
                    DO UPDATE SET
                        confidence = GREATEST(relations.confidence, EXCLUDED.confidence),
                        last_seen_at = now(),
                        metadata = relations.metadata || EXCLUDED.metadata
                    """,
                    (
                        from_row["id"],
                        to_row["id"],
                        str(r.get("relation_type") or "related"),
                        _safe_int(r.get("confidence"), 50),
                        json.dumps({"legacy_db": "threat_memory.db", "source": r.get("source")}, ensure_ascii=False),
                    ),
                )
                count += 1
        conn.commit()
    return count


def main():
    init_schema()
    stats = {
        "threat_memory": migrate_threat_memory(),
        "url_fingerprints": migrate_url_fingerprints(),
        "spender_reputation": migrate_spender_reputation(),
        "wallet_profiles": migrate_wallet_profiles(),
        "relations": migrate_relations(),
    }
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
