from typing import Any, Dict


def detect_drainer_patterns(tx: Dict[str, Any] | None) -> Dict[str, Any]:
    tx = tx or {}
    flags = []
    score = 0

    t = str(tx.get("type") or "")
    method = str(tx.get("method") or "")
    selector = str(tx.get("selector") or "").lower()
    unlimited = bool(tx.get("unlimited"))
    spender = str(tx.get("spender") or "").lower()

    if t == "erc20_approve" and unlimited:
        flags.append("unlimited_erc20_approval")
        score += 45

    if t == "erc20_transfer_from":
        flags.append("transfer_from_can_move_tokens")
        score += 35

    if spender and spender not in {"", "none", "null"}:
        flags.append("external_spender_permission")
        score += 15

    if selector in {"ac9650d8", "5ae401dc"}:
        flags.append("multicall_batch_transaction")
        score += 35

    if "permit" in method.lower() or selector in {"d505accf", "2b67b570", "30f28b7a"}:
        flags.append("permit_signature_or_permission")
        score += 40

    high = score >= 60

    return {
        "detected": bool(flags),
        "score": min(score, 100),
        "risk": "high" if high else ("medium" if score >= 35 else "low"),
        "flags": flags,
        "summary": "Possible wallet-drainer behavior detected." if flags else "No drainer pattern detected.",
    }
