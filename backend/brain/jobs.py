from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone
from typing import Any
from urllib.parse import urlparse

from .candidate import CANDIDATE, resume_is_ready
from .config import JOB_SOURCES_PATH, jobs_auto_send_threshold, jobs_daily_auto_send_limit, jobs_max_sources_per_run
from .discovery import career_page_urls, fetch_public_source, is_public_recruiting_email, load_sources
from .job_scoring import score_job
from .job_writer import generate_job_application_draft
from .outreach import auto_send_draft
from .reports import notify_draft_for_approval
from .repository import (
    active_sources, add_contact, add_evidence, create_draft, create_run, evidence_for_prospect,
    finish_run, first_contact, mark_source_run, sent_count_since, sync_sources,
    upsert_opportunity, upsert_prospect,
)


PIPELINE = "serhii_job_search"


def _same_organisation_email(email: str, domain: str) -> bool:
    email_domain = str(email or "").rsplit("@", 1)[-1].lower().removeprefix("www.")
    clean_domain = str(domain or "").lower().removeprefix("www.")
    return bool(clean_domain and (email_domain == clean_domain or email_domain.endswith("." + clean_domain)))


def _deliverable_recruiting_email(email: str, domain: str) -> bool:
    """Validate syntax and receiving domain. Inbox ownership is confirmed only by responses/bounces."""
    if not is_public_recruiting_email(email) or not _same_organisation_email(email, domain):
        return False
    try:
        from email_validator import EmailNotValidError, validate_email
        try:
            validate_email(email, check_deliverability=True)
        except EmailNotValidError:
            return False
    except ImportError:
        return False
    return True


def _summary(page: dict[str, Any]) -> str:
    return str(page.get("description") or page.get("title") or page.get("text") or "")[:1200]


def _career_research_pages(page: dict[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for link in career_page_urls(page, limit=limit):
        try:
            pages.append(fetch_public_source(link))
        except Exception:
            continue
    return pages


def _today_start() -> str:
    return datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc).isoformat()


def _route_draft(*, opportunity_id: int, prospect_id: int, prospect: dict[str, Any], contact: dict[str, Any], scores: dict[str, Any]) -> bool:
    evidence = evidence_for_prospect(prospect_id)
    draft = asyncio.run(generate_job_application_draft(company=prospect, contact=contact, evidence=evidence, score=scores))
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
    within_daily_cap = sent_count_since(pipeline=PIPELINE, start_at=_today_start()) < jobs_daily_auto_send_limit()
    if score >= jobs_auto_send_threshold() and within_daily_cap:
        try:
            auto_send_draft(draft_id)
        except Exception:
            pass
    else:
        notify_draft_for_approval(
            draft_id=draft_id,
            prospect_name=str(prospect["name"]),
            score=score,
            email=str(contact["email"]),
            kind="job",
        )
    return True


def run_job_pipeline(*, limit: int | None = None) -> dict[str, Any]:
    """Research public technical vacancies and email only verified published HR inboxes."""
    if not resume_is_ready():
        return {"status": "blocked", "reason": "candidate_resume_not_available", "sources_checked": 0, "prospects_seen": 0, "prospects_qualified": 0, "drafts_created": 0}
    sync_sources(load_sources(JOB_SOURCES_PATH))
    sources = active_sources(limit or jobs_max_sources_per_run(), source_type="job_board")
    run_id = create_run(PIPELINE)
    errors: list[dict[str, str]] = []
    seen = qualified = drafts = 0
    try:
        for source in sources:
            try:
                root_page = fetch_public_source(str(source["url"]))
                mark_source_run(int(source["id"]))
                pages = [root_page, *_career_research_pages(root_page)]
                evidence_text = " ".join(
                    " ".join(str(item.get(key) or "") for key in ("title", "description", "text")) for item in pages
                )
                has_apply_route = bool(root_page.get("career_links")) or len(pages) > 1
                prospect_id = upsert_prospect(
                    pipeline=PIPELINE,
                    name=str(source["name"]),
                    domain=str(root_page["domain"]),
                    website_url=str(root_page["url"]),
                    category="technical_job",
                    summary=_summary(root_page),
                )
                seen += 1
                for page in pages:
                    add_evidence(prospect_id, source_url=str(page["url"]), claim_type="official_careers_page", excerpt=_summary(page), confidence=0.85)
                    for email in page.get("recruiting_emails", [])[:4]:
                        if _deliverable_recruiting_email(email, str(root_page["domain"])):
                            add_contact(
                                prospect_id,
                                email=email,
                                source_url=str(page["url"]),
                                role="recruiting_contact",
                                contact_basis="published_recruiting_contact_mx_verified",
                            )
                contact = first_contact(prospect_id, role="recruiting_contact")
                scores = score_job(
                    text=evidence_text,
                    has_verified_recruiting_contact=bool(contact),
                    has_apply_route=has_apply_route,
                )
                opportunity_id = upsert_opportunity(prospect_id, scores)
                if not contact or scores["decision"] == "researching":
                    continue
                qualified += 1
                prospect = {
                    "id": prospect_id, "name": source["name"], "primary_domain": root_page["domain"],
                    "category": "technical_job", "summary": _summary(root_page), "website_url": root_page["url"],
                }
                if _route_draft(opportunity_id=opportunity_id, prospect_id=prospect_id, prospect=prospect, contact=contact, scores=scores):
                    drafts += 1
            except Exception as exc:
                errors.append({"source": str(source.get("name") or source.get("url") or "unknown"), "error": str(exc)[:300]})
        summary = {
            "status": "completed" if not errors else "completed_with_source_errors",
            "candidate": CANDIDATE["name"],
            "sources_checked": len(sources), "prospects_seen": seen,
            "prospects_qualified": qualified, "drafts_created": drafts, "errors": errors,
        }
        finish_run(run_id, status=summary["status"], sources_checked=len(sources), prospects_seen=seen, prospects_qualified=qualified, drafts_created=drafts, details=summary)
        return {"run_id": run_id, **summary}
    except Exception as exc:
        summary = {"status": "failed", "sources_checked": len(sources), "prospects_seen": seen, "prospects_qualified": qualified, "drafts_created": drafts, "errors": errors + [{"source": "job_pipeline", "error": str(exc)[:300]}]}
        finish_run(run_id, status="failed", sources_checked=len(sources), prospects_seen=seen, prospects_qualified=qualified, drafts_created=drafts, details=summary, error=str(exc))
        return {"run_id": run_id, **summary}
