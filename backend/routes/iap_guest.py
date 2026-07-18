from collections.abc import Callable

from fastapi import APIRouter, Body, HTTPException, Request

from identity import resolve_from_request
from subscriptions import entitlement_status, sync_google_play_purchase


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
        user_id = _guest_user_id(request, payload)
        if not user_id:
            raise HTTPException(status_code=400, detail="Missing userId")

        product_type = str(payload.get("productType") or "").strip().lower()
        product_id = str(payload.get("productId") or "").strip()
        package_name = str(payload.get("packageName") or "com.noytrix.app").strip()
        purchase_token = str(payload.get("purchaseToken") or "").strip()
        identity_user_id = resolve_from_request(
            request,
            [
                ("guest", user_id),
                ("revenuecat", user_id),
                ("google_play_token", purchase_token),
            ],
        )

        data = google_play_verify_purchase(product_type, package_name, product_id, purchase_token)
        active, status, expiry_dt = active_from_google_purchase(product_type, data)
        subscription_id = sync_google_play_purchase(
            user_id=identity_user_id,
            product_type=product_type,
            product_id=product_id,
            purchase_token=purchase_token,
            data=data,
            active=active,
            status=status,
            expires_at=expiry_dt.isoformat() if expiry_dt else None,
            environment=str(payload.get("environment") or "production"),
        )
        upsert_guest_iap_purchase(
            user_id=user_id,
            product_type=product_type,
            product_id=product_id,
            package_name=package_name,
            purchase_token=purchase_token,
            data=data,
            active=active,
            status=status,
            expiry_dt=expiry_dt,
        )

        if active:
            set_guest_pro(
                user_id,
                active=True,
                source=f"google_play_verified:{product_id}",
                expires_at=expiry_dt.isoformat() if expiry_dt else None,
            )
        else:
            sync_guest_google_entitlement(user_id)

        server_status = iap_status_payload(user_id)
        return {
            "ok": True,
            "userId": user_id,
            "identityUserId": identity_user_id,
            "active": bool(server_status.get("active")),
            "googleActive": active,
            "status": status,
            "subscriptionId": subscription_id,
            "productType": product_type,
            "productId": product_id,
            "orderId": data.get("orderId"),
            "expiryUtc": expiry_dt.isoformat() if expiry_dt else None,
            "acknowledgementState": data.get("acknowledgementState"),
            "purchaseState": data.get("purchaseState"),
            "paymentState": data.get("paymentState"),
        }

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
        return iap_status_payload(_guest_user_id(request, userId))

    @router.get("/subscriptions/status")
    async def subscriptions_status(request: Request, userId: str | None = None, entitlement: str = "pro"):
        uid = (
            str(userId or "").strip()
            or str(request.headers.get("x-noytrix-user-id") or "").strip()
            or str(request.headers.get("x-install-user-id") or "").strip()
            or str(request.headers.get("x-user-id") or "").strip()
        )
        auth_uid = get_user_id(request, None)
        candidates = [value for value in [uid, auth_uid] if value]
        status = entitlement_status(candidates, entitlement)
        return {
            "ok": True,
            **status,
            "userId": uid or auth_uid or status.get("userId"),
            "entitlementUserId": status.get("userId"),
        }

    return router
