from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import os, json, requests

from google.oauth2 import service_account
from google.auth.transport.requests import Request as GRequest

from db import get_db, Base, engine
from auth.deps import get_current_user
from auth.models import User
from iap_models import IAPPurchase
from identity import resolve_user_id
from subscriptions import entitlement_status, sync_google_play_purchase

Base.metadata.create_all(bind=engine)

router = APIRouter(tags=["iap"])

class GoogleVerifyIn(BaseModel):
    productType: str      # "subs" | "inapp"
    productId: str
    purchaseToken: str
    packageName: str

def _google_access_token() -> str:
    sa_path = os.getenv("GOOGLE_PLAY_SA_JSON", "").strip()
    if not sa_path or not os.path.exists(sa_path):
        raise HTTPException(status_code=500, detail="GOOGLE_PLAY_SA_JSON is missing on server")

    scopes = ["https://www.googleapis.com/auth/androidpublisher"]
    creds = service_account.Credentials.from_service_account_file(sa_path, scopes=scopes)
    creds.refresh(GRequest())
    return creds.token

def _call_android_publisher(product_type: str, package_name: str, product_id: str, token: str) -> dict:
    at = _google_access_token()
    headers = {"Authorization": f"Bearer {at}"}

    if product_type == "subs":
        url = f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{package_name}/purchases/subscriptions/{product_id}/tokens/{token}"
    else:
        url = f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{package_name}/purchases/products/{product_id}/tokens/{token}"

    r = requests.get(url, headers=headers, timeout=20)
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Google verify failed: {r.status_code} {r.text[:300]}")
    return r.json()

def _dt_from_ms(ms: int | str | None) -> datetime | None:
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except Exception:
        return None

def _to_naive_utc(dt_aware: datetime | None) -> datetime | None:
    if not dt_aware:
        return None
    return dt_aware.astimezone(timezone.utc).replace(tzinfo=None)

