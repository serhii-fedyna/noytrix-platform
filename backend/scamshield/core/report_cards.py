"""Stable, evidence-led cards for every Noytrix client.

This module deliberately does not accept model prose as an input.  A card is
shown only when a detector returned a coded fact; the UI can then explain the
fact without turning an LLM response or provider message into a verdict.
"""
from __future__ import annotations

from typing import Any

from scamshield.core.evidence import canonical_evidence, evidence_from_sources
from scamshield.core.sources import normalize_source_status, source_is_failed


REPORT_CARDS_SCHEMA_VERSION = "cards-v2"


COPY: dict[str, dict[str, tuple[str, str]]] = {
    "documented_incident_exact_match": {
        "en": ("Documented incident match", "This exact identifier matches a reviewed documented scam incident."),
        "ru": ("Совпадение с документированным инцидентом", "Этот точный идентификатор совпадает с проверенным документированным случаем мошенничества."),
        "uk": ("Збіг із документованим інцидентом", "Цей точний ідентифікатор збігається з перевіреним документованим випадком шахрайства."),
    },
    "noytrix_scam_database_exact_match": {
        "en": ("Noytrix intelligence match", "This exact identifier is in Noytrix’s reviewed threat registry."),
        "ru": ("Совпадение в разведке Noytrix", "Этот точный идентификатор есть в проверенном реестре угроз Noytrix."),
        "uk": ("Збіг у розвідці Noytrix", "Цей точний ідентифікатор є у перевіреному реєстрі загроз Noytrix."),
    },
    "gsb_match": {
        "en": ("Known unsafe URL", "Google Safe Browsing matched this URL to a known unsafe category."),
        "ru": ("Известный опасный URL", "Google Safe Browsing отнёс этот URL к известной опасной категории."),
        "uk": ("Відомий небезпечний URL", "Google Safe Browsing відніс цей URL до відомої небезпечної категорії."),
    },
    "vt_detection": {
        "en": ("Malware detection", "Independent security scanners reported a malicious detection for this object."),
        "ru": ("Обнаружение вредоносной угрозы", "Независимые сканеры безопасности сообщили о вредоносном обнаружении для этого объекта."),
        "uk": ("Виявлення шкідливої загрози", "Незалежні сканери безпеки повідомили про шкідливе виявлення для цього об’єкта."),
    },
    "honeypot_detected": {
        "en": ("Exit restriction detected", "The token showed a sell or exit restriction consistent with honeypot risk."),
        "ru": ("Выявлено ограничение выхода", "У токена выявлено ограничение продажи или выхода, характерное для honeypot-риска."),
        "uk": ("Виявлено обмеження виходу", "У токена виявлено обмеження продажу або виходу, характерне для honeypot-ризику."),
    },
    "known_malicious_contract_identity": {
        "en": ("Known malicious contract", "Noytrix intelligence identifies this contract or spender as malicious."),
        "ru": ("Известный вредоносный контракт", "Разведка Noytrix определяет этот контракт или spender как вредоносный."),
        "uk": ("Відомий шкідливий контракт", "Розвідка Noytrix визначає цей контракт або spender як шкідливий."),
    },
    "seed_phrase_request": {
        "en": ("Recovery phrase request", "The page asks for a seed or recovery phrase. Legitimate services do not need it."),
        "ru": ("Запрос seed-фразы", "Страница просит seed- или recovery-фразу. Легитимным сервисам она не нужна."),
        "uk": ("Запит seed-фрази", "Сторінка просить seed- або recovery-фразу. Легітимним сервісам вона не потрібна."),
    },
    "private_key_request": {
        "en": ("Private-key request", "The page asks for a private key. Never provide it."),
        "ru": ("Запрос приватного ключа", "Страница просит приватный ключ. Никогда не передавайте его."),
        "uk": ("Запит приватного ключа", "Сторінка просить приватний ключ. Ніколи не передавайте його."),
    },
    "malicious_wallet_permission": {
        "en": ("Risky wallet permission", "A wallet approval points to a confirmed malicious spender or a drain-capable action."),
        "ru": ("Опасное разрешение кошелька", "Разрешение кошелька указывает на подтверждённо вредоносного получателя или действие с риском вывода средств."),
        "uk": ("Небезпечний дозвіл гаманця", "Дозвіл гаманця вказує на підтверджено шкідливого отримувача або дію з ризиком виведення коштів."),
    },
    "token_exit_risk": {
        "en": ("Token exit risk", "The token’s observed controls can restrict selling or impose a materially harmful exit cost."),
        "ru": ("Риск выхода из токена", "Наблюдаемые настройки токена могут ограничить продажу или создать существенную стоимость выхода."),
        "uk": ("Ризик виходу з токена", "Спостережені налаштування токена можуть обмежити продаж або створити істотну вартість виходу."),
    },
    "wallet_drainer_behavior": {
        "en": ("Wallet-drainer behavior", "The page combines wallet interaction with approval, signature, or transaction behavior associated with asset-draining flows."),
        "ru": ("Поведение wallet drainer", "Страница сочетает взаимодействие с кошельком с запросами разрешений, подписей или транзакций, характерными для схем вывода активов."),
        "uk": ("Поведінка wallet drainer", "Сторінка поєднує взаємодію з гаманцем із запитами дозволів, підписів або транзакцій, характерними для схем виведення активів."),
    },
    "phishing_interface": {
        "en": ("Phishing interface", "The page contains an observed credential, support, exchange, or brand-impersonation pattern consistent with phishing."),
        "ru": ("Фишинговый интерфейс", "На странице обнаружен шаблон кражи учётных данных, поддельной поддержки, биржи или имитации бренда, характерный для фишинга."),
        "uk": ("Фішинговий інтерфейс", "На сторінці виявлено шаблон викрадення облікових даних, підробленої підтримки, біржі або імітації бренду, характерний для фішингу."),
    },
    "token_control_observed": {
        "en": ("Token control remains active", "A privileged token control is active. This is a control fact, not proof of a scam by itself."),
        "ru": ("Контроль токена активен", "Привилегированный контроль токена активен. Это факт контроля, но сам по себе не доказательство скама."),
        "uk": ("Контроль токена активний", "Привілейований контроль токена активний. Це факт контролю, але сам по собі не доказ скаму."),
    },
}


