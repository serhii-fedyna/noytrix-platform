from __future__ import annotations

from typing import Any, Dict, List


def analyze_transaction_behavior(
    tx_decoded: Dict[str, Any] | None,
    permissions: Dict[str, Any] | None = None,
    spender_rep: Dict[str, Any] | None = None,
    domain: str | None = None,
) -> Dict[str, Any]:
    tx = tx_decoded or {}
    perm = permissions or {}
    rep = spender_rep or perm.get("spender_reputation") or {}

    tx_type = str(tx.get("type") or "").lower()
    method = str(tx.get("method") or "").lower()
    spender = str(tx.get("spender") or perm.get("spender") or "").lower().strip()
    trust = str(rep.get("trust") or perm.get("spender_trust") or "unknown").lower()
    risk = str(rep.get("risk") or perm.get("spender_risk") or "unknown").lower()
    category = str(rep.get("category") or perm.get("spender_category") or "").lower()

    signals: List[Dict[str, Any]] = []
    score = 0

    def add(code: str, severity: int, text: str):
        nonlocal score
        severity = max(0, min(100, int(severity)))
        signals.append({"code": code, "severity": severity, "text": text})
        score = max(score, severity)

    if tx.get("unlimited"):
        add(
            "unlimited_permission",
            80,
            "The transaction grants unlimited future spending permission."
        )

    if tx_type == "nft_set_approval_for_all":
        add(
            "nft_collection_wide_permission",
            92,
            "The transaction grants an operator access to all NFTs in this collection."
        )

    if "permit" in method or tx_type == "permit_or_permit2":
        add(
            "signature_based_permission",
            88,
            "The action uses a signature-based permission that may not look like a normal transfer."
        )

    if tx_type == "multicall":
        add(
            "batched_transaction",
            65,
            "The transaction is a batched call, which can hide multiple actions inside one wallet prompt."
        )

        nested = tx.get("nested_selectors") or {}

        if nested.get("has_hidden_approval"):
            add(
                "hidden_approval_inside_multicall",
                92,
                "A token or NFT approval was detected inside the batched transaction."
            )

        if nested.get("has_hidden_permit"):
            add(
                "hidden_permit_inside_multicall",
                94,
                "A signature permission was detected inside the batched transaction."
            )

        if nested.get("has_hidden_transfer_from"):
            add(
                "hidden_transfer_from_inside_multicall",
                96,
                "A transferFrom operation was detected inside the batched transaction."
            )

    if spender and trust in {"unknown", "", "none"} and tx.get("can_spend"):
        add(
            "unknown_spender_with_permission",
            90,
            "The spender is unknown and receives permission to move assets."
        )

    if trust == "malicious" or risk == "critical":
        add(
            "known_malicious_spender_behavior",
            98,
            "The spender is known or classified as malicious."
        )

    if category in {"dex_router", "permit_manager", "marketplace", "bridge"} and trust == "trusted":
        add(
            "trusted_protocol_context",
            5,
            "The spender matches trusted protocol infrastructure."
        )

    if domain:
        d = str(domain).lower()
        if any(x in d for x in ["claim", "airdrop", "bonus", "reward", "mint", "gift"]):
            add(
                "phishing_lure_domain_context",
                72,
                "The domain context contains common phishing lure wording."
            )

    level = "safe"
    if score >= 90:
        level = "critical"
    elif score >= 70:
        level = "high"
    elif score >= 40:
        level = "medium"
    elif score > 0:
        level = "low"

    return {
        "available": bool(tx),
        "score": score,
        "level": level,
        "signals": sorted(signals, key=lambda x: int(x.get("severity") or 0), reverse=True),
        "summary": (
            "Critical transaction behavior detected."
            if level == "critical"
            else "High-risk transaction behavior detected."
            if level == "high"
            else "Transaction behavior has moderate risk signals."
            if level == "medium"
            else "No dangerous transaction behavior detected."
        ),
    }
