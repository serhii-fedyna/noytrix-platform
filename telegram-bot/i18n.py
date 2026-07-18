STRINGS = {
    "en": {
        "check": "🛡 Check",
        "top_scams": "🚨 Scam Radar",
        "language": "🌐 Language",
        "profile": "👤 Profile",

        "safe": "🟢 SAFE",
        "suspicious": "🟠 SUSPICIOUS",
        "danger": "🔴 DANGER",

        "ai_analysis": "🧠 AI Risk Analysis",
        "risk_engine": "📊 Risk Engine",
        "community": "🌍 Community",
        "recommended_action": "🛠 Recommended Action",
        "wallet_permissions": "🔐 Wallet Permissions",

        "headline_safe": "No confirmed scam signals found.",
        "headline_warn": "Risk signals detected. Do not rush.",
        "headline_danger": "High-risk target. Avoid interaction.",

        "action_safe": "Continue carefully. Never share seed phrase or private keys.",
        "action_warn": "Do not connect wallet yet. Verify the domain from official sources.",
        "action_danger": "Leave the site immediately. Do not connect wallet or sign transactions.",

        "profile_title": "👤 NOYTRIX ID",
        "plan_free": "⚪ FREE",
        "plan_pro": "💎 PRO ACTIVE",

        "total_scans": "Total scans",
        "scam_reports": "Scam reports",
        "last_activity": "Last activity",

        "loading": "🛡 Analyzing with Noytrix Risk Engine...",
        "limit_reached": "FREE daily limit reached.",
        "upgrade_pro": "Upgrade to PRO for unlimited protection.",

        "invalid_email": "Invalid email address.",
        "invalid_code": "Invalid verification code.",

        "open_app": "Open App",
        "vote_safe": "Safe",
        "vote_scam": "Scam",
    },

    "ru": {
        "check": "🛡 Проверить",
        "top_scams": "🚨 Скам-радар",
        "language": "🌐 Язык",
        "profile": "👤 Профиль",

        "safe": "🟢 БЕЗОПАСНО",
        "suspicious": "🟠 ПОДОЗРИТЕЛЬНО",
        "danger": "🔴 ОПАСНО",

        "ai_analysis": "🧠 AI-анализ риска",
        "risk_engine": "📊 Risk Engine",
        "community": "🌍 Сообщество",
        "recommended_action": "🛠 Рекомендуемое действие",
        "wallet_permissions": "🔐 Разрешения кошелька",

        "headline_safe": "Подтверждённых признаков скама не найдено.",
        "headline_warn": "Обнаружены риск-сигналы. Будьте осторожны.",
        "headline_danger": "Высокий риск. Избегайте взаимодействия.",

        "action_safe": "Соблюдайте осторожность. Никому не передавайте seed-фразу и приватные ключи.",
        "action_warn": "Не подключайте кошелёк. Проверьте домен через официальные источники.",
        "action_danger": "Немедленно покиньте сайт. Не подключайте кошелёк и не подписывайте транзакции.",

        "profile_title": "👤 NOYTRIX ID",
        "plan_free": "⚪ FREE",
        "plan_pro": "💎 PRO ACTIVE",

        "total_scans": "Всего проверок",
        "scam_reports": "Скам-репорты",
        "last_activity": "Последняя активность",

        "loading": "🛡 Анализ через Noytrix Risk Engine...",
        "limit_reached": "Дневной лимит FREE исчерпан.",
        "upgrade_pro": "Перейдите на PRO для полной защиты.",

        "invalid_email": "Неверный email.",
        "invalid_code": "Неверный код подтверждения.",

        "open_app": "Открыть приложение",
        "vote_safe": "Безопасно",
        "vote_scam": "Скам",
    },

    "uk": {
        "check": "🛡 Перевірити",
        "top_scams": "🚨 Скам-радар",
        "language": "🌐 Мова",
        "profile": "👤 Профіль",

        "safe": "🟢 БЕЗПЕЧНО",
        "suspicious": "🟠 ПІДОЗРІЛО",
        "danger": "🔴 НЕБЕЗПЕЧНО",

        "ai_analysis": "🧠 AI-аналіз ризику",
        "risk_engine": "📊 Risk Engine",
        "community": "🌍 Спільнота",
        "recommended_action": "🛠 Рекомендована дія",
        "wallet_permissions": "🔐 Дозволи гаманця",

        "headline_safe": "Підтверджених ознак шахрайства не знайдено.",
        "headline_warn": "Виявлено ризик-сигнали. Будьте обережні.",
        "headline_danger": "Високий ризик. Уникайте взаємодії.",

        "action_safe": "Будьте обережні. Не передавайте seed-фразу або приватні ключі.",
        "action_warn": "Не підключайте гаманець. Перевірте домен через офіційні джерела.",
        "action_danger": "Негайно залиште сайт. Не підключайте гаманець і не підписуйте транзакції.",

        "profile_title": "👤 NOYTRIX ID",
        "plan_free": "⚪ FREE",
        "plan_pro": "💎 PRO ACTIVE",

        "total_scans": "Усього перевірок",
        "scam_reports": "Скам-репорти",
        "last_activity": "Остання активність",

        "loading": "🛡 Аналіз через Noytrix Risk Engine...",
        "limit_reached": "Денний ліміт FREE вичерпано.",
        "upgrade_pro": "Перейдіть на PRO для повного захисту.",

        "invalid_email": "Невірний email.",
        "invalid_code": "Невірний код підтвердження.",

        "open_app": "Відкрити застосунок",
        "vote_safe": "Безпечно",
        "vote_scam": "Скам",
    }
}

