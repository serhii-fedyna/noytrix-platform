from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse

from scamshield.ai.followup import answer_security_followup
from product_analytics import ANALYTICS_DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lang(value: Any) -> str:
    raw = str(value or "en").lower()
    if raw.startswith("ru"):
        return "ru"
    if raw.startswith(("uk", "ua")):
        return "uk"
    return "en"



def _text(lang: str, key: str) -> str:
    """Workspace copy kept as unicode escapes so the API never emits mojibake."""
    values = {
        "en": {
            "accepted": "Input received and prepared for security analysis.",
            "engine": "Noytrix security engine is analyzing the object.",
            "evidence": "Verified risk signals are being collected.",
            "ai": "The AI explanation is being prepared from the verified result.",
            "ai_skip": "The result is ready without an AI explanation.",
            "verdict": "The final risk score and safety verdict were calculated.",
            "failed": "The security analysis could not be completed. Please try again.",
            "watch_saved": "This object is now followed by your Noytrix account.",
            "watch_removed": "Tracking was removed from your account.",
            "watch_missing": "This tracked object was not found.",
            "watch_rechecked": "The object was checked again. A verified change was found.",
            "watch_unchanged": "The object was checked again. Its risk status has not changed.",
            "watch_paused": "24/7 protection was paused for this object.",
            "watch_resumed": "24/7 protection is active for this object again.",
            "watch_paused_skip": "This object is paused. Resume protection before rechecking it.",
            "watch_updated": "Protection settings were updated.",
            "pro_required": "Immunity 24/7 protection is available with Noytrix PRO.",
            "auth_required": "Sign in to follow an object and receive verified changes.",
            "chat_limit": "You have used four free follow-up questions for this result today. PRO has unlimited follow-up questions.",
        },
        "ru": {
            "accepted": "\u0414\u0430\u043d\u043d\u044b\u0435 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u044b \u0438 \u043f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u043b\u0435\u043d\u044b \u043a \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0435 \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e\u0441\u0442\u0438.",
            "engine": "\u0414\u0432\u0438\u0436\u043e\u043a \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e\u0441\u0442\u0438 Noytrix \u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u0435\u0442 \u043e\u0431\u044a\u0435\u043a\u0442.",
            "evidence": "\u0421\u043e\u0431\u0438\u0440\u0430\u0435\u043c \u043f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043d\u044b\u0435 \u0441\u0438\u0433\u043d\u0430\u043b\u044b \u0440\u0438\u0441\u043a\u0430.",
            "ai": "\u0413\u043e\u0442\u043e\u0432\u0438\u043c AI-\u043e\u0431\u044a\u044f\u0441\u043d\u0435\u043d\u0438\u0435 \u043d\u0430 \u043e\u0441\u043d\u043e\u0432\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043d\u043e\u0433\u043e \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u0430.",
            "ai_skip": "\u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442 \u0433\u043e\u0442\u043e\u0432 \u0431\u0435\u0437 AI-\u043e\u0431\u044a\u044f\u0441\u043d\u0435\u043d\u0438\u044f.",
            "verdict": "\u0420\u0430\u0441\u0441\u0447\u0438\u0442\u0430\u043d\u044b \u0438\u0442\u043e\u0433\u043e\u0432\u044b\u0439 \u0440\u0438\u0441\u043a \u0438 \u0432\u0435\u0440\u0434\u0438\u043a\u0442 \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e\u0441\u0442\u0438.",
            "failed": "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u0442\u044c \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443 \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e\u0441\u0442\u0438. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0435\u0449\u0435 \u0440\u0430\u0437.",
            "watch_saved": "\u041e\u0431\u044a\u0435\u043a\u0442 \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d \u0432 \u043e\u0442\u0441\u043b\u0435\u0436\u0438\u0432\u0430\u043d\u0438\u0435 \u0432\u0430\u0448\u0435\u0433\u043e \u0430\u043a\u043a\u0430\u0443\u043d\u0442\u0430 Noytrix.",
            "watch_removed": "\u041e\u0442\u0441\u043b\u0435\u0436\u0438\u0432\u0430\u043d\u0438\u0435 \u0443\u0434\u0430\u043b\u0435\u043d\u043e \u0438\u0437 \u0430\u043a\u043a\u0430\u0443\u043d\u0442\u0430.",
            "watch_missing": "\u042d\u0442\u043e\u0442 \u043e\u0431\u044a\u0435\u043a\u0442 \u043e\u0442\u0441\u043b\u0435\u0436\u0438\u0432\u0430\u043d\u0438\u044f \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.",
            "watch_rechecked": "\u041e\u0431\u044a\u0435\u043a\u0442 \u043f\u0440\u043e\u0432\u0435\u0440\u0435\u043d \u043f\u043e\u0432\u0442\u043e\u0440\u043d\u043e. \u041d\u0430\u0439\u0434\u0435\u043d\u043e \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u043d\u043e\u0435 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0435.",
            "watch_unchanged": "\u041e\u0431\u044a\u0435\u043a\u0442 \u043f\u0440\u043e\u0432\u0435\u0440\u0435\u043d \u043f\u043e\u0432\u0442\u043e\u0440\u043d\u043e. \u0421\u0442\u0430\u0442\u0443\u0441 \u0440\u0438\u0441\u043a\u0430 \u043d\u0435 \u0438\u0437\u043c\u0435\u043d\u0438\u043b\u0441\u044f.",
            "auth_required": "\u0412\u043e\u0439\u0434\u0438\u0442\u0435 \u0432 \u0430\u043a\u043a\u0430\u0443\u043d\u0442, \u0447\u0442\u043e\u0431\u044b \u043e\u0442\u0441\u043b\u0435\u0436\u0438\u0432\u0430\u0442\u044c \u043e\u0431\u044a\u0435\u043a\u0442 \u0438 \u043f\u043e\u043b\u0443\u0447\u0430\u0442\u044c \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u043d\u044b\u0435 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u044f.",
            "chat_limit": "\u0421\u0435\u0433\u043e\u0434\u043d\u044f \u0432\u044b \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043b\u0438 \u0447\u0435\u0442\u044b\u0440\u0435 \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0445 \u0443\u0442\u043e\u0447\u043d\u044f\u044e\u0449\u0438\u0445 \u0432\u043e\u043f\u0440\u043e\u0441\u0430. \u0412 PRO \u0432\u043e\u043f\u0440\u043e\u0441\u044b \u0431\u0435\u0437 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u0439.",
        },
        "uk": {
            "accepted": "\u0414\u0430\u043d\u0456 \u043e\u0442\u0440\u0438\u043c\u0430\u043d\u043e \u0442\u0430 \u043f\u0456\u0434\u0433\u043e\u0442\u043e\u0432\u043b\u0435\u043d\u043e \u0434\u043e \u043f\u0435\u0440\u0435\u0432\u0456\u0440\u043a\u0438 \u0431\u0435\u0437\u043f\u0435\u043a\u0438.",
            "engine": "\u0420\u0443\u0448\u0456\u0439 \u0431\u0435\u0437\u043f\u0435\u043a\u0438 Noytrix \u0430\u043d\u0430\u043b\u0456\u0437\u0443\u0454 \u043e\u0431\u2019\u0454\u043a\u0442.",
            "evidence": "\u0417\u0431\u0438\u0440\u0430\u0454\u043c\u043e \u043f\u0435\u0440\u0435\u0432\u0456\u0440\u0435\u043d\u0456 \u0441\u0438\u0433\u043d\u0430\u043b\u0438 \u0440\u0438\u0437\u0438\u043a\u0443.",
            "ai": "\u0413\u043e\u0442\u0443\u0454\u043c\u043e AI-\u043f\u043e\u044f\u0441\u043d\u0435\u043d\u043d\u044f \u043d\u0430 \u043e\u0441\u043d\u043e\u0432\u0456 \u043f\u0435\u0440\u0435\u0432\u0456\u0440\u0435\u043d\u043e\u0433\u043e \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u0443.",
            "ai_skip": "\u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442 \u0433\u043e\u0442\u043e\u0432\u0438\u0439 \u0431\u0435\u0437 AI-\u043f\u043e\u044f\u0441\u043d\u0435\u043d\u043d\u044f.",
            "verdict": "\u0420\u043e\u0437\u0440\u0430\u0445\u043e\u0432\u0430\u043d\u043e \u043f\u0456\u0434\u0441\u0443\u043c\u043a\u043e\u0432\u0438\u0439 \u0440\u0438\u0437\u0438\u043a \u0442\u0430 \u0432\u0435\u0440\u0434\u0438\u043a\u0442 \u0431\u0435\u0437\u043f\u0435\u043a\u0438.",
            "failed": "\u041d\u0435 \u0432\u0434\u0430\u043b\u043e\u0441\u044f \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u0442\u0438 \u043f\u0435\u0440\u0435\u0432\u0456\u0440\u043a\u0443 \u0431\u0435\u0437\u043f\u0435\u043a\u0438. \u0421\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0449\u0435 \u0440\u0430\u0437.",
            "watch_saved": "\u041e\u0431\u2019\u0454\u043a\u0442 \u0434\u043e\u0434\u0430\u043d\u043e \u0434\u043e \u0432\u0456\u0434\u0441\u0442\u0435\u0436\u0435\u043d\u043d\u044f \u0432 \u0432\u0430\u0448\u043e\u043c\u0443 \u043e\u0431\u043b\u0456\u043a\u043e\u0432\u043e\u043c\u0443 \u0437\u0430\u043f\u0438\u0441\u0456 Noytrix.",
            "watch_removed": "\u0412\u0456\u0434\u0441\u0442\u0435\u0436\u0435\u043d\u043d\u044f \u0432\u0438\u0434\u0430\u043b\u0435\u043d\u043e \u0437 \u043e\u0431\u043b\u0456\u043a\u043e\u0432\u043e\u0433\u043e \u0437\u0430\u043f\u0438\u0441\u0443.",
            "watch_missing": "\u0426\u0435\u0439 \u043e\u0431\u2019\u0454\u043a\u0442 \u0432\u0456\u0434\u0441\u0442\u0435\u0436\u0435\u043d\u043d\u044f \u043d\u0435 \u0437\u043d\u0430\u0439\u0434\u0435\u043d\u043e.",
            "watch_rechecked": "\u041e\u0431\u2019\u0454\u043a\u0442 \u043f\u0435\u0440\u0435\u0432\u0456\u0440\u0435\u043d\u043e \u043f\u043e\u0432\u0442\u043e\u0440\u043d\u043e. \u0417\u043d\u0430\u0439\u0434\u0435\u043d\u043e \u043f\u0456\u0434\u0442\u0432\u0435\u0440\u0434\u0436\u0435\u043d\u0443 \u0437\u043c\u0456\u043d\u0443.",
            "watch_unchanged": "\u041e\u0431\u2019\u0454\u043a\u0442 \u043f\u0435\u0440\u0435\u0432\u0456\u0440\u0435\u043d\u043e \u043f\u043e\u0432\u0442\u043e\u0440\u043d\u043e. \u0421\u0442\u0430\u0442\u0443\u0441 \u0440\u0438\u0437\u0438\u043a\u0443 \u043d\u0435 \u0437\u043c\u0456\u043d\u0438\u0432\u0441\u044f.",
            "auth_required": "\u0423\u0432\u0456\u0439\u0434\u0456\u0442\u044c \u0434\u043e \u043e\u0431\u043b\u0456\u043a\u043e\u0432\u043e\u0433\u043e \u0437\u0430\u043f\u0438\u0441\u0443, \u0449\u043e\u0431 \u0432\u0456\u0434\u0441\u0442\u0435\u0436\u0443\u0432\u0430\u0442\u0438 \u043e\u0431\u2019\u0454\u043a\u0442 \u0442\u0430 \u043e\u0442\u0440\u0438\u043c\u0443\u0432\u0430\u0442\u0438 \u043f\u0456\u0434\u0442\u0432\u0435\u0440\u0434\u0436\u0435\u043d\u0456 \u0437\u043c\u0456\u043d\u0438.",
            "chat_limit": "\u0421\u044c\u043e\u0433\u043e\u0434\u043d\u0456 \u0432\u0438 \u0432\u0438\u043a\u043e\u0440\u0438\u0441\u0442\u0430\u043b\u0438 \u0447\u043e\u0442\u0438\u0440\u0438 \u0431\u0435\u0437\u043a\u043e\u0448\u0442\u043e\u0432\u043d\u0456 \u0443\u0442\u043e\u0447\u043d\u044e\u0432\u0430\u043b\u044c\u043d\u0456 \u0437\u0430\u043f\u0438\u0442\u0430\u043d\u043d\u044f. \u0423 PRO \u0437\u0430\u043f\u0438\u0442\u0430\u043d\u043d\u044f \u0431\u0435\u0437 \u043e\u0431\u043c\u0435\u0436\u0435\u043d\u044c.",
        },
    }
    return values.get(lang, values["en"]).get(key, values["en"][key])


