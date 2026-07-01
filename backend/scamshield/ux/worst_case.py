def build_worst_case(level: str, kind: str, lang: str = "en") -> str:
    if kind == "url":
        if lang == "ru":
            return "Главный риск: сайт может позже попросить seed-фразу, приватный ключ, approve или подозрительную подпись."
        return "Main risk: the site may later ask for a seed phrase, private key, wallet approval, or suspicious signature."

    if kind in ("wallet", "contract"):
        if lang == "ru":
            return "Главный риск: адрес может быть связан с выводом средств, опасными approvals или скам-активностью."
        return "Main risk: the address may be linked to fund draining, dangerous approvals, or scam activity."

    return "Оставшийся риск зависит от дальнейших действий пользователя." if lang == "ru" else "Remaining risk depends on the user's next actions."