def t(lang: str, key: str) -> str:
    lang = lang if lang in STRINGS else "en"
    return STRINGS.get(lang, {}).get(key) or STRINGS["en"].get(key) or key


for _lang, _data in STRINGS.items():
    _data.update({
        "choose_lang": {
            "en": "🌐 Choose your language",
            "ru": "🌐 Выберите язык",
            "uk": "🌐 Оберіть мову",
        }[_lang],
        "welcome": {
            "en": "✦ NOYTRIX SCAMSHIELD ✦\n\n🟠 Premium AI-powered crypto security assistant.\n\nSend a link, wallet, contract, token or suspicious message — I will check it before you click, connect or sign.",
            "ru": "✦ NOYTRIX SCAMSHIELD ✦\n\n🟠 Премиальный AI-ассистент для крипто-защиты.\n\nОтправьте ссылку, кошелёк, контракт, токен или подозрительное сообщение — я проверю это до клика, подключения или подписи.",
            "uk": "✦ NOYTRIX SCAMSHIELD ✦\n\n🟠 Преміальний AI-асистент для криптозахисту.\n\nНадішліть посилання, гаманець, контракт, токен або підозріле повідомлення — я перевірю це до кліку, підключення чи підпису.",
        }[_lang],
        "lang_saved": {
            "en": "Language saved",
            "ru": "Язык сохранён",
            "uk": "Мову збережено",
        }[_lang],
        "error": {
            "en": "Something went wrong",
            "ru": "Что-то пошло не так",
            "uk": "Щось пішло не так",
        }[_lang],
        "profile_refresh": {
            "en": "🔄 Refresh",
            "ru": "🔄 Обновить",
            "uk": "🔄 Оновити",
        }[_lang],
        "profile_disconnect": {
            "en": "🚪 Disconnect",
            "ru": "🚪 Отключить",
            "uk": "🚪 Відключити",
        }[_lang],
        "profile_connect": {
            "en": "🔗 Connect Account",
            "ru": "🔗 Подключить аккаунт",
            "uk": "🔗 Підключити акаунт",
        }[_lang],
        "connected": {
            "en": "✅ Connected",
            "ru": "✅ Подключено",
            "uk": "✅ Підключено",
        }[_lang],
        "not_connected": {
            "en": "❌ Not connected",
            "ru": "❌ Не подключено",
            "uk": "❌ Не підключено",
        }[_lang],
        "account": {
            "en": "Account",
            "ru": "Аккаунт",
            "uk": "Акаунт",
        }[_lang],
        "status": {
            "en": "Status",
            "ru": "Статус",
            "uk": "Статус",
        }[_lang],
        "plan": {
            "en": "Plan",
            "ru": "Тариф",
            "uk": "Тариф",
        }[_lang],
        "activity": {
            "en": "Activity",
            "ru": "Активность",
            "uk": "Активність",
        }[_lang],
        "pro_unlocks": {
            "en": "PRO unlocks unlimited scans, advanced reports, wallet approval analyzer and instant scam alerts.",
            "ru": "PRO открывает безлимитные проверки, расширенные отчёты, анализ разрешений кошелька и мгновенные scam-alerts.",
            "uk": "PRO відкриває безлімітні перевірки, розширені звіти, аналіз дозволів гаманця та миттєві scam-alerts.",
        }[_lang],
        "connect_title": {
            "en": "🔗 Connect Noytrix Account",
            "ru": "🔗 Подключение аккаунта Noytrix",
            "uk": "🔗 Підключення акаунта Noytrix",
        }[_lang],
        "connect_email_prompt": {
            "en": "Send the email connected to your Noytrix app account. I will send a 6-digit verification code to that email.",
            "ru": "Отправьте email, привязанный к аккаунту Noytrix. Я отправлю на него 6-значный код подтверждения.",
            "uk": "Надішліть email, прив’язаний до акаунта Noytrix. Я надішлю на нього 6-значний код підтвердження.",
        }[_lang],
        "code_sent": {
            "en": "📩 Verification code sent",
            "ru": "📩 Код подтверждения отправлен",
            "uk": "📩 Код підтвердження надіслано",
        }[_lang],
        "send_code_now": {
            "en": "Now send the 6-digit code from the email.",
            "ru": "Теперь отправьте 6-значный код из письма.",
            "uk": "Тепер надішліть 6-значний код із листа.",
        }[_lang],
        "account_connected": {
            "en": "✅ Noytrix account connected",
            "ru": "✅ Аккаунт Noytrix подключён",
            "uk": "✅ Акаунт Noytrix підключено",
        }[_lang],
        "account_disconnected": {
            "en": "✅ Noytrix account disconnected.",
            "ru": "✅ Аккаунт Noytrix отключён.",
            "uk": "✅ Акаунт Noytrix відключено.",
        }[_lang],
        "no_scams": {
            "en": "🛡 No community scam flags yet.",
            "ru": "🛡 Пока нет scam-сигналов от сообщества.",
            "uk": "🛡 Поки немає scam-сигналів від спільноти.",
        }[_lang],
        "ios_soon": {
            "en": "🍎 iOS version is coming soon.",
            "ru": "🍎 Версия для iOS скоро появится.",
            "uk": "🍎 Версія для iOS скоро з’явиться.",
        }[_lang],
        "open_noytrix": {
            "en": "🟠 Open Noytrix App",
            "ru": "🟠 Открыть приложение Noytrix",
            "uk": "🟠 Відкрити застосунок Noytrix",
        }[_lang],
        "choose_platform": {
            "en": "Choose your platform:",
            "ru": "Выберите платформу:",
            "uk": "Оберіть платформу:",
        }[_lang],
        "checking": {
            "en": "🛡 Analyzing with Noytrix Risk Engine...",
            "ru": "🛡 Анализ через Noytrix Risk Engine...",
            "uk": "🛡 Аналіз через Noytrix Risk Engine...",
        }[_lang],
        "free_limit_title": {
            "en": "🚫 FREE LIMIT REACHED",
            "ru": "🚫 ЛИМИТ FREE ИСЧЕРПАН",
            "uk": "🚫 ЛІМІТ FREE ВИЧЕРПАНО",
        }[_lang],
        "free_limit_body": {
            "en": "You used all free checks for today.",
            "ru": "Вы использовали все бесплатные проверки на сегодня.",
            "uk": "Ви використали всі безкоштовні перевірки на сьогодні.",
        }[_lang],
        "pro_unlocks_short": {
            "en": "PRO unlocks:",
            "ru": "PRO открывает:",
            "uk": "PRO відкриває:",
        }[_lang],
    })


