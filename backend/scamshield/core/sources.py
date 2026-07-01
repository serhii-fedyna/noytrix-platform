VALID_SOURCE_STATUSES = {
    "clean",
    "suspicious",
    "malicious",
    "error",
    "unavailable",
    "quota",
    "invalid_key",
    "unknown",
    "observed",
}


def normalize_source_status(status: str) -> str:
    s = (status or "unknown").lower().strip()
    if s in VALID_SOURCE_STATUSES:
        return s
    if s in ("ok", "safe"):
        return "clean"
    if s in ("warn", "warning"):
        return "suspicious"
    if s in ("bad", "danger", "scam"):
        return "malicious"
    return "unknown"


def source_is_failed(status: str) -> bool:
    return normalize_source_status(status) in {"error", "unavailable", "quota", "invalid_key"}


def scan_coverage(sources: list) -> dict:
    total = len(sources or [])
    failed = 0
    active = 0

    for s in sources or []:
        status = normalize_source_status(s.get("status"))
        if source_is_failed(status):
            failed += 1
        else:
            active += 1

    return {
        "total": total,
        "active": active,
        "failed": failed,
        "partial": failed > 0,
    }
