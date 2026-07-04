from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


RE_EVM = re.compile(r"^0x[a-fA-F0-9]{40}$")
RE_TRON = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
RE_BTC = re.compile(r"^(bc1|[13])[a-zA-HJ-NP-Z0-9]{25,62}$")
RE_SOL = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
RE_TON = re.compile(r"^(EQ|UQ)[A-Za-z0-9_-]{46,}$")


EVM_CHAIN_HINTS = {
    "1": ("ethereum", "Ethereum"),
    "eth": ("ethereum", "Ethereum"),
    "ethereum": ("ethereum", "Ethereum"),
    "56": ("bsc", "BNB Smart Chain"),
    "bsc": ("bsc", "BNB Smart Chain"),
    "binance": ("bsc", "BNB Smart Chain"),
    "8453": ("base", "Base"),
    "base": ("base", "Base"),
    "137": ("polygon", "Polygon"),
    "polygon": ("polygon", "Polygon"),
    "matic": ("polygon", "Polygon"),
    "42161": ("arbitrum", "Arbitrum"),
    "arbitrum": ("arbitrum", "Arbitrum"),
    "10": ("optimism", "Optimism"),
    "optimism": ("optimism", "Optimism"),
    "43114": ("avalanche", "Avalanche"),
    "avalanche": ("avalanche", "Avalanche"),
    "avax": ("avalanche", "Avalanche"),
}

SUPPORTED_CHAINS = [
    "ethereum",
    "bsc",
    "base",
    "polygon",
    "arbitrum",
    "optimism",
    "avalanche",
    "tron",
    "bitcoin",
    "ton",
    "solana",
]


def _flatten_values(value: Any) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: List[str] = []
        for key in ("chain", "chainId", "chain_id", "network", "platform", "source_chain"):
            if value.get(key) is not None:
                out.append(str(value.get(key)))
        return out
    if isinstance(value, (list, tuple, set)):
        out: List[str] = []
        for item in value:
            out.extend(_flatten_values(item))
        return out
    return [str(value)]


def _chain_hint(hints: Any = None) -> tuple[str | None, str | None]:
    for raw in _flatten_values(hints):
        key = str(raw or "").strip().lower()
        if key in EVM_CHAIN_HINTS:
            return EVM_CHAIN_HINTS[key]
    return None, None


def detect_chain(value: str, hints: Any = None) -> Dict[str, Any]:
    address = str(value or "").strip()
    hint_chain, hint_label = _chain_hint(hints)

    if RE_EVM.match(address):
        chain = hint_chain or "evm"
        label = hint_label or "EVM compatible"
        return {
            "available": True,
            "address": address,
            "chain": chain,
            "chain_family": "evm",
            "chain_label": label,
            "supported": True,
            "confidence": 95 if hint_chain else 85,
        }

    if RE_TRON.match(address):
        return {
            "available": True,
            "address": address,
            "chain": "tron",
            "chain_family": "tron",
            "chain_label": "Tron",
            "supported": True,
            "confidence": 94,
        }

    if RE_BTC.match(address):
        return {
            "available": True,
            "address": address,
            "chain": "bitcoin",
            "chain_family": "bitcoin",
            "chain_label": "Bitcoin",
            "supported": True,
            "confidence": 92,
        }

    if RE_TON.match(address):
        return {
            "available": True,
            "address": address,
            "chain": "ton",
            "chain_family": "ton",
            "chain_label": "TON",
            "supported": True,
            "confidence": 92,
        }

    if RE_SOL.match(address):
        return {
            "available": True,
            "address": address,
            "chain": "solana",
            "chain_family": "solana",
            "chain_label": "Solana",
            "supported": True,
            "confidence": 82,
        }

    return {
        "available": False,
        "address": address,
        "chain": hint_chain,
        "chain_family": None,
        "chain_label": hint_label,
        "supported": False,
        "confidence": 0,
    }


