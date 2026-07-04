import asyncio
from typing import Dict


async def build_spender_reputation(
    address: str,
    re_evm_addr,
    get_db_rep,
    normalize_rep,
    malicious_book,
    trusted_book,
    explorer_checker,
) -> Dict:

    addr = str(address or "").lower().strip()

    if not re_evm_addr.match(addr):
        return {
            "address": addr,
            "status": "invalid",
            "label": None,
            "trust": "unknown",
            "risk": "unknown",
            "reasons": ["invalid_evm_address"],
        }

    bad = malicious_book.get(addr)
    if bad:
        return normalize_rep({
            "address": addr,
            "status": "known_malicious",
            "label": bad.get("label"),
            "category": bad.get("category"),
            "trust": "malicious",
            "risk": "critical",
            "reasons": ["known_wallet_drainer_spender"],
        }, addr)

    known = trusted_book.get(addr)
    if known:
        return normalize_rep({
            "address": addr,
            "status": "known",
            "label": known.get("label"),
            "category": known.get("category"),
            "trust": known.get("trust") or "trusted",
            "risk": "low",
            "reasons": ["known_trusted_spender"],
        }, addr)

    db_rep = get_db_rep(addr)
    if db_rep:
        return db_rep

    eth_res, bsc_res = await asyncio.gather(
        explorer_checker(addr, "eth"),
        explorer_checker(addr, "bsc"),
        return_exceptions=True,
    )

    sources = []

    for r in [eth_res, bsc_res]:
        if isinstance(r, dict):
            sources.append(r)

    verified = []
    names = []
    proxy = False
    recent_tx = 0

    for s in sources:
        d = s.get("details") or {}

        if d.get("verified_contract"):
            verified.append(str(s.get("name") or "explorer"))

            if d.get("contract_name"):
                names.append(str(d.get("contract_name")))

        if d.get("is_proxy"):
            proxy = True

        try:
            recent_tx = max(
                recent_tx,
                int(d.get("recent_tx_sample_count") or 0)
            )
        except Exception:
            pass

    if verified:
        return normalize_rep({
            "address": addr,
            "status": "verified",
            "label": names[0] if names else None,
            "trust": "medium",
            "risk": "medium",
            "verified_on": verified,
            "is_proxy": proxy,
            "recent_tx_sample_count": recent_tx,
            "reasons": ["verified_contract", "not_in_trusted_book"],
        }, addr)

    return normalize_rep({
        "address": addr,
        "status": "unknown",
        "label": None,
        "trust": "unknown",
        "risk": "high",
        "verified_on": [],
        "is_proxy": proxy,
        "recent_tx_sample_count": recent_tx,
        "reasons": ["unknown_or_unverified_spender"],
    }, addr)
