import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
IDENTITY_DB_PATH = DATA_DIR / "identity.sqlite3"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_user_id() -> str:
    return f"usr_{uuid.uuid4().hex}"


def normalize_identity(kind: str, value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    k = str(kind or "").strip().lower()
    if k in {"email", "api_email"}:
        return raw.lower()
    if k in {"guest", "device", "install", "revenuecat", "auth_user_id", "telegram", "google_play_token"}:
        return raw
    return raw.lower()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(IDENTITY_DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def init_identity_db() -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS identities (
              user_id TEXT PRIMARY KEY,
              primary_email TEXT,
              created_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS identity_links (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              value_norm TEXT NOT NULL,
              value_raw TEXT,
              meta_json TEXT,
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              UNIQUE(kind, value_norm)
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_identity_links_user ON identity_links(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_identity_links_kind_value ON identity_links(kind, value_norm)")
        conn.commit()
    finally:
        conn.close()


init_identity_db()


def _safe_json(meta: Optional[dict]) -> str:
    try:
        return json.dumps(meta or {}, ensure_ascii=False)
    except Exception:
        return "{}"


def _existing_user_ids(cur: sqlite3.Cursor, links: Iterable[tuple[str, Any]]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for kind, value in links:
        k = str(kind or "").strip().lower()
        v = normalize_identity(k, value)
        if not k or not v:
            continue
        row = cur.execute(
            "SELECT user_id FROM identity_links WHERE kind=? AND value_norm=? LIMIT 1",
            (k, v),
        ).fetchone()
        if row and row["user_id"] not in seen:
            found.append(row["user_id"])
            seen.add(row["user_id"])
    return found


def _canonical_user_id(cur: sqlite3.Cursor, user_ids: list[str]) -> str:
    if not user_ids:
        return _new_user_id()
    q = ",".join(["?"] * len(user_ids))
    rows = cur.execute(
        f"SELECT user_id, created_at FROM identities WHERE user_id IN ({q})",
        user_ids,
    ).fetchall()
    if not rows:
        return user_ids[0]
    rows = sorted(rows, key=lambda r: (str(r["created_at"] or ""), str(r["user_id"] or "")))
    return str(rows[0]["user_id"])


def resolve_user_id(links: Iterable[tuple[str, Any]], meta: Optional[dict] = None) -> str:
    clean_links = []
    for kind, value in links:
        k = str(kind or "").strip().lower()
        v = normalize_identity(k, value)
        if k and v:
            clean_links.append((k, str(value or "").strip(), v))

    if not clean_links:
        user_id = _new_user_id()
        now = _now_iso()
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO identities(user_id, created_at, last_seen_at) VALUES(?,?,?)",
                (user_id, now, now),
            )
            conn.commit()
        finally:
            conn.close()
        return user_id

    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.cursor()
        existing = _existing_user_ids(cur, [(k, norm) for k, _raw, norm in clean_links])
        user_id = _canonical_user_id(cur, existing)

        cur.execute(
            """
            INSERT INTO identities(user_id, created_at, last_seen_at)
            VALUES(?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET last_seen_at=excluded.last_seen_at
            """,
            (user_id, now, now),
        )

        if existing:
            for old_user_id in existing:
                if old_user_id == user_id:
                    continue
                cur.execute(
                    "UPDATE identity_links SET user_id=?, last_seen_at=? WHERE user_id=?",
                    (user_id, now, old_user_id),
                )
                cur.execute("DELETE FROM identities WHERE user_id=?", (old_user_id,))

        primary_email = None
        for kind, raw, norm in clean_links:
            if kind in {"email", "api_email"} and "@" in norm:
                primary_email = norm
            cur.execute(
                """
                INSERT INTO identity_links(user_id, kind, value_norm, value_raw, meta_json, first_seen_at, last_seen_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(kind, value_norm) DO UPDATE SET
                  user_id=excluded.user_id,
                  value_raw=excluded.value_raw,
                  meta_json=excluded.meta_json,
                  last_seen_at=excluded.last_seen_at
                """,
                (user_id, kind, norm, raw, _safe_json(meta), now, now),
            )

        if primary_email:
            cur.execute(
                "UPDATE identities SET primary_email=?, last_seen_at=? WHERE user_id=?",
                (primary_email, now, user_id),
            )
        conn.commit()
        return user_id
    finally:
        conn.close()


def identity_links_for(user_id: str) -> list[dict]:
    uid = str(user_id or "").strip()
    if not uid:
        return []
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT kind, value_raw, value_norm, first_seen_at, last_seen_at
            FROM identity_links
            WHERE user_id=?
            ORDER BY kind, first_seen_at
            """,
            (uid,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def resolve_from_request(request: Any, extra_links: Optional[Iterable[tuple[str, Any]]] = None) -> str:
    headers = getattr(request, "headers", {}) or {}
    links: list[tuple[str, Any]] = []
    for header_name, kind in (
        ("x-noytrix-user-id", "internal"),
        ("x-install-user-id", "guest"),
        ("x-guest-id", "guest"),
        ("x-revenuecat-app-user-id", "revenuecat"),
        ("x-user-id", "guest"),
    ):
        value = headers.get(header_name)
        if value:
            links.append((kind, value))
    if extra_links:
        links.extend(list(extra_links))
    return resolve_user_id(links)