def _collect_evidence_codes(evidence: Any = None, sources: Any = None) -> set[str]:
    codes: set[str] = set()

    def add(item: Any) -> None:
        if isinstance(item, dict) and item.get("code"):
            codes.add(str(item.get("code")).lower())

    for item in evidence or []:
        add(item)
    for src in sources or []:
        if not isinstance(src, dict):
            continue
        for item in src.get("evidence") or []:
            add(item)
    return codes


def _is_hard_risk_code(code: str) -> bool:
    value = str(code or "").lower()
    benign_tokens = (
        "checked",
        "no_match",
        "not_listed",
        "no_listing",
        "clean",
        "without_listing",
    )
    if any(token in value for token in benign_tokens):
        return False
    return any(token in value for token in ("malicious", "drainer", "phishing", "blocked", "suspended", "wallet_drain"))


def _signal(code: str, severity: int, text: str, hard: bool = False) -> Dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "text": text,
        "hard_evidence": hard,
        "module": "multi_chain_intelligence",
    }


def build_multichain_intelligence(
    value: str,
    kind: str = "",
    sources: Any = None,
    evidence: Any = None,
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    metadata = dict(metadata or {})
    chain_info = detect_chain(value, metadata)
    evidence_codes = _collect_evidence_codes(evidence, sources)
    family = chain_info.get("chain_family")
    label = chain_info.get("chain_label")

    signals: List[Dict[str, Any]] = []
    limitations: List[str] = []

    if family == "evm":
        signals.append(_signal(
            "multichain_evm_address",
            0,
            "Address uses the EVM format and can exist on Ethereum, BSC, Base, Polygon, Arbitrum, Optimism, Avalanche, and other EVM networks.",
        ))
        if chain_info.get("chain") != "evm":
            signals.append(_signal(
                "evm_chain_context_hint",
                0,
                f"Backend context points this EVM address to {label}.",
            ))
    elif family == "tron":
        signals.append(_signal(
            "multichain_tron_address",
            0,
            "Address uses the Tron format; TRC20 approvals and transfers should be checked with Tron-specific intelligence.",
        ))
    elif family == "bitcoin":
        signals.append(_signal(
            "multichain_bitcoin_address",
            0,
            "Address uses the Bitcoin format; UTXO activity and scam reports are evaluated separately from token approvals.",
        ))
    elif family == "ton":
        signals.append(_signal(
            "multichain_ton_address",
            0,
            "Address uses the TON wallet format; TON status and reputation signals should be shown as TON-specific context.",
        ))
    elif family == "solana":
        signals.append(_signal(
            "multichain_solana_address",
            0,
            "Address uses the Solana format; SPL token authority and account interaction risk need Solana-specific analysis.",
        ))

    hard_codes = {code for code in evidence_codes if _is_hard_risk_code(code)}
    if hard_codes:
        signals.append(_signal(
            "multichain_existing_hard_evidence",
            80,
            "Existing verdict evidence already contains hard risk signals; chain context must not downgrade the verdict.",
            True,
        ))

    if chain_info.get("available"):
        limitations.append("This layer identifies the chain family and attaches chain-specific context.")
        limitations.append("Full on-chain tracing still depends on the configured chain providers and available source data.")
    else:
        limitations.append("The input was not recognized as a supported chain address.")

    return {
        "available": bool(chain_info.get("available")),
        "version": "1.0",
        "input": value,
        "kind": kind or metadata.get("kind") or "",
        "address": chain_info.get("address"),
        "chain": chain_info.get("chain"),
        "chain_family": chain_info.get("chain_family"),
        "chain_label": chain_info.get("chain_label"),
        "supported": bool(chain_info.get("supported")),
        "supported_chains": SUPPORTED_CHAINS,
        "confidence": int(chain_info.get("confidence") or 0),
        "signals": signals,
        "risk_context": {
            "hard_evidence_codes": sorted(hard_codes)[:20],
            "has_existing_hard_evidence": bool(hard_codes),
            "score_adjustment": 0,
            "policy": "chain context never raises risk without independent evidence",
        },
        "limitations": limitations,
        "recommended_frontend_sections": [
            "chain",
            "chain_family",
            "signals",
            "limitations",
            "risk_context",
        ],
    }
