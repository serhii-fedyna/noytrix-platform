from __future__ import annotations

from typing import Any, Dict


RUNTIME_CONTRACT_VERSION = "1.0"


def normalize_runtime_payload(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = dict(payload or {})
    source = str(
        payload.get("source")
        or payload.get("client")
        or payload.get("platform")
        or payload.get("provider")
        or "extension"
    ).strip().lower()

    if source in {"ios", "android", "react_native", "expo", "app"}:
        source = "mobile"
    elif "mobile" in source:
        source = "mobile"
    elif "extension" in source or source in {"chrome", "browser"}:
        source = "extension"

    method = str(payload.get("method") or payload.get("rpc_method") or payload.get("type") or "").strip()
    data = payload.get("data")
    typed_data = payload.get("typedData") or payload.get("typed_data")
    tx = payload.get("tx") or payload.get("transaction") or {}
    if not isinstance(tx, dict):
        tx = {}

    domain = str(payload.get("domain") or payload.get("host") or payload.get("origin") or "").strip()
    url = str(payload.get("url") or payload.get("page_url") or payload.get("input") or payload.get("target") or "").strip()
    wallet = str(payload.get("wallet") or payload.get("from") or tx.get("from") or "").strip()
    spender = str(payload.get("spender") or payload.get("approveSpender") or payload.get("approve_spender") or "").strip()

    if not data and isinstance(tx, dict):
        data = tx.get("data") or tx.get("input")

    return {
        "source": source,
        "method": method,
        "domain": domain,
        "url": url,
        "wallet": wallet,
        "spender": spender,
        "data": data,
        "typed_data": typed_data,
        "transaction": tx,
        "flags": payload.get("flags") or [],
        "raw": payload,
    }


def build_runtime_contract(payload: Dict[str, Any], verdict: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_runtime_payload(payload)
    permissions = verdict.get("permissions_summary") or {}
    simulation = verdict.get("simulation") or {}
    behavior = verdict.get("runtime_behavior") or {}
    execution_graph = verdict.get("execution_graph") or {}
    recursive_graph = verdict.get("recursive_execution_graph") or {}
    campaign = verdict.get("campaign") or {}
    wallet_profile = verdict.get("wallet_profile") or {}
    signature_simulation = verdict.get("signature_simulation") or {}
    multi_chain = verdict.get("multi_chain_intelligence") or {}
    ai_investigation = verdict.get("ai_investigation") or {}

    score = int(verdict.get("score") or verdict.get("runtime_severity") or 0)
    level = str(verdict.get("level") or "unknown").lower()
    should_block = level in {"critical", "danger", "high"} or bool(permissions.get("unlimited")) or score >= 70
    should_warn = should_block or level in {"suspicious", "warning", "medium"} or score >= 30

    return {
        "version": RUNTIME_CONTRACT_VERSION,
        "source": normalized["source"],
        "method": normalized["method"],
        "domain": normalized["domain"],
        "url": normalized["url"],
        "wallet": normalized["wallet"],
        "spender": permissions.get("spender") or normalized["spender"],
        "level": level,
        "score": score,
        "should_warn": should_warn,
        "should_block": should_block,
        "reason_codes": [
            item.get("code")
            for item in (verdict.get("evidence") or [])
            if isinstance(item, dict) and item.get("code")
        ][:10],
        "permissions": {
            "can_spend": bool(permissions.get("can_spend")),
            "unlimited": bool(permissions.get("unlimited")),
            "tokens": permissions.get("tokens") or [],
            "spend_limit": permissions.get("spend_limit"),
            "revoke_difficulty": permissions.get("revoke_difficulty"),
            "summary": permissions.get("summary") or "",
        },
        "simulation": {
            "available": bool(simulation.get("available")),
            "summary": simulation.get("summary") or verdict.get("what_can_happen") or "",
            "worst_case": verdict.get("worst_case") or simulation.get("worst_case") or "",
            "estimated_wallet_exposure_usd": simulation.get("estimated_wallet_exposure_usd"),
            "loss_scenarios": simulation.get("loss_scenarios") or [],
            "recommended_actions": simulation.get("recommended_actions") or [],
        },
        "runtime_behavior": behavior,
        "signature_simulation": signature_simulation,
        "execution_graph": {
            "available": bool(execution_graph) or bool(recursive_graph),
            "direct": execution_graph,
            "recursive": recursive_graph,
            "attack_chain_score": recursive_graph.get("attack_chain_score"),
            "attack_chain_level": recursive_graph.get("attack_chain_level"),
        },
        "campaign": campaign,
        "wallet_profile": wallet_profile,
        "multi_chain_intelligence": multi_chain,
        "ai_investigation": {
            "available": bool(ai_investigation.get("available")),
            "engine": ai_investigation.get("engine"),
            "primary_hypothesis": ai_investigation.get("primary_hypothesis"),
            "confidence": ai_investigation.get("confidence"),
            "evidence_links": ai_investigation.get("evidence_links") or [],
            "recommended_actions": ai_investigation.get("recommended_actions") or [],
        },
    }
