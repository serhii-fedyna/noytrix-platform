from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
TOKEN_PROGRAMS = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "spl-token",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "token-2022",
}


async def _rpc(client: httpx.AsyncClient, endpoint: str, method: str, params: list[Any]) -> Any:
    response = await client.post(endpoint, json={"jsonrpc": "2.0", "id": method, "method": method, "params": params})
    response.raise_for_status()
    body = response.json()
    if body.get("error"):
        raise RuntimeError(f"{method}:{body['error'].get('code')}:{str(body['error'].get('message'))[:160]}")
    return body.get("result")


def _parsed_account(value: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    data = value.get("data") if isinstance(value, dict) else None
    parsed = data.get("parsed") if isinstance(data, dict) else None
    return (str((parsed or {}).get("type") or "account"), dict((parsed or {}).get("info") or {}))


def _account_keys(transaction: dict[str, Any]) -> list[str]:
    message = ((transaction.get("transaction") or {}).get("message") or {})
    keys = []
    for item in message.get("accountKeys") or []:
        keys.append(str(item.get("pubkey")) if isinstance(item, dict) else str(item))
    return [item for item in keys if item]


def _instructions(transaction: dict[str, Any]) -> list[dict[str, Any]]:
    message = ((transaction.get("transaction") or {}).get("message") or {})
    items = list(message.get("instructions") or [])
    for group in ((transaction.get("meta") or {}).get("innerInstructions") or []):
        items.extend(group.get("instructions") or [])
    return [item for item in items if isinstance(item, dict)]


def _largest_owner_distribution(
    largest_accounts: list[dict[str, Any]],
    account_values: list[dict[str, Any] | None],
    raw_supply: int,
) -> dict[str, Any]:
    """Aggregate token accounts by owner before reporting concentration.

    One holder may control many associated token accounts. Reporting raw token
    accounts as holders materially overstates decentralisation.
    """
    owner_amounts: dict[str, int] = {}
    unresolved_amount = 0
    for row, value in zip(largest_accounts or [], account_values or []):
        amount = int((row or {}).get("amount") or 0)
        _account_type, info = _parsed_account(value or {})
        owner = str(info.get("owner") or "").strip()
        if owner:
            owner_amounts[owner] = owner_amounts.get(owner, 0) + amount
        else:
            unresolved_amount += amount
    owners = sorted(owner_amounts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    top10_amount = sum(amount for _owner, amount in owners[:10])
    return {
        "largest_owners": [
            {
                "owner": owner,
                "raw_amount": str(amount),
                "supply_pct": round((amount / raw_supply) * 100, 6) if raw_supply > 0 else None,
            }
            for owner, amount in owners
        ],
        "resolved_owner_count": len(owners),
        "unresolved_raw_amount": str(unresolved_amount),
        "top10_owner_concentration_pct": round((top10_amount / raw_supply) * 100, 6) if raw_supply > 0 else None,
        "sample_complete": bool(largest_accounts) and len(account_values or []) == len(largest_accounts or []) and unresolved_amount == 0,
    }


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if mapping.get(key) is not None:
            return mapping.get(key)
    return None


def normalize_token_2022_extensions(extensions: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize security-relevant Token-2022 controls from jsonParsed RPC."""
    controls: dict[str, Any] = {
        "extension_types": [],
        "transfer_fee": None,
        "permanent_delegate": None,
        "transfer_hook": None,
        "default_account_state": None,
        "non_transferable": False,
        "mint_close_authority": None,
        "confidential_transfer": None,
        "interest_bearing": None,
    }
    evidence: list[dict[str, Any]] = []
    for extension in extensions or []:
        if not isinstance(extension, dict):
            continue
        extension_type = str(
            extension.get("extension")
            or extension.get("extensionType")
            or extension.get("type")
            or "unknown"
        ).strip()
        normalized_type = extension_type.replace("_", "").replace("-", "").lower()
        state = extension.get("state") if isinstance(extension.get("state"), dict) else extension
        controls["extension_types"].append(extension_type)

        if normalized_type in {"transferfeeconfig", "transferfeeamount"}:
            controls["transfer_fee"] = {
                "config_authority": _first(state, "transferFeeConfigAuthority", "authority"),
                "withdraw_withheld_authority": state.get("withdrawWithheldAuthority"),
                "withheld_amount": state.get("withheldAmount"),
                "older_fee": state.get("olderTransferFee"),
                "newer_fee": state.get("newerTransferFee"),
            }
            evidence.append({"code": "solana_transfer_fee_control_observed", "severity": 0, "polarity": "neutral", "value": controls["transfer_fee"], "text": "Token-2022 transfer fee controls are configured."})
        elif normalized_type == "permanentdelegate":
            controls["permanent_delegate"] = _first(state, "delegate", "authority")
            evidence.append({"code": "solana_permanent_delegate_observed", "severity": 0, "polarity": "neutral", "value": controls["permanent_delegate"], "text": "Token-2022 has a permanent delegate control."})
        elif normalized_type == "transferhook":
            controls["transfer_hook"] = {
                "authority": state.get("authority"),
                "program_id": _first(state, "programId", "program_id"),
            }
            evidence.append({"code": "solana_transfer_hook_observed", "severity": 0, "polarity": "neutral", "value": controls["transfer_hook"], "text": "Token transfers invoke a configured Token-2022 hook program."})
        elif normalized_type == "defaultaccountstate":
            controls["default_account_state"] = _first(state, "state", "accountState")
            evidence.append({"code": "solana_default_account_state_observed", "severity": 0, "polarity": "neutral", "value": controls["default_account_state"], "text": "Token-2022 defines a default state for newly created token accounts."})
        elif normalized_type == "nontransferable":
            controls["non_transferable"] = True
            evidence.append({"code": "solana_non_transferable_token", "severity": 0, "polarity": "neutral", "value": True, "text": "Token-2022 marks this asset as non-transferable."})
        elif normalized_type == "mintcloseauthority":
            controls["mint_close_authority"] = _first(state, "closeAuthority", "authority")
            evidence.append({"code": "solana_mint_close_authority_observed", "severity": 0, "polarity": "neutral", "value": controls["mint_close_authority"], "text": "Token-2022 mint close authority is configured."})
        elif normalized_type.startswith("confidentialtransfer"):
            controls["confidential_transfer"] = {
                "authority": state.get("authority"),
                "auto_approve_new_accounts": state.get("autoApproveNewAccounts"),
                "auditor_elgamal_pubkey": state.get("auditorElgamalPubkey"),
            }
            evidence.append({"code": "solana_confidential_transfer_observed", "severity": 0, "polarity": "neutral", "value": controls["confidential_transfer"], "text": "Token-2022 confidential transfer controls are configured."})
        elif normalized_type == "interestbearingconfig":
            controls["interest_bearing"] = {
                "rate_authority": state.get("rateAuthority"),
                "current_rate": state.get("currentRate"),
            }
            evidence.append({"code": "solana_interest_bearing_control_observed", "severity": 0, "polarity": "neutral", "value": controls["interest_bearing"], "text": "Token-2022 interest-bearing controls are configured."})

    controls["extension_types"] = sorted(set(controls["extension_types"]))
    return {"controls": controls, "evidence": evidence}


async def analyze_solana_address(address: str, rpc_url: str | None = None) -> dict[str, Any]:
    endpoint = str(rpc_url or os.getenv("SOLANA_RPC_URL") or DEFAULT_RPC).strip()
    started = time.perf_counter()
    observed_at = datetime.now(timezone.utc)
    base = {
        "name": "solana_rpc",
        "source": "solana_rpc",
        "observed_at": observed_at.isoformat(),
        "fresh_until": (observed_at + timedelta(minutes=15)).isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(18.0, connect=6.0)) as client:
            account_result = await _rpc(client, endpoint, "getAccountInfo", [address, {"encoding": "jsonParsed", "commitment": "confirmed"}])
            value = (account_result or {}).get("value")
            if value is None:
                # A Solana transaction signature and an address are both base58
                # strings.  Resolve a plausible signature before reporting an
                # address as missing, so pasted transaction links are useful.
                if 64 <= len(address) <= 88:
                    transaction = await _rpc(
                        client,
                        endpoint,
                        "getTransaction",
                        [address, {"commitment": "confirmed", "encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
                    )
                    if isinstance(transaction, dict):
                        meta = transaction.get("meta") or {}
                        return {
                            **base,
                            "status": "observed",
                            "verdict": "unknown",
                            "latency_ms": int((time.perf_counter() - started) * 1000),
                            "details": {
                                "address": address,
                                "exists": True,
                                "entity_type": "transaction",
                                "signature": address,
                                "slot": transaction.get("slot"),
                                "block_time": transaction.get("blockTime"),
                                "fee_lamports": meta.get("fee"),
                                "execution_error": meta.get("err"),
                                "account_keys": _account_keys(transaction),
                                "program_interactions": sorted({
                                    str(item.get("programId") or item.get("program") or "")
                                    for item in _instructions(transaction)
                                    if str(item.get("programId") or item.get("program") or "")
                                }),
                            },
                            "evidence": [],
                        }
                return {**base, "status": "no_data", "verdict": "unknown", "latency_ms": int((time.perf_counter() - started) * 1000), "details": {"address": address, "exists": False}, "evidence": []}

            account_type, info = _parsed_account(value)
            owner_program = str(value.get("owner") or "")
            signatures_task = _rpc(client, endpoint, "getSignaturesForAddress", [address, {"commitment": "confirmed", "limit": 20}])
            details: dict[str, Any] = {
                "address": address,
                "exists": True,
                "account_type": account_type,
                "account_owner": owner_program,
                "program": TOKEN_PROGRAMS.get(owner_program, owner_program),
                "executable": bool(value.get("executable")),
                "lamports": int(value.get("lamports") or 0),
            }
            evidence: list[dict[str, Any]] = []

            if account_type == "mint":
                supply_result, largest_result, signatures = await asyncio.gather(
                    _rpc(client, endpoint, "getTokenSupply", [address, {"commitment": "confirmed"}]),
                    _rpc(client, endpoint, "getTokenLargestAccounts", [address, {"commitment": "confirmed"}]),
                    signatures_task,
                )
                supply_value = (supply_result or {}).get("value") or {}
                raw_supply = int(supply_value.get("amount") or info.get("supply") or 0)
                largest = (largest_result or {}).get("value") or []
                largest_addresses = [str(item.get("address") or "") for item in largest if item.get("address")]
                largest_owner_values: list[dict[str, Any] | None] = []
                if largest_addresses:
                    owner_result = await _rpc(
                        client,
                        endpoint,
                        "getMultipleAccounts",
                        [largest_addresses, {"encoding": "jsonParsed", "commitment": "confirmed"}],
                    )
                    largest_owner_values = list((owner_result or {}).get("value") or [])
                owner_distribution = _largest_owner_distribution(largest, largest_owner_values, raw_supply)
                token_2022 = normalize_token_2022_extensions(info.get("extensions") or [])
                details.update({
                    "entity_type": "mint",
                    "supply": float(supply_value.get("uiAmountString") or 0),
                    "raw_supply": str(raw_supply),
                    "decimals": int(supply_value.get("decimals") or info.get("decimals") or 0),
                    "mint_authority": info.get("mintAuthority"),
                    "freeze_authority": info.get("freezeAuthority"),
                    "token_2022_extensions": info.get("extensions") or [],
                    "token_2022_controls": token_2022["controls"],
                    "largest_token_accounts": largest,
                    "largest_owner_sample": owner_distribution["largest_owners"],
                    "largest_owner_sample_count": owner_distribution["resolved_owner_count"],
                    "largest_owner_sample_complete": owner_distribution["sample_complete"],
                    "top10_owner_concentration_pct": owner_distribution["top10_owner_concentration_pct"],
                    # Compatibility alias. This remains a sampled concentration,
                    # not a claim about the complete holder population.
                    "top_holder_concentration_pct": owner_distribution["top10_owner_concentration_pct"],
                    "recent_signature_count": len(signatures or []),
                    "recent_signatures": signatures or [],
                })
                if info.get("mintAuthority"):
                    evidence.append({"code": "solana_mint_authority_active", "severity": 0, "polarity": "neutral", "value": info.get("mintAuthority"), "text": "Token supply can still be changed by its mint authority."})
                if info.get("freezeAuthority"):
                    evidence.append({"code": "solana_freeze_authority_active", "severity": 0, "polarity": "neutral", "value": info.get("freezeAuthority"), "text": "Token accounts can be frozen by the configured authority."})
                evidence.extend(token_2022["evidence"])
            elif bool(value.get("executable")):
                signatures = await signatures_task
                details.update({
                    "entity_type": "program",
                    "recent_signature_count": len(signatures or []),
                    "recent_signatures": signatures or [],
                })
            else:
                balance_result, signatures = await asyncio.gather(
                    _rpc(client, endpoint, "getBalance", [address, {"commitment": "confirmed"}]),
                    signatures_task,
                )
                signature_rows = signatures or []
                tx_rows = await asyncio.gather(*[
                    _rpc(client, endpoint, "getTransaction", [row["signature"], {"commitment": "confirmed", "encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
                    for row in signature_rows[:5] if row.get("signature")
                ], return_exceptions=True)
                transactions = [item for item in tx_rows if isinstance(item, dict)]
                counterparties: set[str] = set()
                programs: set[str] = set()
                approvals = 0
                for transaction in transactions:
                    counterparties.update(key for key in _account_keys(transaction) if key != address)
                    for instruction in _instructions(transaction):
                        program = str(instruction.get("programId") or instruction.get("program") or "")
                        if program:
                            programs.add(program)
                        parsed = instruction.get("parsed") or {}
                        instruction_type = str(parsed.get("type") or "").lower()
                        if instruction_type in {"approve", "approvechecked", "setauthority"}:
                            approvals += 1
                details.update({
                    "entity_type": "wallet_or_account",
                    "balance_sol": round(int(((balance_result or {}).get("value") or 0)) / 1_000_000_000, 9),
                    "recent_signature_count": len(signature_rows),
                    "recent_signatures": signature_rows,
                    "recent_transactions_decoded": len(transactions),
                    "recent_failed_transactions": sum(1 for row in signature_rows if row.get("err") is not None),
                    "new_approvals": approvals,
                    "counterparties": sorted(counterparties)[:100],
                    "program_interactions": sorted(programs),
                })

            return {**base, "status": "observed", "verdict": "unknown", "latency_ms": int((time.perf_counter() - started) * 1000), "details": details, "evidence": evidence}
    except httpx.TimeoutException as exc:
        return {**base, "status": "timeout", "verdict": "unknown", "latency_ms": int((time.perf_counter() - started) * 1000), "details": {"address": address, "error": str(exc)[:200]}, "evidence": []}
    except Exception as exc:
        return {**base, "status": "source_unavailable", "verdict": "unknown", "latency_ms": int((time.perf_counter() - started) * 1000), "details": {"address": address, "error": str(exc)[:300]}, "evidence": []}
