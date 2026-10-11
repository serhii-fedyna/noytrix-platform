from typing import Dict, List
from scamshield.core.levels import normalize_score, normalize_level, legacy_level, enforce_risk_floor
from scamshield.core.sources import scan_coverage
from scamshield.core.evidence import actionable_risk_evidence, evidence_from_sources


EXTERNAL_SOURCE_NAMES = {
    "virustotal",
    "google_safe_browsing",
    "urlscan",
    "goplus",
    "goplus_approvals",
    "goplus_counterparties",
}

INTERNAL_SOURCE_NAMES = {
    "infrastructure",
    "redirect_chain",
    "domain_age",
    "visual_phishing",
    "advanced_url_intel",
    "js_behavior",
    "js_obfuscation",
    "crypto_lure",
    "wallet_trap",
    "page_fetch",
    "noytrix_url_intelligence",
    "threat_memory",
}


def _source_name(src: dict) -> str:
    return str((src or {}).get("name") or (src or {}).get("source") or "").strip().lower()


def _is_external_source(src: dict) -> bool:
    return _source_name(src) in EXTERNAL_SOURCE_NAMES


def _is_internal_source(src: dict) -> bool:
    name = _source_name(src)
    return name in INTERNAL_SOURCE_NAMES or name not in EXTERNAL_SOURCE_NAMES


def _score_to_level(score: int, confirmed: bool = False) -> str:
    score = int(score or 0)

    if confirmed and score >= 85:
        return "critical"
    if score >= 85:
        return "critical"
    if score >= 60:
        return "danger"
    if score >= 30:
        return "suspicious"
    return "safe"


def _verdicts(level: str) -> tuple[str, str]:
    legacy = legacy_level(normalize_level(level, 0))
    verdict_en = {
        "safe": "Safe",
        "suspicious": "Suspicious",
        "danger": "Danger",
        "critical": "Critical / Scam",
    }[legacy]

    verdict_ru = {
        "safe": "Безопасно",
        "suspicious": "Подозрительно",
        "danger": "Опасно",
        "critical": "Критично / Скам",
    }[legacy]

    return verdict_en, verdict_ru


