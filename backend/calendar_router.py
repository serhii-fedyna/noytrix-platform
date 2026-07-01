# backend/calendar_router.py
from __future__ import annotations

from fastapi import APIRouter, Query
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path as FsPath
import asyncio
import hashlib
import os
import sqlite3
import re

import httpx
from providers import eu_macro
from providers import us_macro

# ✅ ВАЖНО: router prefix НЕ должен содержать /api, потому что /api добавляется в main.py include_router(..., prefix="/api")
# Тогда эндпоинты будут: /api/calendar/events
router = APIRouter(prefix="/calendar", tags=["calendar"])

BASE_DIR = FsPath(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "events.sqlite3"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ====== SOURCES CONFIG ======
COINMARKETCAL_API_KEY = (os.getenv("COINMARKETCAL_API_KEY") or "").strip()
COINMARKETCAL_RANGE_DAYS = int((os.getenv("COINMARKETCAL_RANGE_DAYS") or "30").strip() or "30")
COINMARKETCAL_MAX_PAGES = int((os.getenv("COINMARKETCAL_MAX_PAGES") or "5").strip() or "5")

DERIBIT_API = "https://www.deribit.com/api/v2"

# Macro (официальные расписания)
BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
FOMC_CAL_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FED_EVENTS_MONTH_URL = "https://www.federalreserve.gov/newsevents/{year}-{month}.htm"
MACRO_TZ = ZoneInfo("America/New_York")

# Token unlocks / vesting (Mobula)
MOBULA_API_KEY = (os.getenv("MOBULA_API_KEY") or "").strip()
MOBULA_BASE = "https://api.mobula.io" if MOBULA_API_KEY else "https://demo-api.mobula.io"
MOBULA_TOP_N = int((os.getenv("MOBULA_TOP_N") or "300").strip() or "300")
MOBULA_METADATA_BATCH = int((os.getenv("MOBULA_METADATA_BATCH") or "50").strip() or "50")
UNLOCK_LOOKAHEAD_DAYS = int((os.getenv("UNLOCK_LOOKAHEAD_DAYS") or "180").strip() or "180")

VALID_TYPES = {"Network", "Listing", "Tokenomics", "Macro", "Airdrop", "Derivatives"}
IMPACT_ORDER = {"low": 0, "mid": 1, "high": 2}


# ====== DB ======
def db():
    return sqlite3.connect(DB_PATH)


def _ensure_column(cur: sqlite3.Cursor, table: str, column: str, ddl: str) -> None:
    cur.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db():
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS events (
          hash TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          asset TEXT,
          type TEXT NOT NULL,
          impact TEXT NOT NULL,
          start_ts TEXT NOT NULL,      -- ISO UTC (Z)
          source_url TEXT,
          summary TEXT,
          provider TEXT,
          updated_at TEXT NOT NULL
        );
        """
        )

        # Автомиграции для старой базы
        _ensure_column(cur, "events", "all_day", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(cur, "events", "has_time", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(cur, "events", "event_date", "TEXT")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_ts);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_impact ON events(impact);")

        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS meta (
          k TEXT PRIMARY KEY,
          v TEXT
        );
        """
        )
        conn.commit()
    finally:
        conn.close()


