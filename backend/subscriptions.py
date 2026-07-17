import json
import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from identity import find_user_ids, resolve_user_id


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SUBSCRIPTIONS_DB_PATH = DATA_DIR / "subscriptions.sqlite3"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value or {}, ensure_ascii=False)
    except Exception:
        return "{}"


def _parse_iso(value: Any) -> Optional[datetime]:
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


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SUBSCRIPTIONS_DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_provider(provider: Any) -> str:
    p = str(provider or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "google": "google_play",
        "googleplay": "google_play",
        "play": "google_play",
        "revenue_cat": "revenuecat",
        "rc": "revenuecat",
    }
    return aliases.get(p, p or "manual")


def normalize_environment(environment: Any) -> str:
    env = str(environment or "").strip().lower()
    if env in {"sandbox", "test"}:
        return env
    return "production"


def init_subscriptions_db() -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id TEXT NOT NULL,
              provider TEXT NOT NULL,
              product_id TEXT,
              status TEXT NOT NULL,
              started_at TEXT,
              expires_at TEXT,
              auto_renew INTEGER NOT NULL DEFAULT 0,
              environment TEXT NOT NULL DEFAULT 'production',
              original_transaction_id TEXT,
              purchase_token TEXT,
              source TEXT,
              raw_json TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS entitlements (
              user_id TEXT NOT NULL,
              entitlement TEXT NOT NULL,
              is_active INTEGER NOT NULL DEFAULT 0,
              expires_at TEXT,
              source TEXT,
              provider TEXT,
              subscription_id INTEGER,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(user_id, entitlement)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS purchase_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id TEXT NOT NULL,
              provider TEXT NOT NULL,
              external_event_id TEXT,
              event_type TEXT NOT NULL,
              product_id TEXT,
              status TEXT,
              purchase_token TEXT,
              transaction_id TEXT,
              original_transaction_id TEXT,
              environment TEXT NOT NULL DEFAULT 'production',
              raw_json TEXT,
              created_at TEXT NOT NULL
            );
            """
        )
        columns = {
            row["name"]
            for row in cur.execute("PRAGMA table_info(purchase_events)").fetchall()
        }
        if "external_event_id" not in columns:
            cur.execute("ALTER TABLE purchase_events ADD COLUMN external_event_id TEXT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_provider_token ON subscriptions(provider, purchase_token)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_original ON subscriptions(provider, original_transaction_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_entitlements_active ON entitlements(entitlement, is_active)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_purchase_events_user ON purchase_events(user_id, created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_purchase_events_token ON purchase_events(provider, purchase_token)")
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_purchase_events_external
            ON purchase_events(provider, external_event_id)
            WHERE external_event_id IS NOT NULL
            """
        )
        conn.commit()
    finally:
        conn.close()


init_subscriptions_db()