def score_scan(
    sources: List[dict],
    heuristics: List[dict],
    page_content: List[dict],
    community: Dict,
    internal_only: bool = False,
) -> dict:
    coverage = scan_coverage(sources or [])
    canonical_evidence = evidence_from_sources(sources or [])
    actionable_evidence = actionable_risk_evidence(canonical_evidence)
    internal_confirmed_score = 0
    external_confirmed_score = 0

    internal_red_flag = False
    external_red_flag = False
    confirmed_red_flag = False

    internal_malicious_sources = []
    external_malicious_sources = []
    malicious_sources = []

    internal_clean_sources = 0
    external_clean_sources = 0

    strong_codes = {
        "credential_theft_ui",
        "seed_phrase_request",
        "private_key_request",
        "recovery_phrase_request",
        "connect_wallet_reward_flow",
        "possible_js_drainer_flow",
        "approval_or_drain_functions",
        "brand_impersonation_plus_wallet_pressure",
        "multi_source_public_scam_match",
        "known_malicious_entity",
        "wallet_drainer_runtime",
        "obfuscated_wallet_drainer_javascript",
        "runtime_wallet_calls_with_obfuscation",
        "compromised_legitimate_site_wallet_flow",
        "compromised_legitimate_redirect_to_lure",
        "legitimate_domain_obfuscated_wallet_flow",
        "hosted_platform_abuse_wallet_flow",
        "gsb_match",
        "vt_detection",
        "virustotal_malicious",
        "urlscan_malicious",
        "phishtank_match",
        "openphish_match",
        "scamsniffer_match",
        "cryptoscamdb_match",
        "noytrix_scam_database_match",
        "honeypot_detected",
        "extreme_sell_tax",
        "goplus_honeypot_confirmed",
        "goplus_cannot_sell_all",
        "goplus_extreme_sell_tax",
        "active_approval_to_confirmed_malicious_spender",
        "known_malicious_contract_identity",
    }
    strong_evidence = [
        item
        for item in actionable_evidence
        if item.get("code") in strong_codes
    ]

    for s in sources or []:
        name = _source_name(s)
        status = str((s or {}).get("status") or "").lower()
        if status in {"clean", "observed", "available"}:
            if _is_external_source(s):
                external_clean_sources += 1
            else:
                internal_clean_sources += 1

    for item in strong_evidence:
        corroborating = set(item.get("corroborating_sources") or [item.get("source")])
        internal_sources = sorted(source for source in corroborating if source and source not in EXTERNAL_SOURCE_NAMES)
        external_sources = sorted(source for source in corroborating if source in EXTERNAL_SOURCE_NAMES)
        # Corroboration raises confidence, not the inherent severity of one fact.
        # Mirrored feeds and copied databases must not amplify a single event.
        evidence_weight = 55
        if internal_sources:
            internal_red_flag = True
            internal_malicious_sources.extend(internal_sources)
            internal_confirmed_score = max(internal_confirmed_score, evidence_weight)
        if external_sources:
            external_red_flag = True
            external_malicious_sources.extend(external_sources)
            external_confirmed_score = max(external_confirmed_score, evidence_weight)

    # Production verdict: Noytrix remains the final decision-maker, but trusted
    # external threat confirmations are real evidence and must affect the score.
    malicious_sources = list(dict.fromkeys(internal_malicious_sources + external_malicious_sources))
    confirmed_red_flag = bool(internal_red_flag or external_red_flag)

    heuristics_score = int(sum(int(x.get("severity") or 0) for x in (heuristics or [])))
    content_score = int(sum(int(x.get("severity") or 0) for x in (page_content or [])))

    # GLOBAL PRODUCTION SAFETY GATE:
    # Context/noise signals must never create medium/danger/critical on their own.
    # Only strong scam evidence may raise URL verdict.
    strong_scam_codes = {
        "credential_theft_ui",
        "seed_phrase_request",
        "private_key_request",
        "recovery_phrase_request",
        "connect_wallet_reward_flow",
        "brand_impersonation_plus_wallet_pressure",
        "drainer_pattern",
        "wallet_drainer",
        "known_malicious_contract_identity",
        "gsb_match",
        "vt_detection",
        "virustotal_malicious",
        "urlscan_malicious",
        "phishtank_match",
        "openphish_match",
        "scamsniffer_match",
        "cryptoscamdb_match",
        "noytrix_scam_database_match",
        "obfuscated_wallet_drainer_javascript",
        "runtime_wallet_calls_with_obfuscation",
        "compromised_legitimate_site_wallet_flow",
        "compromised_legitimate_redirect_to_lure",
        "hosted_platform_abuse_wallet_flow",
        "honeypot_detected",
        "extreme_sell_tax",
        "goplus_honeypot_confirmed",
        "goplus_cannot_sell_all",
        "goplus_extreme_sell_tax",
        "active_approval_to_confirmed_malicious_spender",
    }

    all_codes = set()

    for x in (heuristics or []):
        all_codes.add(str(x.get("code") or ""))

    for x in (page_content or []):
        all_codes.add(str(x.get("code") or ""))

    for src in (sources or []):
        for ev in ((src or {}).get("evidence") or []):
            all_codes.add(str(ev.get("code") or ""))

    has_strong_scam_evidence = bool(all_codes & strong_scam_codes)

    if not has_strong_scam_evidence and not internal_red_flag:
        heuristics_score = 0
        content_score = 0

    community_score = 0
    scam_votes = int((community or {}).get("scam_votes") or 0)
    safe_votes = int((community or {}).get("safe_votes") or 0)
    if scam_votes >= 3 and scam_votes > safe_votes:
        community_score += min(25, 8 + scam_votes * 2)

    internal_score = min(
        100,
        internal_confirmed_score
        + min(45, heuristics_score)
        + min(30, content_score)
        + min(25, community_score)
    )

    external_score = min(100, external_confirmed_score)

    final_score = internal_score

    unknown_or_failed_internal_sources = any(
        (not _is_external_source(s)) and str((s or {}).get("status") or "") in {"timeout", "error", "invalid_key", "quota", "no_data"}
        for s in (sources or [])
    )

    strong_scam_combo = any(
        str(x.get("code") or "") in {
            "brand_impersonation_plus_wallet_pressure",
            "connect_wallet_reward_flow",
        }
        for x in (heuristics or [])
    )

    internal_level = _score_to_level(internal_score, internal_red_flag)
    external_level = _score_to_level(external_score, external_red_flag)

    if internal_red_flag:
        level = "critical" if internal_score >= 85 else "danger"

    else:
        if strong_scam_combo and heuristics_score >= 40:
            level = "critical"
        elif final_score >= 80:
            level = "critical"
        elif final_score >= 50:
            level = "danger"
        elif final_score >= 25:
            level = "suspicious"
        else:
            if internal_clean_sources > 0 and not unknown_or_failed_internal_sources and heuristics_score == 0 and content_score == 0:
                level = "safe"
            elif internal_clean_sources > 0 and heuristics_score <= 5 and content_score == 0:
                level = "safe"
            else:
                level = "suspicious"

    if (
        internal_clean_sources == 0
        and internal_confirmed_score == 0
        and heuristics_score == 0
        and content_score == 0
        and community_score == 0
        and unknown_or_failed_internal_sources
        and (internal_only or external_confirmed_score == 0)
    ):
        # No evidence is not evidence of safety. Keep the numeric risk at zero,
        # but expose an unknown verdict and insufficient coverage below.
        level = "safe"
        final_score = 0
    elif level == "critical":
        final_score = max(final_score, 85)
    elif level == "danger":
        final_score = max(final_score, 60)
    elif level == "suspicious":
        final_score = max(final_score, 30)

    final_score = normalize_score(final_score)
    normalized_level = normalize_level(level, final_score)

    final_score, normalized_level = enforce_risk_floor(
        final_score,
        normalized_level,
        malicious_sources=malicious_sources,
        confirmed_red_flag=confirmed_red_flag,
    )

    level = legacy_level(normalized_level)
    verdict_en, verdict_ru = _verdicts(level)

    has_local_risk_evidence = bool(
        internal_confirmed_score
        or heuristics_score
        or content_score
        or community_score
    )
    if coverage["assessment_status"] == "insufficient_data" and has_local_risk_evidence:
        coverage = {**coverage, "partial": True, "assessment_status": "partial"}
    elif coverage["assessment_status"] == "insufficient_data" and not confirmed_red_flag:
        final_score = 0
        level = "unknown"
        normalized_level = "unknown"
        verdict_en = "Insufficient data"
        verdict_ru = "Недостаточно данных"

    unresolved_malicious_claim = any(
        str((source or {}).get("status") or "").lower() == "malicious"
        for source in (sources or [])
    ) and not confirmed_red_flag
    if (
        unresolved_malicious_claim
        and internal_clean_sources == 0
        and external_clean_sources == 0
        and not has_local_risk_evidence
    ):
        final_score = 0
        level = "unknown"
        normalized_level = "unknown"
        verdict_en = "Insufficient verified evidence"
        verdict_ru = "Недостаточно подтверждённых данных"
        coverage = {**coverage, "partial": True, "assessment_status": "partial"}

    return {
        "level": level,
        "normalized_level": normalized_level,
        "score": final_score,
        "verdict_en": verdict_en,
        "verdict_ru": verdict_ru,
        "confirmed_red_flag": confirmed_red_flag,
        "internal_red_flag": internal_red_flag,
        "external_red_flag": external_red_flag,
        "malicious_sources": malicious_sources,
        "internal_malicious_sources": internal_malicious_sources,
        "external_malicious_sources": external_malicious_sources,
        "internal_score": normalize_score(internal_score),
        "external_score": normalize_score(external_score),
        "internal_level": internal_level,
        "external_level": external_level,
        "internal_only": bool(internal_only),
        "assessment_status": coverage["assessment_status"],
        "source_coverage": coverage,
        "canonical_evidence": canonical_evidence,
        "components": {
            "internal_confirmed_signals": min(100, internal_confirmed_score),
            "external_confirmed_signals": min(100, external_confirmed_score),
            "confirmed_external_signals": min(100, external_confirmed_score),
            "heuristics": min(100, heuristics_score),
            "page_content": min(100, content_score),
            "community_votes": min(100, community_score),
        },
    }
