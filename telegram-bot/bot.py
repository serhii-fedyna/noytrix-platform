import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN, ADMIN_TELEGRAM_ID
from db import init_db, init_scan_db, upsert_user, set_lang, get_lang, save_scan, get_scan
from i18n import t
from keyboards import lang_keyboard, result_keyboard, premium_menu, app_store_keyboard
from api import scan_input, vote_scan, get_top_scams, get_telegram_profile, confirm_telegram_link_code, create_telegram_link_code, unlink_telegram_account, track_telegram_profile_stats, check_telegram_scan_limit, NoytrixAPIError
from formatters import fmt_scan_result
from api import render_scan_card


CONNECT_WAITING = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher()



def premium_error(title: str = "Something went wrong", detail: str = "", action: str = "Please try again later.") -> str:
    clean = str(detail or "").replace("<", "").replace(">", "")
    if len(clean) > 180:
        clean = clean[:180] + "..."

    return (
        "⚠️ <b>NOYTRIX SYSTEM NOTICE</b>\n"
        "━━━━━━━━━━━━━━\n\n"
        f"❌ <b>{title}</b>\n\n"
        f"🧠 {action}\n\n"
        + (f"Details: <code>{clean}</code>\n\n" if clean else "")
        + "━━━━━━━━━━━━━━\n"
        "Noytrix Risk Engine"
    )

async def admin_alert(text: str):
    if not ADMIN_TELEGRAM_ID:
        return
    try:
        await bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID,
            text=text
        )
    except Exception:
        pass



def verdict_emoji(level: str) -> str:
    level = (level or "").lower()

    if level == "safe":
        return "🟢"

    if level == "suspicious":
        return "🟠"

    if level in {"danger", "critical"}:
        return "🔴"

    return "⚪"


@dp.message(CommandStart())
async def start(message: Message):
    user = message.from_user

    await upsert_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    lang = await get_lang(user.id)

    await message.answer(
        t(lang, "choose_lang"),
        reply_markup=lang_keyboard(),
    )


@dp.message(Command("language"))
async def language(message: Message):
    lang = await get_lang(message.from_user.id)

    await message.answer(
        t(lang, "choose_lang"),
        reply_markup=lang_keyboard(),
    )


@dp.callback_query(F.data.startswith("lang:"))
async def choose_language(callback: CallbackQuery):
    lang = callback.data.split(":", 1)[1]

    if lang not in {"en", "ru", "uk"}:
        await callback.answer()
        return

    await set_lang(callback.from_user.id, lang)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        t(lang, "welcome"),
        reply_markup=premium_menu(lang),
    )

    await callback.answer(t(lang, "lang_saved"))


@dp.callback_query(F.data.startswith("menu:"))
async def menu_callback(callback: CallbackQuery):
    lang = await get_lang(callback.from_user.id)
    action = callback.data.split(":", 1)[1]

    try:
        await callback.answer()
    except Exception:
        pass

    if action == "check":
        await callback.message.answer(
            "🛡 <b>NOYTRIX SCAMSHIELD</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"{t(lang, 'check_prompt')}\n\n"
            f"{t(lang, 'check_before_action')}"
        )
        return

    if action == "lang":
        await callback.message.answer(t(lang, "choose_lang"), reply_markup=lang_keyboard())
        return

    if action == "top":
        await send_top_scams(callback.message, lang)
        return

    if action == "profile":
        try:
            data = await get_telegram_profile(str(callback.from_user.id), lang)
            linked = data.get("linked")
            is_pro = bool(data.get("isPro"))

            email = linked.get("email") if linked else t(lang, "not_connected_plain")
            status = t(lang, "connected") if linked else t(lang, "not_connected")
            plan = "🟠 PRO" if is_pro else t(lang, "plan_free")

            stats = data.get("stats") or {}
            total_scans = stats.get("total_scans", 0)
            scam_reports = stats.get("scam_reports", 0)
            last_activity = stats.get("last_activity") or "—"

            pro_badge = "🟠 <b>PRO ACTIVE</b>" if is_pro else "⚪ <b>FREE</b>"

            text = (
                f"👤 <b>NOYTRIX ID</b>\n"
                f"━━━━━━━━━━━━━━\n\n"
                f"🆔 {t(lang, 'telegram_id')}:\n<code>{callback.from_user.id}</code>\n\n"
                f"📧 {t(lang, 'account')}:\n{email}\n\n"
                f"🔗 {t(lang, 'status')}:\n{status}\n\n"
                f"💎 {t(lang, 'plan')}:\n{pro_badge}\n\n"
                f"📊 <b>{t(lang, 'activity')}</b>\n"
                f"• {t(lang, 'total_scans')}: <b>{total_scans}</b>\n"
                f"• {t(lang, 'scam_reports')}: <b>{scam_reports}</b>\n"
                f"• {t(lang, 'last_activity')}: <code>{last_activity}</code>\n\n"
                f"━━━━━━━━━━━━━━\n\n"
                f"{t(lang, 'pro_features_full')}"
            )

            if linked:
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(text=t(lang, "profile_refresh"), callback_data="menu:profile"),
                            InlineKeyboardButton(text=t(lang, "profile_disconnect"), callback_data="profile:disconnect"),
                        ]
                    ]
                )
            else:
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(text=t(lang, "profile_connect"), callback_data="profile:connect")
                        ]
                    ]
                )

            await callback.message.answer(text, reply_markup=kb)
        except Exception as e:
            await callback.message.answer(premium_error(lang, t(lang, "profile_error"), str(e)))
        return


