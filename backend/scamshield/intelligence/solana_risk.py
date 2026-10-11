from __future__ import annotations

from typing import Any


def _copy(lang: str, en: str, ru: str, uk: str) -> str:
    return ru if lang == "ru" else uk if lang == "uk" else en


def _finding(code: str, weight: int, lang: str, titles: tuple[str, str, str], details: tuple[str, str, str]) -> dict[str, Any]:
    return {
        "code": code,
        "weight": weight,
        "status": "attention" if weight else "info",
        "title": _copy(lang, *titles),
        "detail": _copy(lang, *details),
    }


def build_solana_risk_summary(details: dict[str, Any] | None, lang: str = "en") -> dict[str, Any]:
    """Explain observable Solana mint controls without turning controls into a scam verdict."""
    details = details or {}
    entity_type = str(details.get("entity_type") or "").lower()
    unavailable = {
        "version": "1.0", "chain": "solana", "available": False,
        # A control score of zero looks like a clean security score in clients.
        # This branch means that there was no mint-control assessment at all.
        "entity_type": entity_type or "unknown", "control_score": None, "level": "not_applicable",
        "headline": _copy(lang, "Solana controls were not available for this address.", "Для этого адреса данные о контроле Solana недоступны.", "Для цієї адреси дані про контроль Solana недоступні."),
        "summary": _copy(lang, "This check did not resolve the address as a token mint.", "Проверка не определила адрес как выпуск токена.", "Перевірка не визначила адресу як випуск токена."),
        "recommended_action": _copy(lang, "Check the exact transaction or signature before approving it.", "Проверяйте конкретную транзакцию или подпись перед подтверждением.", "Перевіряйте конкретну транзакцію або підпис перед підтвердженням."),
        "limitations": [], "findings": [],
    }
    if entity_type != "mint":
        return unavailable

    findings: list[dict[str, Any]] = []
    controls = details.get("token_2022_controls") or {}
    if details.get("freeze_authority"):
        findings.append(_finding("solana_freeze_authority_active", 22, lang,
            ("Accounts can be frozen", "Счета токена могут быть заморожены", "Рахунки токена можна заморозити"),
            ("A configured authority can freeze token accounts. This is a control, not proof of fraud.", "Настроенный адрес может замораживать счета токена. Это полномочие, а не доказательство мошенничества.", "Налаштована адреса може заморожувати рахунки токена. Це повноваження, а не доказ шахрайства.")))
    if details.get("mint_authority"):
        findings.append(_finding("solana_mint_authority_active", 12, lang,
            ("Supply can still change", "Выпуск токена всё ещё можно изменить", "Випуск токена все ще можна змінити"),
            ("A mint authority remains active and can create additional supply under the token program rules.", "Адрес выпуска активен и может создать дополнительное предложение по правилам программы токена.", "Адреса випуску активна й може створити додаткову пропозицію за правилами програми токена.")))
    if controls.get("permanent_delegate"):
        findings.append(_finding("solana_permanent_delegate_observed", 20, lang,
            ("Permanent delegate is configured", "Настроен постоянный делегат", "Налаштовано постійного делегата"),
            ("The mint has a permanent delegate control. Review the project's documented purpose before acquiring the token.", "У выпуска есть полномочие постоянного делегата. Перед покупкой проверьте, зачем оно заявлено проектом.", "У випуску є повноваження постійного делегата. Перед купівлею перевірте, навіщо воно заявлене проєктом.")))
    if controls.get("transfer_hook"):
        findings.append(_finding("solana_transfer_hook_observed", 10, lang,
            ("Transfers call an extra program", "Перевод вызывает дополнительную программу", "Переказ викликає додаткову програму"),
            ("Transfers invoke a configured Token-2022 hook program. Verify the hook before relying on normal transfer behavior.", "Перевод вызывает настроенную программу Token-2022. Проверьте её перед тем, как рассчитывать на обычный перевод.", "Переказ викликає налаштовану програму Token-2022. Перевірте її перед тим, як розраховувати на звичайний переказ.")))
    default_state = str(controls.get("default_account_state") or "").lower()
    if "frozen" in default_state:
        findings.append(_finding("solana_default_account_frozen", 20, lang,
            ("New accounts default to frozen", "Новые счета по умолчанию заморожены", "Нові рахунки за замовчуванням заморожені"),
            ("New token accounts default to a frozen state. Transfers may require an authority action first.", "Новые счета токена создаются замороженными. Для перевода может потребоваться действие управляющего адреса.", "Нові рахунки токена створюються замороженими. Для переказу може знадобитися дія керівної адреси.")))
    if controls.get("mint_close_authority"):
        findings.append(_finding("solana_mint_close_authority_observed", 12, lang,
            ("Mint close authority is configured", "Настроено полномочие закрытия выпуска", "Налаштовано повноваження закриття випуску"),
            ("The mint has a configured close authority. Read the project's token-control documentation before buying.", "У выпуска настроено полномочие закрытия. Перед покупкой ознакомьтесь с документацией проекта о контроле токена.", "У випуску налаштовано повноваження закриття. Перед купівлею ознайомтеся з документацією проєкту щодо контролю токена.")))
    if controls.get("transfer_fee"):
        findings.append(_finding("solana_transfer_fee_control_observed", 8, lang,
            ("Transfer fees are configured", "Настроена комиссия за перевод", "Налаштовано комісію за переказ"),
            ("Token-2022 transfer-fee controls are present. Check the current fee terms before transacting.", "У токена есть контроль комиссии за перевод в Token-2022. Проверьте актуальные условия комиссии перед операцией.", "У токена є контроль комісії за переказ у Token-2022. Перевірте актуальні умови комісії перед операцією.")))
    if controls.get("non_transferable"):
        findings.append(_finding("solana_non_transferable_token", 8, lang,
            ("Token is non-transferable", "Токен нельзя переводить", "Токен не можна переказувати"),
            ("The mint is marked non-transferable. Do not assume it can be sold or moved like a standard token.", "Выпуск отмечен как непереводимый. Не рассчитывайте, что его можно продать или переместить как обычный токен.", "Випуск позначено як непереказний. Не розраховуйте, що його можна продати або перемістити як звичайний токен.")))

    concentration = details.get("top10_owner_concentration_pct")
    if isinstance(concentration, (int, float)):
        weight = 15 if concentration >= 80 else 7 if concentration >= 50 else 0
        findings.append(_finding("solana_largest_owner_sample", weight, lang,
            ("Largest-account concentration sample", "Выборка концентрации крупнейших счетов", "Вибірка концентрації найбільших рахунків"),
            (f"The resolved owners behind the largest sampled token accounts hold {concentration:.2f}% of supply. This is a sample, not the full holder population.", f"Разрешённые владельцы крупнейших выбранных счетов держат {concentration:.2f}% выпуска. Это выборка, а не все владельцы токена.", f"Визначені власники найбільших вибраних рахунків тримають {concentration:.2f}% випуску. Це вибірка, а не всі власники токена.")))

    score = min(100, sum(int(item["weight"]) for item in findings))
    level = "high_control" if score >= 35 else "moderate_control" if score >= 12 else "limited_control"
    headline = _copy(lang, "Important token controls need review" if level == "high_control" else "Token controls need context" if level == "moderate_control" else "No high-impact token control was observed", "Важные полномочия токена требуют проверки" if level == "high_control" else "Полномочия токена нужно проверить в контексте" if level == "moderate_control" else "Критичных полномочий токена не обнаружено", "Важливі повноваження токена потребують перевірки" if level == "high_control" else "Повноваження токена потрібно перевірити в контексті" if level == "moderate_control" else "Критичних повноважень токена не виявлено")
    return {
        "version": "1.0", "chain": "solana", "available": True, "entity_type": "mint",
        "control_score": score, "level": level, "headline": headline,
        "summary": _copy(lang, "Noytrix observed on-chain token controls. They are not a scam verdict, but they can change what a holder can do.", "Noytrix обнаружил ончейн-полномочия токена. Это не вердикт о мошенничестве, но они могут менять возможности держателя.", "Noytrix виявив ончейн-повноваження токена. Це не вердикт про шахрайство, але вони можуть змінювати можливості власника."),
        "recommended_action": _copy(lang, "Before buying or signing, compare these controls with the project's official documentation and review the exact transaction.", "Перед покупкой или подписью сопоставьте эти полномочия с официальной документацией проекта и проверьте конкретную транзакцию.", "Перед купівлею або підписом зіставте ці повноваження з офіційною документацією проєкту та перевірте конкретну транзакцію."),
        "limitations": [_copy(lang, "The largest-account figure covers only the RPC response sample, not every holder.", "Показатель крупнейших счетов охватывает только выборку ответа RPC, а не всех держателей.", "Показник найбільших рахунків охоплює лише вибірку відповіді RPC, а не всіх власників."), _copy(lang, "A mint scan cannot determine what a future wallet signature will authorize.", "Проверка выпуска не может определить, что разрешит будущая подпись кошелька.", "Перевірка випуску не може визначити, що дозволить майбутній підпис гаманця.")],
        "findings": sorted(findings, key=lambda item: int(item["weight"]), reverse=True),
        "attention_count": sum(1 for item in findings if item["weight"] > 0),
    }
