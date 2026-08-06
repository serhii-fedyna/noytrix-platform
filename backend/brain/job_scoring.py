from __future__ import annotations

from typing import Any


STRONG_ROLE_TERMS = (
    "full stack", "full-stack", "backend engineer", "backend developer", "software engineer",
    "python developer", "python engineer", "fastapi", "ai engineer", "llm engineer",
    "machine learning engineer", "founding engineer", "platform engineer",
)
DOMAIN_TERMS = ("web3", "crypto", "blockchain", "wallet", "defi", "security", "fintech")
SKILL_TERMS = ("python", "fastapi", "postgres", "docker", "api", "llm", "ai", "machine learning")


def _contains(text: str, terms: tuple[str, ...]) -> list[str]:
    lowered = str(text or "").lower()
    return [term for term in terms if term in lowered]


def score_job(*, text: str, has_verified_recruiting_contact: bool, has_apply_route: bool) -> dict[str, Any]:
    """Score only explicit, evidence-backed job-role compatibility."""
    role_matches = _contains(text, STRONG_ROLE_TERMS)
    domain_matches = _contains(text, DOMAIN_TERMS)
    skill_matches = _contains(text, SKILL_TERMS)
    remote = _contains(text, ("remote", "europe", "ukraine", "distributed"))

    fit = min(95, 35 + 18 * min(3, len(role_matches)) + 6 * min(3, len(skill_matches)))
    technical = min(95, 35 + 11 * min(5, len(skill_matches)))
    revenue = min(80, 45 + 8 * min(3, len(domain_matches)))
    timing = 75 if has_apply_route else 35
    if remote:
        timing = min(90, timing + 10)
    contact = 85 if has_verified_recruiting_contact else 20
    rationale = []
    if role_matches:
        rationale.append("Explicit role-match terms: " + ", ".join(role_matches[:4]) + ".")
    else:
        rationale.append("No explicit matching engineering role was found on the reviewed public page.")
    if skill_matches:
        rationale.append("Relevant technical terms: " + ", ".join(skill_matches[:5]) + ".")
    if has_apply_route:
        rationale.append("A public job or application route is available.")
    else:
        rationale.append("No public application route was found; sending is blocked.")
    if has_verified_recruiting_contact:
        rationale.append("A public generic recruiting inbox passed domain deliverability checks.")
    else:
        rationale.append("No verified published recruiting inbox was found; sending is blocked.")

    overall = round(0.38 * fit + 0.22 * technical + 0.15 * revenue + 0.10 * timing + 0.15 * contact)
    if not role_matches or not has_apply_route or not has_verified_recruiting_contact:
        decision = "researching"
    elif overall >= 80:
        decision = "automatic_delivery"
    else:
        decision = "manual_review"
    return {
        "fit_score": fit,
        "revenue_score": revenue,
        "technical_score": technical,
        "timing_score": timing,
        "contact_score": contact,
        "risk_penalty": 0,
        "overall_score": max(0, min(100, overall)),
        "decision": decision,
        "rationale": rationale,
    }