# --- Missing Telegram bot translations ---
_EXTRA_TRANSLATIONS = {
    "en": {
        "check_prompt": "Send me a link, wallet, contract, token or suspicious message.",
        "check_before_action": "I will check it before you click, connect your wallet or sign anything.",
        "fresh_scams": "🚨 Fresh community scam flags",
        "top": "Top scam flags",
        "send_anything_check": "Send anything suspicious here — I will check it with Noytrix ScamShield.",
        "vote_done": "Vote saved",
        "pro_features_full": "💎 PRO gives unlimited checks, deeper source analysis, wallet approval risk review, priority reports and instant scam alerts.",
    },
    "ru": {
        "check_prompt": "Отправьте ссылку, кошелёк, контракт, токен или подозрительное сообщение.",
        "check_before_action": "Я проверю это до клика, подключения кошелька или подписи.",
        "fresh_scams": "🚨 Свежие scam-сигналы сообщества",
        "top": "Топ scam-сигналов",
        "send_anything_check": "Отправьте сюда всё подозрительное — я проверю это через Noytrix ScamShield.",
        "vote_done": "Голос сохранён",
        "pro_features_full": "💎 PRO даёт безлимитные проверки, глубокий анализ источников, проверку рисков wallet approvals, приоритетные отчёты и мгновенные scam-alerts.",
    },
    "uk": {
        "check_prompt": "Надішліть посилання, гаманець, контракт, токен або підозріле повідомлення.",
        "check_before_action": "Я перевірю це до кліку, підключення гаманця або підпису.",
        "fresh_scams": "🚨 Свіжі scam-сигнали спільноти",
        "top": "Топ scam-сигналів",
        "send_anything_check": "Надішліть сюди все підозріле — я перевірю це через Noytrix ScamShield.",
        "vote_done": "Голос збережено",
        "pro_features_full": "💎 PRO дає безлімітні перевірки, глибший аналіз джерел, перевірку ризиків wallet approvals, пріоритетні звіти та миттєві scam-alerts.",
    },
}

