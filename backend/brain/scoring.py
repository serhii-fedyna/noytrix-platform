from __future__ import annotations

from typing import Any


PARTNERSHIP_CATEGORIES = {"wallet", "wallet_infrastructure", "wallet_security", "security", "blockchain_analytics", "exchange", "defi", "launchpad", "web3", "saas"}


def _contains(text: str, *phrases: str) -> bool:
    low = text.lower()
    return any(phrase in low for phrase in phrases)


def score_partnership(*, category: str, text: str, has_business_contact: bool, relevant_links: list[str]) -> dict[str, Any]:
    fit = 82 if category in PARTNERSHIP_CATEGORIES else 55
    technical = 45
    timing = 45
    revenue = 55
    contact = 70 if has_business_contact else 25
    rationale: list[str] = []

    if _contains(text, "api", "developer", "developers", "sdk", "integration") or any("api" in link.lower() or "developer" in link.lower() or "docs" in link.lower() for link in relevant_links):
        technical = 82
        rationale.append("Public API, developer, documentation, or integration evidence is available.")
    else:
        rationale.append("No public API or integration evidence was found on the reviewed source page.")
    if _contains(text, "partner", "partnership", "ecosystem", "collaboration") or any("partner" in link.lower() for link in relevant_links):
        timing = 75
        rationale.append("The source exposes partnership or ecosystem signals.")
    if category in {"wallet", "wallet_security", "security", "blockchain_analytics"}:
        revenue = 75
        rationale.append("The category has direct alignment with Noytrix crypto-security capabilities.")
    if has_business_contact:
        rationale.append("A public business contact method was found.")
    else:
        rationale.append("No verified public business email was found; research can continue but outreach is blocked.")

    risk_penalty = 0
    overall = round(0.30 * fit + 0.20 * technical + 0.20 * revenue + 0.15 * timing + 0.15 * contact - risk_penalty)
    decision = "ready_for_review" if overall >= 65 and has_business_contact else "researching"
    return {
        "fit_score": fit,
        "revenue_score": revenue,
        "technical_score": technical,
        "timing_score": timing,
        "contact_score": contact,
        "risk_penalty": risk_penalty,
        "overall_score": max(0, min(100, overall)),
        "decision": decision,
        "rationale": rationale,
    }
