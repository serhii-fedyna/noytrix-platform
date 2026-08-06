from __future__ import annotations

import hashlib
import json
from typing import Any

from .db import connect, now_iso


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))


def sync_sources(items: list[dict[str, Any]]) -> None:
    conn = connect()
    try:
        for item in items:
            conn.execute(
                """
                INSERT INTO brain_sources(source_key,name,url,category,source_type,enabled,terms_checked_at,created_at)
                VALUES(?,?,?,?,?,1,?,?)
                ON CONFLICT(source_key) DO UPDATE SET
                  name=excluded.name,url=excluded.url,category=excluded.category,source_type=excluded.source_type
                """,
                (item["source_key"], item["name"], item["url"], item["category"], item.get("source_type", "website"), now_iso(), now_iso()),
            )
        conn.commit()
    finally:
        conn.close()


def active_sources(limit: int, *, source_type: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        if source_type:
            rows = conn.execute(
                "SELECT * FROM brain_sources WHERE enabled=1 AND source_type=? ORDER BY COALESCE(last_run_at,'') ASC, id ASC LIMIT ?",
                (source_type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM brain_sources WHERE enabled=1 ORDER BY COALESCE(last_run_at,'') ASC, id ASC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def create_run(pipeline: str) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO brain_runs(pipeline,started_at,status) VALUES(?,?,?)", (pipeline, now_iso(), "running")
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def finish_run(run_id: int, *, status: str, sources_checked: int, prospects_seen: int, prospects_qualified: int, drafts_created: int, details: dict[str, Any], error: str | None = None) -> None:
    conn = connect()
    try:
        conn.execute(
            """UPDATE brain_runs SET finished_at=?,status=?,sources_checked=?,prospects_seen=?,prospects_qualified=?,drafts_created=?,details_json=?,error_text=? WHERE id=?""",
            (now_iso(), status, sources_checked, prospects_seen, prospects_qualified, drafts_created, _json(details), (error or "")[:800], run_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_source_run(source_id: int) -> None:
    conn = connect()
    try:
        conn.execute("UPDATE brain_sources SET last_run_at=? WHERE id=?", (now_iso(), source_id))
        conn.commit()
    finally:
        conn.close()


def upsert_prospect(*, pipeline: str, name: str, domain: str, website_url: str, category: str, summary: str) -> int:
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO brain_prospects(pipeline,name,primary_domain,website_url,category,status,summary,first_seen_at,last_seen_at)
            VALUES(?,?,?,?,?,'researching',?,?,?)
            ON CONFLICT(pipeline,primary_domain) DO UPDATE SET
              name=excluded.name,website_url=excluded.website_url,category=excluded.category,
              summary=excluded.summary,last_seen_at=excluded.last_seen_at
            """,
            (pipeline, name[:180], domain[:255], website_url[:1000], category[:100], summary[:4000], now_iso(), now_iso()),
        )
        row = conn.execute("SELECT id FROM brain_prospects WHERE pipeline=? AND primary_domain=?", (pipeline, domain)).fetchone()
        conn.commit()
        return int(row["id"])
    finally:
        conn.close()


def add_evidence(prospect_id: int, *, source_url: str, claim_type: str, excerpt: str, confidence: float = 0.7) -> int | None:
    clean = " ".join(str(excerpt or "").split())[:1800]
    if not clean:
        return None
    digest = hashlib.sha256(f"{prospect_id}|{source_url}|{claim_type}|{clean}".encode("utf-8")).hexdigest()
    conn = connect()
    try:
        cur = conn.execute(
            """INSERT OR IGNORE INTO brain_evidence(prospect_id,source_url,claim_type,excerpt,captured_at,confidence,evidence_hash)
               VALUES(?,?,?,?,?,?,?)""",
            (prospect_id, source_url[:1000], claim_type[:80], clean, now_iso(), max(0, min(1, confidence)), digest),
        )
        conn.commit()
        return int(cur.lastrowid) if cur.rowcount else None
    finally:
        conn.close()


def add_contact(
    prospect_id: int,
    *,
    email: str,
    source_url: str,
    role: str = "business_contact",
    contact_basis: str = "public_business_contact",
) -> int | None:
    normalized = email.strip().lower()[:320]
    if not normalized or is_suppressed(normalized):
        return None
    conn = connect()
    try:
        conn.execute(
            """INSERT INTO brain_contacts(prospect_id,email,role,source_url,contact_basis,status,created_at)
               VALUES(?,?,?,?,?,'available',?)
               ON CONFLICT(email) DO UPDATE SET prospect_id=excluded.prospect_id,source_url=excluded.source_url,status='available'""",
            (prospect_id, normalized, role, source_url[:1000], contact_basis[:100], now_iso()),
        )
        row = conn.execute("SELECT id FROM brain_contacts WHERE email=?", (normalized,)).fetchone()
        conn.commit()
        return int(row["id"])
    finally:
        conn.close()


def is_suppressed(value: str) -> bool:
    conn = connect()
    try:
        return bool(conn.execute("SELECT 1 FROM brain_suppressions WHERE value=? LIMIT 1", (value.strip().lower(),)).fetchone())
    finally:
        conn.close()


def upsert_opportunity(prospect_id: int, scores: dict[str, Any]) -> int:
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO brain_opportunities(prospect_id,fit_score,revenue_score,technical_score,timing_score,contact_score,risk_penalty,overall_score,decision,rationale_json,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(prospect_id) DO UPDATE SET
              fit_score=excluded.fit_score,revenue_score=excluded.revenue_score,technical_score=excluded.technical_score,
              timing_score=excluded.timing_score,contact_score=excluded.contact_score,risk_penalty=excluded.risk_penalty,
              overall_score=excluded.overall_score,decision=excluded.decision,rationale_json=excluded.rationale_json,updated_at=excluded.updated_at
            """,
            (prospect_id, scores["fit_score"], scores["revenue_score"], scores["technical_score"], scores["timing_score"], scores["contact_score"], scores["risk_penalty"], scores["overall_score"], scores["decision"], _json(scores["rationale"]), now_iso()),
        )
        row = conn.execute("SELECT id FROM brain_opportunities WHERE prospect_id=?", (prospect_id,)).fetchone()
        conn.execute("UPDATE brain_prospects SET status=? WHERE id=?", (scores["decision"], prospect_id))
        conn.commit()
        return int(row["id"])
    finally:
        conn.close()


def evidence_for_prospect(prospect_id: int, limit: int = 12) -> list[dict[str, Any]]:
    conn = connect()
    try:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM brain_evidence WHERE prospect_id=? ORDER BY confidence DESC, id ASC LIMIT ?", (prospect_id, limit)
        ).fetchall()]
    finally:
        conn.close()


def first_contact(prospect_id: int, *, role: str | None = None) -> dict[str, Any] | None:
    conn = connect()
    try:
        query = "SELECT * FROM brain_contacts WHERE prospect_id=? AND status='available'"
        params: list[Any] = [prospect_id]
        if role:
            query += " AND role=?"
            params.append(role)
        row = conn.execute(query + " ORDER BY id ASC LIMIT 1", params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_draft(*, opportunity_id: int, contact_id: int, subject: str, body: str, evidence_ids: list[int], model: str | None) -> int | None:
    conn = connect()
    try:
        existing = conn.execute(
            "SELECT id FROM brain_drafts WHERE opportunity_id=? AND contact_id=? AND status IN ('pending_review','approved','sent') LIMIT 1",
            (opportunity_id, contact_id),
        ).fetchone()
        if existing:
            return None
        cur = conn.execute(
            """INSERT INTO brain_drafts(opportunity_id,contact_id,subject,body,evidence_ids_json,status,model,created_at)
               VALUES(?,?,?,?,?,'pending_review',?,?)""",
            (opportunity_id, contact_id, subject[:220], body[:8000], _json(evidence_ids), model or "", now_iso()),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def draft_delivery_snapshot(draft_id: int) -> dict[str, Any] | None:
    """Return the single verified contact and draft needed for one idempotent send."""
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT d.*, o.overall_score, o.decision, p.id AS prospect_id, p.name AS prospect_name,
                   p.website_url, p.category, p.pipeline, c.email, c.status AS contact_status
            FROM brain_drafts d
            JOIN brain_opportunities o ON o.id=d.opportunity_id
            JOIN brain_prospects p ON p.id=o.prospect_id
            JOIN brain_contacts c ON c.id=d.contact_id
            WHERE d.id=? LIMIT 1
            """,
            (draft_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def record_approval(draft_id: int, *, decision: str, actor: str, note: str = "") -> bool:
    if decision not in {"approved", "rejected"}:
        raise ValueError("unsupported_draft_decision")
    conn = connect()
    try:
        row = conn.execute("SELECT status FROM brain_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row["status"] != "pending_review":
            return False
        conn.execute(
            "INSERT INTO brain_approvals(draft_id,decision,approved_by,note,created_at) VALUES(?,?,?,?,?)",
            (draft_id, decision, actor[:120], note[:800], now_iso()),
        )
        conn.execute("UPDATE brain_drafts SET status=? WHERE id=?", ("approved" if decision == "approved" else "rejected", draft_id))
        conn.commit()
        return True
    finally:
        conn.close()


def start_outreach_message(draft_id: int, *, provider: str, idempotency_key: str) -> bool:
    conn = connect()
    try:
        existing = conn.execute(
            "SELECT status FROM brain_outreach_messages WHERE draft_id=? LIMIT 1", (draft_id,)
        ).fetchone()
        if existing:
            if existing["status"] == "sent":
                return False
            conn.execute(
                "UPDATE brain_outreach_messages SET status='sending', error_text=NULL WHERE draft_id=?", (draft_id,)
            )
            conn.commit()
            return True
        conn.execute(
            """INSERT INTO brain_outreach_messages(draft_id,provider,idempotency_key,status,created_at)
               VALUES(?,?,?,?,?)""",
            (draft_id, provider[:40], idempotency_key[:200], "sending", now_iso()),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def finish_outreach_message(draft_id: int, *, sent: bool, provider_message_id: str = "", error: str = "") -> None:
    conn = connect()
    try:
        status = "sent" if sent else "failed"
        conn.execute(
            """UPDATE brain_outreach_messages
               SET status=?, sent_at=?, provider_message_id=?, error_text=? WHERE draft_id=?""",
            (status, now_iso() if sent else None, provider_message_id[:300], error[:800], draft_id),
        )
        if sent:
            conn.execute("UPDATE brain_drafts SET status='sent' WHERE id=?", (draft_id,))
        conn.commit()
    finally:
        conn.close()


def sent_count_since(*, pipeline: str, start_at: str) -> int:
    conn = connect()
    try:
        return int(conn.execute(
            """
            SELECT COUNT(*)
            FROM brain_outreach_messages m
            JOIN brain_drafts d ON d.id=m.draft_id
            JOIN brain_opportunities o ON o.id=d.opportunity_id
            JOIN brain_prospects p ON p.id=o.prospect_id
            WHERE p.pipeline=? AND m.status='sent' AND m.sent_at>=?
            """,
            (pipeline, start_at),
        ).fetchone()[0])
    finally:
        conn.close()


def record_inbound_reply(*, imap_uid: str, draft_id: int | None, kind: str, sender: str, subject: str, snippet: str, received_at: str) -> bool:
    """Store each inbound reply or bounce once so reports are auditable."""
    if kind not in {"reply", "bounce"}:
        raise ValueError("unsupported_inbound_kind")
    conn = connect()
    try:
        cur = conn.execute(
            """INSERT OR IGNORE INTO brain_inbound_replies(imap_uid,draft_id,kind,sender,subject,snippet,received_at,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (imap_uid[:160], draft_id, kind, sender[:320], subject[:500], snippet[:1200], received_at, now_iso()),
        )
        if cur.rowcount and kind == "bounce" and draft_id:
            conn.execute(
                "UPDATE brain_outreach_messages SET status='bounced', error_text=? WHERE draft_id=?",
                (snippet[:800], draft_id),
            )
        conn.commit()
        return bool(cur.rowcount)
    finally:
        conn.close()


def outreach_daily_summary(*, start_at: str, end_at: str, pipeline: str | None = None) -> dict[str, int]:
    """Return delivery facts and auditable daily research throughput."""
    conn = connect()
    try:
        scope = ""
        if pipeline:
            scope = " JOIN brain_drafts d ON d.id=m.draft_id JOIN brain_opportunities o ON o.id=d.opportunity_id JOIN brain_prospects p ON p.id=o.prospect_id AND p.pipeline=?"
            params.append(pipeline)
        sent = int(conn.execute(f"SELECT COUNT(*) FROM brain_outreach_messages m {scope} WHERE m.status IN ('sent','bounced') AND m.sent_at>=? AND m.sent_at<?", ([pipeline] if pipeline else []) + [start_at, end_at]).fetchone()[0])
        failed = int(conn.execute(f"SELECT COUNT(*) FROM brain_outreach_messages m {scope} WHERE m.status='failed' AND m.created_at>=? AND m.created_at<?", ([pipeline] if pipeline else []) + [start_at, end_at]).fetchone()[0])
        reply_scope = ""
        if pipeline:
            reply_scope = " JOIN brain_drafts d ON d.id=r.draft_id JOIN brain_opportunities o ON o.id=d.opportunity_id JOIN brain_prospects p ON p.id=o.prospect_id AND p.pipeline=?"
        bounced = int(conn.execute(f"SELECT COUNT(*) FROM brain_inbound_replies r {reply_scope} WHERE r.kind='bounce' AND r.received_at>=? AND r.received_at<?", ([pipeline] if pipeline else []) + [start_at, end_at]).fetchone()[0])
        replies = int(conn.execute(f"SELECT COUNT(*) FROM brain_inbound_replies r {reply_scope} WHERE r.kind='reply' AND r.received_at>=? AND r.received_at<?", ([pipeline] if pipeline else []) + [start_at, end_at]).fetchone()[0])
        contact_scope = ""
        if pipeline:
            contact_scope = " JOIN brain_prospects p ON p.id=c.prospect_id AND p.pipeline=?"
        contacts_found = int(conn.execute(f"SELECT COUNT(*) FROM brain_contacts c {contact_scope} WHERE c.created_at>=? AND c.created_at<?", ([pipeline] if pipeline else []) + [start_at, end_at]).fetchone()[0])
        draft_scope = ""
        if pipeline:
            draft_scope = " JOIN brain_opportunities o ON o.id=d.opportunity_id JOIN brain_prospects p ON p.id=o.prospect_id AND p.pipeline=?"
        drafts_created = int(conn.execute(f"SELECT COUNT(*) FROM brain_drafts d {draft_scope} WHERE d.created_at>=? AND d.created_at<?", ([pipeline] if pipeline else []) + [start_at, end_at]).fetchone()[0])
        run_scope = " AND pipeline=?" if pipeline else ""
        sources_checked = int(conn.execute(f"SELECT COALESCE(SUM(sources_checked), 0) FROM brain_runs WHERE finished_at>=? AND finished_at<?{run_scope}", [start_at, end_at] + ([pipeline] if pipeline else [])).fetchone()[0])
        return {
            "sent": sent,
            "failed": failed,
            "bounced": bounced,
            "replies": replies,
            "contacts_found": contacts_found,
            "drafts_created": drafts_created,
            "sources_checked": sources_checked,
        }
    finally:
        conn.close()


def runtime_state(key: str) -> str | None:
    conn = connect()
    try:
        row = conn.execute("SELECT state_value FROM brain_runtime_state WHERE state_key=?", (key[:120],)).fetchone()
        return str(row["state_value"]) if row else None
    finally:
        conn.close()


def set_runtime_state(key: str, value: str) -> None:
    conn = connect()
    try:
        conn.execute(
            """INSERT INTO brain_runtime_state(state_key,state_value,updated_at) VALUES(?,?,?)
               ON CONFLICT(state_key) DO UPDATE SET state_value=excluded.state_value,updated_at=excluded.updated_at""",
            (key[:120], value[:1000], now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def prospect_snapshot(limit: int = 50, *, pipeline: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        scope = "WHERE p.pipeline=?" if pipeline else ""
        params: list[Any] = [pipeline] if pipeline else []
        params.append(max(1, min(limit, 200)))
        return [dict(row) for row in conn.execute(
            f"""
            SELECT p.*, o.overall_score, o.decision, o.rationale_json,
                   (SELECT COUNT(1) FROM brain_evidence e WHERE e.prospect_id=p.id) AS evidence_count,
                   (SELECT COUNT(1) FROM brain_contacts c WHERE c.prospect_id=p.id) AS contact_count,
                   (SELECT COUNT(1) FROM brain_drafts d JOIN brain_opportunities od ON od.id=d.opportunity_id WHERE od.prospect_id=p.id) AS draft_count
            FROM brain_prospects p LEFT JOIN brain_opportunities o ON o.prospect_id=p.id
            {scope}
            ORDER BY COALESCE(o.overall_score,0) DESC, p.last_seen_at DESC LIMIT ?
            """, params
        ).fetchall()]
    finally:
        conn.close()


def run_snapshot(limit: int = 20) -> list[dict[str, Any]]:
    conn = connect()
    try:
        return [dict(row) for row in conn.execute("SELECT * FROM brain_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
    finally:
        conn.close()
