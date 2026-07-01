from typing import Any, Dict, List


CANONICAL_TRUSTED_PROTOCOL_CATEGORIES = {
    "dex_router",
    "permit_manager",
    "bridge",
    "marketplace",
    "lending_protocol",
    "staking_protocol",
}


def apply_anti_false_positive_layer(verdict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Production anti-false-positive layer.
    It never marks unsafe things as safe.
    It only reduces over-aggressive confidence when trusted context exists.
    """
    out = dict(verdict or {})
    raw = out.get("raw") or {}
    permissions = out.get("permissions_summary") or raw.get("permissions_summary") or {}
    contract_identity = out.get("contract_identity") or raw.get("contract_identity") or (raw.get("details") or {}).get("contract_identity") or {}
    evidence: List[Dict[str, Any]] = list(out.get("evidence") or [])
    notes: List[str] = []

    spender = permissions.get("spender")
    spender_trust = (
        permissions.get("spender_trust")
        or permissions.get("trust")
        or raw.get("spender_trust")
        or contract_identity.get("trust")
        or ""
    )
    spender_category = (
        permissions.get("spender_category")
        or raw.get("spender_category")
        or contract_identity.get("category")
        or ""
    )

    level = str(out.get("level") or "").lower()
    confidence = int(out.get("confidence_score") or out.get("confidence") or 0)

    trusted_context = (
        str(spender_trust).lower() == "trusted"
        or str(spender_category).lower() in CANONICAL_TRUSTED_PROTOCOL_CATEGORIES
    )

    high_risk_levels = {"high", "critical"}

    if trusted_context and level in high_risk_levels:
        evidence.append({
            "source": "anti_false_positive",
            "code": "trusted_protocol_context",
            "severity": 0,
            "text": "Trusted protocol context detected. Risk is not automatically downgraded, but confidence is capped unless stronger malicious evidence exists.",
        })
        notes.append("trusted_protocol_context")

        strong_bad_evidence = any(
            int(e.get("severity") or 0) >= 80
            for e in evidence
            if isinstance(e, dict)
        )

        if not strong_bad_evidence:
            confidence = min(confidence, 70)

    out["confidence"] = confidence
    out["confidence_score"] = confidence
    out["evidence"] = evidence
    out["anti_false_positive"] = {
        "applied": bool(notes),
        "notes": notes,
        "trusted_context": bool(trusted_context),
        "spender": spender,
        "spender_trust": spender_trust or None,
        "spender_category": spender_category or None,
        "contract_identity": contract_identity or None,
    }

    return out