@router.get("/status")
def iap_status(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    identity_user_id = resolve_user_id(
        [("auth_user_id", str(current.id)), ("email", current.email)],
        meta={"source": "iap_status"},
    )
    ent = entitlement_status([identity_user_id, current.email, str(current.id)], "pro")
    active = bool(ent.get("active"))
    return {
        "ok": True,
        "plan": "PRO" if active else "FREE",
        "active": active,
        "isPro": active,
        "identityUserId": identity_user_id,
        "entitlement": ent,
    }

@router.post("/google/verify")
def google_verify(payload: GoogleVerifyIn, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ptype = (payload.productType or "").strip().lower()
    if ptype not in ("subs", "inapp"):
        raise HTTPException(status_code=400, detail="productType must be 'subs' or 'inapp'")

    product_id = payload.productId.strip()
    token = payload.purchaseToken.strip()
    package_name = payload.packageName.strip()

    if not product_id or not token or not package_name:
        raise HTTPException(status_code=400, detail="Missing productId/purchaseToken/packageName")

    data = _call_android_publisher(ptype, package_name, product_id, token)

    # ===== extract safety fields =====
    order_id = data.get("orderId")
    purchase_dt = _dt_from_ms(data.get("purchaseTimeMillis"))
    linked_token = data.get("linkedPurchaseToken")
    ack_state = data.get("acknowledgementState")

    status = "unknown"
    expiry_dt = None
    active = False

    if ptype == "subs":
        expiry_dt = _dt_from_ms(data.get("expiryTimeMillis"))
        payment_state = data.get("paymentState")
        cancel_reason = data.get("cancelReason")

        # Base rule: must be not expired
        if expiry_dt and expiry_dt > datetime.now(timezone.utc):
            active = True
            status = "active"
        else:
            active = False
            status = "expired"

        # 2nd level: require payment received if present
        if active and payment_state is not None:
            try:
                if int(payment_state) != 1:
                    active = False
                    status = "unknown"
            except Exception:
                active = False
                status = "unknown"

        # if canceled but still not expired -> keep active (normal behavior)
        # we store cancel_reason for analytics

        purchase_state = None  # not used for subs

    else:
        purchase_state = data.get("purchaseState")  # 0 purchased, 1 canceled, 2 pending (varies)
        payment_state = None
        cancel_reason = None

        if purchase_state == 0:
            active = True
            status = "active"
        elif purchase_state == 2:
            active = False
            status = "unknown"
        else:
            active = False
            status = "canceled"

        expiry_dt = None  # lifetime inapp => no expiry in db

    raw_json = json.dumps(data, ensure_ascii=False)
    now = datetime.utcnow()
    identity_user_id = resolve_user_id(
        [("auth_user_id", str(current.id)), ("email", current.email), ("google_play_token", token)],
        meta={"source": "iap_google_verify"},
    )

    expiry_naive = _to_naive_utc(expiry_dt)
    purchase_naive = _to_naive_utc(purchase_dt)

    # ===== Upgrades/Downgrades: if token is linked, previous entitlement should be invalidated =====
    if linked_token:
        prev = db.query(IAPPurchase).filter(IAPPurchase.purchase_token == linked_token).first()
        if prev and (prev.status or "").lower() == "active":
            prev.status = "canceled"
            prev.updated_at = now

    rec = db.query(IAPPurchase).filter(IAPPurchase.purchase_token == token).first()

    if not rec:
        rec = IAPPurchase(
            user_id=current.id,
            provider="google",
            product_type=ptype,
            product_id=product_id,
            package_name=package_name,
            purchase_token=token,
            status=status,
            expiry_time_utc=expiry_naive,
            order_id=str(order_id) if order_id else None,
            purchase_time_utc=purchase_naive,
            linked_purchase_token=str(linked_token) if linked_token else None,
            acknowledgement_state=int(ack_state) if ack_state is not None else None,
            payment_state=int(payment_state) if payment_state is not None else None,
            cancel_reason=int(cancel_reason) if cancel_reason is not None else None,
            purchase_state=int(purchase_state) if purchase_state is not None else None,
            raw=raw_json,
            created_at=now,
            updated_at=now,
        )
        db.add(rec)
    else:
        rec.user_id = current.id
        rec.product_type = ptype
        rec.product_id = product_id
        rec.package_name = package_name
        rec.status = status
        rec.expiry_time_utc = expiry_naive
        rec.order_id = str(order_id) if order_id else None
        rec.purchase_time_utc = purchase_naive
        rec.linked_purchase_token = str(linked_token) if linked_token else None
        rec.acknowledgement_state = int(ack_state) if ack_state is not None else None
        rec.payment_state = int(payment_state) if payment_state is not None else None
        rec.cancel_reason = int(cancel_reason) if cancel_reason is not None else None
        rec.purchase_state = int(purchase_state) if purchase_state is not None else None
        rec.raw = raw_json
        rec.updated_at = now

    subscription_id = sync_google_play_purchase(
        user_id=identity_user_id,
        product_type=ptype,
        product_id=product_id,
        purchase_token=token,
        data=data,
        active=active,
        status=status,
        expires_at=expiry_dt.isoformat() if expiry_dt else None,
        environment="production",
    )

    db.commit()

    return {
        "ok": True,
        "active": active,
        "status": status,
        "plan": "PRO" if active else "FREE",
        "identityUserId": identity_user_id,
        "subscriptionId": subscription_id,
        "expiryUtc": expiry_dt.isoformat() if expiry_dt else None,
        "orderId": order_id,
        "purchaseTimeUtc": purchase_dt.isoformat() if purchase_dt else None,
        "linkedPurchaseToken": linked_token,
        "acknowledgementState": ack_state,
    }

@router.post("/sync/plans")
def sync_plans(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Manual sync endpoint for current user.
    You can call it after app starts, or on profile refresh.
    """
    identity_user_id = resolve_user_id(
        [("auth_user_id", str(current.id)), ("email", current.email)],
        meta={"source": "iap_sync_plans"},
    )
    ent = entitlement_status([identity_user_id, current.email, str(current.id)], "pro")
    active = bool(ent.get("active"))
    return {"ok": True, "plan": "PRO" if active else "FREE", "active": active, "identityUserId": identity_user_id, "entitlement": ent}
