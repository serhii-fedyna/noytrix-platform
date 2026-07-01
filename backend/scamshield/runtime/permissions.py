from typing import Any, Dict


def build_permissions_summary(tx_decoded: Dict[str, Any], spender_rep: Dict[str, Any] | None, lang: str = "en") -> Dict[str, Any]:
    unlimited = bool(tx_decoded.get("unlimited"))
    can_spend = bool(tx_decoded.get("can_spend"))

    if lang == "ru":
        summary = (
            "Эта транзакция даёт spender разрешение списывать токены без лимита." if unlimited
            else "Эта транзакция даёт разрешение на списание токенов." if can_spend
            else "Это обычный transfer без approve-разрешения."
        )
    else:
        summary = (
            "This transaction gives the spender unlimited token spending permission." if unlimited
            else "This transaction grants token spending permission." if can_spend
            else "This is a transfer without approval permission."
        )

    return {
        "can_spend": can_spend,
        "unlimited": unlimited,
        "tokens": tx_decoded.get("tokens") or [],
        "token_contract": tx_decoded.get("token_contract"),
        "token_symbol": tx_decoded.get("token_symbol"),
        "token_chain": tx_decoded.get("token_chain"),
        "spend_limit": "unlimited" if unlimited else (tx_decoded.get("amount_raw") or "unknown"),
        "spender": tx_decoded.get("spender"),
        "spender_reputation": spender_rep,
        "spender_label": (spender_rep or {}).get("label"),
        "spender_trust": (spender_rep or {}).get("trust"),
        "spender_risk": (spender_rep or {}).get("risk"),
        "spender_category": (spender_rep or {}).get("category"),
        "spender_verified": bool((spender_rep or {}).get("verified")),
        "spender_protocol": (spender_rep or {}).get("protocol"),
        "spender_source": (spender_rep or {}).get("source"),
        "spender_first_seen": (spender_rep or {}).get("first_seen"),
        "spender_last_seen": (spender_rep or {}).get("last_seen"),
        "revoke_difficulty": "high" if unlimited else "medium",
        "summary": summary,
    }
