import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from identity import resolve_user_id  # noqa: E402
from subscriptions import (  # noqa: E402
    entitlement_status,
    normalize_environment,
    purchase_event_exists,
    record_purchase_event,
    set_entitlement,
    set_user_flags,
    upsert_subscription,
)


DATA_DIR = ROOT / "data"
GUEST_PRO_DB = DATA_DIR / "guest_pro.sqlite3"
EXPORT_DIR = DATA_DIR / "migration_exports"

INTERNAL_EMAILS = {
    "kritea2024@gmail.com",
    "serhiifedyna1997@gmail.com",
    "fedinalv9@gmail.com",
    "noytrixapp@gmail.com",
}


def now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def parse_dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.isdigit():
            ts = int(raw)
            if ts > 10_000_000_000:
                ts = ts // 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def is_unexpired(expires_at: Any) -> bool:
    expiry = parse_dt(expires_at)
    return not expiry or expiry > datetime.now(timezone.utc)


def identity_links(old_user_id: str, source: str) -> list[tuple[str, str]]:
    uid = str(old_user_id or "").strip()
    src = str(source or "").strip().lower()
    links: list[tuple[str, str]] = []
    if not uid:
        return links
    if "@" in uid:
        links.append(("email", uid.lower()))
    elif uid.startswith("telegram_"):
        links.append(("telegram", uid.replace("telegram_", "", 1)))
        links.append(("guest", uid))
    elif uid.isdigit():
        links.append(("auth_user_id", uid))
        links.append(("guest", uid))
    else:
        links.append(("guest", uid))
    if src == "revenuecat_guest":
        links.append(("revenuecat", uid))
    return links


def classify(row: dict) -> dict:
    old_user_id = str(row.get("user_id") or "").strip()
    source = str(row.get("source") or "").strip()
    src = source.lower()
    email = old_user_id.lower() if "@" in old_user_id else ""
    active = int(row.get("is_active") or 0) == 1 and is_unexpired(row.get("expires_at"))

    classification = "complimentary"
    provider = "manual"
    environment = "production"
    is_test_user = False
    is_internal_user = False
    reason = source or "legacy_guest_pro"

    if old_user_id == "audit_test_pro" or src == "audit":
        classification = "audit"
        environment = "test"
        is_test_user = True
        is_internal_user = True
    elif "test" in src or "debug" in src or old_user_id in {"web_demo", "debug"}:
        classification = "test"
        environment = "test"
        is_test_user = True
    elif email in INTERNAL_EMAILS:
        classification = "test"
        environment = "test"
        is_test_user = True
        is_internal_user = True
        reason = f"{source}; internal_email"
    elif src == "telegram_lifetime_pro":
        classification = "telegram_lifetime"
        provider = "telegram"
    elif old_user_id.startswith("telegram_") and src in {"manual", "telegram"}:
        classification = "complimentary"
        provider = "telegram"
    elif src.startswith("manual_paid_month_recovery") or src.startswith("manual_recovery"):
        classification = "manual_recovery"
        provider = "manual"
    elif src.startswith("google_play"):
        classification = "production_paid"
        provider = "google_play"
    elif src == "revenuecat_guest":
        classification = "production_paid"
        provider = "revenuecat"

    status = "active" if active else "inactive"
    if classification == "audit":
        status = "audit_active" if active else "audit_inactive"
    elif classification == "test":
        status = "test_active" if active else "test_inactive"

    return {
        "classification": classification,
        "provider": provider,
        "environment": normalize_environment(environment),
        "is_test_user": is_test_user,
        "is_internal_user": is_internal_user,
        "active": active,
        "status": status,
        "reason": reason,
    }


def load_guest_pro_rows() -> list[dict]:
    conn = sqlite3.connect(f"file:{GUEST_PRO_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT user_id, is_active, source, updated_at, expires_at FROM guest_pro ORDER BY updated_at DESC, user_id"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def export_report(rows: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "guest_pro_export.json"
    csv_path = out_dir / "guest_pro_export.csv"
    summary_path = out_dir / "summary.json"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["user_id"])
        writer.writeheader()
        writer.writerows(rows)
    summary: dict[str, int] = {}
    for row in rows:
        key = f"{row.get('classification')}:{row.get('status')}"
        summary[key] = summary.get(key, 0) + 1
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def migrate_row(row: dict, dry_run: bool) -> dict:
    info = classify(row)
    links = identity_links(row["user_id"], row.get("source") or "")
    if not links:
        links = [("guest", row["user_id"])]
    user_id = resolve_user_id(links, meta={"source": "guest_pro_migration", "old_user_id": row["user_id"]})
    out = {**row, **info, "new_user_id": user_id, "event_id": f"legacy_guest_pro:{row['user_id']}"}
    if dry_run:
        return out

    set_user_flags(
        user_id,
        is_test_user=info["is_test_user"],
        is_internal_user=info["is_internal_user"],
        environment=info["environment"],
        classification=info["classification"],
        reason=info["reason"],
    )

    sub_id = upsert_subscription(
        user_id=user_id,
        provider=info["provider"],
        product_id="pro",
        status=info["status"],
        started_at=parse_dt(row.get("updated_at")).isoformat() if parse_dt(row.get("updated_at")) else None,
        expires_at=row.get("expires_at") or None,
        auto_renew=False,
        environment=info["environment"],
        original_transaction_id=f"legacy_guest_pro:{row['user_id']}",
        purchase_token=None,
        source=f"legacy_guest_pro:{info['classification']}",
        raw=row,
    )

    if info["active"]:
        set_entitlement(
            user_id=user_id,
            entitlement="pro",
            is_active=True,
            expires_at=row.get("expires_at") or None,
            source=f"legacy_guest_pro:{info['classification']}",
            provider=info["provider"],
            subscription_id=sub_id,
        )
    elif not entitlement_status([user_id], "pro").get("active"):
        set_entitlement(
            user_id=user_id,
            entitlement="pro",
            is_active=False,
            expires_at=None,
            source=f"legacy_guest_pro:{info['classification']}:inactive",
            provider=info["provider"],
            subscription_id=sub_id,
        )

    if not purchase_event_exists(info["provider"], out["event_id"]):
        record_purchase_event(
            user_id=user_id,
            provider=info["provider"],
            external_event_id=out["event_id"],
            event_type="legacy_guest_pro_migrated",
            product_id="pro",
            status=info["status"],
            original_transaction_id=out["event_id"],
            environment=info["environment"],
            raw={**row, **info},
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write subscriptions, entitlements, events and flags")
    parser.add_argument("--out-dir", default="", help="optional export directory")
    args = parser.parse_args()

    rows = load_guest_pro_rows()
    out_dir = Path(args.out_dir) if args.out_dir else EXPORT_DIR / f"guest_pro_migration_{now_tag()}"
    migrated = [migrate_row(row, dry_run=not args.apply) for row in rows]
    export_report(migrated, out_dir)

    readonly_copy = out_dir / "guest_pro.readonly.sqlite3"
    if not readonly_copy.exists():
        readonly_copy.write_bytes(GUEST_PRO_DB.read_bytes())
        readonly_copy.chmod(0o444)

    print(json.dumps({
        "ok": True,
        "applied": bool(args.apply),
        "rows": len(migrated),
        "outDir": str(out_dir),
        "readonlyCopy": str(readonly_copy),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
