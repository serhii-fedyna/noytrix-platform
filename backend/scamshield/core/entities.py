from __future__ import annotations

import hashlib
import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit


EVM_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
TRON_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
BTC_RE = re.compile(r"^(bc1|[13])[a-zA-HJ-NP-Z0-9]{25,62}$")
SOLANA_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
TON_RE = re.compile(r"^(EQ|UQ)[A-Za-z0-9_-]{46,}$")
DOMAIN_RE = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,63}$", re.I)
TICKER_RE = re.compile(r"^[A-Z0-9._-]{2,15}$")


def _result(
    raw: str,
    *,
    syntax: str,
    normalized: str,
    network: str | None,
    candidates: list[str],
    resolution_status: str,
    confidence: int,
    route_kind: str,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "contract_version": "1.0",
        "raw": raw,
        "syntax": syntax,
        "normalized": normalized,
        "network": network,
        "candidate_types": candidates,
        "resolved_type": candidates[0] if len(candidates) == 1 and resolution_status == "resolved" else None,
        "resolution_status": resolution_status,
        "confidence": max(0, min(100, int(confidence))),
        "route_kind": route_kind,
        "limitations": limitations or [],
    }


def resolve_input_syntax(value: str) -> dict[str, Any]:
    """Resolve only what can be proven from syntax.

    Address roles are deliberately ambiguous until chain data confirms whether
    they are wallets, token contracts/mints, programs, or other accounts.
    """
    raw = str(value or "").strip()
    if not raw:
        return _result(raw, syntax="empty", normalized="", network=None, candidates=[], resolution_status="invalid", confidence=100, route_kind="text", limitations=["empty_input"])

    if raw.lower().startswith(("http://", "https://")):
        try:
            parsed = urlsplit(raw)
            host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
            if not host:
                raise ValueError("missing_host")
            port = f":{parsed.port}" if parsed.port else ""
            normalized = urlunsplit((parsed.scheme.lower(), host + port, parsed.path or "/", parsed.query, ""))
            return _result(raw, syntax="url", normalized=normalized, network=None, candidates=["website"], resolution_status="resolved", confidence=100, route_kind="url")
        except (ValueError, UnicodeError):
            return _result(raw, syntax="url", normalized=raw, network=None, candidates=["website"], resolution_status="invalid", confidence=100, route_kind="url", limitations=["invalid_url"])

    domain = raw.lower().rstrip(".")
    try:
        ascii_domain = domain.encode("idna").decode("ascii")
    except UnicodeError:
        ascii_domain = domain
    if DOMAIN_RE.fullmatch(ascii_domain):
        return _result(raw, syntax="domain", normalized=ascii_domain, network=None, candidates=["website"], resolution_status="resolved", confidence=100, route_kind="domain")

    try:
        ip = ipaddress.ip_address(raw)
        return _result(raw, syntax="ip_address", normalized=ip.compressed, network=str(ip.version), candidates=["infrastructure"], resolution_status="resolved", confidence=100, route_kind="infrastructure")
    except ValueError:
        pass

    if EVM_RE.fullmatch(raw):
        return _result(raw, syntax="evm_address", normalized=raw.lower(), network="evm_unknown", candidates=["wallet", "contract", "token"], resolution_status="ambiguous", confidence=100, route_kind="address", limitations=["network_required", "onchain_role_required"])
    if TRON_RE.fullmatch(raw):
        return _result(raw, syntax="tron_address", normalized=raw, network="tron", candidates=["wallet", "contract", "token"], resolution_status="ambiguous", confidence=100, route_kind="address", limitations=["onchain_role_required"])
    btc_match = bool(BTC_RE.fullmatch(raw))
    solana_match = bool(SOLANA_RE.fullmatch(raw))
    if btc_match and solana_match:
        return _result(raw, syntax="cross_chain_address", normalized=raw, network=None, candidates=["wallet", "token", "program", "account"], resolution_status="ambiguous", confidence=100, route_kind="address", limitations=["network_required", "bitcoin_solana_syntax_collision", "onchain_role_required"])
    if btc_match:
        return _result(raw, syntax="bitcoin_address", normalized=raw, network="bitcoin", candidates=["wallet"], resolution_status="resolved", confidence=100, route_kind="address")
    if TON_RE.fullmatch(raw):
        return _result(raw, syntax="ton_address", normalized=raw, network="ton", candidates=["wallet", "contract", "token"], resolution_status="ambiguous", confidence=100, route_kind="address", limitations=["onchain_role_required"])
    if solana_match:
        return _result(raw, syntax="solana_address", normalized=raw, network="solana", candidates=["wallet", "token", "program", "account"], resolution_status="ambiguous", confidence=100, route_kind="address", limitations=["onchain_role_required"])

    upper = raw.upper()
    if " " not in raw and TICKER_RE.fullmatch(upper) and not raw.lower().startswith("0x"):
        return _result(raw, syntax="ticker", normalized=upper, network=None, candidates=["token"], resolution_status="ambiguous", confidence=70, route_kind="ticker", limitations=["ticker_not_unique", "contract_or_mint_required_for_exact_identity"])

    digest = hashlib.sha256(raw.lower().encode("utf-8")).hexdigest()[:24]
    return _result(raw, syntax="text", normalized=raw, network=None, candidates=["text"], resolution_status="resolved", confidence=100, route_kind="text", limitations=[f"text_id:{digest}"])


def canonical_entity_id(resolution: dict[str, Any], resolved_type: str | None = None, network: str | None = None) -> str:
    normalized = str((resolution or {}).get("normalized") or "").strip()
    entity_type = str(resolved_type or (resolution or {}).get("resolved_type") or "ambiguous").lower()
    chain = str(network or (resolution or {}).get("network") or "unknown").lower()
    syntax = str((resolution or {}).get("syntax") or "unknown").lower()
    if syntax in {"url", "domain"}:
        host = urlsplit(normalized if "://" in normalized else f"https://{normalized}").hostname or normalized
        return f"website:{host.lower().removeprefix('www.')}"
    if syntax.endswith("_address") or syntax == "evm_address":
        return f"{chain}:{entity_type}:{normalized.lower() if syntax == 'evm_address' else normalized}"
    if syntax == "ticker":
        return f"ticker:ambiguous:{normalized}"
    return f"{entity_type}:{hashlib.sha256(normalized.lower().encode()).hexdigest()[:24]}"
