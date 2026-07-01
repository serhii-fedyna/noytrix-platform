def build_tx_risk_blocks(tx: dict, permissions: dict, lang: str = "en") -> dict:
    tx = tx or {}
    permissions = permissions or {}

    is_ru = lang == "ru"

    method = str(tx.get("method") or "")
    spender = str(tx.get("spender") or "").strip()
    spender_label = str(permissions.get("spender_label") or "").strip()
    spender_trust = str(permissions.get("spender_trust") or "").lower().strip()
    spender_part = spender_label or spender

    tokens = permissions.get("tokens") or tx.get("tokens") or []
    token_names = ", ".join([str(x) for x in tokens if x])
    token_ru = token_names if token_names else "токены"
    token_en = token_names if token_names else "tokens"

    if tx.get("type") == "erc20_approve" and tx.get("unlimited"):
        if spender_trust == "trusted":
            return {
                "what": (
                    f"Ты даёшь безлимитный доступ к {token_ru} доверенному spender: {spender_part}."
                    if is_ru else
                    f"You are giving unlimited {token_en} access to a trusted spender: {spender_part}."
                ),
                "worst": (
                    "Если ты ошибся сайтом, разрешённые токены могут быть списаны без новой подписи."
                    if is_ru else
                    "If you are on the wrong site, approved tokens can be spent without another signature."
                )
            }

        if spender_trust == "unknown":
            return {
                "what": (
                    f"Ты даёшь безлимитный доступ к {token_ru} неизвестному spender: {spender_part}. Это высокий риск."
                    if is_ru else
                    f"You are giving unlimited {token_en} access to an unknown spender: {spender_part}. This is high risk."
                ),
                "worst": (
                    "Неизвестный spender сможет позже списать все разрешённые токены без новой подписи."
                    if is_ru else
                    "The unknown spender can later drain all approved tokens without another signature."
                )
            }

        return {
            "what": (
                f"Эта подпись вызывает {method} и даёт spender {spender_part} разрешение списывать {token_ru} без лимита."
                if is_ru else
                f"This signature calls {method} and gives spender {spender_part} unlimited {token_en} spending permission."
            ),
            "worst": (
                "Если spender вредный, он сможет позже списать все разрешённые токены без новой подписи."
                if is_ru else
                "If the spender is malicious, it can later drain all approved tokens without another signature."
            )
        }

    if tx.get("type") == "erc20_approve":
        amount = str(tx.get("amount_raw") or "unknown")
        return {
            "what": (
                f"Эта подпись вызывает {method} и разрешает spender {spender} списать сумму: {amount}."
                if is_ru else
                f"This signature calls {method} and allows spender {spender} to spend amount: {amount}."
            ),
            "worst": (
                "Разрешённая сумма может быть списана spender-адресом."
                if is_ru else
                "The approved amount can be spent by the spender address."
            )
        }

    if tx.get("type") == "erc20_transfer_from":
        return {
            "what": (
                "Это transferFrom: транзакция пытается переместить токены от одного адреса к другому."
                if is_ru else
                "This is transferFrom: the transaction attempts to move tokens from one address to another."
            ),
            "worst": (
                "Если действие неожиданное, токены могут быть переведены без понимания пользователем."
                if is_ru else
                "If unexpected, tokens may be moved without the user understanding the action."
            )
        }

    if tx.get("type") == "erc20_transfer":
        return {
            "what": (
                "Это обычный transfer токенов на другой адрес."
                if is_ru else
                "This is a regular token transfer to another address."
            ),
            "worst": (
                "Средства уйдут на указанный адрес, если ты подтверждаешь не того получателя."
                if is_ru else
                "Funds go to the specified address if you confirm the wrong recipient."
            )
        }

    return {
        "what": (
            "Обнаружены данные EVM-транзакции, но метод пока не распознан."
            if is_ru else
            "EVM transaction data was detected, but the method is not recognized yet."
        ),
        "worst": (
            "Худший сценарий зависит от метода транзакции и адреса получателя."
            if is_ru else
            "Worst case depends on the transaction method and recipient address."
        )
    }
