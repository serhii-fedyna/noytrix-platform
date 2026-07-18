import time
from collections.abc import Callable
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel


class B2BScanIn(BaseModel):
    input: str
    lang: Optional[str] = "en"
    user_id: Optional[str] = None
    explanation_mode: Optional[str] = "detailed"
    internal_only: Optional[bool] = False
    external_check: Optional[bool] = False


def create_b2b_router(
    require_b2b_api_key: Callable,
    api_current_month: Callable[[], str],
    api_client_ip: Callable[[Request], str],
    api_log_usage: Callable,
    b2b_increment_usage: Callable[[int, str], None],
    security_analyze_core: Callable,
    normalize_lang: Callable[[str | None], str],
    attach_legacy_fields: Callable,
    attach_ux_risk_blocks: Callable,
    build_ai_explanation_context: Callable,
    generate_ai_security_judge: Callable,
    generate_ai_security_explanation: Callable,
    internal_mode: bool,
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/docs")
    async def b2b_v1_docs():
        return {
            "ok": True,
            "name": "Noytrix API",
            "version": "v1",
            "base_url": "https://api.noytrixapp.com",
            "authentication": {
                "header": "x-api-key",
                "alternative": "Authorization: Bearer YOUR_API_KEY",
            },
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/v1/me",
                    "description": "Check API key status, plan and usage.",
                },
                {
                    "method": "POST",
                    "path": "/v1/scan",
                    "description": "Scan URL, domain, wallet, smart contract, token/ticker or text for crypto scam risk.",
                    "body": {
                        "input": "https://example.com",
                        "lang": "en",
                        "explanation_mode": "short | detailed",
                    },
                },
            ],
            "example_curl": "curl -X POST https://api.noytrixapp.com/v1/scan -H 'Content-Type: application/json' -H 'x-api-key: YOUR_API_KEY' -d '{\"input\":\"https://example.com\",\"lang\":\"en\"}'",
            "response_fields": {
                "score": "Risk score from 0 to 100",
                "level": "safe, suspicious, danger or critical",
                "sources": "External and internal security checks",
                "evidence": "Human-readable risk evidence",
                "api.usage": "Monthly usage and limits",
                "ai_explanation_result": "AI-generated human-readable explanation with structured short/details/risks/actions fields",
            },
        }

    @router.get("/v1/me")
    async def b2b_v1_me(request: Request):
        api_key = require_b2b_api_key(request)
        used = int(api_key.get("requests_used_month") or 0)
        limit = int(api_key.get("monthly_limit") or 0)

        return {
            "ok": True,
            "api": {
                "version": "v1",
                "status": api_key.get("status"),
                "plan": api_key.get("plan_code"),
                "key_prefix": api_key.get("key_prefix"),
                "owner_email": api_key.get("owner_email"),
                "company_name": api_key.get("company_name"),
                "rate_limit_per_minute": api_key.get("rate_limit_per_minute"),
                "expires_at": api_key.get("expires_at"),
                "usage": {
                    "month": api_current_month(),
                    "used": used,
                    "limit": limit,
                    "left": max(limit - used, 0) if limit > 0 else None,
                },
            },
        }

    @router.post("/v1/scan")
    async def b2b_v1_scan(request: Request, payload: B2BScanIn = Body(...)):
        started = time.time()
        ip = api_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        api_key = require_b2b_api_key(request)

        target = (payload.input or "").strip()
        selected_lang = normalize_lang(payload.lang or "en")

        if not target:
            api_log_usage(
                api_key_id=api_key["id"],
                key_prefix=api_key["key_prefix"],
                status_code=400,
                latency_ms=int((time.time() - started) * 1000),
                ip=ip,
                user_agent=user_agent,
                error_code="missing_input",
            )
            raise HTTPException(status_code=400, detail={"error": "missing_input", "message": "Input is required."})

        try:
            data = await security_analyze_core({
                "input": target,
                "lang": selected_lang,
                "user_id": payload.user_id or f"api_key_{api_key['id']}",
                "is_pro": True,
                "internal_only": bool(payload.internal_only or (internal_mode and not bool(payload.external_check))),
                "external_check": bool(payload.external_check),
            })
            data = attach_legacy_fields(data, selected_lang)
            data = attach_ux_risk_blocks(data, selected_lang)

            try:
                judge_context = build_ai_explanation_context(data)
                data["ai_security_judge"] = await generate_ai_security_judge(judge_context, selected_lang)
                judge = data.get("ai_security_judge") or {}
                judge_delta = int(judge.get("risk_delta") or 0)

                if judge.get("available") and judge_delta > 0:
                    data["score_before_ai_judge"] = int(data.get("score") or 0)
                    data["score"] = min(100, int(data.get("score") or 0) + judge_delta)

                    if data["score"] >= 90:
                        data["level"] = "critical"
                        data["verdict"] = "critical"
                    elif data["score"] >= 70:
                        data["level"] = "high"
                        data["verdict"] = "high"
                    elif data["score"] >= 40:
                        data["level"] = "suspicious"
                        data["verdict"] = "suspicious"

                    data.setdefault("sources", []).append({
                        "name": "ai_security_judge",
                        "source": "ai_security_judge",
                        "status": data.get("level"),
                        "verdict": judge.get("level"),
                        "details": judge,
                        "evidence": [{
                            "code": "ai_security_judge",
                            "severity": judge.get("score"),
                            "text": judge.get("reasoning") or "AI security judge added risk signal.",
                        }],
                        "status_text": "AI judge",
                    })
                    data.setdefault("evidence", []).append({
                        "source": "ai_security_judge",
                        "code": "ai_security_judge",
                        "severity": judge.get("score"),
                        "text": judge.get("reasoning") or "AI security judge added risk signal.",
                    })

                data["ai_explanation_context"] = build_ai_explanation_context(data)
                data["ai_explanation_result"] = await generate_ai_security_explanation(
                    data,
                    selected_lang,
                    payload.explanation_mode or "detailed",
                )
                data["ai_explanation"] = (
                    (data.get("ai_explanation_result") or {}).get("text")
                    or data.get("ai_explanation")
                    or ""
                )
            except Exception as exc:
                data["ai_explanation_result"] = {
                    "available": False,
                    "reason": str(exc)[:300],
                    "text": "",
                }

            b2b_increment_usage(api_key["id"], ip)

            used_after = int(api_key.get("requests_used_month") or 0) + 1
            limit = int(api_key.get("monthly_limit") or 0)
            data["api"] = {
                "version": "v1",
                "plan": api_key.get("plan_code"),
                "key_prefix": api_key.get("key_prefix"),
                "usage": {
                    "month": api_current_month(),
                    "used": used_after,
                    "limit": limit,
                    "left": max(limit - used_after, 0) if limit > 0 else None,
                },
            }

            api_log_usage(
                api_key_id=api_key["id"],
                key_prefix=api_key["key_prefix"],
                input_value=target[:500],
                input_kind=data.get("kind"),
                verdict_level=data.get("level"),
                score=data.get("score"),
                status_code=200,
                latency_ms=int((time.time() - started) * 1000),
                ip=ip,
                user_agent=user_agent,
            )
            return data

        except HTTPException:
            raise
        except Exception as exc:
            print("[b2b-api] /v1/scan fatal:", exc)
            api_log_usage(
                api_key_id=api_key["id"],
                key_prefix=api_key["key_prefix"],
                input_value=target[:500],
                status_code=500,
                latency_ms=int((time.time() - started) * 1000),
                ip=ip,
                user_agent=user_agent,
                error_code="scan_failed",
            )
            raise HTTPException(status_code=500, detail={"error": "scan_failed", "message": "Scan failed."})

    @router.post("/v1/security/analyze")
    async def security_analyze(request: Request, payload: dict = Body(...)):
        return await security_analyze_core(payload)

    return router
