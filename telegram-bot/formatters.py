from i18n import t


def short(s: str, n: int = 90) -> str:
    s = str(s or "").strip()
    return s if len(s) <= n else s[: n - 3] + "..."


def tr_level(lang: str, level: str) -> str:
    level = str(level or "").lower()
    if level == "safe":
        return t(lang, "safe")
    if level == "suspicious":
        return t(lang, "suspicious")
    return t(lang, "danger")


def tr_source_name(name: str) -> str:
    names = {
        "virustotal": "VirusTotal",
        "google_safe_browsing": "Google Safe Browsing",
        "urlscan": "urlscan",
        "page_fetch": "Page Fetch",
        "etherscan": "Etherscan",
        "bscscan": "BscScan",
        "honeypot": "Honeypot",
        "dexscreener": "DexScreener",
        "noytrix_scam_database": "Noytrix Scam Database",
        "noytrix_url_intelligence": "Noytrix URL Intelligence",
    }
    return names.get(str(name or "").lower(), str(name or ""))


def backend_signal_text(item) -> str:
    if not isinstance(item, dict):
        return str(item or "")
    return (
        item.get("text")
        or item.get("reason")
        or item.get("code")
        or item.get("source")
        or item.get("label")
        or ""
    )


def investigation_label(lang: str, key: str) -> str:
    labels = {
        "ru": {
            "title": "AI-\u0440\u0430\u0441\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u043d\u0438\u0435",
            "attack": "\u041a\u0430\u0440\u0442\u0430 \u0430\u0442\u0430\u043a\u0438",
            "chain": "\u0421\u0435\u0442\u044c",
            "runtime": "Runtime",
            "reputation": "\u0420\u0435\u043f\u0443\u0442\u0430\u0446\u0438\u044f",
        },
        "uk": {
            "title": "AI-\u0440\u043e\u0437\u0441\u043b\u0456\u0434\u0443\u0432\u0430\u043d\u043d\u044f",
            "attack": "\u041a\u0430\u0440\u0442\u0430 \u0430\u0442\u0430\u043a\u0438",
            "chain": "\u041c\u0435\u0440\u0435\u0436\u0430",
            "runtime": "Runtime",
            "reputation": "\u0420\u0435\u043f\u0443\u0442\u0430\u0446\u0456\u044f",
        },
        "en": {
            "title": "AI investigation",
            "attack": "Attack map",
            "chain": "Chain",
            "runtime": "Runtime",
            "reputation": "Reputation",
        },
    }
    return labels.get(lang, labels["en"]).get(key, key)


def investigation_rows(data: dict, lang: str) -> list[str]:
    details = data.get("details") or {}
    investigation = data.get("ai_investigation") or details.get("ai_investigation") or {}
    multi = data.get("multi_chain_intelligence") or details.get("multi_chain_intelligence") or {}
    runtime = data.get("runtime_contract") or details.get("runtime_contract") or {}
    graph = data.get("graph") or details.get("graph") or (details.get("internal_verdict") or {}).get("graph_context") or {}
    reputation = data.get("reputation") or details.get("reputation") or (details.get("internal_verdict") or {}).get("reputation_context") or data.get("threat_memory") or {}
    rows = []

    if investigation.get("primary_hypothesis") or investigation.get("summary"):
        evidence_links = investigation.get("evidence_links") or []
        suffix = f" ({len(evidence_links)} evidence links)" if evidence_links else ""
        rows.append(f"<b>{investigation_label(lang, 'title')}:</b> {short(investigation.get('primary_hypothesis') or investigation.get('summary'), 150)}{suffix}")

    attack_path = investigation.get("attack_path") or []
    if attack_path:
        rows.append(f"<b>{investigation_label(lang, 'attack')}:</b>")
        for idx, step in enumerate(attack_path[:4], 1):
            rows.append(f"{idx}. {short(step, 130)}")

    if multi.get("available") or multi.get("chain_label"):
        rows.append(f"<b>{investigation_label(lang, 'chain')}:</b> {short(multi.get('chain_label') or multi.get('chain') or 'unknown', 80)}")

    if "should_warn" in runtime or "should_block" in runtime:
        rows.append(f"<b>{investigation_label(lang, 'runtime')}:</b> warn={runtime.get('should_warn')} · block={runtime.get('should_block')}")

    if graph.get("available") or graph.get("nodes") or reputation.get("risk_score") or reputation.get("level") or reputation.get("memory_level"):
        rep = reputation.get("level") or reputation.get("memory_level") or reputation.get("risk_level") or reputation.get("risk_score") or "context"
        rows.append(f"<b>{investigation_label(lang, 'reputation')}:</b> {short(rep, 80)}")

    return rows[:10]


