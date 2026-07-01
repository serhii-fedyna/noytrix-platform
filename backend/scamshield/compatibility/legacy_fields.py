def attach_legacy_fields(data: dict, lang: str = "en") -> dict:
    """
    Compatibility layer.
    Keeps old app/extension fields alive while backend moves to clean architecture.
    Do not remove until mobile app + extension stop depending on these keys.
    """
    if not isinstance(data, dict):
        return data

    verdict = data.get("verdict_localized") or data.get("verdict_en") or data.get("verdict") or "Unknown"

    data.setdefault("ai_verdict", verdict)
    data.setdefault("ai_verdict_en", data.get("verdict_en", verdict))
    data.setdefault("ai_verdict_ru", data.get("verdict_ru", verdict))
    data.setdefault("ai_verdict_localized", verdict)

    data.setdefault("honeypot_verdict", None)
    data.setdefault("honeypot_status", None)
    data.setdefault("honeypot_risk", None)

    data.setdefault("risk_reasons", [])
    data.setdefault("permissions_summary", {
        "can_spend": False,
        "unlimited": False,
        "tokens": [],
        "spend_limit": None,
        "revoke_difficulty": "unknown",
        "summary": "",
    })

    return data
