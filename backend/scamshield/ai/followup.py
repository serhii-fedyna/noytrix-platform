from __future__ import annotations

import json
import os
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx


_SCOPE_TERMS = (
    "wallet", "token", "contract", "transaction", "signature", "approve", "permit", "drainer",
    "phishing", "scam", "crypto", "blockchain", "seed", "airdrop", "bridge", "swap", "transfer",
    "address", "domain", "url", "risk", "fund", "asset", "liquidity", "honeypot", "scan", "verdict",
    "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "binance", "stablecoin", "defi", "nft", "web3", "price", "market", "gas", "blockchain",
    "\u0433\u0430\u043c\u0430\u043d\u0435\u0446\u044c", "\u0433\u0430\u043c\u0430\u043d\u0435\u0446", "\u0442\u043e\u043a\u0435\u043d", "\u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442", "\u0442\u0440\u0430\u043d\u0437\u0430\u043a\u0446",
    "\u043f\u0456\u0434\u043f\u0438\u0441", "\u0430\u043f\u0440\u0443\u0432", "\u0444\u0456\u0448\u0438\u043d\u0433", "\u0448\u0430\u0445\u0440\u0430", "\u043a\u0440\u0438\u043f\u0442", "\u0440\u0438\u0437\u0438\u043a", "\u043f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f",
    "\u043a\u043e\u0448\u0435\u043b\u0435\u043a", "\u0442\u043e\u043a\u0435\u043d", "\u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442", "\u0442\u0440\u0430\u043d\u0437\u0430\u043a\u0446", "\u043f\u043e\u0434\u043f\u0438\u0441", "\u0444\u0438\u0448\u0438\u043d\u0433", "\u043c\u043e\u0448\u0435\u043d\u043d", "\u043a\u0440\u0438\u043f\u0442", "\u0440\u0438\u0441\u043a", "\u0441\u0441\u044b\u043b\u043a", "\u0431\u0438\u0442\u043a\u043e\u0438\u043d", "\u0446\u0435\u043d\u0430", "\u0440\u044b\u043d\u043e\u043a", "\u0442\u043e\u0440\u0433\u043e\u0432\u043b",
)

