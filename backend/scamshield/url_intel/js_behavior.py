from __future__ import annotations

import re
from typing import Any, Dict, List


JS_PATTERNS = [
    {
        "code": "wallet_provider_access",
        "severity": 25,
        "patterns": [
            r"window\.ethereum",
            r"ethereum\.request",
            r"web3\.currentprovider",
        ],
        "text": "JavaScript references browser wallet provider access.",
    },
    {
        "code": "wallet_connect_request",
        "severity": 10,
        "patterns": [
            r"eth_requestaccounts",
            r"wallet_requestpermissions",
            r"walletconnect",
            r"web3modal",
            r"rainbowkit",
        ],
        "text": "JavaScript references wallet connection requests.",
    },
    {
        "code": "signature_request",
        "severity": 25,
        "patterns": [
            r"personal_sign",
            r"eth_sign",
            r"eth_signtypeddata",
            r"signtypeddata",
            r"signmessage",
            r"signer\.sign",
        ],
        "text": "JavaScript references wallet signature requests.",
    },
    {
        "code": "transaction_request",
        "severity": 20,
        "patterns": [
            r"eth_sendtransaction",
            r"sendtransaction",
            r"contract\.methods",
            r"writecontract",
        ],
        "text": "JavaScript references transaction sending behavior.",
    },
    {
        "code": "approval_or_drain_functions",
        "severity": 75,
        "patterns": [
            r"\bapprove\s*\(",
            r"\bsetapprovalforall\s*\(",
            r"\bpermit\s*\(",
            r"\bpermit2\b",
            r"\btransferfrom\s*\(",
        ],
        "text": "JavaScript references approval or asset-transfer functions.",
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


def analyze_js_behavior(html: str) -> Dict[str, Any]:
    html = str(html or "")
    signals = _hits(html, JS_PATTERNS)

    codes = {x.get("code") for x in signals}
    score = 0

    for sig in signals:
        score = max(score, int(sig.get("severity") or 0))

    if "wallet_connect_request" in codes and "signature_request" in codes:
        score = max(score, 35)
        signals.append({
            "code": "connect_plus_signature_flow_context",
            "severity": 35,
            "text": "JavaScript combines wallet connection with signature request behavior.",
            "matches": [],
        })

    if "wallet_connect_request" in codes and "transaction_request" in codes:
        score = max(score, 35)
        signals.append({
            "code": "connect_plus_transaction_flow_context",
            "severity": 35,
            "text": "JavaScript combines wallet connection with transaction sending behavior.",
            "matches": [],
        })

    if "approval_or_drain_functions" in codes and ("transaction_request" in codes or "signature_request" in codes):
        score = max(score, 90)
        signals.append({
            "code": "possible_js_drainer_flow",
            "severity": 90,
            "text": "JavaScript contains a possible wallet drainer execution flow.",
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
            "JavaScript wallet behavior observed."
            if score >= 40 else
            "No strong risky JavaScript wallet behavior detected."
        ),
    }