init_db()


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _to_iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _parse_iso_any(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    try:
        s = v.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _parse_ymd_date(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    try:
        s = str(v).strip()
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _ymd(v: datetime) -> str:
    return v.astimezone(timezone.utc).strftime("%Y-%m-%d")


def get_meta(k: str) -> Optional[str]:
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT v FROM meta WHERE k=?", (k,))
        r = cur.fetchone()
        return r[0] if r else None
    finally:
        conn.close()


def set_meta(k: str, v: str) -> None:
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
        INSERT INTO meta(k,v) VALUES(?,?)
        ON CONFLICT(k) DO UPDATE SET v=excluded.v
        """,
            (k, v),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_event(row: Dict[str, Any]) -> None:
    title = (row.get("title") or "").strip()
    if not title:
        return

    typ = (row.get("type") or "Tokenomics").strip()
    if typ not in VALID_TYPES:
        typ = "Tokenomics"

    impact = (row.get("impact") or "mid").strip().lower()
    if impact not in IMPACT_ORDER:
        impact = "mid"

    all_day = 1 if bool(row.get("all_day")) else 0
    has_time = 0 if all_day else 1

    event_date = None

    start_dt = row.get("start_dt")
    if isinstance(start_dt, datetime):
        start_ts = _to_iso_utc(start_dt)
        event_date = row.get("event_date") or _ymd(start_dt)
    else:
        start_ts = (row.get("start_ts") or "").strip()
        dt = _parse_iso_any(start_ts)
        if not dt:
            return
        start_ts = _to_iso_utc(dt)
        event_date = row.get("event_date") or _ymd(dt)

    asset = row.get("asset")
    asset = (str(asset).strip()[:64] if asset else None)

    source_url = (row.get("source_url") or None)
    summary = (row.get("summary") or None)
    provider = (row.get("provider") or None)

    # дедуп: title+asset+type+event_date+all_day/start
    if all_day:
        h = _sha1(f"{title}|{asset or ''}|{typ}|{event_date}|all_day")
    else:
        h = _sha1(f"{title}|{asset or ''}|{typ}|{start_ts}")

    conn = db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
        INSERT INTO events(
          hash,title,asset,type,impact,start_ts,source_url,summary,provider,updated_at,all_day,has_time,event_date
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(hash) DO UPDATE SET
          title=excluded.title,
          asset=excluded.asset,
          type=excluded.type,
          impact=excluded.impact,
          start_ts=excluded.start_ts,
          source_url=COALESCE(excluded.source_url, events.source_url),
          summary=COALESCE(excluded.summary, events.summary),
          provider=COALESCE(excluded.provider, events.provider),
          updated_at=excluded.updated_at,
          all_day=excluded.all_day,
          has_time=excluded.has_time,
          event_date=COALESCE(excluded.event_date, events.event_date)
        """,
            (
                h,
                title,
                asset,
                typ,
                impact,
                start_ts,
                source_url,
                summary,
                provider,
                _now_iso(),
                all_day,
                has_time,
                event_date,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def cleanup_noisy_events() -> None:
    """
    Удаляем старый шум из базы:
    - старые RSS/news записи, где дата события = дата публикации статьи
    - прошлые устаревшие события далеко в прошлом
    """
    conn = db()
    try:
        cur = conn.cursor()

        # Удаляем старые мусорные провайдеры полностью
        cur.execute("DELETE FROM events WHERE provider IN ('news_rss', 'exchange_rss', 'network_rss')")

        # Дополнительная чистка очень старых событий
        cutoff_old = _to_iso_utc(datetime.now(timezone.utc) - timedelta(days=30))
        cur.execute("DELETE FROM events WHERE start_ts < ?", (cutoff_old,))

        conn.commit()
    finally:
        conn.close()


# ====== классификация ======
_ASSET_PAREN = re.compile(r"\(([A-Z0-9]{2,10})\)")
_ASSET_TICKER = re.compile(r"\b([A-Z]{2,10})\b")


def _guess_asset(title: str) -> Optional[str]:
    title = title or ""
    m = _ASSET_PAREN.search(title)
    if m:
        return m.group(1)

    up = title.upper()
    for key in ["WILL LIST ", "LISTS ", "LISTING ", "DELIST ", "DELISTING "]:
        if key in up:
            tail = up.split(key, 1)[1]
            m2 = _ASSET_TICKER.search(tail)
            if m2:
                return m2.group(1)

    return None


def _guess_type(title: str, url: Optional[str] = None, provider: Optional[str] = None) -> str:
    t = (title or "").lower()

    if any(k in t for k in ["cpi", "inflation", "fomc", "fed rate", "rate decision", "nonfarm", "nfp", "ppi", "gdp"]):
        return "Macro"

    if any(k in t for k in ["futures", "perpetual", "perp", "options", "derivatives", "funding", "expiry", "expiration"]):
        return "Derivatives"

    if any(k in t for k in ["list", "listing", "delist", "delisting", "adds trading pair", "trading pair", "new asset", "spot listing"]):
        return "Listing"

    if any(k in t for k in ["airdrop", "rewards", "campaign", "learn & earn", "bonus", "giveaway", "snapshot"]):
        return "Airdrop"

    if any(k in t for k in ["upgrade", "hardfork", "hard fork", "mainnet", "testnet", "network", "maintenance", "deposit", "withdrawal", "suspended", "resume"]):
        return "Network"

    if any(k in t for k in ["unlock", "vesting", "burn", "emission", "supply", "tge", "tokenomics"]):
        return "Tokenomics"

    return "Tokenomics"


def _impact_from_text(title: str, typ: str) -> str:
    low = (title or "").lower()

    if typ in {"Macro", "Listing"}:
        return "high"
    if any(k in low for k in ["delist", "delisting", "hack", "exploit", "critical", "emergency", "suspend", "halt"]):
        return "high"
    if any(k in low for k in ["mainnet", "hardfork", "hard fork", "upgrade"]):
        return "high"
    if "airdrop" in low:
        return "high"

    if any(k in low for k in ["integration", "partnership", "collaboration", "roadmap", "testnet"]):
        return "mid"

    return "mid"


# ====== MACRO PARSERS ======
def _parse_ics_dt(line: str) -> Optional[datetime]:
    s = (line or "").strip()
    if ":" in s:
        s = s.split(":", 1)[1].strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        if "T" in s:
            fmt = "%Y%m%dT%H%M%S" if len(s) == 15 else "%Y%m%dT%H%M"
            dt = datetime.strptime(s, fmt).replace(tzinfo=MACRO_TZ)
            return dt.astimezone(timezone.utc)
        dt = datetime.strptime(s, "%Y%m%d").replace(tzinfo=MACRO_TZ)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


async def _fetch_bls_macro_from_ics() -> int:
    cnt = 0
    try:
        async with httpx.AsyncClient(timeout=25.0, headers={"User-Agent": "NoytrixCalendar/1.0"}) as c:
            r = await c.get(BLS_ICS_URL, follow_redirects=True)
            r.raise_for_status()
            ics = r.text
    except Exception:
        return 0

    now = datetime.now(timezone.utc)
    d1 = now - timedelta(days=7)
    d2 = now + timedelta(days=UNLOCK_LOOKAHEAD_DAYS)

    for b in ics.split("BEGIN:VEVENT")[1:]:
        try:
            if "END:VEVENT" in b:
                b = b.split("END:VEVENT", 1)[0]

            m_sum = re.search(r"^SUMMARY(?:;[^:]*)?:(.+)$", b, re.MULTILINE)
            if not m_sum:
                continue
            summary = m_sum.group(1).strip()
            low = summary.lower()

            if "consumer price index" in low:
                title = "CPI (US Inflation) — BLS"
            elif "employment situation" in low:
                title = "NFP / Employment Situation — BLS"
            elif "producer price index" in low:
                title = "PPI (US Producer Inflation) — BLS"
            else:
                continue

            m_dt = re.search(r"^DTSTART(?:;[^:]*)?:(.+)$", b, re.MULTILINE)
            if not m_dt:
                continue
            dt = _parse_ics_dt(m_dt.group(0))
            if not dt or dt < d1 or dt > d2:
                continue

            upsert_event(
                {
                    "title": title,
                    "asset": "USD",
                    "type": "Macro",
                    "impact": "high",
                    "start_dt": dt,
                    "source_url": BLS_ICS_URL,
                    "summary": "Official BLS calendar (iCal).",
                    "provider": "bls_ics",
                    "all_day": False,
                    "event_date": _ymd(dt),
                }
            )
            cnt += 1
        except Exception:
            continue

    return cnt


def _extract_year_fomc_ranges(html: str, year: int) -> List[Tuple[int, int, int, bool]]:
    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }

    out: List[Tuple[int, int, int, bool]] = []
    m = re.search(
        rf"{year}\s+FOMC Meetings(.+?)({year-1}\s+FOMC Meetings|{year+1}\s+FOMC Meetings|$)",
        html,
        re.DOTALL | re.IGNORECASE,
    )
    block = m.group(1) if m else html

    for name, mm in month_map.items():
        mmatch = re.search(rf"\b{name}\b[\s\S]{{0,200}}?\b(\d{{1,2}})\s*-\s*(\d{{1,2}})(\*)?", block, re.IGNORECASE)
        if not mmatch:
            continue
        d1 = int(mmatch.group(1))
        d2 = int(mmatch.group(2))
        star = bool(mmatch.group(3))
        out.append((mm, d1, d2, star))

    uniq: Dict[Tuple[int, int, int], bool] = {}
    for mm, d1v, d2v, star in out:
        uniq[(mm, d1v, d2v)] = star

    return [(mm, d1v, d2v, uniq[(mm, d1v, d2v)]) for (mm, d1v, d2v) in sorted(uniq.keys())]


async def _fetch_fomc_macro() -> int:
    cnt = 0
    try:
        async with httpx.AsyncClient(timeout=25.0, headers={"User-Agent": "NoytrixCalendar/1.0"}) as c:
            r = await c.get(FOMC_CAL_URL, follow_redirects=True)
            r.raise_for_status()
            html = r.text
    except Exception:
        return 0

    current_year = datetime.now(timezone.utc).year
    years = [current_year, current_year + 1]

    now = datetime.now(timezone.utc)
    d1 = now - timedelta(days=7)
    d2 = now + timedelta(days=UNLOCK_LOOKAHEAD_DAYS)

    for year in years:
        ranges = _extract_year_fomc_ranges(html, year)
        for (month, _day_start, day_end, star) in ranges:
            try:
                local_dt = datetime(year, month, day_end, 14, 0, 0, tzinfo=MACRO_TZ)
                dt = local_dt.astimezone(timezone.utc)
                if dt < d1 or dt > d2:
                    continue

                upsert_event(
                    {
                        "title": "FOMC Rate Decision — Federal Reserve",
                        "asset": "USD",
                        "type": "Macro",
                        "impact": "high",
                        "start_dt": dt,
                        "source_url": FOMC_CAL_URL,
                        "summary": "Official Fed calendar. Time set to 14:00 ET (typical statement).",
                        "provider": "fed_fomc",
                        "all_day": False,
                        "event_date": _ymd(dt),
                    }
                )
                cnt += 1

                if star:
                    pc_local = datetime(year, month, day_end, 14, 30, 0, tzinfo=MACRO_TZ)
                    pc_dt = pc_local.astimezone(timezone.utc)
                    upsert_event(
                        {
                            "title": "FOMC Press Conference (SEP meeting) — Federal Reserve",
                            "asset": "USD",
                            "type": "Macro",
                            "impact": "high",
                            "start_dt": pc_dt,
                            "source_url": FOMC_CAL_URL,
                            "summary": "SEP meeting press conference (approx 14:30 ET).",
                            "provider": "fed_fomc",
                            "all_day": False,
                            "event_date": _ymd(pc_dt),
                        }
                    )
                    cnt += 1
            except Exception:
                continue

    return cnt


def _strip_tags(v: str) -> str:
    return re.sub(r"<[^>]+>", " ", v or "").replace("&nbsp;", " ").replace("&amp;", "&").strip()


def _norm_ampm(v: str) -> str:
    s = (v or "").strip().lower().replace("a.m.", "AM").replace("p.m.", "PM").replace("am", "AM").replace("pm", "PM")
    s = re.sub(r"\s+", " ", s).strip()
    return s


async def _fetch_fed_speeches() -> int:
    cnt = 0
    now_local = datetime.now(MACRO_TZ)
    months = []
    for add in (0, 1):
        idx = (now_local.month - 1) + add
        y = now_local.year + (idx // 12)
        m = (idx % 12) + 1
        months.append((y, m))

    d1 = datetime.now(timezone.utc) - timedelta(days=7)
    d2 = datetime.now(timezone.utc) + timedelta(days=UNLOCK_LOOKAHEAD_DAYS)

    try:
        async with httpx.AsyncClient(timeout=25.0, headers={"User-Agent": "NoytrixCalendar/1.0"}) as c:
            for year, month_num in months:
                month_name = datetime(year, month_num, 1).strftime("%B").lower()
                url = FED_EVENTS_MONTH_URL.format(year=year, month=month_name)
                try:
                    r = await c.get(url, follow_redirects=True)
                    r.raise_for_status()
                    html = r.text
                except Exception:
                    continue

                blocks = html.split('<div class="row">')
                for block in blocks:
                    if 'col-xs-2' not in block or 'col-xs-7' not in block or 'col-xs-3' not in block:
                        continue

                    m_time = re.search(r'<div class="col-xs-2">[\s\S]*?<p>([^<]+)</p>', block, re.IGNORECASE)
                    m_day = re.search(r'<div class="col-xs-3">[\s\S]*?<p>(\d{1,2})</p>', block, re.IGNORECASE)
                    m_col7 = re.search(r'<div class="col-xs-7">([\s\S]*?)</div>[\s\S]*?<div class="col-xs-3">', block, re.IGNORECASE)

                    if not m_time or not m_day or not m_col7:
                        continue

                    col7 = m_col7.group(1)
                    ps = re.findall(r'<p[^>]*>([\s\S]*?)</p>', col7, re.IGNORECASE)
                    ps = [_strip_tags(x).strip() for x in ps if _strip_tags(x).strip()]
                    if not ps:
                        continue

                    title_raw = ps[0]
                    subtitle_raw = ps[1] if len(ps) > 1 else ""
                    place_raw = ps[2] if len(ps) > 2 else ""

                    text_blob = f"{title_raw} {subtitle_raw} {place_raw}"
                    if not re.search(r"Powell|Federal Reserve|Board of Governors|Governor|Chair", text_blob, re.IGNORECASE):
                        continue

                    try:
                        day = int(m_day.group(1))
                        tm = _norm_ampm(m_time.group(1))
                        dt_local = datetime.strptime(
                            f"{year}-{month_num:02d}-{day:02d} {tm}",
                            "%Y-%m-%d %I:%M %p"
                        ).replace(tzinfo=MACRO_TZ)
                        dt = dt_local.astimezone(timezone.utc)
                    except Exception:
                        continue

                    if dt < d1 or dt > d2:
                        continue

                    title = "Jerome Powell Speech — Federal Reserve" if re.search(r"Powell", title_raw, re.IGNORECASE) else "Federal Reserve Event"
                    summary = re.sub(r"\s+", " ", f"{title_raw}. {subtitle_raw}. {place_raw}").strip()[:280]

                    upsert_event(
                        {
                            "title": title,
                            "asset": "USD",
                            "type": "Macro",
                            "impact": "high",
                            "start_dt": dt,
                            "source_url": url,
                            "summary": summary,
                            "provider": "fed_calendar",
                            "all_day": False,
                            "event_date": _ymd(dt),
                        }
                    )
                    cnt += 1
    except Exception:
        return cnt

    return cnt

async def _fetch_eu_macro() -> int:
    cnt = 0
    try:
        items = eu_macro.fetch() or []
    except Exception:
        return 0

    now = datetime.now(timezone.utc)
    d1 = now - timedelta(days=7)
    d2 = now + timedelta(days=UNLOCK_LOOKAHEAD_DAYS)

    for row in items:
        try:
            start_dt = row.get("start_ts")
            if not isinstance(start_dt, datetime):
                continue
            dt = start_dt.astimezone(timezone.utc)
            if dt < d1 or dt > d2:
                continue

            upsert_event(
                {
                    "title": row.get("title") or "ECB Event",
                    "asset": "EUR",
                    "type": "Macro",
                    "impact": (row.get("impact") or "high").lower(),
                    "start_dt": dt,
                    "source_url": row.get("source_url"),
                    "summary": row.get("summary"),
                    "provider": "eu_macro",
                    "all_day": False,
                    "event_date": _ymd(dt),
                }
            )
            cnt += 1
        except Exception:
            continue
    return cnt




# ===== FMP ECONOMIC CALENDAR =====
async def _fetch_fmp_macro() -> int:
    import os
    import httpx
    from datetime import datetime, timezone, timedelta

    key = os.getenv("FMP_API_KEY")
    if not key:
        return 0

    url = f"https://financialmodelingprep.com/stable/economic-calendar?apikey={key}"

    now = datetime.now(timezone.utc)
    d1 = now - timedelta(days=7)
    d2 = now + timedelta(days=UNLOCK_LOOKAHEAD_DAYS)

    cnt = 0
    try:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return 0

    for e in data:
        try:
            title = (e.get("event") or "").lower()

            if not any(x in title for x in ["cpi","inflation","employment","nonfarm","nfp","ppi"]):
                continue

            dt = datetime.fromisoformat(e.get("date")).replace(tzinfo=timezone.utc)
            if dt < d1 or dt > d2:
                continue

            upsert_event(
                {
                    "title": e.get("event"),
                    "asset": "USD",
                    "type": "Macro",
                    "impact": (e.get("impact") or "high").lower(),
                    "start_dt": dt,
                    "source_url": "https://financialmodelingprep.com",
                    "summary": "FMP economic calendar",
                    "provider": "fmp_macro",
                    "all_day": False,
                    "event_date": _ymd(dt),
                }
            )
            cnt += 1
        except Exception:
            continue

    return cnt
async def _fetch_us_macro() -> int:
    cnt = 0
    try:
        items = us_macro.fetch() or []
    except Exception:
        return 0

    now = datetime.now(timezone.utc)
    d1 = now - timedelta(days=7)
    d2 = now + timedelta(days=UNLOCK_LOOKAHEAD_DAYS)

    for row in items:
        try:
            start_dt = row.get("start_ts")
            if not isinstance(start_dt, datetime):
                continue
            dt = start_dt.astimezone(timezone.utc)
            if dt < d1 or dt > d2:
                continue

            upsert_event(
                {
                    "title": row.get("title") or "US Macro Event",
                    "asset": "USD",
                    "type": "Macro",
                    "impact": (row.get("impact") or "high").lower(),
                    "start_dt": dt,
                    "source_url": row.get("source_url"),
                    "summary": row.get("summary"),
                    "provider": "us_macro",
                    "all_day": False,
                    "event_date": _ymd(dt),
                }
            )
            cnt += 1
        except Exception:
            continue
    return cnt


# ====== HARVEST (AUTO) ======
_harvest_lock = asyncio.Lock()


async def _http_get_json(
    c: httpx.AsyncClient, url: str, params: Optional[dict] = None, headers: Optional[dict] = None
) -> Optional[dict]:
    try:
        r = await c.get(url, params=params, headers=headers, follow_redirects=True)
        r.raise_for_status()
        j = r.json()
        return j if isinstance(j, dict) else None
    except Exception:
        return None


async def _fetch_coinmarketcal() -> int:
    if not COINMARKETCAL_API_KEY:
        return 0

    url = "https://developers.coinmarketcal.com/v1/events"
    now = datetime.now(timezone.utc)
    d1 = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    d2 = (now + timedelta(days=COINMARKETCAL_RANGE_DAYS)).strftime("%Y-%m-%d")

    headers = {
        "x-api-key": COINMARKETCAL_API_KEY,
        "Accept": "application/json",
        "User-Agent": "NoytrixCalendar/1.0",
    }

    cnt = 0
    async with httpx.AsyncClient(timeout=25.0) as c:
        for page in range(1, COINMARKETCAL_MAX_PAGES + 1):
            params = {
                "page": page,
                "max": 200,
                "dateRangeStart": d1,
                "dateRangeEnd": d2,
            }

            data = await _http_get_json(c, url, params=params, headers=headers)
            if not data:
                continue

            events = data.get("body")
            if not isinstance(events, list) or not events:
                continue

            for ev in events:
                try:
                    raw_title = ev.get("title")
                    if isinstance(raw_title, dict):
                        title = (raw_title.get("en") or "").strip()
                    else:
                        title = (raw_title or ev.get("name") or "").strip()

                    if not title:
                        continue

                    dt_raw = ev.get("date_event") or ev.get("start_date") or ev.get("date")
                    if not dt_raw:
                        continue

                    raw_str = str(dt_raw).strip()

                    all_day = False
                    event_date = None
                    dt = None

                    # 1) дата без времени
                    if "T" not in raw_str:
                        date_dt = _parse_ymd_date(raw_str)
                        if not date_dt:
                            continue
                        dt = date_dt.replace(hour=12, minute=0, second=0)
                        all_day = True
                        event_date = raw_str

                    else:
                        parsed = _parse_iso_any(raw_str)
                        if not parsed:
                            continue

                        # 2) CoinMarketCal часто отдаёт fake midnight = 00:00:00Z
                        # считаем это date-only, а НЕ реальным временем
                        if (
                            parsed.hour == 0
                            and parsed.minute == 0
                            and parsed.second == 0
                        ):
                            dt = parsed.replace(hour=12, minute=0, second=0)
                            all_day = True
                            event_date = _ymd(parsed)
                        else:
                            dt = parsed
                            all_day = False
                            event_date = _ymd(parsed)

                    symbol = None
                    coins = ev.get("coins") or []
                    if isinstance(coins, list) and coins:
                        c0 = coins[0]
                        if isinstance(c0, dict):
                            symbol = (c0.get("symbol") or c0.get("name") or "").upper() or None

                    src = ev.get("source") or ev.get("url") or None

                    categories = ev.get("categories") or []
                    cat_names = []
                    if isinstance(categories, list):
                        for cat in categories:
                            if isinstance(cat, dict) and cat.get("name"):
                                cat_names.append(str(cat.get("name")).strip())

                    BAD_CATEGORIES = {
                        "AMA",
                        "Team Update",
                        "Community",
                        "Community Update",
                        "Podcast",
                        "Spaces",
                        "Interview",
                        "Town Hall",
                    }

                    if any(c in BAD_CATEGORIES for c in cat_names):
                        continue

                    typ = _guess_type(title, src, "coinmarketcal")
                    impact = "high"

                    desc = None
                    if cat_names:
                        desc = "Categories: " + ", ".join(cat_names)

                    upsert_event(
                        {
                            "title": title,
                            "asset": symbol or _guess_asset(title),
                            "type": typ,
                            "impact": impact,
                            "start_dt": dt,
                            "source_url": src,
                            "summary": desc,
                            "provider": "coinmarketcal",
                            "all_day": all_day,
                            "event_date": event_date,
                        }
                    )
                    cnt += 1
                except Exception:
                    continue

    return cnt

async def _fetch_deribit_expirations() -> int:
    cnt = 0
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "NoytrixCalendar/1.0"}) as c:
        for cur in ("BTC", "ETH"):
            for kind in ("option", "future"):
                try:
                    j = await _http_get_json(
                        c,
                        f"{DERIBIT_API}/public/get_expirations",
                        params={"currency": cur, "kind": kind},
                    )
                    arr = (j or {}).get("result") or []
                    if not isinstance(arr, list):
                        continue

                    for ts_ms in arr[:30]:
                        dt = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc)
                        title = f"Deribit: {cur} {('options' if kind == 'option' else 'futures')} expiry"
                        upsert_event(
                            {
                                "title": title,
                                "asset": cur,
                                "type": "Derivatives",
                                "impact": "mid",
                                "start_dt": dt,
                                "source_url": "https://www.deribit.com",
                                "summary": "Expiry may increase volatility.",
                                "provider": "deribit",
                                "all_day": False,
                                "event_date": _ymd(dt),
                            }
                        )
                        cnt += 1
                except Exception:
                    continue
    return cnt


