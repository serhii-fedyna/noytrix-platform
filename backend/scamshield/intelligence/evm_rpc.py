from __future__ import annotations

import os
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


CHAIN_RPC = {
    "1": ("ETH_RPC_URL", "https://cloudflare-eth.com"),
    "56": ("BSC_RPC_URL", "https://bsc-dataseed.binance.org"),
    "8453": ("BASE_RPC_URL", "https://mainnet.base.org"),
    "42161": ("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc"),
    "10": ("OPTIMISM_RPC_URL", "https://mainnet.optimism.io"),
    "137": ("POLYGON_RPC_URL", "https://polygon-rpc.com"),
}

EIP1967_IMPLEMENTATION_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
EIP1967_ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e0190933d6a8a9855d3a860b7e8e7b5d6103"

PRIVILEGED_FUNCTION_FAMILIES = {
    "ownership": {"transferownership", "renounceownership", "acceptownership"},
    "minting": {"mint", "mintto", "setminter", "addminter"},
    "freezing_or_blacklist": {"freeze", "unfreeze", "blacklist", "unblacklist", "blockaddress", "unblockaddress"},
    "pausing": {"pause", "unpause"},
    "fees": {"setfee", "setfees", "settax", "setbuytax", "setselltax", "setfeerecipient"},
    "trading_controls": {"enabletrading", "settradingenabled", "opentrading", "setmaxwallet", "setmaxtxamount"},
    "upgrade": {"upgradeto", "upgradetoandcall", "changeadmin"},
    "seizure_or_recovery": {"recovererc20", "rescuetokens", "sweep", "confiscate"},
}


def analyze_verified_abi(raw_abi: Any) -> dict[str, Any]:
    try:
        abi = json.loads(raw_abi) if isinstance(raw_abi, str) else raw_abi
    except (json.JSONDecodeError, TypeError):
        abi = None
    if not isinstance(abi, list):
        return {"available": False, "function_count": 0, "privileged_functions": {}, "reason": "invalid_or_missing_abi"}
    functions: list[dict[str, Any]] = []
    privileged: dict[str, list[dict[str, Any]]] = {}
    for item in abi:
        if not isinstance(item, dict) or item.get("type") != "function":
            continue
        name = str(item.get("name") or "").strip()
        normalized = name.replace("_", "").lower()
        descriptor = {
            "name": name,
            "state_mutability": item.get("stateMutability"),
            "inputs": [str(row.get("type") or "") for row in (item.get("inputs") or []) if isinstance(row, dict)],
        }
        functions.append(descriptor)
        for family, names in PRIVILEGED_FUNCTION_FAMILIES.items():
            if normalized in names:
                privileged.setdefault(family, []).append(descriptor)
    return {
        "available": True,
        "function_count": len(functions),
        "privileged_functions": privileged,
        "functions": functions,
    }


async def _rpc(client: httpx.AsyncClient, endpoint: str, method: str, params: list[Any]) -> Any:
    response = await client.post(endpoint, json={"jsonrpc": "2.0", "id": method, "method": method, "params": params})
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(f"{method}:{payload['error'].get('code')}:{str(payload['error'].get('message'))[:160]}")
    return payload.get("result")


def _address_word(value: Any) -> str | None:
    raw = str(value or "").lower().removeprefix("0x")
    if len(raw) < 40:
        return None
    address = raw[-40:]
    if address == "0" * 40 or any(char not in "0123456789abcdef" for char in address):
        return None
    return "0x" + address


def _bool_word(value: Any) -> bool | None:
    raw = str(value or "").lower().removeprefix("0x")
    if not raw:
        return None
    try:
        number = int(raw, 16)
    except ValueError:
        return None
    return False if number == 0 else True if number == 1 else None


async def _optional_call(client: httpx.AsyncClient, endpoint: str, address: str, selector: str) -> Any:
    try:
        return await _rpc(client, endpoint, "eth_call", [{"to": address, "data": selector}, "latest"])
    except Exception:
        return None


