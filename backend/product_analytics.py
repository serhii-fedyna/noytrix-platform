import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from identity import resolve_user_id


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ANALYTICS_DB_PATH = DATA_DIR / "product_analytics.sqlite3"
SUBSCRIPTIONS_DB_PATH = DATA_DIR / "subscriptions.sqlite3"

ALLOWED_EVENTS = {
    "app_first_open",
    "session_started",
    "signup_started",
    "signup_completed",
    "scan_started",
    "scan_completed",
    "scan_failed",
    "scan_result_viewed",
    "risk_explanation_viewed",
    "paywall_viewed",
    "trial_started",
    "purchase_started",
    "purchase_completed",
    "purchase_failed",
    "purchase_cancelled",
    "subscription_renewed",
    "subscription_cancelled",
    "subscription_expired",
    "app_feedback_submitted",
}

SENSITIVE_KEY_PARTS = {
    "private",
    "seed",
    "mnemonic",
    "password",
    "passphrase",
    "secret",
    "token",
    "authorization",
    "auth",
    "key",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(ANALYTICS_DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_iso(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return _now_iso()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return _now_iso()


def init_product_analytics_db() -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS product_events (
              event_id TEXT PRIMARY KEY,
              user_id TEXT,
              anonymous_id TEXT,
              session_id TEXT,
              platform TEXT,
              app_version TEXT,
              event_name TEXT NOT NULL,
              event_time TEXT NOT NULL,
              country TEXT,
              source TEXT,
              campaign TEXT,
              ad_group TEXT,
              install_date TEXT,
              properties_json TEXT,
              created_at TEXT NOT NULL
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_attribution (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id TEXT,
              anonymous_id TEXT,
              platform TEXT,
              first_source TEXT,
              first_campaign TEXT,
              first_ad_group TEXT,
              first_country TEXT,
              install_date TEXT,
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              UNIQUE(user_id, anonymous_id, platform)
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_product_events_name_time ON product_events(event_name, event_time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_product_events_user_time ON product_events(user_id, event_time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_product_events_anon_time ON product_events(anonymous_id, event_time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_product_events_campaign_time ON product_events(source, campaign, ad_group, event_time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_product_events_install_date ON product_events(install_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_attribution_campaign ON user_attribution(first_source, first_campaign, first_ad_group)")
        conn.commit()
    finally:
        conn.close()


init_product_analytics_db()


def canonical_event_name(name: Any) -> str:
    raw = str(name or "").strip().lower()
    aliases = {
        "app_open_noytrix": "app_first_open",
        "screen_open": "session_started",
        "pro_screen_open": "paywall_viewed",
        "pro_opened": "paywall_viewed",
        "home_open_pro": "paywall_viewed",
        "scan_submitted": "scan_started",
        "scan_result": "scan_completed",
        "registration_success": "signup_completed",
        "register_success": "signup_completed",
        "purchase_start": "purchase_started",
        "google_play_purchase_start": "purchase_started",
        "purchase_success": "purchase_completed",
        "google_play_purchase_verified": "purchase_completed",
        "purchase_error": "purchase_failed",
        "google_play_restore_error": "purchase_failed",
        "review_prompt_feedback_sent": "app_feedback_submitted",
    }
    return aliases.get(raw, raw)


def _is_sensitive_key(key: str) -> bool:
    low = str(key or "").strip().lower()
    return any(part in low for part in SENSITIVE_KEY_PARTS)


def sanitize_properties(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return str(value)[:500]
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            k = str(key or "").strip()
            if not k or _is_sensitive_key(k):
                continue
            out[k[:80]] = sanitize_properties(item, depth + 1)
        return out
    if isinstance(value, list):
        return [sanitize_properties(x, depth + 1) for x in value[:50]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:1000]


def _json(value: Any) -> str:
    try:
        return json.dumps(sanitize_properties(value or {}), ensure_ascii=False)
    except Exception:
        return "{}"


def _string(value: Any, limit: int = 160) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    return raw[:limit]


def _resolve_user_id(user_id: Any, anonymous_id: Any, properties: dict) -> Optional[str]:
    links: list[tuple[str, Any]] = []
    if user_id:
        links.append(("internal" if str(user_id).startswith("usr_") else "guest", user_id))
    if anonymous_id:
        links.append(("guest", anonymous_id))
        links.append(("revenuecat", anonymous_id))
    email = properties.get("email") if isinstance(properties, dict) else None
    if email:
        links.append(("email", email))
    if not links:
        return None
    return resolve_user_id(links, meta={"source": "product_analytics"})


def record_product_event(payload: dict) -> dict:
    data = dict(payload or {})
    event_name = canonical_event_name(data.get("event_name") or data.get("name"))
    if event_name not in ALLOWED_EVENTS:
        raise ValueError("unsupported_event_name")

    properties = data.get("properties") if isinstance(data.get("properties"), dict) else {}
    anonymous_id = _string(data.get("anonymous_id") or data.get("anonymousId") or properties.get("anonymous_id"))
    user_id_raw = _string(data.get("user_id") or data.get("userId") or properties.get("user_id"))
    user_id = _resolve_user_id(user_id_raw, anonymous_id, properties) or user_id_raw
    event_id = _string(data.get("event_id") or data.get("eventId"), 120) or f"evt_{uuid.uuid4().hex}"
    event_time = _parse_iso(data.get("event_time") or data.get("eventTime"))

    row = {
        "event_id": event_id,
        "user_id": user_id,
        "anonymous_id": anonymous_id,
        "session_id": _string(data.get("session_id") or data.get("sessionId") or properties.get("session_id")),
        "platform": _string(data.get("platform") or properties.get("platform"), 40),
        "app_version": _string(data.get("app_version") or data.get("appVersion") or properties.get("app_version"), 80),
        "event_name": event_name,
        "event_time": event_time,
        "country": _string(data.get("country") or properties.get("country"), 80),
        "source": _string(data.get("source") or properties.get("source") or properties.get("utm_source"), 160),
        "campaign": _string(data.get("campaign") or properties.get("campaign") or properties.get("utm_campaign"), 160),
        "ad_group": _string(data.get("ad_group") or data.get("adGroup") or properties.get("ad_group") or properties.get("utm_adgroup"), 160),
        "install_date": _string(data.get("install_date") or data.get("installDate") or properties.get("install_date"), 40),
        "properties_json": _json(properties),
        "created_at": _now_iso(),
    }

    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO product_events(
              event_id, user_id, anonymous_id, session_id, platform, app_version,
              event_name, event_time, country, source, campaign, ad_group,
              install_date, properties_json, created_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            tuple(row[k] for k in (
                "event_id", "user_id", "anonymous_id", "session_id", "platform", "app_version",
                "event_name", "event_time", "country", "source", "campaign", "ad_group",
                "install_date", "properties_json", "created_at",
            )),
        )
        inserted = cur.rowcount > 0
        if inserted and (row["source"] or row["campaign"] or row["ad_group"] or row["install_date"]):
            cur.execute(
                """
                INSERT INTO user_attribution(
                  user_id, anonymous_id, platform, first_source, first_campaign,
                  first_ad_group, first_country, install_date, first_seen_at, last_seen_at
                )
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id, anonymous_id, platform) DO UPDATE SET
                  last_seen_at=excluded.last_seen_at
                """,
                (
                    row["user_id"],
                    row["anonymous_id"],
                    row["platform"],
                    row["source"],
                    row["campaign"],
                    row["ad_group"],
                    row["country"],
                    row["install_date"],
                    row["event_time"],
                    row["event_time"],
                ),
            )
        conn.commit()
        return {"ok": True, "inserted": inserted, "eventId": event_id, "eventName": event_name, "userId": user_id}
    finally:
        conn.close()


def record_product_event_safe(payload: dict) -> None:
    try:
        record_product_event(payload)
    except Exception as e:
        print("[product_analytics] event error:", e)


def analytics_funnel(days: int = 30) -> dict:
    cutoff = datetime.now(timezone.utc).timestamp() - max(1, min(int(days or 30), 365)) * 86400
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).replace(microsecond=0).isoformat()
    conn = _connect()
    try:
        if SUBSCRIPTIONS_DB_PATH.exists():
            conn.execute(f"ATTACH DATABASE '{SUBSCRIPTIONS_DB_PATH}' AS subdb")
        excluded = """
          COALESCE((SELECT is_test_user FROM subdb.user_flags uf WHERE uf.user_id=pe.user_id LIMIT 1), 0)=0
          AND COALESCE((SELECT is_internal_user FROM subdb.user_flags uf WHERE uf.user_id=pe.user_id LIMIT 1), 0)=0
        """ if SUBSCRIPTIONS_DB_PATH.exists() else "1=1"
        rows = conn.execute(
            f"""
            SELECT event_name, COUNT(1) events, COUNT(DISTINCT COALESCE(user_id, anonymous_id)) users
            FROM product_events pe
            WHERE event_time >= ? AND {excluded}
            GROUP BY event_name
            ORDER BY event_name
            """,
            (cutoff_iso,),
        ).fetchall()
        campaign_rows = conn.execute(
            f"""
            SELECT
              COALESCE(source, '') source,
              COALESCE(campaign, '') campaign,
              COALESCE(ad_group, '') ad_group,
              COUNT(DISTINCT CASE WHEN event_name='app_first_open' THEN COALESCE(user_id, anonymous_id) END) installs,
              COUNT(DISTINCT CASE WHEN event_name='scan_completed' THEN COALESCE(user_id, anonymous_id) END) first_or_repeat_scanners,
              COUNT(DISTINCT CASE WHEN event_name='paywall_viewed' THEN COALESCE(user_id, anonymous_id) END) paywall_users,
              COUNT(DISTINCT CASE WHEN event_name IN ('trial_started','purchase_completed') THEN COALESCE(user_id, anonymous_id) END) trial_or_purchase_users
            FROM product_events pe
            WHERE event_time >= ? AND {excluded}
            GROUP BY source, campaign, ad_group
            ORDER BY trial_or_purchase_users DESC, first_or_repeat_scanners DESC, installs DESC
            LIMIT 50
            """,
            (cutoff_iso,),
        ).fetchall()
        return {
            "ok": True,
            "days": days,
            "events": [dict(row) for row in rows],
            "campaigns": [dict(row) for row in campaign_rows],
            "primaryMetricNow": "scan_completed",
            "primaryMetricLater": "trial_started_or_purchase_completed",
        }
    finally:
        conn.close()
