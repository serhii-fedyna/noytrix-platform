"""Daily, user-facing scam intelligence feed.

This module deliberately keeps daily alerts separate from the scan quota.  A
signal is collected once by the threat pipeline, while a user's reaction,
saved copy and expanded AI investigation are stored against their identity.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

try:
    from fastapi import APIRouter, Body, HTTPException, Query, Request
except ModuleNotFoundError:
    # Lightweight unit tests exercise the pure feed logic without FastAPI.
    # Production always installs FastAPI before this router is created.
    APIRouter = Any
    Request = Any

    def Body(*_args, **_kwargs):
        return None

    def Query(*_args, **_kwargs):
        return None

    class HTTPException(Exception):
        pass

try:
    from scamshield.intelligence.postgres_intelligence import connect, guess_entity_type, normalize_entity
except ModuleNotFoundError:
    # The lightweight unit-test runtime deliberately has no PostgreSQL driver.
    # Keep deterministic, pure helpers testable without a database connection.
    connect = None

    def normalize_entity(value: str) -> str:
        value = str(value or "").strip().lower().split("#")[0].rstrip("/")
        value = re.sub(r"^https?://", "", value)
        return re.sub(r"^www\.", "", value)

    def guess_entity_type(value: str) -> str:
        value = str(value or "").strip().lower()
        if value.startswith(("https://", "http://")):
            return "url"
        return "domain" if "." in value and " " not in value else "text"


_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False
_LANGS = {"en", "ru", "uk"}

_COPY = {
    "en": {
        "title": "Scam of the day",
        "summary": "Noytrix detected a fresh high-risk crypto threat. Review it before you connect, approve, sign or send.",
        "source": "Noytrix threat intelligence",
        "empty": "No new high-risk signal has been added today.",
        "saved": "Saved scam signals",
        "saved_empty": "Save a signal to keep its full investigation here.",
        "unavailable": "This signal is no longer available. Please refresh the feed.",
    },
    "ru": {
        "title": "Скам дня",
        "summary": "Noytrix обнаружил свежую крипто-угрозу с высоким риском. Проверьте её до подключения кошелька, approve, подписи или отправки средств.",
        "source": "Аналитика угроз Noytrix",
        "empty": "Сегодня новых сигналов с высоким риском пока нет.",
        "saved": "Сохранённые сигналы скама",
        "saved_empty": "Сохраните сигнал, чтобы его полный разбор остался здесь.",
        "unavailable": "Этот сигнал больше недоступен. Обновите ленту.",
    },
    "uk": {
        "title": "Скам дня",
        "summary": "Noytrix виявив свіжу криптозагрозу з високим ризиком. Перевірте її до підключення гаманця, approve, підпису або надсилання коштів.",
        "source": "Аналітика загроз Noytrix",
        "empty": "Сьогодні нових сигналів з високим ризиком ще немає.",
        "saved": "Збережені сигнали шахрайства",
        "saved_empty": "Збережіть сигнал, щоб його повний розбір залишився тут.",
        "unavailable": "Цей сигнал більше недоступний. Оновіть стрічку.",
    },
}


def normalize_language(value: str | None) -> str:
    value = str(value or "en").lower()
    if value.startswith(("uk", "ua")):
        return "uk"
    if value.startswith("ru"):
        return "ru"
    return "en"


def signal_id_for(source: str, source_url: str, target: str) -> str:
    normalized = normalize_entity(target)
    stable = "|".join((str(source or "reddit").lower(), str(source_url or "").strip().lower(), normalized))
    return "sod_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    if connect is None:
        raise RuntimeError("PostgreSQL intelligence driver is unavailable")
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS scam_of_day_signals (
                        id TEXT PRIMARY KEY,
                        day_key DATE NOT NULL,
                        source TEXT NOT NULL DEFAULT 'reddit',
                        source_url TEXT NOT NULL DEFAULT '',
                        target TEXT NOT NULL,
                        normalized_target TEXT NOT NULL,
                        entity_type TEXT NOT NULL DEFAULT 'text',
                        source_title TEXT NOT NULL DEFAULT '',
                        source_summary TEXT NOT NULL DEFAULT '',
                        risk_level TEXT NOT NULL DEFAULT 'danger',
                        risk_score INTEGER NOT NULL DEFAULT 70,
                        detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        raw_record JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    CREATE INDEX IF NOT EXISTS idx_scam_of_day_signals_day
                        ON scam_of_day_signals(day_key, risk_score DESC, detected_at DESC);
                    CREATE TABLE IF NOT EXISTS scam_of_day_user_state (
                        user_id TEXT NOT NULL,
                        signal_id TEXT NOT NULL REFERENCES scam_of_day_signals(id) ON DELETE CASCADE,
                        reaction TEXT NULL CHECK (reaction IN ('like', 'dislike')),
                        saved BOOLEAN NOT NULL DEFAULT FALSE,
                        saved_payload JSONB NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        PRIMARY KEY (user_id, signal_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_scam_of_day_saved
                        ON scam_of_day_user_state(user_id, saved, updated_at DESC);
                    CREATE TABLE IF NOT EXISTS scam_of_day_ai_cache (
                        signal_id TEXT NOT NULL REFERENCES scam_of_day_signals(id) ON DELETE CASCADE,
                        language TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        PRIMARY KEY (signal_id, language)
                    );
                """)
            conn.commit()
        _SCHEMA_READY = True