@dp.callback_query(F.data == "profile:disconnect")
async def profile_disconnect(callback: CallbackQuery):
    try:
        await unlink_telegram_account(str(callback.from_user.id))
        await callback.message.answer(t(lang, "account_disconnected"))
        await admin_alert(
            "🚪 <b>Telegram account disconnected</b>\n"
            f"User: <code>{callback.from_user.id}</code>"
        )
    except Exception as e:
        await callback.message.answer(premium_error(lang, t(lang, "disconnect_error"), str(e)))

    await callback.answer()


@dp.callback_query(F.data == "profile:connect")
async def profile_connect(callback: CallbackQuery):
    await callback.answer()
    CONNECT_WAITING[callback.from_user.id] = {"step": "email"}
    await callback.message.answer(
        f"{t(lang, 'connect_title')}\n\n"
        f"{t(lang, 'connect_email_prompt')}"
    )


async def send_top_scams(message: Message, lang: str):
    data = await get_top_scams(lang=lang, limit=7)
    items = data.get("items") or data.get("data") or []

    if not items:
        await message.answer(t(lang, "no_scams"))
        return

    lines = [
        "🚨 <b>NOYTRIX SCAM RADAR</b>",
        "━━━━━━━━━━━━━━",
        t(lang, "fresh_scams"),
        "",
    ]

    for i, item in enumerate(items[:7], 1):
        obj = item.get("obj") or item.get("input") or item.get("url") or "unknown"
        kind = str(item.get("kind") or "unknown").upper()
        scam_votes = item.get("scam_votes") or item.get("scamVotes") or item.get("votes") or 0
        safe_votes = item.get("safe_votes") or item.get("safeVotes") or 0

        clean = obj.replace("https://", "").replace("http://", "").strip("/")
        if len(clean) > 44:
            clean = clean[:41] + "..."

        lines.append(
            f"<b>{i}. {kind}</b>  🚨 {scam_votes}  ·  ✅ {safe_votes}\n"
            f"<code>{clean}</code>"
        )

    lines.append("")
    lines.append(t(lang, "send_anything_check"))

    await message.answer("\n\n".join(lines), disable_web_page_preview=True)


@dp.message(Command("top"))
async def top_scams(message: Message):
    lang = await get_lang(message.from_user.id)

    try:
        data = await get_top_scams(lang=lang, limit=7)
        items = data.get("items") or data.get("data") or []

        if not items:
            await message.answer(t(lang, "no_scams"))
            return

        lines = [
            "🚨 <b>NOYTRIX COMMUNITY RADAR</b>",
            "━━━━━━━━━━━━━━",
            f"<b>{t(lang, 'top')}</b>",
            "",
        ]

        for i, item in enumerate(items[:7], 1):
            obj = item.get("obj") or item.get("input") or item.get("url") or "unknown"
            kind = str(item.get("kind") or "unknown").upper()
            scam_votes = item.get("scam_votes") or item.get("scamVotes") or item.get("votes") or 0
            safe_votes = item.get("safe_votes") or item.get("safeVotes") or 0

            clean = obj.replace("https://", "").replace("http://", "").strip("/")
            if len(clean) > 46:
                clean = clean[:43] + "..."

            lines.append(
                f"<b>{i}. {kind}</b>  🚨 {scam_votes}  ·  ✅ {safe_votes}\n"
                f"<code>{clean}</code>"
            )

        lines.append("")
        lines.append(t(lang, "send_anything_check"))

        await message.answer("\n\n".join(lines), disable_web_page_preview=True)

    except Exception as e:
        await message.answer(premium_error("{t(lang, 'error')}", str(e)))


@dp.callback_query(F.data.startswith("open:"))
async def open_noytrix_callback(callback: CallbackQuery):
    lang = await get_lang(callback.from_user.id)
    action = callback.data.split(":", 1)[1]

    try:
        await callback.answer()
    except Exception:
        pass

    if action == "ios":
        await callback.message.answer(t(lang, "ios_soon"))
        return

    await callback.message.answer(
        f"{t(lang, 'open_noytrix')}\n\n{t(lang, 'choose_platform')}",
        reply_markup=app_store_keyboard(lang),
    )


