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
    github = int(summary.get("github_candidates") or 0)
    investors = int(summary.get("investors_cataloged") or 0)
    message = (
        "\U0001f91d Noytrix Brain - \u043f\u0430\u0440\u0442\u043d\u0451\u0440\u0441\u043a\u0438\u0439 \u043f\u043e\u0438\u0441\u043a\n\n"
        f"\u0421\u0442\u0430\u0442\u0443\u0441: {status}\n"
        f"\u041f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043e \u043f\u0443\u0431\u043b\u0438\u0447\u043d\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432: {sources}\n"
        f"\u041a\u043e\u043c\u043f\u0430\u043d\u0438\u0439 \u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0438\u043b\u0438 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u043e: {seen}\n"
        f"\u041a\u0430\u043d\u0434\u0438\u0434\u0430\u0442\u043e\u0432 \u0434\u043b\u044f \u0440\u0443\u0447\u043d\u043e\u0433\u043e \u0440\u0430\u0441\u0441\u043c\u043e\u0442\u0440\u0435\u043d\u0438\u044f: {qualified}\n"
        f"\u041d\u043e\u0432\u044b\u0445 \u043f\u0435\u0440\u0441\u043e\u043d\u0430\u043b\u044c\u043d\u044b\u0445 \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a\u043e\u0432: {drafts}\n"
        f"\u041f\u0440\u043e\u0435\u043a\u0442\u043e\u0432 \u0438\u0437 GitHub: {github}\n"
        f"\u041f\u0443\u0431\u043b\u0438\u0447\u043d\u044b\u0445 \u0438\u043d\u0432\u0435\u0441\u0442\u043e\u0440\u0441\u043a\u0438\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432: {investors}\n"
        f"\u041e\u0448\u0438\u0431\u043e\u043a \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432: {error_count}\n\n"
        "\u041f\u0438\u0441\u044c\u043c\u0430 \u0441 \u043e\u0446\u0435\u043d\u043a\u043e\u0439 \u0432\u044b\u0448\u0435 70 \u0438 \u043f\u0443\u0431\u043b\u0438\u0447\u043d\u044b\u043c \u043a\u043e\u0440\u043f\u043e\u0440\u0430\u0442\u0438\u0432\u043d\u044b\u043c \u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043e\u043c \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u044e\u0442\u0441\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438; \u043e\u0441\u0442\u0430\u043b\u044c\u043d\u044b\u0435 \u0436\u0434\u0443\u0442 \u0440\u0435\u0448\u0435\u043d\u0438\u044f \u0432 Telegram."
    )
    queue_admin_notification(f"brain:partnership-run:{run_id}", "brain_partnership_run", message, {"run_id": run_id, **summary})


def notify_draft_for_approval(*, draft_id: int, prospect_name: str, score: int, email: str) -> None:
    local, _, domain = email.partition("@")
    masked = f"{local[:2]}***@{domain}" if domain else "\u043a\u043e\u043d\u0442\u0430\u043a\u0442 \u0441\u043a\u0440\u044b\u0442"
    message = (
        "\u2709\ufe0f Noytrix Brain - \u043d\u043e\u0432\u044b\u0439 \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a\n\n"
        f"\u041a\u043e\u043c\u043f\u0430\u043d\u0438\u044f: {prospect_name}\n"
        f"\u041e\u0446\u0435\u043d\u043a\u0430 \u0432\u043e\u0437\u043c\u043e\u0436\u043d\u043e\u0441\u0442\u0438: {score}/100\n"
        f"\u041a\u043e\u043d\u0442\u0430\u043a\u0442: {masked}\n"
        f"\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a ID: {draft_id}\n\n"
        "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435: \u043f\u043e\u0441\u043b\u0435 \u043e\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u044f \u043f\u0438\u0441\u044c\u043c\u043e \u0431\u0443\u0434\u0435\u0442 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e \u0447\u0435\u0440\u0435\u0437 \u0441\u0435\u0440\u0432\u0435\u0440\u043d\u044b\u0439 SMTP."
    )
    queue_admin_notification(
        f"brain:draft:{draft_id}",
        "brain_partnership_draft",
        message,
        {"draft_id": draft_id, "prospect": prospect_name, "score": score},
        {
            "inline_keyboard": [[
                {"text": "✅ Одобрить и отправить", "callback_data": f"brain:approve:{draft_id}"},
                {"text": "❌ Отклонить", "callback_data": f"brain:reject:{draft_id}"},
            ]]
        },
    )


def notify_auto_delivery(*, draft_id: int, prospect_name: str, score: int, status: str) -> None:
    message = (
        "\U0001f4e8 Noytrix Brain - автоматическая отправка\n\n"
        f"Компания: {prospect_name}\n"
        f"Оценка: {score}/100\n"
        f"Черновик ID: {draft_id}\n"
        f"Статус: {status}\n\n"
        "Письмо отправляется автоматически только при оценке выше 70 и подтверждённом публичном корпоративном контакте."
    )
    queue_admin_notification(
        f"brain:auto-delivery:{draft_id}:{status}",
        "brain_partnership_auto_delivery",
        message,
        {"draft_id": draft_id, "prospect": prospect_name, "score": score, "status": status},
    )
