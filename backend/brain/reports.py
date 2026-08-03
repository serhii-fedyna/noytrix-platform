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
        "🤝 Noytrix Brain — партнёрства\n\n"
        f"Статус запуска: {status}\n"
        f"Публичных источников проверено: {sources}\n"
        f"Компаний найдено/обновлено: {seen}\n"
        f"Кандидатов для рассмотрения: {qualified}\n"
        f"Новых персональных черновиков: {drafts}\n"
        f"Ошибок источников: {error_count}\n\n"
        "Отправка писем отключена до ручного одобрения каждого черновика."
    )
    queue_admin_notification(
        f"brain:partnership-run:{run_id}",
        "brain_partnership_run",
        message,
        {"run_id": run_id, **summary},
    )


def notify_high_quality_draft(*, draft_id: int, prospect_name: str, score: int, email: str) -> None:
    local, _, domain = email.partition("@")
    masked = f"{local[:2]}***@{domain}" if domain else "контакт скрыт"
    message = (
        "✉️ Noytrix Brain — новый черновик\n\n"
        f"Компания: {prospect_name}\n"
        f"Оценка возможности: {score}/100\n"
        f"Контакт: {masked}\n"
        f"Черновик ID: {draft_id}\n\n"
        "Письмо не отправлено. Оно ожидает ручной проверки и одобрения."
    )
    queue_admin_notification(
        f"brain:draft:{draft_id}",
        "brain_partnership_draft",
        message,
        {"draft_id": draft_id, "prospect": prospect_name, "score": score},
    )
