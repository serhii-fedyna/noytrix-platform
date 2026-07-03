from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import urlparse


LEGITIMATE_PLATFORM_ROOTS = {
    "github.io",
    "pages.dev",
    "vercel.app",
    "netlify.app",
    "firebaseapp.com",
    "web.app",
}

SUSPICIOUS_PATH_WORDS = {
    "claim",
    "airdrop",
    "bonus",
    "reward",
    "mint",
    "verify",
    "wallet",
    "connect",
    "gift",
    "whitelist",
    "presale",
    "login",
    "support",
}


def _level(score: int) -> str:
    if score >= 90:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    if score > 0:
        return "low"
    return "safe"


def _root(host: str) -> str:
    parts = [p for p in str(host or "").lower().strip(".").split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else str(host or "").lower().strip(".")


def _host(url: str) -> str:
    try:
        return (urlparse(str(url or "")).hostname or "").lower().strip(".")
    except Exception:
        return ""


def _path_text(url: str) -> str:
    try:
        parsed = urlparse(str(url or ""))
        return f"{parsed.path} {parsed.query}".lower()
    except Exception:
        return ""


def _signals_from(*objects: Dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for obj in objects:
        for sig in (obj or {}).get("signals") or []:
            if isinstance(sig, dict) and sig.get("code"):
                out.add(str(sig.get("code")).lower())
    return out


def _score_of(obj: Dict[str, Any] | None) -> int:
    try:
        return int((obj or {}).get("score") or 0)
    except Exception:
        return 0


def _add(signals: List[Dict[str, Any]], code: str, severity: int, text: str, **extra: Any) -> None:
    item = {
        "code": code,
        "severity": max(0, min(100, int(severity))),
        "text": text,
    }
    item.update(extra)
    signals.append(item)


def analyze_compromised_legitimate_site(
    url: str,
    host: str,
    *,
    domain_age: Dict[str, Any] | None = None,
    redirect_chain: Dict[str, Any] | None = None,
    wallet_trap: Dict[str, Any] | None = None,
    crypto_lure: Dict[str, Any] | None = None,
    js_behavior: Dict[str, Any] | None = None,
    headless_sandbox: Dict[str, Any] | None = None,
    js_obfuscation: Dict[str, Any] | None = None,
    visual_phishing: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    host = str(host or _host(url)).lower().strip(".")
    root = _root(host)
    age_days = (domain_age or {}).get("age_days")
    try:
        age_days_int = int(age_days) if age_days is not None else None
    except Exception:
        age_days_int = None

    old_domain = bool(age_days_int is not None and age_days_int >= 365)
    platform_root = root in LEGITIMATE_PLATFORM_ROOTS
    known_legitimate_context = old_domain or platform_root

    signals: List[Dict[str, Any]] = []
    path = _path_text(url)
    suspicious_path_words = sorted(w for w in SUSPICIOUS_PATH_WORDS if w in path)
    codes = _signals_from(wallet_trap or {}, crypto_lure or {}, js_behavior or {}, headless_sandbox or {}, js_obfuscation or {}, visual_phishing or {})

    wallet_runtime = bool(codes & {
        "runtime_approval_or_drain_flow",
        "runtime_connect_plus_signature_flow",
        "runtime_connect_plus_transaction_flow",
        "possible_js_drainer_flow",
        "approval_or_drain_functions",
        "obfuscated_wallet_drainer_javascript",
        "runtime_wallet_calls_with_obfuscation",
        "credential_theft_ui",
        "seed_phrase_request",
        "private_key_request",
        "recovery_phrase_request",
    })

    lure_context = bool(codes & {
        "connect_wallet_reward_flow",
        "fake_airdrop_bonus_ui",
        "wallet_connect_pressure",
        "brand_impersonation_plus_wallet_pressure",
        "brand_plus_scam_keywords",
    }) or bool(suspicious_path_words)

    redirect = redirect_chain or {}
    redirect_roots = redirect.get("unique_root_domains") or []
    final_host = str(redirect.get("final_host") or "").lower()
    final_root = _root(final_host)
    cross_root_redirect = bool(len(redirect_roots) >= 2 and final_root and final_root != root)

    if known_legitimate_context:
        _add(
            signals,
            "legitimate_domain_context",
            0,
            "Domain has legitimate context; compromise detection requires fresh malicious behavior.",
            age_days=age_days_int,
            platform_root=platform_root,
        )

    if known_legitimate_context and suspicious_path_words:
        _add(
            signals,
            "legitimate_domain_suspicious_path",
            35,
            "Legitimate/old domain is serving a suspicious crypto or account-action path.",
            words=suspicious_path_words[:10],
        )

    if known_legitimate_context and cross_root_redirect and lure_context:
        _add(
            signals,
            "compromised_legitimate_redirect_to_lure",
            82,
            "Legitimate/old domain redirects across roots into a lure-like flow.",
            final_host=final_host,
        )

    if known_legitimate_context and wallet_runtime:
        _add(
            signals,
            "compromised_legitimate_site_wallet_flow",
            92,
            "Legitimate/old domain shows wallet-drainer, credential theft, or dangerous runtime behavior.",
        )

    if known_legitimate_context and _score_of(js_obfuscation) >= 70 and (wallet_runtime or lure_context):
        _add(
            signals,
            "legitimate_domain_obfuscated_wallet_flow",
            88,
            "Legitimate/old domain combines obfuscated JavaScript with wallet or lure behavior.",
        )

    if platform_root and (wallet_runtime or _score_of(wallet_trap) >= 75):
        _add(
            signals,
            "hosted_platform_abuse_wallet_flow",
            86,
            "A hosted platform page shows wallet-drainer or credential-theft behavior.",
            platform_root=root,
        )

    score = max([int(s.get("severity") or 0) for s in signals] or [0])
    return {
        "available": True,
        "score": score,
        "level": _level(score),
        "host": host,
        "root_domain": root,
        "known_legitimate_context": known_legitimate_context,
        "old_domain": old_domain,
        "platform_root": platform_root,
        "suspicious_path_words": suspicious_path_words,
        "signals": sorted(signals, key=lambda x: int(x.get("severity") or 0), reverse=True),
        "summary": (
            "Possible compromised legitimate site behavior detected."
            if score >= 70 else
            "No confirmed compromised legitimate site behavior detected."
        ),
    }
