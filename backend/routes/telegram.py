import os
import secrets
import smtplib
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request

from identity import resolve_user_id
from subscriptions import entitlement_status


def send_telegram_link_email(to_email: str, code: str) -> None:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    mail_from = os.getenv("MAIL_FROM", smtp_user)

    if not smtp_user or not smtp_pass or not to_email:
        raise RuntimeError("smtp_not_configured")

    html = f"""
    <div style="background:#06080f;padding:28px;font-family:Arial,sans-serif;color:#e9ecff">
      <div style="max-width:560px;margin:auto;background:#101826;border:1px solid rgba(255,255,255,.12);border-radius:22px;padding:28px">
        <div style="color:#ffb020;font-size:24px;font-weight:800">NOYTRIX</div>
        <h2 style="margin:12px 0 8px;color:#fff">Telegram connect code</h2>
        <p style="color:#A8B4CF">Use this code to connect your Telegram bot to your Noytrix account.</p>
        <div style="margin:24px 0;padding:20px;border-radius:18px;background:#0b1020;text-align:center;font-size:38px;font-weight:900;letter-spacing:8px;color:#ffb020">
          {code}
        </div>
        <p style="color:#A8B4CF">This code is valid for 10 minutes.</p>
        <p style="color:#A8B4CF">If you did not request this, you can ignore this email.</p>
      </div>
    </div>
    """

    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = "Your Noytrix Telegram connect code"
    msg["From"] = f"Noytrix <{mail_from}>"
    msg["To"] = to_email

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(mail_from, [to_email], msg.as_string())


