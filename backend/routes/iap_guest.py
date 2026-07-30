from collections.abc import Callable

from fastapi import APIRouter, Body, HTTPException, Request

def _guest_user_id(request: Request, payload_or_user_id: dict | str | None = None) -> str:
    if isinstance(payload_or_user_id, dict):
        raw = payload_or_user_id.get("userId") or ""
    else:
        raw = payload_or_user_id or ""
    return (
        str(raw).strip()
        or str(request.headers.get("x-user-id") or "").strip()
        or str(request.headers.get("x_user_id") or "").strip()
        or str(request.headers.get("user-id") or "").strip()
    )


def create_iap_guest_router(
    google_play_verify_purchase: Callable[[str, str, str, str], dict],
    active_from_google_purchase: Callable,
    upsert_guest_iap_purchase: Callable,
    set_guest_pro: Callable,
    sync_guest_google_entitlement: Callable[[str], dict],
    iap_status_payload: Callable[[str | None], dict],
    payload_bool: Callable[[dict, list[str]], bool | None],
    get_user_id: Callable,
) -> APIRouter:
    router = APIRouter()

    @router.post("/iap/google/guest/verify")
    async def iap_google_guest_verify(request: Request, payload: dict = Body(...)):
        # A store receipt may only unlock the authenticated Noytrix account
        # selected by the purchaser. The legacy guest path used a device id and
        # could accidentally make the same purchase active for another account.
        raise HTTPException(
            status_code=410,
            detail="Google Play purchase restoration now requires signing in to your Noytrix account.",
        )

    @router.post("/iap/guest/activate")
    async def iap_guest_activate(request: Request, payload: dict = Body(...), lang: str | None = None):
        user_id = _guest_user_id(request, payload)
        if not user_id:
            raise HTTPException(status_code=400, detail="Missing userId")

        has_pro = payload_bool(payload, ["hasPro", "isPro", "active", "pro", "premium", "entitlementActive"])
        if has_pro is None:
            has_pro = True
        source = str(payload.get("source") or "guest_iap").strip()

        if not has_pro:
            out = iap_status_payload(user_id)
            out.update({
                "ignored": True,
                "reason": "client_false_does_not_revoke_pro",
            })
            return out

        out = iap_status_payload(user_id)
        out.update({
            "ignored": True,
            "reason": "client_activation_disabled_use_google_verify",
            "requestedSource": source,
        })
        return out

    @router.get("/iap/guest/status")
    async def iap_guest_status(request: Request, userId: str | None = None):
        raise HTTPException(
            status_code=410,
            detail="Subscription status is available only for an authenticated Noytrix account.",
        )

    @router.get("/subscriptions/status")
    async def subscriptions_status(request: Request, userId: str | None = None, entitlement: str = "pro"):
        raise HTTPException(
            status_code=410,
            detail="Subscription status is available only for an authenticated Noytrix account.",
        )

    return router
