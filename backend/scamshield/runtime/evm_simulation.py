from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from scamshield.intelligence.evm_rpc import CHAIN_RPC


EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
HEX_DATA = re.compile(r"^0x(?:[0-9a-fA-F]{2})*$")
PUBLIC_RPC_FALLBACKS = {
    "1": ["https://ethereum.publicnode.com", "https://1rpc.io/eth"],
    "56": ["https://bsc-rpc.publicnode.com", "https://bsc-dataseed1.binance.org"],
    "8453": ["https://base-rpc.publicnode.com", "https://1rpc.io/base"],
    "42161": ["https://arbitrum-one-rpc.publicnode.com", "https://1rpc.io/arb"],
    "10": ["https://optimism-rpc.publicnode.com", "https://1rpc.io/op"],
    "137": ["https://polygon-bor-rpc.publicnode.com", "https://1rpc.io/matic"],
}


class RpcError(RuntimeError):
    def __init__(self, method: str, error: dict[str, Any]):
        self.method = method
        self.error = error
        super().__init__(str(error.get("message") or "JSON-RPC error"))


def _base() -> dict[str, Any]:
    observed = datetime.now(timezone.utc)
    return {
        "name": "evm_transaction_simulation",
        "source": "evm_rpc",
        "observed_at": observed.isoformat(),
        "fresh_until": (observed + timedelta(minutes=2)).isoformat(),
        "verdict": "unknown",
    }


def _chain_id(payload: dict[str, Any]) -> str:
    value = payload.get("chainId") or payload.get("chain_id") or payload.get("chain") or payload.get("network") or ""
    text = str(value).strip().lower()
    aliases = {
        "ethereum": "1", "eth": "1", "mainnet": "1", "bsc": "56", "bnb": "56",
        "base": "8453", "arbitrum": "42161", "arb": "42161", "optimism": "10",
        "op": "10", "polygon": "137", "matic": "137",
    }
    if text in aliases:
        return aliases[text]
    try:
        return str(int(text, 0))
    except (TypeError, ValueError):
        return text


def _transaction(payload: dict[str, Any]) -> dict[str, str]:
    nested = payload.get("tx") or payload.get("transaction") or {}
    if not isinstance(nested, dict):
        nested = {}
    tx: dict[str, str] = {}
    for key in ("from", "to", "data", "value", "gas", "gasPrice", "maxFeePerGas", "maxPriorityFeePerGas"):
        value = nested.get(key) if nested.get(key) not in (None, "") else payload.get(key)
        if value not in (None, ""):
            tx[key] = str(value).strip()
    if "data" not in tx and payload.get("input"):
        tx["data"] = str(payload["input"]).strip()
    tx.setdefault("data", "0x")
    return tx


def _validate(tx: dict[str, str], chain_id: str) -> str | None:
    if chain_id not in CHAIN_RPC:
        return "unsupported_chain"
    if not EVM_ADDRESS.fullmatch(tx.get("to") or ""):
        return "invalid_or_missing_to"
    if tx.get("from") and not EVM_ADDRESS.fullmatch(tx["from"]):
        return "invalid_from"
    if not HEX_DATA.fullmatch(tx.get("data") or ""):
        return "invalid_calldata"
    for key in ("value", "gas", "gasPrice", "maxFeePerGas", "maxPriorityFeePerGas"):
        if key not in tx:
            continue
        try:
            number = int(tx[key], 0)
            if number < 0:
                raise ValueError
            tx[key] = hex(number)
        except ValueError:
            return f"invalid_{key}"
    return None


async def _rpc(client: httpx.AsyncClient, endpoint: str, method: str, params: list[Any]) -> Any:
    response = await client.post(endpoint, json={"jsonrpc": "2.0", "id": method, "method": method, "params": params})
    response.raise_for_status()
    body = response.json()
    if isinstance(body.get("error"), dict):
        raise RpcError(method, body["error"])
    return body.get("result")


