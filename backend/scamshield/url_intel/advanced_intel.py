from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse


DB_PATH = Path("data/url_intelligence.sqlite3")


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
    CREATE TABLE IF NOT EXISTS url_fingerprints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        host TEXT UNIQUE,
        root_domain TEXT,
        title TEXT,
        text_hash TEXT,
        script_hash TEXT,
        ui_hash TEXT,
        infra_hash TEXT,
        behavior_hash TEXT,
        brands TEXT,
        first_seen INTEGER,
        last_seen INTEGER,
        seen_count INTEGER DEFAULT 1
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_url_fp_root ON url_fingerprints(root_domain)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_url_fp_text ON url_fingerprints(text_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_url_fp_ui ON url_fingerprints(ui_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_url_fp_behavior ON url_fingerprints(behavior_hash)")
    conn.commit()
    return conn


def _sha(x: str, n: int = 24) -> str:
    return hashlib.sha256(str(x or "").encode("utf-8", "ignore")).hexdigest()[:n]


def _root(host: str) -> str:
    parts = [p for p in str(host or "").lower().split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else str(host or "").lower()


def _clean_text(x: str, limit: int = 30000) -> str:
    x = re.sub(r"\s+", " ", str(x or "").lower()).strip()
    return x[:limit]


def _extract_scripts(html: str) -> str:
    html = str(html or "")
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.I | re.S)
    srcs = re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", html, flags=re.I)
    return _clean_text(" ".join(srcs + scripts), 40000)


def _ui_tokens(html: str, visible_text: str) -> str:
    html = str(html or "").lower()
    text = str(visible_text or "").lower()

    buttons = re.findall(r"<button[^>]*>(.*?)</button>", html, flags=re.I | re.S)
    inputs = re.findall(r"<input[^>]*(?:placeholder|name|type)=[\"']([^\"']+)[\"']", html, flags=re.I)
    links = re.findall(r"<a[^>]*>(.*?)</a>", html, flags=re.I | re.S)

    blob = " ".join(buttons + inputs + links + [text])
    blob = re.sub(r"<[^>]+>", " ", blob)
    return _clean_text(blob, 20000)


def _brands(text: str, host: str) -> List[str]:
    known = [
        "binance", "coinbase", "metamask", "trust wallet", "phantom", "okx",
        "bybit", "kraken", "uniswap", "pancakeswap", "opensea", "ledger",
        "trezor", "walletconnect"
    ]
    blob = f"{text} {host}".lower()
    return sorted({b for b in known if b in blob or b.replace(" ", "") in blob})


def _jaccard(a: str, b: str) -> float:
    def grams(x: str) -> set[str]:
        words = re.findall(r"[a-z0-9]{3,}", str(x or "").lower())
        return set(words[:800])
    A, B = grams(a), grams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / max(1, len(A | B))


def analyze_advanced_url_intel(
    url: str,
    host: str,
    html: str,
    visible_text: str,
    title: str,
    infrastructure: Dict[str, Any] | None = None,
    redirect_chain: Dict[str, Any] | None = None,
    wallet_trap: Dict[str, Any] | None = None,
    crypto_lure: Dict[str, Any] | None = None,
    js_behavior: Dict[str, Any] | None = None,
    visual_phishing: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    host = str(host or urlparse(str(url or "")).netloc).lower().strip(".")
    root_domain = _root(host)
    now = int(time.time())

    html_clean = _clean_text(html)
    text_clean = _clean_text(visible_text)
    script_blob = _extract_scripts(html)
    ui_blob = _ui_tokens(html, visible_text)

    infra = infrastructure or {}
    rc = redirect_chain or {}
    wt = wallet_trap or {}
    cl = crypto_lure or {}
    js = js_behavior or {}
    vp = visual_phishing or {}

    infra_parts = []
    for k in ("a_records", "aaaa_records", "ns_records", "cname_records", "known_platform_hints"):
        v = infra.get(k) or []
        infra_parts.extend([str(x).lower() for x in v])

    behavior_parts = []
    for obj in (wt, cl, js, vp):
        for sig in obj.get("signals") or []:
            behavior_parts.append(str(sig.get("code") or ""))

    brands = _brands(f"{title} {visible_text}", host)

    fp = {
        "text_hash": _sha(text_clean),
        "script_hash": _sha(script_blob),
        "ui_hash": _sha(ui_blob),
        "infra_hash": _sha(" ".join(sorted(infra_parts))),
        "behavior_hash": _sha(" ".join(sorted(behavior_parts))),
        "brands": brands,
    }

    signals = []
    score = 0
    related = []

    conn = _db()

    rows = conn.execute("""
        SELECT * FROM url_fingerprints
        WHERE host != ?
        ORDER BY last_seen DESC
        LIMIT 300
    """, (host,)).fetchall()

    for r in rows:
        r = dict(r)
        matched = []

        if fp["text_hash"] and fp["text_hash"] == r.get("text_hash"):
            matched.append("same_text_hash")
        if fp["ui_hash"] and fp["ui_hash"] == r.get("ui_hash"):
            matched.append("same_ui_hash")
        if fp["script_hash"] and fp["script_hash"] == r.get("script_hash"):
            matched.append("same_script_hash")
        if fp["behavior_hash"] and fp["behavior_hash"] == r.get("behavior_hash") and fp["behavior_hash"] != _sha(""):
            matched.append("same_behavior_hash")

        sim = _jaccard(ui_blob, r.get("title") or "")
        if sim >= 0.35:
            matched.append("ui_similarity")

        if matched:
            related.append({
                "host": r.get("host"),
                "root_domain": r.get("root_domain"),
                "matches": matched[:6],
                "seen_count": r.get("seen_count"),
                "last_seen": r.get("last_seen"),
            })

    campaign_seed = "|".join(sorted([host] + [str(x.get("host") or "") for x in related[:10]]))
    campaign_id = "urlcamp_" + _sha(campaign_seed, 16) if related else None

    if related:
        # Similarity alone is context, not proof of risk.
        # It must not raise score unless linked entities are confirmed malicious.
        signals.append({
            "code": "similar_site_fingerprint_context",
            "severity": 0,
            "text": "This page shares fingerprints with previously observed domains.",
            "related": related[:5],
        })

    if brands and not any(b.replace(" ", "") in host.replace("-", "").replace(".", "") for b in brands):
        # Mentioning other crypto brands on a legitimate page is common.
        # Brand mention alone is context, not risk.
        signals.append({
            "code": "brand_mentioned_without_matching_domain_context",
            "severity": 0,
            "text": "Page mentions trusted crypto brands but this is context only.",
            "brands": brands,
        })

    high_layers = []
    for name, obj in [
        ("wallet_trap", wt),
        ("crypto_lure", cl),
        ("js_behavior", js),
        ("visual_phishing", vp),
    ]:
        if int(obj.get("score") or 0) >= 60:
            high_layers.append(name)

    if len(high_layers) >= 2:
        score = max(score, 85)
        signals.append({
            "code": "multi_layer_behavioral_fingerprint",
            "severity": 85,
            "text": "Multiple independent behavioral phishing layers triggered together.",
            "layers": high_layers,
        })

    if rc.get("unique_root_domains") and len(rc.get("unique_root_domains") or []) >= 2 and high_layers:
        score = max(score, 80)
        signals.append({
            "code": "redirect_plus_behavioral_risk",
            "severity": 80,
            "text": "Cross-domain redirect behavior combines with phishing/wallet-risk signals.",
        })

    level = (
        "critical" if score >= 90 else
        "high" if score >= 70 else
        "medium" if score >= 40 else
        "low" if score > 0 else
        "safe"
    )

    conn.execute("""
    INSERT INTO url_fingerprints
    (host, root_domain, title, text_hash, script_hash, ui_hash, infra_hash, behavior_hash, brands, first_seen, last_seen, seen_count)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    ON CONFLICT(host) DO UPDATE SET
        title=excluded.title,
        text_hash=excluded.text_hash,
        script_hash=excluded.script_hash,
        ui_hash=excluded.ui_hash,
        infra_hash=excluded.infra_hash,
        behavior_hash=excluded.behavior_hash,
        brands=excluded.brands,
        last_seen=excluded.last_seen,
        seen_count=seen_count+1
    """, (
        host, root_domain, str(title or "")[:300],
        fp["text_hash"], fp["script_hash"], fp["ui_hash"],
        fp["infra_hash"], fp["behavior_hash"],
        json.dumps(brands, ensure_ascii=False),
        now, now,
    ))
    conn.commit()
    conn.close()

    return {
        "available": True,
        "score": score,
        "level": level,
        "fingerprints": fp,
        "campaign_id": campaign_id,
        "related_domains": related[:10],
        "signals": signals,
        "summary": (
            "Advanced clone/campaign/infrastructure intelligence found risk signals."
            if score > 0 else
            "No strong clone/campaign/infrastructure relation signals detected."
        ),
    }
