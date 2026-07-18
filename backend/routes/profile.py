from collections.abc import Callable

from fastapi import APIRouter


def create_profile_router(
    build_stats: Callable[[str | None], dict],
    build_achievements: Callable[[str | None], list[dict]],
    achievement_texts: Callable[[list[dict], str], list[dict]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/profile/overview")
    def profile_overview(userId: str | None = None, lang: str | None = "ru"):
        uid = userId or "guest"
        stats = build_stats(uid)
        achievements = achievement_texts(build_achievements(uid), (lang or "ru").lower())
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