# A follow-up always has a scan context.  People naturally refer to that
# context with short phrases such as “why is this not safe?” rather than
# repeating “crypto” in every message.  These terms keep those questions in
# scope while an unrelated request (for example, weather or general trivia)
# remains outside the Noytrix assistant's remit.
_SCAN_FOLLOWUP_TERMS = (
    "this", "that", "it", "why", "how", "explain", "result", "check",
    "safe", "unsafe", "danger", "guarantee", "mean", "happen", "do next",
    "\u044d\u0442\u043e", "\u044d\u0442\u043e\u0442", "\u043f\u043e\u0447\u0435\u043c\u0443", "\u043a\u0430\u043a", "\u043e\u0431\u044a\u044f\u0441\u043d", "\u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442", "\u043f\u0440\u043e\u0432\u0435\u0440\u043a", "\u0431\u0435\u0437\u043e\u043f\u0430\u0441", "\u043e\u043f\u0430\u0441", "\u0433\u0430\u0440\u0430\u043d\u0442", "\u0447\u0442\u043e \u0434\u0435\u043b\u0430\u0442\u044c",
    "\u0446\u0435", "\u0446\u0435\u0439", "\u0447\u043e\u043c\u0443", "\u044f\u043a", "\u043f\u043e\u044f\u0441\u043d", "\u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442", "\u043f\u0435\u0440\u0435\u0432\u0456\u0440\u043a", "\u0431\u0435\u0437\u043f\u0435\u043a", "\u043d\u0435\u0431\u0435\u0437\u043f\u0435\u043a", "\u0433\u0430\u0440\u0430\u043d\u0442", "\u0449\u043e \u0440\u043e\u0431\u0438\u0442\u0438",
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
    return any(term in normalized for term in _SCOPE_TERMS + _SCAN_FOLLOWUP_TERMS)


async def _live_market_snapshot(question: str) -> dict[str, Any]:
    """Fetch a narrow, timestamped quote only when the user asks for one.

    This prevents the assistant from inventing a current price while keeping
    ordinary crypto-security questions independent of any market API.
    """
    query = str(question or "").casefold()
    asks_price = any(token in query for token in ("price", "quote", "market price", "цена", "курс", "ціна", "вартість"))
    if not asks_price:
        return {}
    assets = (
        ("BTC", ("bitcoin", "btc", "биткоин", "біткоїн")),
        ("ETH", ("ethereum", "eth", "эфир", "ефір")),
        ("SOL", ("solana", "sol", "солана")),
    )
    symbol = next((symbol for symbol, terms in assets if any(term in query for term in terms)), None)
    if not symbol:
        return {}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": f"{symbol}USDT"})
            response.raise_for_status()
            price = float((response.json() or {}).get("price"))
        return {"asset": symbol, "pair": f"{symbol}/USDT", "price": price, "retrieved_at": datetime.now(timezone.utc).isoformat()}
    except Exception:
        return {}


async def answer_security_followup(question: str, verdict: dict[str, Any], language: str | None = None) -> dict[str, Any]:
    lang = _language(language)
    question = str(question or "").strip()
    if not question:
        return {"ok": False, "blocked": True, "answer": _copy(lang, "outside")}

    try:
        language_name = {"en": "English", "ru": "Russian", "uk": "Ukrainian"}[lang]
        from automation_os.gemini_client import GeminiClient
        market_snapshot = await _live_market_snapshot(question)
        system = (
            "You are Noytrix, a thoughtful crypto security and Web3 assistant. "
            "Answer the user's question directly in plain language, using the supplied scan context whenever it is relevant. "
            "You can answer general questions as well as crypto, blockchain, wallet, token, market-mechanics, and supplied-scan questions. "
            "Never reject a non-empty question merely because it is broader than the scan. If an exact number or live fact is not available, explain the ambiguity or limitation briefly, then give the most useful general answer and a practical way to verify it. "
            "Give a complete answer with concrete steps when it is about the scan. "
            "Use the scan context only for claims about this scanned object; never invent evidence. "
            "You may explain general crypto concepts, but do not give personalized investment advice or promise returns. "
            "Do not state a live asset price unless a current price is included in the supplied context. "
            "Never ask for a seed phrase, private key, password, or API secret. "
            "Do not name third-party data providers. Reply in " + language_name + ". "
            "Use plain text only: never use Markdown, asterisks, bullet characters, numbered lists, hashtags, code formatting, or decorative symbols. "
            "Use short paragraphs and remove repetition. "
            "Return valid JSON only: {\"answer\": string}."
        )
        payload = "SCAN CONTEXT:\n" + json.dumps(_safe_context(verdict), ensure_ascii=False) + "\n\nLIVE MARKET SNAPSHOT (only if present and timestamped):\n" + json.dumps(market_snapshot, ensure_ascii=False) + "\n\nUSER QUESTION:\n" + question
        response = await asyncio.to_thread(
            GeminiClient().generate_json,
            system,
            payload,
            {"type": "OBJECT", "properties": {"answer": {"type": "STRING"}}, "required": ["answer"]},
            operation="security_followup",
            max_tokens=1800,
        )
        answer = str((response or {}).get("answer") or "").strip()
        if not answer:
            raise RuntimeError("empty_gemini_response")
        return {"ok": True, "answer": answer, "scope": "crypto_and_scan"}
    except Exception as exc:
        # Compatibility fallback for an existing production credential. It
        # prevents a transient Vertex failure from ending a user's conversation.
        legacy_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if legacy_key:
            try:
                from openai import AsyncOpenAI
                response = await AsyncOpenAI(api_key=legacy_key).chat.completions.create(
                    model=(os.getenv("NOYTRIX_AI_EXPLAINER_MODEL") or "gpt-4o-mini").strip(),
                    temperature=0.15,
                    max_tokens=1400,
                    messages=[
                        {"role": "system", "content": "You are Noytrix, a crypto and Web3 security assistant. Answer crypto and supplied-scan questions in plain " + language_name + ". Do not invent evidence about the scan, give personalised investment advice, or state a live price without current price data in the context. Never request secrets."},
                        {"role": "user", "content": "SCAN CONTEXT:\n" + json.dumps(_safe_context(verdict), ensure_ascii=False) + "\n\nLIVE MARKET SNAPSHOT:\n" + json.dumps(await _live_market_snapshot(question), ensure_ascii=False) + "\n\nUSER QUESTION:\n" + question},
                    ],
                )
                answer = str(response.choices[0].message.content or "").strip()
                if answer:
                    return {"ok": True, "answer": answer, "scope": "crypto_and_scan", "provider": "compatibility"}
            except Exception:
                pass
        return {"ok": False, "unavailable": True, "reason": str(exc)[:300], "answer": _copy(lang, "unavailable")}
