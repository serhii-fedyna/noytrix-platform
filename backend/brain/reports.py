from __future__ import annotations

from typing import Any

from admin_telegram import queue_admin_notification


def notify_draft_for_approval(*, draft_id: int, prospect_name: str, score: int, email: str, kind: str = "partnership") -> None:
    local, _, domain = email.partition("@")
    masked = f"{local[:2]}***@{domain}" if domain else "\u043a\u043e\u043d\u0442\u0430\u043a\u0442 \u0441\u043a\u0440\u044b\u0442"
    is_job = kind == "job"
    title = "\u043e\u0442\u043a\u043b\u0438\u043a \u043d\u0430 \u0432\u0430\u043a\u0430\u043d\u0441\u0438\u044e \u0436\u0434\u0451\u0442 \u0440\u0435\u0448\u0435\u043d\u0438\u044f" if is_job else "\u043f\u0438\u0441\u044c\u043c\u043e \u0436\u0434\u0451\u0442 \u0440\u0435\u0448\u0435\u043d\u0438\u044f"
    label = "\u0420\u0430\u0431\u043e\u0442\u043e\u0434\u0430\u0442\u0435\u043b\u044c" if is_job else "\u041a\u043e\u043c\u043f\u0430\u043d\u0438\u044f"
    delivery = "\u041a \u043f\u0438\u0441\u044c\u043c\u0443 \u0431\u0443\u0434\u0435\u0442 \u043f\u0440\u0438\u043a\u0440\u0435\u043f\u043b\u0435\u043d\u043e \u0440\u0435\u0437\u044e\u043c\u0435." if is_job else "\u041f\u0438\u0441\u044c\u043c\u043e \u0431\u0443\u0434\u0435\u0442 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e \u0441 \u0441\u0435\u0440\u0432\u0435\u0440\u043d\u043e\u0439 \u043f\u043e\u0447\u0442\u044b Noytrix."
    message = (
        f"\u2709\ufe0f Noytrix Brain \u2014 {title}\n\n"
        f"{label}: {prospect_name}\n"
        f"\u041e\u0446\u0435\u043d\u043a\u0430: {score}/100\n"
        f"\u041a\u043e\u043d\u0442\u0430\u043a\u0442: {masked}\n\n"
        f"\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435. \u041f\u043e\u0441\u043b\u0435 \u043e\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u044f {delivery}"
    )
    queue_admin_notification(
        f"brain:draft:{draft_id}",
        "brain_job_draft" if is_job else "brain_partnership_draft",
        message,
        {"draft_id": draft_id, "prospect": prospect_name, "score": score, "kind": kind},
        {"inline_keyboard": [[
            {"text": "\u2705 \u041e\u0434\u043e\u0431\u0440\u0438\u0442\u044c \u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c", "callback_data": f"brain:approve:{draft_id}"},
            {"text": "\u274c \u041e\u0442\u043a\u043b\u043e\u043d\u0438\u0442\u044c", "callback_data": f"brain:reject:{draft_id}"},
        ]]},
    )


def notify_inbound_reply(*, prospect_name: str, sender: str, subject: str, snippet: str, kind: str = "partnership") -> None:
    preview = " ".join(str(snippet or "").split())[:420] or "\u0422\u0435\u043a\u0441\u0442 \u043e\u0442\u0432\u0435\u0442\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d."
    safe_subject = subject or "\u0431\u0435\u0437 \u0442\u0435\u043c\u044b"
    label = "\u0420\u0430\u0431\u043e\u0442\u043e\u0434\u0430\u0442\u0435\u043b\u044c" if kind == "job" else "\u041a\u043e\u043c\u043f\u0430\u043d\u0438\u044f"
    title = "\u043e\u0442\u0432\u0435\u0442 \u043d\u0430 \u043e\u0442\u043a\u043b\u0438\u043a" if kind == "job" else "\u043f\u043e\u043b\u0443\u0447\u0435\u043d \u043e\u0442\u0432\u0435\u0442"
    message = (
        f"\U0001f4e9 Noytrix Brain \u2014 {title}\n\n"
        f"{label}: {prospect_name}\n"
        f"\u041e\u0442: {sender}\n"
        f"\u0422\u0435\u043c\u0430: {safe_subject}\n\n{preview}"
    )
    queue_admin_notification(
        f"brain:reply:{sender}:{subject}:{preview[:80]}",
        "brain_job_reply" if kind == "job" else "brain_partnership_reply",
        message,
        {"prospect": prospect_name, "sender": sender, "subject": subject, "kind": kind},
    )