CODE_ALIASES = {
    "noytrix_scam_database_match": "noytrix_scam_database_exact_match",
    "goplus_honeypot_confirmed": "honeypot_detected",
    "goplus_cannot_sell_all": "token_exit_risk",
    "extreme_sell_tax": "token_exit_risk",
    "high_sell_tax": "token_exit_risk",
    "active_approval_to_confirmed_malicious_spender": "malicious_wallet_permission",
    "confirmed_malicious_counterparty_observed": "malicious_wallet_permission",
    "approval_or_drain_functions": "wallet_drainer_behavior",
    "possible_js_drainer_flow": "wallet_drainer_behavior",
    "wallet_connect_plus_approval_language": "wallet_drainer_behavior",
    "wallet_connect_plus_reward_lure": "wallet_drainer_behavior",
    "credential_theft_ui": "phishing_interface",
    "fake_support_ui": "phishing_interface",
    "fake_exchange_ui": "phishing_interface",
    "fake_airdrop_bonus_ui": "phishing_interface",
    "cloned_ui_fingerprint": "phishing_interface",
    "brand_impersonation_plus_wallet_pressure": "phishing_interface",
    "brand_impersonation": "phishing_interface",
    "solana_mint_authority_active": "token_control_observed",
    "solana_freeze_authority_active": "token_control_observed",
    "solana_permanent_delegate_observed": "token_control_observed",
    "solana_transfer_hook_observed": "token_control_observed",
    "solana_transfer_fee_control_observed": "token_control_observed",
}


def _lang(value: Any) -> str:
    raw = str(value or "en").lower()
    return "uk" if raw.startswith(("uk", "ua")) else "ru" if raw.startswith("ru") else "en"


def _copy(code: str, lang: str) -> tuple[str, str] | None:
    return (COPY.get(CODE_ALIASES.get(code, code)) or {}).get(lang)


def _source_status_cards(sources: list[dict[str, Any]], lang: str) -> list[dict[str, Any]]:
    labels = {
        "en": {"available": "Completed", "clean": "Completed", "observed": "Completed", "malicious": "Completed", "suspicious": "Completed", "unknown": "No result", "no_data": "No data", "timeout": "Timed out", "error": "Failed", "unavailable": "Unavailable", "source_unavailable": "Unavailable", "quota": "Limit reached", "invalid_key": "Configuration error", "insufficient_data": "Insufficient data"},
        "ru": {"available": "Выполнено", "clean": "Выполнено", "observed": "Выполнено", "malicious": "Выполнено", "suspicious": "Выполнено", "unknown": "Нет результата", "no_data": "Нет данных", "timeout": "Тайм-аут", "error": "Ошибка", "unavailable": "Недоступно", "source_unavailable": "Недоступно", "quota": "Достигнут лимит", "invalid_key": "Ошибка настройки", "insufficient_data": "Недостаточно данных"},
        "uk": {"available": "Виконано", "clean": "Виконано", "observed": "Виконано", "malicious": "Виконано", "suspicious": "Виконано", "unknown": "Немає результату", "no_data": "Немає даних", "timeout": "Тайм-аут", "error": "Помилка", "unavailable": "Недоступно", "source_unavailable": "Недоступно", "quota": "Досягнуто ліміт", "invalid_key": "Помилка налаштування", "insufficient_data": "Недостатньо даних"},
    }[lang]
    cards = []
    for source in sources[:12]:
        if not isinstance(source, dict):
            continue
        status = normalize_source_status(source.get("status"))
        name = str(source.get("name") or source.get("source") or "Noytrix detector").strip()
        cards.append({
            "id": f"check:{name.lower().replace(' ', '_')}",
            "detector": name,
            "status": status,
            "status_label": labels.get(status, labels["unknown"]),
            "available": not source_is_failed(status),
            "observed_at": str(source.get("observed_at") or "").strip() or None,
        })
    return cards


