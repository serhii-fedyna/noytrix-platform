import json
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import APIRouter, Body, HTTPException, Request


def create_admin_spender_router(
    get_lang: Callable,
    require_app_key: Callable,
    db_connect: Callable,
    evm_address_re,
) -> APIRouter:
    router = APIRouter()

    @router.post("/admin/spender-reputation/add")
    def admin_add_spender_reputation(request: Request, payload: dict = Body(...), lang: str | None = None):
        selected_lang = get_lang(request, lang)
        require_app_key(request, selected_lang)

        address = str(payload.get("address") or "").lower().strip()
        if not evm_address_re.match(address):
            raise HTTPException(status_code=400, detail={"error": "invalid_evm_address"})

        label = str(payload.get("label") or "Unknown spender").strip()
        category = str(payload.get("category") or "wallet_drainer").strip()
        trust = str(payload.get("trust") or "malicious").strip().lower()
        risk = str(payload.get("risk") or "critical").strip().lower()
        reasons = payload.get("reasons") or ["manual_admin_reputation"]
        source = str(payload.get("source") or "admin").strip()
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        conn = db_connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO spender_reputation
                (address,label,category,trust,risk,reasons,source,first_seen,last_seen)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    address,
                    label,
                    category,
                    trust,
                    risk,
                    json.dumps(reasons, ensure_ascii=False),
                    source,
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return {"ok": True, "address": address, "label": label, "trust": trust, "risk": risk}

    @router.get("/admin/spender-reputation/list")
    def admin_list_spender_reputation(request: Request, lang: str | None = None, limit: int = 50):
        selected_lang = get_lang(request, lang)
        require_app_key(request, selected_lang)

        conn = db_connect()
        try:
            rows = conn.execute(
                """
                SELECT address,label,category,trust,risk,reasons,source,first_seen,last_seen
                FROM spender_reputation
                ORDER BY last_seen DESC
                LIMIT ?
                """,
                (max(1, min(int(limit or 50), 200)),),
            ).fetchall()
            return {"ok": True, "items": [dict(row) for row in rows]}
        finally:
            conn.close()

    @router.get("/admin/spender-runtime-events/list")
    def admin_list_spender_runtime_events(request: Request, lang: str | None = None, limit: int = 50):
        selected_lang = get_lang(request, lang)
        require_app_key(request, selected_lang)

        conn = db_connect()
        try:
            rows = conn.execute(
                """
                SELECT id,address,domain,method,level,unlimited,drainer_flags,created_at
                FROM spender_runtime_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, min(int(limit or 50), 200)),),
            ).fetchall()
            return {"ok": True, "items": [dict(row) for row in rows]}
        finally:
            conn.close()

    @router.get("/admin/drainer-campaigns/list")
    def admin_list_drainer_campaigns(request: Request, lang: str | None = None, limit: int = 50):
        selected_lang = get_lang(request, lang)
        require_app_key(request, selected_lang)

        conn = db_connect()
        try:
            rows = conn.execute(
                """
                SELECT campaign_id,spender,domains,events_count,critical_count,first_seen,last_seen,risk
                FROM drainer_campaigns
                ORDER BY critical_count DESC, events_count DESC, last_seen DESC
                LIMIT ?
                """,
                (max(1, min(int(limit or 50), 200)),),
            ).fetchall()
            return {"ok": True, "items": [dict(row) for row in rows]}
        finally:
            conn.close()

    return router
