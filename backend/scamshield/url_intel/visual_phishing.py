from __future__ import annotations

import re
from typing import Any, Dict, List


TRUSTED_BRANDS = [
    "binance", "coinbase", "metamask", "trust wallet", "phantom",
    "okx", "bybit", "kraken", "uniswap", "pancakeswap",
    "opensea", "ledger", "trezor", "walletconnect"
]



OFFICIAL_BRAND_DOMAINS = {
    "binance": ["binance.com"],
    "coinbase": ["coinbase.com"],
    "metamask": ["metamask.io"],
    "trustwallet": ["trustwallet.com"],
    "phantom": ["phantom.app"],
    "okx": ["okx.com"],
    "bybit": ["bybit.com"],
    "kraken": ["kraken.com"],
    "uniswap": ["uniswap.org"],
    "pancakeswap": ["pancakeswap.finance"],
    "opensea": ["opensea.io"],
    "ledger": ["ledger.com"],
    "trezor": ["trezor.io"],
    "walletconnect": ["walletconnect.com"],
}


COPY_PATTERNS = [
    {
        "code": "fake_exchange_ui",
        "severity": 45,
        "patterns": [
            r"\blogin\b.*\bexchange\b",
            r"\btrading account\b",
            r"\bwithdraw\b.*\bverify\b",
            r"\bdeposit\b.*\bbonus\b",
            r"\bkyc\b.*\bwallet\b",
        ],
        "text": "Page copy resembles fake exchange/login flow.",
    },
    {
        "code": "fake_support_ui",
        "severity": 55,
        "patterns": [
            r"\bsupport\b.*\bwallet\b",
            r"\bvalidate\b.*\bwallet\b",
            r"\bsync\b.*\bwallet\b",
            r"\brectify\b.*\bwallet\b",
            r"\brecover\b.*\bwallet\b",
        ],
        "text": "Page copy resembles fake wallet support/recovery flow.",
    },
    {
        "code": "fake_airdrop_bonus_ui",
        "severity": 55,
        "patterns": [
            r"\bclaim\b.*\bairdrop\b",
            r"\bclaim\b.*\breward\b",
            r"\bbonus\b.*\busdt\b",
            r"\bfree\b.*\btoken\b",
            r"\beligible\b.*\bclaim\b",
        ],
        "text": "Page copy resembles fake airdrop/bonus claim flow.",
    },
    {
        "code": "wallet_connect_pressure",
        "severity": 60,
        "patterns": [
            r"\bconnect\b.*\bwallet\b.*\bclaim\b",
            r"\bconnect\b.*\bwallet\b.*\bverify\b",
            r"\bconnect\b.*\bwallet\b.*\breward\b",
            r"\bconnect\b.*\bwallet\b.*\bunlock\b",
        ],
        "text": "Page pressures user to connect wallet for claim/verification/reward.",
    },
    {
        "code": "cloned_ui_fingerprint",
        "severity": 35,
        "patterns": [
            r"\ball rights reserved\b",
            r"\bprivacy policy\b.*\bterms\b",
            r"\bconnect wallet\b.*\bterms\b",
            r"\bpowered by\b.*\bwallet\b",
        ],
        "text": "Page has generic cloned landing-page fingerprints.",
    },
]


def _host_words(host: str) -> List[str]:
    h = str(host or "").lower()
    h = h.replace("-", " ").replace(".", " ")
    return [x.strip() for x in h.split() if x.strip()]


def _hits(text: str, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    low = str(text or "").lower()
    out = []

    for block in blocks:
        matched = []
        for pat in block.get("patterns") or []:
            if re.search(pat, low, re.IGNORECASE | re.DOTALL):
                matched.append(pat)

        if matched:
            out.append({
                "code": block["code"],
                "severity": int(block["severity"]),
                "text": block["text"],
                "matches": matched[:8],
            })

    return out


def analyze_visual_phishing(html: str, visible_text: str = "", host: str = "", title: str = "") -> Dict[str, Any]:
    html = str(html or "")
    visible_text = str(visible_text or "")
    host = str(host or "").lower()
    title = str(title or "")

    full_text = f"{title}\n{visible_text}\n{html}"
    signals = _hits(full_text, COPY_PATTERNS)

    host_tokens = _host_words(host)
    text_low = full_text.lower()

    for brand in TRUSTED_BRANDS:
        brand_key = brand.lower()
        brand_compact = brand_key.replace(" ", "")

        brand_in_text = brand_key in text_low or brand_compact in text_low
        brand_in_host = brand_compact in host.replace("-", "").replace(".", "")


        if brand_in_host:
            allowed = OFFICIAL_BRAND_DOMAINS.get(brand_compact, [brand_compact + ".com"])

            exact_domain_ok = False
            for d in allowed:
                if host == d or host.endswith("." + d):
                    exact_domain_ok = True
                    break

            if not exact_domain_ok:
                signals.append({
                    "code": "brand_fragment_in_suspicious_domain",
                    "severity": 55,
                    "text": f"Domain contains trusted brand fragment '{brand}' but does not match the official root domain.",
                    "brand": brand,
                })

    if "connect" in text_low and "wallet" in text_low and ("claim" in text_low or "reward" in text_low or "bonus" in text_low):
        signals.append({
            "code": "connect_wallet_reward_flow",
            "severity": 75,
            "text": "Page combines wallet connection with reward/claim/bonus flow.",
        })

    if "seed phrase" in text_low or "private key" in text_low or "recovery phrase" in text_low:
        signals.append({
            "code": "credential_theft_ui",
            "severity": 95,
            "text": "Page appears to request seed phrase/private key/recovery phrase.",
        })

    score = 0
    for sig in signals:
        score = max(score, int(sig.get("severity") or 0))

    sources = {s.get("code") for s in signals}
    if "brand_name_in_page_not_domain" in sources and "wallet_connect_pressure" in sources:
        score = max(score, 85)
        signals.append({
            "code": "brand_impersonation_plus_wallet_pressure",
            "severity": 85,
            "text": "Page combines brand impersonation with wallet connection pressure.",
        })

    score = min(100, score)

    level = (
        "critical" if score >= 90 else
        "high" if score >= 70 else
        "medium" if score >= 40 else
        "low" if score > 0 else
        "safe"
    )

    return {
        "available": True,
        "score": score,
        "level": level,
        "signals": signals,
        "summary": (
            "Visual/copy phishing indicators detected."
            if score >= 40 else
            "No strong visual/copy phishing indicators detected."
        ),
    }
