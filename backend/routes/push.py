from collections.abc import Callable

from fastapi import APIRouter, Body, Request


def create_push_router(get_lang: Callable, require_app_key: Callable) -> APIRouter:
    router = APIRouter()

    @router.post("/push/register")
    async def push_register(request: Request, payload: dict = Body(...), lang: str | None = None):
        selected_lang = get_lang(request, lang)
        require_app_key(request, selected_lang)

        token = str(payload.get("expo_token", "")).strip()
        if token.startswith("ExponentPushToken") and len(token) > 30:
            return {"ok": True, "legacy": True, "provider": "onesignal", "ignored": True}
        return {"ok": False, "reason": "bad token"}

    return router
