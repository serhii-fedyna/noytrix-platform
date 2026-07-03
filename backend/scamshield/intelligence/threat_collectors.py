from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse

import feedparser
import httpx

from scamshield.intelligence.postgres_intelligence import connect, guess_entity_type, normalize_entity
from scamshield.intelligence.scam_family import classify_scam_family


COLLECTOR_VERSION = "1.0"

DEFAULT_RSS_FEEDS = [
    "https://www.reddit.com/r/CryptoScams/new/.rss",
    "https://www.reddit.com/r/Scams/new/.rss",
]

DEFAULT_TEXT_FEEDS = [
    "https://openphish.com/feed.txt",
]

URL_RE = re.compile(r"https?://[^\s<>'\"\)\]]+", re.I)
DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?\.)+(?:com|net|org|io|app|xyz|finance|capital|co|ai|me|site|online|info|biz|top|vip|shop|live|pro|cloud|dev|global|exchange|market|markets|trade|trading|broker|finance|icu|lol|cc|support|store)\b",
    re.I,
)

BLOCKED_HOST_PARTS = {
    "reddit.com",
    "redd.it",
    "redditmedia.com",
    "preview.redd.it",
    "i.redd.it",
    "imgur.com",
    "youtube.com",
    "youtu.be",
}


def _split_env_urls(name: str, defaults: List[str]) -> List[str]:
    raw = os.getenv(name)
    if not raw:
        return defaults
    return [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]


def _host(value: str) -> str:
    try:
        u = value if str(value or "").startswith(("http://", "https://")) else "https://" + str(value or "")
        return (urlparse(u).hostname or "").lower().strip(".")
    except Exception:
        return ""


def _clean_target(value: str) -> str:
    return str(value or "").strip().rstrip(".,;:!?)]}")


def _is_blocked_target(value: str) -> bool:
    host = _host(value)
    if not host or "." not in host:
        return True
    return any(part in host for part in BLOCKED_HOST_PARTS)


def extract_targets(text: str) -> List[str]:
    text = str(text or "")
    found = [_clean_target(x) for x in URL_RE.findall(text)]
    found.extend(_clean_target(x) for x in DOMAIN_RE.findall(text))
    out: List[str] = []
    for item in found:
        if not item or _is_blocked_target(item):
            continue
        if item not in out:
            out.append(item)
    return out[:50]


def score_collected_target(source: str, title: str, body: str, target: str) -> Dict[str, Any]:
    text = f"{source} {title} {body} {target}".lower()
    host = _host(target)
    score = 0
    reasons: List[str] = []

    weighted = {
        "scam": 22,
        "phishing": 30,
        "fake": 24,
        "stolen": 28,
        "drain": 36,
        "drainer": 38,
        "seed phrase": 40,
        "private key": 45,
        "recovery phrase": 40,
        "wallet": 12,
        "connect wallet": 25,
        "approve": 22,
        "permit2": 30,
        "airdrop": 18,
        "claim": 16,
        "broker": 24,
        "investment": 24,
        "withdraw": 16,
        "recovery scam": 30,
    }

    for word, points in weighted.items():
        if word in text:
            score += points
            reasons.append(word)

    if "cryptoscams" in source.lower():
        score += 25
        reasons.append("crypto scam community")
    if any(w in host for w in ["claim", "airdrop", "reward", "wallet", "verify", "bonus", "mint"]):
        score += 18
        reasons.append("lure domain")
    if any(w in host for w in ["capital", "wealth", "asset", "broker", "trade", "invest"]):
        score += 18
        reasons.append("investment domain")

    score = min(100, score)
    status = "quarantine"
    if score >= 90:
        status = "malicious"
    elif score >= 65:
        status = "quarantine"
    else:
        status = "observed"

    family = classify_scam_family({
        "kind": guess_entity_type(target),
        "input": target,
        "host": host,
        "evidence": [{"code": reason.replace(" ", "_"), "severity": min(90, score), "text": reason} for reason in reasons],
    })

    return {
        "score": score,
        "status": status,
        "confidence": min(92, max(45, score)),
        "reasons": reasons[:10],
        "scam_family": family.get("primary_family"),
        "family_confidence": family.get("confidence"),
    }