def _sse(event: str, payload: dict[str, Any]) -> str:
    return "event: " + event + "\ndata: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n\n"


def _safe_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    blocked = {"api_key", "token", "authorization", "password", "private_key", "seed", "access_token", "refresh_token"}
    safe: dict[str, Any] = {}
    for key, item in value.items():
        if str(key).lower() in blocked:
            continue
        if isinstance(item, str):
            safe[key] = item[:4000]
        elif isinstance(item, list):
            safe[key] = item[:20]
        elif isinstance(item, dict):
            safe[key] = {str(nested_key): nested_value for nested_key, nested_value in list(item.items())[:30] if str(nested_key).lower() not in blocked}
        else:
            safe[key] = item
    return safe


def _normalized_target(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()).rstrip("/")


def _safe_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _score_from_payload(payload: dict[str, Any]) -> int:
    candidates: list[Any] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized_key = str(key).lower().replace("-", "_")
                if normalized_key in {"score", "risk_score", "riskscore", "risk"}:
                    candidates.append(item)
                if normalized_key in {"result", "verdict", "analysis", "scan", "summary", "details"}:
                    visit(item)
        elif isinstance(value, list):
            for item in value[:12]:
                visit(item)

    visit(payload)
    for candidate in candidates:
        try:
            score = int(float(candidate))
        except (TypeError, ValueError):
            continue
        if 0 <= score <= 100:
            return score
    return 0


