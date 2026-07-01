import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "data" / "leads.db"

conn = sqlite3.connect(DB)
rows = conn.execute("""
SELECT id, source, subreddit, priority, score, keyword, title, url, author, found_at, score_reasons
FROM leads
WHERE alerted=0
ORDER BY score DESC, id DESC
LIMIT 50
""").fetchall()

if not rows:
    print("No pending leads.")
    raise SystemExit

for lead_id, source, subreddit, priority, score, keyword, title, url, author, found_at, reasons in rows:
    icon = "🚨" if score >= 9 else "⚠️" if score >= 5 else "ℹ️"
    print(f"""
{icon} NOYTRIX LEAD #{lead_id}

Priority: {priority.upper()}
Score: {score}
Source: {source} / r/{subreddit}
Keyword: {keyword}
Author: {author}

Title:
{title}

Link:
{url}

Reasons:
{reasons}

Found:
{found_at}
""".strip())
    print("-" * 60)
