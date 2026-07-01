from __future__ import annotations

import json
import os
from typing import Any, Dict


def _compact_json(data: Dict[str, Any], max_chars: int = 14000) -> str:
    text = json.dumps(data or {}, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...TRUNCATED"


def _normalize_judge_level(score: int) -> str:
    if score >= 90:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    if score >= 15:
        return "low"
    return "safe"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


async def generate_ai_security_judge(
    context: Dict[str, Any],
    lang: str = "en",
) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("NOYTRIX_AI_JUDGE_MODEL", os.getenv("NOYTRIX_AI_EXPLAINER_MODEL", "gpt-4o-mini"))

    if not api_key:
        return {
            "available": False,
            "reason": "openai_api_key_missing",
            "source": "ai_security_judge",
            "score": 0,
            "confidence": 0,
            "level": "safe",
            "risk_delta": 0,
            "evidence_used": [],
            "reasoning": "",
        }

    try:
        from openai import AsyncOpenAI
    except Exception:
        return {
            "available": False,
            "reason": "openai_package_missing",
            "source": "ai_security_judge",
            "score": 0,
            "confidence": 0,
            "level": "safe",
            "risk_delta": 0,
            "evidence_used": [],
            "reasoning": "",
        }

    system = (
        "You are Noytrix AI Security Judge. "
        "Your job is to evaluate whether the object is risky using ONLY the structured backend context. "
        "You are an additional risk source, not the final authority. "
        "Do not invent external facts. Do not browse. Do not claim confirmation unless evidence exists in the context. "
        "Return ONLY valid JSON with this exact shape: "
        "{\"score\":integer,\"confidence\":integer,\"level\":string,\"risk_delta\":integer,\"evidence_used\":[string],\"reasoning\":string}. "
        "Score means AI-only risk score from 0 to 100. "
        "Confidence means how confident you are based on backend evidence from 0 to 100. "
        "risk_delta is how much should be added to backend score: 0 if no clear extra signal, 5-10 weak, 15-25 medium, 30-40 strong. "
        "Never set risk_delta above 40. "
        "If evidence is weak, score and confidence must stay low. "
        "No markdown. No extra text."
    )

    user = (
        "Evaluate this security context as an additional AI source. "
        "Focus on missed scam patterns, social engineering, suspicious transaction behavior, wallet drain signs, hidden permissions, source disagreements, and weak evidence limits.\n\n"
        f"{_compact_json(context)}"
    )

    try:
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            temperature=0.1,
            max_tokens=500,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

        text = (resp.choices[0].message.content or "").strip()

        try:
            data = json.loads(text)
        except Exception:
            data = {
                "score": 0,
                "confidence": 0,
                "level": "safe",
                "risk_delta": 0,
                "evidence_used": [],
                "reasoning": "",
                "parse_error": True,
                "raw_text": text[:500],
            }

        score = max(0, min(100, _safe_int(data.get("score"))))
        confidence = max(0, min(100, _safe_int(data.get("confidence"))))
        risk_delta = max(0, min(40, _safe_int(data.get("risk_delta"))))

        if confidence < 50:
            risk_delta = min(risk_delta, 10)

        level = str(data.get("level") or _normalize_judge_level(score)).lower()
        if level not in {"safe", "low", "medium", "high", "critical"}:
            level = _normalize_judge_level(score)

        evidence_used = data.get("evidence_used")
        if not isinstance(evidence_used, list):
            evidence_used = []

        return {
            "available": True,
            "reason": None,
            "source": "ai_security_judge",
            "model": model,
            "language": lang,
            "score": score,
            "confidence": confidence,
            "level": level,
            "risk_delta": risk_delta,
            "evidence_used": [str(x)[:300] for x in evidence_used[:8]],
            "reasoning": str(data.get("reasoning") or "")[:1200],
        }

    except Exception as e:
        return {
            "available": False,
            "reason": str(e)[:300],
            "source": "ai_security_judge",
            "model": model,
            "language": lang,
            "score": 0,
            "confidence": 0,
            "level": "safe",
            "risk_delta": 0,
            "evidence_used": [],
            "reasoning": "",
        }