def tr_status(lang: str, status: str) -> str:
    status = str(status or "").lower()
    if lang == "ru":
        m = {
            "clean": "Чисто",
            "malicious": "Опасно",
            "danger": "Опасно",
            "suspicious": "Подозрительно",
            "no_data": "Нет данных",
            "error": "Ошибка",
            "timeout": "Таймаут",
            "invalid_key": "Источник недоступен",
            "quota": "Лимит источника",
        }
    elif lang == "uk":
        m = {
            "clean": "Чисто",
            "malicious": "Небезпечно",
            "danger": "Небезпечно",
            "suspicious": "Підозріло",
            "no_data": "Немає даних",
            "error": "Помилка",
            "timeout": "Таймаут",
            "invalid_key": "Джерело недоступне",
            "quota": "Ліміт джерела",
        }
    else:
        m = {
            "clean": "Clean",
            "malicious": "Danger",
            "danger": "Danger",
            "suspicious": "Suspicious",
            "no_data": "No data",
            "error": "Error",
            "timeout": "Timeout",
            "invalid_key": "Source unavailable",
            "quota": "Source limit",
        }
    return m.get(status, status or "—")


def tr_kind(lang: str, kind: str) -> str:
    kind = str(kind or "").lower()
    ru = {
        "url": "Ссылка",
        "domain": "Домен",
        "wallet": "Кошелёк",
        "contract": "Контракт",
        "ticker": "Тикер",
        "text": "Текст",
        "tx": "Транзакция",
        "transaction": "Транзакция",
    }
    uk = {
        "url": "Посилання",
        "domain": "Домен",
        "wallet": "Гаманець",
        "contract": "Контракт",
        "ticker": "Тікер",
        "text": "Текст",
        "tx": "Транзакція",
        "transaction": "Транзакція",
    }
    en = {
        "url": "Link",
        "domain": "Domain",
        "wallet": "Wallet",
        "contract": "Contract",
        "ticker": "Ticker",
        "text": "Text",
        "tx": "Transaction",
        "transaction": "Transaction",
    }
    return {"ru": ru, "uk": uk}.get(lang, en).get(kind, kind or "—")


def tr_phrase(lang: str, key: str) -> str:
    d = {
        "ru": {
            "external": "Внешние источники",
            "heuristics": "Эвристика",
            "page": "Страница",
            "community": "Сообщество",
            "possible_impact": "🛡 Возможное влияние",
            "verification_sources": "🔎 Источники проверки",
            "community_signals": "👥 Сигналы сообщества",
            "permissions_unknown": "Точные разрешения видны только из транзакции/подписи.",
            "community_unknown": "неизвестно",
            "pro_unlimited": "∞ PRO · безлимитные проверки",
            "free_left": "🟠 FREE · осталось проверок сегодня: {left}/{limit}",
            "worst_case": "Худший сценарий:",
        },
        "uk": {
            "external": "Зовнішні джерела",
            "heuristics": "Евристика",
            "page": "Сторінка",
            "community": "Спільнота",
            "possible_impact": "🛡 Можливий вплив",
            "verification_sources": "🔎 Джерела перевірки",
            "community_signals": "👥 Сигнали спільноти",
            "permissions_unknown": "Точні дозволи видно лише з транзакції/підпису.",
            "community_unknown": "невідомо",
            "pro_unlimited": "∞ PRO · безлімітні перевірки",
            "free_left": "🟠 FREE · залишилось перевірок сьогодні: {left}/{limit}",
            "worst_case": "Найгірший сценарій:",
        },
        "en": {
            "external": "External",
            "heuristics": "Heuristics",
            "page": "Page",
            "community": "Community",
            "possible_impact": "🛡 Possible Impact",
            "verification_sources": "🔎 Verification Sources",
            "community_signals": "👥 Community Signals",
            "permissions_unknown": "Exact permissions are visible only from the transaction/signature.",
            "community_unknown": "unknown",
            "pro_unlimited": "∞ PRO · unlimited checks",
            "free_left": "🟠 FREE · {left}/{limit} checks left today",
            "worst_case": "Worst case:",
        },
    }
    return d.get(lang, d["en"]).get(key, key)


