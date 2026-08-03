from __future__ import annotations

import hashlib

from . import repository
from .config import outreach_enabled


def approve_draft(draft_id: int, approved_by: str, note: str = "") -> bool:
    """Record an explicit human approval; delivery is a separate idempotent action."""
    return repository.record_approval(draft_id, decision="approved", actor=approved_by, note=note)


def reject_draft(draft_id: int, rejected_by: str, note: str = "") -> bool:
    return repository.record_approval(draft_id, decision="rejected", actor=rejected_by, note=note)


def _delivery_key(draft: dict) -> str:
    raw = f"noytrix-brain|{draft['id']}|{draft['email']}|{draft['subject']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def send_approved_draft(draft_id: int) -> dict:
    """Send one approved message once, keeping the complete provider audit in Brain."""
    if not outreach_enabled():
        raise RuntimeError("brain_outreach_delivery_disabled")
    draft = repository.draft_delivery_snapshot(draft_id)
    if not draft:
        raise ValueError("brain_draft_not_found")
    if draft["status"] == "sent":
        return {"status": "already_sent", "draft_id": draft_id}
    if draft["status"] != "approved":
        raise RuntimeError("brain_draft_not_approved")
    if draft.get("contact_status") != "available" or repository.is_suppressed(str(draft.get("email") or "")):
        raise RuntimeError("brain_contact_not_available")

    if not repository.start_outreach_message(draft_id, provider="smtp", idempotency_key=_delivery_key(draft)):
        return {"status": "already_sent", "draft_id": draft_id}
    try:
        from auth.emailer import send_business_email

        send_business_email(str(draft["email"]), str(draft["subject"]), str(draft["body"]))
    except Exception as exc:
        repository.finish_outreach_message(draft_id, sent=False, error=str(exc))
        raise RuntimeError("brain_outreach_delivery_failed") from exc
    repository.finish_outreach_message(draft_id, sent=True, provider_message_id="smtp")
    return {"status": "sent", "draft_id": draft_id, "prospect": draft["prospect_name"]}


def auto_send_draft(draft_id: int) -> dict:
    """Only score-qualified drafts use this path; it still goes through the normal audit."""
    if not approve_draft(draft_id, "brain:auto_score_over_70", "Automatic delivery: score above 70."):
        return {"status": "not_pending", "draft_id": draft_id}
    return send_approved_draft(draft_id)