def _level_from_payload(payload: dict[str, Any]) -> str:
    aliases = {
        "scam": "critical",
        "malicious": "critical",
        "danger": "critical",
        "dangerous": "critical",
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "warning": "medium",
        "low": "low",
        "safe": "safe",
    }

    def visit(value: Any) -> str | None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized_key = str(key).lower().replace("-", "_")
                if normalized_key in {"level", "risk_level", "status", "verdict", "risk"}:
                    raw = str(item).strip().lower()
                    if raw in aliases:
                        return aliases[raw]
                if normalized_key in {"result", "verdict", "analysis", "scan", "summary", "details"}:
                    found = visit(item)
                    if found:
                        return found
        elif isinstance(value, list):
            for item in value[:12]:
                found = visit(item)
                if found:
                    return found
        return None

    detected = visit(payload)
    if detected:
        return detected
    score = _score_from_payload(payload)
    if score >= 85:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    if score > 0:
        return "low"
    return "safe"


def _risk_rank(level: Any) -> int:
    normalized = str(level or "").lower()
    return {"safe": 0, "low": 0, "medium": 1, "warning": 1, "high": 2, "danger": 2, "critical": 3, "malicious": 3, "scam": 3}.get(normalized, 0)


def _object_kind(target: str, payload: dict[str, Any]) -> str:
    for key in ("kind", "type", "object_type", "target_type"):
        value = str(payload.get(key) or "").lower()
        if value in {"url", "domain", "wallet", "contract", "token", "text", "address"}:
            return "wallet" if value == "address" else value
    normalized = target.strip().lower()
    if normalized.startswith(("http://", "https://")) or "." in normalized:
        return "domain"
    if re.fullmatch(r"0x[a-f0-9]{40}", normalized):
        return "wallet"
    if len(normalized) <= 16 and re.fullmatch(r"[a-z0-9/_-]+", normalized):
        return "token"
    return "text"


