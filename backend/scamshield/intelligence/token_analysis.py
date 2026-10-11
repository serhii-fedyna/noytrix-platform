from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


EVM_PLATFORM_CHAIN_IDS = {
    "ethereum": "1",
    "binance-smart-chain": "56",
    "bsc": "56",
    "base": "8453",
    "arbitrum-one": "42161",
    "arbitrum": "42161",
    "optimistic-ethereum": "10",
    "optimism": "10",
    "polygon-pos": "137",
    "polygon": "137",
    "avalanche": "43114",
    "fantom": "250",
}


def platform_chain_id(platform: Any) -> str | None:
    return EVM_PLATFORM_CHAIN_IDS.get(str(platform or "").strip().lower())


def evm_platform_candidates(platforms: dict[str, Any], address_validator) -> list[dict[str, str]]:
    """Return deterministic contract candidates without guessing a network.

    A platform with an unknown chain id is intentionally omitted: querying the
    right address on the wrong chain is worse than reporting incomplete data.
    """
    candidates: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for platform in sorted((platforms or {}).keys()):
        address = str((platforms or {}).get(platform) or "").strip()
        chain_id = platform_chain_id(platform)
        if not chain_id or not address_validator(address):
            continue
        key = (address.lower(), chain_id)
        if key in seen:
            continue
        seen.add(key)
        candidates.append({
            "address": address.lower(),
            "chain_id": chain_id,
            "platform": str(platform).strip().lower(),
        })
    return candidates


def _decimal(value: Any) -> Decimal | None:
    try:
        if value is None or value == "":
            return None
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _liquidity_usd(pair: dict[str, Any]) -> Decimal:
    value = ((pair or {}).get("liquidity") or {}).get("usd")
    return _decimal(value) or Decimal(0)


def select_dex_pairs(pairs: Iterable[dict[str, Any]], address: str) -> dict[str, Any]:
    """Select only pairs whose base or quote token is the requested asset.

    Dex APIs do not promise useful ordering.  The most liquid matching pair is
    the display pair; liquidity is not summed because pools may be duplicated
    by upstream indexing.
    """
    target = str(address or "").strip().lower()
    matched: list[dict[str, Any]] = []
    role_by_pair: dict[int, str] = {}
    for pair in pairs or []:
        if not isinstance(pair, dict):
            continue
        base = str(((pair.get("baseToken") or {}).get("address")) or "").lower()
        quote = str(((pair.get("quoteToken") or {}).get("address")) or "").lower()
        role = "base" if base == target else "quote" if quote == target else None
        if role:
            role_by_pair[id(pair)] = role
            matched.append(pair)

    matched.sort(
        key=lambda pair: (
            _liquidity_usd(pair),
            str(pair.get("chainId") or ""),
            str(pair.get("pairAddress") or ""),
        ),
        reverse=True,
    )
    primary = matched[0] if matched else None
    return {
        "matched_pairs": matched,
        "pair_count": len(matched),
        "primary_pair": primary,
        "token_role": role_by_pair.get(id(primary)) if primary else None,
        "max_liquidity_usd": float(_liquidity_usd(primary)) if primary else None,
    }


def normalize_honeypot_payload(data: dict[str, Any]) -> dict[str, Any]:
    summary = (data or {}).get("summary") or {}
    result = (data or {}).get("honeypotResult") or {}
    simulation = (data or {}).get("simulationResult") or {}
    contract_code = (data or {}).get("contractCode") or {}
    token = (data or {}).get("token") or {}
    simulation_success = (data or {}).get("simulationSuccess")
    is_honeypot = result.get("isHoneypot")
    risk = str(summary.get("risk") or "").strip().lower() or None
    try:
        risk_level = int(summary.get("riskLevel") or 0)
    except (TypeError, ValueError):
        risk_level = 0

    findings: list[dict[str, Any]] = []
    if is_honeypot is True:
        findings.append({
            "code": "honeypot_detected",
            "severity": 95,
            "confidence": 95 if simulation_success is True else 80,
            "confirmed": True,
            "hard_evidence": True,
            "value": True,
            "method": "sell_simulation",
            "text": "A transaction simulation identified honeypot sell restrictions.",
        })

    sell_tax = _decimal(simulation.get("sellTax"))
    buy_tax = _decimal(simulation.get("buyTax"))
    if sell_tax is not None and sell_tax >= Decimal("50"):
        findings.append({
            "code": "extreme_sell_tax",
            "severity": 80,
            "confidence": 90 if simulation_success is True else 65,
            "confirmed": simulation_success is True,
            "hard_evidence": simulation_success is True,
            "value": str(sell_tax),
            "method": "sell_simulation",
            "text": "Sell simulation measured an extreme sell tax.",
        })
    elif sell_tax is not None and sell_tax >= Decimal("20"):
        findings.append({
            "code": "high_sell_tax",
            "severity": 45,
            "confidence": 90 if simulation_success is True else 60,
            "value": str(sell_tax),
            "method": "sell_simulation",
            "text": "Sell simulation measured a high sell tax.",
        })

    status = "malicious" if any(item.get("hard_evidence") and item["severity"] >= 70 for item in findings) else "observed"
    if is_honeypot is False and simulation_success is True and not findings:
        status = "clean"

    return {
        "status": status,
        "assessment_status": "available" if simulation_success is True else "partial",
        "is_honeypot": is_honeypot if isinstance(is_honeypot, bool) else None,
        "risk": risk,
        "risk_level": risk_level,
        "simulation_success": simulation_success if isinstance(simulation_success, bool) else None,
        "buy_tax": float(buy_tax) if buy_tax is not None else None,
        "sell_tax": float(sell_tax) if sell_tax is not None else None,
        "transfer_tax": simulation.get("transferTax"),
        "open_source": contract_code.get("openSource"),
        "is_proxy": contract_code.get("isProxy"),
        "total_holders": token.get("totalHolders") if token.get("totalHolders") is not None else token.get("holders"),
        "findings": findings,
    }


