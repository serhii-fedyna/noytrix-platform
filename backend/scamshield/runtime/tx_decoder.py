from typing import Dict, Optional


def decode_evm_tx_input(
    raw: str,
    re_evm_addr,
    known_tokens,
    evm_word_to_addr,
    evm_word_to_int,
) -> Optional[Dict]:

    x = str(raw or "").strip()

    token_contract = None
    token_symbol = None
    token_chain = None

    if "|" in x:
        left, right = x.split("|", 1)
        left = left.strip().lower()
        right = right.strip()

        if re_evm_addr.match(left):
            token_contract = left
            meta = known_tokens.get(left) or {}
            token_symbol = meta.get("symbol")
            token_chain = meta.get("chain")
            x = right

    if not x.startswith("0x"):
        return None

    h = x[2:].lower()

    if len(h) < 8:
        return None

    selector = h[:8]
    data = h[8:]

    words = [
        data[i:i+64]
        for i in range(0, len(data), 64)
        if len(data[i:i+64]) == 64
    ]

    if selector == "095ea7b3" and len(words) >= 2:
        spender = evm_word_to_addr(words[0])
        amount = evm_word_to_int(words[1])

        unlimited = amount == (2**256 - 1)

        return {
            "detected": True,
            "type": "erc20_approve",
            "method": "approve(address,uint256)",
            "selector": selector,
            "spender": spender,
            "amount_raw": str(amount) if amount is not None else None,
            "unlimited": bool(unlimited),
            "can_spend": True,
            "tokens": [token_symbol] if token_symbol else [],
            "token_contract": token_contract,
            "token_symbol": token_symbol,
            "token_chain": token_chain,
        }

    if selector == "a22cb465" and len(words) >= 2:
        operator = evm_word_to_addr(words[0])
        approved_raw = evm_word_to_int(words[1])
        approved = bool(approved_raw)

        return {
            "detected": True,
            "type": "nft_set_approval_for_all",
            "method": "setApprovalForAll(address,bool)",
            "selector": selector,
            "spender": operator,
            "operator": operator,
            "approved": approved,
            "amount_raw": "all_nfts" if approved else "revoked",
            "unlimited": bool(approved),
            "can_spend": bool(approved),
            "asset_type": "nft",
            "tokens": [token_symbol] if token_symbol else [],
            "token_contract": token_contract,
            "token_symbol": token_symbol,
            "token_chain": token_chain,
        }

    if selector in {"d505accf", "2b67b570", "30f28b7a"}:
        return {
            "detected": True,
            "type": "permit_or_permit2",
            "method": "permit / Permit2 permission",
            "selector": selector,
            "unlimited": True,
            "can_spend": True,
            "tokens": [token_symbol] if token_symbol else [],
            "token_contract": token_contract,
            "token_symbol": token_symbol,
            "token_chain": token_chain,
        }

    if selector in {"ac9650d8", "5ae401dc"}:
        nested = scan_nested_selectors(x)

        return {
            "detected": True,
            "type": "multicall",
            "method": "multicall / batch transaction",
            "selector": selector,
            "unlimited": bool(nested.get("has_hidden_approval") or nested.get("has_hidden_permit")),
            "can_spend": bool(nested.get("dangerous_selector_count")),
            "nested_selectors": nested,
            "hidden_approval": bool(nested.get("has_hidden_approval")),
            "hidden_permit": bool(nested.get("has_hidden_permit")),
            "hidden_transfer_from": bool(nested.get("has_hidden_transfer_from")),
            "tokens": [token_symbol] if token_symbol else [],
            "token_contract": token_contract,
            "token_symbol": token_symbol,
            "token_chain": token_chain,
        }

    if selector == "23b872dd" and len(words) >= 3:
        from_addr = evm_word_to_addr(words[0])
        to_addr = evm_word_to_addr(words[1])
        amount = evm_word_to_int(words[2])

        return {
            "detected": True,
            "type": "erc20_transfer_from",
            "method": "transferFrom(address,address,uint256)",
            "selector": selector,
            "from": from_addr,
            "to": to_addr,
            "amount_raw": str(amount) if amount is not None else None,
            "unlimited": False,
            "can_spend": True,
            "tokens": [token_symbol] if token_symbol else [],
            "token_contract": token_contract,
            "token_symbol": token_symbol,
            "token_chain": token_chain,
        }

    if selector == "a9059cbb" and len(words) >= 2:
        to_addr = evm_word_to_addr(words[0])
        amount = evm_word_to_int(words[1])

        return {
            "detected": True,
            "type": "erc20_transfer",
            "method": "transfer(address,uint256)",
            "selector": selector,
            "to": to_addr,
            "amount_raw": str(amount) if amount is not None else None,
            "unlimited": False,
            "can_spend": False,
            "tokens": [token_symbol] if token_symbol else [],
            "token_contract": token_contract,
            "token_symbol": token_symbol,
            "token_chain": token_chain,
        }

    return None


DANGEROUS_SELECTORS = {
    "095ea7b3": {
        "type": "erc20_approve",
        "method": "approve(address,uint256)",
        "risk": "token_approval",
    },
    "a22cb465": {
        "type": "nft_set_approval_for_all",
        "method": "setApprovalForAll(address,bool)",
        "risk": "nft_collection_approval",
    },
    "d505accf": {
        "type": "permit",
        "method": "permit(...)",
        "risk": "signature_permission",
    },
    "2b67b570": {
        "type": "permit2",
        "method": "Permit2 permission",
        "risk": "signature_permission",
    },
    "30f28b7a": {
        "type": "permit2",
        "method": "Permit2 permission",
        "risk": "signature_permission",
    },
    "23b872dd": {
        "type": "erc20_transfer_from",
        "method": "transferFrom(address,address,uint256)",
        "risk": "asset_transfer",
    },
}


def scan_nested_selectors(raw: str) -> Dict:
    """
    Lightweight production-safe calldata intelligence.
    Finds dangerous selectors even when they are embedded inside batched/multicall payloads.
    """
    h = str(raw or "").lower().replace("0x", "")
    found = []

    for selector, meta in DANGEROUS_SELECTORS.items():
        positions = []
        start = 0

        while True:
            idx = h.find(selector, start)
            if idx == -1:
                break
            positions.append(idx)
            start = idx + len(selector)

        if positions:
            found.append({
                "selector": selector,
                "count": len(positions),
                "positions": positions[:20],
                **meta,
            })

    high_risk_count = sum(x["count"] for x in found if x.get("risk") in {
        "token_approval",
        "nft_collection_approval",
        "signature_permission",
        "asset_transfer",
    })

    return {
        "available": bool(h),
        "found": found,
        "dangerous_selector_count": high_risk_count,
        "has_hidden_approval": any(x.get("risk") in {"token_approval", "nft_collection_approval"} for x in found),
        "has_hidden_permit": any(x.get("risk") == "signature_permission" for x in found),
        "has_hidden_transfer_from": any(x.get("risk") == "asset_transfer" for x in found),
    }