def record_scam_of_day_signal(
    target: str,
    *,
    source: str = "reddit",
    source_url: str = "",
    title: str = "",
    summary: str = "",
    score: int = 70,
    raw_record: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Insert or refresh a daily threat signal and return its stable id.

    Collector failures must never stop the normal threat import, hence this
    helper returns ``None`` when PostgreSQL is unavailable.
    """
    target = str(target or "").strip()
    if not target:
        return None
    try:
        _ensure_schema()
        score = max(0, min(int(score or 0), 100))
        level = "critical" if score >= 85 else "danger" if score >= 65 else "suspicious"
        signal_id = signal_id_for(source, source_url, target)
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO scam_of_day_signals (
                        id, day_key, source, source_url, target, normalized_target,
                        entity_type, source_title, source_summary, risk_level,
                        risk_score, detected_at, raw_record
                    ) VALUES (
                        %(id)s, (now() AT TIME ZONE 'UTC')::date, %(source)s, %(source_url)s,
                        %(target)s, %(normalized_target)s, %(entity_type)s, %(title)s,
                        %(summary)s, %(risk_level)s, %(risk_score)s, now(), %(raw_record)s::jsonb
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        day_key = EXCLUDED.day_key,
                        source_title = EXCLUDED.source_title,
                        source_summary = EXCLUDED.source_summary,
                        risk_score = GREATEST(scam_of_day_signals.risk_score, EXCLUDED.risk_score),
                        risk_level = CASE
                            WHEN GREATEST(scam_of_day_signals.risk_score, EXCLUDED.risk_score) >= 85 THEN 'critical'
                            WHEN GREATEST(scam_of_day_signals.risk_score, EXCLUDED.risk_score) >= 65 THEN 'danger'
                            ELSE 'suspicious'
                        END,
                        detected_at = now(), raw_record = EXCLUDED.raw_record, updated_at = now()
                    """,
                    {
                        "id": signal_id,
                        "source": str(source or "reddit")[:80],
                        "source_url": str(source_url or "")[:2000],
                        "target": target[:2000],
                        "normalized_target": normalize_entity(target)[:2000],
                        "entity_type": guess_entity_type(target),
                        "title": str(title or "")[:1000],
                        "summary": str(summary or "")[:4000],
                        "risk_level": level,
                        "risk_score": score,
                        "raw_record": json.dumps(raw_record or {}, ensure_ascii=False),
                    },
                )
            conn.commit()
        return signal_id
    except Exception as exc:
        print("[scam_of_day] record skipped:", str(exc)[:250])
        return None


