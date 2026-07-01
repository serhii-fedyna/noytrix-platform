def build_contract_risk_blocks(level: str, codes: set, lang: str = "en") -> dict:
    is_ru = lang == "ru"

    def has(*names):
        return any(n in codes for n in names)

    if has("honeypot_detected"):
        return {
            "what": (
                "Контракт показывает honeypot-риск: купить легче, чем продать."
                if is_ru else
                "The contract shows honeypot risk: buying may be easier than selling."
            ),
            "worst": (
                "Токены могут оказаться непродаваемыми."
                if is_ru else
                "The tokens may become impossible to sell."
            )
        }

    if has("token_approval", "wallet_drainer_hint"):
        return {
            "what": (
                "Контракт связан с рискованным approval/drainer-паттерном."
                if is_ru else
                "The contract is linked to risky approval/drainer patterns."
            ),
            "worst": (
                "Approval может дать доступ к токенам."
                if is_ru else
                "An approval may give access to the user's tokens."
            )
        }

    if has("unverified_address", "unverified_or_wallet"):
        return {
            "what": (
                "Explorer не подтвердил контракт достаточно надёжно."
                if is_ru else
                "Explorers did not strongly verify the contract."
            ),
            "worst": (
                "Скрытая логика может проявиться позже."
                if is_ru else
                "Hidden contract logic may appear later."
            )
        }

    if level == "safe":
        return {
            "what": (
                "Явных scam/honeypot-флагов не найдено."
                if is_ru else
                "No obvious scam/honeypot flags were found."
            ),
            "worst": (
                "Approval и подписи всё равно нужно проверять отдельно."
                if is_ru else
                "Approvals and signatures still must be checked separately."
            )
        }

    return {
        "what": (
            "У контракта есть риск-сигналы."
            if is_ru else
            "The contract has risk signals."
        ),
        "worst": (
            "Возможна потеря токенов через malicious logic."
            if is_ru else
            "Token loss through malicious logic is possible."
        )
    }
