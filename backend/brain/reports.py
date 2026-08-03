from __future__ import annotations

from typing import Any

from admin_telegram import queue_admin_notification


def notify_partnership_run(run_id: int, summary: dict[str, Any]) -> None:
    status = str(summary.get("status") or "unknown")
    sources = int(summary.get("sources_checked") or 0)
    seen = int(summary.get("prospects_seen") or 0)
    qualified = int(summary.get("prospects_qualified") or 0)
    drafts = int(summary.get("drafts_created") or 0)
    error_count = len(summary.get("errors") or [])
    message = (
        "\U0001f91d Noytrix Brain - \u043f\u0430\u0440\u0442\u043d\u0451\u0440\u0441\u043a\u0438\u0439 \u043f\u043e\u0438\u0441\u043a\n\n"
        f"\u0421\u0442\u0430\u0442\u0443\u0441: {status}\n"
        f"\u041f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043e \u043f\u0443\u0431\u043b\u0438\u0447\u043d\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432: {sources}\n"
        f"\u041a\u043e\u043c\u043f\u0430\u043d\u0438\u0439 \u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0438\u043b\u0438 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u043e: {seen}\n"
        f"\u041a\u0430\u043d\u0434\u0438\u0434\u0430\u0442\u043e\u0432 \u0434\u043b\u044f \u0440\u0443\u0447\u043d\u043e\u0433\u043e \u0440\u0430\u0441\u0441\u043c\u043e\u0442\u0440\u0435\u043d\u0438\u044f: {qualified}\n"
        f"\u041d\u043e\u0432\u044b\u0445 \u043f\u0435\u0440\u0441\u043e\u043d\u0430\u043b\u044c\u043d\u044b\u0445 \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a\u043e\u0432: {drafts}\n"
        f"\u041e\u0448\u0438\u0431\u043e\u043a \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432: {error_count}\n\n"
        "\u041f\u0438\u0441\u044c\u043c\u0430 \u043d\u0435 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u044e\u0442\u0441\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438: \u043a\u0430\u0436\u0434\u044b\u0439 \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a \u0442\u0440\u0435\u0431\u0443\u0435\u0442 \u0432\u0430\u0448\u0435\u0433\u043e \u043e\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u044f."
    )
    queue_admin_notification(f"brain:partnership-run:{run_id}", "brain_partnership_run", message, {"run_id": run_id, **summary})


def notify_high_quality_draft(*, draft_id: int, prospect_name: str, score: int, email: str) -> None:
    local, _, domain = email.partition("@")
    masked = f"{local[:2]}***@{domain}" if domain else "\u043a\u043e\u043d\u0442\u0430\u043a\u0442 \u0441\u043a\u0440\u044b\u0442"
    message = (
        "\u2709\ufe0f Noytrix Brain - \u043d\u043e\u0432\u044b\u0439 \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a\n\n"
        f"\u041a\u043e\u043c\u043f\u0430\u043d\u0438\u044f: {prospect_name}\n"
        f"\u041e\u0446\u0435\u043d\u043a\u0430 \u0432\u043e\u0437\u043c\u043e\u0436\u043d\u043e\u0441\u0442\u0438: {score}/100\n"
        f"\u041a\u043e\u043d\u0442\u0430\u043a\u0442: {masked}\n"
        f"\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a ID: {draft_id}\n\n"
        "\u041f\u0438\u0441\u044c\u043c\u043e \u043d\u0435 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e. \u041e\u043d\u043e \u043e\u0436\u0438\u0434\u0430\u0435\u0442 \u0440\u0443\u0447\u043d\u043e\u0439 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438 \u0438 \u043e\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u044f."
    )
    queue_admin_notification(f"brain:draft:{draft_id}", "brain_partnership_draft", message, {"draft_id": draft_id, "prospect": prospect_name, "score": score})