# ====== TOKEN UNLOCKS (MOBULA) ======
def _dt_from_epoch(value: Any) -> Optional[datetime]:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            ts = float(value)
        else:
            ts = float(str(value).strip())
        if ts > 1e12:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None


def _fmt_num(x: Any) -> str:
    try:
        v = float(x)
        if v >= 1e9:
            return f"{v/1e9:.2f}B"
        if v >= 1e6:
            return f"{v/1e6:.2f}M"
        if v >= 1e3:
            return f"{v/1e3:.2f}K"
        return f"{v:.2f}"
    except Exception:
        return str(x)


async def _fetch_mobula_unlocks() -> int:
    """
    Берём unlock / vesting из Mobula через multi-metadata
    по списку сильных market-moving токенов.
    """
    headers: Dict[str, str] = {"User-Agent": "NoytrixCalendar/1.0"}
    if MOBULA_API_KEY:
        headers["Authorization"] = f"Bearer {MOBULA_API_KEY}"
    else:
        return 0

    now = datetime.now(timezone.utc)
    d1 = now - timedelta(days=7)
    d2 = now + timedelta(days=UNLOCK_LOOKAHEAD_DAYS)

    strong_assets = [
        "Aptos",
        "Arbitrum",
        "Sui",
        "Optimism",
        "Avalanche",
        "Starknet",
        "Sei",
        "Celestia",
        "Worldcoin",
        "Ethena",
        "ZetaChain",
        "Jupiter",
        "dYdX",
        "EigenLayer",
        "Wormhole",
        "Immutable",
        "ApeCoin",
        "Axie Infinity",
        "Manta Network",
        "Saga",
    ]

    cnt = 0
    url = f"{MOBULA_BASE}/api/1/multi-metadata"

    async with httpx.AsyncClient(timeout=30.0, headers=headers) as c:
        j = await _http_get_json(c, url, params={"assets": ",".join(strong_assets)})
        arr = (j or {}).get("data") or []
        if not isinstance(arr, list) or not arr:
            return 0

        for item in arr:
            if not isinstance(item, dict):
                continue

            meta = item.get("data") or item
            if not isinstance(meta, dict):
                continue

            symbol = (meta.get("symbol") or "").upper().strip() or None
            schedule = (
                meta.get("release_schedule")
                or meta.get("vesting_schedule")
                or meta.get("unlock_schedule")
            )

            if not isinstance(schedule, list) or not schedule:
                continue

            for it in schedule:
                if not isinstance(it, dict):
                    continue

                dt = (
                    _dt_from_epoch(it.get("unlock_date"))
                    or _dt_from_epoch(it.get("date"))
                    or _dt_from_epoch(it.get("timestamp"))
                )
                if not dt:
                    continue
                if dt < d1 or dt > d2:
                    continue

                amt = (
                    it.get("tokens_to_unlock")
                    or it.get("amount")
                    or it.get("unlock_amount")
                    or it.get("token_amount")
                    or None
                )

                cat = (it.get("category") or it.get("type") or "Unlock").strip()

                if symbol:
                    title = f"{symbol} Token Unlock — {cat}"
                    asset = symbol
                else:
                    title = f"Token Unlock — {cat}"
                    asset = None

                summary = "Token unlock / vesting release schedule."
                if amt is not None:
                    summary = f"Unlock amount: {_fmt_num(amt)} (tokens)."

                upsert_event(
                    {
                        "title": title,
                        "asset": asset,
                        "type": "Tokenomics",
                        "impact": "high",
                        "start_dt": dt,
                        "source_url": "https://mobula.io",
                        "summary": summary,
                        "provider": "mobula_unlocks",
                        "all_day": False,
                        "event_date": _ymd(dt),
                    }
                )
                cnt += 1

    return cnt