async def analyze_evm_contract(address: str, chain_id: str, rpc_url: str | None = None) -> dict[str, Any]:
    config = CHAIN_RPC.get(str(chain_id))
    observed = datetime.now(timezone.utc)
    base = {
        "name": "evm_rpc",
        "source": "evm_rpc",
        "observed_at": observed.isoformat(),
        "fresh_until": (observed + timedelta(minutes=10)).isoformat(),
    }
    if not config and not rpc_url:
        return {**base, "status": "unavailable", "verdict": "unknown", "details": {"address": address, "chain_id": str(chain_id), "reason": "unsupported_chain"}, "evidence": []}
    endpoint = str(rpc_url or os.getenv(config[0]) or config[1]).strip()
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(18.0, connect=6.0), trust_env=False) as client:
            code = await _rpc(client, endpoint, "eth_getCode", [address, "latest"])
            has_code = str(code or "0x") not in {"", "0x", "0x0"}
            if not has_code:
                return {
                    **base,
                    "status": "observed",
                    "verdict": "unknown",
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "details": {"address": address, "chain_id": str(chain_id), "has_contract_code": False, "entity_type": "externally_owned_account"},
                    "evidence": [{"code": "evm_no_contract_code", "severity": 0, "polarity": "neutral", "text": "No contract bytecode exists at this address on the selected network."}],
                }

            implementation_word = await _rpc(client, endpoint, "eth_getStorageAt", [address, EIP1967_IMPLEMENTATION_SLOT, "latest"])
            admin_word = await _rpc(client, endpoint, "eth_getStorageAt", [address, EIP1967_ADMIN_SLOT, "latest"])
            owner_word = await _optional_call(client, endpoint, address, "0x8da5cb5b")
            if not _address_word(owner_word):
                owner_word = await _optional_call(client, endpoint, address, "0x893d20e8")
            paused_word = await _optional_call(client, endpoint, address, "0x5c975abb")
            implementation = _address_word(implementation_word)
            proxy_admin = _address_word(admin_word)
            owner = _address_word(owner_word)
            paused = _bool_word(paused_word)
            details = {
                "address": address.lower(),
                "chain_id": str(chain_id),
                "entity_type": "contract",
                "has_contract_code": True,
                "bytecode_size": max(0, (len(str(code).removeprefix("0x")) // 2)),
                "owner": owner,
                "paused": paused,
                "is_eip1967_proxy": implementation is not None,
                "implementation": implementation,
                "proxy_admin": proxy_admin,
            }
            evidence = [{"code": "evm_contract_code_observed", "severity": 0, "polarity": "neutral", "text": "Contract bytecode was read from the selected network."}]
            for code_name, value, text in (
                ("evm_owner_observed", owner, "The contract exposes an owner address."),
                ("evm_proxy_implementation_observed", implementation, "An EIP-1967 implementation address is configured."),
                ("evm_proxy_admin_observed", proxy_admin, "An EIP-1967 proxy admin address is configured."),
            ):
                if value:
                    evidence.append({"code": code_name, "severity": 0, "polarity": "neutral", "value": value, "method": "eth_call" if code_name == "evm_owner_observed" else "eth_getStorageAt", "text": text})
            if paused is not None:
                evidence.append({"code": "evm_paused_state_observed", "severity": 0, "polarity": "neutral", "value": paused, "method": "eth_call", "text": "The contract paused state was read on-chain."})
            return {**base, "status": "observed", "verdict": "unknown", "latency_ms": int((time.perf_counter() - started) * 1000), "details": details, "evidence": evidence}
    except httpx.TimeoutException as exc:
        return {**base, "status": "timeout", "verdict": "unknown", "latency_ms": int((time.perf_counter() - started) * 1000), "details": {"address": address, "chain_id": str(chain_id), "error": str(exc)[:200]}, "evidence": []}
    except Exception as exc:
        return {**base, "status": "source_unavailable", "verdict": "unknown", "latency_ms": int((time.perf_counter() - started) * 1000), "details": {"address": address, "chain_id": str(chain_id), "error": str(exc)[:300]}, "evidence": []}
