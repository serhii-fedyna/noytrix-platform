from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import admin_telegram

from .outreach import approve_draft, reject_draft, send_approved_draft
from .repository import runtime_state, set_runtime_state


STATE_KEY = "telegram_callback_offset"


def _telegram_call(token: str, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{admin_telegram.TELEGRAM_API_ROOT}/bot{token}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        result = json.loads(response.read().decode("utf-8") or "{}")
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"telegram_{method}_failed")
    return result


def _get_updates(token: str, offset: int) -> list[dict[str, Any]]:
    params = urlencode({"offset": offset, "timeout": 0, "allowed_updates": json.dumps(["callback_query"])})
    request = Request(
        f"{admin_telegram.TELEGRAM_API_ROOT}/bot{token}/getUpdates?{params}",
        headers={"User-Agent": "NoytrixBrain/1.0"},
    )
    with urlopen(request, timeout=15) as response:
        result = json.loads(response.read().decode("utf-8") or "{}")
    return list(result.get("result") or []) if isinstance(result, dict) and result.get("ok") else []


def _answer(token: str, callback_id: str, text: str) -> None:
    try:
        _telegram_call(token, "answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:180]})
    except Exception:
        pass


def _clear_buttons(token: str, chat_id: str, message_id: int) -> None:
    try:
        _telegram_call(token, "editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id, "reply_markup": {"inline_keyboard": []}})
    except Exception:
        pass


def process_telegram_actions_once() -> int:
    """Process only signed-in admin button clicks. Other bot messages are ignored."""
    config = admin_telegram._config()
    if not config:
        return 0
    token, configured_chat_id = config
    try:
        offset = int(runtime_state(STATE_KEY) or "0")
    except ValueError:
        offset = 0
    processed = 0
    for update in _get_updates(token, offset):
        update_id = int(update.get("update_id") or 0)
        if update_id:
            set_runtime_state(STATE_KEY, str(update_id + 1))
        callback = update.get("callback_query") or {}
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        if str(chat.get("id") or "") != str(configured_chat_id):
            continue
        data = str(callback.get("data") or "")
        parts = data.split(":")
        if len(parts) != 3 or parts[0] != "brain" or parts[1] not in {"approve", "reject"}:
            continue
        try:
            draft_id = int(parts[2])
        except ValueError:
            _answer(token, str(callback.get("id") or ""), "Некорректное действие.")
            continue
        actor = f"telegram:{configured_chat_id}"
        if parts[1] == "reject":
            accepted = reject_draft(draft_id, actor, "Rejected in Telegram")
            text = "Черновик отклонён." if accepted else "Этот черновик уже обработан."
        else:
            accepted = approve_draft(draft_id, actor, "Approved in Telegram")
            if accepted:
                try:
                    result = send_approved_draft(draft_id)
                    text = "Письмо отправлено." if result.get("status") == "sent" else "Письмо уже было отправлено."
                except Exception:
                    text = "Одобрено, но отправить письмо не удалось. Событие сохранено для проверки."
            else:
                text = "Этот черновик уже обработан."
        _answer(token, str(callback.get("id") or ""), text)
        if accepted:
            _clear_buttons(token, str(configured_chat_id), int(message.get("message_id") or 0))
        admin_telegram.queue_admin_notification(
            f"brain:telegram-action:{draft_id}:{parts[1]}",
            "brain_telegram_action",
            f"Noytrix Brain: {text} Черновик ID: {draft_id}",
            {"draft_id": draft_id, "action": parts[1], "accepted": accepted},
        )
        processed += 1
    return processed


async def brain_telegram_actions_loop() -> None:
    await asyncio.sleep(15)
    while True:
        try:
            await asyncio.to_thread(process_telegram_actions_once)
            await asyncio.sleep(12)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print("[noytrix_brain] Telegram action loop error:", str(exc)[:180])
            await asyncio.sleep(60)