async def harvest_if_stale(force: bool = False) -> None:
    async with _harvest_lock:
        last = get_meta("events:last_harvest")
        now = datetime.now(timezone.utc)

        if not force and last:
            dt = _parse_iso_any(last)
            if dt and (now - dt) < timedelta(minutes=15):
                return

        if force:
            cleanup_noisy_events()

        tasks = [
            _fetch_coinmarketcal(),
            _fetch_deribit_expirations(),
            _fetch_bls_macro_from_ics(),
            _fetch_fed_speeches(),
            _fetch_fomc_macro(),
            _fetch_eu_macro(),
            _fetch_us_macro(),
            _fetch_fmp_macro(),
            _fetch_mobula_unlocks(),
        ]
        try:
            await asyncio.gather(*tasks)
        except Exception:
            pass

        set_meta("events:last_harvest", _now_iso())


# ====== API ======
def _sql_filters(
    d1: Optional[datetime],
    d2: Optional[datetime],
    types_set: Optional[set],
    impact_set: Optional[set],
) -> Tuple[str, List[Any]]:
    wh = []
    args: List[Any] = []

    if d1:
        wh.append("start_ts >= ?")
        args.append(_to_iso_utc(d1))
    if d2:
        d2 = d2.replace(hour=23, minute=59, second=59)
        wh.append("start_ts <= ?")
        args.append(_to_iso_utc(d2))

    if types_set:
        wh.append("type IN (" + ",".join(["?"] * len(types_set)) + ")")
        args.extend(sorted(list(types_set)))

    if impact_set:
        wh.append("impact IN (" + ",".join(["?"] * len(impact_set)) + ")")
        args.extend(sorted(list(impact_set)))

    where = (" WHERE " + " AND ".join(wh)) if wh else ""
    return where, args


