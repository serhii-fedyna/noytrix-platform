from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


MALICIOUS_STATUSES = {"malicious", "scam", "danger", "critical", "high", "blocked"}
SAFE_STATUSES = {"safe", "trusted", "allowlisted", "allowlist"}
OBSERVED_STATUSES = {"suspicious", "observed", "quarantine"}


def clamp_score(value: Any, minimum: int = 0, maximum: int = 100) -> int:
    try:
        number = int(round(float(value or 0)))
    except Exception:
        number = minimum
    return max(minimum, min(maximum, number))


def source_trust_from_stats(row: Dict[str, Any]) -> Dict[str, Any]:
    raw_count = int(row.get("raw_indicator_count") or 0)
    promoted_count = int(row.get("promoted_entity_count") or 0)
    true_positive_count = int(row.get("true_positive_count") or 0)
    false_positive_count = int(row.get("false_positive_count") or 0)
    avg_confidence = float(row.get("avg_confidence") or 0)
    avg_risk_score = float(row.get("avg_risk_score") or 0)

    volume_bonus = min(20, raw_count // 100000)
    promotion_bonus = min(15, promoted_count // 250)
    confidence_bonus = min(15, int(avg_confidence // 8))
    risk_consistency_bonus = 8 if avg_risk_score >= 70 else 4 if avg_risk_score >= 40 else 0
    true_positive_bonus = min(12, true_positive_count * 2)
    false_positive_penalty = min(35, false_positive_count * 8)

    trust = clamp_score(
        35
        + volume_bonus
        + promotion_bonus
        + confidence_bonus
        + risk_consistency_bonus
        + true_positive_bonus
        - false_positive_penalty,
        20,
        98,
    )

    return {
        "trust_score": trust,
        "signals": {
            "volume_bonus": volume_bonus,
            "promotion_bonus": promotion_bonus,
            "confidence_bonus": confidence_bonus,
            "risk_consistency_bonus": risk_consistency_bonus,
            "true_positive_bonus": true_positive_bonus,
            "false_positive_penalty": false_positive_penalty,
        },
    }


def _freshness_score(value: Any) -> int:
    if not value:
        return 0
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return 0
    if not isinstance(value, datetime):
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    days = max(0, int((datetime.now(timezone.utc) - value.astimezone(timezone.utc)).total_seconds() // 86400))
    if days <= 7:
        return 10
    if days <= 30:
        return 7
    if days <= 90:
        return 4
    return 1


def build_reputation_context(
    *,
    status: str,
    base_confidence: int,
    observations: Iterable[Dict[str, Any]] | None = None,
    source_reputation: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = [dict(x) for x in (observations or []) if isinstance(x, dict)]
    status_l = str(status or "").lower()
    base = clamp_score(base_confidence)

    if not rows and source_reputation:
        rows = [{
            "source_name": source_reputation.get("source_name") or "unknown",
            "status": status_l or "observed",
            "risk_score": 0,
            "confidence": base,
            "trust_score": source_reputation.get("trust_score") or 50,
            "last_seen_at": source_reputation.get("last_seen_at"),
        }]

    source_names = sorted({str(x.get("source_name") or "unknown") for x in rows})
    source_count = len(source_names)
    trust_scores = [clamp_score(x.get("trust_score") or 50) for x in rows]
    avg_source_trust = clamp_score(sum(trust_scores) / max(1, len(trust_scores)))
    max_source_trust = max(trust_scores) if trust_scores else 0

    statuses = Counter(str(x.get("status") or "observed").lower() for x in rows)
    malicious_count = sum(statuses.get(x, 0) for x in MALICIOUS_STATUSES)
    safe_count = sum(statuses.get(x, 0) for x in SAFE_STATUSES)
    observed_count = sum(statuses.get(x, 0) for x in OBSERVED_STATUSES)

    if status_l in MALICIOUS_STATUSES:
        aligned = malicious_count
        conflicting = safe_count
    elif status_l in SAFE_STATUSES:
        aligned = safe_count
        conflicting = malicious_count
    else:
        aligned = observed_count
        conflicting = 0

    independent_bonus = min(15, max(0, source_count - 1) * 5)
    trust_bonus = max(0, min(18, (avg_source_trust - 50) // 3))
    alignment_bonus = min(12, aligned * 4)
    freshness_bonus = max([_freshness_score(x.get("last_seen_at")) for x in rows] or [0])
    conflict_penalty = min(30, conflicting * 12)
    low_trust_penalty = 10 if rows and avg_source_trust < 40 else 0

    adjusted = clamp_score(
        base
        + independent_bonus
        + trust_bonus
        + alignment_bonus
        + freshness_bonus
        - conflict_penalty
        - low_trust_penalty,
        0,
        99,
    )

    return {
        "version": "1.0",
        "base_confidence": base,
        "adjusted_confidence": adjusted,
        "source_count": source_count,
        "avg_source_trust": avg_source_trust,
        "max_source_trust": max_source_trust,
        "aligned_observations": aligned,
        "conflicting_observations": conflicting,
        "status_counts": dict(statuses),
        "top_sources": sorted(
            [
                {
                    "source_name": str(x.get("source_name") or "unknown"),
                    "trust_score": clamp_score(x.get("trust_score") or 50),
                    "status": str(x.get("status") or "observed").lower(),
                    "risk_score": clamp_score(x.get("risk_score") or 0),
                    "confidence": clamp_score(x.get("confidence") or 0),
                }
                for x in rows
            ],
            key=lambda x: (x["trust_score"], x["confidence"], x["risk_score"]),
            reverse=True,
        )[:8],
        "signals": {
            "independent_source_bonus": independent_bonus,
            "trust_bonus": trust_bonus,
            "alignment_bonus": alignment_bonus,
            "freshness_bonus": freshness_bonus,
            "conflict_penalty": conflict_penalty,
            "low_trust_penalty": low_trust_penalty,
        },
    }
