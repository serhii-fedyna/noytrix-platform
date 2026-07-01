from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import urlparse


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_host(value: str) -> str:
    x = str(value or "").strip()
    if "://" not in x:
        x = "https://" + x
    host = urlparse(x).netloc or urlparse(x).path
    host = host.split("@")[-1].split(":")[0].strip(".").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _to_datetime(value: Any) -> datetime | None:
    if isinstance(value, list):
        value = next((x for x in value if x), None)

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if isinstance(value, str):
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(value[:19], fmt).replace(tzinfo=timezone.utc)
            except Exception:
                pass

    return None


def analyze_domain_age(value: str) -> Dict[str, Any]:
    host = _normalize_host(value)

    if not host or "." not in host:
        return {
            "available": False,
            "reason": "invalid_domain",
            "host": host,
            "score": 0,
            "level": "unknown",
            "signals": [],
        }

    try:
        import whois
        raw = whois.whois(host)
    except Exception as e:
        return {
            "available": False,
            "reason": str(e)[:300],
            "host": host,
            "score": 0,
            "level": "unknown",
            "signals": [],
        }

    created = _to_datetime(getattr(raw, "creation_date", None) or raw.get("creation_date") if isinstance(raw, dict) else None)
    updated = _to_datetime(getattr(raw, "updated_date", None) or raw.get("updated_date") if isinstance(raw, dict) else None)
    expires = _to_datetime(getattr(raw, "expiration_date", None) or raw.get("expiration_date") if isinstance(raw, dict) else None)

    now = _now()

    age_days = None
    if created:
        age_days = max(0, int((now - created).total_seconds() // 86400))

    expires_in_days = None
    if expires:
        expires_in_days = int((expires - now).total_seconds() // 86400)

    signals = []
    score = 0

    crypto_words = [
        "airdrop", "claim", "bonus", "swap", "bridge", "wallet",
        "connect", "defi", "dex", "staking", "reward", "token",
        "presale", "mint", "verify", "secure"
    ]

    has_crypto_word = any(w in host for w in crypto_words)

    if age_days is not None:
        if age_days <= 3:
            score += 45
            signals.append({"code": "very_new_domain", "severity": 45, "text": "Domain was created within the last 3 days."})
        elif age_days <= 14:
            score += 35
            signals.append({"code": "new_domain", "severity": 35, "text": "Domain is younger than 14 days."})
        elif age_days <= 60:
            score += 20
            signals.append({"code": "young_domain", "severity": 20, "text": "Domain is younger than 60 days."})

    if has_crypto_word and age_days is not None and age_days <= 60:
        score += 25
        signals.append({"code": "young_crypto_domain", "severity": 25, "text": "Young domain contains crypto-related wording."})

    if expires_in_days is not None and expires_in_days <= 45:
        score += 10
        signals.append({"code": "short_expiry_window", "severity": 10, "text": "Domain expiration is close."})

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
        "host": host,
        "created_at": created.isoformat() if created else None,
        "updated_at": updated.isoformat() if updated else None,
        "expires_at": expires.isoformat() if expires else None,
        "age_days": age_days,
        "expires_in_days": expires_in_days,
        "has_crypto_word": has_crypto_word,
        "score": score,
        "level": level,
        "signals": signals,
    }
