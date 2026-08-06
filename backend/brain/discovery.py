from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

try:
    from bs4 import BeautifulSoup
except ImportError:  # Keep the discovery worker usable in minimal deployments.
    BeautifulSoup = None


BUSINESS_LOCAL_PARTS = {
    "hello", "contact", "partnerships", "partnership", "partner", "partners",
    "business", "sales", "bd", "bizdev", "growth", "ecosystem", "alliances",
    "support", "info", "team", "marketing", "community",
}
RECRUITING_LOCAL_PARTS = {
    "careers", "career", "jobs", "job", "recruiting", "recruitment", "talent",
    "hiring", "hr", "people", "workwithus", "work-with-us",
}
EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}(?![\w.-])", re.I)
CONTACT_PATHS = (
    "/contact", "/contact-us", "/partnerships", "/partners", "/ecosystem",
    "/business", "/about", "/company",
)
CAREER_PATHS = (
    "/careers", "/career", "/jobs", "/job-openings", "/vacancies", "/work-with-us",
)


class _MinimalHtmlCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.description = ""
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._in_title = False
        self._link_href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
        elif tag.lower() == "meta" and values.get("name", "").lower() == "description":
            self.description = values.get("content", "")
        elif tag.lower() == "meta" and values.get("property", "").lower() == "og:description" and not self.description:
            self.description = values.get("content", "")
        elif tag.lower() == "a" and values.get("href"):
            self._link_href = values["href"]
            self._link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
        elif tag.lower() == "a" and self._link_href:
            self.links.append((self._link_href, " ".join(self._link_text)))
            self._link_href = None
            self._link_text = []

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)
        if self._in_title:
            self.title += data
        if self._link_href:
            self._link_text.append(data)


def load_sources(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("brain sources must be a list")
    result = []
    for item in raw:
        url = str(item.get("url") or "").strip()
        if not url.startswith("https://"):
            continue
        result.append({
            "source_key": str(item.get("source_key") or urlparse(url).netloc).lower(),
            "name": str(item.get("name") or urlparse(url).netloc),
            "url": url,
            "category": str(item.get("category") or "web3"),
            "source_type": str(item.get("source_type") or "website"),
        })
    return result


def _clean(value: str, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def is_public_business_email(value: str) -> bool:
    """Accept only generic corporate inboxes published by the organisation."""
    local, separator, domain = str(value or "").strip().lower().partition("@")
    return bool(separator and domain and local in BUSINESS_LOCAL_PARTS)


def is_public_recruiting_email(value: str) -> bool:
    """Only accept a published generic recruitment inbox; never infer a person's address."""
    local, separator, domain = str(value or "").strip().lower().partition("@")
    return bool(separator and domain and local in RECRUITING_LOCAL_PARTS)


def contact_page_urls(page: dict[str, Any], *, limit: int = 10) -> list[str]:
    """Bounded same-site contact research; no guessed email addresses or profile scraping."""
    base_url = str(page.get("url") or "").strip()
    parsed_base = urlparse(base_url)
    domain = str(page.get("domain") or parsed_base.netloc).lower().removeprefix("www.")
    if not parsed_base.scheme or not parsed_base.netloc or not domain:
        return []

    candidates = list(page.get("relevant_links") or [])
    root = f"{parsed_base.scheme}://{parsed_base.netloc}"
    candidates.extend(urljoin(root, path) for path in CONTACT_PATHS)

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        parsed = urlparse(str(candidate))
        candidate_domain = parsed.netloc.lower().removeprefix("www.")
        normalized = parsed._replace(fragment="").geturl()
        if candidate_domain != domain or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def career_page_urls(page: dict[str, Any], *, limit: int = 10) -> list[str]:
    """Return only same-organisation pages that visibly relate to open roles."""
    base_url = str(page.get("url") or "").strip()
    parsed_base = urlparse(base_url)
    domain = str(page.get("domain") or parsed_base.netloc).lower().removeprefix("www.")
    if not parsed_base.scheme or not parsed_base.netloc or not domain:
        return []
    root = f"{parsed_base.scheme}://{parsed_base.netloc}"
    candidates = list(page.get("career_links") or [])
    candidates.extend(urljoin(root, path) for path in CAREER_PATHS)
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        parsed = urlparse(str(candidate))
        normalized = parsed._replace(fragment="").geturl()
        if parsed.netloc.lower().removeprefix("www.") != domain or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def fetch_public_source(url: str, timeout: int = 12) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "NoytrixBrain/0.1 (+https://noytrix.com)"})
    with urlopen(request, timeout=timeout) as response:
        body = response.read(700_000)
        final_url = str(response.geturl() or url)
        content_type = str(response.headers.get("Content-Type") or "")
    if "html" not in content_type.lower() and b"<html" not in body[:400].lower():
        raise ValueError("source did not return HTML")
    html = body.decode("utf-8", errors="ignore")
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        title = _clean((soup.title.string if soup.title else "") or "", 240)
        desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        description = _clean(desc_tag.get("content", "") if desc_tag else "", 800)
        text = _clean(soup.get_text(" ", strip=True), 8000)
        raw_links = [(str(node.get("href") or "").strip(), _clean(node.get_text(" ", strip=True), 100).lower()) for node in soup.select("a[href]")]
    else:
        collector = _MinimalHtmlCollector()
        collector.feed(html)
        title = _clean(collector.title, 240)
        description = _clean(collector.description, 800)
        text = _clean(" ".join(collector.text_parts), 8000)
        raw_links = [(href.strip(), _clean(label, 100).lower()) for href, label in collector.links]
    # Keep the HTML source too: many organisations put a public mailbox only in
    # a mailto link or structured data, neither of which is always visible text.
    all_emails = sorted({item.lower() for item in EMAIL_RE.findall(f"{html}\n{text}")})
    emails = [item for item in all_emails if is_public_business_email(item)]
    recruiting_emails = [item for item in all_emails if is_public_recruiting_email(item)]
    links = []
    career_links = []
    for href, label in raw_links:
        href = urljoin(final_url, href)
        if href.startswith("mailto:"):
            email = href.split(":", 1)[1].split("?", 1)[0].strip().lower()
            if is_public_business_email(email):
                emails.append(email)
            if is_public_recruiting_email(email):
                recruiting_emails.append(email)
        elif href.startswith("http") and any(word in label or word in href.lower() for word in ("partner", "contact", "api", "developer", "docs")):
            links.append(href[:1000])
        if href.startswith("http") and any(word in label or word in href.lower() for word in ("career", "careers", "job", "jobs", "vacanc", "opening", "hiring", "work with us")):
            career_links.append(href[:1000])
    return {
        "url": final_url,
        "domain": urlparse(final_url).netloc.lower().removeprefix("www."),
        "title": title,
        "description": description,
        "text": text,
        "emails": sorted(set(emails)),
        "recruiting_emails": sorted(set(recruiting_emails)),
        "relevant_links": sorted(set(links))[:16],
        "career_links": sorted(set(career_links))[:16],
    }
