from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable

from scamshield.core.levels import normalize_score
from scamshield.core.sources import normalize_source_status


EVIDENCE_CONTRACT_VERSION = "1.0"

POSITIVE_MARKERS = (
    "hard_evidence",
    "confirmed",
    "malicious",
    "is_malicious",
    "detected",
    "matched",
)


def _text(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _timestamp(value: Any) -> str | None:
    raw = _text(value, 80)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _stable_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))[:1000]
        except (TypeError, ValueError):
            pass
    return _text(value, 1000)


def _polarity(item: dict[str, Any], severity: int) -> str:
    explicit = _text(item.get("polarity"), 20).lower()
    if explicit in {"risk", "clean", "neutral", "unknown"}:
        return explicit
    if any(item.get(marker) is True for marker in POSITIVE_MARKERS) or severity > 0:
        return "risk"
    if item.get("clean") is True or item.get("safe") is True:
        return "clean"
    return "neutral"


def canonical_evidence(
    item: dict[str, Any],
    *,
    source: str,
    source_status: str,
    entity: str | None = None,
    network: str | None = None,
    source_observed_at: str | None = None,
    source_fresh_until: str | None = None,
) -> dict[str, Any] | None:
    """Normalize one provider finding into the Noytrix evidence contract.

    Unknown provider fields are preserved under ``raw`` for debugging, but only
    contract fields may be consumed by decision policy.
    """
    if not isinstance(item, dict):
        return None

    code = _text(item.get("code") or item.get("signal_code") or item.get("id"), 120).lower()
    code = "_".join(code.replace("-", "_").split())
    if not code:
        return None

    severity = normalize_score(item.get("severity") or item.get("risk_score") or 0)
    confidence = normalize_score(item.get("confidence") if item.get("confidence") is not None else 50)
    observed_at = _timestamp(item.get("observed_at") or source_observed_at)
    fresh_until = _timestamp(item.get("fresh_until") or source_fresh_until)
    source_name = _text(item.get("source") or source, 100).lower() or "unknown"
    entity_value = _text(item.get("entity") or entity, 300)
    network_value = _text(item.get("network") or item.get("chain") or network, 40).lower()
    method = _text(item.get("method") or item.get("detector") or item.get("module"), 100)
    raw_ref = _text(
        item.get("raw_ref")
        or item.get("record_id")
        or item.get("match_id")
        or item.get("transaction")
        or item.get("tx_hash"),
        300,
    )
    value = _stable_value(item.get("value") if "value" in item else item.get("matched_value"))
    polarity = _polarity(item, severity)
    confirmed = any(item.get(marker) is True for marker in POSITIVE_MARKERS)
    hard_evidence = bool(item.get("hard_evidence") is True or confirmed)

    identity_payload = {
        "code": code,
        "entity": entity_value.lower(),
        "network": network_value,
        "raw_ref": raw_ref.lower(),
        "value": value.lower(),
        "polarity": polarity,
    }
    evidence_id = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]

    return {
        "contract_version": EVIDENCE_CONTRACT_VERSION,
        "evidence_id": evidence_id,
        "code": code,
        "source": source_name,
        "source_status": normalize_source_status(source_status),
        "entity": entity_value or None,
        "network": network_value or None,
        "polarity": polarity,
        "severity": severity,
        "confidence": confidence,
        "confirmed": confirmed,
        "hard_evidence": hard_evidence,
        "method": method or None,
        "observed_at": observed_at,
        "fresh_until": fresh_until,
        "raw_ref": raw_ref or None,
        "value": value or None,
        "text": _text(item.get("text") or item.get("message") or item.get("description"), 1000),
        "raw": dict(item),
    }


def evidence_from_sources(
    sources: Iterable[dict[str, Any]],
    *,
    entity: str | None = None,
    network: str | None = None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for src in sources or []:
        if not isinstance(src, dict):
            continue
        source_name = _text(src.get("name") or src.get("source"), 100).lower() or "unknown"
        status = normalize_source_status(_text(src.get("status"), 40))
        for item in src.get("evidence") or []:
            canonical = canonical_evidence(
                item,
                source=source_name,
                source_status=status,
                entity=entity,
                network=network,
                source_observed_at=src.get("observed_at"),
                source_fresh_until=src.get("fresh_until"),
            )
            if canonical:
                normalized.append(canonical)
    return deduplicate_evidence(normalized)


def deduplicate_evidence(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse copies of the same fact while retaining source corroboration."""
    grouped: dict[str, dict[str, Any]] = {}
    for item in items or []:
        if not isinstance(item, dict) or not item.get("evidence_id"):
            continue
        key = str(item["evidence_id"])
        current = grouped.get(key)
        if current is None:
            selected = dict(item)
            selected["corroborating_sources"] = [item.get("source")]
            selected["corroboration_count"] = 1
            grouped[key] = selected
            continue

        sources = set(current.get("corroborating_sources") or [])
        sources.add(item.get("source"))
        winner = max(
            (current, item),
            key=lambda candidate: (
                bool(candidate.get("hard_evidence")),
                int(candidate.get("confidence") or 0),
                int(candidate.get("severity") or 0),
            ),
        )
        selected = dict(winner)
        selected["corroborating_sources"] = sorted(x for x in sources if x)
        selected["corroboration_count"] = len(selected["corroborating_sources"])
        grouped[key] = selected

    return sorted(
        grouped.values(),
        key=lambda item: (
            bool(item.get("hard_evidence")),
            int(item.get("severity") or 0),
            int(item.get("confidence") or 0),
        ),
        reverse=True,
    )


def actionable_risk_evidence(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in items or []
        if item.get("polarity") == "risk"
        and item.get("source_status") == "malicious"
        and evidence_is_fresh(item)
        and (item.get("hard_evidence") is True or int(item.get("severity") or 0) >= 70)
    ]


def evidence_is_fresh(item: dict[str, Any], now: datetime | None = None) -> bool:
    """Only an explicit expired deadline makes evidence stale.

    Sources that do not yet provide freshness metadata remain usable for
    backward compatibility, while the coverage layer can report that metadata
    as a limitation. An explicitly stale record can never drive current risk.
    """
    fresh_until = _timestamp((item or {}).get("fresh_until"))
    if not fresh_until:
        return True
    deadline = datetime.fromisoformat(fresh_until)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return deadline > current.astimezone(timezone.utc)