def build_token_snapshot(
    dex: dict[str, Any] | None,
    honeypot: dict[str, Any] | None,
    chain_state: dict[str, Any] | None = None,
    goplus: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a stable public token metric contract without zero-filling unknowns."""
    dex = dex or {}
    honeypot = honeypot or {}
    chain_state = chain_state or {}
    goplus = goplus or {}
    token = dex.get("token") or dex.get("baseToken") or {}
    liquidity = dex.get("liquidity") or {}
    liquidity_usd = liquidity.get("usd") if isinstance(liquidity, dict) else None
    if liquidity_usd is None:
        liquidity_usd = dex.get("max_liquidity_usd")

    metrics = {
        "identity": {
            "address": token.get("address"),
            "symbol": token.get("symbol"),
            "name": token.get("name"),
            "chain": dex.get("chainId"),
            "dex": dex.get("dexId"),
            "pair_address": dex.get("pairAddress"),
            "token_role": dex.get("token_role"),
        },
        "market": {
            "market_cap_usd": dex.get("marketCap"),
            "fully_diluted_valuation_usd": dex.get("fdv"),
            "liquidity_usd": liquidity_usd,
        },
        "holders": {
            "total": honeypot.get("total_holders") if honeypot.get("total_holders") is not None else goplus.get("holder_count"),
            "largest_owner_sample": chain_state.get("largest_owner_sample"),
            "concentration_top_10_pct": chain_state.get("top10_owner_concentration_pct"),
            "sample_complete": chain_state.get("largest_owner_sample_complete"),
            "source_available": honeypot.get("total_holders") is not None or goplus.get("holder_count") is not None or chain_state.get("largest_owner_sample") is not None,
        },
        "sellability": {
            "simulation_success": honeypot.get("simulation_success"),
            "is_honeypot": honeypot.get("is_honeypot"),
            "buy_tax_pct": honeypot.get("buy_tax"),
            "sell_tax_pct": honeypot.get("sell_tax"),
            "max_buy": honeypot.get("max_buy"),
            "max_sell": honeypot.get("max_sell"),
            "independent_provider_honeypot": goplus.get("is_honeypot"),
            "cannot_sell_all": goplus.get("cannot_sell_all"),
        },
        "controls": {
            "source_open": honeypot.get("open_source"),
            "is_proxy": chain_state.get("is_eip1967_proxy") if chain_state.get("is_eip1967_proxy") is not None else honeypot.get("is_proxy"),
            "owner": chain_state.get("owner"),
            "mint_authority": chain_state.get("mint_authority"),
            "freeze_authority": chain_state.get("freeze_authority"),
            "upgrade_authority": chain_state.get("upgrade_authority"),
            "implementation": chain_state.get("implementation"),
            "proxy_admin": chain_state.get("proxy_admin"),
            "paused": chain_state.get("paused"),
            "token_2022": chain_state.get("token_2022_controls"),
            "verified_abi": chain_state.get("abi_analysis"),
            "independent_provider_controls": goplus.get("controls"),
        },
    }
    missing: list[str] = []
    required_paths = {
        "market.liquidity_usd": metrics["market"]["liquidity_usd"],
        "holders.total": metrics["holders"]["total"],
        "holders.concentration_top_10_pct": metrics["holders"]["concentration_top_10_pct"],
        "sellability.simulation_success": metrics["sellability"]["simulation_success"],
        "controls.owner_or_authority": (
            metrics["controls"]["owner"]
            or metrics["controls"]["mint_authority"]
            or metrics["controls"]["freeze_authority"]
            or metrics["controls"]["upgrade_authority"]
        ),
    }
    for path, value in required_paths.items():
        if value is None:
            missing.append(path)
    return {
        **metrics,
        "missing_metrics": missing,
        "complete": not missing,
    }