def _card(row: Dict[str, Any], lang: str) -> Dict[str, Any]:
    copy = _COPY[lang]
    target = str(row.get("target") or "")
    return {
        "id": row["id"],
        "title": copy["title"],
        "target": target,
        "summary": copy["summary"],
        "source": copy["source"],
        "source_type": str(row.get("source") or "reddit"),
        "detected_at": row.get("detected_at").isoformat() if hasattr(row.get("detected_at"), "isoformat") else str(row.get("detected_at") or ""),
        "risk_level": str(row.get("risk_level") or "danger"),
        "risk_score": int(row.get("risk_score") or 0),
        "entity_type": str(row.get("entity_type") or "text"),
        "reaction": row.get("reaction"),
        "saved": bool(row.get("saved")),
    }


def _current_rows(user_id: str, *, saved_only: bool = False) -> list[Dict[str, Any]]:
    _ensure_schema()
    predicate = "state.saved = TRUE" if saved_only else "signal.day_key = (now() AT TIME ZONE 'UTC')::date"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT signal.*, state.reaction, COALESCE(state.saved, FALSE) AS saved,
                       state.saved_payload
                FROM scam_of_day_signals signal
                LEFT JOIN scam_of_day_user_state state
                    ON state.signal_id = signal.id AND state.user_id = %(user_id)s
                WHERE {predicate}
                ORDER BY signal.risk_score DESC, signal.detected_at DESC
                LIMIT 24
                """,
                {"user_id": user_id},
            )
            return list(cur.fetchall())


def _state_user(user_id: Optional[str]) -> str:
    if not user_id or not str(user_id).strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail={"error": "identity_required", "message": "Sign in to save or rate scam signals."})
    return str(user_id).strip()[:500]


def create_scam_of_day_router(
    get_lang: Callable[[Request, Optional[str]], str],
    require_app_key: Callable[[Request, str], None],
    get_user_id: Callable[[Request, Optional[str]], Optional[str]],
    analyze_signal: Callable[[str, str, str], Awaitable[Dict[str, Any]]],
) -> APIRouter:
    router = APIRouter(tags=["scam-of-day"])

    @router.get("/scam-of-day")
    async def get_scam_of_day(request: Request, lang: Optional[str] = Query(None), userId: Optional[str] = Query(None)):
        language = normalize_language(get_lang(request, lang))
        require_app_key(request, language)
        user_id = _state_user(get_user_id(request, userId))
        try:
            rows = await asyncio.to_thread(_current_rows, user_id)
        except Exception as exc:
            raise HTTPException(status_code=503, detail={"error": "scam_feed_unavailable", "message": str(exc)[:180]})
        return {"ok": True, "day": datetime.now(timezone.utc).date().isoformat(), "items": [_card(row, language) for row in rows]}

    @router.get("/scam-of-day/saved")
    async def get_saved_scam_signals(request: Request, lang: Optional[str] = Query(None), userId: Optional[str] = Query(None)):
        language = normalize_language(get_lang(request, lang))
        require_app_key(request, language)
        user_id = _state_user(get_user_id(request, userId))
        rows = await asyncio.to_thread(_current_rows, user_id, saved_only=True)
        return {"ok": True, "items": [_card(row, language) for row in rows]}

    async def _signal_or_404(signal_id: str, user_id: str) -> Dict[str, Any]:
        def read() -> Optional[Dict[str, Any]]:
            _ensure_schema()
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT signal.*, state.reaction, COALESCE(state.saved, FALSE) AS saved
                        FROM scam_of_day_signals signal
                        LEFT JOIN scam_of_day_user_state state
                            ON state.signal_id = signal.id AND state.user_id = %(user_id)s
                        WHERE signal.id = %(signal_id)s
                        """,
                        {"signal_id": signal_id, "user_id": user_id},
                    )
                    return cur.fetchone()
        row = await asyncio.to_thread(read)
        if not row:
            raise HTTPException(status_code=404, detail={"error": "scam_signal_unavailable", "message": "Signal is unavailable."})
        return row

    async def _analysis(row: Dict[str, Any], language: str, user_id: str) -> Dict[str, Any]:
        signal_id = row["id"]
        def cached() -> Optional[Dict[str, Any]]:
            _ensure_schema()
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT payload FROM scam_of_day_ai_cache WHERE signal_id = %(id)s AND language = %(language)s", {"id": signal_id, "language": language})
                    result = cur.fetchone()
                    return dict(result["payload"]) if result and result.get("payload") else None
        payload = await asyncio.to_thread(cached)
        if payload:
            return payload
        payload = await analyze_signal(str(row.get("target") or ""), language, user_id)
        def store() -> None:
            _ensure_schema()
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO scam_of_day_ai_cache(signal_id, language, payload)
                        VALUES (%(id)s, %(language)s, %(payload)s::jsonb)
                        ON CONFLICT(signal_id, language) DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
                        """,
                        {"id": signal_id, "language": language, "payload": json.dumps(payload, ensure_ascii=False)},
                    )
                conn.commit()
        await asyncio.to_thread(store)
        return payload

    @router.get("/scam-of-day/{signal_id}/analysis")
    async def get_scam_signal_analysis(request: Request, signal_id: str, lang: Optional[str] = Query(None), userId: Optional[str] = Query(None)):
        language = normalize_language(get_lang(request, lang))
        require_app_key(request, language)
        user_id = _state_user(get_user_id(request, userId))
        row = await _signal_or_404(signal_id, user_id)
        payload = await _analysis(row, language, user_id)
        return {"ok": True, "signal": _card(row, language), "analysis": payload}

    @router.post("/scam-of-day/{signal_id}/reaction")
    async def set_scam_signal_reaction(request: Request, signal_id: str, body: Dict[str, Any] = Body(default={}), lang: Optional[str] = Query(None), userId: Optional[str] = Query(None)):
        language = normalize_language(get_lang(request, lang))
        require_app_key(request, language)
        user_id = _state_user(get_user_id(request, userId))
        await _signal_or_404(signal_id, user_id)
        reaction = body.get("reaction")
        if reaction not in {"like", "dislike", None, ""}:
            raise HTTPException(status_code=400, detail={"error": "invalid_reaction", "message": "Reaction is invalid."})
        reaction = reaction or None
        def write() -> None:
            _ensure_schema()
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO scam_of_day_user_state(user_id, signal_id, reaction)
                        VALUES (%(user_id)s, %(signal_id)s, %(reaction)s)
                        ON CONFLICT(user_id, signal_id) DO UPDATE SET reaction = EXCLUDED.reaction, updated_at = now()
                        """,
                        {"user_id": user_id, "signal_id": signal_id, "reaction": reaction},
                    )
                conn.commit()
        await asyncio.to_thread(write)
        return {"ok": True, "reaction": reaction}

    @router.post("/scam-of-day/{signal_id}/save")
    async def save_scam_signal(request: Request, signal_id: str, body: Dict[str, Any] = Body(default={}), lang: Optional[str] = Query(None), userId: Optional[str] = Query(None)):
        language = normalize_language(get_lang(request, lang))
        require_app_key(request, language)
        user_id = _state_user(get_user_id(request, userId))
        row = await _signal_or_404(signal_id, user_id)
        saved = bool(body.get("saved", True))
        analysis = await _analysis(row, language, user_id) if saved else None
        payload = {"signal": _card(row, language), "analysis": analysis} if saved else None
        def write() -> None:
            _ensure_schema()
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO scam_of_day_user_state(user_id, signal_id, saved, saved_payload)
                        VALUES (%(user_id)s, %(signal_id)s, %(saved)s, %(payload)s::jsonb)
                        ON CONFLICT(user_id, signal_id) DO UPDATE SET
                            saved = EXCLUDED.saved, saved_payload = EXCLUDED.saved_payload, updated_at = now()
                        """,
                        {"user_id": user_id, "signal_id": signal_id, "saved": saved, "payload": json.dumps(payload, ensure_ascii=False)},
                    )
                conn.commit()
        await asyncio.to_thread(write)
        return {"ok": True, "saved": saved}

    return router