def _actions(level: str, lang: str) -> list[dict[str, str]]:
    if level in {"critical", "danger"}:
        copy = {
            "en": [("Do not interact", "Do not connect a wallet, sign, approve, or send funds."), ("If you already interacted", "Move remaining assets to a clean wallet and revoke risky approvals."), ("Preserve the evidence", "Keep the URL, transaction hash, and screenshots for a report." )],
            "ru": [("Не взаимодействуйте", "Не подключайте кошелёк, не подписывайте, не давайте разрешений и не отправляйте средства."), ("Если уже взаимодействовали", "Переведите оставшиеся активы на чистый кошелёк и отзовите опасные разрешения."), ("Сохраните доказательства", "Сохраните URL, хеш транзакции и скриншоты для обращения." )],
            "uk": [("Не взаємодійте", "Не підключайте гаманець, не підписуйте, не надавайте дозволів і не надсилайте кошти."), ("Якщо вже взаємодіяли", "Переведіть решту активів на чистий гаманець і відкличте небезпечні дозволи."), ("Збережіть докази", "Збережіть URL, хеш транзакції та знімки екрана для звернення." )],
        }[lang]
    elif level == "suspicious":
        copy = {
            "en": [("Pause before acting", "Do not connect, sign, or send funds until the warning signals are independently verified.")],
            "ru": [("Поставьте действие на паузу", "Не подключайтесь, не подписывайте и не отправляйте средства, пока предупреждающие сигналы не будут проверены независимо.")],
            "uk": [("Поставте дію на паузу", "Не підключайтеся, не підписуйте і не надсилайте кошти, доки попереджувальні сигнали не будуть перевірені незалежно.")],
        }[lang]
    else:
        copy = {
            "en": [("Verify each transaction", "A clean result is not a guarantee for a future signature or transfer.")],
            "ru": [("Проверяйте каждую транзакцию", "Чистый результат не гарантирует безопасность будущей подписи или перевода.")],
            "uk": [("Перевіряйте кожну транзакцію", "Чистий результат не гарантує безпеку майбутнього підпису або переказу.")],
        }[lang]
    return [{"id": f"action:{index + 1}", "title": title, "detail": detail} for index, (title, detail) in enumerate(copy)]


def build_report_cards(data: dict[str, Any], lang: str) -> dict[str, Any]:
    """Build public, typed cards from detector output only.

    `raw` content and free-form source messages never leave this function.
    """
    language = _lang(lang)
    sources = [source for source in (data.get("sources") or []) if isinstance(source, dict)]
    entity = str(data.get("normalized_input") or data.get("input") or "").strip() or None
    network = str(data.get("chain") or "").strip() or None
    canonical = evidence_from_sources(sources, entity=entity, network=network)
    known_ids = {item.get("evidence_id") for item in canonical}
    statuses = {str(source.get("name") or source.get("source") or "").lower(): source.get("status") for source in sources}
    for raw in data.get("evidence") or []:
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source") or "noytrix_detector").lower()
        item = canonical_evidence(raw, source=source, source_status=statuses.get(source, "observed"), entity=entity, network=network)
        if item and item.get("evidence_id") not in known_ids:
            canonical.append(item)
            known_ids.add(item.get("evidence_id"))

    evidence_cards = []
    for item in canonical:
        code = str(item.get("code") or "").lower()
        copy = _copy(code, language)
        if not copy:
            continue
        title, detail = copy
        evidence_cards.append({
            "id": item["evidence_id"],
            "code": code,
            "title": title,
            "detail": detail,
            "detector": item.get("source"),
            "status": item.get("source_status"),
            "severity": item.get("severity"),
            "confidence": item.get("confidence"),
            "confirmed": bool(item.get("confirmed")),
            "observed_at": item.get("observed_at"),
            "fresh_until": item.get("fresh_until"),
            "corroboration_count": item.get("corroboration_count", 1),
        })

    level = str(data.get("level") or data.get("verdict") or "unknown").lower()
    inspection = data.get("source_coverage") if isinstance(data.get("source_coverage"), dict) else {}
    missing = [str(item) for item in inspection.get("missing_capabilities") or [] if str(item)]
    limits = []
    if missing:
        message = {
            "en": "Some required checks were not available, so this result does not prove the object safe.",
            "ru": "Часть обязательных проверок недоступна, поэтому результат не доказывает безопасность объекта.",
            "uk": "Частина обов’язкових перевірок недоступна, тому результат не доводить безпеку об’єкта.",
        }[language]
        limits.append({"id": "coverage:missing", "title": {"en": "Coverage limit", "ru": "Ограничение покрытия", "uk": "Обмеження покриття"}[language], "detail": message, "capabilities": missing[:8]})

    return {
        "schema_version": REPORT_CARDS_SCHEMA_VERSION,
        "evidence_cards": evidence_cards[:6],
        "check_cards": _source_status_cards(sources, language),
        "action_cards": _actions(level, language),
        "limit_cards": limits,
    }
