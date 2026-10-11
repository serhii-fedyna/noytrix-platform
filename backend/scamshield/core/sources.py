VALID_SOURCE_STATUSES = {
    "available",
    "clean",
    "suspicious",
    "malicious",
    "error",
    "unavailable",
    "quota",
    "invalid_key",
    "unknown",
    "observed",
    "no_data",
    "timeout",
    "source_unavailable",
    "insufficient_data",
}


SOURCE_CAPABILITIES = {
    "page_fetch": {"website_reachability", "website_content"},
    "virustotal": {"threat_reputation"},
    "google_safe_browsing": {"threat_reputation"},
    "urlscan": {"threat_reputation", "website_content", "website_infrastructure"},
    "noytrix_url_intelligence": {"threat_reputation", "website_behavior", "website_infrastructure"},
    "noytrix_scam_database": {"threat_reputation"},
    "threat_memory": {"threat_reputation"},
    "headless_sandbox": {"website_behavior"},
    "js_behavior": {"website_behavior"},
    "infrastructure": {"website_infrastructure"},
    "redirect_chain": {"website_infrastructure"},
    "domain_age": {"website_infrastructure"},
    "coingecko": {"token_identity", "market_data"},
    "dexscreener": {"token_identity", "market_data", "liquidity"},
    "honeypot": {"sellability", "token_controls", "holder_distribution"},
    "goplus": {"token_identity", "token_controls", "holder_distribution", "sellability", "threat_reputation"},
    "goplus_approvals": {"permission_analysis", "token_balances", "wallet_exposure", "threat_reputation"},
    "goplus_counterparties": {"threat_reputation", "transaction_history"},
    "noytrix_counterparties": {"transaction_history"},
    "wallet_flow_graph": {"transaction_history", "fund_flow_graph"},
    "solana_rpc": {"chain_state", "token_identity", "token_controls", "holder_distribution", "transaction_history"},
    "evm_rpc": {"chain_state", "contract_code", "token_controls"},
    "etherscan": {"chain_state", "contract_code", "transaction_history"},
    "bscscan": {"chain_state", "contract_code", "transaction_history"},
    "tronscan": {"chain_state", "transaction_history"},
    "tonapi": {"chain_state", "transaction_history"},
    "blockchair": {"chain_state", "transaction_history"},
    "noytrix_identity": {"threat_reputation"},
}


REQUIRED_CAPABILITIES = {
    "url": {"website_reachability", "website_content", "website_behavior", "website_infrastructure", "threat_reputation"},
    "domain": {"website_reachability", "website_content", "website_behavior", "website_infrastructure", "threat_reputation"},
    "website": {"website_reachability", "website_content", "website_behavior", "website_infrastructure", "threat_reputation"},
    "token": {"token_identity", "market_data", "liquidity", "token_controls", "holder_distribution", "sellability", "threat_reputation"},
    "ticker": {"token_identity", "market_data", "liquidity", "token_controls", "holder_distribution", "sellability", "threat_reputation"},
    "contract": {"chain_state", "contract_code", "token_controls", "threat_reputation"},
    "program": {"chain_state", "token_controls", "threat_reputation"},
    "wallet": {"chain_state", "transaction_history", "threat_reputation"},
    "address": {"chain_state", "threat_reputation"},
    "transaction": {"chain_state", "transaction_simulation", "threat_reputation"},
    "typed_signature": {"signature_decode", "permission_analysis"},
}

SAFE_VERDICT_CAPABILITIES = {
    "url": {"website_reachability", "website_content", "website_behavior", "threat_reputation"},
    "domain": {"website_reachability", "website_content", "website_behavior", "threat_reputation"},
    "website": {"website_reachability", "website_content", "website_behavior", "threat_reputation"},
    "token": {"token_identity", "liquidity", "token_controls", "holder_distribution", "sellability", "threat_reputation"},
    "ticker": {"token_identity", "liquidity", "token_controls", "holder_distribution", "sellability", "threat_reputation"},
    "contract": {"chain_state", "contract_code", "token_controls", "threat_reputation"},
    "program": {"chain_state", "token_controls", "threat_reputation"},
    "wallet": {"chain_state", "transaction_history", "threat_reputation"},
    "address": {"chain_state", "threat_reputation"},
    "transaction": {"chain_state", "transaction_simulation", "threat_reputation"},
    "typed_signature": {"signature_decode", "permission_analysis"},
}


