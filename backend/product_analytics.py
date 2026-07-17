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
PROFILE_DB_PATH = DATA_DIR / "profile.sqlite3"

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
    "paywall_value_viewed",
    "paywall_plan_selected",
    "paywall_cta_clicked",
    "paywall_restore_clicked",
    "paywall_restore_completed",
    "paywall_restore_failed",
    "paywall_nudge_viewed",
    "paywall_nudge_clicked",
    "paywall_nudge_dismissed",
    "trial_started",
    "purchase_started",
    "purchase_completed",
    "purchase_failed",
    "purchase_cancelled",
    "subscription_renewed",
    "subscription_cancelled",
    "subscription_expired",
    "app_feedback_submitted",
    "app_crashed",
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


def _parse_dt(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _identity_key(row: sqlite3.Row | dict) -> Optional[str]:
    return _string(row["user_id"] if row["user_id"] else row["anonymous_id"], 220)


def _safe_props(row: sqlite3.Row | dict) -> dict:
    try:
        value = json.loads(row["properties_json"] or "{}")
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _num(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        n = float(value)
        return n if n >= 0 else None
    except Exception:
        return None


def _money_from_props(props: dict) -> float:
    for key in ("ad_spend", "spend", "campaign_spend", "cost", "cost_usd", "spend_usd"):
        value = _num(props.get(key))
        if value is not None:
            return value
    return 0.0


def _percent(numerator: float, denominator: float) -> Optional[float]:
    if not denominator:
        return None
    return round((float(numerator) / float(denominator)) * 100, 2)


def _avg(values: list[float]) -> Optional[float]:
    valid = [x for x in values if isinstance(x, (int, float)) and x >= 0]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 2)


def _estimate_monthly_revenue(product_id: Any, raw_json: Any = None) -> Optional[float]:
    text = " ".join([str(product_id or ""), str(raw_json or "")]).lower()
    if any(x in text for x in ("lifetime", "prolifetime")):
        return 0.0
    if any(x in text for x in ("pro-1year", "annual", "year", "p1y", "p12m")):
        return round(199.99 / 12, 2)
    if any(x in text for x in ("pro6month", "6month", "six", "p6m")):
        return round(49.99 / 6, 2)
    if "pro_access" in text or "monthly" in text or "p1m" in text or "pro" in text:
        return 9.99
    return None


def _blank_metric(value: Any, unit: str | None = None, note: str | None = None) -> dict:
    return {"value": value, "unit": unit, "note": note}


def _period_bounds(days: int) -> tuple[str, datetime, int]:
    raw_days = int(30 if days is None else days)
    if raw_days <= 0:
        cutoff_dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return cutoff_dt.isoformat(), cutoff_dt, 0
    days_norm = max(1, min(raw_days, 365))
    cutoff_ts = datetime.now(timezone.utc).timestamp() - days_norm * 86400
    cutoff_dt = datetime.fromtimestamp(cutoff_ts, tz=timezone.utc).replace(microsecond=0)
    return cutoff_dt.isoformat(), cutoff_dt, days_norm
    return cutoff_dt.isoformat(), cutoff_dt


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


def company_dashboard(days: int = 30) -> dict:
    cutoff_iso, cutoff_dt, days_norm = _period_bounds(days)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    today = now.date()
    month_cutoff = now.timestamp() - 30 * 86400
    conn = _connect()
    try:
        if SUBSCRIPTIONS_DB_PATH.exists():
            conn.execute(f"ATTACH DATABASE '{SUBSCRIPTIONS_DB_PATH}' AS subdb")
        excluded = """
          COALESCE((SELECT is_test_user FROM subdb.user_flags uf WHERE uf.user_id=pe.user_id LIMIT 1), 0)=0
          AND COALESCE((SELECT is_internal_user FROM subdb.user_flags uf WHERE uf.user_id=pe.user_id LIMIT 1), 0)=0
        """ if SUBSCRIPTIONS_DB_PATH.exists() else "1=1"
        event_rows = conn.execute(
            f"""
            SELECT *
            FROM product_events pe
            WHERE event_time >= ? AND {excluded}
            ORDER BY event_time ASC
            """,
            (cutoff_iso,),
        ).fetchall()

        users_by_event: dict[str, set[str]] = {}
        counts_by_event: dict[str, int] = {}
        first_seen: dict[str, datetime] = {}
        first_scan: dict[str, datetime] = {}
        today_active: set[str] = set()
        month_active: set[str] = set()
        day_events: dict[str, dict[str, int]] = {}
        source_rows: dict[tuple[str, str], dict[str, Any]] = {}
        country_rows: dict[str, dict[str, Any]] = {}
        total_ad_spend = 0.0
        response_times: list[float] = []
        useful_results = 0
        historic_profile_events = 0

        for row in event_rows:
            event = row["event_name"]
            user = _identity_key(row)
            dt = _parse_dt(row["event_time"])
            props = _safe_props(row)
            counts_by_event[event] = counts_by_event.get(event, 0) + 1
            if user:
                users_by_event.setdefault(event, set()).add(user)
                if user not in first_seen or (dt and dt < first_seen[user]):
                    first_seen[user] = dt or cutoff_dt
                if event == "scan_completed" and (user not in first_scan or (dt and dt < first_scan[user])):
                    first_scan[user] = dt or cutoff_dt
                if dt and dt.date() == today:
                    today_active.add(user)
                if dt and dt.timestamp() >= month_cutoff:
                    month_active.add(user)

            day = (dt.date().isoformat() if dt else "unknown")
            bucket = day_events.setdefault(day, {"events": 0, "scans": 0, "users": 0})
            bucket["events"] += 1
            if event == "scan_completed":
                bucket["scans"] += 1

            if event == "scan_completed":
                rt = _num(props.get("response_time_ms") or props.get("duration_ms") or props.get("latency_ms"))
                if rt is not None:
                    response_times.append(rt)
                status_text = str(props.get("status") or props.get("result") or "").lower()
                if "error" not in status_text and "fail" not in status_text:
                    useful_results += 1

            total_ad_spend += _money_from_props(props)
            source = row["source"] or props.get("source") or "unknown"
            campaign = row["campaign"] or props.get("campaign") or ""
            source_key = (str(source or "unknown"), str(campaign or ""))
            source_item = source_rows.setdefault(
                source_key,
                {"source": source_key[0], "campaign": source_key[1], "installs": 0, "registrations": 0, "scans": 0, "paywalls": 0, "purchases": 0, "spend": 0.0},
            )
            source_item["spend"] += _money_from_props(props)
            if event == "app_first_open":
                source_item["installs"] += 1
            elif event == "signup_completed":
                source_item["registrations"] += 1
            elif event == "scan_completed":
                source_item["scans"] += 1
            elif event == "paywall_viewed":
                source_item["paywalls"] += 1
            elif event == "purchase_completed":
                source_item["purchases"] += 1

            country = row["country"] or props.get("country") or "unknown"
            country_item = country_rows.setdefault(str(country or "unknown"), {"country": str(country or "unknown"), "users": set(), "events": 0, "installs": 0, "scans": 0})
            if user:
                country_item["users"].add(user)
            country_item["events"] += 1
            if event == "app_first_open":
                country_item["installs"] += 1
            elif event == "scan_completed":
                country_item["scans"] += 1

        if PROFILE_DB_PATH.exists():
            try:
                conn.execute(f"ATTACH DATABASE '{PROFILE_DB_PATH}' AS profdb")
                profile_rows = conn.execute(
                    """
                    SELECT user_key, event_type, object_ref, meta_json, created_at
                    FROM profdb.profile_events
                    WHERE created_at >= ?
                      AND event_type IN ('scamshield_scan','immunity_analyze','app_feedback')
                    ORDER BY created_at ASC
                    """,
                    (cutoff_iso,),
                ).fetchall()
                historic_profile_events = len(profile_rows)
                for row in profile_rows:
                    raw_event = str(row["event_type"] or "")
                    event = "scan_completed" if raw_event in {"scamshield_scan", "immunity_analyze"} else "app_feedback_submitted"
                    user = _string(row["user_key"], 220)
                    dt = _parse_dt(row["created_at"])
                    props = {}
                    try:
                        parsed = json.loads(row["meta_json"] or "{}")
                        props = parsed if isinstance(parsed, dict) else {}
                    except Exception:
                        props = {}

                    counts_by_event[event] = counts_by_event.get(event, 0) + 1
                    if user:
                        users_by_event.setdefault(event, set()).add(user)
                        if user not in first_seen or (dt and dt < first_seen[user]):
                            first_seen[user] = dt or cutoff_dt
                        if event == "scan_completed" and (user not in first_scan or (dt and dt < first_scan[user])):
                            first_scan[user] = dt or cutoff_dt
                        if dt and dt.date() == today:
                            today_active.add(user)
                        if dt and dt.timestamp() >= month_cutoff:
                            month_active.add(user)

                    day = (dt.date().isoformat() if dt else "unknown")
                    bucket = day_events.setdefault(day, {"events": 0, "scans": 0, "users": 0})
                    bucket["events"] += 1
                    if event == "scan_completed":
                        bucket["scans"] += 1
                        verdict = str(props.get("verdict") or props.get("level") or "").lower()
                        if "error" not in verdict and "fail" not in verdict:
                            useful_results += 1
            except Exception as e:
                print("[product_analytics] historical profile dashboard error:", e)

        install_users = users_by_event.get("app_first_open", set())
        scan_users = users_by_event.get("scan_completed", set())
        signup_users = users_by_event.get("signup_completed", set())
        paywall_users = users_by_event.get("paywall_viewed", set())
        purchase_users = users_by_event.get("purchase_completed", set())

        first_scan_minutes = []
        for user, scan_dt in first_scan.items():
            start_dt = first_seen.get(user)
            if start_dt and scan_dt:
                first_scan_minutes.append(max(0.0, (scan_dt - start_dt).total_seconds() / 60.0))

        d1_returned = set()
        d7_returned = set()
        activity_days: dict[str, set[str]] = {}
        for row in event_rows:
            user = _identity_key(row)
            dt = _parse_dt(row["event_time"])
            if not user or not dt:
                continue
            activity_days.setdefault(user, set()).add(dt.date().isoformat())
        for user, start_dt in first_seen.items():
            days_seen = activity_days.get(user, set())
            if (start_dt.date().toordinal() + 1) in {datetime.fromisoformat(d).date().toordinal() for d in days_seen}:
                d1_returned.add(user)
            if (start_dt.date().toordinal() + 7) in {datetime.fromisoformat(d).date().toordinal() for d in days_seen}:
                d7_returned.add(user)

        active_paid = 0
        active_subscriptions = 0
        total_active_pro_access = 0
        legacy_active_pro_access = 0
        manual_active_pro_access = 0
        test_or_internal_active_pro_access = 0
        mrr_values: list[float] = []
        cancellations = 0
        refunds = 0
        payment_errors = counts_by_event.get("purchase_failed", 0)
        if SUBSCRIPTIONS_DB_PATH.exists():
            active_paid = conn.execute(
                """
                SELECT COUNT(DISTINCT e.user_id)
                FROM subdb.entitlements e
                JOIN subdb.subscriptions s ON s.id=e.subscription_id
                LEFT JOIN subdb.user_flags uf ON uf.user_id=e.user_id
                WHERE e.entitlement='pro' AND e.is_active=1
                  AND e.provider IN ('google_play','revenuecat')
                  AND s.status IN ('active','trial','trialing')
                  AND s.environment='production'
                  AND COALESCE(e.source,'') NOT LIKE 'legacy_guest_pro:%'
                  AND COALESCE(s.source,'') NOT LIKE 'legacy_guest_pro:%'
                  AND COALESCE(uf.is_test_user,0)=0
                  AND COALESCE(uf.is_internal_user,0)=0
                """
            ).fetchone()[0]
            total_active_pro_access = conn.execute(
                """
                SELECT COUNT(DISTINCT e.user_id)
                FROM subdb.entitlements e
                LEFT JOIN subdb.user_flags uf ON uf.user_id=e.user_id
                WHERE e.entitlement='pro' AND e.is_active=1
                  AND COALESCE(uf.is_test_user,0)=0
                  AND COALESCE(uf.is_internal_user,0)=0
                """
            ).fetchone()[0]
            legacy_active_pro_access = conn.execute(
                """
                SELECT COUNT(DISTINCT e.user_id)
                FROM subdb.entitlements e
                LEFT JOIN subdb.user_flags uf ON uf.user_id=e.user_id
                WHERE e.entitlement='pro' AND e.is_active=1
                  AND COALESCE(e.source,'') LIKE 'legacy_guest_pro:%'
                  AND COALESCE(uf.is_test_user,0)=0
                  AND COALESCE(uf.is_internal_user,0)=0
                """
            ).fetchone()[0]
            manual_active_pro_access = conn.execute(
                """
                SELECT COUNT(DISTINCT e.user_id)
                FROM subdb.entitlements e
                LEFT JOIN subdb.user_flags uf ON uf.user_id=e.user_id
                WHERE e.entitlement='pro' AND e.is_active=1
                  AND e.provider='manual'
                  AND COALESCE(uf.is_test_user,0)=0
                  AND COALESCE(uf.is_internal_user,0)=0
                """
            ).fetchone()[0]
            test_or_internal_active_pro_access = conn.execute(
                """
                SELECT COUNT(DISTINCT e.user_id)
                FROM subdb.entitlements e
                LEFT JOIN subdb.user_flags uf ON uf.user_id=e.user_id
                WHERE e.entitlement='pro' AND e.is_active=1
                  AND (COALESCE(uf.is_test_user,0)=1 OR COALESCE(uf.is_internal_user,0)=1)
                """
            ).fetchone()[0]
            sub_rows = conn.execute(
                """
                SELECT s.*
                FROM subdb.subscriptions s
                LEFT JOIN subdb.user_flags uf ON uf.user_id=s.user_id
                WHERE COALESCE(uf.is_test_user,0)=0
                  AND COALESCE(uf.is_internal_user,0)=0
                """
            ).fetchall()
            for sub in sub_rows:
                status = str(sub["status"] or "").lower()
                source = str(sub["source"] or "")
                provider = str(sub["provider"] or "")
                is_live_paid = provider in {"google_play", "revenuecat"} and not source.startswith("legacy_guest_pro:")
                if status in {"active", "trial", "trialing"}:
                    active_subscriptions += 1
                    if is_live_paid:
                        value = _estimate_monthly_revenue(sub["product_id"], sub["raw_json"])
                        if value is not None:
                            mrr_values.append(value)
                if status in {"canceled", "cancelled"}:
                    cancellations += 1
            event_sub_rows = conn.execute(
                """
                SELECT event_type
                FROM subdb.purchase_events
                WHERE created_at >= ?
                """,
                (cutoff_iso,),
            ).fetchall()
            for row in event_sub_rows:
                event_type = str(row["event_type"] or "").lower()
                if "refund" in event_type:
                    refunds += 1
                if "cancel" in event_type:
                    cancellations += 1

        installs = counts_by_event.get("app_first_open", 0)
        registrations = counts_by_event.get("signup_completed", 0)
        scan_completed = counts_by_event.get("scan_completed", 0)
        scan_failed = counts_by_event.get("scan_failed", 0)
        scan_started = counts_by_event.get("scan_started", 0)
        scan_total = scan_completed + scan_failed

        sources = []
        for item in source_rows.values():
            spend = round(item["spend"], 2)
            sources.append({
                **item,
                "spend": spend if spend else None,
                "cpi": round(spend / item["installs"], 2) if spend and item["installs"] else None,
                "cpr": round(spend / item["registrations"], 2) if spend and item["registrations"] else None,
            })
        sources.sort(key=lambda x: (x["purchases"], x["scans"], x["installs"]), reverse=True)

        countries = []
        for item in country_rows.values():
            countries.append({**item, "users": len(item["users"])})
        countries.sort(key=lambda x: (x["users"], x["scans"], x["installs"]), reverse=True)

        daily = []
        for day, item in sorted(day_events.items())[-30:]:
            daily.append({"day": day, **item})

        return {
            "ok": True,
            "generatedAt": now.isoformat(),
            "windowDays": days_norm,
            "windowLabel": "all_time" if days_norm == 0 else f"{days_norm}_days",
            "dataFreshness": {
                "lastEventAt": event_rows[-1]["event_time"] if event_rows else None,
                "eventRows": len(event_rows),
                "historicProfileEvents": historic_profile_events,
                "subscriptionsDb": SUBSCRIPTIONS_DB_PATH.exists(),
                "profileDb": PROFILE_DB_PATH.exists(),
            },
            "acquisition": {
                "installs": _blank_metric(installs),
                "costPerInstall": _blank_metric(round(total_ad_spend / installs, 2) if total_ad_spend and installs else None, "долл."),
                "registrations": _blank_metric(registrations),
                "costPerRegistration": _blank_metric(round(total_ad_spend / registrations, 2) if total_ad_spend and registrations else None, "долл."),
                "sources": sources[:20],
                "countries": countries[:20],
            },
            "activation": {
                "firstAnalysisUsers": _blank_metric(len(scan_users)),
                "installToAnalysisConversion": _blank_metric(_percent(len(scan_users & install_users) or len(scan_users), len(install_users)), "%"),
                "averageMinutesToFirstAnalysis": _blank_metric(_avg(first_scan_minutes), "min"),
                "usefulResultsWithoutError": _blank_metric(useful_results),
                "usefulResultRate": _blank_metric(_percent(useful_results, scan_total or scan_completed), "%"),
            },
            "retention": {
                "returnedNextDay": _blank_metric(len(d1_returned)),
                "returnedDay7": _blank_metric(len(d7_returned)),
                "analysesPerActiveUser": _blank_metric(round(scan_completed / len(month_active), 2) if month_active else None),
                "dailyActiveUsers": _blank_metric(len(today_active)),
                "monthlyActiveUsers": _blank_metric(len(month_active)),
            },
            "revenue": {
                "paywallViewedUsers": _blank_metric(len(paywall_users)),
                "purchaseStartedUsers": _blank_metric(len(users_by_event.get("purchase_started", set()))),
                "purchaseCompletedUsers": _blank_metric(len(purchase_users)),
                "activePaidSubscriptions": _blank_metric(active_paid, None, "только реальные активные оплаты Google Play / RevenueCat, без legacy и ручных выдач"),
                "totalActiveProAccess": _blank_metric(total_active_pro_access, None, "все, у кого сейчас включен PRO-доступ, включая старые и ручные выдачи"),
                "legacyActiveProAccess": _blank_metric(legacy_active_pro_access, None, "старые перенесенные доступы; это не равно реальным платным клиентам"),
                "manualActiveProAccess": _blank_metric(manual_active_pro_access, None, "доступ, выданный вручную или как восстановление"),
                "testActiveProAccess": _blank_metric(test_or_internal_active_pro_access, None, "тестовые и внутренние аккаунты"),
                "monthlyRecurringRevenue": _blank_metric(round(sum(mrr_values), 2) if mrr_values else 0, "долл.", "считается только по реальным активным оплатам, legacy не учитывается"),
                "cancellations": _blank_metric(cancellations),
                "refunds": _blank_metric(refunds),
                "activeSubscriptionRows": _blank_metric(active_subscriptions),
            },
            "quality": {
                "analysisErrorRate": _blank_metric(_percent(scan_failed, scan_total), "%"),
                "averageResponseTimeMs": _blank_metric(_avg(response_times), "ms"),
                "appCrashes": _blank_metric(counts_by_event.get("app_crashed", 0), None, "появится, когда приложение начнет отправлять события падений"),
                "paymentErrors": _blank_metric(payment_errors),
                "apiAvailability": _blank_metric(round(100 - (_percent(scan_failed, scan_total) or 0), 2) if scan_total else None, "%", "оценка по ошибкам анализов"),
            },
            "events": {name: {"events": counts_by_event.get(name, 0), "users": len(users_by_event.get(name, set()))} for name in sorted(ALLOWED_EVENTS)},
            "daily": daily,
        }
    finally:
        conn.close()
