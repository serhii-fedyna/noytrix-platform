from __future__ import annotations

from typing import Any

from admin_telegram import queue_admin_notification


def notify_draft_for_approval(*, draft_id: int, prospect_name: str, score: int, email: str) -> None:
    local, _, domain = email.partition("@")
    masked = f"{local[:2]}***@{domain}" if domain else "контакт скрыт"
    message = (
        "✉️ Noytrix Brain — письмо ждёт решения\n\n"
        f"Компания: {prospect_name}\n"
        f"Оценка: {score}/100\n"
        f"Контакт: {masked}\n\n"
        "Выберите действие. После одобрения письмо будет отправлено с серверной почты Noytrix."
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


def notify_inbound_reply(*, prospect_name: str, sender: str, subject: str, snippet: str) -> None:
    preview = " ".join(str(snippet or "").split())[:420] or "Текст ответа недоступен."
    message = (
        "📩 Noytrix Brain — получен ответ\n\n"
        f"Компания: {prospect_name}\n"
        f"От: {sender}\n"
        f"Тема: {subject or 'без темы'}\n\n"
        f"{preview}"
    )
    queue_admin_notification(
        f"brain:reply:{sender}:{subject}:{preview[:80]}",
        "brain_partnership_reply",
        message,
        {"prospect": prospect_name, "sender": sender, "subject": subject},
    )


def notify_daily_outreach_report(*, report_date: str, sender_address: str, summary: dict[str, Any]) -> None:
    sent = int(summary.get("sent") or 0)
    failed = int(summary.get("failed") or 0)
    bounced = int(summary.get("bounced") or 0)
    replies = int(summary.get("replies") or 0)
    without_bounce = max(0, sent - bounced)
    message = (
        f"📬 Noytrix Brain — отчёт за {report_date}\n\n"
        f"Почта отправителя: {sender_address}\n"
        f"Отправлено (принято SMTP): {sent}\n"
        f"Без сообщения о недоставке: {without_bounce}\n"
        f"Ошибки отправки: {failed}\n"
        f"Сообщения о недоставке: {bounced}\n"
        f"Ответы: {replies}\n\n"
        "Показатель «без сообщения о недоставке» не является подтверждением прочтения получателем."
    )
    queue_admin_notification(
        f"brain:daily-outreach:{report_date}",
        "brain_daily_outreach_report",
        message,
        {"date": report_date, "sender": sender_address, **summary},
    )
