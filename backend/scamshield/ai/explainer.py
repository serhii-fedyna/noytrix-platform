from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict


CACHE_DB_PATH = Path("data/ai_explanations_cache.sqlite3")


def _cache_connect() -> sqlite3.Connection:
    CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
    CREATE TABLE IF NOT EXISTS ai_explanations_cache (
        cache_key TEXT PRIMARY KEY,
        lang TEXT,
        mode TEXT,
        model TEXT,
        response_json TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        hit_count INTEGER NOT NULL DEFAULT 0
    )
    """)
    conn.commit()
    return conn


def _cache_key(context_json: str, lang: str, mode: str, model: str) -> str:
    raw = f"{lang}|{mode}|{model}|{context_json}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached_ai_explanation(cache_key: str) -> Dict[str, Any] | None:
    conn = _cache_connect()
    try:
        row = conn.execute(
            "SELECT response_json FROM ai_explanations_cache WHERE cache_key=?",
            (cache_key,),
        ).fetchone()

        if not row:
            return None

        conn.execute(
            "UPDATE ai_explanations_cache SET hit_count=hit_count+1, updated_at=? WHERE cache_key=?",
            (int(time.time()), cache_key),
        )
        conn.commit()

        data = json.loads(row["response_json"])

        data["cache_hit"] = True
        data["_cache"] = {
            "hit": True,
            "provider": "sqlite",
        }

        return data
    finally:
        conn.close()


def save_cached_ai_explanation(cache_key: str, lang: str, mode: str, model: str, response: Dict[str, Any]) -> None:
    conn = _cache_connect()
    try:
        now = int(time.time())
        conn.execute(
            """
            INSERT OR REPLACE INTO ai_explanations_cache
            (cache_key, lang, mode, model, response_json, created_at, updated_at, hit_count)
            VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM ai_explanations_cache WHERE cache_key=?), ?), ?, COALESCE((SELECT hit_count FROM ai_explanations_cache WHERE cache_key=?), 0))
            """,
            (
                cache_key,
                lang,
                mode,
                model,
                json.dumps(response, ensure_ascii=False),
                cache_key,
                now,
                now,
                cache_key,
            ),
        )
        conn.commit()
    finally:
        conn.close()




def build_threat_specific_prompt(ctx: Dict[str, Any]) -> str:
    parts = []

    kind = str(ctx.get("kind") or "").lower()
    risk_type = str(ctx.get("risk_type") or "").lower()

    if kind == "url":
        parts.append(
            "This is a website or link check. Explain domain/page risk, external source results, and what the user should avoid on the site."
        )
    elif kind == "wallet":
        parts.append(
            "This is a wallet or address check. Explain wallet reputation, known activity, memory, source limitations, and avoid claiming future transaction safety."
        )
    elif kind == "contract":
        parts.append(
            "This is a smart contract check. Explain contract identity, spender role, token permissions, honeypot or contract-specific risks if present."
        )
    elif kind == "transaction":
        parts.append(
            "This is a transaction/signature check. Explain what signing may allow, what permissions are requested, and whether hidden execution behavior exists."
        )
    elif kind == "text":
        parts.append(
            "This is a text/message check. Explain social engineering, fake promises, impersonation, deposit requests, or missing evidence if not detected."
        )

    permissions = ctx.get("permissions_summary") or {}
    graph = ctx.get("recursive_execution_graph") or {}
    drain = ctx.get("wallet_drain_simulation") or {}
    runtime = ctx.get("runtime_behavior") or {}
    noytrix_url_intel = ctx.get("noytrix_url_intelligence") or {}

    if permissions.get("unlimited"):
        parts.append(
            "The explanation must clearly explain that unlimited token spending permission may allow future wallet draining without another approval popup."
        )

    if graph.get("attack_chain_summary", {}).get("has_attack_chain"):
        parts.append(
            "Explain the attack chain step-by-step in human language and explain what hidden calls may happen after confirmation."
        )

    if graph.get("max_depth", 0) >= 2:
        parts.append(
            "Explain that nested hidden calls were detected inside another transaction structure."
        )

    if drain.get("drain_probability", 0) >= 90:
        parts.append(
            "Clearly explain that the transaction behavior strongly matches known wallet drainer patterns."
        )

    if runtime.get("level") in {"critical", "high"}:
        parts.append(
            "Clearly explain why the runtime behavior itself appears dangerous."
        )

    if noytrix_url_intel.get("score", 0) >= 70:
        parts.append(
            "The explanation must mention that Noytrix internal URL intelligence itself detected strong risk signals."
        )

    if noytrix_url_intel.get("confirmed_internal_red_flag"):
        parts.append(
            "Explain that the internal Noytrix threat intelligence system already has historical risk evidence connected to this entity."
        )

    if noytrix_url_intel.get("only_memory_signal"):
        parts.append(
            "Explain that the current risk is mainly based on historical intelligence memory rather than newly observed live malicious behavior."
        )

    if risk_type == "phishing":
        parts.append(
            "Explain that the website may imitate a trusted brand or service to trick users into approvals or wallet connections."
        )

    if risk_type == "execution_attack_chain":
        parts.append(
            "Explain that multiple hidden blockchain actions were detected in a chained execution flow."
        )

    if risk_type == "approval":
        parts.append(
            "Explain what token approval means and why malicious approvals are dangerous."
        )

    if risk_type == "drainer":
        parts.append(
            "Explain that the behavior resembles known wallet drainers used to steal tokens and NFTs."
        )

    return " ".join(parts[:12])


def build_ai_explanation_context(verdict: Dict[str, Any]) -> Dict[str, Any]:
    verdict = verdict or {}
    raw = verdict.get("raw") or {}

    sources_for_context = verdict.get("sources") or raw.get("sources") or []
    noytrix_url_intelligence = (
        verdict.get("noytrix_url_intelligence")
        or raw.get("noytrix_url_intelligence")
        or {}
    )

    if not noytrix_url_intelligence:
        for src in sources_for_context:
            if str((src or {}).get("name") or (src or {}).get("source") or "").lower() == "noytrix_url_intelligence":
                noytrix_url_intelligence = {
                    **((src or {}).get("details") or {}),
                    "evidence": (src or {}).get("evidence") or [],
                    "status": (src or {}).get("status"),
                    "verdict": (src or {}).get("verdict"),
                }
                break

    return {
        "input": verdict.get("input"),
        "kind": verdict.get("kind"),
        "score": verdict.get("score"),
        "confidence": verdict.get("confidence_score") or verdict.get("confidence"),
        "level": verdict.get("level"),
        "risk_type": verdict.get("risk_type"),
        "summary": verdict.get("summary"),
        "what_can_happen": verdict.get("what_can_happen"),
        "what_can_be_stolen": verdict.get("what_can_be_stolen"),
        "recommended_action": verdict.get("recommended_action"),

        "permissions_summary": verdict.get("permissions_summary") or {},
        "runtime_behavior": verdict.get("runtime_behavior") or {},
        "execution_graph": verdict.get("execution_graph") or {},
        "recursive_execution_graph": verdict.get("recursive_execution_graph") or {},
        "wallet_drain_simulation": verdict.get("wallet_drain_simulation") or {},
        "anti_false_positive": verdict.get("anti_false_positive") or {},
        "threat_memory": verdict.get("threat_memory") or {},
        "memory_summary": verdict.get("memory_summary") or {},
        "campaign": verdict.get("campaign") or {},
        "wallet_profile": verdict.get("wallet_profile") or {},
        "contract_identity": verdict.get("contract_identity") or raw.get("contract_identity") or {},
        "internal_verdict": (verdict.get("details") or {}).get("internal_verdict") if isinstance(verdict.get("details"), dict) else {},
        "scam_family": verdict.get("scam_family") or ((verdict.get("details") or {}).get("scam_family") if isinstance(verdict.get("details"), dict) else {}) or {},
        "multi_chain_intelligence": verdict.get("multi_chain_intelligence") or ((verdict.get("details") or {}).get("multi_chain_intelligence") if isinstance(verdict.get("details"), dict) else {}) or {},
        "ai_investigation": verdict.get("ai_investigation") or ((verdict.get("details") or {}).get("ai_investigation") if isinstance(verdict.get("details"), dict) else {}) or {},

        "noytrix_url_intelligence": noytrix_url_intelligence,

        "evidence": verdict.get("evidence") or raw.get("evidence") or [],
        "sources": verdict.get("sources") or raw.get("sources") or [],
    }


def _compact_context(ctx: Dict[str, Any], max_chars: int = 14000) -> str:
    text = json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...TRUNCATED"


def _ai_explanation_unavailable(
    lang: str = "en",
    mode: str = "detailed",
    reason: str | None = None,
    model: str | None = None,
) -> Dict[str, Any]:
    lang = str(lang or "en").lower()
    if lang.startswith("ru"):
        lang = "ru"
    elif lang.startswith("uk") or lang.startswith("ua"):
        lang = "uk"
    else:
        lang = "en"

    messages = {
        "en": "AI explanation is temporarily unavailable. Please try again later.",
        "ru": "AI-?????????? ???????? ??????????. ?????????? ????????? ?????.",
        "uk": "AI-????????? ????????? ??????????. ????????? ????????? ???????.",
    }
    text = messages[lang]
    structured = {
        "short": text,
        "details": text,
        "risks": [],
        "actions": [],
        "confidence_note": text,
        "severity_label": "",
        "next_step_priority": text,
        "attack_scenario": "",
        "hidden_danger": "",
        "attacker_intent": "",
        "loss_scenario": "",
    }
    return {
        "available": False,
        "reason": reason or "openai_unavailable",
        "model": model,
        "language": lang,
        "mode": mode if mode in {"short", "detailed"} else "detailed",
        "text": text,
        "structured": structured,
    }


async def generate_ai_security_explanation(
    verdict: Dict[str, Any],
    lang: str = "en",
    mode: str = "detailed",
) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _ai_explanation_unavailable(
            verdict,
            lang,
            mode if "mode" in locals() else "detailed",
            "openai_api_key_missing",
            None,
        )

    try:
        from openai import AsyncOpenAI
    except Exception:
        return _ai_explanation_unavailable(
            verdict,
            lang,
            mode if "mode" in locals() else "detailed",
            "openai_package_missing",
            None,
        )

    ctx = build_ai_explanation_context(verdict)
    context_json = _compact_context(ctx)

    language_rule = {
        "ru": "Answer in Russian.",
        "uk": "Answer in Ukrainian.",
        "en": "Answer in English.",
    }.get(str(lang or "en").lower(), "Answer in English.")

    threat_specific_prompt = build_threat_specific_prompt(ctx)

    system = (
        "You are Noytrix AI Security Analyst for Web3. "
        "Use only the structured backend data provided. "
        "Do not invent facts. Do not claim exact financial loss unless the backend provides it. "
        "If evidence is weak or unavailable, say that clearly. "
        "Write for a normal crypto user, not for a developer. "
        "Avoid raw technical terms unless they are necessary; when used, explain them simply. "
        "Do not use panic language. Be calm, clear, and direct. "
        "Do not repeat the same warning in different words. "
        "Do not say something is definitely a scam unless backend evidence supports it. "
        "If the result is safe, still explain the limits of the check briefly. "
        "Never say '100% safe', 'fully safe', or 'guaranteed safe'. "
        "If confidence is low or source data is empty, clearly say that the check found no evidence, not that the object is definitely safe. "
        "If a wallet has no history, explain that an empty wallet history is not proof of trust. "
        "If URL scan sources are clean but final dynamic behavior is unknown, explain that future wallet actions still need separate checking. "
        "Actions must be specific and useful. "
        "For dangerous transactions, suggest not signing, disconnecting wallet, checking approvals, and using a fresh wallet if already signed. "
        "For suspicious links, suggest not connecting wallet and checking the official domain. "
        "For wallets with little data, suggest not sending funds based only on this check. "
        "For safe results, suggest continuing only with normal caution and checking every future signature separately. "
        "Do not give generic explanations. Always explain WHY the object received this risk level using concrete backend evidence. "
        "Write like a calm senior crypto security analyst: clear, confident, practical, and user-protective. "
        "If hidden danger exists, explain what is hidden from the normal user and why it matters. "
        "Do not claim hidden scripts, wallet-drainer scripts, or malicious JavaScript as fact unless js_behavior, wallet_trap, runtime_behavior, or execution_graph provides evidence. "
        "If ai_investigation.evidence_links exists, base the explanation on those linked evidence items and mention the strongest evidence IDs naturally when useful. "
        "If multi_chain_intelligence exists, explain chain context as context only and never as risk by itself. "
        "If JavaScript evidence is clean or missing, phrase script-based danger only as a possible future risk, not as confirmed behavior. "
        "If social manipulation exists, explain the psychological trick: fake bonus, urgency, impersonation, guaranteed profit, deposit pressure, or trust abuse. "
        "If an attack chain exists, explain the flow in plain language: first action, hidden action, possible consequence. "
        "For signatures or transactions, always explain what may happen after signing, not only what is visible before signing. "
        "Avoid vague phrases like 'be careful' unless followed by a specific action. "
        "Never over-comfort the user on safe results; say the current check found no evidence, but future signatures still need checking. "
        "Explain the likely attack scenario step-by-step in human language when enough evidence exists. "
        "Explain what may be hidden from the user interface, transaction popup, or website flow. "
        "Clearly explain HOW the user could lose funds, tokens, NFTs, wallet access, or approvals. "
        "If social engineering patterns exist, explain the manipulation tactic: urgency, fake support, fake rewards, impersonation, trust abuse, guaranteed profit, recovery scam, or emotional pressure. "
        "Explain the likely attacker intent and what the attacker is trying to achieve. "
        "If execution behavior exists, explain the execution flow in plain language: what the user sees first, what hidden action may happen next, and the possible final outcome. "
        "For wallet-drain style behavior, clearly explain that signing can create future risk even without immediate theft. "
        "If confidence is high, explain WHY confidence is high using concrete evidence sources and repeated signals. "
        "If confidence is low or mixed, explain WHY uncertainty exists and which signals are missing or incomplete. "
        "Avoid robotic assistant wording. Write like an experienced crypto threat analyst speaking to a real user. "
        "Do not just list risks — connect them into a believable attack narrative. "
        "If evidence suggests phishing or wallet draining, explain the likely real-world consequence to the user in practical terms. "
        "Prioritize clarity over technical jargon, but explain dangerous blockchain behavior accurately when necessary. "
        "Return ONLY valid JSON with this exact shape: "
        "{\"short\":string,\"details\":string,\"risks\":[string],\"actions\":[string],\"confidence_note\":string,\"severity_label\":string,\"next_step_priority\":string,\"attack_scenario\":string,\"hidden_danger\":string,\"attacker_intent\":string,\"loss_scenario\":string}. "
        "No markdown. No extra text. "
        + threat_specific_prompt + " "
        + language_rule
    )

    mode = str(mode or "detailed").lower().strip()
    if mode not in {"short", "detailed"}:
        mode = "detailed"

    mode_rule = (
        "Use short mode: short must be one very clear sentence, details must be no more than 2 short sentences, risks/actions max 2 items each. "
        if mode == "short"
        else "Use detailed mode: details should explain the situation clearly, risks/actions may contain up to 5 useful items each. "
    )

    user = (
        "Create a user-facing security explanation from this backend verdict JSON. "
        "The explanation must be clear for a normal crypto user. "
        "Fields: short = one sentence; details = fuller explanation; risks = concrete risks; actions = what user should do; confidence_note = uncertainty/limits; severity_label = user-friendly danger label; next_step_priority = the single most important next action; attack_scenario = likely attack flow; hidden_danger = what user may not see; attacker_intent = what attacker wants; loss_scenario = how user may lose funds/assets/access. "
        "You MUST include ALL fields even if some are short. "
        "Example JSON shape: "
        "{"
        "\"short\":\"...\","
        "\"details\":\"...\","
        "\"risks\":[\"...\"],"
        "\"actions\":[\"...\"],"
        "\"confidence_note\":\"...\","
        "\"severity_label\":\"...\","
        "\"next_step_priority\":\"...\","
        "\"attack_scenario\":\"...\","
        "\"hidden_danger\":\"...\","
        "\"attacker_intent\":\"...\","
        "\"loss_scenario\":\"...\""
        "}. "
        + mode_rule +
        "\n\n"
        f"{context_json}"
    )

    model = os.getenv("NOYTRIX_AI_EXPLAINER_MODEL", "gpt-4o-mini")
    cache_key = _cache_key(context_json, str(lang or "en").lower(), mode, model)
    cached = get_cached_ai_explanation(cache_key)

    if cached:
        return cached

    try:
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            temperature=0.2,
            max_tokens=450,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

        text = (resp.choices[0].message.content or "").strip()

        structured = None
        try:
            structured = json.loads(text)
        except Exception:
            fallback_note = {
                "ru": "Модель вернула обычный текст вместо структурированного ответа.",
                "uk": "Модель повернула звичайний текст замість структурованої відповіді.",
                "en": "The model returned plain text instead of structured JSON.",
            }.get(str(lang or "en").lower(), "The model returned plain text instead of structured JSON.")

            structured = {
                "short": text[:300],
                "details": text,
                "risks": [],
                "actions": [],
                "confidence_note": fallback_note,
            }

        structured = validate_ai_explanation_output(structured, ctx)

        result = {
            "available": True,
            "reason": None,
            "model": model,
            "language": lang,
            "mode": mode,
            "cache_hit": False,
            "text": structured.get("details") or structured.get("short") or text,
            "structured": structured,
            "_cache": {
                "hit": False,
                "provider": "sqlite",
            },
        }

        save_cached_ai_explanation(cache_key, str(lang or "en").lower(), mode, model, result)

        return result
    except Exception as e:
        return _ai_explanation_unavailable(
            verdict,
            lang,
            mode if "mode" in locals() else "detailed",
            str(e)[:300],
            model,
        )


def validate_ai_explanation_output(
    structured: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    structured = structured or {}
    context = context or {}

    estimated_loss = (
        (context.get("wallet_drain_simulation") or {}).get("estimated_loss_usd")
    )

    def clean_list(value):
        if not isinstance(value, list):
            return []
        return [str(x).strip() for x in value if str(x or "").strip()][:5]

    cleaned = {
        "short": str(structured.get("short") or "").strip()[:500],
        "details": str(structured.get("details") or "").strip()[:2000],
        "risks": clean_list(structured.get("risks")),
        "actions": clean_list(structured.get("actions")),
        "confidence_note": str(structured.get("confidence_note") or "").strip()[:500],
        "severity_label": str(structured.get("severity_label") or "").strip()[:120],
        "next_step_priority": str(structured.get("next_step_priority") or "").strip()[:300],
        "attack_scenario": str(structured.get("attack_scenario") or "").strip()[:1200],
        "hidden_danger": str(structured.get("hidden_danger") or "").strip()[:1200],
        "attacker_intent": str(structured.get("attacker_intent") or "").strip()[:1200],
        "loss_scenario": str(structured.get("loss_scenario") or "").strip()[:1200],
    }

    combined = " ".join([
        cleaned["short"],
        cleaned["details"],
        " ".join(cleaned["risks"]),
        " ".join(cleaned["actions"]),
    ]).lower()

    hallucination_flags = []

    if estimated_loss is None:
        money_patterns = ["$", "usd", "usdt", "доллар", "долларов", "грив", "євро", "euro"]
        if any(x in combined for x in money_patterns):
            hallucination_flags.append("possible_exact_loss_without_backend_amount")

    if hallucination_flags:
        cleaned["confidence_note"] = (
            (cleaned.get("confidence_note") + " " if cleaned.get("confidence_note") else "")
            + "Exact loss amount was not confirmed by backend data."
        ).strip()

    cleaned.setdefault("attack_scenario", str(structured.get("attack_scenario") or "").strip()[:1200])
    cleaned.setdefault("hidden_danger", str(structured.get("hidden_danger") or "").strip()[:1200])
    cleaned.setdefault("attacker_intent", str(structured.get("attacker_intent") or "").strip()[:1200])
    cleaned.setdefault("loss_scenario", str(structured.get("loss_scenario") or "").strip()[:1200])

    cleaned["_guardrails"] = {
        "applied": True,
        "flags": hallucination_flags,
    }

    return cleaned
