def build_safe_text(lang: str = "en") -> str:
    if lang == "ru":
        return "Явных признаков скама не найдено по доступным источникам."
    return "No obvious scam signals were found in available sources."


def build_partial_scan_note(lang: str = "en") -> str:
    if lang == "ru":
        return "Проверка выполнена не полностью: часть источников недоступна."
    return "Scan is partial: some security sources are unavailable."


def build_human_explanation(level: str, coverage: dict, lang: str = "en") -> str:
    if coverage.get("partial"):
        return build_partial_scan_note(lang)

    if level in ("critical", "high"):
        return "Обнаружены серьёзные признаки риска." if lang == "ru" else "Serious risk signals were detected."

    if level == "medium":
        return "Есть подозрительные признаки. Лучше проверить дополнительно." if lang == "ru" else "Some suspicious signals were detected. Extra caution is recommended."

    return build_safe_text(lang)