def _collect_risk_flags(payload: dict[str, Any]) -> list[str]:
    watched = {
        "malicious",
        "blacklist",
        "phishing",
        "malware",
        "honeypot",
        "owner",
        "ownership",
        "upgrade",
        "upgradeable",
        "permission",
        "approval",
        "sell_tax",
        "buy_tax",
        "liquidity",
        "whale",
        "holder",
        "dangerous",
        "scam",
        "reputation",
        "drain",
        "drainer",
    }
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                haystack = f"{key} {item}".lower()
                for token in watched:
                    if token in haystack:
                        found.add(token)
                visit(item)
        elif isinstance(value, list):
            for item in value[:40]:
                visit(item)
        elif isinstance(value, str):
            haystack = value.lower()
            for token in watched:
                if token in haystack:
                    found.add(token)

    visit(payload)
    return sorted(found)


def _meaningful_change(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    before_score = _score_from_payload(previous)
    after_score = _score_from_payload(current)
    before_level = _level_from_payload(previous)
    after_level = _level_from_payload(current)
    previous_flags = set(_collect_risk_flags(previous))
    current_flags = set(_collect_risk_flags(current))
    new_flags = sorted(current_flags - previous_flags)
    score_crossed = (before_score < 70 <= after_score) or (before_score < 85 <= after_score)
    level_increased = _risk_rank(after_level) > _risk_rank(before_level)
    score_jump = abs(after_score - before_score) >= 25
    changed = bool(score_crossed or level_increased or score_jump or new_flags)
    pieces: list[str] = []
    if before_score != after_score:
        pieces.append(f"Risk score changed from {before_score} to {after_score}.")
    if before_level != after_level:
        pieces.append(f"Risk level changed from {before_level} to {after_level}.")
    if new_flags:
        pieces.append("New risk signals: " + ", ".join(new_flags[:6]) + ".")
    return {
        "changed": changed,
        "event_type": "risk_status_changed" if changed else "risk_status_stable",
        "severity": after_level if changed else "info",
        "summary": " ".join(pieces) if pieces else "No meaningful security change found.",
    }


DEFAULT_WORKSPACE_SETTINGS: dict[str, Any] = {
    "language": "en",
    "region": "UA",
    "timezone": "Europe/Kyiv",
    "theme": "dark",
    "density": "compact",
    "reduce_motion": False,
    "auto_detect": True,
    "show_sources": True,
    "save_history": True,
    "detail_level": "detailed",
    "sync_settings": True,
    "reopen_last_result": False,
    "history_retention": "90",
}


def _workspace_settings(payload: Any) -> dict[str, Any]:
    """Keep the saved workspace preference contract deliberately small and typed."""
    values = payload if isinstance(payload, dict) else {}
    normalized = dict(DEFAULT_WORKSPACE_SETTINGS)
    allowed_choices = {
        "language": {"en", "ru", "uk"},
        "region": {"UA", "EU", "US", "GLOBAL"},
        "timezone": {"Europe/Kyiv", "Europe/Rome", "Europe/London", "America/New_York", "UTC"},
        "theme": {"dark", "system", "light"},
        "density": {"compact", "comfortable"},
        "detail_level": {"standard", "detailed"},
        "history_retention": {"7", "30", "90", "365", "forever"},
    }
    for key, choices in allowed_choices.items():
        value = str(values.get(key) or "")
        if value in choices:
            normalized[key] = value
    for key in ("reduce_motion", "auto_detect", "show_sources", "save_history", "sync_settings", "reopen_last_result"):
        if isinstance(values.get(key), bool):
            normalized[key] = values[key]
    return normalized


def create_workspace_router(
    scan_fn: Callable[..., Awaitable[dict[str, Any]]],
    authenticated_identity: Callable[[Request], str | None],
    entitlement_active: Callable[[str], bool],
    billing_snapshot: Callable[[str], dict[str, Any]],
    watch_db_path: Path,
) -> APIRouter:
    router = APIRouter(tags=["workspace"])
    watch_db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect() -> sqlite3.Connection:
        conn = sqlite3.connect(str(watch_db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workspace_watches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                target TEXT NOT NULL,
                normalized_target TEXT NOT NULL,
                kind TEXT,
                initial_score INTEGER,
                initial_level TEXT,
                snapshot_json TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_checked_at TEXT,
                last_change_at TEXT,
                UNIQUE(user_id, normalized_target)
            );
            CREATE TABLE IF NOT EXISTS workspace_watch_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                watch_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                previous_json TEXT,
                current_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                delivered_at TEXT
            );
            CREATE TABLE IF NOT EXISTS workspace_chat_usage (
                subject TEXT NOT NULL,
                scan_hash TEXT NOT NULL,
                usage_day TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(subject, scan_hash, usage_day)
            );
            CREATE TABLE IF NOT EXISTS workspace_settings (
                user_id TEXT PRIMARY KEY,
                settings_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        migrations = (
            "ALTER TABLE workspace_watches ADD COLUMN paused INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE workspace_watches ADD COLUMN alert_settings_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE workspace_watches ADD COLUMN last_event_type TEXT",
            "ALTER TABLE workspace_watches ADD COLUMN last_event_summary TEXT",
            "ALTER TABLE workspace_watches ADD COLUMN last_event_at TEXT",
            "ALTER TABLE workspace_watch_events ADD COLUMN severity TEXT",
            "ALTER TABLE workspace_watch_events ADD COLUMN summary TEXT",
        )
        for statement in migrations:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError:
                pass
        conn.commit()
        return conn

    def identity_for_request(request: Request) -> str | None:
        try:
            return authenticated_identity(request)
        except Exception:
            return None

    def analytics_timestamp(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None

    def analytics_number(payload: dict[str, Any], *keys: str) -> int | None:
        sources = [payload]
        for key in ("result", "verdict", "scan", "analysis"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                sources.append(nested)
        for source in sources:
            for key in keys:
                value = source.get(key)
                try:
                    return int(float(value))
                except (TypeError, ValueError):
                    continue
        return None

    def analytics_text(payload: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for nested_key in ("result", "verdict", "scan", "analysis"):
            nested = payload.get(nested_key)
            if isinstance(nested, dict):
                value = analytics_text(nested, *keys)
                if value:
                    return value
        return ""

    def analytics_kind(payload: dict[str, Any]) -> str:
        raw = analytics_text(payload, "analysis_type", "object_type", "type", "kind", "entity_type").lower()
        if any(token in raw for token in ("contract", "smart_contract")):
            return "contract"
        if any(token in raw for token in ("wallet", "address")):
            return "wallet"
        if "token" in raw or "ticker" in raw:
            return "token"
        if any(token in raw for token in ("transaction", "signature", "approve", "transfer")):
            return "transaction"
        if any(token in raw for token in ("url", "domain", "website", "link")):
            return "link"
        return "other"

    def analytics_risk(payload: dict[str, Any]) -> tuple[str, int]:
        score = analytics_number(payload, "risk_score", "riskScore", "score")
        level = analytics_text(payload, "risk_level", "riskLevel", "level", "verdict", "status").lower()
        if score is None:
            score = 0
        if score >= 70 or any(token in level for token in ("critical", "high", "scam", "danger", "malicious")):
            return "high", max(score, 70)
        if score >= 30 or any(token in level for token in ("medium", "warning", "suspicious", "attention")):
            return "attention", max(score, 30)
        return "low", max(score, 0)

    @router.get("/workspace/analytics")
    async def get_workspace_analytics(request: Request, days: int = 30):
        days = min(max(int(days), 7), 90)
        user_id = identity_for_request(request)
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days - 1)
        buckets = {(start + timedelta(days=index)).date().isoformat(): {"total": 0, "high": 0} for index in range(days)}
        empty = {
            "ok": True,
            "authenticated": bool(user_id),
            "days": days,
            "summary": {"checks": 0, "high_risk": 0, "watched": 0, "safe": 0, "watch_changes": 0},
            "distribution": {"low": 0, "attention": 0, "high": 0},
            "series": [{"date": key, **value} for key, value in buckets.items()],
            "types": [],
            "recent": [],
        }
        if not user_id:
            return empty

        distribution = {"low": 0, "attention": 0, "high": 0}
        type_counts: dict[str, int] = {}
        recent: list[dict[str, Any]] = []
        try:
            analytics_conn = sqlite3.connect(str(ANALYTICS_DB_PATH))
            analytics_conn.row_factory = sqlite3.Row
            rows = analytics_conn.execute(
                """
                SELECT event_time, properties_json
                FROM product_events
                WHERE user_id = ? AND event_name = 'scan_completed'
                ORDER BY event_time DESC
                LIMIT 5000
                """,
                (user_id,),
            ).fetchall()
            analytics_conn.close()
        except sqlite3.Error:
            rows = []

        for row in rows:
            event_time = analytics_timestamp(row["event_time"])
            if not event_time or event_time < start:
                continue
            try:
                properties = json.loads(row["properties_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                properties = {}
            if not isinstance(properties, dict):
                properties = {}
            risk, score = analytics_risk(properties)
            kind = analytics_kind(properties)
            bucket = buckets.get(event_time.date().isoformat())
            if bucket:
                bucket["total"] += 1
                if risk == "high":
                    bucket["high"] += 1
            distribution[risk] += 1
            type_counts[kind] = type_counts.get(kind, 0) + 1
            if len(recent) < 8:
                recent.append({
                    "target": analytics_text(properties, "target", "input", "object", "value")[:180] or "Security check",
                    "kind": kind,
                    "score": score,
                    "risk": risk,
                    "at": event_time.isoformat(),
                })

        watched = 0
        watch_changes = 0
        try:
            conn = connect()
            watched = int(conn.execute("SELECT COUNT(*) FROM workspace_watches WHERE user_id = ? AND active = 1", (user_id,)).fetchone()[0])
            watch_changes = int(conn.execute("SELECT COUNT(*) FROM workspace_watches WHERE user_id = ? AND active = 1 AND last_change_at IS NOT NULL AND last_change_at >= ?", (user_id, start.isoformat())).fetchone()[0])
            conn.close()
        except sqlite3.Error:
            pass

        checks = sum(distribution.values())
        return {
            "ok": True,
            "authenticated": True,
            "days": days,
            "summary": {"checks": checks, "high_risk": distribution["high"], "watched": watched, "safe": distribution["low"], "watch_changes": watch_changes},
            "distribution": distribution,
            "series": [{"date": key, **value} for key, value in buckets.items()],
            "types": [{"key": key, "count": value} for key, value in sorted(type_counts.items(), key=lambda item: item[1], reverse=True)],
            "recent": recent,
        }

    def chat_subject(request: Request) -> tuple[str, bool]:
        account_id = identity_for_request(request)
        if account_id:
            return account_id, bool(entitlement_active(account_id))
        session_id = (request.headers.get("x-noytrix-session") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", session_id):
            raise HTTPException(status_code=400, detail="invalid_workspace_session")
        return "session:" + session_id, False

    @router.get("/workspace/billing")
    async def get_workspace_billing(request: Request):
        user_id = identity_for_request(request)
        if not user_id:
            return {"ok": True, "authenticated": False, "current": None, "history": []}
        return {"ok": True, "authenticated": True, **billing_snapshot(user_id)}

    @router.get("/workspace/settings")
    async def get_workspace_settings(request: Request):
        user_id = identity_for_request(request)
        if not user_id:
            return {"ok": True, "authenticated": False, "settings": dict(DEFAULT_WORKSPACE_SETTINGS)}
        conn = connect()
        try:
            row = conn.execute("SELECT settings_json,updated_at FROM workspace_settings WHERE user_id=?", (user_id,)).fetchone()
        finally:
            conn.close()
        if not row:
            return {"ok": True, "authenticated": True, "settings": dict(DEFAULT_WORKSPACE_SETTINGS), "updated_at": None}
        try:
            stored = json.loads(str(row["settings_json"] or "{}"))
        except (TypeError, ValueError):
            stored = {}
        return {
            "ok": True,
            "authenticated": True,
            "settings": _workspace_settings(stored),
            "updated_at": str(row["updated_at"] or "") or None,
        }

    @router.put("/workspace/settings")
    async def save_workspace_settings(request: Request, payload: dict[str, Any] = Body(...)):
        user_id = identity_for_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="workspace_auth_required")
        settings = _workspace_settings(payload.get("settings"))
        updated_at = _now()
        conn = connect()
        try:
            conn.execute(
                """
                INSERT INTO workspace_settings(user_id,settings_json,updated_at)
                VALUES(?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET settings_json=excluded.settings_json,updated_at=excluded.updated_at
                """,
                (user_id, json.dumps(settings, ensure_ascii=False), updated_at),
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "settings": settings, "updated_at": updated_at}

    @router.post("/workspace/scan-stream")
    async def scan_stream(request: Request, payload: dict[str, Any] = Body(...)):
        target = str(payload.get("input") or "").strip()
        language = _lang(payload.get("lang"))
        user_id = str(payload.get("userId") or "").strip() or None
        if not target or len(target) > 5000:
            raise HTTPException(status_code=422, detail="invalid_scan_input")

        async def events():
            stages = [
                ("input", _text(language, "accepted")),
                ("engine", _text(language, "engine")),
                ("evidence", _text(language, "evidence")),
                ("ai", _text(language, "ai")),
                ("verdict", _text(language, "verdict")),
            ]
            yield _sse("analysis_started", {"stages": [{"id": stage, "text": text, "status": "pending"} for stage, text in stages]})
            yield _sse("stage", {"id": "input", "status": "done", "text": _text(language, "accepted")})
            yield _sse("stage", {"id": "engine", "status": "running", "text": _text(language, "engine")})
            await asyncio.sleep(0)
            try:
                result = await scan_fn(request, input=target, lang=language, userId=user_id)
            except HTTPException as exc:
                yield _sse("error", {"message": _text(language, "failed"), "status": exc.status_code})
                return
            except Exception:
                yield _sse("error", {"message": _text(language, "failed"), "status": 500})
                return

            safe_result = _safe_result(result)
            yield _sse("stage", {"id": "engine", "status": "done", "text": _text(language, "engine")})
            yield _sse("stage", {"id": "evidence", "status": "done", "text": _text(language, "evidence")})
            ai_text = str(safe_result.get("ai_explanation") or "").strip()
            yield _sse("stage", {"id": "ai", "status": "done" if ai_text else "skipped", "text": _text(language, "ai") if ai_text else _text(language, "ai_skip")})
            yield _sse("stage", {"id": "verdict", "status": "done", "text": _text(language, "verdict")})
            yield _sse("verdict", {"result": safe_result})

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})

    @router.post("/workspace/chat")
    async def workspace_chat(request: Request, payload: dict[str, Any] = Body(...)):
        language = _lang(payload.get("lang"))
        question = str(payload.get("question") or "").strip()
        verdict = _safe_result(payload.get("scan"))
        if not question or len(question) > 1200 or not verdict:
            raise HTTPException(status_code=422, detail="invalid_followup")
        subject, pro_active = chat_subject(request)
        scan_hash = hashlib.sha256(str(verdict.get("input") or "").strip().lower().encode("utf-8")).hexdigest()
        usage_day = datetime.now(timezone.utc).date().isoformat()
        used = 0
        if not pro_active:
            conn = connect()
            try:
                row = conn.execute("SELECT used FROM workspace_chat_usage WHERE subject=? AND scan_hash=? AND usage_day=?", (subject, scan_hash, usage_day)).fetchone()
                used = int(row["used"] if row else 0)
                if used >= 4:
                    return {"ok": False, "upgrade_required": True, "limit": 4, "used": used, "remaining": 0, "answer": _text(language, "chat_limit")}
            finally:
                conn.close()

        answer = await answer_security_followup(question, verdict, language)
        if answer.get("ok") and not pro_active:
            conn = connect()
            try:
                conn.execute(
                    "INSERT INTO workspace_chat_usage(subject,scan_hash,usage_day,used,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(subject,scan_hash,usage_day) DO UPDATE SET used=used+1,updated_at=excluded.updated_at",
                    (subject, scan_hash, usage_day, 1, _now()),
                )
                conn.commit()
                used += 1
            finally:
                conn.close()
        answer.update({"pro": pro_active, "limit": None if pro_active else 4, "used": None if pro_active else used, "remaining": None if pro_active else max(0, 4 - used)})
        return answer

    @router.post("/workspace/watches")
    async def create_watch(request: Request, payload: dict[str, Any] = Body(...)):
        language = _lang(payload.get("lang"))
        user_id = identity_for_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail={"message": _text(language, "auth_required")})
        if not entitlement_active(user_id):
            raise HTTPException(status_code=402, detail={"message": _text(language, "pro_required"), "code": "pro_required"})
        target = str(payload.get("target") or "").strip()
        result = _safe_result(payload.get("scan"))
        if not target or len(target) > 5000 or not result:
            raise HTTPException(status_code=422, detail="invalid_watch")
        now = _now()
        score = _score_from_payload(result)
        level = _level_from_payload(result)
        kind = _object_kind(target, result)
        alert_settings = payload.get("alertSettings") or payload.get("alerts") or {"risk_change": True, "critical_only": False}
        conn = connect()
        try:
            conn.execute(
                """
                INSERT INTO workspace_watches(user_id,target,normalized_target,kind,initial_score,initial_level,snapshot_json,active,paused,alert_settings_json,created_at,updated_at,last_checked_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id,normalized_target) DO UPDATE SET target=excluded.target,kind=excluded.kind,initial_score=excluded.initial_score,initial_level=excluded.initial_level,snapshot_json=excluded.snapshot_json,active=1,paused=0,alert_settings_json=excluded.alert_settings_json,updated_at=excluded.updated_at,last_checked_at=excluded.last_checked_at
                """,
                (user_id, target, _normalized_target(target), kind, score, level, json.dumps(result, ensure_ascii=False), 1, 0, json.dumps(alert_settings, ensure_ascii=False), now, now, now),
            )
            row = conn.execute(
                "SELECT * FROM workspace_watches WHERE user_id=? AND normalized_target=? AND active=1",
                (user_id, _normalized_target(target)),
            ).fetchone()
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "message": _text(language, "watch_saved"), "item": watch_item(row)}

    def watch_item(row: sqlite3.Row) -> dict[str, Any]:
        snapshot = _safe_json_dict(row["snapshot_json"])
        last_checked_at = str(row["last_checked_at"] or "")
        last_change_at = str(row["last_change_at"] or "")
        score = _score_from_payload(snapshot) or row["initial_score"] or 0
        level = _level_from_payload(snapshot) or row["initial_level"] or "safe"
        paused = bool(row["paused"]) if "paused" in row.keys() else False
        alerts = _safe_json_dict(row["alert_settings_json"] if "alert_settings_json" in row.keys() else "{}")
        last_event_at = str(row["last_event_at"] or "") if "last_event_at" in row.keys() else ""
        last_event_type = str(row["last_event_type"] or "") if "last_event_type" in row.keys() else ""
        last_event_summary = str(row["last_event_summary"] or "") if "last_event_summary" in row.keys() else ""
        return {
            "id": int(row["id"]),
            "target": str(row["target"]),
            "normalizedTarget": str(row["normalized_target"]),
            "kind": str(row["kind"] or "unknown"),
            "score": score,
            "level": level,
            "createdAt": str(row["created_at"] or ""),
            "created_at": str(row["created_at"] or ""),
            "updatedAt": str(row["updated_at"] or ""),
            "lastCheckedAt": last_checked_at,
            "last_checked_at": last_checked_at,
            "lastChangeAt": last_change_at or None,
            "last_changed_at": last_change_at or None,
            "lastEventAt": last_event_at or None,
            "lastEventType": last_event_type or None,
            "lastEventSummary": last_event_summary or None,
            "status": "paused" if paused else ("changed" if last_event_at else "protected"),
            "paused": paused,
            "protected": not paused,
            "alertSettings": alerts,
        }

    @router.get("/workspace/watches")
    async def list_watches(request: Request, lang: str = "en"):
        language = _lang(lang)
        user_id = identity_for_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail={"message": _text(language, "auth_required")})
        conn = connect()
        try:
            rows = conn.execute(
                "SELECT * FROM workspace_watches WHERE user_id=? AND active=1 ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        finally:
            conn.close()
        return {"ok": True, "items": [watch_item(row) for row in rows]}

    @router.post("/workspace/watches/{watch_id}/recheck")
    async def recheck_watch(watch_id: int, request: Request, payload: dict[str, Any] = Body(default={})):
        language = _lang((payload or {}).get("lang"))
        user_id = identity_for_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail={"message": _text(language, "auth_required")})
        conn = connect()
        try:
            row = conn.execute(
                "SELECT * FROM workspace_watches WHERE id=? AND user_id=? AND active=1",
                (watch_id, user_id),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="watch_not_found")
        if int(row["paused"] or 0):
            return {"ok": True, "changed": False, "message": _text(language, "watch_paused_skip"), "item": watch_item(row)}

        result = _safe_result(await scan_fn(request, input=str(row["target"]), lang=language, userId=user_id))
        previous = _safe_json_dict(row["snapshot_json"])
        change = _meaningful_change(previous, result)
        changed = bool(change["changed"])
        now = _now()
        conn = connect()
        try:
            conn.execute(
                """
                UPDATE workspace_watches
                SET snapshot_json=?,kind=?,initial_score=?,initial_level=?,updated_at=?,last_checked_at=?,last_change_at=?,
                    last_event_type=?,last_event_summary=?,last_event_at=?
                WHERE id=? AND user_id=?
                """,
                (
                    json.dumps(result, ensure_ascii=False),
                    _object_kind(str(row["target"]), result),
                    _score_from_payload(result),
                    _level_from_payload(result),
                    now,
                    now,
                    now if changed else row["last_change_at"],
                    change["event_type"] if changed else row["last_event_type"],
                    change["summary"] if changed else row["last_event_summary"],
                    now if changed else row["last_event_at"],
                    watch_id,
                    user_id,
                ),
            )
            if changed:
                conn.execute(
                    "INSERT INTO workspace_watch_events(watch_id,event_type,severity,summary,previous_json,current_json,created_at) VALUES(?,?,?,?,?,?,?)",
                    (
                        watch_id,
                        change["event_type"],
                        change["severity"],
                        change["summary"],
                        json.dumps(previous, ensure_ascii=False),
                        json.dumps(result, ensure_ascii=False),
                        now,
                    ),
                )
            updated = conn.execute("SELECT * FROM workspace_watches WHERE id=?", (watch_id,)).fetchone()
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "changed": changed, "message": _text(language, "watch_rechecked" if changed else "watch_unchanged"), "item": watch_item(updated), "result": result}

    @router.get("/workspace/watches/{watch_id}/events")
    async def list_watch_events(watch_id: int, request: Request, lang: str = "en"):
        language = _lang(lang)
        user_id = identity_for_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail={"message": _text(language, "auth_required")})
        conn = connect()
        try:
            row = conn.execute("SELECT id FROM workspace_watches WHERE id=? AND user_id=? AND active=1", (watch_id, user_id)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="watch_not_found")
            events = conn.execute(
                "SELECT * FROM workspace_watch_events WHERE watch_id=? ORDER BY created_at DESC LIMIT 50",
                (watch_id,),
            ).fetchall()
        finally:
            conn.close()
        return {
            "ok": True,
            "items": [
                {
                    "id": int(event["id"]),
                    "eventType": str(event["event_type"]),
                    "severity": str(event["severity"] or "info") if "severity" in event.keys() else "info",
                    "summary": str(event["summary"] or "") if "summary" in event.keys() else "",
                    "createdAt": str(event["created_at"] or ""),
                }
                for event in events
            ],
        }

    @router.patch("/workspace/watches/{watch_id}")
    async def update_watch(watch_id: int, request: Request, payload: dict[str, Any] = Body(default={})):
        language = _lang((payload or {}).get("lang"))
        user_id = identity_for_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail={"message": _text(language, "auth_required")})
        updates: list[str] = []
        values: list[Any] = []
        if "paused" in payload:
            updates.append("paused=?")
            values.append(1 if bool(payload.get("paused")) else 0)
        alerts = payload.get("alertSettings") or payload.get("alerts")
        if isinstance(alerts, dict):
            updates.append("alert_settings_json=?")
            values.append(json.dumps(alerts, ensure_ascii=False))
        if not updates:
            raise HTTPException(status_code=422, detail="nothing_to_update")
        updates.append("updated_at=?")
        values.append(_now())
        values.extend([watch_id, user_id])
        conn = connect()
        try:
            result = conn.execute(
                f"UPDATE workspace_watches SET {', '.join(updates)} WHERE id=? AND user_id=? AND active=1",
                tuple(values),
            )
            row = conn.execute("SELECT * FROM workspace_watches WHERE id=? AND user_id=? AND active=1", (watch_id, user_id)).fetchone()
            conn.commit()
        finally:
            conn.close()
        if not result.rowcount or not row:
            raise HTTPException(status_code=404, detail="watch_not_found")
        paused_now = bool(row["paused"])
        return {"ok": True, "message": _text(language, "watch_paused" if paused_now else "watch_resumed"), "item": watch_item(row)}

    @router.delete("/workspace/watches/{watch_id}")
    async def delete_watch(watch_id: int, request: Request, lang: str = "en"):
        language = _lang(lang)
        user_id = identity_for_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail={"message": _text(language, "auth_required")})
        conn = connect()
        try:
            result = conn.execute(
                "UPDATE workspace_watches SET active=0,updated_at=? WHERE id=? AND user_id=? AND active=1",
                (_now(), watch_id, user_id),
            )
            conn.commit()
        finally:
            conn.close()
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="watch_not_found")
        return {"ok": True}

    return router
