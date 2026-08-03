from __future__ import annotations

from typing import Any

from .config import INVESTOR_SOURCES_PATH
from .discovery import fetch_public_source, load_sources
from .repository import add_evidence, upsert_prospect


PIPELINE = "noytrix_investors"


def sync_public_investor_catalog(limit: int = 10) -> dict[str, Any]:
    """Maintain a small, transparent public investor catalog for later fit research."""
    seen = 0
    errors: list[dict[str, str]] = []
    for source in load_sources(INVESTOR_SOURCES_PATH)[:max(1, limit)]:
        try:
            page = fetch_public_source(source["url"])
            prospect_id = upsert_prospect(
                pipeline=PIPELINE,
                name=source["name"],
                domain=page["domain"],
                website_url=page["url"],
                category="web3_investor",
                summary=str(page.get("description") or page.get("title") or "")[:1200],
            )
            add_evidence(prospect_id, source_url=page["url"], claim_type="public_investor_source", excerpt=page.get("description") or page.get("title") or source["name"], confidence=0.8)
            seen += 1
        except Exception as exc:
            errors.append({"source": source["name"], "error": str(exc)[:200]})
    return {"cataloged": seen, "errors": errors}
