from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


FAMILY_LABELS = {
    "wallet_drainer": "Wallet drainer",
    "credential_theft": "Credential / seed phrase theft",
    "brand_impersonation": "Brand impersonation phishing",
    "fake_airdrop": "Fake airdrop / reward claim",
    "investment_scam": "Investment / broker scam",
    "giveaway_scam": "Giveaway / doubling scam",
    "malicious_contract": "Malicious contract / token",
    "marketplace_order_abuse": "Marketplace/order signature abuse",
    "known_scam_database": "Known scam database match",
    "compromised_or_redirect": "Compromised site or malicious redirect",
    "general_crypto_risk": "General crypto risk",
}


FAMILY_RULES = {
    "wallet_drainer": {
        "codes": {
            "possible_js_drainer_flow",
            "approval_or_drain_functions",
            "wallet_drainer_runtime",
            "runtime_approval_or_drain_flow",
            "runtime_connect_plus_signature_flow",
            "runtime_connect_plus_transaction_flow",
            "obfuscated_wallet_drainer_javascript",
            "runtime_wallet_calls_with_obfuscation",
            "permit_signature_permission",
            "permit2_signature_permission",
            "signature_unlimited_allowance",
            "hidden_approval_inside_multicall",
            "hidden_permit_inside_multicall",
            "hidden_transfer_from_inside_multicall",
        },
        "words": {"drain", "drainer", "approve", "permit2", "setapprovalforall", "transferfrom", "connect wallet"},
        "base": 40,
    },
    "credential_theft": {
        "codes": {"seed_phrase_request", "private_key_request", "recovery_phrase_request", "credential_theft_ui", "runtime_secret_phrase_request", "signature_secret_phrase_request"},
        "words": {"seed phrase", "private key", "recovery phrase", "secret phrase", "mnemonic"},
        "base": 45,
    },
    "brand_impersonation": {
        "codes": {"brand_impersonation_plus_wallet_pressure", "brand_plus_scam_keywords", "visual_phishing_score", "brand_spoofing", "brand_impersonation"},
        "words": {"metamask", "coinbase", "binance", "ledger", "trezor", "phantom", "walletconnect", "support", "verify"},
        "base": 28,
    },
    "fake_airdrop": {
        "codes": {"connect_wallet_reward_flow", "fake_airdrop_bonus_ui", "wallet_connect_pressure", "host_keyword_airdrop", "host_keyword_claim", "host_keyword_reward"},
        "words": {"airdrop", "claim", "reward", "bonus", "mint", "whitelist", "allocation"},
        "base": 25,
    },
    "investment_scam": {
        "codes": {"deposit_to_activate_scam", "broker_scam", "guaranteed_profit"},
        "words": {"investment", "broker", "guaranteed profit", "daily profit", "trading platform", "deposit", "withdrawal", "activate"},
        "base": 25,
    },
    "giveaway_scam": {
        "codes": {"btc_giveaway_scam", "doubling_scam", "send_receive_scam", "celebrity_giveaway_scam"},
        "words": {"giveaway", "double", "2x", "send btc", "send eth", "elon", "musk", "vitalik"},
        "base": 25,
    },
    "malicious_contract": {
        "codes": {"known_malicious_contract_identity", "honeypot", "token_approval", "nft_collection_approval", "asset_transfer"},
        "words": {"honeypot", "blacklist", "sell tax", "transferfrom"},
        "base": 35,
    },
    "marketplace_order_abuse": {
        "codes": {"marketplace_order_signature", "delegated_wallet_permission", "raw_eth_sign_blind_signature"},
        "words": {"seaport", "order", "offerer", "consideration", "delegate", "session key"},
        "base": 25,
    },
    "known_scam_database": {
        "codes": {"noytrix_scam_database_match", "known_malicious_entity", "part_of_known_scam_campaign"},
        "words": {"scam database", "known scam"},
        "base": 35,
    },
    "compromised_or_redirect": {
        "codes": {
            "redirect_plus_behavioral_risk",
            "multi_layer_behavioral_fingerprint",
            "cross_domain_redirect",
            "suspicious_redirect",
            "compromised_legitimate_site_wallet_flow",
            "compromised_legitimate_redirect_to_lure",
            "legitimate_domain_obfuscated_wallet_flow",
            "hosted_platform_abuse_wallet_flow",
        },
        "words": {"redirect", "shortlink", "pages.dev", "vercel.app", "netlify.app"},
        "base": 20,
    },
}


