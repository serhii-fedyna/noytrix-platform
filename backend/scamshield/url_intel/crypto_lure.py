from __future__ import annotations

import re
from typing import Any, Dict, List


LURE_PATTERNS = [
    {
        "code": "airdrop_claim_lure",
        "severity": 40,
        "patterns": [
            r"\bairdrop\b",
            r"\bclaim\b",
            r"claim your",
            r"claim now",
            r"claim reward",
            r"claim tokens?",
            r"claim allocation",
        ],
        "text": "Page contains airdrop/claim lure wording.",
    },
    {
        "code": "free_crypto_lure",
        "severity": 35,
        "patterns": [
            r"free crypto",
            r"free tokens?",
            r"free usdt",
            r"free eth",
            r"free btc",
            r"bonus tokens?",
            r"reward pool",
        ],
        "text": "Page promises free crypto or reward-like benefits.",
    },
    {
        "code": "urgency_lure",
        "severity": 25,
        "patterns": [
            r"limited time",
            r"last chance",
            r"only today",
            r"ends soon",
            r"before it expires",
            r"act now",
            r"verify now",
        ],
        "text": "Page uses urgency or pressure wording.",
    },
    {
        "code": "wallet_verification_lure",
        "severity": 45,
        "patterns": [
            r"verify wallet",
            r"wallet verification",
            r"validate wallet",
            r"sync wallet",
            r"rectify wallet",
            r"restore wallet",
            r"secure your wallet",
        ],
        "text": "Page contains wallet verification or wallet-fix wording.",
    },
    {
        "code": "guaranteed_profit_lure",
        "severity": 55,
        "patterns": [
            r"guaranteed profit",
            r"guaranteed return",
            r"risk[- ]?free",
            r"\b\d{2,4}%\b",
            r"\+\s?\d{2,4}\s?%",
        ],
        "text": "Page contains unrealistic guaranteed profit wording.",
    },
]


def _hits(text: str, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    low = str(text or "").lower()
    out = []

    for block in blocks:
        matched = []
        for pat in block.get("patterns") or []:
            if re.search(pat, low, re.IGNORECASE):
                matched.append(pat)

        if matched:
            out.append({
                "code": block["code"],
                "severity": int(block["severity"]),
                "text": block["text"],
                "matches": matched[:8],
            })

    return out


def analyze_crypto_lure(visible_text: str, html: str = "", host: str = "") -> Dict[str, Any]:
    text = f"{visible_text or ''}\n{html or ''}"
    signals = _hits(text, LURE_PATTERNS)

    codes = {x.get("code") for x in signals}
    score = 0

    for sig in signals:
        score = max(score, int(sig.get("severity") or 0))

    if "airdrop_claim_lure" in codes and "wallet_verification_lure" in codes:
        score = max(score, 75)
        signals.append({
            "code": "claim_plus_wallet_verification",
            "severity": 75,
            "text": "Page combines reward claiming with wallet verification wording.",
            "matches": [],
        })

    if "airdrop_claim_lure" in codes and "urgency_lure" in codes:
        score = max(score, 65)
        signals.append({
            "code": "claim_plus_urgency",
            "severity": 65,
            "text": "Page combines reward claiming with urgency pressure.",
            "matches": [],
        })

    if "guaranteed_profit_lure" in codes and ("free_crypto_lure" in codes or "airdrop_claim_lure" in codes):
        score = max(score, 80)
        signals.append({
            "code": "profit_plus_reward_lure",
            "severity": 80,
            "text": "Page combines unrealistic profit/reward promises.",
            "matches": [],
        })

    suspicious_host_words = ["claim", "airdrop", "bonus", "reward", "verify", "wallet"]
    if any(w in str(host or "").lower() for w in suspicious_host_words):
        score = max(score, min(100, score + 10))
        signals.append({
            "code": "lure_word_in_domain",
            "severity": 10,
            "text": "Domain contains crypto lure wording.",
            "matches": [],
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
            "Crypto lure or fake-claim wording detected."
            if score >= 40 else
            "No strong crypto lure wording detected."
        ),
    }