@dp.callback_query(F.data.startswith("vote:"))
async def vote_callback(callback: CallbackQuery):
    lang = await get_lang(callback.from_user.id)

    try:
        _, vote, scan_id_raw = callback.data.split(":", 2)
        scan_id = int(scan_id_raw)
        row = await get_scan(scan_id, callback.from_user.id)

        if not row:
            await callback.answer(t(lang, "error"), show_alert=True)
            return

        input_text, kind = row
        reporter = callback.from_user.username or callback.from_user.first_name or str(callback.from_user.id)

        await vote_scan(
            input_text=input_text,
            kind=kind,
            vote=vote,
            lang=lang,
            user_id=f"telegram_{callback.from_user.id}",
            reporter=reporter,
        )

        await callback.answer(t(lang, "vote_done"), show_alert=False)

    except Exception as e:
        await callback.answer(t(lang, "error"), show_alert=True)


@dp.message()
async def scan_message(message: Message):
    user = message.from_user
    lang = await get_lang(user.id)

    if user.id in CONNECT_WAITING:
        state = CONNECT_WAITING.get(user.id) or {}
        step = state.get("step")

        if step == "email":
            email = (message.text or "").strip().lower()

            if "@" not in email or "." not in email:
                await message.answer(premium_error(lang, t(lang, "invalid_email"), "", t(lang, "invalid_email_action")))
                return

            try:
                await create_telegram_link_code(email, lang)
                CONNECT_WAITING[user.id] = {"step": "code", "email": email}

                await message.answer(
                    f"{t(lang, 'code_sent')}\n\n"
                    f"{t(lang, 'email_label')}: <code>{email}</code>\n\n"
                    f"{t(lang, 'send_code_now')}"
                )
            except Exception as e:
                await message.answer(premium_error(lang, t(lang, "could_not_send_code"), str(e)))
            return

        if step == "code":
            code = (message.text or "").strip()

            if not code.isdigit() or len(code) != 6:
                await message.answer(premium_error(lang, t(lang, "invalid_code"), "", t(lang, "invalid_code_action")))
                return

            try:
                data = await confirm_telegram_link_code(str(user.id), code, lang)
                CONNECT_WAITING.pop(user.id, None)

                profile = await get_telegram_profile(str(user.id), lang)
                is_pro = bool(profile.get("isPro"))

                email = data.get("email") or state.get("email") or "Unknown"
                plan_text = "🟠 <b>PRO Active</b>" if is_pro else "⚪ <b>FREE</b>"

                await message.answer(
                    f"{t(lang, 'account_connected')}\n\n"
                    f"📧 {email}\n"
                    f"💎 {t(lang, 'plan')}: {plan_text}"
                )

                await admin_alert(
                    "🔗 <b>Telegram account connected</b>\n"
                    f"User: <code>{user.id}</code>\n"
                    f"Email: <code>{email}</code>\n"
                    f"Plan: {plan_text}"
                )
            except Exception as e:
                await message.answer(premium_error(lang, t(lang, "connect_error"), str(e)))
            return


    if not message.text:
        return

    user = message.from_user
    lang = await get_lang(user.id)

    wait_msg = await message.answer(
        t(lang, "checking")
    )

    try:
        data = await scan_input(
            input_text=message.text,
            lang=lang,
            user_id=f"telegram_{user.id}",
        )

        level = str(data.get("level") or "unknown")
        kind = data.get("kind") or "unknown"
        score = int(data.get("score") or 0)

        scan_id = await save_scan(
            telegram_id=user.id,
            input_text=message.text,
            kind=kind,
            level=level,
            score=score,
        )

        try:
            await track_telegram_profile_stats(str(user.id), level, lang)
        except Exception as e:
            logging.warning("profile stats track failed: %s", e)

        if level.lower() in {"danger", "critical"}:
            await admin_alert(
                "🚨 <b>Danger scan detected</b>\n"
                f"User: <code>{user.id}</code>\n"
                f"Input: <code>{message.text[:180]}</code>\n"
                f"Level: <b>{level}</b>\n"
                f"Score: <b>{score}/100</b>"
            )

        text = fmt_scan_result(data, lang)

        await bot.send_chat_action(message.chat.id, "upload_photo")
        card_bytes = await render_scan_card(data, lang)

        await wait_msg.delete()

        short_caption = "🛡 Noytrix ScamShield"

        await message.answer_photo(
            photo=BufferedInputFile(
                card_bytes,
                filename=f"scan_{scan_id}.png"
            ),
            caption=short_caption,
        )

        await message.answer(
            text,
            reply_markup=result_keyboard(
                lang=lang,
                scan_id=scan_id,
            ),
        )

    except NoytrixAPIError as e:
        err_text = f"❌ {t(lang, 'error')}\n\n<code>{str(e)[:300]}</code>"
        try:
            await wait_msg.edit_text(err_text)
        except Exception:
            await message.answer(err_text)

    except Exception as e:
        err_text = f"❌ {t(lang, 'error')}\n\n<code>{str(e)[:300]}</code>"
        try:
            await wait_msg.edit_text(err_text)
        except Exception:
            await message.answer(err_text)


async def main():
    await init_db()
    await init_scan_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
