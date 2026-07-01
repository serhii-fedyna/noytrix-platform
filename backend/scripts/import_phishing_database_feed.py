from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from scamshield.intelligence.postgres_intelligence import connect, normalize_entity

RE_EVM = re.compile(r"^0x[a-fA-F0-9]{40}$")

REPO_URL = "https://github.com/Phishing-Database/Phishing.Database.git"
REPO_DIR = Path("data/public_feeds/phishing_database")


def guess_type(value: str) -> str:
    v = (value or "").strip().lower().strip('"').strip("'").strip()
    if not v:
        return "unknown"
    if RE_EVM.match(v):
        return "evm_address"
    if v.startswith("http://") or v.startswith("https://"):
        return "url"
    if "." in v and " " not in v and len(v) <= 253:
        return "domain"
    return "unknown"


def clean_value(value: str) -> str:
    v = (value or "").strip()
    v = v.split(",")[0].strip()
    v = v.split(";")[0].strip()
    v = v.strip('"').strip("'").strip()
    if v.startswith("0.0.0.0 "):
        v = v.replace("0.0.0.0 ", "", 1).strip()
    if v.startswith("127.0.0.1 "):
        v = v.replace("127.0.0.1 ", "", 1).strip()
    return v


def ensure_repo():
    if REPO_DIR.exists():
        subprocess.run(["git", "-C", str(REPO_DIR), "pull", "--ff-only"], check=False)
    else:
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, str(REPO_DIR)], check=True)


def get_feed_id(cur):
    cur.execute("SELECT id FROM source_feeds WHERE name=%s", ("phishing_database",))
    row = cur.fetchone()
    return row["id"] if row else None


def import_value(cur, feed_id, raw_value: str):
    raw_value = clean_value(raw_value)
    typ = guess_type(raw_value)
    if typ == "unknown":
        return False

    normalized = normalize_entity(raw_value)
    if not normalized:
        return False

    cur.execute(
        """
        INSERT INTO raw_indicators (
            feed_id, source_name, raw_value, normalized_value,
            indicator_type, status, confidence, risk_score, raw_record, metadata
        )
        VALUES (%s, %s, %s, %s, %s, 'quarantine', 65, 65, %s::jsonb, %s::jsonb)
        ON CONFLICT (source_name, normalized_value, indicator_type)
        DO UPDATE SET
            last_seen_at = now(),
            seen_count = raw_indicators.seen_count + 1,
            confidence = GREATEST(raw_indicators.confidence, EXCLUDED.confidence),
            risk_score = GREATEST(raw_indicators.risk_score, EXCLUDED.risk_score),
            metadata = raw_indicators.metadata || EXCLUDED.metadata
        """,
        (
            feed_id,
            "phishing_database",
            raw_value,
            normalized,
            typ,
            json.dumps({"value": raw_value}, ensure_ascii=False),
            json.dumps({"importer": "phishing_database", "mode": "quarantine"}, ensure_ascii=False),
        ),
    )
    return True


def main():
    ensure_repo()

    imported = 0
    scanned_files = 0
    batch = 0

    allowed_suffixes = {".txt", ".csv", ".list", ".conf", ".domains", ".urls"}

    with connect() as conn:
        with conn.cursor() as cur:
            feed_id = get_feed_id(cur)

            for path in REPO_DIR.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in allowed_suffixes:
                    continue

                scanned_files += 1

                try:
                    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                        line = line.strip()
                        if not line or line.startswith("#") or line.startswith("//"):
                            continue

                        if import_value(cur, feed_id, line):
                            imported += 1
                            batch += 1

                        if batch >= 1000:
                            conn.commit()
                            print(json.dumps({
                                "progress_imported": imported,
                                "scanned_files": scanned_files
                            }, ensure_ascii=False), flush=True)
                            batch = 0

                except Exception as e:
                    print("SKIP_FILE", str(path), e, flush=True)

            cur.execute(
                "UPDATE source_feeds SET last_import_at=now() WHERE name=%s",
                ("phishing_database",),
            )

        conn.commit()

    print(json.dumps({
        "feed": "phishing_database",
        "scanned_files": scanned_files,
        "imported_or_updated": imported,
        "mode": "quarantine"
    }, indent=2))


if __name__ == "__main__":
    main()
