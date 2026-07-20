from collections.abc import Callable
from typing import Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel


class MarketSnapshot(BaseModel):
    symbol: str
    lastPrice: float | None = None
    priceChangePercent: float | None = None
    quoteVolume: float | None = None
    vol24hProxy: float | None = None
    spreadBps: float | None = None


class UserIntent(BaseModel):
    amountUsdt: float
    horizon: str
    targetPct: float
    maxDrawdownPct: float
    alreadyHolding: bool = False
    reason: str = "STRATEGY"
    userId: str | None = None


class Behavior(BaseModel):
    analyses24h: int = 0


class ImmunityAnalyzeRequest(BaseModel):
    market: MarketSnapshot
    user: UserIntent
    behavior: Behavior | None = None


IMMUNITY_I18N = {
    "en": {
        "verdict": {"critical": "REJECTED", "high": "HIGH RISK", "medium": "RISKY", "low": "OK"},
        "reasons": {
            "FOMO_AFTER_PUMP": "Price is up {change24h}% in 24h - common FOMO trap.",
            "TARGET_TOO_HIGH": "Target {target}% looks aggressive for horizon ({horizon}).",
            "DRAWDOWN_MISMATCH": "Volatility (~{vol}%) exceeds your max drawdown ({dd}).",
            "WIDE_SPREAD": "Spread is wide (~{spread_bps} bps) - execution risk.",
            "OVERTRADING_SIGNAL": "Many analyses today ({count}) - risk of impulsive actions.",
            "NARRATIVE_PRESSURE": "Your reason is hype/pressure - manipulation risk increases.",
            "ADD_WHILE_HOT": "Adding while already holding on short horizon can amplify mistakes.",
            "BIG_TICKET": "Large ticket size - consider splitting entries.",
        },
        "plan": {
            "fix_1": "Split entries (2-3 parts) instead of one full buy.",
            "fix_2": "Define invalidation before entry (max loss or time-stop).",
            "now_high": "Do not enter immediately. Wait for confirmation or a pullback.",
            "safer_high": "If you want exposure: start with a very small starter position.",
            "now_med": "If you enter: do it in parts and keep risk tight.",
            "safer_med": "Prefer entry after consolidation, not during spike.",
            "now_low": "Plan looks reasonable if you follow your risk limits.",
            "safer_low": "Avoid changing the plan mid-trade.",
        },
    },
    "ru": {
        "verdict": {"critical": "REJECTED", "high": "HIGH RISK", "medium": "RISKY", "low": "OK"},
        "reasons": {
            "FOMO_AFTER_PUMP": "Price is up {change24h}% in 24h - common FOMO trap.",
            "TARGET_TOO_HIGH": "Target {target}% looks aggressive for horizon ({horizon}).",
            "DRAWDOWN_MISMATCH": "Volatility (~{vol}%) exceeds your max drawdown ({dd}).",
            "WIDE_SPREAD": "Spread is wide (~{spread_bps} bps) - execution risk.",
            "OVERTRADING_SIGNAL": "Many analyses today ({count}) - risk of impulsive actions.",
            "NARRATIVE_PRESSURE": "Your reason is hype/pressure - manipulation risk increases.",
            "ADD_WHILE_HOT": "Adding while already holding on short horizon can amplify mistakes.",
            "BIG_TICKET": "Large ticket size - consider splitting entries.",
        },
        "plan": {
            "fix_1": "Split entries (2-3 parts) instead of one full buy.",
            "fix_2": "Define invalidation before entry (max loss or time-stop).",
            "now_high": "Do not enter immediately. Wait for confirmation or a pullback.",
            "safer_high": "If you want exposure: start with a very small starter position.",
            "now_med": "If you enter: do it in parts and keep risk tight.",
            "safer_med": "Prefer entry after consolidation, not during spike.",
            "now_low": "Plan looks reasonable if you follow your risk limits.",
            "safer_low": "Avoid changing the plan mid-trade.",
        },
    },
}


def _pick_lang(request: Request) -> str:
    acc = (request.headers.get("accept-language") or "").lower()
    return "ru" if ("ru" in acc or acc.startswith("ru")) else "en"


def _clamp(n: float, a: float, b: float) -> float:
    return max(a, min(b, n))


def _level(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 55:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _color(level: str) -> str:
    if level == "critical":
        return "#FF6B6B"
    if level == "high":
        return "#ff7b7b"
    if level == "medium":
        return "#FFB547"
    return "#29d37a"


def _uniq(xs: list[str]) -> list[str]:
    out, seen = [], set()
    for x in xs or []:
        s = (x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def create_immunity_router(
    get_lang: Callable,
    require_app_key: Callable,
    tr: Callable[[str, str], str],
    community_immunity_compute: Callable[[str, Optional[str]], dict],
    community_top_items: Callable[..., list[dict]],
    get_user_id: Callable,
    enforce_free_quota: Callable,
    profile_track_event: Callable,
    daily_free_limit: int,
) -> APIRouter:
    router = APIRouter()

    @router.get("/immunity")
    def immunity_get(
        request: Request,
        input: str = Query(...),
        kind: str | None = None,
        lang: str | None = None,
    ):
        L = get_lang(request, lang)
        data = community_immunity_compute(input, kind)

        v = data.get("community_verdict")
        if v == "safe":
            data["community_verdict_text"] = tr(L, "safe")
        elif v == "scam":
            data["community_verdict_text"] = tr(L, "danger")
        elif v == "mixed":
            data["community_verdict_text"] = tr(L, "suspicious")
        else:
            data["community_verdict_text"] = "-"

        data["lang"] = L
        return data

    @router.get("/immunity/top")
    def immunity_top(request: Request, limit: int = 50, lang: str | None = None):
        L = get_lang(request, lang)
        require_app_key(request, L)

        items = community_top_items(limit=limit, only_scam_first=True)
        out = []
        for it in items:
            total_users = int(it["total_users"] or 0)
            scam_votes = int(it["scam_votes"] or 0)
            safe_votes = int(it["safe_votes"] or 0)
            immunity_score = int(round((safe_votes / total_users) * 100)) if total_users else 0
            out.append(
                {
                    "obj": it["obj"],
                    "kind": it["kind"],
                    "checks": total_users,
                    "scam_votes": scam_votes,
                    "safe_votes": safe_votes,
                    "immunity_score": immunity_score,
                    "community_verdict": it["community_verdict"],
                    "last_seen": it["last_seen"],
                    "last_reporter": it["last_reporter"],
                    "total_users": total_users,
                }
            )
        return {"items": out}

    @router.post("/immunity/analyze")
    async def immunity_analyze(payload: ImmunityAnalyzeRequest, request: Request):
        L = _pick_lang(request)
        t = IMMUNITY_I18N[L]

        uid = payload.user.userId or get_user_id(request, None)
        quota_info = enforce_free_quota(request, feature="immunity_analyze", user_id=uid, lang=L)

        reasons = []
        score = 0

        m = payload.market
        u = payload.user
        b = payload.behavior or Behavior()

        change24h = m.priceChangePercent
        vol = m.vol24hProxy
        spread_bps = m.spreadBps

        def add_reason(code: str, sev: int, **fmt):
            txt = t["reasons"][code].format(**fmt)
            reasons.append({"code": code, "text": txt, "severity": sev})

        if isinstance(change24h, (int, float)) and change24h >= 8 and u.horizon in ("1D", "1W"):
            score += 18
            add_reason("FOMO_AFTER_PUMP", 8, change24h=round(change24h, 2))

        horizon_cap = 8 if u.horizon == "1D" else 18 if u.horizon == "1W" else 35 if u.horizon == "1M" else 60
        if isinstance(u.targetPct, (int, float)) and u.targetPct > horizon_cap:
            score += 22
            add_reason("TARGET_TOO_HIGH", 9, target=round(u.targetPct, 2), horizon=u.horizon)

        if isinstance(vol, (int, float)) and isinstance(u.maxDrawdownPct, (int, float)) and u.maxDrawdownPct > 0 and vol > u.maxDrawdownPct:
            score += 16
            add_reason("DRAWDOWN_MISMATCH", 8, vol=round(vol, 2), dd=round(u.maxDrawdownPct, 2))

        if isinstance(spread_bps, (int, float)) and spread_bps >= 25:
            score += 10
            add_reason("WIDE_SPREAD", 6, spread_bps=int(round(spread_bps)))

        if b.analyses24h >= 6:
            score += 12
            add_reason("OVERTRADING_SIGNAL", 7, count=int(b.analyses24h))

        if (u.reason or "").upper() == "HYPE":
            score += 14
            add_reason("NARRATIVE_PRESSURE", 7)

        if u.alreadyHolding and u.horizon in ("1D", "1W"):
            score += 8
            add_reason("ADD_WHILE_HOT", 5)

        if isinstance(u.amountUsdt, (int, float)) and u.amountUsdt >= 5000:
            score += 8
            add_reason("BIG_TICKET", 5)

        score = int(_clamp(score, 0, 100))
        level = _level(score)
        verdict = t["verdict"][level]
        color = _color(level)
        top = sorted(reasons, key=lambda x: x.get("severity", 0), reverse=True)[:3]

        p = t["plan"]
        fixes = [p["fix_1"], p["fix_2"]]
        now = []
        safer = []

        if level in ("critical", "high"):
            now.append(p["now_high"])
            safer.append(p["safer_high"])
        elif level == "medium":
            now.append(p["now_med"])
            safer.append(p["safer_med"])
        else:
            now.append(p["now_low"])
            safer.append(p["safer_low"])

        resp = {
            "score": score,
            "level": level,
            "verdict": verdict,
            "color": color,
            "topReasons": top,
            "plan": {
                "now": _uniq(now),
                "fixes": _uniq(fixes)[:6],
                "safer": _uniq(safer)[:6],
                "reasons": [r["text"] for r in top],
            },
            "quota": {
                "freeLimit": quota_info.get("freeLimit", daily_free_limit),
                "feature": quota_info.get("feature", "immunity_analyze"),
                "day": quota_info.get("day"),
                "used": quota_info.get("used", 0),
                "left": quota_info.get("left", 0),
            },
            "isPro": bool(quota_info.get("isPro", False)),
        }

        try:
            profile_track_event(
                uid,
                "immunity_analyze",
                object_ref=(m.symbol or "").strip(),
                meta={
                    "symbol": (m.symbol or "").strip(),
                    "score": score,
                    "level": level,
                    "verdict": verdict,
                    "targetPct": u.targetPct,
                    "horizon": u.horizon,
                    "isPro": bool(quota_info.get("isPro", False)),
                },
            )
        except Exception as e:
            print("[profile] immunity track error:", e)

        return resp

    return router
