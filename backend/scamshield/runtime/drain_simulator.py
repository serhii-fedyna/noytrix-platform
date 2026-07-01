from __future__ import annotations

from typing import Any, Dict, List


HIGH_VALUE_TOKENS = {
    "USDT": 1.0,
    "USDC": 1.0,
    "DAI": 1.0,
    "WETH": 3500.0,
    "WBTC": 100000.0,
    "ETH": 3500.0,
    "BNB": 700.0,
}


def _estimate_token_value(symbol: str | None, amount_raw: str | None) -> float:
    try:
        symbol = str(symbol or "").upper()
        amount = float(amount_raw or 0)

        if symbol in HIGH_VALUE_TOKENS:
            return amount * HIGH_VALUE_TOKENS[symbol]

        return amount
    except Exception:
        return 0.0


def simulate_wallet_drain(
    tx: Dict[str, Any] | None,
    permissions: Dict[str, Any] | None,
    behavior: Dict[str, Any] | None,
    execution_graph: Dict[str, Any] | None,
) -> Dict[str, Any]:

    tx = tx or {}
    permissions = permissions or {}
    behavior = behavior or {}
    execution_graph = execution_graph or {}

    risks: List[str] = []
    possible_assets: List[str] = []
    actions: List[str] = []

    unlimited = bool(permissions.get("unlimited"))
    spender = permissions.get("spender")
    token_symbol = permissions.get("token_symbol")
    asset_type = tx.get("asset_type")

    estimated_loss_usd = 0.0
    exposure_level = "low"

    if unlimited:
        risks.append("Unlimited spending permission detected.")
        actions.append("The spender may drain assets later without another wallet popup.")

    if token_symbol:
        possible_assets.append(token_symbol)

    if tx.get("type") == "nft_set_approval_for_all":
        risks.append("NFT collection-wide approval detected.")
        actions.append("The spender may transfer NFTs from the wallet.")
        exposure_level = "critical"

    graph_score = int(execution_graph.get("attack_chain_score") or 0)

    if graph_score >= 90:
        risks.append("Critical hidden execution chain detected.")
        actions.append("Nested hidden calls may execute after approval.")

    behavior_score = int(behavior.get("score") or 0)

    if behavior_score >= 90:
        risks.append("Behavior analysis indicates strong drainer patterns.")

    amount_raw = permissions.get("spend_limit")

    estimated_loss_type = "unknown"

    if unlimited:
        estimated_loss_usd = None
        estimated_loss_type = "unbounded_wallet_exposure"
    else:
        estimated_loss_usd = _estimate_token_value(token_symbol, amount_raw)
        estimated_loss_type = "estimated_from_amount" if estimated_loss_usd else "unknown"

    if estimated_loss_usd is not None and estimated_loss_usd >= 100000:
        exposure_level = "critical"
    elif estimated_loss_usd is not None and estimated_loss_usd >= 10000:
        exposure_level = "high"
    elif estimated_loss_usd is not None and estimated_loss_usd >= 1000:
        exposure_level = "medium"

    if graph_score >= 90:
        exposure_level = "critical"

    drain_probability = min(
        100,
        max(
            graph_score,
            behavior_score,
            85 if unlimited else 35,
        )
    )

    summary = (
        "Critical wallet drain risk detected."
        if drain_probability >= 90
        else "High wallet drain risk detected."
        if drain_probability >= 70
        else "Potential wallet risk detected."
    )

    explanation_context = {
        "drain_probability": drain_probability,
        "estimated_loss_type": estimated_loss_type,
        "exposure_level": exposure_level,
        "spender": spender,
        "unlimited_permission": unlimited,
        "hidden_execution_detected": graph_score >= 90,
        "behavior_score": behavior_score,
        "graph_score": graph_score,
        "possible_assets": sorted(set(possible_assets)),
        "risks": sorted(set(risks)),
        "possible_actions": sorted(set(actions)),
        "wallet_impact": {
            "can_drain_tokens": unlimited,
            "can_drain_nfts": tx.get("type") == "nft_set_approval_for_all",
            "hidden_execution_detected": graph_score >= 90,
            "delayed_drain_possible": unlimited,
        },
    }

    return {
        "available": True,
        "drain_probability": drain_probability,
        "estimated_loss_usd": estimated_loss_usd,
        "estimated_loss_type": estimated_loss_type,
        "exposure_level": exposure_level,
        "explanation_context": explanation_context,
        "spender": spender,
        "possible_assets": sorted(set(possible_assets)),
        "risks": sorted(set(risks)),
        "possible_actions": sorted(set(actions)),
        "summary": summary,
        "wallet_impact": {
            "can_drain_tokens": unlimited,
            "can_drain_nfts": tx.get("type") == "nft_set_approval_for_all",
            "hidden_execution_detected": graph_score >= 90,
            "delayed_drain_possible": unlimited,
        },
    }
