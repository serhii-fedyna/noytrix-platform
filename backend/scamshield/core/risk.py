def normalize_score(score: int) -> int:
    try:
        score = int(score)
    except Exception:
        score = 0
    return max(0, min(100, score))


def level_from_score(score: int) -> str:
    score = normalize_score(score)
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    if score >= 15:
        return "low"
    return "safe"


def enforce_confirmed_red_flags(score: int, level: str, malicious_sources: list) -> tuple[int, str]:
    if malicious_sources:
        score = max(score, 80)
        if level in ("safe", "low", "medium"):
            level = "high"
    return normalize_score(score), level