def _iter_evidence(verdict: Dict[str, Any] | None, evidence_trace: Dict[str, Any] | None = None) -> Iterable[Dict[str, Any]]:
    verdict = verdict or {}
    for item in verdict.get("evidence") or []:
        if isinstance(item, dict):
            yield item
    for src in verdict.get("sources") or []:
        if not isinstance(src, dict):
            continue
        source_name = src.get("name") or src.get("source")
        for ev in src.get("evidence") or []:
            if isinstance(ev, dict):
                out = dict(ev)
                out.setdefault("source", source_name)
                yield out
    details = verdict.get("details") or {}
    for item in details.get("evidence_trace") or []:
        if isinstance(item, dict):
            yield item
    trace = evidence_trace or {}
    for item in trace.get("items") or []:
        if isinstance(item, dict):
            yield item


def _text_blob(verdict: Dict[str, Any] | None, evidence: List[Dict[str, Any]]) -> str:
    verdict = verdict or {}
    parts = [
        verdict.get("input"),
        verdict.get("normalized_input"),
        verdict.get("host"),
        verdict.get("risk_type"),
        verdict.get("what_can_happen"),
        verdict.get("worst_case"),
    ]
    details = verdict.get("details") or {}
    page = details.get("page") or {}
    parts.extend([page.get("title"), page.get("description")])
    for ev in evidence:
        parts.extend([ev.get("code"), ev.get("text"), ev.get("source"), ev.get("module")])
    return " ".join(str(x or "") for x in parts).lower()


def classify_scam_family(verdict: Dict[str, Any] | None, evidence_trace: Dict[str, Any] | None = None) -> Dict[str, Any]:
    verdict = verdict or {}
    evidence = list(_iter_evidence(verdict, evidence_trace))
    codes = {str(x.get("code") or "").lower() for x in evidence if isinstance(x, dict)}
    text = _text_blob(verdict, evidence)
    kind = str(verdict.get("kind") or "").lower()

    scores: Dict[str, Dict[str, Any]] = {}

    for family, rule in FAMILY_RULES.items():
        score = 0
        reasons: List[Dict[str, Any]] = []

        matched_codes = sorted(codes & {str(c).lower() for c in rule.get("codes") or []})
        if matched_codes:
            score += int(rule.get("base") or 20)
            score += min(50, len(matched_codes) * 14)
            reasons.append({"type": "evidence_code", "matches": matched_codes[:10]})

        matched_words = sorted({w for w in (rule.get("words") or set()) if w in text})
        if matched_words:
            score += min(28, len(matched_words) * 7)
            reasons.append({"type": "text_pattern", "matches": matched_words[:10]})

        if family == "malicious_contract" and kind in {"wallet", "contract", "transaction", "typed_signature"}:
            score += 8
        if family == "wallet_drainer" and kind in {"transaction", "typed_signature"}:
            score += 12

        if score > 0:
            scores[family] = {
                "family": family,
                "label": FAMILY_LABELS.get(family, family.replace("_", " ").title()),
                "score": min(100, score),
                "reasons": reasons,
            }

    if not scores:
        scores["general_crypto_risk"] = {
            "family": "general_crypto_risk",
            "label": FAMILY_LABELS["general_crypto_risk"],
            "score": 10 if codes or text.strip() else 0,
            "reasons": [],
        }

    ranked = sorted(scores.values(), key=lambda x: int(x.get("score") or 0), reverse=True)
    primary = ranked[0]
    confidence = min(100, max(int(primary.get("score") or 0), 40 if codes else 20))

    if len(ranked) > 1 and int(ranked[1].get("score") or 0) >= int(primary.get("score") or 0) - 10:
        confidence = max(45, confidence - 10)

    return {
        "available": True,
        "primary_family": primary.get("family"),
        "label": primary.get("label"),
        "confidence": confidence,
        "families": ranked[:6],
        "evidence_codes": sorted(codes)[:40],
        "summary": (
            f"Classified as {primary.get('label')}."
            if primary.get("family") != "general_crypto_risk" else
            "No specific scam family was confirmed."
        ),
    }


def risk_family_from_classifier(classification: Dict[str, Any] | None, fallback: str = "general_crypto_risk") -> str:
    classification = classification or {}
    return str(classification.get("primary_family") or fallback or "general_crypto_risk")
