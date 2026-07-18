from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import APP_URL
from i18n import t


def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="English", callback_data="lang:en"),
                InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
                InlineKeyboardButton(text="Українська", callback_data="lang:uk"),
            ]
        ]
    )


def result_keyboard(lang: str, scan_id: int) -> InlineKeyboardMarkup:
    safe_data = f"vote:safe:{scan_id}"
    scam_data = f"vote:scam:{scan_id}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ " + t(lang, "vote_safe"), callback_data=safe_data),
                InlineKeyboardButton(text="🚨 " + t(lang, "vote_scam"), callback_data=scam_data),
            ],
            [
                InlineKeyboardButton(text="🟠 " + t(lang, "open_app"), callback_data="open:noytrix"),
            ],
        ]
    )


from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu(lang: str) -> ReplyKeyboardMarkup:
    labels = {
        "en": {
            "check": "🛡 Check",
            "top": "🚨 Top Scams",
            "lang": "🌐 Language",
            "profile": "👤 Profile",
        },
        "ru": {
            "check": "🛡 Проверить",
            "top": "🚨 Топ Scam",
            "lang": "🌐 Язык",
            "profile": "👤 Профиль",
        },
        "uk": {
            "check": "🛡 Перевірити",
            "top": "🚨 Топ Scam",
            "lang": "🌐 Мова",
            "profile": "👤 Профіль",
        },
    }

    x = labels.get(lang, labels["en"])

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=x["check"]),
                KeyboardButton(text=x["top"]),
            ],
            [
                KeyboardButton(text=x["lang"]),
                KeyboardButton(text=x["profile"]),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Noytrix ScamShield",
    )


def premium_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "check"), callback_data="menu:check"),
                InlineKeyboardButton(text=t(lang, "top_scams"), callback_data="menu:top"),
            ],
            [
                InlineKeyboardButton(text=t(lang, "profile"), callback_data="menu:profile"),
            ],
        ]
    )

def app_store_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤖 Android / Google Play",
                    url="https://play.google.com/store/apps/details?id=com.noytrix.app&hl=ru"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🍎 iOS",
                    callback_data="open:ios"
                )
            ],
        ]
    )