@router.get("/events")
async def events(
    d1: Optional[str] = Query(None),
    d2: Optional[str] = Query(None),
    from_: Optional[str] = Query(None, alias="from"),
    to_: Optional[str] = Query(None, alias="to"),
    types: Optional[str] = Query(None),
    impact: Optional[str] = Query(None),
):
    d1 = d1 or from_
    d2 = d2 or to_
    await harvest_if_stale()

    want_types = {x.strip() for x in (types or "").split(",") if x.strip()} or None
    if want_types:
        want_types = {t for t in want_types if t in VALID_TYPES} or None

    want_impact = {x.strip().lower() for x in (impact or "").split(",") if x.strip()} or None
    if want_impact:
        want_impact = {i for i in want_impact if i in IMPACT_ORDER} or None

    e1 = _parse_iso_any(d1) if d1 else None
    e2 = _parse_iso_any(d2) if d2 else None

    now = datetime.now(timezone.utc)
    if not e1:
        e1 = now - timedelta(days=7)
    if not e2:
        e2 = now + timedelta(days=UNLOCK_LOOKAHEAD_DAYS)

    where, args = _sql_filters(e1, e2, want_types, want_impact)

    conn = db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT title, asset, type, impact, start_ts, source_url, summary, provider, all_day, has_time, event_date
            FROM events
            """ + where,
            args,
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    out = []
    seen = set()
    allowed_providers = {"fed_calendar", "fed_fomc", "bls_ics", "eu_macro", "us_macro"}
    allowed_types = {"Macro"}

    for title, asset, typ, imp, start_ts, source_url, summary, provider, all_day, has_time, event_date in rows:
        dt = _parse_iso_any(start_ts)
        if not dt:
            continue

        if provider not in allowed_providers:
            continue
        if typ not in allowed_types:
            continue
        if bool(all_day):
            continue
        if not bool(has_time):
            continue

        key = f"{provider}|{title}|{start_ts}"
        if key in seen:
            continue
        seen.add(key)

        out.append(
            {
                "id": _sha1(f"{title}|{asset or ''}|{typ}|{event_date or start_ts}|{int(bool(all_day))}")[:16],
                "title": title,
                "start_ts": _to_iso_utc(dt),
                "impact": (imp or "mid").lower(),
                "type": typ,
                "asset": asset,
                "summary": summary,
                "source_url": source_url,
                "provider": provider,
                "all_day": bool(all_day),
                "has_time": bool(has_time),
                "event_date": event_date or _ymd(dt),
            }
        )

    out.sort(key=lambda x: (x.get("event_date") or "", x["start_ts"], x["title"]))
    return {"items": out}


# ✅ совместимость: если где-то дергаешь /api/calendar без /events
@router.get("")
async def calendar_root(
    d1: Optional[str] = Query(None),
    d2: Optional[str] = Query(None),
    from_: Optional[str] = Query(None, alias="from"),
    to_: Optional[str] = Query(None, alias="to"),
    types: Optional[str] = Query(None),
    impact: Optional[str] = Query(None),
):
    return await events(d1=d1 or from_, d2=d2 or to_, types=types, impact=impact)


@router.post("/events/refresh")
async def events_refresh():
    await harvest_if_stale(force=True)
    return {"ok": True}
