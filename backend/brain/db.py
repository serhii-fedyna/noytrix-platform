from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .config import BRAIN_DB_PATH


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(BRAIN_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS brain_sources (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source_key TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL,
              url TEXT NOT NULL,
              category TEXT NOT NULL,
              source_type TEXT NOT NULL DEFAULT 'website',
              enabled INTEGER NOT NULL DEFAULT 1,
              terms_checked_at TEXT,
              last_run_at TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS brain_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              pipeline TEXT NOT NULL,
              started_at TEXT NOT NULL,
              finished_at TEXT,
              status TEXT NOT NULL,
              sources_checked INTEGER NOT NULL DEFAULT 0,
              prospects_seen INTEGER NOT NULL DEFAULT 0,
              prospects_qualified INTEGER NOT NULL DEFAULT 0,
              drafts_created INTEGER NOT NULL DEFAULT 0,
              error_text TEXT,
              details_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS brain_prospects (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              pipeline TEXT NOT NULL,
              name TEXT NOT NULL,
              primary_domain TEXT NOT NULL,
              website_url TEXT NOT NULL,
              category TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'researching',
              summary TEXT NOT NULL DEFAULT '',
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              UNIQUE(pipeline, primary_domain)
            );
            CREATE TABLE IF NOT EXISTS brain_evidence (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              prospect_id INTEGER NOT NULL REFERENCES brain_prospects(id) ON DELETE CASCADE,
              source_url TEXT NOT NULL,
              claim_type TEXT NOT NULL,
              excerpt TEXT NOT NULL,
              captured_at TEXT NOT NULL,
              confidence REAL NOT NULL DEFAULT 0.5,
              evidence_hash TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS brain_contacts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              prospect_id INTEGER NOT NULL REFERENCES brain_prospects(id) ON DELETE CASCADE,
              email TEXT NOT NULL UNIQUE,
              role TEXT NOT NULL DEFAULT 'business_contact',
              source_url TEXT NOT NULL,
              contact_basis TEXT NOT NULL DEFAULT 'public_business_contact',
              status TEXT NOT NULL DEFAULT 'available',
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS brain_opportunities (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              prospect_id INTEGER NOT NULL UNIQUE REFERENCES brain_prospects(id) ON DELETE CASCADE,
              fit_score INTEGER NOT NULL,
              revenue_score INTEGER NOT NULL,
              technical_score INTEGER NOT NULL,
              timing_score INTEGER NOT NULL,
              contact_score INTEGER NOT NULL,
              risk_penalty INTEGER NOT NULL DEFAULT 0,
              overall_score INTEGER NOT NULL,
              decision TEXT NOT NULL,
              rationale_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS brain_drafts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              opportunity_id INTEGER NOT NULL REFERENCES brain_opportunities(id) ON DELETE CASCADE,
              contact_id INTEGER NOT NULL REFERENCES brain_contacts(id) ON DELETE CASCADE,
              subject TEXT NOT NULL,
              body TEXT NOT NULL,
              evidence_ids_json TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending_review',
              model TEXT,
              created_at TEXT NOT NULL,
              UNIQUE(opportunity_id, contact_id, status)
            );
            CREATE TABLE IF NOT EXISTS brain_approvals (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              draft_id INTEGER NOT NULL REFERENCES brain_drafts(id) ON DELETE CASCADE,
              decision TEXT NOT NULL,
              approved_by TEXT NOT NULL,
              note TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS brain_outreach_messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              draft_id INTEGER NOT NULL UNIQUE REFERENCES brain_drafts(id) ON DELETE CASCADE,
              provider TEXT NOT NULL,
              idempotency_key TEXT NOT NULL UNIQUE,
              status TEXT NOT NULL,
              sent_at TEXT,
              provider_message_id TEXT,
              error_text TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS brain_suppressions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              value TEXT NOT NULL UNIQUE,
              reason TEXT NOT NULL,
              created_at TEXT NOT NULL,
              expires_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_brain_prospects_status ON brain_prospects(pipeline, status, last_seen_at);
            CREATE INDEX IF NOT EXISTS idx_brain_evidence_prospect ON brain_evidence(prospect_id, captured_at);
            CREATE INDEX IF NOT EXISTS idx_brain_drafts_status ON brain_drafts(status, created_at);
            """
        )
        conn.commit()
    finally:
        conn.close()


init_db()
