from __future__ import annotations

import re
from typing import Any, Dict, List


PATTERNS = [
    {
        "code": "connect_wallet_prompt",
        "severity": 30,
        "patterns": [
            r"connect wallet",
            r"walletconnect",
            r"connect your wallet",
            r"подключ.*кошел",
            r"підключ.*гаманець",
        ],
        "text": "Page contains wallet connection prompts.",
    },
    {
        "code": "claim_airdrop_lure",
        "severity": 35,
        "patterns": [
            r"claim.*airdrop",
            r"airdrop.*claim",
            r"claim reward",
            r"claim tokens?",
            r"free tokens?",
            r"bonus reward",
        ],
        "text": "Page contains claim/airdrop reward lure wording.",
    },
    {
        "code": "signature_or_approval_wording",
        "severity": 40,
        "patterns": [
            r"approve transaction",
            r"sign message",
            r"sign.*wallet",
            r"permit2",
            r"setapprovalforall",
            r"token approval",
        ],
        "text": "Page contains signature or approval-related wording.",
    },
    {
        "code": "seed_phrase_request",
        "severity": 95,
        "patterns": [
            r"seed phrase",
            r"recovery phrase",
            r"private key",
            r"mnemonic",
            r"secret phrase",
        ],
        "text": "Page contains seed phrase/private key request wording.",
    },
    {
        "code": "urgent_crypto_pressure",
        "severity": 25,
        "patterns": [
            r"limited time",
            r"only today",
            r"act now",
            r"last chance",
            r"verify now",
            r"urgent",
        ],
        "text": "Page contains urgency or pressure wording.",
    },
]


SCRIPT_PATTERNS = [
    {
        "code": "web3_script_reference",
        "severity": 20,
        "patterns": [
            r"window\.ethereum",
            r"eth_requestaccounts",
            r"walletconnect",
            r"web3modal",
            r"ethers\.js",
            r"wagmi",
            r"rainbowkit",
        ],
        "text": "Page script references wallet/web3 connection libraries or APIs.",
    },
    {
        "code": "approval_function_reference",
        "severity": 45,
        "patterns": [
            r"approve\s*\(",
            r"setapprovalforall\s*\(",
            r"permit\s*\(",
            r"transferfrom\s*\(",
        ],
        "text": "Page script references approval or transfer functions.",
    },
]


def _find_patterns(text: str, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    low = str(text or "").lower()

    for block in blocks:
        hits = []
        for pat in block.get("patterns") or []:
            if re.search(pat, low, re.IGNORECASE):
                hits.append(pat)

        if hits:
            out.append({
                "code": block["code"],
                "severity": int(block["severity"]),
                "text": block["text"],
                "matches": hits[:5],
            })

    return out


def _has_secret_request_context(text: str) -> bool:
    text = str(text or "").lower()
    secret_terms = r"(seed phrase|secret phrase|recovery phrase|mnemonic|private key)"
    request_terms = r"(enter|input|submit|provide|paste|type|import|restore|verify|validate|sync|unlock|recover|confirm)"
    return bool(
        re.search(request_terms + r".{0,90}" + secret_terms, text, re.I | re.S)
        or re.search(secret_terms + r".{0,90}" + request_terms, text, re.I | re.S)
    )


def analyze_wallet_trap(html: str, visible_text: str = "") -> Dict[str, Any]:
    html = str(html or "")
    visible_text = str(visible_text or "")

    signals = []
    signals.extend(_find_patterns(visible_text, PATTERNS))
    signals.extend(_find_patterns(html, SCRIPT_PATTERNS))

    if not _has_secret_request_context(f"{visible_text}\n{html}"):
        signals = [s for s in signals if s.get("code") != "seed_phrase_request"]

    score = 0
    for sig in signals:
        score = max(score, int(sig.get("severity") or 0))

    codes = {s.get("code") for s in signals}

    if "connect_wallet_prompt" in codes and "claim_airdrop_lure" in codes:
        score = max(score, 65)
        signals.append({
            "code": "wallet_connect_plus_reward_lure",
            "severity": 65,
            "text": "Page combines wallet connection with reward/airdrop lure.",
            "matches": [],
        })

    if "connect_wallet_prompt" in codes and "signature_or_approval_wording" in codes:
        score = max(score, 80)
        signals.append({
            "code": "wallet_connect_plus_approval_language",
            "severity": 80,
            "text": "Page combines wallet connection with approval/signature wording.",
            "matches": [],
        })

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
            "Wallet trap indicators detected."
            if score >= 40 else
            "No strong wallet trap indicators detected."
        ),
    }