def upsert_subscription(
    *,
    user_id: str,
    provider: str,
    product_id: str | None,
    status: str,
    started_at: str | None = None,
    expires_at: str | None = None,
    auto_renew: bool = False,
    environment: str = "production",
    original_transaction_id: str | None = None,
    purchase_token: str | None = None,
    source: str | None = None,
    raw: Any = None,
) -> int:
    uid = str(user_id or "").strip()
    if not uid:
        raise ValueError("user_id_required")

    provider_norm = normalize_provider(provider)
    env_norm = normalize_environment(environment)
    now = _now_iso()
    started = started_at or now
    token = str(purchase_token or "").strip() or None
    original = str(original_transaction_id or "").strip() or token

    conn = _connect()
    try:
        cur = conn.cursor()
        row = None
        if token:
            row = cur.execute(
                "SELECT id FROM subscriptions WHERE provider=? AND purchase_token=? LIMIT 1",
                (provider_norm, token),
            ).fetchone()
        if row is None and original:
            row = cur.execute(
                "SELECT id FROM subscriptions WHERE provider=? AND original_transaction_id=? LIMIT 1",
                (provider_norm, original),
            ).fetchone()

        if row:
            sub_id = int(row["id"])
            cur.execute(
                """
                UPDATE subscriptions
                SET user_id=?, product_id=?, status=?, started_at=COALESCE(started_at, ?),
                    expires_at=?, auto_renew=?, environment=?, original_transaction_id=?,
                    purchase_token=COALESCE(?, purchase_token), source=?, raw_json=?, updated_at=?
                WHERE id=?
                """,
                (
                    uid,
                    product_id,
                    status,
                    started,
                    expires_at,
                    1 if auto_renew else 0,
                    env_norm,
                    original,
                    token,
                    source,
                    _safe_json(raw),
                    now,
                    sub_id,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO subscriptions(
                  user_id, provider, product_id, status, started_at, expires_at,
                  auto_renew, environment, original_transaction_id, purchase_token,
                  source, raw_json, created_at, updated_at
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    uid,
                    provider_norm,
                    product_id,
                    status,
                    started,
                    expires_at,
                    1 if auto_renew else 0,
                    env_norm,
                    original,
                    token,
                    source,
                    _safe_json(raw),
                    now,
                    now,
                ),
            )
            sub_id = int(cur.lastrowid)
        conn.commit()
        return sub_id
    finally:
        conn.close()


def record_purchase_event(
    *,
    user_id: str,
    provider: str,
    event_type: str,
    external_event_id: str | None = None,
    product_id: str | None = None,
    status: str | None = None,
    purchase_token: str | None = None,
    transaction_id: str | None = None,
    original_transaction_id: str | None = None,
    environment: str = "production",
    raw: Any = None,
) -> int:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO purchase_events(
              user_id, provider, external_event_id, event_type, product_id, status, purchase_token,
              transaction_id, original_transaction_id, environment, raw_json, created_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(user_id or "").strip(),
                normalize_provider(provider),
                str(external_event_id or "").strip() or None,
                str(event_type or "unknown"),
                product_id,
                status,
                purchase_token,
                transaction_id,
                original_transaction_id,
                normalize_environment(environment),
                _safe_json(raw),
                _now_iso(),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def purchase_event_exists(provider: str, external_event_id: str | None) -> Optional[int]:
    event_id = str(external_event_id or "").strip()
    if not event_id:
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id FROM purchase_events WHERE provider=? AND external_event_id=? LIMIT 1",
            (normalize_provider(provider), event_id),
        ).fetchone()
        return int(row["id"]) if row else None
    finally:
        conn.close()


def set_entitlement(
    *,
    user_id: str,
    entitlement: str = "pro",
    is_active: bool,
    expires_at: str | None = None,
    source: str | None = None,
    provider: str | None = None,
    subscription_id: int | None = None,
) -> None:
    uid = str(user_id or "").strip()
    ent = str(entitlement or "pro").strip().lower()
    if not uid or not ent:
        return
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO entitlements(user_id, entitlement, is_active, expires_at, source, provider, subscription_id, updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id, entitlement) DO UPDATE SET
              is_active=excluded.is_active,
              expires_at=excluded.expires_at,
              source=excluded.source,
              provider=excluded.provider,
              subscription_id=excluded.subscription_id,
              updated_at=excluded.updated_at
            """,
            (
                uid,
                ent,
                1 if is_active else 0,
                expires_at,
                source,
                normalize_provider(provider) if provider else None,
                subscription_id,
                _now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _candidate_user_ids(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    links = []
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        for candidate in (raw, raw.lower()):
            if candidate and candidate not in seen:
                out.append(candidate)
                seen.add(candidate)
        if raw.startswith("usr_"):
            links.append(("internal", raw))
        elif "@" in raw:
            links.append(("email", raw))
        else:
            links.append(("guest", raw))
            links.append(("auth_user_id", raw))
            links.append(("revenuecat", raw))
            links.append(("revenuecat_transaction", raw))
    for uid in find_user_ids(links):
        if uid and uid not in seen:
            out.append(uid)
            seen.add(uid)
    return out


def entitlement_status(values: Iterable[Any], entitlement: str = "pro") -> dict:
    ent = str(entitlement or "pro").strip().lower()
    candidates = _candidate_user_ids(values)
    if not candidates:
        return {"active": False, "entitlement": ent, "expiresAt": None, "source": None, "provider": None, "userId": None}

    now = datetime.now(timezone.utc)
    qmarks = ",".join(["?"] * len(candidates))
    conn = _connect()
    try:
        rows = conn.execute(
            f"""
            SELECT user_id, entitlement, is_active, expires_at, source, provider, subscription_id, updated_at
            FROM entitlements
            WHERE entitlement=? AND user_id IN ({qmarks})
            ORDER BY is_active DESC, updated_at DESC
            """,
            tuple([ent] + candidates),
        ).fetchall()
        for row in rows:
            active = int(row["is_active"] or 0) == 1
            expiry = _parse_iso(row["expires_at"])
            if active and expiry and expiry <= now:
                conn.execute(
                    "UPDATE entitlements SET is_active=0, source=?, updated_at=? WHERE user_id=? AND entitlement=?",
                    ("expired", _now_iso(), row["user_id"], ent),
                )
                conn.commit()
                active = False
            if active:
                return {
                    "active": True,
                    "entitlement": ent,
                    "expiresAt": row["expires_at"],
                    "source": row["source"],
                    "provider": row["provider"],
                    "userId": row["user_id"],
                    "subscriptionId": row["subscription_id"],
                }
        return {"active": False, "entitlement": ent, "expiresAt": None, "source": None, "provider": None, "userId": None}
    finally:
        conn.close()


def has_active_entitlement(values: Iterable[Any], entitlement: str = "pro") -> bool:
    return bool(entitlement_status(values, entitlement).get("active"))


def provider_from_source(source: str | None) -> str:
    s = str(source or "").strip().lower()
    if "google" in s or "play" in s:
        return "google_play"
    if "revenuecat" in s:
        return "revenuecat"
    if "stripe" in s:
        return "stripe"
    if "telegram" in s:
        return "telegram"
    if "promo" in s:
        return "promotional"
    return "manual"


def _active_subscription_for_user(user_id: str) -> Optional[sqlite3.Row]:
    uid = str(user_id or "").strip()
    if not uid:
        return None
    now = datetime.now(timezone.utc)
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, provider, product_id, expires_at, source
            FROM subscriptions
            WHERE user_id=? AND lower(status) IN ('active', 'purchased', 'verified')
            ORDER BY updated_at DESC
            """,
            (uid,),
        ).fetchall()
        for row in rows:
            expiry = _parse_iso(row["expires_at"])
            if expiry and expiry <= now:
                continue
            return row
        return None
    finally:
        conn.close()


