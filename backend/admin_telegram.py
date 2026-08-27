"""Private operational alerts for the Noytrix administrator.

The module deliberately keeps Telegram credentials outside source control.  It
records every alert in a local audit store first, then sends it asynchronously
when the integration is enabled.  A Telegram delivery failure never blocks a
registration, payment verification, feedback submission, or scan.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import threading
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import product_analytics


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ADMIN_ALERTS_DB_PATH = DATA_DIR / "admin_telegram.sqlite3"
TELEGRAM_API_ROOT = "https://api.telegram.org"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(ADMIN_ALERTS_DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def init_admin_telegram_db() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_telegram_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_key TEXT NOT NULL UNIQUE,
              event_type TEXT NOT NULL,
              message_text TEXT NOT NULL,
              payload_json TEXT NOT NULL DEFAULT '{}',
              reply_markup_json TEXT NOT NULL DEFAULT '{}',
              status TEXT NOT NULL DEFAULT 'queued',
              attempts INTEGER NOT NULL DEFAULT 0,
              telegram_message_id TEXT,
              created_at TEXT NOT NULL,
              sent_at TEXT,
              last_error TEXT
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(admin_telegram_events)").fetchall()}
        if "reply_markup_json" not in columns:
            conn.execute("ALTER TABLE admin_telegram_events ADD COLUMN reply_markup_json TEXT NOT NULL DEFAULT '{}'")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_admin_telegram_events_created ON admin_telegram_events(created_at)"
        )
        conn.commit()
    finally:
        conn.close()


init_admin_telegram_db()


def _enabled() -> bool:
    return str(os.getenv("NOYTRIX_ADMIN_TELEGRAM_ENABLED", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _config() -> tuple[str, str] | None:
    token = str(os.getenv("NOYTRIX_ADMIN_TELEGRAM_TOKEN", "")).strip()
    chat_id = str(os.getenv("NOYTRIX_ADMIN_TELEGRAM_CHAT_ID", "")).strip()
    if not _enabled() or not token or not chat_id:
        return None
    return token, chat_id


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return "{}"


def _mask_email(value: Any) -> str:
    email = str(value or "").strip().lower()
    if "@" not in email:
        return "не указан"
    local, domain = email.split("@", 1)
    visible = local[:3] if len(local) > 3 else local[:1]
    return f"{visible}***@{domain}"


def _short_user_id(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "не определён"
    return raw[:10] + ("…" if len(raw) > 10 else "")


def _store_event(
    event_key: str,
    event_type: str,
    message: str,
    payload: dict[str, Any] | None = None,
    reply_markup: dict[str, Any] | None = None,
) -> int | None:
    conn = _connect()
    try:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO admin_telegram_events(
              event_key, event_type, message_text, payload_json, reply_markup_json, status, created_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (event_key[:240], event_type[:80], message[:3900], _safe_json(payload), _safe_json(reply_markup), "queued", _now_iso()),
        )
        conn.commit()
        return int(cursor.lastrowid) if cursor.rowcount else None
    finally:
        conn.close()


def _deliver_event(event_id: int) -> None:
    config = _config()
    if not config:
        return
    token, chat_id = config
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT message_text, reply_markup_json, status FROM admin_telegram_events WHERE id=? LIMIT 1", (event_id,)
        ).fetchone()
        if not row or row["status"] == "sent":
            return
        stale_before = (datetime.now(timezone.utc) - timedelta(minutes=15)).replace(microsecond=0).isoformat()
        claim = conn.execute(
            """
            UPDATE admin_telegram_events
            SET status='sending', attempts=attempts+1
            WHERE id=?
              AND (
                status IN ('queued', 'failed')
                OR (status='sending' AND created_at <= ?)
              )
            """,
            (event_id, stale_before),
        )
        conn.commit()
        if claim.rowcount != 1:
            return
        message = str(row["message_text"] or "")
        try:
            reply_markup = json.loads(str(row["reply_markup_json"] or "{}"))
        except Exception:
            reply_markup = {}
    finally:
        conn.close()

    try:
        request_payload: dict[str, Any] = {"chat_id": chat_id, "text": message, "disable_web_page_preview": True}
        if isinstance(reply_markup, dict) and reply_markup:
            request_payload["reply_markup"] = reply_markup
        body = json.dumps(
            request_payload,
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            f"{TELEGRAM_API_ROOT}/bot{token}/sendMessage",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=12) as response:
            result = json.loads(response.read().decode("utf-8") or "{}")
        if not isinstance(result, dict) or not result.get("ok"):
            raise RuntimeError("Telegram rejected the notification")
        message_id = ((result.get("result") or {}).get("message_id")) if isinstance(result, dict) else None
        conn = _connect()
        try:
            conn.execute(
                "UPDATE admin_telegram_events SET status='sent', sent_at=?, telegram_message_id=?, last_error=NULL WHERE id=?",
                (_now_iso(), str(message_id or ""), event_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        conn = _connect()
        try:
            conn.execute(
                "UPDATE admin_telegram_events SET status='failed', last_error=? WHERE id=?",
                (str(exc)[:500], event_id),
            )
            conn.commit()
        finally:
            conn.close()
        print("[admin_telegram] delivery failed:", str(exc)[:180])


def queue_admin_notification(
    event_key: str,
    event_type: str,
    message: str,
    payload: dict[str, Any] | None = None,
    reply_markup: dict[str, Any] | None = None,
) -> bool:
    """Persist once and send in a background thread when configured."""
    try:
        event_id = _store_event(event_key, event_type, message, payload, reply_markup)
    except Exception as exc:
        print("[admin_telegram] audit store failed:", str(exc)[:180])
        return False
    if event_id is None:
        return False
    if _config():
        threading.Thread(target=_deliver_event, args=(event_id,), daemon=True).start()
    return True


def deliver_pending_notifications(limit: int = 100) -> int:
    """Retry persisted alerts after credentials are configured or Telegram recovers."""
    if not _config():
        return 0
    conn = _connect()
    try:
        stale_before = (datetime.now(timezone.utc) - timedelta(minutes=15)).replace(microsecond=0).isoformat()
        rows = conn.execute(
            """
            SELECT id FROM admin_telegram_events
            WHERE status IN ('queued', 'failed')
               OR (status='sending' AND created_at <= ?)
            ORDER BY id ASC LIMIT ?
            """,
            (stale_before, max(1, min(int(limit), 500))),
        ).fetchall()
    finally:
        conn.close()
    for row in rows:
        _deliver_event(int(row["id"]))
    return len(rows)


def notify_registration(*, user_id: str, email: str, country: str | None = None, total_users: int | None = None, source: str = "registration") -> None:
    timestamp = datetime.now().astimezone().strftime("%d.%m.%Y, %H:%M")
    total = str(total_users) if total_users is not None else "обновляется"
    message = (
        "🎉 Новая регистрация\n"
        f"Пользователь: {_mask_email(email)}\n"
        f"Страна: {country or 'не определена'}\n"
        f"Источник: {source}\n"
        f"Время: {timestamp}\n"
        f"Всего пользователей: {total}"
    )
    queue_admin_notification(
        f"registration:{user_id}", "registration", message,
        {"user_id": user_id, "email_masked": _mask_email(email), "source": source},
    )


def notify_subscription_event(*, event_key: str, user_id: str, provider: str, event_type: str, status: str, product_id: str | None = None, expires_at: str | None = None) -> None:
    kind = str(event_type or "").upper()
    status_low = str(status or "").lower()
    if kind in {"CANCELLATION", "SUBSCRIPTION_PAUSED"} or status_low in {"cancelled", "canceled"}:
        title = "⚠️ Подписка отменена"
    elif kind in {"BILLING_ISSUE", "PRODUCT_NOT_PROVIDED"} or status_low in {"billing_issue", "pending"}:
        title = "⚠️ Проблема с оплатой"
    elif kind in {"REFUND", "EXPIRATION"} or status_low in {"refund", "expired"}:
        title = "↩️ PRO-доступ завершён"
    elif kind in {"INITIAL_PURCHASE", "RENEWAL", "NON_RENEWING_PURCHASE", "PURCHASE_REDEEMED"} or status_low in {"active", "trial"}:
        title = "💳 Новая подписка" if kind != "RENEWAL" else "🔄 Подписка продлена"
    else:
        title = "💳 Обновление подписки"
    lines = [
        title,
        f"Пользователь: {_short_user_id(user_id)}",
        f"Провайдер: {provider}",
        f"Статус: {status or 'unknown'}",
    ]
    if product_id:
        lines.append(f"Тариф: {product_id}")
    if expires_at:
        lines.append(f"Действует до: {expires_at[:19]}")
    queue_admin_notification(
        f"subscription:{event_key}", "subscription", "\n".join(lines),
        {"user_id": user_id, "provider": provider, "event_type": event_type, "status": status, "product_id": product_id},
    )


def notify_feedback(*, event_key: str, flow: str, user_id: str | None, nps: int | None, most_useful: str | None, problem: str | None, requested_feature: str | None) -> None:
    title = "⭐ Новый положительный отзыв" if flow == "positive" else "📝 Новая обратная связь"
    lines = [title, f"Пользователь: {_short_user_id(user_id)}"]
    if nps is not None:
        lines.append(f"Оценка рекомендации: {nps}/10")
    if most_useful:
        lines.append(f"Полезно: {most_useful[:300]}")
    if problem:
        lines.append(f"Проблема: {problem[:300]}")
    if requested_feature:
        lines.append(f"Запрос: {requested_feature[:500]}")
    queue_admin_notification(
        f"feedback:{event_key}", "feedback", "\n".join(lines),
        {"flow": flow, "user_id": user_id, "nps": nps},
    )


def notify_critical_error(*, path: str, status_code: int, error: Any) -> None:
    now = datetime.now(timezone.utc)
    clean_error = str(error or "unknown server error").replace("\n", " ")[:360]
    fingerprint = hashlib.sha256(f"{path}|{status_code}|{clean_error}|{now:%Y%m%d%H}".encode("utf-8")).hexdigest()[:18]
    message = (
        "🚨 Критическая ошибка сервера\n"
        f"Путь: {path[:160]}\n"
        f"Код ответа: {status_code}\n"
        f"Ошибка: {clean_error}\n"
        f"Время UTC: {now:%d.%m.%Y, %H:%M}"
    )
    queue_admin_notification(
        f"server_error:{fingerprint}", "critical_server_error", message,
        {"path": path[:160], "status_code": status_code, "error": clean_error},
    )


def _timezone() -> ZoneInfo:
    name = str(os.getenv("NOYTRIX_ADMIN_TELEGRAM_TIMEZONE", "Europe/Kyiv")).strip() or "Europe/Kyiv"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Kyiv")


def _read_properties(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _scan_kind(properties: dict[str, Any]) -> str:
    raw = str(
        properties.get("kind")
        or properties.get("scan_type")
        or properties.get("object_type")
        or properties.get("analysis_type")
        or ""
    ).strip().lower()
    if raw in {"url", "domain", "link", "website", "text"}:
        return "links"
    if raw in {"token", "ticker", "coin"}:
        return "tokens"
    if raw in {"wallet", "address", "account"}:
        return "wallets"
    if raw in {"contract", "smart_contract"}:
        return "contracts"
    return "other"


def _is_dangerous(properties: dict[str, Any]) -> bool:
    level = str(properties.get("level") or properties.get("risk_level") or properties.get("verdict") or "").lower()
    if level in {"critical", "high", "danger", "dangerous", "scam", "malicious"}:
        return True
    try:
        return float(properties.get("score") or properties.get("risk_score") or 0) >= 70
    except Exception:
        return False


def _count_recent_critical_errors(start_utc: datetime, end_utc: datetime) -> int:
    conn = _connect()
    try:
        return int(conn.execute(
            """
            SELECT COUNT(1) FROM admin_telegram_events
            WHERE event_type='critical_server_error' AND created_at>=? AND created_at<?
            """,
            (start_utc.isoformat(), end_utc.isoformat()),
        ).fetchone()[0])
    finally:
        conn.close()


def _event_identity(row: sqlite3.Row, *, prefer_anonymous: bool = False) -> str:
    """Return one stable identity for a metric without counting repeats."""
    values = (
        (row["anonymous_id"], row["user_id"])
        if prefer_anonymous
        else (row["user_id"], row["anonymous_id"])
    )
    for value in values:
        identity = str(value or "").strip()
        if identity:
            return identity
    return ""


def _payment_funnel_for_day(start_utc: datetime, end_utc: datetime) -> dict[str, int]:
    metrics = {
        "paywall_viewed": 0,
        "purchase_started": 0,
        "purchase_completed": 0,
        "purchase_cancelled": 0,
        "purchase_failed": 0,
    }
    analytics_path = product_analytics.ANALYTICS_DB_PATH
    if not analytics_path.exists():
        return metrics

    users = {name: set() for name in metrics}
    conn = sqlite3.connect(analytics_path, timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT event_name, user_id, anonymous_id
            FROM product_events
            WHERE event_name IN ('paywall_viewed', 'purchase_started', 'purchase_completed',
                                 'purchase_cancelled', 'purchase_failed')
              AND event_time>=? AND event_time<?
            """,
            (start_utc.isoformat(), end_utc.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        identity = _event_identity(row)
        if identity:
            users[row["event_name"]].add(identity)
    return {name: len(items) for name, items in users.items()}


def _total_unique_installs() -> int:
    """Count each known installation once, preferring its anonymous install ID."""
    analytics_path = product_analytics.ANALYTICS_DB_PATH
    if not analytics_path.exists():
        return 0

    conn = sqlite3.connect(analytics_path, timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT user_id, anonymous_id FROM product_events WHERE event_name='app_first_open'"
        ).fetchall()
    finally:
        conn.close()
    return len({identity for row in rows if (identity := _event_identity(row, prefer_anonymous=True))})


def _tracking_activity_for_day(start_utc: datetime, end_utc: datetime) -> dict[str, dict[str, int]]:
    names = tuple(sorted(name for name in product_analytics.ALLOWED_EVENTS if name.startswith("tracking_") or name == "platform_impact_viewed"))
    result = {name: {"events": 0, "users": 0} for name in names}
    if not product_analytics.ANALYTICS_DB_PATH.exists() or not names:
        return result
    placeholders = ",".join("?" for _ in names)
    conn = sqlite3.connect(product_analytics.ANALYTICS_DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT event_name,user_id,anonymous_id FROM product_events WHERE event_name IN ({placeholders}) AND event_time>=? AND event_time<?",
            (*names, start_utc.isoformat(), end_utc.isoformat()),
        ).fetchall()
    finally:
        conn.close()
    identities: dict[str, set[str]] = {name: set() for name in names}
    for row in rows:
        name = str(row["event_name"])
        result[name]["events"] += 1
        identity = _event_identity(row)
        if identity:
            identities[name].add(identity)
    for name in names:
        result[name]["users"] = len(identities[name])
    return result


def _outreach_activity_for_day(start_utc: datetime, end_utc: datetime) -> dict[str, dict[str, int]]:
    blank = {"sent": 0, "failed": 0, "bounced": 0, "replies": 0, "contactsFound": 0, "draftsCreated": 0, "sourcesChecked": 0}
    try:
        from brain.repository import outreach_daily_summary
        args = {"start_at": start_utc.isoformat(), "end_at": end_utc.isoformat()}
        return {
            "partnerships": {**blank, **outreach_daily_summary(**args, pipeline="noytrix_partnerships")},
            "jobs": {**blank, **outreach_daily_summary(**args, pipeline="serhii_job_search")},
        }
    except Exception as exc:
        print("[admin_telegram] outreach metrics unavailable:", str(exc)[:180])
        return {"partnerships": dict(blank), "jobs": dict(blank)}


def build_daily_scan_summary(report_day: date | None = None) -> tuple[str, dict[str, Any]]:
    tz = _timezone()
    local_day = report_day or datetime.now(tz).date()
    start_local = datetime.combine(local_day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc).replace(microsecond=0)
    end_utc = end_local.astimezone(timezone.utc).replace(microsecond=0)
    counts = {"links": 0, "tokens": 0, "wallets": 0, "contracts": 0, "other": 0}
    completed = failed = dangerous = 0
    unique_users: set[str] = set()

    analytics_path = product_analytics.ANALYTICS_DB_PATH
    if analytics_path.exists():
        conn = sqlite3.connect(analytics_path, timeout=20)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT event_name, user_id, anonymous_id, properties_json
                FROM product_events
                WHERE event_name IN ('scan_completed','scan_failed')
                  AND source='backend_scan'
                  AND event_time>=? AND event_time<?
                """,
                (start_utc.isoformat(), end_utc.isoformat()),
            ).fetchall()
        finally:
            conn.close()
        for row in rows:
            props = _read_properties(row["properties_json"])
            user = str(row["user_id"] or row["anonymous_id"] or "").strip()
            if user:
                unique_users.add(user)
            if row["event_name"] == "scan_failed":
                failed += 1
                continue
            completed += 1
            counts[_scan_kind(props)] += 1
            if _is_dangerous(props):
                dangerous += 1

    total = completed + failed
    error_count = _count_recent_critical_errors(start_utc, end_utc)
    payment_funnel = _payment_funnel_for_day(start_utc, end_utc)
    total_unique_installs = _total_unique_installs()
    tracking = _tracking_activity_for_day(start_utc, end_utc)
    outreach = _outreach_activity_for_day(start_utc, end_utc)
    message = (
        f"📊 Noytrix — сводка за {local_day.strftime('%d.%m.%Y')}\n\n"
        f"Всего сканов: {total}\n"
        f"Уникальных пользователей: {len(unique_users)}\n\n"
        f"🔗 Ссылки и сайты: {counts['links']}\n"
        f"🪙 Токены: {counts['tokens']}\n"
        f"👛 Кошельки: {counts['wallets']}\n"
        f"📄 Контракты: {counts['contracts']}\n"
        f"📦 Другие проверки: {counts['other']}\n\n"
        f"✅ Успешно: {completed}\n"
        f"❌ Неуспешно: {failed}\n"
        f"🚨 Опасных объектов найдено: {dangerous}\n"
        f"⚠️ Критических ошибок сервера: {error_count}"
    )
    message += (
        f"\n\n💳 PRO за этот день (уникальные пользователи)\n"
        f"Открыли экран PRO: {payment_funnel['paywall_viewed']}\n"
        f"Начали оплату: {payment_funnel['purchase_started']}\n"
        f"Успешно купили: {payment_funnel['purchase_completed']}\n"
        f"Отменили оплату: {payment_funnel['purchase_cancelled']}\n"
        f"Ошибка оплаты: {payment_funnel['purchase_failed']}\n\n"
        f"📱 Уникальных установок за всё время: {total_unique_installs}"
    )
    message += (
        "\n\n👁 Наблюдение — реальные события приложения\n"
        f"Открыли страницу: {tracking['tracking_screen_opened']['users']} чел. / {tracking['tracking_screen_opened']['events']} раз\n"
        f"Добавили объект: {tracking['tracking_object_added']['users']} чел. / {tracking['tracking_object_added']['events']} раз\n"
        f"Открыли объект: {tracking['tracking_object_opened']['users']} чел. / {tracking['tracking_object_opened']['events']} раз\n"
        f"Запустили перепроверку: {tracking['tracking_recheck_started']['users']} чел. / {tracking['tracking_recheck_started']['events']} раз\n"
        f"Удалили объект: {tracking['tracking_object_removed']['users']} чел. / {tracking['tracking_object_removed']['events']} раз\n"
        f"Увидели счётчик платформы: {tracking['platform_impact_viewed']['users']} чел. / {tracking['platform_impact_viewed']['events']} раз"
    )
    message += (
        "\n\n📬 Поиск работы и партнёрств — реальные записи backend\n"
        f"Работа: отправлено {outreach['jobs']['sent']}, ответов {outreach['jobs']['replies']}, ошибок {outreach['jobs']['failed']}\n"
        f"B2B: отправлено {outreach['partnerships']['sent']}, ответов {outreach['partnerships']['replies']}, ошибок {outreach['partnerships']['failed']}"
    )
    return message, {
        "day": local_day.isoformat(), "total": total, "completed": completed,
        "failed": failed, "dangerous": dangerous, "unique_users": len(unique_users),
        "counts": counts, "critical_errors": error_count,
        "payment_funnel": payment_funnel,
        "total_unique_installs": total_unique_installs,
        "tracking_activity": tracking,
        "outreach_activity": outreach,
    }


def send_daily_scan_summary(report_day: date | None = None) -> bool:
    if not _config():
        return False
    tz = _timezone()
    local_day = report_day or datetime.now(tz).date()
    message, payload = build_daily_scan_summary(local_day)
    return queue_admin_notification(
        f"daily_scan_summary:{local_day.isoformat()}", "daily_scan_summary", message, payload
    )


def _daily_hour() -> int:
    try:
        return max(0, min(23, int(os.getenv("NOYTRIX_ADMIN_TELEGRAM_DAILY_HOUR", "23"))))
    except Exception:
        return 23


def _daily_minute() -> int:
    try:
        return max(0, min(59, int(os.getenv("NOYTRIX_ADMIN_TELEGRAM_DAILY_MINUTE", "55"))))
    except Exception:
        return 55


async def daily_scan_summary_loop() -> None:
    """Send one idempotent admin report at the configured end-of-day hour."""
    await asyncio.sleep(10)
    if _config():
        await asyncio.to_thread(deliver_pending_notifications)
    while True:
        try:
            now = datetime.now(_timezone())
            target_day = now.date()
            target = datetime.combine(
                target_day,
                time(hour=_daily_hour(), minute=_daily_minute()),
                tzinfo=now.tzinfo,
            )
            if now >= target:
                await asyncio.to_thread(send_daily_scan_summary, target_day)
                next_run = target + timedelta(days=1)
            else:
                next_run = target
            await asyncio.sleep(max(30, (next_run - datetime.now(_timezone())).total_seconds()))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print("[admin_telegram] daily summary loop error:", str(exc)[:180])
            await asyncio.sleep(300)
