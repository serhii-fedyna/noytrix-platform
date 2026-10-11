from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _rows(payload: Any) -> list[dict[str, Any]]:
    result = payload.get("result") if isinstance(payload, dict) else None
    return [row for row in result if isinstance(row, dict)] if isinstance(result, list) else []


def _timestamp(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _amount(row: dict[str, Any], event_type: str) -> tuple[float | None, str | None, str | None]:
    try:
        raw = int(str(row.get("value") or "0"))
    except (TypeError, ValueError):
        return None, None, None
    if event_type in {"normal", "internal"}:
        return raw / 1_000_000_000_000_000_000, "native", None
    if event_type == "token":
        try:
            decimals = int(row.get("tokenDecimal") or 0)
            return raw / (10 ** decimals), str(row.get("tokenSymbol") or "token"), str(row.get("contractAddress") or "").lower() or None
        except (TypeError, ValueError, OverflowError):
            return None, str(row.get("tokenSymbol") or "token"), str(row.get("contractAddress") or "").lower() or None
    return 1.0, str(row.get("tokenSymbol") or "NFT"), str(row.get("contractAddress") or "").lower() or None


def _event(row: dict[str, Any], event_type: str, target: str) -> dict[str, Any] | None:
    sender = str(row.get("from") or "").lower()
    recipient = str(row.get("to") or "").lower()
    if not sender and not recipient:
        return None
    direction = "outgoing" if sender == target else "incoming" if recipient == target else "related"
    amount, asset, contract = _amount(row, event_type)
    return {
        "event_type": event_type,
        "transaction_hash": row.get("hash"),
        "block_number": row.get("blockNumber"),
        "timestamp": _timestamp(row.get("timeStamp")),
        "from": sender or None,
        "to": recipient or None,
        "direction": direction,
        "amount": amount,
        "asset": asset,
        "asset_contract": contract,
        "token_id": row.get("tokenID") or row.get("tokenId"),
        "failed": str(row.get("isError") or "0") == "1" or str(row.get("txreceipt_status") or "1") == "0",
        "method_id": str(row.get("methodId") or "")[:10] or None,
        "function_name": str(row.get("functionName") or "")[:160] or None,
    }


def summarize_evm_history(
    address: str,
    normal_payload: dict[str, Any],
    internal_payload: dict[str, Any],
    token_payload: dict[str, Any],
    nft_payload: dict[str, Any],
) -> dict[str, Any]:
    target = address.lower()
    normal = _rows(normal_payload)
    internal = _rows(internal_payload)
    tokens = _rows(token_payload)
    nfts = _rows(nft_payload)
    all_rows = normal + internal + tokens + nfts
    typed_rows = [("normal", row) for row in normal] + [("internal", row) for row in internal] + [("token", row) for row in tokens] + [("nft", row) for row in nfts]
    events = [event for event in (_event(row, kind, target) for kind, row in typed_rows) if event]
    counterparties: set[str] = set()
    contracts: set[str] = set()
    incoming = 0
    outgoing = 0
    failed = 0
    timestamps: list[int] = []
    for row in all_rows:
        sender = str(row.get("from") or "").lower()
        recipient = str(row.get("to") or "").lower()
        if sender == target:
            outgoing += 1
            if recipient:
                counterparties.add(recipient)
        elif recipient == target:
            incoming += 1
            if sender:
                counterparties.add(sender)
        contract = str(row.get("contractAddress") or "").lower()
        if contract:
            contracts.add(contract)
        if str(row.get("isError") or "0") == "1" or str(row.get("txreceipt_status") or "1") == "0":
            failed += 1
        try:
            timestamps.append(int(row.get("timeStamp")))
        except (TypeError, ValueError):
            pass
    return {
        "sample_limits": {"normal": 100, "internal": 100, "token": 100, "nft": 100},
        "normal_transactions": len(normal),
        "internal_transfers": len(internal),
        "token_transfers": len(tokens),
        "nft_transfers": len(nfts),
        "sampled_events": len(all_rows),
        "incoming_events": incoming,
        "outgoing_events": outgoing,
        "failed_events": failed,
        "counterparties": sorted(counterparties)[:200],
        "counterparty_count_in_sample": len(counterparties),
        "token_contracts": sorted(contracts)[:200],
        "token_contract_count_in_sample": len(contracts),
        "first_activity_in_sample": _timestamp(min(timestamps)) if timestamps else None,
        "last_activity_in_sample": _timestamp(max(timestamps)) if timestamps else None,
        "history_found": bool(all_rows),
        "sample_complete": False,
        "events": events[:400],
        "event_schema": "directional_sample_v1",
    }


async def fetch_evm_history(client, base: str, chain_id: str, address: str, api_key: str) -> dict[str, Any]:
    common = {"chainid": chain_id, "module": "account", "address": address, "startblock": 0, "endblock": 99999999, "page": 1, "offset": 100, "sort": "desc", "apikey": api_key}
    actions = ("txlist", "txlistinternal", "tokentx", "tokennfttx")
    responses = await __import__("asyncio").gather(*[
        client.get(base, params={**common, "action": action}) for action in actions
    ], return_exceptions=True)
    payloads: list[dict[str, Any]] = []
    failures: list[str] = []
    for action, response in zip(actions, responses):
        if isinstance(response, Exception):
            payloads.append({})
            failures.append(action)
            continue
        try:
            payloads.append(response.json() if response.status_code == 200 else {})
            if response.status_code != 200:
                failures.append(action)
        except ValueError:
            payloads.append({})
            failures.append(action)
    summary = summarize_evm_history(address, *payloads)
    summary["failed_queries"] = failures
    summary["assessment_status"] = "partial" if failures else "available"
    return summary
