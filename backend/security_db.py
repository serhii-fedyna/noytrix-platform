import sqlite3
import math
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SCAN_DB_PATH = DATA_DIR / "scan_votes.sqlite3"
QUOTA_DB_PATH = DATA_DIR / "quota.sqlite3"


def init_scan_db():
    conn = sqlite3.connect(SCAN_DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                obj TEXT NOT NULL,
                kind TEXT,
                is_scam INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def init_quota_db():
    conn = sqlite3.connect(QUOTA_DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS quota (
                user_id TEXT NOT NULL,
                day TEXT NOT NULL,
                feature TEXT NOT NULL,
                used INTEGER NOT NULL,
                PRIMARY KEY (user_id, day, feature)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


init_scan_db()
init_quota_db()


def today_key_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def client_ip(request) -> str:
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if xff:
        return xff
    if request.client and request.client.host:
        return request.client.host
    return "0.0.0.0"


def device_id_from_request(request) -> Optional[str]:
    for k in ("x-device-id", "x-deviceid", "device-id", "x-install-id"):
        v = request.headers.get(k)
        if v and v.strip():
            return v.strip()
    return None


def device_fingerprint(request) -> str:
    did = device_id_from_request(request)
    if did:
        return f"dev:{did}"
    ip = client_ip(request)
    ua = (request.headers.get("user-agent") or "").strip()
    raw = f"{ip}|{ua}"
    h = hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:24]
    return f"fp:{h}"


def quota_used(user_id: str, day: str, feature: str) -> int:
    conn = sqlite3.connect(QUOTA_DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT used FROM quota WHERE user_id=? AND day=? AND feature=?", (user_id, day, feature))
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def quota_inc(user_id: str, day: str, feature: str, inc: int = 1) -> int:
    conn = sqlite3.connect(QUOTA_DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT used FROM quota WHERE user_id=? AND day=? AND feature=?", (user_id, day, feature))
        row = cur.fetchone()
        if row:
            used = int(row[0]) + inc
            cur.execute("UPDATE quota SET used=? WHERE user_id=? AND day=? AND feature=?", (used, user_id, day, feature))
        else:
            used = inc
            cur.execute("INSERT INTO quota (user_id, day, feature, used) VALUES (?,?,?,?)", (user_id, day, feature, used))
        conn.commit()
        return used
    finally:
        conn.close()


def enforce_free_quota(request, feature: str, daily_free_limit: int) -> Dict[str, Any]:
    uid = device_fingerprint(request)
    day = today_key_utc()

    used_before = quota_used(uid, day, feature)
    if used_before >= daily_free_limit:
        # caller will raise HTTPException with localized string
        return {"blocked": True, "uid": uid, "day": day, "used": used_before, "left": 0, "freeLimit": daily_free_limit}

    used_after = quota_inc(uid, day, feature, 1)
    left = max(0, daily_free_limit - used_after)
    return {"blocked": False, "uid": uid, "day": day, "used": used_after, "left": left, "freeLimit": daily_free_limit}


def normalize_obj(raw: str) -> str:
    return (raw or "").strip()


def immunity_compute(obj: str, kind: Optional[str] = None) -> Dict[str, Any]:
    obj = (obj or "").strip()
    if not obj:
        return {"ok": False, "error": "empty_input"}

    conn = sqlite3.connect(SCAN_DB_PATH)
    try:
        cur = conn.cursor()
        if kind:
            cur.execute("SELECT COUNT(*), SUM(is_scam) FROM scan_votes WHERE obj=? AND kind=?", (obj, kind))
        else:
            cur.execute("SELECT COUNT(*), SUM(is_scam) FROM scan_votes WHERE obj=?", (obj,))
        total, scam_sum = cur.fetchone()
    finally:
        conn.close()

    total = int(total or 0)
    scam_votes = int(scam_sum or 0)
    safe_votes = total - scam_votes

    if total <= 0:
        return {
            "ok": True,
            "obj": obj,
            "kind": kind,
            "total_votes": 0,
            "safe_votes": 0,
            "scam_votes": 0,
            "immunity_score": 0,
            "confidence": 0,
            "community_verdict": "unknown",
        }

    immunity_score = int(round((safe_votes / total) * 100))
    confidence = int(min(100, round(math.log10(total + 1) * 60)))

    scam_ratio = scam_votes / total
    if scam_ratio >= 0.6:
        verdict = "scam"
    elif scam_ratio <= 0.4:
        verdict = "safe"
    else:
        verdict = "mixed"

    return {
        "ok": True,
        "obj": obj,
        "kind": kind,
        "total_votes": total,
        "safe_votes": safe_votes,
        "scam_votes": scam_votes,
        "immunity_score": immunity_score,
        "confidence": confidence,
        "community_verdict": verdict,
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }