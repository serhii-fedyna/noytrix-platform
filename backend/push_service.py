import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx


PUSH_LANGS = ("en", "ru", "uk")
PUSH_DEFAULT_DEDUPE_SEC = 12 * 60 * 60
PUSH_CATEGORY_LIMITS = {
    "education": 1,
    "market": 2,
    "security": 2,
    "general": 2,
}


class NoytrixPushService:
    def __init__(self, data_dir: Path, app_id: str, api_key: str):
        self.db_path = Path(data_dir) / "push_dedupe.sqlite3"
        self.app_id = (app_id or "").strip()
        self.api_key = (api_key or "").strip()
        self.init_db()

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=20)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        conn = self.connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sent_push_alerts (
                  dedupe_key TEXT PRIMARY KEY,
                  title TEXT,
                  body TEXT,
                  data_json TEXT,
                  first_sent_at TEXT NOT NULL,
                  last_sent_at TEXT NOT NULL,
                  send_count INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS push_daily_counts (
                  day TEXT NOT NULL,
                  category TEXT NOT NULL,
                  send_count INTEGER NOT NULL DEFAULT 0,
                  updated_at TEXT NOT NULL,
                  PRIMARY KEY(day, category)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS calendar_push_reminders (
                  event_id TEXT PRIMARY KEY,
                  title TEXT,
                  start_ts TEXT,
                  sent_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def norm_target(value) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        try:
            u = raw if raw.startswith(("http://", "https://")) else "http://" + raw
            host = (urlparse(u).hostname or raw).lower()
            return host[4:] if host.startswith("www.") else host
        except Exception:
            return raw.split("?")[0].strip("/")

    def dedupe_key(self, title: str, body: str, data: dict | None = None) -> str:
        data = data if isinstance(data, dict) else {}
        alert_type = str(data.get("type") or data.get("alert_type") or "").strip().lower()
        source = str(data.get("source") or "").strip().lower()
        lang = str(data.get("lang") or "").strip().lower()
        target = self.norm_target(data.get("input") or data.get("target") or data.get("url"))
        if target:
            base = f"{source}:{alert_type}:{target}:{lang}"
        else:
            base = f"title_body:{str(title or '').strip().lower()}::{str(body or '').strip().lower()}::{lang}"
        return hashlib.sha256(base.encode("utf-8", errors="ignore")).hexdigest()

    @staticmethod
    def daily_key() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def category_limit(self, category: str, default_limit: int = 2) -> int:
        cat = str(category or "general").strip().lower()
        return int(PUSH_CATEGORY_LIMITS.get(cat, default_limit))

    def daily_can_send(self, category: str = "general", limit: int | None = None) -> bool:
        cat = str(category or "general").strip().lower()
        if cat in {"calendar", "transactional"}:
            return True
        max_count = max(1, int(limit if limit is not None else self.category_limit(cat)))
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT send_count FROM push_daily_counts WHERE day=? AND category=? LIMIT 1",
                (self.daily_key(), cat),
            ).fetchone()
            return int(row["send_count"] if row else 0) < max_count
        finally:
            conn.close()

    def daily_mark_sent(self, category: str = "general") -> None:
        cat = str(category or "general").strip().lower()
        if cat in {"calendar", "transactional"}:
            return
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        conn = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO push_daily_counts(day, category, send_count, updated_at)
                VALUES(?,?,1,?)
                ON CONFLICT(day, category) DO UPDATE SET
                  send_count=send_count+1,
                  updated_at=excluded.updated_at
                """,
                (self.daily_key(), cat, now_iso),
            )
            conn.commit()
        finally:
            conn.close()

    def recently_sent(self, dedupe_key: str, cooldown_sec: int = PUSH_DEFAULT_DEDUPE_SEC) -> bool:
        if not dedupe_key:
            return False
        cutoff = datetime.now(timezone.utc).timestamp() - max(60, int(cooldown_sec or PUSH_DEFAULT_DEDUPE_SEC))
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT last_sent_at FROM sent_push_alerts WHERE dedupe_key=? LIMIT 1",
                (dedupe_key,),
            ).fetchone()
            if not row:
                return False
            dt = datetime.fromisoformat(str(row["last_sent_at"]).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp() >= cutoff
        except Exception:
            return False
        finally:
            conn.close()

    def mark_sent(self, dedupe_key: str, title: str, body: str, data: dict | None = None) -> None:
        if not dedupe_key:
            return
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        conn = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO sent_push_alerts(dedupe_key, title, body, data_json, first_sent_at, last_sent_at, send_count)
                VALUES(?,?,?,?,?,?,1)
                ON CONFLICT(dedupe_key) DO UPDATE SET
                  title=excluded.title,
                  body=excluded.body,
                  data_json=excluded.data_json,
                  last_sent_at=excluded.last_sent_at,
                  send_count=send_count+1
                """,
                (dedupe_key, str(title or "")[:240], str(body or "")[:1000], json.dumps(data or {}, ensure_ascii=False), now_iso, now_iso),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def lang_filter(lang: str) -> list[dict]:
        return [{"field": "tag", "key": "lang", "relation": "=", "value": str(lang or "en")}]

    async def send_onesignal_push(
        self,
        title: str,
        body: str,
        data: dict | None = None,
        filters: list[dict] | None = None,
    ) -> dict:
        if not self.app_id or not self.api_key:
            raise RuntimeError("OneSignal is not configured")

        payload = {
            "app_id": self.app_id,
            "headings": {"en": title},
            "contents": {"en": body},
            "priority": 10,
        }
        if filters:
            payload["filters"] = filters
        else:
            payload["included_segments"] = ["All"]
        if isinstance(data, dict) and data:
            payload["data"] = data

        headers = {
            "Authorization": f"Basic {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=15.0) as cl:
            r = await cl.post("https://onesignal.com/api/v1/notifications", json=payload, headers=headers)
            print("[onesignal] status =", r.status_code)
            print("[onesignal] body =", r.text)
            r.raise_for_status()
            return r.json()

    async def broadcast_localized_push(
        self,
        messages: dict,
        data: dict | None = None,
        category: str = "general",
        bypass_daily_limit: bool = False,
    ) -> dict:
        if not bypass_daily_limit and not self.daily_can_send(category):
            print("[broadcast_localized_push] daily limit skipped", {"category": category})
            return {"ok": True, "provider": "onesignal", "skipped": True, "reason": "daily_push_limit"}

        sent = []
        errors = []
        for lang in PUSH_LANGS:
            msg = messages.get(lang) or messages.get("en") or {}
            title = str(msg.get("title") or "Noytrix").strip()
            body = str(msg.get("body") or "").strip()
            if not body:
                continue
            lang_data = dict(data or {})
            lang_data["lang"] = lang
            dedupe_key = self.dedupe_key(title, body, lang_data)
            if self.recently_sent(dedupe_key):
                sent.append({"lang": lang, "skipped": "duplicate_recent_push"})
                continue
            try:
                resp = await self.send_onesignal_push(title, body, data=lang_data, filters=self.lang_filter(lang))
                self.mark_sent(dedupe_key, title, body, lang_data)
                sent.append({"lang": lang, "response": resp})
            except Exception as e:
                errors.append({"lang": lang, "error": str(e)})
                print("[broadcast_localized_push] onesignal error:", lang, e)

        if sent and not all(x.get("skipped") for x in sent):
            self.daily_mark_sent(category)
        return {"ok": not errors, "provider": "onesignal", "sent": sent, "errors": errors}
