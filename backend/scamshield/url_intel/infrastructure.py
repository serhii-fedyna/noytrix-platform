from __future__ import annotations

from typing import Any, Dict, List
import ipaddress
import socket


def _resolve(host: str, record_type: str = "A") -> List[str]:
    try:
        import dns.resolver
        answers = dns.resolver.resolve(host, record_type, lifetime=4)
        return [str(x).strip() for x in answers]
    except Exception:
        return []


def _is_ip_private(ip: str) -> bool:
    try:
        obj = ipaddress.ip_address(ip)
        return obj.is_private or obj.is_loopback or obj.is_reserved or obj.is_multicast
    except Exception:
        return False


def analyze_infrastructure(host: str) -> Dict[str, Any]:
    host = str(host or "").strip().lower().strip(".")
    signals = []
    score = 0

    if not host or "." not in host:
        return {
            "available": False,
            "reason": "invalid_host",
            "host": host,
            "score": 0,
            "level": "unknown",
            "signals": [],
        }

    a_records = _resolve(host, "A")
    aaaa_records = _resolve(host, "AAAA")
    ns_records = _resolve(host, "NS")
    mx_records = _resolve(host, "MX")
    cname_records = _resolve(host, "CNAME")

    if not a_records and not aaaa_records:
        score += 35
        signals.append({
            "code": "dns_no_ip_records",
            "severity": 35,
            "text": "Domain has no resolvable A/AAAA IP records.",
        })

    private_ips = [ip for ip in a_records + aaaa_records if _is_ip_private(ip)]
    if private_ips:
        score += 50
        signals.append({
            "code": "private_or_reserved_ip",
            "severity": 50,
            "text": "Domain resolves to private/reserved IP space.",
        })

    if len(a_records) >= 8:
        score += 10
        signals.append({
            "code": "many_a_records",
            "severity": 10,
            "text": "Domain has many A records, which may indicate rotating infrastructure.",
        })

    if not ns_records:
        score += 15
        signals.append({
            "code": "missing_ns_records",
            "severity": 15,
            "text": "Domain NS records could not be resolved.",
        })

    host_words = host.replace("-", ".").split(".")
    suspicious_host_words = {"claim", "airdrop", "bonus", "reward", "verify", "wallet", "connect", "secure", "support"}
    matched_words = sorted(set(host_words) & suspicious_host_words)

    if matched_words:
        score += 15
        signals.append({
            "code": "suspicious_host_words",
            "severity": 15,
            "text": "Host contains scam-lure infrastructure wording.",
            "words": matched_words,
        })

    known_platform_hints = []
    joined = " ".join(ns_records + cname_records).lower()
    for name in ["cloudflare", "vercel", "netlify", "pages.dev", "workers.dev", "github", "firebase", "amazonaws"]:
        if name in joined:
            known_platform_hints.append(name)

    score = min(100, score)

    level = (
        "critical" if score >= 85 else
        "high" if score >= 60 else
        "medium" if score >= 35 else
        "low" if score > 0 else
        "safe"
    )

    return {
        "available": True,
        "host": host,
        "score": score,
        "level": level,
        "a_records": a_records[:20],
        "aaaa_records": aaaa_records[:20],
        "ns_records": ns_records[:20],
        "mx_records": mx_records[:20],
        "cname_records": cname_records[:20],
        "known_platform_hints": known_platform_hints,
        "signals": signals,
        "summary": (
            "Suspicious infrastructure signals detected."
            if score >= 35 else
            "No strong suspicious infrastructure signals detected."
        ),
    }
