from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict


DB_PATH = Path("data/threat_memory.db")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_threat_memory() -> None:
    conn = _connect()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS threat_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        level TEXT,
        score INTEGER DEFAULT 0,
        confidence INTEGER DEFAULT 0,
        first_seen INTEGER,
        last_seen INTEGER,
        seen_count INTEGER DEFAULT 1,
        source TEXT,
        risk_type TEXT,
        UNIQUE(entity, entity_type)
    )
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_threat_entity
    ON threat_memory(entity)
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS threat_memory_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        level TEXT,
        score INTEGER DEFAULT 0,
        confidence INTEGER DEFAULT 0,
        source TEXT,
        risk_type TEXT,
        created_at INTEGER
    )
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_threat_history_entity
    ON threat_memory_history(entity, entity_type)
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS threat_graph_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_entity TEXT NOT NULL,
        source_type TEXT NOT NULL,
        target_entity TEXT NOT NULL,
        target_type TEXT NOT NULL,
        relation_type TEXT NOT NULL,
        confidence INTEGER DEFAULT 50,
        source TEXT,
        first_seen INTEGER,
        last_seen INTEGER,
        seen_count INTEGER DEFAULT 1,
        UNIQUE(source_entity, source_type, target_entity, target_type, relation_type)
    )
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_threat_graph_source
    ON threat_graph_edges(source_entity, source_type)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_threat_graph_target
    ON threat_graph_edges(target_entity, target_type)
    """)

    conn.commit()
    conn.close()


def remember_entity(
    entity: str,
    entity_type: str,
    level: str,
    score: int,
    confidence: int,
    source: str = "runtime",
    risk_type: str = "unknown",
) -> None:
    entity = str(entity or "").strip()
    entity_type = str(entity_type or "unknown").strip()

    if not entity:
        return

    init_threat_memory()

    now = int(time.time())
    conn = _connect()
    cur = conn.cursor()

    cur.execute("""
    SELECT id
    FROM threat_memory
    WHERE entity = ? AND entity_type = ?
    """, (entity, entity_type))

    row = cur.fetchone()

    if row:
        cur.execute("""
        UPDATE threat_memory
        SET
            level = ?,
            score = ?,
            confidence = ?,
            last_seen = ?,
            seen_count = seen_count + 1,
            source = ?,
            risk_type = ?
        WHERE id = ?
        """, (
            level,
            int(score or 0),
            int(confidence or 0),
            now,
            source,
            risk_type,
            row["id"],
        ))
    else:
        cur.execute("""
        INSERT INTO threat_memory (
            entity,
            entity_type,
            level,
            score,
            confidence,
            first_seen,
            last_seen,
            seen_count,
            source,
            risk_type
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entity,
            entity_type,
            level,
            int(score or 0),
            int(confidence or 0),
            now,
            now,
            1,
            source,
            risk_type,
        ))

    cur.execute("""
    INSERT INTO threat_memory_history (
        entity,
        entity_type,
        level,
        score,
        confidence,
        source,
        risk_type,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        entity,
        entity_type,
        level,
        int(score or 0),
        int(confidence or 0),
        source,
        risk_type,
        now,
    ))

    conn.commit()
    conn.close()


def get_entity_memory(entity: str, entity_type: str) -> Dict[str, Any] | None:
    init_threat_memory()

    conn = _connect()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM threat_memory
    WHERE entity = ? AND entity_type = ?
    """, (str(entity or "").strip(), str(entity_type or "unknown").strip()))

    row = cur.fetchone()
    conn.close()

    return dict(row) if row else None


def remember_many_from_verdict(verdict: Dict[str, Any], source: str = "security_core") -> None:
    if not isinstance(verdict, dict):
        return

    level = str(verdict.get("level") or "unknown")
    score = int(verdict.get("score") or 0)
    confidence = int(verdict.get("confidence_score") or verdict.get("confidence") or 0)
    risk_type = str(verdict.get("risk_type") or "unknown")

    main_entity = str(verdict.get("normalized_input") or verdict.get("input") or "").strip()
    main_type = str(verdict.get("kind") or "unknown").strip() or "unknown"

    if main_entity:
        remember_entity(main_entity, main_type, level, score, confidence, source=source, risk_type=risk_type)

    permissions = verdict.get("permissions_summary") or {}
    spender = str(permissions.get("spender") or "").strip().lower()
    if spender:
        remember_entity(spender, "spender", level, score, confidence, source=source, risk_type=risk_type)

    raw = verdict.get("raw") or {}
    contract_identity = verdict.get("contract_identity") or raw.get("contract_identity") or (raw.get("details") or {}).get("contract_identity") or {}
    contract_address = str(contract_identity.get("address") or "").strip().lower()
    if contract_address:
        remember_entity(contract_address, "contract_identity", level, score, confidence, source=source, risk_type=risk_type)

    campaign = verdict.get("campaign") or {}
    campaign_id = str(campaign.get("campaign_id") or campaign.get("id") or "").strip()
    if campaign_id:
        remember_entity(campaign_id, "campaign", level, score, confidence, source=source, risk_type=risk_type)