def normalize_source_status(status: str) -> str:
    s = (status or "unknown").lower().strip()
    if s in VALID_SOURCE_STATUSES:
        return s
    if s in ("ok", "safe"):
        return "clean"
    if s in ("warn", "warning"):
        return "suspicious"
    if s in ("bad", "danger", "scam"):
        return "malicious"
    return "unknown"


def source_is_failed(status: str) -> bool:
    return normalize_source_status(status) in {"error", "unavailable", "source_unavailable", "timeout", "quota", "invalid_key"}


def scan_coverage(sources: list) -> dict:
    total = len(sources or [])
    failed = 0
    active = 0

    for s in sources or []:
        status = normalize_source_status(s.get("status"))
        if source_is_failed(status):
            failed += 1
        elif status not in {"unknown", "no_data", "insufficient_data"}:
            active += 1

    return {
        "total": total,
        "active": active,
        "failed": failed,
        "partial": failed > 0,
        "assessment_status": "insufficient_data" if active == 0 else ("partial" if failed else "available"),
    }


def source_capabilities(source: dict) -> set[str]:
    explicit = source.get("capabilities") if isinstance(source, dict) else None
    if isinstance(explicit, (list, tuple, set)):
        return {str(item).strip().lower() for item in explicit if str(item).strip()}
    name = str((source or {}).get("name") or (source or {}).get("source") or "").strip().lower()
    return set(SOURCE_CAPABILITIES.get(name, set()))


def capability_coverage(sources: list, entity_type: str | None, additional_capabilities: list[str] | None = None) -> dict:
    entity = str(entity_type or "unknown").strip().lower()
    required = set(REQUIRED_CAPABILITIES.get(entity, set()))
    available: set[str] = set()
    failed: set[str] = set()
    declared: set[str] = set()
    for capability in additional_capabilities or []:
        value = str(capability).strip().lower()
        if value:
            declared.add(value)
            available.add(value)

    for source in sources or []:
        if not isinstance(source, dict):
            continue
        capabilities = source_capabilities(source)
        declared.update(capabilities)
        status = normalize_source_status(source.get("status"))
        if status in {"available", "clean", "suspicious", "malicious", "observed"}:
            available.update(capabilities)
        elif source_is_failed(status):
            failed.update(capabilities)

    missing = required - available
    failed_required = failed & missing
    if not required:
        assessment = "insufficient_data" if not available else "partial"
    elif not available:
        assessment = "insufficient_data"
    elif missing:
        assessment = "partial"
    else:
        assessment = "available"

    return {
        "entity_type": entity,
        "required_capabilities": sorted(required),
        "available_capabilities": sorted(available),
        "missing_capabilities": sorted(missing),
        "failed_capabilities": sorted(failed_required),
        "declared_capabilities": sorted(declared),
        "coverage_ratio": round(len(required & available) / len(required), 4) if required else 0.0,
        "assessment_status": assessment,
        "partial": assessment == "partial",
    }


def safe_verdict_coverage(capability_report: dict, entity_type: str | None) -> dict:
    entity = str(entity_type or "unknown").strip().lower()
    required = set(SAFE_VERDICT_CAPABILITIES.get(entity, set()))
    available = set((capability_report or {}).get("available_capabilities") or [])
    missing = required - available
    return {
        "entity_type": entity,
        "required_capabilities": sorted(required),
        "available_capabilities": sorted(required & available),
        "missing_capabilities": sorted(missing),
        "eligible": bool(required) and not missing,
    }
