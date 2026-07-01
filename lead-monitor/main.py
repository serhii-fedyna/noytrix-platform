import os
import re
import time
import sqlite3
import logging
import subprocess
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "leads.db"

load_dotenv(BASE_DIR / ".env")

POLL_SECONDS = int(os.getenv("POLL_SECONDS", "120"))
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 NoytrixLeadMonitor/0.2")
SEND_ALERTS = os.getenv("SEND_ALERTS", "false").lower() == "true"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "monitor.log"),
        logging.StreamHandler(),
    ],
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_lines(name: str) -> list[str]:
    p = BASE_DIR / name
    if not p.exists():
        return []
    return [
        line.strip()
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            external_id TEXT NOT NULL,
            subreddit TEXT,
            keyword TEXT,
            title TEXT,
            text TEXT,
            url TEXT NOT NULL,
            author TEXT,
            created_utc INTEGER,
            found_at TEXT NOT NULL,
            alerted INTEGER NOT NULL DEFAULT 0,
            priority TEXT NOT NULL DEFAULT 'medium',
            score INTEGER NOT NULL DEFAULT 0,
            score_reasons TEXT NOT NULL DEFAULT '',
            UNIQUE(source, external_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_found_at ON leads(found_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_alerted ON leads(alerted)")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(leads)").fetchall()]
    if "priority" not in cols:
        conn.execute("ALTER TABLE leads ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'")
    if "score" not in cols:
        conn.execute("ALTER TABLE leads ADD COLUMN score INTEGER NOT NULL DEFAULT 0")
    if "score_reasons" not in cols:
        conn.execute("ALTER TABLE leads ADD COLUMN score_reasons TEXT NOT NULL DEFAULT ''")
    conn.commit()
    return conn


def get_state(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def keyword_match(text: str, keywords: list[str]) -> str | None:
    hay = re.sub(r"\s+", " ", text.lower())
    for kw in keywords:
        if kw.lower() in hay:
            return kw
    return None


def keyword_priority(keyword: str | None) -> str:
    if not keyword:
        return "none"

    p = BASE_DIR / "keyword_priority.json"
    if not p.exists():
        return "medium"

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return "medium"

    k = keyword.lower().strip()
    for level in ("high", "medium", "low"):
        for item in data.get(level, []):
            if item.lower().strip() == k:
                return level

    return "medium"


def lead_score(text: str) -> tuple[int, list[str]]:
    p = BASE_DIR / "scoring_rules.json"
    if not p.exists():
        return 0, []

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return 0, []

    hay = re.sub(r"\s+", " ", text.lower())
    score = 0
    reasons = []

    for phrase, points in data.get("rules", {}).items():
        if phrase.lower() in hay:
            score += int(points)
            reasons.append(f"{phrase}:{points}")

    for phrase, points in data.get("boosts", {}).items():
        if phrase.lower() in hay:
            score += int(points)
            reasons.append(f"boost:{phrase}:{points}")

    for phrase, points in data.get("negative", {}).items():
        if phrase.lower() in hay:
            score += int(points)
            reasons.append(f"negative:{phrase}:{points}")

    return score, reasons


def min_score() -> int:
    p = BASE_DIR / "scoring_rules.json"
    if not p.exists():
        return 5
    try:
        return int(json.loads(p.read_text(encoding="utf-8")).get("min_score", 5))
    except Exception:
        return 5


def clean_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&lt;", "<", s)
    s = re.sub(r"&gt;", ">", s)
    s = re.sub(r"&quot;", '"', s)
    s = re.sub(r"&#39;", "'", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_dt(value: str) -> int:
    try:
        return int(parsedate_to_datetime(value).timestamp())
    except Exception:
        return 0


def reddit_new(subreddit: str) -> list[dict]:
    url = f"https://www.reddit.com/r/{subreddit}/new/.rss?limit=25"
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()

    root = ET.fromstring(r.text)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
    }

    posts = []
    for entry in root.findall("atom:entry", ns):
        title = entry.findtext("atom:title", default="", namespaces=ns)
        external_id = entry.findtext("atom:id", default="", namespaces=ns)
        updated = entry.findtext("atom:updated", default="", namespaces=ns)
        author_node = entry.find("atom:author/atom:name", ns)
        author = author_node.text if author_node is not None else ""
        content = entry.findtext("atom:content", default="", namespaces=ns)

        link = ""
        for lnk in entry.findall("atom:link", ns):
            href = lnk.attrib.get("href", "")
            if href:
                link = href
                break

        posts.append({
            "external_id": external_id or link,
            "created_utc": parse_dt(updated),
            "title": clean_html(title),
            "selftext": clean_html(content),
            "author": clean_html(author),
            "url": link,
        })

    return posts



def reddit_comments(subreddit: str) -> list[dict]:
    url = f"https://www.reddit.com/r/{subreddit}/comments/.rss?limit=25"
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()

    root = ET.fromstring(r.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    comments = []
    for entry in root.findall("atom:entry", ns):
        title = clean_html(entry.findtext("atom:title", default="", namespaces=ns))
        external_id = entry.findtext("atom:id", default="", namespaces=ns)
        updated = entry.findtext("atom:updated", default="", namespaces=ns)
        author_node = entry.find("atom:author/atom:name", ns)
        author = author_node.text if author_node is not None else ""
        content = clean_html(entry.findtext("atom:content", default="", namespaces=ns))

        link = ""
        for lnk in entry.findall("atom:link", ns):
            href = lnk.attrib.get("href", "")
            if href:
                link = href
                break

        comments.append({
            "external_id": "comment:" + (external_id or link),
            "created_utc": parse_dt(updated),
            "title": title[:500],
            "selftext": content[:2000],
            "author": clean_html(author),
            "url": link,
        })

    return comments


def save_lead(conn: sqlite3.Connection, lead: dict) -> bool:
    try:
        conn.execute(
            """
            INSERT INTO leads(source, external_id, subreddit, keyword, title, text, url, author, created_utc, found_at, alerted, priority, score, score_reasons)
            VALUES(:source, :external_id, :subreddit, :keyword, :title, :text, :url, :author, :created_utc, :found_at, :alerted, :priority, :score, :score_reasons)
            """,
            lead,
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def next_subreddit(conn: sqlite3.Connection, subreddits: list[str], state_key: str = "reddit_sub_index") -> str | None:
    if not subreddits:
        return None

    raw = get_state(conn, state_key)
    try:
        idx = int(raw or "0")
    except ValueError:
        idx = 0

    sub = subreddits[idx % len(subreddits)]
    set_state(conn, state_key, str((idx + 1) % len(subreddits)))
    return sub


def scan_reddit(conn: sqlite3.Connection, bootstrap: bool) -> int:
    keywords = read_lines("keywords.txt")
    subreddits = read_lines("subreddits.txt")
    added = 0

    sub = next_subreddit(conn, subreddits)
    if not sub:
        logging.warning("No subreddits configured")
        return 0

    try:
        posts = reddit_new(sub)
        logging.info("Fetched r/%s posts=%s", sub, len(posts))
    except Exception as e:
        logging.warning("Failed reddit r/%s: %s", sub, e)
        return 0

    for p in posts:
        external_id = p.get("external_id")
        created_utc = int(p.get("created_utc") or 0)
        title = p.get("title") or ""
        body = p.get("selftext") or ""
        author = p.get("author") or ""
        full_url = p.get("url") or ""

        if not external_id or not full_url:
            continue

        matched = keyword_match(f"{title}\n{body}", keywords)

        if bootstrap:
            conn.execute(
                """
                INSERT OR IGNORE INTO leads(source, external_id, subreddit, keyword, title, text, url, author, created_utc, found_at, alerted)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                ("reddit", external_id, sub, matched or "", title[:500], body[:2000], full_url, author, created_utc, utc_now_iso(), 1),
            )
            continue

        score, reasons = lead_score(f"{title}\n{body}")
        if not matched or score < min_score():
            continue

        lead = {
            "source": "reddit",
            "external_id": external_id,
            "subreddit": sub,
            "keyword": matched,
            "title": title[:500],
            "text": body[:2000],
            "url": full_url,
            "author": author,
            "created_utc": created_utc,
            "found_at": utc_now_iso(),
            "alerted": 0,
            "priority": keyword_priority(matched),
            "score": score,
            "score_reasons": ",".join(reasons[:12]),
        }

        if save_lead(conn, lead):
            added += 1
            logging.info("NEW LEAD reddit r/%s keyword=%s url=%s", sub, matched, full_url)

    conn.commit()
    return added



def scan_reddit_comments(conn: sqlite3.Connection, bootstrap: bool) -> int:
    keywords = read_lines("keywords.txt")
    subreddits = read_lines("subreddits.txt")
    added = 0

    sub = next_subreddit(conn, subreddits, "reddit_comment_sub_index")
    if not sub:
        logging.warning("No subreddits configured for comments")
        return 0

    try:
        comments = reddit_comments(sub)
        logging.info("Fetched r/%s comments=%s", sub, len(comments))
    except Exception as e:
        logging.warning("Failed reddit comments r/%s: %s", sub, e)
        return 0

    for c in comments:
        external_id = c.get("external_id")
        created_utc = int(c.get("created_utc") or 0)
        title = c.get("title") or ""
        body = c.get("selftext") or ""
        author = c.get("author") or ""
        full_url = c.get("url") or ""

        if not external_id or not full_url:
            continue

        matched = keyword_match(f"{title}\n{body}", keywords)
        score, reasons = lead_score(f"{title}\n{body}")

        if bootstrap:
            conn.execute(
                """
                INSERT OR IGNORE INTO leads(source, external_id, subreddit, keyword, title, text, url, author, created_utc, found_at, alerted, priority, score, score_reasons)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                ("reddit_comment", external_id, sub, matched or "", title[:500], body[:2000], full_url, author, created_utc, utc_now_iso(), 1, keyword_priority(matched), score, ",".join(reasons[:12])),
            )
            continue

        if not matched or score < min_score():
            continue

        lead = {
            "source": "reddit_comment",
            "external_id": external_id,
            "subreddit": sub,
            "keyword": matched,
            "title": title[:500],
            "text": body[:2000],
            "url": full_url,
            "author": author,
            "created_utc": created_utc,
            "found_at": utc_now_iso(),
            "alerted": 0,
            "priority": keyword_priority(matched),
            "score": score,
            "score_reasons": ",".join(reasons[:12]),
        }

        if save_lead(conn, lead):
            added += 1
            logging.info("NEW COMMENT LEAD reddit r/%s keyword=%s score=%s url=%s", sub, matched, score, full_url)

    conn.commit()
    return added


def print_unalerted(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, source, subreddit, keyword, title, url, author, found_at, priority, score, score_reasons
        FROM leads
        WHERE alerted=0 AND score >= 8
        ORDER BY score DESC, id DESC
        LIMIT 20
        """
    ).fetchall()

    if not rows:
        print("No new leads.")
        return

    for row in rows:
        lead_id, source, subreddit, keyword, title, url, author, found_at, priority, score, score_reasons = row
        print()
        print(f"🎯 Lead #{lead_id}")
        print(f"Source: {source} / r/{subreddit}")
        print(f"Priority: {priority.upper()}")
        print(f"Score: {score}")
        print(f"Keyword: {keyword}")
        print(f"Author: {author}")
        print(f"Title: {title}")
        print(f"Link: {url}")
        print(f"Found: {found_at}")


def main() -> None:
    conn = db()
    bootstrapped = get_state(conn, "bootstrapped") == "1"

    if not bootstrapped:
        logging.info("First run bootstrap: saving current posts as old, no alerts.")
        scan_reddit(conn, bootstrap=True)
        scan_reddit_comments(conn, bootstrap=True)
        set_state(conn, "bootstrapped", "1")
        logging.info("Bootstrap finished. Next runs will collect only new matching posts.")
        print("BOOTSTRAP DONE: current posts marked as old. No old alerts will be sent.")
        return

    added_posts = scan_reddit(conn, bootstrap=False)

    comment_tick_raw = get_state(conn, "comment_tick")
    try:
        comment_tick = int(comment_tick_raw or "0")
    except ValueError:
        comment_tick = 0

    added_comments = 0
    if comment_tick % 3 == 0:
        time.sleep(8)
        added_comments = scan_reddit_comments(conn, bootstrap=False)
    else:
        logging.info("Skipping comments this run. comment_tick=%s", comment_tick)

    set_state(conn, "comment_tick", str(comment_tick + 1))
    added = added_posts + added_comments
    logging.info("Scan finished. New post leads: %s. New comment leads: %s. Total: %s", added_posts, added_comments, added)

    try:
        result = subprocess.run(
            [str(BASE_DIR / "venv" / "bin" / "python"), str(BASE_DIR / "send_pending.py")],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.stderr.strip():
            logging.warning("send_pending stderr: %s", result.stderr.strip())
    except Exception as e:
        logging.warning("send_pending failed: %s", e)

    print_unalerted(conn)


if __name__ == "__main__":
    main()
