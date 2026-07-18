import hmac
import os
from typing import Optional

import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Body, HTTPException, Request

from identity import identity_links_for, resolve_from_request
from product_analytics import analytics_funnel, record_product_event
from subscriptions import process_revenuecat_webhook


load_dotenv("/root/backend/.env")

router = APIRouter()

JWT_SECRET = os.getenv("JWT_SECRET", "devsecret_change_me")
JWT_ALG = "HS256"
NOYTRIX_APP_KEY = (os.getenv("NOYTRIX_APP_KEY") or "").strip()
REVENUECAT_WEBHOOK_SECRET = (
    os.getenv("REVENUECAT_WEBHOOK_SECRET")
    or os.getenv("REVENUECAT_WEBHOOK_AUTH")
    or ""
).strip()


def _get_user_id(request: Request, user_id_q: Optional[str] = None) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.strip().lower().startswith("bearer "):
        token = auth.strip()[7:].strip()
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
            for key in ("email", "user_email", "sub", "userId", "user_id", "id", "uid", "nick", "username"):
                value = payload.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
        except Exception:
            pass

    header_user_id = (
        request.headers.get("x-user-id")
        or request.headers.get("x_user_id")
        or request.headers.get("user-id")
    )
    if header_user_id and header_user_id.strip():
        return header_user_id.strip()
    if user_id_q and str(user_id_q).strip():
        return str(user_id_q).strip()
    return None


def _extract_candidate_app_keys(request: Request) -> list[str]:
    values = [
        request.headers.get("x-app-key"),
        request.headers.get("X-App-Key"),
        request.headers.get("x-api-key"),
        request.query_params.get("appKey"),
        request.query_params.get("app_key"),
    ]
    return [str(value).strip().strip('"').strip("'") for value in values if value]


def _has_valid_app_key(request: Request) -> bool:
    if not NOYTRIX_APP_KEY:
        return True
    expected = NOYTRIX_APP_KEY.strip().strip('"').strip("'")
    return any(got == expected for got in _extract_candidate_app_keys(request))


def _require_app_key(request: Request) -> None:
    if not _has_valid_app_key(request):
        raise HTTPException(status_code=403, detail="forbidden")


@router.post("/identity/identify")
async def identity_identify(request: Request, payload: dict = Body(default={})):
    payload = dict(payload or {})
    links: list[tuple[str, object]] = []

    for kind, *names in (
        ("guest", "guest_id", "guestId", "install_user_id", "installUserId", "device_id", "deviceId"),
        ("revenuecat", "revenuecat_app_user_id", "revenueCatAppUserId", "app_user_id", "appUserId"),
        ("email", "email"),
        ("telegram", "telegram_id", "telegramId"),
        ("google_play_token", "purchase_token", "purchaseToken", "googlePlayPurchaseToken"),
        ("api_email", "api_email", "apiEmail", "owner_email", "ownerEmail"),
        ("auth_user_id", "auth_user_id", "authUserId", "user_db_id", "userDbId"),
    ):
        for name in names:
            value = payload.get(name)
            if value:
                links.append((kind, value))

    auth_uid = _get_user_id(request)
    if auth_uid:
        links.append(("email" if "@" in str(auth_uid) else "auth_user_id", auth_uid))

    user_id = resolve_from_request(request, links)
    return {
        "ok": True,
        "user_id": user_id,
        "userId": user_id,
        "links": identity_links_for(user_id),
    }


def _valid_revenuecat_webhook_auth(request: Request) -> bool:
    got = (request.headers.get("authorization") or request.headers.get("Authorization") or "").strip()
    secrets: list[str] = []
    if REVENUECAT_WEBHOOK_SECRET:
        secrets.append(REVENUECAT_WEBHOOK_SECRET)
        if not REVENUECAT_WEBHOOK_SECRET.lower().startswith("bearer "):
            secrets.append(f"Bearer {REVENUECAT_WEBHOOK_SECRET}")
    if NOYTRIX_APP_KEY:
        key = NOYTRIX_APP_KEY.strip().strip('"').strip("'")
        secrets.extend([key, f"Bearer {key}"])
    return any(hmac.compare_digest(got, str(secret or "").strip()) for secret in secrets if str(secret or "").strip())


@router.post("/webhooks/revenuecat")
async def revenuecat_webhook(request: Request, payload: dict = Body(default={})):
    if not _valid_revenuecat_webhook_auth(request):
        raise HTTPException(status_code=401, detail="invalid_revenuecat_webhook_authorization")
    try:
        return process_revenuecat_webhook(dict(payload or {}))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        print("[revenuecat_webhook] error:", exc)
        raise HTTPException(status_code=500, detail="revenuecat_webhook_failed")


@router.post("/analytics/events")
async def analytics_events(request: Request, payload: dict = Body(default={})):
    data = dict(payload or {})
    if not data.get("user_id"):
        uid = _get_user_id(request)
        if uid:
            data["user_id"] = uid
    return record_product_event(data)


@router.get("/analytics/funnel")
async def analytics_funnel_endpoint(request: Request, days: int = 30):
    _require_app_key(request)
    return analytics_funnel(days=days)