def grant_entitlement(
    user_id: str,
    *,
    entitlement: str = "pro",
    source: str = "manual",
    expires_at: str | None = None,
    provider: str | None = None,
    environment: str = "production",
    raw: Any = None,
) -> None:
    provider_norm = normalize_provider(provider or provider_from_source(source))
    sub_id = upsert_subscription(
        user_id=user_id,
        provider=provider_norm,
        product_id=entitlement,
        status="active",
        started_at=None,
        expires_at=expires_at,
        auto_renew=False,
        environment=environment,
        original_transaction_id=f"{provider_norm}:{user_id}:{entitlement}",
        purchase_token=None,
        source=source,
        raw=raw,
    )
    set_entitlement(
        user_id=user_id,
        entitlement=entitlement,
        is_active=True,
        expires_at=expires_at,
        source=source,
        provider=provider_norm,
        subscription_id=sub_id,
    )
    record_purchase_event(
        user_id=user_id,
        provider=provider_norm,
        event_type="entitlement_granted",
        product_id=entitlement,
        status="active",
        original_transaction_id=f"{provider_norm}:{user_id}:{entitlement}",
        environment=environment,
        raw=raw,
    )


def revoke_entitlement(
    user_id: str,
    *,
    entitlement: str = "pro",
    source: str = "revoked",
    provider: str | None = None,
    raw: Any = None,
) -> None:
    provider_norm = normalize_provider(provider or provider_from_source(source))
    set_entitlement(
        user_id=user_id,
        entitlement=entitlement,
        is_active=False,
        expires_at=None,
        source=source,
        provider=provider_norm,
    )
    record_purchase_event(
        user_id=user_id,
        provider=provider_norm,
        event_type="entitlement_revoked",
        product_id=entitlement,
        status="inactive",
        environment="production",
        raw=raw,
    )


