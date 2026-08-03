from __future__ import annotations

from . import repository
from .config import outreach_enabled
from .db import connect, now_iso


def approve_draft(draft_id: int, approved_by: str, note: str = "") -> bool:
    """Record a human decision. Approval alone never sends a message."""
    conn = connect()
    try:
        row = conn.execute("SELECT id,status FROM brain_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row["status"] != "pending_review":
            return False
        conn.execute("INSERT INTO brain_approvals(draft_id,decision,approved_by,note,created_at) VALUES(?,?,?,?,?)", (draft_id, "approved", approved_by[:120], note[:800], now_iso()))
        conn.execute("UPDATE brain_drafts SET status='approved' WHERE id=?", (draft_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def send_approved_draft(_draft_id: int) -> None:
    """Outbound delivery is intentionally unavailable until a provider rollout is approved."""
    if not outreach_enabled():
        raise RuntimeError("brain_outreach_delivery_disabled")
    raise RuntimeError("brain_outreach_provider_not_configured")
