from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from typing import Any

GOPLUS_BASE_URL = "https://api.gopluslabs.io/api/v1"


def _flag(value: Any) -> bool | None:
    if value in ("1", 1, True):
        return True
    if value in ("0", 0, False):
        return False
    return None


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def normalize_goplus_token(record: dict[str, Any], address: str, chain_id: str) -> dict[str, Any]:
    """Normalize facts without interpreting a missing/zero flag as proof of safety."""
    record = record if isinstance(record, dict) else {}
    findings: list[dict[str, Any]] = []
    is_honeypot = _flag(record.get("is_honeypot"))
    cannot_sell_all = _flag(record.get("cannot_sell_all"))
    sell_tax = _number(record.get("sell_tax"))
    buy_tax = _number(record.get("buy_tax"))

    if is_honeypot is True:
        findings.append({
            "code": "goplus_honeypot_confirmed",
            "severity": 95,
            "confidence": 90,
            "confirmed": True,
            "hard_evidence": True,
            "value": True,
            "method": "independent_token_security_provider",
            "text": "GoPlus explicitly identified the token as a honeypot.",
        })
    if cannot_sell_all is True:
        findings.append({
            "code": "goplus_cannot_sell_all",
            "severity": 90,
            "confidence": 88,
            "confirmed": True,
            "hard_evidence": True,
            "value": True,
            "method": "independent_token_security_provider",
            "text": "GoPlus reports that holders may be unable to sell their full balance.",
        })
    if sell_tax is not None and sell_tax >= 50:
        findings.append({
            "code": "goplus_extreme_sell_tax",
            "severity": 80,
            "confidence": 82,
            "confirmed": True,
            "hard_evidence": True,
            "value": sell_tax,
            "method": "independent_token_security_provider",
            "text": "GoPlus reports an extreme sell tax.",
        })

    controls = {
        key: _flag(record.get(field))
        for key, field in {
            "open_source": "is_open_source",
            "proxy": "is_proxy",
            "mintable": "is_mintable",
            "hidden_owner": "hidden_owner",
            "owner_can_change_balance": "owner_change_balance",
            "ownership_can_be_reclaimed": "can_take_back_ownership",
            "self_destruct": "selfdestruct",
            "external_call": "external_call",
            "transfer_pausable": "transfer_pausable",
            "blacklist": "is_blacklisted",
            "whitelist": "is_whitelisted",
            "trading_cooldown": "trading_cooldown",
            "slippage_modifiable": "slippage_modifiable",
        }.items()
    }
    has_data = bool(record)
    status = "malicious" if findings else ("observed" if has_data else "no_data")
    return {
        "address": address.lower(),
        "chain_id": str(chain_id),
        "assessment_status": "available" if has_data else "insufficient_data",
        "status": status,
        "is_honeypot": is_honeypot,
        "cannot_sell_all": cannot_sell_all,
        "buy_tax": buy_tax,
        "sell_tax": sell_tax,
        "holder_count": record.get("holder_count"),
        "holders": record.get("holders") if isinstance(record.get("holders"), list) else None,
        "lp_holder_count": record.get("lp_holder_count"),
        "lp_holders": record.get("lp_holders") if isinstance(record.get("lp_holders"), list) else None,
        "owner": record.get("owner_address") or None,
        "creator": record.get("creator_address") or None,
        "token_name": record.get("token_name") or None,
        "token_symbol": record.get("token_symbol") or None,
        "total_supply": record.get("total_supply"),
        "controls": controls,
        "trust_list": _flag(record.get("trust_list")),
        "doubt_list": _flag(record.get("doubt_list")),
        "findings": findings,
    }


async def check_goplus_token(address: str, chain_id: str | None) -> dict[str, Any]:
    import httpx

    if not chain_id:
        return {
            "name": "goplus",
            "status": "no_data",
            "verdict": "unknown",
            "details": {"address": address, "reason": "network_not_resolved"},
            "evidence": [],
        }

    headers = {"Accept": "application/json", "User-Agent": "Noytrix-Security/1.0"}
    token = (os.getenv("GOPLUS_API_TOKEN") or os.getenv("GOPLUS_API_KEY") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{GOPLUS_BASE_URL}/token_security/{chain_id}"
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as client:
            response = await client.get(url, params={"contract_addresses": address}, headers=headers)
        if response.status_code == 429:
            status = "quota"
        elif response.status_code in {401, 403}:
            status = "invalid_key"
        elif response.status_code >= 500:
            status = "source_unavailable"
        elif response.status_code != 200:
            status = "error"
        else:
            status = None
        if status:
            return {
                "name": "goplus", "status": status, "verdict": "unknown",
                "details": {"address": address, "chain_id": chain_id, "status_code": response.status_code},
                "evidence": [],
            }

        payload = response.json()
        if str(payload.get("code")) != "1":
            return {
                "name": "goplus", "status": "no_data", "verdict": "unknown",
                "details": {"address": address, "chain_id": chain_id, "provider_code": payload.get("code")},
                "evidence": [],
            }
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        exact = next((value for key, value in result.items() if str(key).lower() == address.lower()), None)
        if not isinstance(exact, dict):
            return {
                "name": "goplus", "status": "no_data", "verdict": "unknown",
                "details": {"address": address, "chain_id": chain_id, "reason": "exact_contract_not_returned"},
                "evidence": [],
            }
        normalized = normalize_goplus_token(exact, address, chain_id)
        return {
            "name": "goplus",
            "status": normalized["status"],
            "verdict": "malicious" if normalized["status"] == "malicious" else "unknown",
            "details": normalized,
            "evidence": normalized["findings"],
        }
    except httpx.TimeoutException:
        return {"name": "goplus", "status": "timeout", "verdict": "unknown", "details": {"address": address, "chain_id": chain_id}, "evidence": []}
    except (httpx.HTTPError, ValueError) as exc:
        return {"name": "goplus", "status": "source_unavailable", "verdict": "unknown", "details": {"address": address, "chain_id": chain_id, "error_type": type(exc).__name__}, "evidence": []}
