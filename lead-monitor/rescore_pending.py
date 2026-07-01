import json
import re
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "leads.db"
RULES = json.loads((BASE / "scoring_rules.json").read_text())

def score_text(text: str):
    hay = re.sub(r"\s+", " ", (text or "").lower())
    score = 0
    reasons = []

    for phrase, points in RULES.get("rules", {}).items():
        if phrase.lower() in hay:
            score += int(points)
            reasons.append(f"{phrase}:{points}")

    for phrase, points in RULES.get("boosts", {}).items():
        if phrase.lower() in hay:
            score += int(points)
            reasons.append(f"boost:{phrase}:{points}")

    for phrase, points in RULES.get("negative", {}).items():
        if phrase.lower() in hay:
            score += int(points)
            reasons.append(f"negative:{phrase}:{points}")

    return score, ",".join(reasons[:12])

conn = sqlite3.connect(DB)
rows = conn.execute("SELECT id, title, text FROM leads WHERE alerted=0").fetchall()

for lead_id, title, body in rows:
    score, reasons = score_text(f"{title}\n{body}")
    conn.execute(
        "UPDATE leads SET score=?, score_reasons=? WHERE id=?",
        (score, reasons, lead_id),
    )

conn.commit()
print(f"rescored {len(rows)} pending leads")
