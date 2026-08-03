from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from .config import SOURCES_PATH, auto_send_threshold, github_max_results, max_sources_per_run
from .discovery import fetch_public_source, load_sources
from .github_discovery import discover_web3_repositories
from .investor_catalog import sync_public_investor_catalog
from .outreach import auto_send_draft
from .reports import notify_auto_delivery, notify_draft_for_approval, notify_partnership_run
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


def _create_and_route_draft(*, opportunity_id: int, prospect_id: int, prospect: dict[str, Any], contact: dict[str, Any], scores: dict[str, Any]) -> bool:
    """Create one factual draft, then route it to automatic delivery or Telegram review."""
    evidence = evidence_for_prospect(prospect_id)
    draft = asyncio.run(generate_partnership_draft(prospect=prospect, contact=contact, evidence=evidence, score=scores))
    if not draft:
        return False
    draft_id = create_draft(
        opportunity_id=opportunity_id,
        contact_id=int(contact["id"]),
        subject=draft["subject"],
        body=draft["body"],
        evidence_ids=[int(item["id"]) for item in evidence],
        model=draft.get("model"),
    )
    if not draft_id:
        return False
    score = int(scores["overall_score"])
    if score >= auto_send_threshold():
        try:
            result = auto_send_draft(draft_id)
            notify_auto_delivery(draft_id=draft_id, prospect_name=str(prospect["name"]), score=score, status=str(result.get("status") or "unknown"))
        except Exception as exc:
            notify_auto_delivery(draft_id=draft_id, prospect_name=str(prospect["name"]), score=score, status=f"delivery_failed: {str(exc)[:80]}")
    else:
        notify_draft_for_approval(draft_id=draft_id, prospect_name=str(prospect["name"]), score=score, email=str(contact["email"]))
    return True


def _research_github_candidates() -> dict[str, int]:
    """Add public GitHub project evidence and research only any linked official website."""
    seen = qualified = drafts = 0
    for candidate in discover_web3_repositories(limit=github_max_results()):
        try:
            prospect_id = upsert_prospect(
                pipeline=PIPELINE,
                name=candidate["name"],
                domain=candidate["domain"],
                website_url=candidate["website_url"],
                category=candidate["category"],
                summary=candidate["summary"],
            )
            seen += 1
            add_evidence(prospect_id, source_url=candidate["github_url"], claim_type="github_repository", excerpt=f"{candidate['name']} | stars: {candidate['stars']} | topics: {', '.join(candidate['topics'])}", confidence=0.75)
            page: dict[str, Any] | None = None
            if candidate["website_url"] != candidate["github_url"]:
                try:
                    page = fetch_public_source(candidate["website_url"])
                    for email in page.get("emails", [])[:3]:
                        add_contact(prospect_id, email=email, source_url=page["url"])
                    for research_page in _contact_research_pages(page):
                        for email in research_page.get("emails", [])[:3]:
                            add_contact(prospect_id, email=email, source_url=research_page["url"])
                        if research_page.get("description"):
                            add_evidence(prospect_id, source_url=research_page["url"], claim_type="public_contact_page", excerpt=research_page["description"], confidence=0.8)
                except Exception:
                    page = None
            contact = first_contact(prospect_id)
            research_text = " ".join([candidate["summary"], " ".join(candidate["topics"]), str((page or {}).get("text") or "")])
            scores = score_partnership(category=candidate["category"], text=research_text, has_business_contact=bool(contact), relevant_links=list((page or {}).get("relevant_links") or []))
            opportunity_id = upsert_opportunity(prospect_id, scores)
            if contact:
                qualified += 1
                if _create_and_route_draft(
                    opportunity_id=opportunity_id,
                    prospect_id=prospect_id,
                    prospect={"id": prospect_id, "name": candidate["name"], "primary_domain": candidate["domain"], "category": candidate["category"], "summary": candidate["summary"], "website_url": candidate["website_url"]},
                    contact=contact,
                    scores=scores,
                ):
                    drafts += 1
        except Exception:
            continue
    return {"github_candidates": seen, "github_qualified": qualified, "github_drafts": drafts}


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
                if not contact:
                    continue
                qualified += 1
                prospect = {
                    "id": prospect_id,
                    "name": source["name"],
                    "primary_domain": page["domain"],
                    "category": source["category"],
                    "summary": _summary_from_page(page),
                    "website_url": page["url"],
                }
                if _create_and_route_draft(
                    opportunity_id=opportunity_id,
                    prospect_id=prospect_id,
                    prospect=prospect,
                    contact=contact,
                    scores=scores,
                ):
                    drafts_created += 1
            except Exception as exc:
                errors.append({"source": str(source.get("name") or source.get("url") or "unknown"), "error": str(exc)[:300]})

        try:
            github_summary = _research_github_candidates()
        except Exception as exc:
            github_summary = {"github_candidates": 0, "github_qualified": 0, "github_drafts": 0}
            errors.append({"source": "github_public_api", "error": str(exc)[:300]})
        try:
            investor_summary = sync_public_investor_catalog()
        except Exception as exc:
            investor_summary = {"cataloged": 0, "errors": [{"source": "investor_catalog", "error": str(exc)[:300]}]}
            errors.append({"source": "public_investor_catalog", "error": str(exc)[:300]})
        summary = {
            "status": "completed" if not errors else "completed_with_source_errors",
            "sources_checked": len(sources),
            "prospects_seen": seen + int(github_summary["github_candidates"]),
            "prospects_qualified": qualified + int(github_summary["github_qualified"]),
            "drafts_created": drafts_created + int(github_summary["github_drafts"]),
            "errors": errors,
            **github_summary,
            "investors_cataloged": int(investor_summary.get("cataloged") or 0),
            "investor_source_errors": len(investor_summary.get("errors") or []),
        }
        finish_run(run_id, status=summary["status"], sources_checked=len(sources), prospects_seen=int(summary["prospects_seen"]), prospects_qualified=int(summary["prospects_qualified"]), drafts_created=int(summary["drafts_created"]), details=summary)
        notify_partnership_run(run_id, summary)
        return {"run_id": run_id, **summary}
    except Exception as exc:
        summary = {"status": "failed", "sources_checked": len(sources), "prospects_seen": seen, "prospects_qualified": qualified, "drafts_created": drafts_created, "errors": errors + [{"source": "pipeline", "error": str(exc)[:300]}]}
        finish_run(run_id, status="failed", sources_checked=len(sources), prospects_seen=seen, prospects_qualified=qualified, drafts_created=drafts_created, details=summary, error=str(exc))
        notify_partnership_run(run_id, summary)
        return {"run_id": run_id, **summary}
