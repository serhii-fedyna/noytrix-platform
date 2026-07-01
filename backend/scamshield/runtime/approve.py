from typing import Any, Dict, List


def _spender_trust(spender_rep: Dict[str, Any] | None) -> str:
    return str((spender_rep or {}).get("trust") or "unknown").lower()


def _spender_risk(spender_rep: Dict[str, Any] | None) -> str:
    return str((spender_rep or {}).get("risk") or "unknown").lower()


def _spender_category(spender_rep: Dict[str, Any] | None) -> str:
    return str((spender_rep or {}).get("category") or "").lower()


def approve_runtime_severity(tx_decoded: Dict[str, Any], spender_rep: Dict[str, Any] | None) -> int:
    trust = _spender_trust(spender_rep)
    risk = _spender_risk(spender_rep)
    category = _spender_category(spender_rep)
    unlimited = bool(tx_decoded.get("unlimited"))
    is_nft_approval = str(tx_decoded.get("type") or "") == "nft_set_approval_for_all"

    if trust == "malicious" or risk == "critical":
        return 96

    if unlimited and trust == "trusted" and category in {"dex_router", "permit_manager", "marketplace", "bridge"}:
        return 38

    if unlimited and trust == "trusted":
        return 48

    if is_nft_approval and trust in {"unknown", "", "none"}:
        return 94

    if unlimited and trust in {"unknown", "", "none"}:
        return 92

    if unlimited:
        return 85

    if trust == "trusted":
        return 20

    if risk in {"high", "critical"}:
        return 80

    return 45


def approve_drain_probability(tx_decoded: Dict[str, Any], spender_rep: Dict[str, Any] | None) -> int:
    trust = _spender_trust(spender_rep)
    risk = _spender_risk(spender_rep)
    category = _spender_category(spender_rep)
    unlimited = bool(tx_decoded.get("unlimited"))
    is_nft_approval = str(tx_decoded.get("type") or "") == "nft_set_approval_for_all"

    probability = 15

    if is_nft_approval:
        probability += 55
    elif unlimited:
        probability += 45

    if trust in {"unknown", "", "none"}:
        probability += 25

    if trust == "malicious" or risk == "critical":
        probability = 98

    if risk == "high":
        probability += 25

    if trust == "trusted":
        probability -= 35

    if category in {"dex_router", "permit_manager", "marketplace", "bridge"}:
        probability -= 15

    return max(1, min(99, int(probability)))


def approve_risk_reasons(tx_decoded: Dict[str, Any], spender_rep: Dict[str, Any] | None) -> List[str]:
    trust = _spender_trust(spender_rep)
    risk = _spender_risk(spender_rep)
    category = _spender_category(spender_rep)
    reasons: List[str] = []

    if str(tx_decoded.get("type") or "") == "nft_set_approval_for_all":
        reasons.append("nft_set_approval_for_all")

    if tx_decoded.get("unlimited"):
        reasons.append("unlimited_token_approval")

    if trust == "unknown":
        reasons.append("unknown_spender")

    if trust == "malicious":
        reasons.append("known_malicious_spender")

    if risk in {"high", "critical"}:
        reasons.append("high_risk_spender_reputation")

    if trust == "trusted":
        reasons.append("trusted_spender_context")

    if category:
        reasons.append(f"spender_category:{category}")

    return reasons


def approve_risk_type(tx_decoded: Dict[str, Any], spender_rep: Dict[str, Any] | None) -> str:
    trust = _spender_trust(spender_rep)

    if trust == "malicious":
        return "confirmed_drainer_spender"

    if str(tx_decoded.get("type") or "") == "nft_set_approval_for_all":
        return "nft_collection_approval"

    if tx_decoded.get("unlimited") and trust == "unknown":
        return "unlimited_approval_to_unknown_spender"

    if tx_decoded.get("unlimited"):
        return "unlimited_approval"

    return "token_permission"


def approve_confirmed_red_flag(tx_decoded: Dict[str, Any], spender_rep: Dict[str, Any] | None) -> bool:
    trust = _spender_trust(spender_rep)
    return bool(
        trust == "malicious"
        or (tx_decoded.get("unlimited") and trust not in {"trusted"})
    )


def approve_verdict_text(tx_decoded: Dict[str, Any], spender_rep: Dict[str, Any] | None, lang: str = "en") -> dict:
    trust = _spender_trust(spender_rep)
    unlimited = bool(tx_decoded.get("unlimited"))

    if lang == "ru":
        if trust == "malicious":
            text = "Подтверждённый риск дренера"
        elif unlimited and trust == "trusted":
            text = "Высокое разрешение доверенному протоколу"
        elif unlimited and trust == "unknown":
            text = "Критический риск разрешения"
        elif unlimited:
            text = "Высокий риск разрешения"
        else:
            text = "Разрешение на списание токенов"
        return {"verdict": text}

    if trust == "malicious":
        text = "Confirmed drainer spender risk"
    elif unlimited and trust == "trusted":
        text = "High-impact permission to trusted protocol"
    elif unlimited and trust == "unknown":
        text = "Critical approval risk"
    elif unlimited:
        text = "High approval risk"
    else:
        text = "Token spending permission"

    return {"verdict": text}


def build_approve_runtime_fields(tx_decoded: Dict[str, Any], spender_rep: Dict[str, Any] | None, lang: str = "en") -> Dict[str, Any]:
    from scamshield.core.levels import normalize_level, legacy_level

    severity = approve_runtime_severity(tx_decoded, spender_rep)
    normalized = normalize_level("", severity)
    legacy = legacy_level(normalized)
    probability = approve_drain_probability(tx_decoded, spender_rep)

    return {
        "score": severity,
        "runtime_severity": severity,
        "normalized_level": normalized,
        "level": legacy,
        "risk_type": approve_risk_type(tx_decoded, spender_rep),
        "drain_probability": probability,
        "approval_risk_reasons": approve_risk_reasons(tx_decoded, spender_rep),
        "verdict_en": approve_verdict_text(tx_decoded, spender_rep, "en")["verdict"],
        "verdict_ru": approve_verdict_text(tx_decoded, spender_rep, "ru")["verdict"],
        "verdict_localized": approve_verdict_text(tx_decoded, spender_rep, lang)["verdict"],
        "confirmed_red_flag": approve_confirmed_red_flag(tx_decoded, spender_rep),
        "heuristics_score": severity,
    }
