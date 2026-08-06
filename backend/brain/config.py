from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
BRAIN_DB_PATH = DATA_DIR / "noytrix_brain.sqlite3"
SOURCES_PATH = Path(__file__).with_name("sources.json")
INVESTOR_SOURCES_PATH = Path(__file__).with_name("investor_sources.json")
JOB_SOURCES_PATH = Path(__file__).with_name("job_sources.json")


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
    return str(os.getenv("NOYTRIX_BRAIN_OUTREACH_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def auto_send_threshold() -> int:
    try:
        return max(71, min(100, int(os.getenv("NOYTRIX_BRAIN_AUTO_SEND_THRESHOLD", "71"))))
    except ValueError:
        return 71


def github_max_results() -> int:
    try:
        return max(1, min(30, int(os.getenv("NOYTRIX_BRAIN_GITHUB_MAX_RESULTS", "10"))))
    except ValueError:
        return 10


def daily_report_hour() -> int:
    """Local hour for the concise daily outreach report."""
    try:
        return max(0, min(23, int(os.getenv("NOYTRIX_BRAIN_DAILY_REPORT_HOUR", "20"))))
    except ValueError:
        return 20


def report_timezone() -> str:
    return str(os.getenv("NOYTRIX_BRAIN_REPORT_TIMEZONE", "Europe/Kyiv")).strip() or "Europe/Kyiv"


def inbox_poll_seconds() -> int:
    try:
        return max(60, min(3600, int(os.getenv("NOYTRIX_BRAIN_INBOX_POLL_SECONDS", "300"))))
    except ValueError:
        return 300


def jobs_enabled() -> bool:
    return str(os.getenv("NOYTRIX_JOBS_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def jobs_max_sources_per_run() -> int:
    try:
        return max(1, min(25, int(os.getenv("NOYTRIX_JOBS_MAX_SOURCES_PER_RUN", "8"))))
    except ValueError:
        return 8


def jobs_auto_send_threshold() -> int:
    """Keep autonomous job applications stricter than partnership outreach."""
    try:
        return max(80, min(100, int(os.getenv("NOYTRIX_JOBS_AUTO_SEND_THRESHOLD", "80"))))
    except ValueError:
        return 80


def jobs_daily_auto_send_limit() -> int:
    try:
        return max(1, min(20, int(os.getenv("NOYTRIX_JOBS_DAILY_AUTO_SEND_LIMIT", "5"))))
    except ValueError:
        return 5


def candidate_resume_path() -> Path:
    configured = str(os.getenv("NOYTRIX_CANDIDATE_RESUME_PATH", "")).strip()
    return Path(configured) if configured else DATA_DIR / "resumes" / "Serhii_Fedyna_Resume.pdf"
