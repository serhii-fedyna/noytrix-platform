from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Header, HTTPException, Query

from .config import admin_token, enabled, outreach_enabled
from .outreach import approve_draft
from .repository import prospect_snapshot, run_snapshot
from .service import run_partnership_pipeline


router = APIRouter(prefix="/internal/brain", tags=["noytrix-brain"])


def _require_admin(token: str | None) -> None:
    configured = admin_token()
    if not configured:
        raise HTTPException(status_code=503, detail="brain_admin_token_not_configured")
    if token != configured:
        raise HTTPException(status_code=403, detail="brain_forbidden")


def _decode(item: dict) -> dict:
    item = dict(item)
    for key in ("rationale_json", "details_json"):
        if key in item:
            try:
                item[key.removesuffix("_json")] = json.loads(item.pop(key) or "{}")
            except Exception:
                item.pop(key, None)
    return item


@router.get("/health")
def brain_health() -> dict:
    return {"ok": True, "enabled": enabled(), "outreach_delivery_enabled": outreach_enabled(), "mode": "approval_required"}


@router.get("/partnerships")
def partnerships(
    limit: int = Query(50, ge=1, le=200),
    x_brain_admin_token: str | None = Header(default=None),
) -> dict:
    _require_admin(x_brain_admin_token)
    return {"ok": True, "items": [_decode(item) for item in prospect_snapshot(limit)]}


@router.get("/runs")
def runs(x_brain_admin_token: str | None = Header(default=None)) -> dict:
    _require_admin(x_brain_admin_token)
    return {"ok": True, "items": [_decode(item) for item in run_snapshot()]}


@router.post("/partnerships/run")
async def run_partnerships(
    limit: int = Query(8, ge=1, le=25),
    x_brain_admin_token: str | None = Header(default=None),
) -> dict:
    _require_admin(x_brain_admin_token)
    return await asyncio.to_thread(run_partnership_pipeline, limit=limit)


@router.post("/drafts/{draft_id}/approve")
def approve(draft_id: int, approved_by: str = "admin", x_brain_admin_token: str | None = Header(default=None)) -> dict:
    _require_admin(x_brain_admin_token)
    if not approve_draft(draft_id, approved_by):
        raise HTTPException(status_code=409, detail="draft_not_pending_review")
    return {"ok": True, "draft_id": draft_id, "status": "approved", "delivery": "still_disabled_until_provider_rollout"}
