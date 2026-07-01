CANONICAL_LEVELS = {"safe", "low", "medium", "high", "critical"}

LEGACY_TO_CANONICAL = {
    "safe": "safe",
    "clean": "safe",
    "ok": "safe",

    "watch": "low",
    "info": "low",

    "suspicious": "medium",
    "warning": "medium",
    "warn": "medium",

    "high": "high",
    "danger": "high",
    "dangerous": "high",
    "malicious": "high",
    "scam": "critical",

    "critical": "critical",
}


def normalize_level(level: str, score: int | None = None) -> str:
    raw = str(level or "").lower().strip()
    if raw in LEGACY_TO_CANONICAL:
        return LEGACY_TO_CANONICAL[raw]

    if score is not None:
        try:
            s = int(score)
        except Exception:
            s = 0

        if s >= 85:
            return "critical"
        if s >= 60:
            return "high"
        if s >= 35:
            return "medium"
        if s >= 15:
            return "low"
        return "safe"

    return "safe"


def legacy_level(level: str) -> str:
    lvl = normalize_level(level, None)
    if lvl == "safe":
        return "safe"
    if lvl == "low":
        return "suspicious"
    if lvl == "medium":
        return "suspicious"
    if lvl == "high":
        return "danger"
    if lvl == "critical":
        return "critical"
    return "safe"


def normalize_score(score) -> int:
    try:
        s = int(score)
    except Exception:
        s = 0
    return max(0, min(100, s))


def level_from_score(score) -> str:
    return normalize_level("", normalize_score(score))


def enforce_risk_floor(score, level, malicious_sources=None, confirmed_red_flag=False):
    score = normalize_score(score)
    level = normalize_level(level, score)

    if confirmed_red_flag or malicious_sources:
        score = max(score, 80)
        if level in {"safe", "low", "medium"}:
            level = "high"

    return score, level
