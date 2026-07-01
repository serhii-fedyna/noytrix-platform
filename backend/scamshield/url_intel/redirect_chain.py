from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx


def _host(url: str) -> str:
    try:
        return (urlparse(str(url or "")).netloc or "").split("@")[-1].split(":")[0].lower().strip(".")
    except Exception:
        return ""


def _root(host: str) -> str:
    parts = [p for p in str(host or "").lower().split(".") if p]
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


async def analyze_redirect_chain(url: str, timeout: float = 8.0) -> Dict[str, Any]:
    hops: List[Dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "NoytrixSecurityBot/1.0"},
        ) as client:
            r = await client.get(url)

            history = list(r.history or []) + [r]

            for idx, item in enumerate(history):
                u = str(item.url)
                hops.append({
                    "index": idx,
                    "url": u,
                    "host": _host(u),
                    "root_domain": _root(_host(u)),
                    "status_code": item.status_code,
                })

    except Exception as e:
        return {
            "available": False,
            "reason": str(e)[:300],
            "score": 0,
            "level": "unknown",
            "hops": hops,
            "signals": [],
        }

    signals = []
    score = 0

    unique_hosts = []
    for h in [x.get("host") for x in hops]:
        if h and h not in unique_hosts:
            unique_hosts.append(h)

    unique_roots = []
    for r in [x.get("root_domain") for x in hops]:
        if r and r not in unique_roots:
            unique_roots.append(r)

    if len(hops) >= 4:
        score += 15
        signals.append({
            "code": "long_redirect_chain",
            "severity": 15,
            "text": "The URL uses a long redirect chain."
        })

    if len(unique_roots) >= 2:
        score += 25
        signals.append({
            "code": "cross_domain_redirect",
            "severity": 25,
            "text": "The URL redirects across different root domains."
        })

    suspicious_words = ["claim", "airdrop", "bonus", "verify", "wallet", "connect", "reward", "mint"]
    if any(any(w in (hop.get("url") or "").lower() for w in suspicious_words) for hop in hops):
        score += 15
        signals.append({
            "code": "redirect_crypto_lure_words",
            "severity": 15,
            "text": "Redirect chain contains crypto lure wording."
        })

    score = min(100, score)

    level = (
        "critical" if score >= 80 else
        "high" if score >= 55 else
        "medium" if score >= 30 else
        "low" if score > 0 else
        "safe"
    )

    return {
        "available": True,
        "score": score,
        "level": level,
        "hop_count": len(hops),
        "unique_hosts": unique_hosts,
        "unique_root_domains": unique_roots,
        "final_url": hops[-1]["url"] if hops else None,
        "final_host": hops[-1]["host"] if hops else None,
        "hops": hops,
        "signals": signals,
    }
