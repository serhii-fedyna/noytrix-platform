from __future__ import annotations

from typing import Any, Dict, List

from scamshield.core.levels import legacy_level, normalize_level, normalize_score
from scamshield.intelligence.scam_family import classify_scam_family, risk_family_from_classifier


EXTERNAL_REFERENCE_SOURCES = {
    "virustotal",
    "google_safe_browsing",
    "urlscan",
    "external_sources",
}


def _source_name(src: dict) -> str:
    return str((src or {}).get("name") or (src or {}).get("source") or "").strip().lower()


def _is_external_source(src: dict) -> bool:
    return _source_name(src) in EXTERNAL_REFERENCE_SOURCES


def _compact_evidence(item: dict, authority: str) -> dict:
    return {
        "source": item.get("source") or item.get("module") or authority,
        "module": item.get("module"),
        "code": item.get("code") or "unknown",
        "severity": normalize_score(item.get("severity") or 0),
        "text": item.get("text") or item.get("message") or "",
        "hard_evidence": bool(item.get("hard_evidence")),
        "generic_web3_noise": bool(item.get("generic_web3_noise")),
        "authority": authority,
    }


def _evidence_from_sources(sources: List[dict]) -> tuple[list[dict], list[dict]]:
    internal: list[dict] = []
    external: list[dict] = []

    for src in sources or []:
        if not isinstance(src, dict):
            continue
        authority = "external_reference" if _is_external_source(src) else "internal"
        bucket = external if authority == "external_reference" else internal
        name = _source_name(src) or "source"
        for ev in src.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            item = dict(ev)
            item.setdefault("source", name)
            bucket.append(_compact_evidence(item, authority))

    return internal, external


def _risk_family(evidence: List[dict], kind: str) -> str:
    codes = {str(x.get("code") or "").lower() for x in evidence if isinstance(x, dict)}

    if codes & {"seed_phrase_request", "private_key_request", "recovery_phrase_request", "credential_theft_ui"}:
        return "credential_theft"
    if codes & {"possible_js_drainer_flow", "approval_or_drain_functions", "wallet_drainer_runtime"}:
        return "wallet_drainer"
    if codes & {"noytrix_scam_database_match", "known_malicious_entity", "part_of_known_scam_campaign"}:
        return "known_scam_database"
    if codes & {"brand_impersonation_plus_wallet_pressure", "brand_plus_scam_keywords", "visual_phishing_score"}:
        return "brand_impersonation"
    if str(kind or "").lower() in {"wallet", "contract", "transaction", "tx", "typed_signature"}:
        return "web3_runtime"
    return "general_crypto_risk"


def build_internal_verdict(
    *,
    kind: str,
    target: str,
    score_info: Dict[str, Any],
    sources: List[dict] | None = None,
    evidence_trace: Dict[str, Any] | None = None,
    community: Dict[str, Any] | None = None,
    noytrix_database: Dict[str, Any] | None = None,
    graph_context: Dict[str, Any] | None = None,
    reputation_context: Dict[str, Any] | None = None,
    runtime_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build the first-party Noytrix verdict envelope.

    This core treats external providers as reference evidence only. The top-level
    API can keep legacy fields, but the decision trace here is the internal truth
    that products should inspect for explanation and debugging.
    """

    score_info = dict(score_info or {})
    trace = evidence_trace or {}
    sources = sources or []

    internal_from_sources, external_reference = _evidence_from_sources(sources)
    trace_items = [
        _compact_evidence(x, "internal")
        for x in (trace.get("items") or [])
        if isinstance(x, dict)
    ]

    internal_evidence = sorted(
        trace_items + internal_from_sources,
        key=lambda x: int(x.get("severity") or 0),
        reverse=True,
    )

    level = legacy_level(score_info.get("level") or normalize_level("", score_info.get("score")))
    score = normalize_score(score_info.get("score") or 0)
    confidence = normalize_score(
        score_info.get("confidence_score")
        or score_info.get("confidence")
        or (90 if trace.get("hard_evidence_found") else 60 if score >= 30 else 75)
    )

    db = noytrix_database or score_info.get("noytrix_scam_database") or {}
    db_applied = bool(db.get("applied"))
    safety = score_info.get("false_positive_safety_gate") or {}
    hard_codes = trace.get("hard_evidence_codes") or []
    generic_codes = trace.get("generic_noise_codes") or []
    top_internal = internal_evidence[:8]

    source_weights = {
        "noytrix_database": 100 if db_applied else 0,
        "internal_evidence": min(100, sum(int(x.get("severity") or 0) for x in top_internal[:5])),
        "community": normalize_score((community or {}).get("scam_votes") or 0),
        "external_reference": min(100, sum(int(x.get("severity") or 0) for x in external_reference[:5])),
    }
    family_context = {
        "kind": kind,
        "input": target,
        "normalized_input": target,
        "score": score,
        "level": level,
        "evidence": top_internal,
        "sources": sources,
        "details": {
            "evidence_trace": trace.get("items") or [],
            "runtime_context": runtime_context or {},
        },
    }
    scam_family = classify_scam_family(family_context, trace)

    decision_reasons: list[str] = []
    if db_applied:
        decision_reasons.append(str(db.get("reason") or "noytrix_database_decision"))
    if hard_codes:
        decision_reasons.append("hard_internal_evidence")
    if safety.get("applied"):
        decision_reasons.append("false_positive_safety_gate_applied")
    if not decision_reasons and top_internal:
        decision_reasons.append("internal_evidence_scoring")
    if not decision_reasons:
        decision_reasons.append("no_confirmed_internal_threat")

    return {
        "engine": "noytrix_internal_verdict_core",
        "version": "1.0",
        "authority": "internal",
        "target": target,
        "kind": kind,
        "level": level,
        "score": score,
        "confidence": confidence,
        "risk_family": risk_family_from_classifier(scam_family, _risk_family(top_internal, kind)),
        "scam_family": scam_family,
        "risk_reasons": decision_reasons,
        "evidence": top_internal,
        "external_reference_evidence": sorted(
            external_reference,
            key=lambda x: int(x.get("severity") or 0),
            reverse=True,
        )[:8],
        "source_weights": source_weights,
        "internal_decision_trace": {
            "final_level": level,
            "final_score": score,
            "internal_level": score_info.get("internal_level"),
            "internal_score": score_info.get("internal_score"),
            "external_level": score_info.get("external_level"),
            "external_score": score_info.get("external_score"),
            "external_sources_are_reference_only": True,
            "database_applied": db_applied,
            "hard_evidence_found": bool(trace.get("hard_evidence_found")),
            "hard_evidence_codes": hard_codes,
            "generic_noise_codes": generic_codes,
        },
        "false_positive_controls": {
            "safety_gate": safety,
            "generic_noise_codes": generic_codes,
        },
        "graph_context": graph_context or {},
        "reputation_context": reputation_context or {},
        "runtime_context": runtime_context or {},
    }
