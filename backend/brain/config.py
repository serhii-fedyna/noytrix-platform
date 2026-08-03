from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
BRAIN_DB_PATH = DATA_DIR / "noytrix_brain.sqlite3"
SOURCES_PATH = Path(__file__).with_name("sources.json")


def enabled() -> bool:
    return str(os.getenv("NOYTRIX_BRAIN_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def max_sources_per_run() -> int:
    try:
        return max(1, min(25, int(os.getenv("NOYTRIX_BRAIN_MAX_SOURCES_PER_RUN", "8"))))
    except ValueError:
        return 8


def interval_seconds() -> int:
    try:
        return max(3600, min(7 * 24 * 3600, int(os.getenv("NOYTRIX_BRAIN_INTERVAL_SECONDS", "43200"))))
    except ValueError:
        return 43200


def admin_token() -> str:
    return str(os.getenv("NOYTRIX_BRAIN_ADMIN_TOKEN", "")).strip()


def outreach_enabled() -> bool:
    return str(os.getenv("NOYTRIX_BRAIN_OUTREACH_ENABLED", "0")).strip().lower() in {"1", "true", "yes", "on"}
