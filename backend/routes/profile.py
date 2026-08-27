from collections.abc import Callable

import sqlite3
from collections.abc import Awaitable
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request


def create_profile_router(
    build_stats: Callable[[str | None], dict],
    build_achievements: Callable[[str | None], list[dict]],
    achievement_texts: Callable[[list[dict], str], list[dict]],
    profile_db_path: Path | None = None,
    authenticated_user: Callable[[Request], str | None] | None = None,
    authenticated_aliases: Callable[[Request], list[str]] | None = None,
    send_push: Callable[[str, str, str, dict], Awaitable[dict]] | None = None,
) -> APIRouter:
    router = APIRouter()
    db_path = Path(profile_db_path) if profile_db_path else None
    if db_path:
        conn = sqlite3.connect(db_path, timeout=20)
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS profile_achievement_notifications(
                user_id TEXT NOT NULL, achievement_code TEXT NOT NULL, notified_at TEXT NOT NULL,
                PRIMARY KEY(user_id,achievement_code))""")
            conn.commit()
        finally:
            conn.close()

    async def notify_new_achievement(user_id: str, achievements: list[dict], lang: str) -> None:
        if not db_path or not send_push or not user_id or user_id == "guest" or not achievements:
            return
        codes = [str(item.get("code") or "").strip() for item in achievements if item.get("code")]
        conn = sqlite3.connect(db_path, timeout=20)
        try:
            placeholders = ",".join("?" for _ in codes)
            existing = {row[0] for row in conn.execute(
                f"SELECT achievement_code FROM profile_achievement_notifications WHERE user_id=? AND achievement_code IN ({placeholders})",
                (user_id, *codes),
            ).fetchall()} if codes else set()
            fresh = [item for item in achievements if str(item.get("code") or "") not in existing]
            if not fresh:
                return
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            conn.executemany(
                "INSERT OR IGNORE INTO profile_achievement_notifications(user_id,achievement_code,notified_at) VALUES(?,?,?)",
                [(user_id, code, now) for code in codes],
            )
            conn.commit()
        finally:
            conn.close()

        achievement = fresh[-1]
        labels = {
            "first_scan": {"en": "First Scan", "ru": "Первая проверка", "uk": "Перша перевірка"},
            "scanner_10": {"en": "10 Checks Strong", "ru": "10 проверок", "uk": "10 перевірок"},
            "hunter_3": {"en": "Scam Hunter", "ru": "Охотник на скам", "uk": "Мисливець на скам"},
            "analyst_5": {"en": "Risk Analyst", "ru": "Аналитик риска", "uk": "Аналітик ризику"},
            "risk_engine_5": {"en": "Risk Engine", "ru": "Risk Engine", "uk": "Risk Engine"},
            "approved_3": {"en": "Setup Reader", "ru": "Читатель сетапов", "uk": "Читач сетапів"},
            "community_3": {"en": "Community Voice", "ru": "Голос сообщества", "uk": "Голос спільноти"},
            "pro_user": {"en": "PRO Protection", "ru": "PRO-защита", "uk": "PRO-захист"},
            "member_30_days": {"en": "One Month Safer", "ru": "Месяц вместе", "uk": "Місяць разом"},
        }
        title = labels.get(str(achievement.get("code") or ""), {}).get(lang) or str(achievement.get("title") or "Noytrix achievement")
        messages = {
            "en": (f"You just unlocked “{title}”", "That progress is yours — we noticed it. Open your profile to see what changed and keep building safer habits."),
            "ru": (f"Новое достижение: «{title}»", "Это не случайная награда — мы заметили ваш прогресс. Загляните в профиль и продолжайте укреплять свою цифровую защиту."),
            "uk": (f"Нове досягнення: «{title}»", "Це не випадкова нагорода — ми помітили ваш прогрес. Відкрийте профіль і продовжуйте зміцнювати свій цифровий захист."),
        }
        push_title, push_body = messages.get(lang, messages["en"])
        await send_push(user_id, push_title, push_body, {
            "screen": "profile", "route": "profile", "type": "achievement_unlocked",
            "achievement_code": achievement.get("code"), "dedupe_key": f"achievement:{achievement.get('code')}",
        })

    @router.get("/profile/overview")
    async def profile_overview(request: Request, userId: str | None = None, lang: str | None = "ru"):
        uid = userId or "guest"
        stats = build_stats(uid)
        achievements = achievement_texts(build_achievements(uid), (lang or "ru").lower())
        account_uid = authenticated_user(request) if authenticated_user else None
        account_aliases = {str(value).strip().lower() for value in (authenticated_aliases(request) if authenticated_aliases else [account_uid]) if value}
        if account_uid and str(uid).strip().lower() in account_aliases:
            try:
                await notify_new_achievement(str(account_uid), achievements, (lang or "ru").lower())
            except Exception as exc:
                print("[profile] achievement push failed:", str(exc)[:180])
        return {
            "ok": True,
            "user": uid,
            **stats,
            "proAccess": {
                "isPro": str(stats.get("identity", {}).get("plan") or "").lower() == "pro"
            },
            "achievements": achievements,
        }

    @router.get("/profile/stats")
    def profile_stats(userId: str | None = None):
        uid = userId or "guest"
        stats = build_stats(uid)
        trust = stats.get("trust", {})
        trading = stats.get("tradingPerformance", {})
        return {
            "ok": True,
            "user": uid,
            "scans": trust.get("scamScans", 0),
            "trades": trading.get("setupsAnalyzed", 0),
            "winrate": trading.get("acceptanceRate", 0),
            "pnl": 0,
            **stats,
        }

    @router.get("/profile/activity")
    def profile_activity(userId: str | None = None, lang: str | None = "ru"):
        uid = userId or "guest"
        stats = build_stats(uid)
        achievements = achievement_texts(build_achievements(uid), (lang or "ru").lower())
        return {
            "ok": True,
            "user": uid,
            "history": stats.get("recent", []),
            "activity": stats.get("activity", {}),
            "achievements": achievements,
        }

    return router
