import os
import sqlite3
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "leads.db"

load_dotenv(BASE / ".telegram.env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
MIN_SEND_SCORE = int(os.getenv("MIN_SEND_SCORE", "12"))
MIN_PRESCAN_SCORE = int(os.getenv("MIN_PRESCAN_SCORE", "8"))

PRESCAN = {
    "is this safe",
    "can someone check",
    "can anyone verify",
    "suspicious website",
    "suspicious token",
    "suspicious wallet",
    "wallet security",
    "crypto security",
    "phishing attack",
    "wallet compromise",
    "wallet compromised",
}

if not BOT_TOKEN or not CHAT_ID:
    raise SystemExit("BOT_TOKEN or CHAT_ID missing")

conn = sqlite3.connect(DB)
rows = conn.execute("""
SELECT id, source, subreddit, priority, score, keyword, title, url, author, found_at, score_reasons
FROM leads
WHERE alerted=0
  AND (
    score >= ?
    OR (score >= ? AND lower(keyword) IN ({placeholders}))
  )
ORDER BY score DESC, id DESC
LIMIT 20
""".format(placeholders=",".join("?" for _ in PRESCAN)), (MIN_SEND_SCORE, MIN_PRESCAN_SCORE, *PRESCAN)).fetchall()

if not rows:
    print(f"No pending leads matching send policy. min={MIN_SEND_SCORE}, prescan={MIN_PRESCAN_SCORE}.")
    raise SystemExit

sent = 0

for lead_id, source, subreddit, priority, score, keyword, title, url, author, found_at, reasons in rows:
    k = (keyword or "").lower()

    if k in PRESCAN:
        icon = "🔍"
        bucket = "PRE-SCAN USER"
    elif k in {"wallet drained", "wallet hacked", "stolen crypto", "funds stolen", "assets stolen", "scammed", "got scammed"}:
        icon = "💰"
        bucket = "SCAM VICTIM"
    else:
        icon = "🛡"
        bucket = "SECURITY LEAD"

    text = f"""{icon} NOYTRIX {bucket} #{lead_id}

Score: {score}
Source: {source} / r/{subreddit}

Keyword:
{keyword}

Title:
{title}

Author:
{author}

Open:
{url}

Matched:
{reasons}
"""

    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

    if r.ok and r.json().get("ok"):
        conn.execute("UPDATE leads SET alerted=1 WHERE id=?", (lead_id,))
        conn.commit()
        sent += 1
        print(f"sent lead #{lead_id}")
    else:
        print(f"failed lead #{lead_id}: {r.text}")

print(f"sent total: {sent}")
