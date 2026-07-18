from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request

from calendar_router import router as calendar_router
from news_router import news_list


router = APIRouter()


def _norm_lang(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw.startswith("ru"):
        return "ru"
    if raw.startswith("uk") or raw.startswith("ua"):
        return "uk"
    return "en"


def _lang_from_request(request: Request, lang_q: str | None) -> str:
    if lang_q:
        return _norm_lang(lang_q)
    query_lang = request.query_params.get("lang") or request.query_params.get("language")
    if query_lang:
        return _norm_lang(query_lang)
    header_lang = request.headers.get("x-lang") or request.headers.get("x-language")
    if header_lang:
        return _norm_lang(header_lang)
    accept = (request.headers.get("accept-language") or "").lower()
    if "uk" in accept or "ua" in accept:
        return "uk"
    if "ru" in accept:
        return "ru"
    return "en"


@router.get("/")
def root():
    return {
        "ok": True,
        "service": "Noytrix API",
        "version": "production",
    }


@router.get("/health")
def health():
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/events")
@router.get("/api/events")
async def events_alias(
    d1: str | None = Query(None, alias="from"),
    d2: str | None = Query(None, alias="to"),
    types: str | None = Query(None),
    impact: str | None = Query(None),
):
    for route in calendar_router.routes:
        if getattr(route, "path", "") == "/calendar/events":
            return await route.endpoint(d1=d1, d2=d2, types=types, impact=impact)
    return {"items": [], "lang": "en"}


@router.get("/news")
@router.get("/api/news")
async def news_alias(request: Request, lang: str | None = None, limit: int = 20):
    selected_lang = _lang_from_request(request, lang)
    try:
        items = await news_list(limit=limit)
    except Exception as exc:
        print("[news] error:", exc)
        items = []
    return {
        "items": items,
        "lang": selected_lang,
    }