def localize_evidence(lang: str, text: str) -> str:
    text = str(text or "")
    low = text.lower()

    if lang == "ru":
        if "domain imitates a trusted brand" in low:
            return "домен похож на подделку известного бренда"
        if "host mixes trusted-brand wording" in low:
            return "домен смешивает название известного бренда с фишинговыми словами"
        if "host contains well-known brand fragment" in low:
            return "домен содержит фрагмент известного бренда, но не является официальным доменом"
        if "domain does not resolve" in low or "could not be resolved" in low:
            return "домен не открывается или не резолвится"
        if "virustotal has no malicious detections" in low:
            return "VirusTotal не нашёл вредоносных срабатываний"
        if "google safe browsing returned no matches" in low:
            return "Google Safe Browsing не нашёл угроз"
        if "approve(address,uint256)" in low:
            return "обнаружено разрешение approve(address,uint256)"
        return text

    if lang == "uk":
        if "domain imitates a trusted brand" in low:
            return "домен схожий на підробку відомого бренду"
        if "host mixes trusted-brand wording" in low:
            return "домен змішує назву відомого бренду з фішинговими словами"
        if "host contains well-known brand fragment" in low:
            return "домен містить фрагмент відомого бренду, але не є офіційним доменом"
        if "domain does not resolve" in low or "could not be resolved" in low:
            return "домен не відкривається або не резолвиться"
        if "virustotal has no malicious detections" in low:
            return "VirusTotal не знайшов шкідливих спрацювань"
        if "google safe browsing returned no matches" in low:
            return "Google Safe Browsing не знайшов загроз"
        if "approve(address,uint256)" in low:
            return "виявлено дозвіл approve(address,uint256)"
        return text

    return text



def localize_backend_text(lang: str, text: str) -> str:
    text = str(text or "")
    low = text.lower()

    if lang == "ru":
        rules = [
            ("the domain looks like a trusted-brand impersonation. its goal may be to make you trust a fake page.", "Домен похож на подделку известного бренда. Его цель — заставить вас доверять фейковой странице."),
            ("worst case: entering data, connecting a wallet, or signing there can lead to lost access or funds.", "В худшем сценарии ввод данных, подключение кошелька или подпись могут привести к потере доступа или средств."),
            ("noytrix did not find confirmed scam signals in available sources.", "Noytrix не нашёл подтверждённых scam-сигналов в доступных источниках."),
            ("risk appears only if the site asks for a seed phrase, private key, wallet approval or suspicious signature.", "Риск появляется, если сайт просит seed-фразу, приватный ключ, разрешение кошелька или подозрительную подпись."),
        ]
        for needle, repl in rules:
            if needle in low:
                return repl

    if lang == "uk":
        rules = [
            ("the domain looks like a trusted-brand impersonation. its goal may be to make you trust a fake page.", "Домен схожий на підробку відомого бренду. Його мета — змусити вас довіряти фейковій сторінці."),
            ("worst case: entering data, connecting a wallet, or signing there can lead to lost access or funds.", "У найгіршому випадку введення даних, підключення гаманця або підпис можуть призвести до втрати доступу чи коштів."),
            ("noytrix did not find confirmed scam signals in available sources.", "Noytrix не знайшов підтверджених scam-сигналів у доступних джерелах."),
            ("risk appears only if the site asks for a seed phrase, private key, wallet approval or suspicious signature.", "Ризик з’являється, якщо сайт просить seed-фразу, приватний ключ, дозвіл гаманця або підозрілий підпис."),
        ]
        for needle, repl in rules:
            if needle in low:
                return repl

    return text


