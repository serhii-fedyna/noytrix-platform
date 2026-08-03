from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


GITHUB_API = "https://api.github.com"
QUERIES = (
    "web3 wallet stars:>30 archived:false fork:false",
    "crypto security sdk stars:>15 archived:false fork:false",
)


def discover_web3_repositories(*, limit: int = 10) -> list[dict[str, Any]]:
    """Use GitHub's public API only; no profile scraping or private data collection."""
    token = str(os.getenv("GITHUB_TOKEN") or "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "NoytrixBrain/1.0 (+https://noytrix.com)",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    per_query = max(1, min(10, (max(1, limit) + len(QUERIES) - 1) // len(QUERIES)))
    for query in QUERIES:
        url = f"{GITHUB_API}/search/repositories?" + urlencode({"q": query, "sort": "updated", "order": "desc", "per_page": per_query})
        request = Request(url, headers=headers)
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
        for item in payload.get("items") or []:
            full_name = str(item.get("full_name") or "").strip()
            html_url = str(item.get("html_url") or "").strip()
            if not full_name or not html_url or full_name.lower() in seen:
                continue
            seen.add(full_name.lower())
            homepage = str(item.get("homepage") or "").strip()
            if not homepage.startswith("https://"):
                homepage = ""
            text = " ".join([
                str(item.get("description") or ""),
                " ".join(str(topic) for topic in (item.get("topics") or [])),
            ]).lower()
            category = "wallet" if "wallet" in text else "security" if "security" in text else "web3"
            candidates.append({
                "source_key": f"github:{full_name.lower()}",
                "name": full_name,
                "domain": f"github.com/{full_name.lower()}",
                "website_url": homepage or html_url,
                "github_url": html_url,
                "category": category,
                "summary": str(item.get("description") or "")[:1200],
                "stars": int(item.get("stargazers_count") or 0),
                "updated_at": str(item.get("updated_at") or ""),
                "topics": [str(topic) for topic in (item.get("topics") or [])[:12]],
            })
            if len(candidates) >= limit:
                return candidates
    return candidates