for _lang, _values in _EXTRA_TRANSLATIONS.items():
    STRINGS.setdefault(_lang, {}).update(_values)


# --- Profile label translations ---
_PROFILE_LABEL_TRANSLATIONS = {
    "en": {
        "telegram_id": "Telegram ID",
        "not_connected_plain": "Not connected",
    },
    "ru": {
        "telegram_id": "Telegram ID",
        "not_connected_plain": "Не подключено",
    },
    "uk": {
        "telegram_id": "Telegram ID",
        "not_connected_plain": "Не підключено",
    },
}

for _lang, _values in _PROFILE_LABEL_TRANSLATIONS.items():
    STRINGS.setdefault(_lang, {}).update(_values)

# --- Error message translations ---
_ERROR_TRANSLATIONS = {
    "en": {
        "profile_error": "Profile error",
        "disconnect_error": "Disconnect error",
        "connect_error": "Connect error",
        "could_not_send_code": "Could not send code",
        "invalid_email_action": "Send the email connected to your Noytrix account.",
        "invalid_code_action": "Send the 6-digit verification code from your email.",
        "email_label": "Email",
    },
    "ru": {
        "profile_error": "Ошибка профиля",
        "disconnect_error": "Ошибка отключения",
        "connect_error": "Ошибка подключения",
        "could_not_send_code": "Не удалось отправить код",
        "invalid_email_action": "Отправьте email, привязанный к аккаунту Noytrix.",
        "invalid_code_action": "Отправьте 6-значный код подтверждения из письма.",
        "email_label": "Email",
    },
    "uk": {
        "profile_error": "Помилка профілю",
        "disconnect_error": "Помилка відключення",
        "connect_error": "Помилка підключення",
        "could_not_send_code": "Не вдалося надіслати код",
        "invalid_email_action": "Надішліть email, прив’язаний до акаунта Noytrix.",
        "invalid_code_action": "Надішліть 6-значний код підтвердження з листа.",
        "email_label": "Email",
    },
}

for _lang, _values in _ERROR_TRANSLATIONS.items():
    STRINGS.setdefault(_lang, {}).update(_values)
