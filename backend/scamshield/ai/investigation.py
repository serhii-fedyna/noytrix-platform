from __future__ import annotations

from typing import Any, Dict, List


HARD_KEYWORDS = (
    "malicious",
    "drainer",
    "phishing",
    "scam",
    "blocked",
    "suspended",
    "steal",
    "approve",
    "approval",
    "permit",
    "unlimited",
    "wallet_drain",
    "obfuscated_wallet",
)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _clip(text: Any, limit: int = 240) -> str:
    s = str(text or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "..."


def _is_hard(item: Dict[str, Any]) -> bool:
    if bool(item.get("hard_evidence")):
        return True
    code = str(item.get("code") or "").lower()
    text = str(item.get("text") or "").lower()
    source = str(item.get("source") or "").lower()
    status = str(item.get("status") or "").lower()
    severity = _to_int(item.get("severity"), 0)
    safe_context = any(token in code or token in text for token in (
        "safe_match",
        "trusted_match",
        "allowlist",
        "verified_safe",
        "benign",
        "clean",
        "untrusted_match",
        "low_confidence_match",
        "context only",
    ))
    if safe_context and not any(token in code or token in text for token in ("malicious", "drainer", "phishing", "blocked", "suspended")):
        return False
    benign_lookup = any(token in code or token in text for token in (
        "checked",
        "without a listing",
        "no listing",
        "not listed",
        "no match",
        "clean",
    ))
    if benign_lookup and not any(token in code for token in ("match", "malicious", "drainer", "phishing", "blocked", "suspended")):
        return False
    if code in {"noytrix_scam_database_checked", "multichain_existing_hard_evidence"} and "match" not in text:
        return False
    has_threat_keyword = any(token in code or token in text for token in HARD_KEYWORDS)
    source_confirms_malicious = status in {"malicious", "danger", "critical"} or source in {
        "noytrix_scam_database",
        "noytrix_url_intelligence",
        "headless_sandbox",
        "runtime_contract",
    }
    return bool(has_threat_keyword and (severity >= 60 or source_confirms_malicious))


def _collect_evidence(verdict: Dict[str, Any]) -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []

    def add(item: Any, source: str, module: str = "") -> None:
        if not isinstance(item, dict):
            return
        code = str(item.get("code") or item.get("id") or "").strip()
        text = str(item.get("text") or item.get("summary") or item.get("reason") or "").strip()
        if not code and not text:
            return
        row = {
            "source": item.get("source") or source,
            "module": item.get("module") or module or source,
            "code": code or source,
            "severity": _to_int(item.get("severity") or item.get("score"), 0),
            "text": _clip(text or code),
            "hard_evidence": bool(item.get("hard_evidence")),
            "raw": item,
        }
        row["hard_evidence"] = _is_hard(row)
        collected.append(row)

    for item in verdict.get("evidence") or []:
        add(item, "verdict_evidence", str((item or {}).get("source") or "verdict"))

    for src in verdict.get("sources") or []:
        if not isinstance(src, dict):
            continue
        src_name = str(src.get("name") or src.get("source") or "source")
        for item in src.get("evidence") or []:
            add(item, src_name, src_name)

    details = verdict.get("details") or {}
    if isinstance(details, dict):
        for item in details.get("evidence_trace") or []:
            add(item, "evidence_trace", "score_trace")
        internal = details.get("internal_verdict") or {}
        if isinstance(internal, dict):
            for item in internal.get("evidence") or []:
                add(item, "internal_verdict", "internal_verdict")

    runtime_contract = verdict.get("runtime_contract") or details.get("runtime_contract") if isinstance(details, dict) else {}
    if isinstance(runtime_contract, dict):
        for code in runtime_contract.get("reason_codes") or []:
            add({"code": code, "severity": verdict.get("score"), "text": f"Runtime contract reason code: {code}."}, "runtime_contract", "runtime_contract")

    multi = verdict.get("multi_chain_intelligence") or details.get("multi_chain_intelligence") if isinstance(details, dict) else {}
    if isinstance(multi, dict):
        for item in multi.get("signals") or []:
            add(item, "multi_chain_intelligence", "multi_chain_intelligence")

    dedup: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    for item in collected:
        key = (str(item.get("source")), str(item.get("code")), str(item.get("text")))
        old = dedup.get(key)
        if old is None or _to_int(item.get("severity")) > _to_int(old.get("severity")):
            dedup[key] = item

    return sorted(
        dedup.values(),
        key=lambda x: (1 if x.get("hard_evidence") else 0, _to_int(x.get("severity"))),
        reverse=True,
    )[:30]


def _family_label(verdict: Dict[str, Any]) -> str:
    family = verdict.get("scam_family") or {}
    if isinstance(family, dict):
        return str(family.get("primary_family") or family.get("family") or "").strip()
    return ""


def _build_summary(verdict: Dict[str, Any], evidence_links: List[Dict[str, Any]]) -> str:
    level = str(verdict.get("level") or "unknown").lower()
    score = _to_int(verdict.get("score"), 0)
    family = _family_label(verdict)
    hard_count = sum(1 for item in evidence_links if item.get("hard_evidence"))

    if hard_count:
        label = family.replace("_", " ") if family else "high-risk behavior"
        return f"Noytrix found {hard_count} hard evidence item(s) consistent with {label}; current verdict is {level} at score {score}."
    if level == "safe" and score < 30:
        return f"Noytrix found no linked threat evidence in this response; current verdict is {level} at score {score}."
    if evidence_links:
        return f"Noytrix found contextual signals but no hard proof of a scam; current verdict is {level} at score {score}."
    return f"Noytrix found no linked evidence in the current response; current verdict is {level} at score {score}."


def build_ai_investigation(verdict: Dict[str, Any]) -> Dict[str, Any]:
    verdict = dict(verdict or {})
    raw_evidence = _collect_evidence(verdict)
    evidence_links = []

    for idx, item in enumerate(raw_evidence, 1):
        evidence_links.append({
            "id": f"E{idx}",
            "source": item.get("source"),
            "module": item.get("module"),
            "code": item.get("code"),
            "severity": _to_int(item.get("severity"), 0),
            "text": item.get("text"),
            "hard_evidence": bool(item.get("hard_evidence")),
        })

    hard_links = [item for item in evidence_links if item.get("hard_evidence")]
    level = str(verdict.get("level") or "unknown").lower()
    score = _to_int(verdict.get("score"), 0)
    family = _family_label(verdict)
    multi = verdict.get("multi_chain_intelligence") or ((verdict.get("details") or {}).get("multi_chain_intelligence") if isinstance(verdict.get("details"), dict) else {})
    chain_label = multi.get("chain_label") if isinstance(multi, dict) else None

    if hard_links:
        primary = family.replace("_", " ") if family else "confirmed high-risk behavior"
        confidence = min(98, max(70, score, max(_to_int(x.get("severity")) for x in hard_links)))
    elif level == "safe" and score < 30:
        primary = "no linked threat evidence in this response"
        confidence = min(70, max(35, 100 - score))
    elif evidence_links:
        primary = "contextual risk requiring caution"
        confidence = min(75, max(35, score))
    else:
        primary = "no linked threat evidence in this response"
        confidence = min(60, max(20, score))

    attack_path = []
    permissions = verdict.get("permissions_summary") or {}
    if permissions.get("unlimited"):
        attack_path.append("User grants unlimited token spending permission.")
    if verdict.get("runtime_behavior"):
        attack_path.append("Runtime behavior is evaluated before the wallet action is allowed.")
    if verdict.get("execution_graph") or verdict.get("recursive_execution_graph"):
        attack_path.append("Execution graph links the visible action to possible hidden follow-up calls.")
    if family:
        attack_path.append(f"Classifier groups the behavior as {family.replace('_', ' ')}.")
    if chain_label:
        attack_path.append(f"Chain context is {chain_label}.")
    if not attack_path:
        attack_path.append("No complete attack path is confirmed from the current evidence.")

    recommended = []
    if level in {"critical", "danger", "high"} or score >= 70:
        recommended.extend([
            "Do not sign or approve this interaction.",
            "Disconnect the wallet from the site.",
            "If already signed, review and revoke token approvals immediately.",
        ])
    elif level in {"suspicious", "warning", "medium"} or score >= 30:
        recommended.extend([
            "Avoid connecting a main wallet until the source is verified.",
            "Check the official project domain and repeat the scan before signing.",
        ])
    else:
        recommended.extend([
            "Continue with normal caution.",
            "Scan every future signature or transaction separately.",
        ])

    confirmed = [f"{item['id']}: {item['text']}" for item in hard_links[:8]]
    if not confirmed:
        confirmed = ["No hard scam evidence is confirmed by the linked evidence in this response."]

    not_confirmed = []
    if not hard_links:
        not_confirmed.append("A scam is not confirmed without stronger evidence.")
    if not verdict.get("wallet_drain_simulation") and not verdict.get("signature_simulation"):
        not_confirmed.append("Exact asset loss is not confirmed unless a transaction or signature simulation is available.")
    if not_confirmed == []:
        not_confirmed.append("Exact attacker identity is not confirmed by the current response.")

    return {
        "available": True,
        "version": "1.0",
        "engine": "noytrix_evidence_linked_investigator",
        "summary": _build_summary(verdict, evidence_links),
        "primary_hypothesis": primary,
        "confidence": confidence,
        "severity": score,
        "level": level,
        "scam_family": family,
        "chain_context": {
            "chain": multi.get("chain") if isinstance(multi, dict) else None,
            "chain_family": multi.get("chain_family") if isinstance(multi, dict) else None,
            "chain_label": chain_label,
        },
        "evidence_links": evidence_links,
        "timeline": [
            {"step": 1, "event": "Input normalized and classified by backend."},
            {"step": 2, "event": "Sources, internal memory, runtime signals, and graph context are scored."},
            {"step": 3, "event": "Evidence-linked investigation summarizes only facts present in the verdict."},
        ],
        "attack_path": attack_path,
        "what_is_confirmed": confirmed,
        "what_is_not_confirmed": not_confirmed,
        "recommended_actions": recommended,
        "open_questions": [
            "Does a live transaction or signature payload expose exact token permissions?",
            "Are there fresh user reports or telemetry events for this entity?",
            "Does the same entity appear across multiple chains or campaigns?",
        ],
        "guardrails": [
            "This layer does not invent facts outside backend evidence.",
            "Weak evidence is described as weak; chain format alone is not treated as risk.",
            "Safe verdicts never mean guaranteed safe forever.",
        ],
    }
