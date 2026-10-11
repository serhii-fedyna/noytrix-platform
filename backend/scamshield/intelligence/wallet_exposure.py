from __future__ import annotations

import asyncio
import os
from decimal import Decimal, InvalidOperation
from typing import Any

GOPLUS_BASE = "https://api.gopluslabs.io/api/v2"
ADDRESS_SECURITY_URL = "https://api.gopluslabs.io/api/v1/address_security"
HARD_MALICIOUS_BEHAVIORS = {
    "phishing_activities", "stealing_attack", "sanctioned", "cybercrime",
    "financial_crime", "blackmail_activities", "money_laundering",
}


def _decimal(value: Any) -> Decimal | None:
    try:
        if value in (None, ""):
            return None
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    return value in (1, "1", True)


def normalize_token_approvals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    approvals: list[dict[str, Any]] = []
    for token in rows or []:
        if not isinstance(token, dict):
            continue
        balance = _decimal(token.get("balance"))
        for approval in token.get("approved_list") or []:
            if not isinstance(approval, dict):
                continue
            raw_amount = approval.get("approved_amount")
            unlimited = str(raw_amount or "").strip().lower() == "unlimited"
            approved = None if unlimited else _decimal(raw_amount)
            exposed = balance if unlimited else min(balance, approved) if balance is not None and approved is not None else None
            info = approval.get("address_info") if isinstance(approval.get("address_info"), dict) else {}
            behaviors = sorted({str(x) for x in info.get("malicious_behavior") or [] if str(x)})
            hard_behaviors = sorted(set(behaviors) & HARD_MALICIOUS_BEHAVIORS)
            approvals.append({
                "asset_type": "erc20",
                "token_address": str(token.get("token_address") or "").lower(),
                "token_name": token.get("token_name"),
                "token_symbol": token.get("token_symbol"),
                "decimals": token.get("decimals"),
                "balance": float(balance) if balance is not None else None,
                "spender": str(approval.get("approved_contract") or "").lower(),
                "spender_name": info.get("contract_name") or info.get("tag"),
                "approved_amount": "unlimited" if unlimited else float(approved) if approved is not None else None,
                "unlimited": unlimited,
                "exposed_units": float(exposed) if exposed is not None else None,
                "approved_time": approval.get("approved_time"),
                "transaction_hash": approval.get("hash"),
                "trust_list": _bool(info.get("trust_list")),
                "doubt_list": _bool(info.get("doubt_list")),
                "malicious_behaviors": behaviors,
                "confirmed_malicious_behaviors": hard_behaviors,
            })
    return approvals


def normalize_nft_approvals(rows: list[dict[str, Any]], standard: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for token in rows or []:
        if not isinstance(token, dict):
            continue
        for approval in token.get("approved_list") or []:
            if not isinstance(approval, dict):
                continue
            info = approval.get("address_info") if isinstance(approval.get("address_info"), dict) else {}
            behaviors = sorted({str(x) for x in info.get("malicious_behavior") or [] if str(x)})
            result.append({
                "asset_type": standard,
                "token_address": str(token.get("nft_address") or token.get("token_address") or "").lower(),
                "token_name": token.get("nft_name") or token.get("token_name"),
                "token_symbol": token.get("nft_symbol") or token.get("token_symbol"),
                "spender": str(approval.get("approved_contract") or "").lower(),
                "spender_name": info.get("contract_name") or info.get("tag"),
                "approved_for_all": _bool(approval.get("approved_for_all")) or standard == "erc1155",
                "approved_token_id": approval.get("approved_token_id"),
                "approved_time": approval.get("approved_time"),
                "transaction_hash": approval.get("hash"),
                "trust_list": _bool(info.get("trust_list")),
                "doubt_list": _bool(info.get("doubt_list")),
                "malicious_behaviors": behaviors,
                "confirmed_malicious_behaviors": sorted(set(behaviors) & HARD_MALICIOUS_BEHAVIORS),
            })
    return result


async def _token_price(client: httpx.AsyncClient, token_address: str) -> float | None:
    import httpx

    try:
        response = await client.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_address}")
        if response.status_code != 200:
            return None
        pairs = response.json().get("pairs") or []
        exact = [pair for pair in pairs if str(((pair.get("baseToken") or {}).get("address")) or "").lower() == token_address.lower()]
        exact.sort(key=lambda pair: float(((pair.get("liquidity") or {}).get("usd")) or 0), reverse=True)
        return float(exact[0].get("priceUsd")) if exact and exact[0].get("priceUsd") is not None else None
    except (httpx.HTTPError, ValueError, TypeError):
        return None


