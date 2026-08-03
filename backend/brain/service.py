from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from .config import SOURCES_PATH, max_sources_per_run
from .discovery import fetch_public_source, load_sources
from .reports import notify_high_quality_draft, notify_partnership_run
from .repository import (
    active_sources,
    add_contact,
    add_evidence,
    create_draft,
    create_run,
    evidence_for_prospect,
    finish_run,
    first_contact,
    mark_source_run,
    sync_sources,
    upsert_opportunity,
    upsert_prospect,
)
from .scoring import score_partnership
from .writer import generate_partnership_draft


PIPELINE = "noytrix_partnerships"


def _summary_from_page(page: dict[str, Any]) -> str:
    return str(page.get("description") or page.get("title") or page.get("text") or "")[:1200]


def _contact_research_pages(page: dict[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
    """Read only a few same-domain public contact/partner pages for evidence."""
    domain = str(page.get("domain") or "").lower()
    pages: list[dict[str, Any]] = []
    for link in page.get("relevant_links", []):
        parsed = urlparse(str(link))
        if parsed.netloc.lower().removeprefix("www.") != domain:
            continue
        try:
            pages.append(fetch_public_source(str(link)))
        except Exception:
            continue
        if len(pages) >= limit:
            break
    return pages


def run_partnership_pipeline(*, limit: int | None = None) -> dict[str, Any]:
    """Run one bounded, idempotent public-source partnership research cycle."""
    sync_sources(load_sources(SOURCES_PATH))
    sources = active_sources(limit or max_sources_per_run())
    run_id = create_run(PIPELINE)
    errors: list[dict[str, str]] = []
    qualified = 0
    drafts_created = 0
    seen = 0

    try:
        for source in sources:
            try:
                page = fetch_public_source(str(source["url"]))
                mark_source_run(int(source["id"]))
                prospect_id = upsert_prospect(
                    pipeline=PIPELINE,
                    name=str(source["name"]),
                    domain=str(page["domain"]),
                    website_url=str(page["url"]),
                    category=str(source["category"]),
                    summary=_summary_from_page(page),
                )
                seen += 1
                add_evidence(prospect_id, source_url=page["url"], claim_type="page_title", excerpt=page.get("title") or source["name"], confidence=0.9)
                if page.get("description"):
                    add_evidence(prospect_id, source_url=page["url"], claim_type="company_description", excerpt=page["description"], confidence=0.8)
                for link in page.get("relevant_links", [])[:6]:
                    add_evidence(prospect_id, source_url=page["url"], claim_type="public_relevant_link", excerpt=link, confidence=0.65)
                for email in page.get("emails", [])[:3]:
                    add_contact(prospect_id, email=email, source_url=page["url"])

                research_pages = _contact_research_pages(page)
                for research_page in research_pages:
                    if research_page.get("description"):
                        add_evidence(prospect_id, source_url=research_page["url"], claim_type="public_contact_page", excerpt=research_page["description"], confidence=0.8)
                    for email in research_page.get("emails", [])[:3]:
                        add_contact(prospect_id, email=email, source_url=research_page["url"])

                contact = first_contact(prospect_id)
                research_text = " ".join(
                    [str(page.get("title") or ""), str(page.get("description") or ""), str(page.get("text") or "")]
                    + [" ".join((str(item.get("title") or ""), str(item.get("description") or ""), str(item.get("text") or ""))) for item in research_pages]
                )
                scores = score_partnership(
                    category=str(source["category"]),
                    text=research_text,
                    has_business_contact=bool(contact),
                    relevant_links=list(page.get("relevant_links") or []),
                )
                opportunity_id = upsert_opportunity(prospect_id, scores)
                if scores["decision"] != "ready_for_review" or not contact:
                    continue
                qualified += 1
                evidence = evidence_for_prospect(prospect_id)
                prospect = {
                    "id": prospect_id,
                    "name": source["name"],
                    "primary_domain": page["domain"],
                    "category": source["category"],
                    "summary": _summary_from_page(page),
                    "website_url": page["url"],
                }
                draft = asyncio.run(generate_partnership_draft(prospect=prospect, contact=contact, evidence=evidence, score=scores))
                if not draft:
                    continue
                draft_id = create_draft(
                    opportunity_id=opportunity_id,
                    contact_id=int(contact["id"]),
                    subject=draft["subject"],
                    body=draft["body"],
                    evidence_ids=[int(item["id"]) for item in evidence],
                    model=draft.get("model"),
                )
                if draft_id:
                    drafts_created += 1
                    notify_high_quality_draft(draft_id=draft_id, prospect_name=str(source["name"]), score=int(scores["overall_score"]), email=str(contact["email"]))
            except Exception as exc:
                errors.append({"source": str(source.get("name") or source.get("url") or "unknown"), "error": str(exc)[:300]})

        summary = {
            "status": "completed" if not errors else "completed_with_source_errors",
            "sources_checked": len(sources),
            "prospects_seen": seen,
            "prospects_qualified": qualified,
            "drafts_created": drafts_created,
            "errors": errors,
        }
        finish_run(run_id, status=summary["status"], sources_checked=len(sources), prospects_seen=seen, prospects_qualified=qualified, drafts_created=drafts_created, details=summary)
        notify_partnership_run(run_id, summary)
        return {"run_id": run_id, **summary}
    except Exception as exc:
        summary = {"status": "failed", "sources_checked": len(sources), "prospects_seen": seen, "prospects_qualified": qualified, "drafts_created": drafts_created, "errors": errors + [{"source": "pipeline", "error": str(exc)[:300]}]}
        finish_run(run_id, status="failed", sources_checked=len(sources), prospects_seen=seen, prospects_qualified=qualified, drafts_created=drafts_created, details=summary, error=str(exc))
        notify_partnership_run(run_id, summary)
        return {"run_id": run_id, **summary}