def build_memory_summary(memory: Dict[str, Any] | None, current_score: int | None = None, current_level: str | None = None) -> Dict[str, Any]:
    if not memory:
        return {
            "known": False,
            "seen_before": False,
            "seen_count": 0,
            "first_seen": None,
            "last_seen": None,
            "previous_level": None,
            "previous_score": 0,
            "previous_confidence": 0,
            "risk_evolution": "new",
            "risk_delta": 0,
        }

    seen_count = int(memory.get("seen_count") or 0)
    previous_score = int(memory.get("score") or 0)

    try:
        current_score_int = int(current_score or 0)
    except Exception:
        current_score_int = 0

    risk_delta = current_score_int - previous_score

    if seen_count <= 1:
        evolution = "new"
    elif risk_delta >= 20:
        evolution = "risk_increased"
    elif risk_delta <= -20:
        evolution = "risk_decreased"
    else:
        evolution = "stable"

    return {
        "known": True,
        "seen_before": seen_count > 1,
        "seen_count": seen_count,
        "first_seen": memory.get("first_seen"),
        "last_seen": memory.get("last_seen"),
        "previous_level": memory.get("level"),
        "previous_score": previous_score,
        "previous_confidence": int(memory.get("confidence") or 0),
        "current_level": current_level,
        "current_score": current_score_int,
        "risk_evolution": evolution,
        "risk_delta": risk_delta,
    }


def remember_relation(
    source_entity: str,
    source_type: str,
    target_entity: str,
    target_type: str,
    relation_type: str,
    confidence: int = 50,
    source: str = "security_core",
) -> None:
    source_entity = str(source_entity or "").strip()
    target_entity = str(target_entity or "").strip()

    if not source_entity or not target_entity:
        return

    init_threat_memory()

    now = int(time.time())
    conn = _connect()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS threat_graph_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_entity TEXT NOT NULL,
        source_type TEXT NOT NULL,
        target_entity TEXT NOT NULL,
        target_type TEXT NOT NULL,
        relation_type TEXT NOT NULL,
        confidence INTEGER DEFAULT 50,
        source TEXT,
        first_seen INTEGER,
        last_seen INTEGER,
        seen_count INTEGER DEFAULT 1,
        UNIQUE(source_entity, source_type, target_entity, target_type, relation_type)
    )
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_threat_graph_source
    ON threat_graph_edges(source_entity, source_type)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_threat_graph_target
    ON threat_graph_edges(target_entity, target_type)
    """)

    cur.execute("""
    SELECT id
    FROM threat_graph_edges
    WHERE source_entity = ?
      AND source_type = ?
      AND target_entity = ?
      AND target_type = ?
      AND relation_type = ?
    """, (
        source_entity,
        source_type,
        target_entity,
        target_type,
        relation_type,
    ))

    row = cur.fetchone()

    if row:
        cur.execute("""
        UPDATE threat_graph_edges
        SET
            confidence = ?,
            source = ?,
            last_seen = ?,
            seen_count = seen_count + 1
        WHERE id = ?
        """, (
            int(confidence or 50),
            source,
            now,
            row["id"],
        ))
    else:
        cur.execute("""
        INSERT INTO threat_graph_edges (
            source_entity,
            source_type,
            target_entity,
            target_type,
            relation_type,
            confidence,
            source,
            first_seen,
            last_seen,
            seen_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source_entity,
            source_type,
            target_entity,
            target_type,
            relation_type,
            int(confidence or 50),
            source,
            now,
            now,
            1,
        ))

    conn.commit()
    conn.close()


def remember_relations_from_verdict(verdict: Dict[str, Any], source: str = "security_core") -> None:
    if not isinstance(verdict, dict):
        return

    main_entity = str(verdict.get("normalized_input") or verdict.get("input") or "").strip()
    main_type = str(verdict.get("kind") or "unknown").strip() or "unknown"
    confidence = int(verdict.get("confidence_score") or verdict.get("confidence") or 50)

    if not main_entity:
        return

    raw = verdict.get("raw") or {}
    permissions = verdict.get("permissions_summary") or raw.get("permissions_summary") or {}

    spender = str(permissions.get("spender") or "").strip().lower()
    if spender:
        remember_relation(
            main_entity,
            main_type,
            spender,
            "spender",
            "uses_spender",
            confidence=confidence,
            source=source,
        )

    contract_identity = verdict.get("contract_identity") or raw.get("contract_identity") or (raw.get("details") or {}).get("contract_identity") or {}
    contract_address = str(contract_identity.get("address") or "").strip().lower()
    if contract_address and contract_address != main_entity.lower():
        remember_relation(
            main_entity,
            main_type,
            contract_address,
            "contract_identity",
            "has_contract_identity",
            confidence=confidence,
            source=source,
        )

    campaign = verdict.get("campaign") or {}
    campaign_id = str(campaign.get("campaign_id") or campaign.get("id") or "").strip()
    if campaign_id:
        remember_relation(
            main_entity,
            main_type,
            campaign_id,
            "campaign",
            "belongs_to_campaign",
            confidence=confidence,
            source=source,
        )
