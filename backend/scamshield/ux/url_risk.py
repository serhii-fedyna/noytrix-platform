def build_url_risk_blocks(level: str, host: str, codes: set, lang: str = "en") -> dict:
    is_ru = lang == "ru"

    def has(*names):
        return any(n in codes for n in names)

    if has("brand_spoofing", "brand_impersonation", "brand_plus_scam_keywords") and ("metamask" in host):
        return {
            "what": (
                "Это похоже на фейковую страницу MetaMask. Она может увести тебя на поддельную поддержку, подключение кошелька или вредную подпись."
                if is_ru else
                "This looks like a fake MetaMask page. It may push you into fake support, wallet connection, or a malicious signature."
            ),
            "worst": (
                "Худший сценарий: ты подключишь кошелёк или подпишешь действие, после чего злоумышленник сможет украсть активы."
                if is_ru else
                "Worst case: you connect your wallet or sign an action, allowing an attacker to steal assets."
            )
        }

    if has("gsb_match", "vt_detection"):
        return {
            "what": (
                "Внешние security-источники уже отметили этот объект как угрозу."
                if is_ru else
                "External security sources already flagged this as a threat."
            ),
            "worst": (
                "Худший сценарий: сайт может использовать phishing или malicious redirects."
                if is_ru else
                "Worst case: the site may use phishing or malicious redirects."
            )
        }

    if level == "safe":
        return {
            "what": (
                "По этой ссылке не найдено явных scam-сигналов."
                if is_ru else
                "No obvious scam signals were found for this link."
            ),
            "worst": (
                "Риск появится только если сайт позже запросит wallet approval или seed phrase."
                if is_ru else
                "Risk appears only if the site later requests wallet approval or a seed phrase."
            )
        }

    return {
        "what": (
            "Есть риск-сигналы по ссылке."
            if is_ru else
            "There are risk signals for this link."
        ),
        "worst": (
            "Худший сценарий зависит от следующего действия пользователя."
            if is_ru else
            "Worst case depends on the user's next action."
        )
    }
