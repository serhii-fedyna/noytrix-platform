from __future__ import annotations

import json
import os
from typing import Any


_SCOPE_TERMS = (
    "wallet", "token", "contract", "transaction", "signature", "approve", "permit", "drainer",
    "phishing", "scam", "crypto", "blockchain", "seed", "airdrop", "bridge", "swap", "transfer",
    "address", "domain", "url", "risk", "fund", "asset", "liquidity", "honeypot", "scan", "verdict",
    "\u0433\u0430\u043c\u0430\u043d\u0435\u0446\u044c", "\u0433\u0430\u043c\u0430\u043d\u0435\u0446", "\u0442\u043e\u043a\u0435\u043d", "\u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442", "\u0442\u0440\u0430\u043d\u0437\u0430\u043a\u0446",
    "\u043f\u0456\u0434\u043f\u0438\u0441", "\u0430\u043f\u0440\u0443\u0432", "\u0444\u0456\u0448\u0438\u043d\u0433", "\u0448\u0430\u0445\u0440\u0430", "\u043a\u0440\u0438\u043f\u0442", "\u0440\u0438\u0437\u0438\u043a", "\u043f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f",
    "\u043a\u043e\u0448\u0435\u043b\u0435\u043a", "\u0442\u043e\u043a\u0435\u043d", "\u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442", "\u0442\u0440\u0430\u043d\u0437\u0430\u043a\u0446", "\u043f\u043e\u0434\u043f\u0438\u0441", "\u0444\u0438\u0448\u0438\u043d\u0433", "\u043c\u043e\u0448\u0435\u043d\u043d", "\u043a\u0440\u0438\u043f\u0442", "\u0440\u0438\u0441\u043a", "\u0441\u0441\u044b\u043b\u043a",
)


def _language(value: str | None) -> str:
    value = str(value or "en").strip().lower()
    if value.startswith("ru"):
        return "ru"
    if value.startswith(("uk", "ua")):
        return "uk"
    return "en"


def _copy(lang: str, key: str) -> str:
    values = {
        "en": {
            "outside": "I can help only with this Noytrix security result and crypto-safety questions.",
            "unavailable": "The Noytrix AI explanation is temporarily unavailable. Please try again shortly.",
        },
        "ru": {
            "outside": "\u042f \u043c\u043e\u0433\u0443 \u043f\u043e\u043c\u043e\u0447\u044c \u0442\u043e\u043b\u044c\u043a\u043e \u0441 \u044d\u0442\u0438\u043c \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u043e\u043c Noytrix \u0438 \u0432\u043e\u043f\u0440\u043e\u0441\u0430\u043c\u0438 \u043a\u0440\u0438\u043f\u0442\u043e\u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e\u0441\u0442\u0438.",
            "unavailable": "AI-\u043e\u0431\u044a\u044f\u0441\u043d\u0435\u043d\u0438\u0435 Noytrix \u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0435\u0449\u0451 \u0440\u0430\u0437 \u043d\u0435\u043c\u043d\u043e\u0433\u043e \u043f\u043e\u0437\u0436\u0435.",
        },
        "uk": {
            "outside": "\u042f \u043c\u043e\u0436\u0443 \u0434\u043e\u043f\u043e\u043c\u043e\u0433\u0442\u0438 \u043b\u0438\u0448\u0435 \u0437 \u0446\u0438\u043c \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u043e\u043c Noytrix \u0456 \u043f\u0438\u0442\u0430\u043d\u043d\u044f\u043c\u0438 \u043a\u0440\u0438\u043f\u0442\u043e\u0431\u0435\u0437\u043f\u0435\u043a\u0438.",
            "unavailable": "AI-\u043f\u043e\u044f\u0441\u043d\u0435\u043d\u043d\u044f Noytrix \u0442\u0438\u043c\u0447\u0430\u0441\u043e\u0432\u043e \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0435. \u0421\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0449\u0435 \u0440\u0430\u0437 \u0442\u0440\u043e\u0445\u0438 \u043f\u0456\u0437\u043d\u0456\u0448\u0435.",
        },
    }
    return values[lang][key]


def _compact(value: Any, depth: int = 0) -> Any:
    if depth > 3:
        return None
    if isinstance(value, str):
        return value.strip()[:900]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_compact(item, depth + 1) for item in value[:8]]
    if isinstance(value, dict):
        blocked = {"api_key", "token", "authorization", "password", "private_key", "seed", "access_token", "refresh_token"}
        return {str(key): _compact(item, depth + 1) for key, item in value.items() if str(key).lower() not in blocked}
    return str(value)[:900]


def _safe_context(verdict: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "input", "kind", "score", "risk_score", "level", "risk_level", "verdict", "summary",
        "ai_explanation", "risks", "evidence", "signals", "what_can_happen", "recommended_action",
        "permissions_summary", "runtime_behavior", "execution_graph", "wallet_drain_simulation",
    )
    return _compact({key: verdict.get(key) for key in keys if verdict.get(key) not in (None, "", [], {})})


def _in_scope(question: str) -> bool:
    normalized = str(question or "").casefold()
    return any(term in normalized for term in _SCOPE_TERMS)


async def answer_security_followup(question: str, verdict: dict[str, Any], language: str | None = None) -> dict[str, Any]:
    lang = _language(language)
    question = str(question or "").strip()
    if not question or not _in_scope(question):
        return {"ok": False, "blocked": True, "answer": _copy(lang, "outside")}

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return {"ok": False, "unavailable": True, "answer": _copy(lang, "unavailable")}

    try:
        from openai import AsyncOpenAI

        language_name = {"en": "English", "ru": "Russian", "uk": "Ukrainian"}[lang]
        response = await AsyncOpenAI(api_key=api_key).chat.completions.create(
            model=(os.getenv("NOYTRIX_AI_EXPLAINER_MODEL") or "gpt-4o-mini").strip(),
            temperature=0.15,
            max_tokens=420,
            messages=[
                {"role": "system", "content": "You are Noytrix, a crypto-security follow-up assistant. Answer only questions about the supplied scan and crypto/Web3 safety. Do not give investment advice, invent evidence, or name third-party providers. Be concrete and concise. Reply in " + language_name + "."},
                {"role": "user", "content": "SCAN CONTEXT:\n" + json.dumps(_safe_context(verdict), ensure_ascii=False) + "\n\nUSER QUESTION:\n" + question},
            ],
        )
        answer = str(response.choices[0].message.content or "").strip()
        if not answer:
            raise RuntimeError("empty_openai_response")
        return {"ok": True, "answer": answer, "scope": "scan_security"}
    except Exception:
        return {"ok": False, "unavailable": True, "answer": _copy(lang, "unavailable")}