def create_telegram_router(
    app_db_path: Path,
    get_lang: Callable[[Request | None, str | None], str],
    require_app_key: Callable[[Request, str], None],
) -> APIRouter:
    router = APIRouter()

    def _profile_payload(request: Request, telegram_id: str, lang: str | None = None) -> dict:
        L = get_lang(request, lang)
        require_app_key(request, L)

        tid = str(telegram_id or "").strip()

        conn = sqlite3.connect(str(app_db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT telegram_id, user_id, email, linked_at FROM telegram_links WHERE telegram_id=?",
                (tid,),
            ).fetchone()
        finally:
            conn.close()

        linked = dict(row) if row else None
        user_ids = [f"telegram_{tid}"]

        if linked:
            if linked.get("user_id"):
                user_ids.append(str(linked["user_id"]))
            if linked.get("email"):
                user_ids.append(str(linked["email"]).lower())

        ent = entitlement_status(user_ids, "pro")
        is_pro = bool(ent.get("active"))

        conn = sqlite3.connect(str(app_db_path))
        conn.row_factory = sqlite3.Row
        try:
            stats_row = conn.execute(
                "SELECT total_scans, scam_reports, last_activity FROM telegram_profile_stats WHERE telegram_id=?",
                (tid,),
            ).fetchone()
        finally:
            conn.close()

        stats = dict(stats_row) if stats_row else {
            "total_scans": 0,
            "scam_reports": 0,
            "last_activity": None,
        }

        return {
            "ok": True,
            "telegram_id": tid,
            "linked": linked,
            "isPro": is_pro,
            "plan": "PRO" if is_pro else "FREE",
            "entitlement": ent,
            "stats": stats,
        }

    @router.post("/telegram/link-code/create")
    def telegram_link_code_create(request: Request, payload: dict = Body(...), lang: str | None = None):
        L = get_lang(request, lang)
        require_app_key(request, L)

        user_id = str(payload.get("user_id") or "").strip().lower()
        email = str(payload.get("email") or "").strip().lower()

        if not user_id:
            raise HTTPException(status_code=400, detail="user_id_required")

        code = str(secrets.randbelow(900000) + 100000)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        expires_at = (now + timedelta(minutes=10)).isoformat()

        conn = sqlite3.connect(str(app_db_path))
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO telegram_link_codes
                (code, user_id, email, expires_at, used_at)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (code, user_id, email, expires_at),
            )
            conn.commit()
        finally:
            conn.close()

        if email:
            send_telegram_link_email(email, code)

        return {
            "ok": True,
            "sent": bool(email),
            "expires_at": expires_at,
        }

    @router.post("/telegram/link")
    def telegram_link(request: Request, payload: dict = Body(...), lang: str | None = None):
        L = get_lang(request, lang)
        require_app_key(request, L)

        telegram_id = str(payload.get("telegram_id") or "").strip()
        email = str(payload.get("email") or "").strip().lower()
        user_id = str(payload.get("user_id") or email or "").strip().lower()

        if not telegram_id or not email:
            raise HTTPException(status_code=400, detail="telegram_id_and_email_required")

        conn = sqlite3.connect(str(app_db_path))
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO telegram_links
                (telegram_id, user_id, email, linked_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    user_id,
                    email,
                    datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        identity_user_id = resolve_user_id(
            [("telegram", telegram_id), ("email", email), ("guest", user_id)],
            meta={"source": "telegram_link"},
        )

        return {
            "ok": True,
            "telegram_id": telegram_id,
            "user_id": user_id,
            "email": email,
            "identityUserId": identity_user_id,
        }

    @router.post("/telegram/link-code/confirm")
    def telegram_link_code_confirm(request: Request, payload: dict = Body(...), lang: str | None = None):
        L = get_lang(request, lang)
        require_app_key(request, L)

        telegram_id = str(payload.get("telegram_id") or "").strip()
        code = str(payload.get("code") or "").strip()

        if not telegram_id or not code:
            raise HTTPException(status_code=400, detail="telegram_id_and_code_required")

        now = datetime.now(timezone.utc).replace(microsecond=0)

        conn = sqlite3.connect(str(app_db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT code, user_id, email, expires_at, used_at
                FROM telegram_link_codes
                WHERE code=?
                """,
                (code,),
            ).fetchone()

            if not row:
                raise HTTPException(status_code=400, detail="invalid_code")
            if row["used_at"]:
                raise HTTPException(status_code=400, detail="code_already_used")

            try:
                exp = datetime.fromisoformat(str(row["expires_at"]))
            except Exception:
                raise HTTPException(status_code=400, detail="invalid_code_expiry")

            if exp < now:
                raise HTTPException(status_code=400, detail="code_expired")

            user_id = str(row["user_id"] or "").strip().lower()
            email = str(row["email"] or user_id or "").strip().lower()

            conn.execute(
                """
                INSERT OR REPLACE INTO telegram_links
                (telegram_id, user_id, email, linked_at)
                VALUES (?, ?, ?, ?)
                """,
                (telegram_id, user_id, email, now.isoformat()),
            )
            conn.execute("UPDATE telegram_link_codes SET used_at=? WHERE code=?", (now.isoformat(), code))
            conn.commit()
        finally:
            conn.close()

        identity_user_id = resolve_user_id(
            [("telegram", telegram_id), ("email", email), ("guest", user_id)],
            meta={"source": "telegram_link_code_confirm"},
        )

        return {
            "ok": True,
            "telegram_id": telegram_id,
            "user_id": user_id,
            "email": email,
            "identityUserId": identity_user_id,
        }

    @router.post("/telegram/unlink")
    async def telegram_unlink(payload: dict):
        telegram_id = str(payload.get("telegram_id") or "").strip()
        if not telegram_id:
            raise HTTPException(status_code=400, detail="telegram_id_required")

        conn = sqlite3.connect(str(app_db_path))
        try:
            conn.execute("DELETE FROM telegram_links WHERE telegram_id=?", (telegram_id,))
            conn.commit()
        finally:
            conn.close()

        return {
            "ok": True,
            "telegram_id": telegram_id,
            "unlinked": True,
        }

    @router.post("/telegram/scan-limit/check")
    def telegram_scan_limit_check(request: Request, payload: dict = Body(...), lang: str | None = None):
        L = get_lang(request, lang)
        require_app_key(request, L)

        telegram_id = str(payload.get("telegram_id") or "").strip()
        if not telegram_id:
            raise HTTPException(status_code=400, detail="telegram_id_required")

        profile = _profile_payload(request, telegram_id=telegram_id, lang=lang)
        is_pro = bool(profile.get("isPro"))

        if is_pro:
            return {
                "ok": True,
                "allowed": True,
                "isPro": True,
                "limit": None,
                "used": 0,
                "left": None,
            }

        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        free_limit = 4

        conn = sqlite3.connect(str(app_db_path))
        try:
            row = conn.execute(
                "SELECT scans FROM telegram_scan_limits WHERE telegram_id=? AND day=?",
                (telegram_id, day),
            ).fetchone()

            used = int(row[0]) if row else 0
            if used >= free_limit:
                return {
                    "ok": True,
                    "allowed": False,
                    "isPro": False,
                    "limit": free_limit,
                    "used": used,
                    "left": 0,
                }

            conn.execute(
                """
                INSERT INTO telegram_scan_limits (telegram_id, day, scans)
                VALUES (?, ?, 1)
                ON CONFLICT(telegram_id, day) DO UPDATE SET scans = scans + 1
                """,
                (telegram_id, day),
            )
            conn.commit()

            return {
                "ok": True,
                "allowed": True,
                "isPro": False,
                "limit": free_limit,
                "used": used + 1,
                "left": max(0, free_limit - used - 1),
            }
        finally:
            conn.close()

    @router.post("/telegram/profile/stats/track")
    def telegram_profile_stats_track(request: Request, payload: dict = Body(...), lang: str | None = None):
        L = get_lang(request, lang)
        require_app_key(request, L)

        telegram_id = str(payload.get("telegram_id") or "").strip()
        level = str(payload.get("level") or "").lower().strip()
        if not telegram_id:
            raise HTTPException(status_code=400, detail="telegram_id_required")

        is_scam = 1 if level in {"danger", "critical"} else 0
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        conn = sqlite3.connect(str(app_db_path))
        try:
            conn.execute(
                """
                INSERT INTO telegram_profile_stats
                (telegram_id, total_scans, scam_reports, last_activity)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    total_scans = total_scans + 1,
                    scam_reports = scam_reports + excluded.scam_reports,
                    last_activity = excluded.last_activity
                """,
                (telegram_id, is_scam, now),
            )
            conn.commit()
        finally:
            conn.close()

        return {"ok": True, "telegram_id": telegram_id}

    @router.get("/telegram/profile")
    def telegram_profile(request: Request, telegram_id: str, lang: str | None = None):
        return _profile_payload(request, telegram_id=telegram_id, lang=lang)

    return router