def ensure_collector_schema(cur) -> None:
    cur.execute("""
    CREATE TABLE IF NOT EXISTS source_feeds (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        source_type TEXT NOT NULL DEFAULT 'public_database',
        url TEXT,
        trust_level INTEGER NOT NULL DEFAULT 50,
        active BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_import_at TIMESTAMPTZ,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE TABLE IF NOT EXISTS raw_indicators (
        id BIGSERIAL PRIMARY KEY,
        feed_id BIGINT REFERENCES source_feeds(id) ON DELETE SET NULL,
        source_name TEXT NOT NULL,
        raw_value TEXT NOT NULL,
        normalized_value TEXT NOT NULL,
        indicator_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'quarantine',
        confidence INTEGER NOT NULL DEFAULT 50,
        risk_score INTEGER NOT NULL DEFAULT 0,
        first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        seen_count INTEGER NOT NULL DEFAULT 1,
        raw_record JSONB NOT NULL DEFAULT '{}'::jsonb,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        UNIQUE(source_name, normalized_value, indicator_type)
    );
    ALTER TABLE raw_indicators ADD COLUMN IF NOT EXISTS dedupe_key TEXT;
    CREATE INDEX IF NOT EXISTS idx_raw_indicators_norm ON raw_indicators(normalized_value);
    CREATE INDEX IF NOT EXISTS idx_raw_indicators_type ON raw_indicators(indicator_type);
    CREATE INDEX IF NOT EXISTS idx_raw_indicators_status ON raw_indicators(status);
    CREATE INDEX IF NOT EXISTS idx_raw_indicators_score ON raw_indicators(risk_score DESC);
    CREATE INDEX IF NOT EXISTS idx_raw_indicators_seen ON raw_indicators(last_seen_at DESC);
    CREATE INDEX IF NOT EXISTS idx_raw_indicators_dedupe_key ON raw_indicators(dedupe_key);
    """)


def upsert_raw_indicator(cur, source_name: str, source_url: str, target: str, score: Dict[str, Any], raw_record: Dict[str, Any]) -> bool:
    raw = _clean_target(target)
    normalized = normalize_entity(raw)
    indicator_type = guess_entity_type(raw)
    if not normalized or indicator_type == "text":
        return False
    dedupe_key = f"{indicator_type}:{normalized}"
    metadata = {
        "collector": "noytrix_autonomous_threat_collectors",
        "collector_version": COLLECTOR_VERSION,
        "reasons": score.get("reasons") or [],
        "scam_family": score.get("scam_family"),
        "family_confidence": score.get("family_confidence"),
        "source_url": source_url,
    }

    cur.execute(
        """
        INSERT INTO source_feeds (name, source_type, url, trust_level, metadata, last_import_at)
        VALUES (%s, 'autonomous_collector', %s, %s, %s::jsonb, now())
        ON CONFLICT (name) DO UPDATE SET
            active = true,
            url = EXCLUDED.url,
            trust_level = GREATEST(source_feeds.trust_level, EXCLUDED.trust_level),
            metadata = source_feeds.metadata || EXCLUDED.metadata,
            last_import_at = now()
        RETURNING id
        """,
        (
            source_name,
            source_url,
            72 if int(score.get("score") or 0) >= 65 else 55,
            json.dumps({"collector_version": COLLECTOR_VERSION}, ensure_ascii=False),
        ),
    )
    feed_id = cur.fetchone()["id"]
    cur.execute(
        """
        INSERT INTO raw_indicators (
            feed_id, source_name, raw_value, normalized_value, indicator_type,
            status, confidence, risk_score, raw_record, metadata, dedupe_key
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (source_name, normalized_value, indicator_type)
        DO UPDATE SET
            last_seen_at = now(),
            seen_count = raw_indicators.seen_count + 1,
            status = CASE
                WHEN raw_indicators.status = 'malicious' THEN raw_indicators.status
                ELSE EXCLUDED.status
            END,
            confidence = GREATEST(raw_indicators.confidence, EXCLUDED.confidence),
            risk_score = GREATEST(raw_indicators.risk_score, EXCLUDED.risk_score),
            raw_record = EXCLUDED.raw_record,
            metadata = raw_indicators.metadata || EXCLUDED.metadata,
            dedupe_key = EXCLUDED.dedupe_key
        """,
        (
            feed_id,
            source_name,
            raw,
            normalized,
            indicator_type,
            score.get("status") or "quarantine",
            int(score.get("confidence") or 50),
            int(score.get("score") or 0),
            json.dumps(raw_record, ensure_ascii=False),
            json.dumps(metadata, ensure_ascii=False),
            dedupe_key,
        ),
    )
    return True