def sync_google_play_purchase(
    *,
    user_id: str,
    product_type: str,
    product_id: str,
    purchase_token: str,
    data: dict,
    active: bool,
    status: str,
    expires_at: str | None,
    environment: str = "production",
) -> int:
    provider = "google_play"
    order_id = str(data.get("orderId") or "").strip() or None
    original = str(data.get("linkedPurchaseToken") or order_id or purchase_token or "").strip() or None
    purchase_time = data.get("purchaseTimeMillis")
    started_at = None
    if purchase_time:
        try:
            started_at = datetime.fromtimestamp(int(purchase_time) / 1000, tz=timezone.utc).replace(microsecond=0).isoformat()
        except Exception:
            started_at = None

    sub_id = upsert_subscription(
        user_id=user_id,
        provider=provider,
        product_id=product_id,
        status=status,
        started_at=started_at,
        expires_at=expires_at,
        auto_renew=(str(product_type or "").lower() == "subs" and active),
        environment=environment,
        original_transaction_id=original,
        purchase_token=purchase_token,
        source="google_play_verified",
        raw=data,
    )
    fallback_active = None if active else _active_subscription_for_user(user_id)
    entitlement_active = bool(active or fallback_active)
    set_entitlement(
        user_id=user_id,
        entitlement="pro",
        is_active=entitlement_active,
        expires_at=expires_at if active else (fallback_active["expires_at"] if fallback_active else None),
        source="google_play_verified" if active else (fallback_active["source"] if fallback_active else f"google_play_{status}"),
        provider=provider if active else (fallback_active["provider"] if fallback_active else provider),
        subscription_id=sub_id if active else (int(fallback_active["id"]) if fallback_active else sub_id),
    )
    record_purchase_event(
        user_id=user_id,
        provider=provider,
        event_type="purchase_verified" if active else f"purchase_{status or 'inactive'}",
        product_id=product_id,
        status=status,
        purchase_token=purchase_token,
        transaction_id=order_id,
        original_transaction_id=original,
        environment=environment,
        raw=data,
    )
    return sub_id


def _ms_to_iso(value: Any) -> str | None:
    try:
        raw = int(value)
    except Exception:
        return None
    if raw <= 0:
        return None
    return datetime.fromtimestamp(raw / 1000, tz=timezone.utc).replace(microsecond=0).isoformat()


def _subscriber_attribute_value(attrs: dict, *names: str) -> str | None:
    if not isinstance(attrs, dict):
        return None
    for name in names:
        item = attrs.get(name)
        if isinstance(item, dict):
            value = item.get("value")
        else:
            value = item
        if value:
            return str(value).strip()
    return None


def _revenuecat_status(event_type: str, period_type: str | None, expires_at: str | None) -> tuple[str, bool, bool]:
    kind = str(event_type or "").strip().upper()
    period = str(period_type or "").strip().upper()
    now = datetime.now(timezone.utc)
    expiry = _parse_iso(expires_at)
    not_expired = not expiry or expiry > now

    if kind in {"INITIAL_PURCHASE", "RENEWAL", "NON_RENEWING_PURCHASE", "PRODUCT_CHANGE", "UNCANCELLATION", "TEMPORARY_ENTITLEMENT_GRANT", "PURCHASE_REDEEMED", "SUBSCRIPTION_EXTENDED"}:
        return ("trial" if period == "TRIAL" else "active", True, kind != "NON_RENEWING_PURCHASE")
    if kind == "CANCELLATION":
        return "cancelled", bool(not_expired), False
    if kind in {"BILLING_ISSUE", "SUBSCRIPTION_PAUSED"}:
        return kind.lower(), bool(not_expired), False
    if kind in {"EXPIRATION", "REFUND", "PRODUCT_NOT_PROVIDED"}:
        return kind.lower(), False, False
    if kind == "TRANSFER":
        return "transferred", False, False
    return kind.lower() or "unknown", bool(not_expired), False


