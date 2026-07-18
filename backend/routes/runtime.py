from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from scamshield.ai.explainer import build_ai_explanation_context, generate_ai_security_explanation
from scamshield.intelligence.scam_family import classify_scam_family
from scamshield.runtime.behavior import analyze_transaction_behavior
from scamshield.runtime.contract import build_runtime_contract, normalize_runtime_payload
from scamshield.runtime.drain_simulator import simulate_wallet_drain
from scamshield.runtime.execution_graph import build_execution_graph, build_recursive_execution_graph


def _is_signature_runtime_method(method: str) -> bool:
    method = str(method or "").lower()
    return any(x in method for x in [
        "signtypeddata",
        "personal_sign",
        "eth_sign",
        "signmessage",
        "sign_typed",
        "wallet_sign",
    ])


def create_runtime_router(
    normalize_lang: Callable[[str | None], str],
    security_analyze_core: Callable[[dict], Any],
    analyze_typed_signature_payload: Callable[[dict], dict],
    track_spender_runtime_event: Callable,
    auto_escalate_spender_reputation: Callable,
    update_drainer_campaign_for_spender: Callable,
    get_campaign_for_spender: Callable,
    build_runtime_simulation: Callable[[dict], dict],
    update_wallet_risk_profile: Callable[[str | None, dict], dict | None],
    attach_multichain_fields: Callable[[dict, str | None, dict], dict],
    attach_ai_investigation_fields: Callable[[dict], dict],
    internal_mode: bool,
) -> APIRouter:
    router = APIRouter()

    @router.post("/runtime/analyze")
    async def runtime_analyze(payload: dict = Body(...)):
        runtime_payload = normalize_runtime_payload(payload)
        runtime_data = str(runtime_payload.get("data") or "").strip()
        runtime_input = str(
            payload.get("input")
            or payload.get("target")
            or runtime_payload.get("url")
            or runtime_payload.get("domain")
            or ""
        ).strip()

        target = runtime_data if runtime_data.startswith("0x") or "|" in runtime_data else runtime_input
        lang = normalize_lang(str(payload.get("lang") or "en"))
        method = str(payload.get("method") or "").lower()

        if _is_signature_runtime_method(method):
            data = analyze_typed_signature_payload(payload)
        else:
            if not target:
                raise HTTPException(status_code=400, detail={"error": "missing_input"})

            data = await security_analyze_core({
                "input": target,
                "lang": lang,
                "user_id": "runtime_extension",
                "is_pro": True,
                "internal_only": bool(internal_mode and not bool(payload.get("external_check") or payload.get("externalCheck"))),
            })

        runtime_spender = (
            data.get("permissions_summary", {}).get("spender")
            or payload.get("spender")
        )
        runtime_unlimited = bool(
            data.get("permissions_summary", {}).get("unlimited")
        ) if data.get("permissions_summary") else bool(payload.get("approve_unlimited"))
        runtime_flags = (data.get("drainer") or {}).get("flags") or []

        if runtime_unlimited:
            permissions = data.get("permissions_summary") or {}
            if not isinstance(permissions, dict):
                permissions = {}
            permissions.setdefault("can_spend", True)
            permissions.setdefault("unlimited", True)
            permissions.setdefault("spender", runtime_spender)
            permissions.setdefault("spend_limit", "unlimited")
            permissions.setdefault("revoke_difficulty", "high")
            permissions.setdefault("summary", "This wallet action can grant unlimited token spending permission.")
            data["permissions_summary"] = permissions
            spender_trust = str(permissions.get("spender_trust") or permissions.get("spender_trust_level") or "").lower()
            if spender_trust not in {"trusted", "verified", "safe"} and int(data.get("score") or 0) < 85:
                data["score"] = 92
                data["runtime_severity"] = 92
                data["heuristics_score"] = max(92, int(data.get("heuristics_score") or 0))
                data["level"] = "critical"
                data["normalized_level"] = "critical"
                data["risk_type"] = data.get("risk_type") or "unlimited_approval_to_unknown_spender"
                data["confirmed_red_flag"] = True
                evidence = data.setdefault("evidence", [])
                if isinstance(evidence, list):
                    evidence.append({
                        "source": "runtime_extension",
                        "code": "unlimited_approval_to_unknown_spender",
                        "severity": 92,
                        "text": "The wallet request can grant unlimited token spending permission to an unverified spender.",
                        "hard_evidence": True,
                    })

        try:
            raw_data = data.get("raw") or {}
            raw_details = raw_data.get("details") or {}
            runtime_behavior = analyze_transaction_behavior(
                raw_details.get("tx_decoded")
                or raw_details.get("transaction")
                or data.get("tx_decoded")
                or data.get("transaction"),
                data.get("permissions_summary") or {},
                (data.get("permissions_summary") or {}).get("spender_reputation") or {},
                payload.get("domain"),
            )
            data["runtime_behavior"] = runtime_behavior
            tx_for_graph = (
                raw_details.get("tx_decoded")
                or raw_details.get("transaction")
                or data.get("tx_decoded")
                or data.get("transaction")
            )

            data["execution_graph"] = build_execution_graph(tx_for_graph)
            data["recursive_execution_graph"] = build_recursive_execution_graph(str(payload.get("data") or payload.get("input") or ""))

            graph_score = int((data.get("recursive_execution_graph") or {}).get("attack_chain_score") or 0)
            graph_level = str((data.get("recursive_execution_graph") or {}).get("attack_chain_level") or "").lower()

            if graph_score > int(data.get("score") or 0):
                data["score"] = graph_score
                data["runtime_severity"] = graph_score
                data["heuristics_score"] = graph_score

            if graph_level in {"high", "critical"}:
                data["level"] = graph_level
                data["normalized_level"] = graph_level
                data["risk_type"] = data.get("risk_type") or "execution_attack_chain"
                data["confirmed_red_flag"] = graph_level == "critical" or bool(data.get("confirmed_red_flag"))

            data["wallet_drain_simulation"] = simulate_wallet_drain(
                raw_details.get("tx_decoded") or {},
                data.get("permissions_summary") or {},
                data.get("runtime_behavior") or {},
                data.get("recursive_execution_graph") or {},
            )
            data["ai_explanation_context"] = build_ai_explanation_context(data)
        except Exception as e:
            data["runtime_behavior_error"] = str(e)

        track_spender_runtime_event(
            runtime_spender,
            payload.get("domain"),
            payload.get("method"),
            data.get("level"),
            runtime_unlimited,
            runtime_flags,
        )

        auto_escalate_spender_reputation(runtime_spender)
        update_drainer_campaign_for_spender(runtime_spender)

        runtime_campaign = get_campaign_for_spender(runtime_spender)
        if runtime_campaign:
            data["campaign"] = runtime_campaign

        data["simulation"] = build_runtime_simulation(data)

        runtime_wallet = payload.get("wallet") or payload.get("from")
        wallet_profile = update_wallet_risk_profile(runtime_wallet, data)
        if wallet_profile:
            data["wallet_profile"] = wallet_profile

        data = attach_multichain_fields(
            data,
            runtime_wallet or runtime_spender or target or runtime_payload.get("url") or runtime_payload.get("domain"),
            {
                "chain": payload.get("chain") or payload.get("network"),
                "chainId": payload.get("chainId") or payload.get("chain_id"),
                "kind": data.get("kind") or "runtime_web3",
            },
        )
        data = attach_ai_investigation_fields(data)
        data["runtime_contract"] = build_runtime_contract(payload, data)
        data["runtime"] = {
            "source": runtime_payload.get("source") or "extension",
            "method": payload.get("method"),
            "domain": payload.get("domain"),
            "provider": payload.get("provider"),
            "flags": payload.get("flags") or [],
            "spender": runtime_spender,
            "contract_version": data["runtime_contract"].get("version"),
        }

        details = data.setdefault("details", {})
        if isinstance(details, dict):
            details["runtime_contract"] = data["runtime_contract"]
            details["runtime_context"] = {
                "source": data["runtime"].get("source"),
                "method": data["runtime"].get("method"),
                "domain": data["runtime"].get("domain"),
                "wallet": runtime_payload.get("wallet"),
                "spender": runtime_spender,
                "should_warn": data["runtime_contract"].get("should_warn"),
                "should_block": data["runtime_contract"].get("should_block"),
            }
            internal_verdict = details.get("internal_verdict")
            if isinstance(internal_verdict, dict):
                internal_verdict["runtime_context"] = details["runtime_context"]
            else:
                details["internal_verdict"] = {
                    "engine": "noytrix_runtime_verdict_core",
                    "version": "1.0",
                    "authority": "internal",
                    "target": target or runtime_payload.get("domain") or runtime_payload.get("url"),
                    "kind": data.get("kind") or "runtime_web3",
                    "level": data.get("level"),
                    "score": data.get("score"),
                    "confidence": data.get("confidence_score") or data.get("confidence") or 50,
                    "evidence": data.get("evidence") or [],
                    "graph_context": data.get("graph") or {},
                    "reputation_context": data.get("reputation") or {},
                    "campaign_context": data.get("campaign") or {},
                    "runtime_context": details["runtime_context"],
                }
            runtime_family = classify_scam_family(data)
            data["scam_family"] = runtime_family
            data["risk_family"] = runtime_family.get("primary_family")
            if isinstance(details.get("internal_verdict"), dict):
                details["internal_verdict"]["scam_family"] = runtime_family
                details["internal_verdict"]["risk_family"] = runtime_family.get("primary_family")
            details["scam_family"] = runtime_family

        try:
            data["ai_explanation_result"] = await generate_ai_security_explanation(
                data,
                payload.get("lang") or "en",
                payload.get("explanation_mode") or "detailed",
            )
            data["ai_explanation"] = (data.get("ai_explanation_result") or {}).get("text") or data.get("ai_explanation") or ""
        except Exception as e:
            data["ai_explanation_result"] = {
                "available": False,
                "reason": str(e)[:300],
                "text": "",
            }

        return data

    @router.post("/runtime/web3/analyze")
    async def runtime_web3_analyze(payload: dict = Body(...)):
        payload = dict(payload or {})
        payload.setdefault("source", "extension")
        return await runtime_analyze(payload)

    @router.post("/mobile/runtime/analyze")
    async def mobile_runtime_analyze(payload: dict = Body(...)):
        payload = dict(payload or {})
        payload.setdefault("source", "mobile")
        return await runtime_analyze(payload)

    return router