def _summary_lines(summary: dict[str, Any]) -> str:
    sent = int(summary.get("sent") or 0)
    failed = int(summary.get("failed") or 0)
    bounced = int(summary.get("bounced") or 0)
    replies = int(summary.get("replies") or 0)
    contacts_found = int(summary.get("contacts_found") or 0)
    drafts_created = int(summary.get("drafts_created") or 0)
    sources_checked = int(summary.get("sources_checked") or 0)
    without_bounce = max(0, sent - bounced)
    return (
        f"\u041f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043e \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432: {sources_checked}\n"
        f"\u041d\u0430\u0439\u0434\u0435\u043d\u043e \u043f\u0443\u0431\u043b\u0438\u0447\u043d\u044b\u0445 \u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043e\u0432: {contacts_found}\n"
        f"\u041f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u043b\u0435\u043d\u043e \u043f\u0438\u0441\u0435\u043c: {drafts_created}\n"
        f"\u041e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e (\u043f\u0440\u0438\u043d\u044f\u0442\u043e SMTP): {sent}\n"
        f"\u0411\u0435\u0437 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u043e \u043d\u0435\u0434\u043e\u0441\u0442\u0430\u0432\u043a\u0435: {without_bounce}\n"
        f"\u041e\u0448\u0438\u0431\u043a\u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u043a\u0438: {failed}\n"
        f"\u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u043e \u043d\u0435\u0434\u043e\u0441\u0442\u0430\u0432\u043a\u0435: {bounced}\n"
        f"\u041e\u0442\u0432\u0435\u0442\u044b: {replies}\n"
    )


def notify_daily_outreach_report(*, report_date: str, sender_address: str, summary: dict[str, Any], job_summary: dict[str, Any] | None = None) -> None:
    message = (
        f"\U0001f4ec Noytrix Brain \u2014 \u043e\u0442\u0447\u0451\u0442 \u0437\u0430 {report_date}\n\n"
        "\U0001f91d \u041f\u0430\u0440\u0442\u043d\u0451\u0440\u0441\u0442\u0432\u0430\n" + _summary_lines(summary)
    )
    if job_summary is not None:
        message += "\n\U0001f4bc \u0412\u0430\u043a\u0430\u043d\u0441\u0438\u0438 \u0438 \u043e\u0442\u043a\u043b\u0438\u043a\u0438\n" + _summary_lines(job_summary)
    message += f"\n\u041f\u043e\u0447\u0442\u0430 \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u0435\u043b\u044f: {sender_address}\n"
    message += "\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u044c \u00ab\u0431\u0435\u0437 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u043e \u043d\u0435\u0434\u043e\u0441\u0442\u0430\u0432\u043a\u0435\u00bb \u043d\u0435 \u043e\u0437\u043d\u0430\u0447\u0430\u0435\u0442, \u0447\u0442\u043e \u043f\u0438\u0441\u044c\u043c\u043e \u0431\u044b\u043b\u043e \u043f\u0440\u043e\u0447\u0438\u0442\u0430\u043d\u043e \u043f\u043e\u043b\u0443\u0447\u0430\u0442\u0435\u043b\u0435\u043c."
    queue_admin_notification(
        f"brain:daily-outreach:{report_date}",
        "brain_daily_outreach_report",
        message,
        {"date": report_date, "sender": sender_address, "partnerships": summary, "jobs": job_summary or {}},
    )
