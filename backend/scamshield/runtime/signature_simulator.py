from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple


MAX_UINT_256 = 2**256 - 1
MAX_UINT_256_STR = str(MAX_UINT_256)
RE_EVM_ADDRESS = re.compile(r"^0x[a-fA-F0-9]{40}$")


def _safe_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value or {}, ensure_ascii=False, sort_keys=True).lower()
    except Exception:
        return str(value or "").lower()


def _walk(value: Any, path: str = "") -> List[Tuple[str, Any]]:
    out: List[Tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = f"{path}.{key}" if path else str(key)
            out.append((next_path, item))
            out.extend(_walk(item, next_path))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            next_path = f"{path}[{idx}]"
            out.append((next_path, item))
            out.extend(_walk(item, next_path))
    return out


def _first_by_keys(value: Any, names: set[str]) -> Any:
    for path, item in _walk(value):
        key = path.split(".")[-1].split("[")[0].lower()
        if key in names and item not in (None, ""):
            return item
    return None


def _all_addresses(value: Any) -> List[str]:
    found: List[str] = []
    for _, item in _walk(value):
        if isinstance(item, str) and RE_EVM_ADDRESS.match(item.strip()):
            found.append(item.strip())
    return sorted(dict.fromkeys(found))


def _amount_is_unlimited(amount: Any) -> bool:
    if amount is None:
        return False
    text = str(amount).strip().lower()
    if text in {"unlimited", "max", "infinite", MAX_UINT_256_STR}:
        return True
    try:
        return int(text, 0) >= MAX_UINT_256
    except Exception:
        return False


def _method_family(method: str, typed: Any, message: Any) -> str:
    method_l = str(method or "").lower()
    text = _json_text({"typed": typed, "message": message})
    primary = ""
    if isinstance(typed, dict):
        primary = str(typed.get("primaryType") or "").lower()

    if "permit2" in text or "permit2" in primary:
        return "permit2"
    if "permit" in text or primary == "permit":
        return "permit"
    if any(x in text for x in ["seaport", "fulfill", "consideration", "offerer", "zonehash"]):
        return "marketplace_order"
    if any(x in text for x in ["delegate", "delegation", "sessionkey", "session key"]):
        return "delegation"
    if "signtypeddata" in method_l or "eip712" in method_l:
        return "typed_data"
    if "personal_sign" in method_l or "signmessage" in method_l:
        return "personal_sign"
    if method_l == "eth_sign":
        return "raw_eth_sign"
    if "sendtransaction" in method_l or "transaction" in method_l:
        return "transaction"
    return "signature"


def _add_signal(signals: List[Dict[str, Any]], code: str, severity: int, text: str) -> None:
    signals.append({
        "code": code,
        "severity": max(0, min(100, int(severity))),
        "text": text,
    })


def simulate_signature(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = dict(payload or {})
    method = str(payload.get("method") or payload.get("rpc_method") or payload.get("type") or "").strip()
    typed = _safe_json(payload.get("typedData") or payload.get("typed_data") or payload.get("data") or {})
    message = _safe_json(payload.get("message") or payload.get("params") or typed)

    if isinstance(typed, dict):
        message = typed.get("message") or message
        domain = typed.get("domain") or {}
        primary_type = typed.get("primaryType")
    else:
        domain = {}
        primary_type = None

    family = _method_family(method, typed, message)
    text = _json_text({"payload": payload, "typed": typed, "message": message})
    signals: List[Dict[str, Any]] = []

    spender = (
        payload.get("spender")
        or _first_by_keys(message, {"spender", "operator", "delegate", "delegatee", "to"})
        or _first_by_keys(typed, {"spender", "operator", "delegate", "delegatee", "to"})
    )
    owner = payload.get("wallet") or payload.get("from") or _first_by_keys(message, {"owner", "from", "account"})
    token = payload.get("token") or _first_by_keys(message, {"token", "tokenaddress", "verifyingcontract"})
    amount = _first_by_keys(message, {"value", "amount", "allowed", "limit", "quantity", "numerator"})
    deadline = _first_by_keys(message, {"deadline", "expiration", "expiry", "sigdeadline", "endtime"})
    nonce = _first_by_keys(message, {"nonce", "salt", "counter"})
    addresses = _all_addresses({"payload": payload, "typed": typed, "message": message})

    if family in {"permit", "permit2"}:
        _add_signal(signals, f"{family}_signature_permission", 90 if family == "permit2" else 86, "Signature can grant token spending permission.")
    elif family == "marketplace_order":
        _add_signal(signals, "marketplace_order_signature", 72, "Signature appears to authorize a marketplace/order action.")
    elif family == "delegation":
        _add_signal(signals, "delegated_wallet_permission", 82, "Signature appears to delegate account or session authority.")
    elif family == "raw_eth_sign":
        _add_signal(signals, "raw_eth_sign_blind_signature", 78, "eth_sign is a raw signature method and can be dangerous if the message is opaque.")
    elif family == "personal_sign":
        _add_signal(signals, "personal_sign_message", 35, "Wallet message signature detected.")
    elif family == "typed_data":
        _add_signal(signals, "typed_data_signature", 45, "EIP-712 typed signature detected.")

    if spender:
        _add_signal(signals, "signature_spender_detected", 72, "Signature contains a spender/operator/delegate address.")
    if amount is not None:
        _add_signal(signals, "signature_amount_limit_detected", 55, "Signature contains an amount or spending limit.")
    if _amount_is_unlimited(amount) or any(x in text for x in ["unlimited", "maxuint", "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"]):
        _add_signal(signals, "signature_unlimited_allowance", 94, "Signature appears to grant unlimited or max spending permission.")
    if deadline:
        _add_signal(signals, "signature_deadline_detected", 25, "Signature includes a deadline or expiration.")
    if any(x in text for x in ["approve", "setapprovalforall", "transferfrom"]):
        _add_signal(signals, "signature_asset_transfer_terms", 85, "Signature text references approval or asset transfer behavior.")
    if any(x in text for x in ["seed phrase", "private key", "recovery phrase"]):
        _add_signal(signals, "signature_secret_phrase_request", 100, "Signature content asks for wallet secrets.")

    score = max([int(s["severity"]) for s in signals] or [0])
    if family in {"permit", "permit2"} and spender:
        score = max(score, 94)
    if family == "raw_eth_sign" and len(str(message)) > 200:
        score = max(score, 84)

    level = "safe"
    if score >= 90:
        level = "critical"
    elif score >= 70:
        level = "danger"
    elif score >= 40:
        level = "suspicious"
    elif score > 0:
        level = "low"

    can_spend = family in {"permit", "permit2"} or bool(spender and score >= 70)
    unlimited = any(s["code"] == "signature_unlimited_allowance" for s in signals)

    simulation = {
        "available": True,
        "signature_family": family,
        "primary_type": primary_type,
        "domain": domain,
        "owner": owner,
        "spender": spender,
        "token": token,
        "amount": "unlimited" if unlimited else amount,
        "deadline": deadline,
        "nonce": nonce,
        "addresses": addresses[:20],
        "can_authorize_spending": can_spend,
        "can_move_assets_later": bool(can_spend and (unlimited or family in {"permit", "permit2"})),
        "requires_onchain_revoke": bool(can_spend),
        "worst_case": (
            "A malicious spender can use this signature to move approved assets without another wallet popup."
            if can_spend else
            "The signature can prove wallet ownership or authorize app-specific actions."
        ),
        "recommended_actions": [
            "Reject the signature if the site, spender, or purpose is unknown.",
            "Verify spender and token before signing.",
            "Revoke allowance immediately if this was signed on a suspicious site.",
        ] if can_spend else [
            "Only sign messages on domains you trust.",
            "Check that the message does not request secrets or asset permissions.",
        ],
    }

    return {
        "available": True,
        "method": method,
        "family": family,
        "score": score,
        "level": level,
        "signals": sorted(signals, key=lambda x: int(x.get("severity") or 0), reverse=True),
        "simulation": simulation,
        "permissions_summary": {
            "can_spend": can_spend,
            "unlimited": unlimited,
            "spender": spender,
            "tokens": [str(token)] if token else [],
            "token_contract": token,
            "spend_limit": "unlimited" if unlimited else (str(amount) if amount is not None else None),
            "revoke_difficulty": "high" if can_spend else "low",
            "summary": (
                "This signature can authorize future token spending."
                if can_spend else
                "This signature does not clearly grant token spending permission."
            ),
        },
    }