def process_revenuecat_webhook(payload: dict) -> dict:
    body = dict(payload or {})
    event = body.get("event") if isinstance(body.get("event"), dict) else body
    if not isinstance(event, dict):
        raise ValueError("missing_revenuecat_event")

    event_type = str(event.get("type") or "UNKNOWN").strip().upper()
    event_id = str(event.get("id") or "").strip()
    if not event_id:
        base = "|".join(
            str(event.get(k) or "")
            for k in ("type", "app_user_id", "transaction_id", "original_transaction_id", "event_timestamp_ms")
        )
        event_id = "rc:" + hashlib.sha256(base.encode("utf-8", errors="ignore")).hexdigest()

    existing = purchase_event_exists("revenuecat", event_id)
    if existing:
        return {"ok": True, "duplicate": True, "purchaseEventId": existing, "eventId": event_id, "eventType": event_type}

    aliases = event.get("aliases") if isinstance(event.get("aliases"), list) else []
    attrs = event.get("subscriber_attributes") if isinstance(event.get("subscriber_attributes"), dict) else {}
    email = _subscriber_attribute_value(attrs, "$email", "email", "Email")

    app_user_id = str(event.get("app_user_id") or "").strip()
    original_app_user_id = str(event.get("original_app_user_id") or "").strip()
    links: list[tuple[str, Any]] = []
    for value in [app_user_id, original_app_user_id, *aliases]:
        if value:
            links.append(("revenuecat", value))
    if email:
        links.append(("email", email))
    if event.get("original_transaction_id"):
        links.append(("revenuecat_transaction", event.get("original_transaction_id")))
    if event.get("transaction_id"):
        links.append(("revenuecat_transaction", event.get("transaction_id")))
    if event_type == "TRANSFER":
        for value in event.get("transferred_to") or []:
            if value:
                links.append(("revenuecat", value))
    if not links:
        links.append(("revenuecat", event_id))

    user_id = resolve_user_id(links, meta={"source": "revenuecat_webhook", "event_id": event_id, "event_type": event_type})
    product_id = str(event.get("product_id") or "").strip() or None
    transaction_id = str(event.get("transaction_id") or "").strip() or None
    original = str(event.get("original_transaction_id") or transaction_id or event_id).strip()
    environment = normalize_environment(event.get("environment"))
    period_type = str(event.get("period_type") or "").strip() or None
    purchased_at = _ms_to_iso(event.get("purchased_at_ms")) or _ms_to_iso(event.get("event_timestamp_ms"))
    expires_at = _ms_to_iso(event.get("expiration_at_ms"))
    status, active, auto_renew = _revenuecat_status(event_type, period_type, expires_at)
    source = f"revenuecat_webhook:{event_type.lower()}"

    sub_id = upsert_subscription(
        user_id=user_id,
        provider="revenuecat",
        product_id=product_id,
        status=status,
        started_at=purchased_at,
        expires_at=expires_at,
        auto_renew=auto_renew,
        environment=environment,
        original_transaction_id=original,
        purchase_token=transaction_id,
        source=source,
        raw=event,
    )

    fallback_active = None if active else _active_subscription_for_user(user_id)
    entitlement_ids = event.get("entitlement_ids")
    if not isinstance(entitlement_ids, list) or not entitlement_ids:
        entitlement_ids = [event.get("entitlement_id") or "pro"]
    entitlements = [str(x or "").strip().lower() for x in entitlement_ids if str(x or "").strip()]
    if not entitlements:
        entitlements = ["pro"]
    if any(x in {"pro", "premium", "noytrix_pro", "scamshield_pro"} for x in entitlements) or product_id:
        set_entitlement(
            user_id=user_id,
            entitlement="pro",
            is_active=bool(active or fallback_active),
            expires_at=expires_at if active else (fallback_active["expires_at"] if fallback_active else None),
            source=source if active else (fallback_active["source"] if fallback_active else source),
            provider="revenuecat" if active else (fallback_active["provider"] if fallback_active else "revenuecat"),
            subscription_id=sub_id if active else (int(fallback_active["id"]) if fallback_active else sub_id),
        )

    try:
        event_row_id = record_purchase_event(
            user_id=user_id,
            provider="revenuecat",
            external_event_id=event_id,
            event_type=event_type.lower(),
            product_id=product_id,
            status=status,
            purchase_token=transaction_id,
            transaction_id=transaction_id,
            original_transaction_id=original,
            environment=environment,
            raw={"api_version": body.get("api_version"), "event": event},
        )
    except sqlite3.IntegrityError:
        existing_after_race = purchase_event_exists("revenuecat", event_id)
        return {
            "ok": True,
            "duplicate": True,
            "purchaseEventId": existing_after_race,
            "eventId": event_id,
            "eventType": event_type,
        }
    return {
        "ok": True,
        "duplicate": False,
        "userId": user_id,
        "provider": "revenuecat",
        "eventId": event_id,
        "eventType": event_type,
        "status": status,
        "active": active,
        "subscriptionId": sub_id,
        "purchaseEventId": event_row_id,
    }