async def _fetch_text(url: str, timeout: float = 30.0) -> str:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent": "NoytrixThreatCollector/1.0"}) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text


async def collect_rss_feed(url: str, limit: int) -> List[Dict[str, Any]]:
    text = await _fetch_text(url)
    parsed = await asyncio.to_thread(feedparser.parse, text)
    out: List[Dict[str, Any]] = []
    for entry in list(parsed.entries or [])[:limit]:
        title = str(entry.get("title") or "")
        summary = str(entry.get("summary") or "")
        link = str(entry.get("link") or "")
        for target in extract_targets(f"{title} {summary}"):
            score = score_collected_target(url, title, summary, target)
            if int(score.get("score") or 0) < 45:
                continue
            out.append({
                "source_name": "autonomous_reddit_rss",
                "source_url": url,
                "target": target,
                "score": score,
                "raw_record": {"title": title, "summary": summary[:1200], "link": link, "feed": url},
            })
    return out


async def collect_text_feed(url: str, limit: int) -> List[Dict[str, Any]]:
    text = await _fetch_text(url)
    out: List[Dict[str, Any]] = []
    source_name = "autonomous_" + re.sub(r"[^a-z0-9]+", "_", (_host(url) or "text_feed").lower()).strip("_")[:40]
    for line in text.splitlines()[:limit]:
        target = _clean_target(line)
        if not target or _is_blocked_target(target):
            continue
        score = score_collected_target(url, "public threat feed", "", target)
        score["score"] = max(int(score.get("score") or 0), 72)
        score["status"] = "quarantine"
        score["confidence"] = max(int(score.get("confidence") or 0), 70)
        out.append({
            "source_name": source_name,
            "source_url": url,
            "target": target,
            "score": score,
            "raw_record": {"line": target, "feed": url},
        })
    return out


async def run_autonomous_collectors_once(limit_per_source: int | None = None) -> Dict[str, Any]:
    limit = max(5, min(int(limit_per_source or os.getenv("NOYTRIX_COLLECTOR_LIMIT", "80")), 500))
    rss_feeds = _split_env_urls("NOYTRIX_COLLECTOR_RSS_FEEDS", DEFAULT_RSS_FEEDS)
    text_feeds = _split_env_urls("NOYTRIX_COLLECTOR_TEXT_FEEDS", DEFAULT_TEXT_FEEDS)

    started = time.time()
    collected: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for url in rss_feeds:
        try:
            collected.extend(await collect_rss_feed(url, limit))
        except Exception as e:
            errors.append({"source": url, "error": str(e)[:250]})

    for url in text_feeds:
        try:
            collected.extend(await collect_text_feed(url, limit))
        except Exception as e:
            errors.append({"source": url, "error": str(e)[:250]})

    imported = 0
    with connect() as conn:
        with conn.cursor() as cur:
            ensure_collector_schema(cur)
            for item in collected:
                if upsert_raw_indicator(
                    cur,
                    item["source_name"],
                    item["source_url"],
                    item["target"],
                    item["score"],
                    item["raw_record"],
                ):
                    imported += 1
        conn.commit()

    return {
        "collector": "noytrix_autonomous_threat_collectors",
        "version": COLLECTOR_VERSION,
        "imported_or_updated": imported,
        "candidates": len(collected),
        "errors": errors[:20],
        "duration_sec": round(time.time() - started, 3),
        "sources": {"rss": rss_feeds, "text": text_feeds},
    }


async def autonomous_collector_loop(interval_sec: int | None = None) -> None:
    await asyncio.sleep(20)
    interval = max(900, int(interval_sec or os.getenv("NOYTRIX_COLLECTOR_INTERVAL_SEC", "21600")))
    print("[threat_collectors] started")
    while True:
        try:
            result = await run_autonomous_collectors_once()
            print("[threat_collectors][result]", result)
        except Exception as e:
            print("[threat_collectors] error:", e)
        await asyncio.sleep(interval)
