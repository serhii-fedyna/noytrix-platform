from __future__ import annotations

from typing import Any, Dict, List


INTERNAL_SOURCE_NAMES = {
    "domain_age",
    "redirect_chain",
    "wallet_trap",
    "crypto_lure",
    "js_behavior",
    "headless_sandbox",
    "infrastructure",
    "visual_phishing",
    "advanced_url_intel",
    "page_fetch",
}


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _level(score: int) -> str:
    if score >= 90:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    if score > 0:
        return "low"
    return "safe"


def build_url_intelligence(
    sources: List[Dict[str, Any]],
    heuristics: List[Dict[str, Any]],
    page_content: List[Dict[str, Any]],
    threat_memory: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    sources = sources or []
    heuristics = heuristics or []
    page_content = page_content or []

    internal_sources = [
        s for s in sources
        if str(s.get("name") or s.get("source") or "").lower() in INTERNAL_SOURCE_NAMES
    ]

    signals = []

    for src in internal_sources:
        name = str(src.get("name") or src.get("source") or "unknown")
        status = str(src.get("status") or "").lower()
        verdict = str(src.get("verdict") or "").lower()
        details = src.get("details") or {}
        evidence = src.get("evidence") or []

        # Production rule:
        # If a detector was suppressed/cleaned by anti-false-positive logic,
        # its old details.score must NOT continue to create risk.
        source_is_clean = status in {"clean", "safe"} or verdict in {"clean", "safe"}
        suppressed = bool((details or {}).get("suppressed_by"))

        if not source_is_clean and not suppressed:
            for ev in evidence:
                severity = _safe_int(ev.get("severity"))
                if severity > 0:
                    signals.append({
                        "source": name,
                        "code": ev.get("code"),
                        "severity": severity,
                        "text": ev.get("text"),
                    })

            details_score = _safe_int(details.get("score"))
            if details_score > 0:
                signals.append({
                    "source": name,
                    "code": f"{name}_score",
                    "severity": details_score,
                    "text": details.get("summary") or f"{name} produced risk score.",
                })

    for h in heuristics:
        severity = _safe_int(h.get("severity"))
        if severity > 0:
            signals.append({
                "source": "heuristic",
                "code": h.get("code"),
                "severity": severity,
                "text": h.get("text"),
            })

    for p in page_content:
        severity = _safe_int(p.get("severity"))
        if severity > 0:
            signals.append({
                "source": "page_content",
                "code": p.get("code"),
                "severity": severity,
                "text": p.get("text"),
            })

    threat_memory = threat_memory or {}

    memory_score = _safe_int(threat_memory.get("score"))
    memory_level = str(threat_memory.get("level") or "").lower()

    if memory_score > 0 or memory_level in {"critical", "high", "danger", "suspicious"}:
        # Production rule:
        # Historical memory is context, not proof.
        # It must NOT create danger/critical by itself without fresh independent signals.
        signals.append({
            "source": "threat_memory",
            "code": "historical_threat_memory",
            "severity": min(max(memory_score, 10), 30),
            "text": "Noytrix threat memory contains historical context for this entity.",
        })

    signals_sorted = sorted(signals, key=lambda x: _safe_int(x.get("severity")), reverse=True)

    score = 0
    if signals_sorted:
        score = max(_safe_int(x.get("severity")) for x in signals_sorted)

        # Multiple independent internal signals should raise confidence/risk.
        independent_sources = {str(x.get("source") or "") for x in signals_sorted}
        if len(independent_sources) >= 2:
            score = min(100, score + 10)
        if len(independent_sources) >= 3:
            score = min(100, score + 10)

    signal_sources = {
        str(x.get("source") or "").lower()
        for x in signals_sorted
        if _safe_int(x.get("severity")) > 0
    }

    only_memory_signal = signal_sources == {"threat_memory"}

    if only_memory_signal and score > 0:
        # Memory-only risk must never become high/critical.
        score = min(score, 30)

    # Production global anti-false-positive rule:
    # Weak informational Web3 / infra / memory signals must not escalate normal websites.
    # Medium/high/critical requires a real strong phishing/scam signal.
    _strong_danger_codes = {
        "credential_theft_ui",
        "connect_wallet_reward_flow",
        "brand_impersonation",
        "brand_impersonation_plus_wallet_pressure",
        "brand_fragment_in_suspicious_domain",
        "brand_spoofing",
        "brand_plus_scam_keywords",
        "domain_resolution_failed",
        "dns_no_ip_records",
        "suspicious_host_words",
        "host_keyword_claim",
        "host_keyword_airdrop",
        "host_keyword_reward",
        "host_keyword_wallet",
        "hyphenated_suspicious_host",
        "fake_airdrop_bonus_ui",
        "wallet_connect_pressure",
        "fake_support_ui",
        "seed_phrase_request",
        "private_key_request",
        "recovery_phrase_request",
        "runtime_approval_or_drain_flow",
        "runtime_secret_phrase_request",
        "runtime_connect_plus_signature_flow",
        "runtime_connect_plus_transaction_flow",
        "headless_possible_js_drainer_flow",
        "headless_approval_or_drain_functions",
    }

    _weak_noise_codes = {
        "historical_threat_memory",
        "missing_ns_records",
        "infrastructure_score",
        "wallet_connect_request",
        "runtime_wallet_connect_request",
        "runtime_many_script_loads",
        "headless_wallet_connect_request",
        "web3_script_reference",
        "visual_phishing_score",
        "wallet_trap_score",
        "crypto_lure_score",
        "brand_name_in_page_not_domain",
        "page_loaded",
        "redirect_chain_observed",
        "advanced_url_intel_checked",
        "crypto_lure_checked",
        "visual_phishing_checked",
        "js_behavior_checked",
        "wallet_trap_checked",
    }

    _has_strong_danger_signal = any(
        str(x.get("code") or "") in _strong_danger_codes
        or (
            _safe_int(x.get("severity")) >= 70
            and str(x.get("source") or "").lower() != "threat_memory"
            and str(x.get("code") or "") not in _weak_noise_codes
        )
        for x in signals_sorted
    )

    if score > 0 and not _has_strong_danger_signal:
        # If all we have is weak/noisy context, do not produce medium/high/critical.
        score = min(score, 20)

    confirmed_internal_red_flag = any(
        _safe_int(x.get("severity")) >= 80
        and str(x.get("source") or "").lower() != "threat_memory"
        for x in signals_sorted
    )

    confidence = 40
    if internal_sources:
        confidence += 20
    if signals_sorted:
        confidence += min(35, len(signals_sorted) * 7)
    if confirmed_internal_red_flag:
        confidence = max(confidence, 85)

    confidence = min(100, confidence)

    return {
        "available": True,
        "source": "noytrix_url_intelligence",
        "score": score,
        "level": _level(score),
        "confidence": confidence,
        "confirmed_internal_red_flag": confirmed_internal_red_flag,
        "only_memory_signal": only_memory_signal,
        "signals_count": len(signals_sorted),
        "top_signals": signals_sorted[:10],
        "internal_sources": [
            str(s.get("name") or s.get("source") or "unknown") for s in internal_sources
        ],
        "summary": (
            "Noytrix internal URL intelligence found risk signals."
            if score > 0 else
            "Noytrix internal URL intelligence found no strong internal risk signals."
        ),
    }