def fmt_scan_result(data: dict, lang: str) -> str:
    level = str(data.get("level") or "unknown").lower()
    score = int(data.get("score") or 0)
    kind_raw = data.get("kind") or "unknown"
    kind = data.get("kind_localized") or tr_kind(lang, kind_raw)
    target = data.get("host") or data.get("normalized_input") or data.get("input") or ""

    scoring = data.get("scoring") or {}
    community = data.get("community") or {}
    permissions = data.get("permissions_summary") or {}
    quota = data.get("quota") or {}
    evidence = data.get("evidence") or []
    sources = data.get("sources") or []
    details = data.get("details") or {}
    db_info = details.get("noytrix_scam_database") or {}
    db_match = db_info.get("match") or {}
    safety_gate = details.get("false_positive_safety_gate") or {}
    top_contributors = details.get("top_score_contributors") or []
    hard_evidence_codes = details.get("hard_evidence_codes") or []

    if level == "safe":
        headline = t(lang, "headline_safe")
        action = t(lang, "action_safe")
    elif level == "suspicious":
        headline = t(lang, "headline_warn")
        action = t(lang, "action_warn")
    else:
        headline = t(lang, "headline_danger")
        action = t(lang, "action_danger")

    lines = [
        "🛡 <b>NOYTRIX SCAMSHIELD</b>",
        "",
        f"{tr_level(lang, level)} · <b>{score}/100</b>",
        f"🧩 {kind}",
    ]

    if target:
        lines.append(f"🎯 <code>{short(target, 54)}</code>")

    lines += [
        "",
        f"{t(lang, 'ai_analysis')}",
        headline,
    ]

    for ev in evidence[:2]:
        txt = ev.get("text")
        if txt:
            lines.append(f"• {short(localize_evidence(lang, txt), 95)}")

    lines += [
        "",
        f"{t(lang, 'risk_engine')}",
        f"{tr_phrase(lang, 'external')} <b>{scoring.get('confirmed_external_signals', 0)}</b> · "
        f"{tr_phrase(lang, 'heuristics')} <b>{scoring.get('heuristics', 0)}</b> · "
        f"{tr_phrase(lang, 'page')} <b>{scoring.get('page_content', 0)}</b> · "
        f"{tr_phrase(lang, 'community')} <b>{scoring.get('community_votes', 0)}</b>",
    ]

    backend_rows = []
    if db_info.get("reason") or db_match.get("database"):
        db_status = db_match.get("status") or ("matched" if db_match.get("matched") else "not listed")
        row = f"вЂў Noytrix DB: {db_status}"
        if db_info.get("reason"):
            row += f" В· {short(db_info.get('reason'), 90)}"
        backend_rows.append(row)

    if isinstance(safety_gate, dict) and ("applied" in safety_gate or safety_gate.get("reason")):
        gate_status = "applied" if safety_gate.get("applied") else "not applied"
        row = f"вЂў Safety gate: {gate_status}"
        if safety_gate.get("reason"):
            row += f" В· {short(safety_gate.get('reason'), 90)}"
        backend_rows.append(row)

    for item in top_contributors[:3]:
        text = backend_signal_text(item)
        if text:
            backend_rows.append(f"вЂў {short(localize_evidence(lang, text), 95)}")

    if hard_evidence_codes:
        backend_rows.append(f"вЂў Hard evidence: {short(', '.join(map(str, hard_evidence_codes[:5])), 110)}")

    if backend_rows:
        lines += ["", "рџ§  Backend Intelligence"] + backend_rows[:7]

    investigation_block = investigation_rows(data, lang)
    if investigation_block:
        lines += ["", investigation_label(lang, "title")] + investigation_block

    impact = data.get("what_can_happen")
    worst = data.get("worst_case")
    if impact or worst:
        lines += ["", tr_phrase(lang, "possible_impact")]
        if impact:
            lines.append(short(localize_backend_text(lang, impact), 240))
        if worst:
            lines.append(f"🚨 {tr_phrase(lang, 'worst_case')} {short(localize_backend_text(lang, worst), 220)}")

    # Contract intelligence from backend source details
    if str(kind_raw or "").lower() == "contract":
        contract_rows = []
        seen_contracts = set()
        for src in sources:
            det = src.get("details") or {}
            cname = det.get("contract_name")
            verified = det.get("verified_contract")
            chain_id = det.get("chain_id")
            if not cname and verified is None:
                continue
            key = (str(cname or ""), str(chain_id or ""), str(src.get("name") or ""))
            if key in seen_contracts:
                continue
            seen_contracts.add(key)

            chain_label = "Ethereum" if str(chain_id) == "1" else ("BNB Chain" if str(chain_id) == "56" else (f"Chain {chain_id}" if chain_id else "EVM"))
            verify_txt = "verified" if verified else "not verified"
            if lang == "ru":
                verify_txt = "верифицирован" if verified else "не верифицирован"
            elif lang == "uk":
                verify_txt = "верифікований" if verified else "не верифікований"

            row = f"• {chain_label}: "
            if cname:
                row += f"<b>{short(cname, 42)}</b> · "
            row += verify_txt
            contract_rows.append(row)

        if contract_rows:
            title = "🧠 Contract Intelligence"
            if lang == "ru":
                title = "🧠 Анализ контракта"
            elif lang == "uk":
                title = "🧠 Аналіз контракту"
            lines += ["", title] + contract_rows[:4]

            names = " ".join(contract_rows).lower()
            if "aggregationrouter" in names or "router" in names:
                if lang == "ru":
                    lines.append("• Обнаружен router/aggregator contract. Риск зависит от конкретной транзакции, approve или подписи.")
                elif lang == "uk":
                    lines.append("• Виявлено router/aggregator contract. Ризик залежить від конкретної транзакції, approve або підпису.")
                else:
                    lines.append("• Router/aggregator contract detected. Risk depends on the exact transaction, approval or signature.")

    perm_summary = localize_backend_text(lang, permissions.get("summary")) if permissions.get("summary") else tr_phrase(lang, "permissions_unknown")
    lines += ["", f"{t(lang, 'wallet_permissions')}", short(str(perm_summary), 220)]

    clean_sources = []
    for src in sources:
        status = str(src.get("status") or "").lower()
        if status in {"error", "timeout", "invalid_key", "quota", "no_data"}:
            continue
        clean_sources.append(src)

    if clean_sources:
        lines += ["", tr_phrase(lang, "verification_sources")]
        for src in clean_sources[:5]:
            name = tr_source_name(src.get("name"))
            status = tr_status(lang, src.get("status"))
            icon = "✅" if str(src.get("status")).lower() == "clean" else "⚠️"
            lines.append(f"{icon} {name}: {status}")

    verdict = community.get("community_verdict") or tr_phrase(lang, "community_unknown")
    lines += [
        "",
        tr_phrase(lang, "community_signals"),
        f"{verdict}: 🚨 {community.get('scam_votes', 0)} / ✅ {community.get('safe_votes', 0)}",
        "",
        f"{t(lang, 'recommended_action')}",
        action,
    ]

    if data.get("isPro"):
        lines += ["", tr_phrase(lang, "pro_unlimited")]
    else:
        left = quota.get("left", 0)
        limit = quota.get("freeLimit", 4)
        lines += ["", tr_phrase(lang, "free_left").format(left=left, limit=limit)]

    return "\n".join(lines)
