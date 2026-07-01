def fallback_what_can_happen(kind: str = "", lang: str = "en") -> str:
    if lang == "ru":
        return "Объект может быть безопасным, но риск зависит от дальнейших действий пользователя."
    return "The object may be safe, but risk depends on the user's next actions."


def fallback_worst_case(kind: str = "", lang: str = "en") -> str:
    if lang == "ru":
        return "В худшем случае можно потерять средства, если подтвердить вредоносное действие."
    return "Worst case: funds may be lost if a malicious action is approved."


def ensure_ux_risk_blocks(data: dict, lang: str = "en") -> dict:
    if not isinstance(data, dict):
        return data

    kind = data.get("kind") or data.get("input_kind") or ""

    data["what_can_happen"] = data.get("what_can_happen") or fallback_what_can_happen(kind, lang)
    data["worst_case"] = data.get("worst_case") or fallback_worst_case(kind, lang)

    return data