def _revert_data(error: dict[str, Any]) -> str:
    data = error.get("data")
    if isinstance(data, dict):
        data = data.get("data") or data.get("result") or data.get("return")
    return str(data or "")


def _decode_revert(error: dict[str, Any]) -> dict[str, Any]:
    raw = _revert_data(error)
    message = str(error.get("message") or "")[:300]
    decoded: dict[str, Any] = {"message": message, "data": raw[:514] if raw else None}
    clean = raw.removeprefix("0x")
    try:
        if clean.startswith("08c379a0") and len(clean) >= 136:
            length = int(clean[72:136], 16)
            decoded["reason"] = bytes.fromhex(clean[136:136 + length * 2]).decode("utf-8", errors="replace")[:300]
        elif clean.startswith("4e487b71") and len(clean) >= 72:
            decoded["panic_code"] = hex(int(clean[8:72], 16))
    except (ValueError, UnicodeDecodeError):
        pass
    return decoded


async def simulate_evm_transaction(payload: dict[str, Any]) -> dict[str, Any]:
    base = _base()
    chain_id = _chain_id(payload)
    tx = _transaction(payload)
    invalid = _validate(tx, chain_id)
    if invalid:
        return {**base, "status": "invalid_input", "details": {"chain_id": chain_id, "reason": invalid}, "evidence": []}

    config = CHAIN_RPC[chain_id]
    primary = str(payload.get("rpc_url") or os.getenv(config[0]) or config[1]).strip()
    endpoints = list(dict.fromkeys([primary, *PUBLIC_RPC_FALLBACKS.get(chain_id, [])]))
    started = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    for endpoint_index, endpoint in enumerate(endpoints):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=4.0), trust_env=False) as client:
                code = await _rpc(client, endpoint, "eth_getCode", [tx["to"], "latest"])
                has_code = str(code or "0x") not in {"", "0x", "0x0"}
                try:
                    result = await _rpc(client, endpoint, "eth_call", [tx, "latest"])
                    call = {"success": True, "return_data_size": len(str(result or "0x").removeprefix("0x")) // 2}
                    status = "observed"
                except RpcError as exc:
                    call = {"success": False, "revert": _decode_revert(exc.error)}
                    status = "reverted"

                gas_estimate = None
                try:
                    gas_raw = await _rpc(client, endpoint, "eth_estimateGas", [tx])
                    gas_estimate = int(str(gas_raw), 16) if gas_raw else None
                except (RpcError, TypeError, ValueError):
                    pass

                return {
                    **base,
                    "status": status,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "details": {
                        "chain_id": chain_id,
                        "to": tx["to"].lower(),
                        "target_has_contract_code": has_code,
                        "call": call,
                        "gas_estimate": gas_estimate,
                        "broadcast": False,
                        "rpc_endpoint_index": endpoint_index,
                        "failed_rpc_attempts": attempts,
                        "interpretation": "A successful call does not prove safety. A revert does not prove malicious intent.",
                    },
                    "evidence": [{
                        "code": "evm_call_simulated" if call["success"] else "evm_call_reverted",
                        "severity": 0,
                        "polarity": "neutral",
                        "method": "eth_call",
                        "text": "The transaction was simulated without broadcasting it." if call["success"] else "The simulated call reverted; this is an execution result, not proof of malicious intent.",
                    }],
                }
        except httpx.TimeoutException:
            attempts.append({"endpoint_index": endpoint_index, "status": "timeout"})
        except Exception as exc:
            attempts.append({"endpoint_index": endpoint_index, "status": "source_unavailable", "error": str(exc)[:160]})

    status = "timeout" if attempts and all(item["status"] == "timeout" for item in attempts) else "source_unavailable"
    return {
        **base,
        "status": status,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "details": {"chain_id": chain_id, "attempts": attempts},
        "evidence": [],
    }
