from typing import Dict


KNOWN_TRUSTED = {
    "uniswap",
    "1inch",
    "cow",
    "paraswap",
}

KNOWN_MALICIOUS = {
    "drainer",
    "scam",
    "fake",
}


def classify_spender_label(label: str | None) -> str:
    raw = str(label or "").lower()

    for x in KNOWN_MALICIOUS:
        if x in raw:
            return "malicious"

    for x in KNOWN_TRUSTED:
        if x in raw:
            return "trusted"

    return "unknown"


def build_spender_reputation(address: str, label: str | None = None) -> Dict:
    trust = classify_spender_label(label)

    risk = (
        "high" if trust == "malicious"
        else "low" if trust == "trusted"
        else "medium"
    )

    return {
        "address": address,
        "label": label,
        "trust": trust,
        "risk": risk,
    }