async def check_wallet_approvals(address: str, chain_id: str) -> dict[str, Any]:
    import httpx

    token = (os.getenv("GOPLUS_API_TOKEN") or os.getenv("GOPLUS_API_KEY") or "").strip()
    headers = {"Accept": "application/json", "User-Agent": "Noytrix-Security/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    endpoints = (
        ("erc20", f"{GOPLUS_BASE}/token_approval_security/{chain_id}"),
        ("erc721", f"{GOPLUS_BASE}/nft721_approval_security/{chain_id}"),
        ("erc1155", f"{GOPLUS_BASE}/nft1155_approval_security/{chain_id}"),
    )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(22.0, connect=7.0), headers=headers) as client:
            responses = await asyncio.gather(*[client.get(url, params={"addresses": address}) for _kind, url in endpoints], return_exceptions=True)
            normalized: list[dict[str, Any]] = []
            failed: list[str] = []
            partial: list[str] = []
            for (kind, _url), response in zip(endpoints, responses):
                if isinstance(response, Exception) or response.status_code != 200:
                    failed.append(kind)
                    continue
                payload = response.json()
                if str(payload.get("code")) not in {"1", "2"}:
                    failed.append(kind)
                    continue
                if str(payload.get("code")) == "2":
                    partial.append(kind)
                rows = payload.get("result") if isinstance(payload.get("result"), list) else []
                normalized.extend(normalize_token_approvals(rows) if kind == "erc20" else normalize_nft_approvals(rows, kind))

            priced = [row for row in normalized if row["asset_type"] == "erc20" and (row.get("exposed_units") or 0) > 0]
            unique_tokens = list(dict.fromkeys(row["token_address"] for row in priced if row.get("token_address")))[:30]
            price_semaphore = asyncio.Semaphore(6)
            async def priced_token(item: str) -> float | None:
                async with price_semaphore:
                    return await _token_price(client, item)
            prices = await asyncio.gather(*[priced_token(item) for item in unique_tokens])
            price_map = dict(zip(unique_tokens, prices))
            total_usd = Decimal(0)
            priced_count = 0
            for row in normalized:
                price = price_map.get(row.get("token_address"))
                exposure = _decimal(row.get("exposed_units"))
                row["price_usd"] = price
                row["exposure_usd"] = round(float(exposure * Decimal(str(price))), 2) if exposure is not None and price is not None else None
                if row["exposure_usd"] is not None:
                    total_usd += Decimal(str(row["exposure_usd"]))
                    priced_count += 1

        hard_rows = [row for row in normalized if row.get("confirmed_malicious_behaviors")]
        evidence = [{
            "code": "active_approval_to_confirmed_malicious_spender",
            "severity": 95,
            "confidence": 90,
            "confirmed": True,
            "hard_evidence": True,
            "value": {"spender": row.get("spender"), "asset": row.get("token_symbol"), "behaviors": row.get("confirmed_malicious_behaviors")},
            "method": "outstanding_approval_security",
            "text": "An outstanding wallet approval points to a spender with explicit malicious behavior.",
        } for row in hard_rows]
        status = "malicious" if evidence else ("observed" if not failed or normalized else "source_unavailable")
        return {
            "name": "goplus_approvals", "status": status,
            "verdict": "malicious" if evidence else "unknown", "evidence": evidence,
            "details": {
                "address": address.lower(), "chain_id": str(chain_id),
                "active_approvals": normalized, "active_approval_count": len(normalized),
                "unlimited_erc20_count": sum(1 for row in normalized if row.get("unlimited")),
                "nft_all_approval_count": sum(1 for row in normalized if row.get("approved_for_all")),
                "confirmed_malicious_spender_count": len(hard_rows),
                "estimated_exposure_usd": round(float(total_usd), 2),
                "priced_exposure_count": priced_count,
                "unpriced_positive_balance_count": max(0, len(priced) - priced_count),
                "exposure_complete": not failed and not partial and len(priced) == priced_count and len(unique_tokens) == len({row["token_address"] for row in priced}),
                "failed_sections": failed, "partial_sections": partial,
            },
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {"name": "goplus_approvals", "status": "source_unavailable", "verdict": "unknown", "evidence": [], "details": {"address": address, "chain_id": chain_id, "error_type": type(exc).__name__}}


async def check_address_reputation(address: str, chain_id: str) -> dict[str, Any]:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(f"{ADDRESS_SECURITY_URL}/{address}", params={"chain_id": chain_id})
        if response.status_code != 200:
            return {"address": address, "status": "unavailable", "behaviors": []}
        payload = response.json()
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        behaviors = {str(x) for x in result.get("malicious_behavior") or [] if str(x)}
        flat_flags = {
            "honeypot_related_address", "phishing_activities", "blackmail_activities",
            "stealing_attack", "malicious_mining_activities", "mixer", "sanctioned",
            "gas_abuse", "fake_token", "fake_standard_interface",
        }
        behaviors.update(key for key in flat_flags if _bool(result.get(key)))
        confirmed = sorted(behaviors & HARD_MALICIOUS_BEHAVIORS)
        classification = sorted(key for key in ("mixer", "sanctioned", "contract_address") if _bool(result.get(key)))
        return {
            "address": address.lower(),
            "status": "malicious" if confirmed else "observed",
            "behaviors": sorted(behaviors),
            "confirmed_behaviors": confirmed,
            "classification": classification,
            "data_source": result.get("data_source"),
            "malicious_contracts_created": result.get("number_of_malicious_contracts_created"),
        }
    except (httpx.HTTPError, ValueError):
        return {"address": address, "status": "unavailable", "behaviors": []}


async def check_counterparty_reputation(addresses: list[str], chain_id: str, limit: int = 10) -> dict[str, Any]:
    selected = list(dict.fromkeys(str(item).lower() for item in addresses if str(item).startswith("0x")))[:limit]
    semaphore = asyncio.Semaphore(6)
    async def guarded(item: str) -> dict[str, Any]:
        async with semaphore:
            return await check_address_reputation(item, chain_id)
    rows = await asyncio.gather(*[guarded(item) for item in selected])
    malicious = [row for row in rows if row.get("confirmed_behaviors")]
    evidence = [{"code": "confirmed_malicious_counterparty_observed", "severity": 20, "confidence": 85, "confirmed": True, "hard_evidence": False, "polarity": "neutral", "value": row, "method": "counterparty_address_reputation", "text": "Recent wallet history includes a counterparty with explicit malicious behavior. Interaction alone does not make this wallet malicious."} for row in malicious]
    return {"name": "goplus_counterparties", "status": "observed", "verdict": "unknown", "evidence": evidence, "details": {"checked_count": len(rows), "candidate_count": len(addresses), "limit": limit, "confirmed_malicious": malicious, "unavailable_count": sum(1 for row in rows if row.get("status") == "unavailable"), "sample_complete": len(selected) == len(set(addresses)), "verdict_policy": "Counterparty contact is context only because unsolicited incoming transfers are possible."}}


def correlate_counterparties(addresses: list[str], lookup, limit: int = 10) -> dict[str, Any]:
    selected = list(dict.fromkeys(str(item).lower() for item in addresses if str(item).startswith("0x")))[:limit]
    matches: list[dict[str, Any]] = []
    for address in selected:
        try:
            match = lookup(address) or {}
        except Exception:
            continue
        if not match.get("matched"):
            continue
        matches.append({
            "address": address,
            "status": match.get("status"),
            "level": match.get("level"),
            "risk_score": match.get("risk_score"),
            "confidence": match.get("confidence"),
            "trusted_match": bool(match.get("force_verdict")),
            "database": match.get("database"),
        })
    evidence = [{
        "code": "noytrix_counterparty_database_context",
        "severity": 20,
        "confidence": int(row.get("confidence") or 0),
        "confirmed": bool(row.get("trusted_match")),
        "hard_evidence": False,
        "polarity": "neutral",
        "value": row,
        "method": "historical_counterparty_correlation",
        "text": "A sampled counterparty appears in Noytrix threat intelligence. Contact alone does not make this wallet malicious.",
    } for row in matches if str(row.get("status") or "").lower() in {"malicious", "scam", "danger", "critical", "high", "blocked"}]
    return {
        "name": "noytrix_counterparties", "status": "observed", "verdict": "unknown",
        "evidence": evidence,
        "details": {"checked_count": len(selected), "candidate_count": len(addresses), "matches": matches, "sample_complete": len(selected) == len(set(addresses)), "verdict_policy": "Historical contact is context only and cannot accuse the scanned wallet."},
    }
