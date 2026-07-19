from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Request
from pydantic import BaseModel


class ScanVoteIn(BaseModel):
    input: str
    kind: str | None = None
    is_scam: bool = False
    userId: str | None = None
    reporter: str | None = None
    vote: str | None = None
    obj: str | None = None


def create_community_router(
    get_lang: Callable,
    require_app_key: Callable,
    normalize_obj: Callable[[str | None], str],
    normalize_kind_for_vote: Callable[[str | None, str], str],
    vote_user_id: Callable[[Request, Any], str],
    vote_reporter_name: Callable[[Any, str], str],
    scan_db_connect: Callable,
    profile_track_event: Callable,
    community_snapshot: Callable[[str, str], dict],
    community_top_items: Callable[..., list[dict]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/scan/vote")
    def scan_vote(request: Request, payload: ScanVoteIn = Body(...), lang: str | None = None):
        L = get_lang(request, lang)
        require_app_key(request, L)

        raw_obj = payload.obj if payload.obj is not None else payload.input
        obj = normalize_obj(raw_obj)
        if not obj:
            return {"ok": False, "error": "empty_input"}

        kind = normalize_kind_for_vote(payload.kind, obj)
        user_id = vote_user_id(request, payload)
        reporter_name = vote_reporter_name(payload, user_id)

        vote_str = (payload.vote or "").strip().lower()
        if vote_str in {"scam", "safe"}:
            is_scam = 1 if vote_str == "scam" else 0
        else:
            is_scam = 1 if payload.is_scam else 0

        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        conn = scan_db_connect()
        try:
            cur = conn.cursor()
            existing = cur.execute(
                """
                SELECT id
                FROM scan_votes
                WHERE obj=? AND kind=? AND user_id=?
                LIMIT 1
                """,
                (obj, kind, user_id),
            ).fetchone()

            if existing:
                cur.execute(
                    """
                    UPDATE scan_votes
                    SET is_scam=?, reporter_name=?, updated_at=?
                    WHERE id=?
                    """,
                    (is_scam, reporter_name, now_iso, existing[0]),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO scan_votes
                      (obj, kind, is_scam, user_id, reporter_name, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (obj, kind, is_scam, user_id, reporter_name, now_iso, now_iso),
                )
            conn.commit()
        finally:
            conn.close()

        try:
            profile_track_event(
                user_id,
                "community_vote",
                object_ref=obj,
                meta={
                    "kind": kind,
                    "vote": "scam" if bool(is_scam) else "safe",
                    "reporter": reporter_name,
                },
            )
        except Exception as e:
            print("[profile] vote track error:", e)

        community = community_snapshot(obj, kind)
        return {
            "ok": True,
            "object": obj,
            "kind": kind,
            "user_id": user_id,
            "is_scam": bool(is_scam),
            "community": community,
        }

    @router.get("/scan/stats")
    def scan_stats(request: Request, limit: int = 200, lang: str | None = None):
        L = get_lang(request, lang)
        require_app_key(request, L)

        items = community_top_items(limit=limit, only_scam_first=True)
        out = []
        for it in items:
            checks = int(it["scam_votes"] or 0) + int(it["safe_votes"] or 0)
            out.append(
                {
                    "obj": it["obj"],
                    "kind": it["kind"],
                    "checks": checks,
                    "scam_votes": int(it["scam_votes"] or 0),
                    "safe_votes": int(it["safe_votes"] or 0),
                    "total_users": int(it["total_users"] or 0),
                    "community_verdict": it["community_verdict"],
                    "last_seen": it["last_seen"],
                    "last_reporter": it["last_reporter"],
                }
            )
        return out

    @router.get("/community/top-scams")
    def community_top_scams(limit: int = 20):
        return {"items": community_top_items(limit=limit, only_scam_first=True)}

    @router.get("/community/stats")
    def community_stats(limit: int = 20):
        return {"items": community_top_items(limit=limit, only_scam_first=True)}

    @router.get("/community/top")
    def community_top(limit: int = 20):
        return {"items": community_top_items(limit=limit, only_scam_first=True)}

    return router
