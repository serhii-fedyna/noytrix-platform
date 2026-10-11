from __future__ import annotations

import hashlib
import asyncio
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict


CACHE_DB_PATH = Path("data/ai_explanations_cache.sqlite3")
EXPLANATION_FORMAT_VERSION = "evidence-first-gemini-v5-single-language"


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
    raw = f"{EXPLANATION_FORMAT_VERSION}|{lang}|{mode}|{model}|{context_json}"
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
            "This is a website or link check. Explain domain/page risk, Noytrix threat signals, and what the user should avoid on the site."
        )
    elif kind == "wallet":
        parts.append(
            "This is a wallet or address check. Explain wallet reputation, known activity, memory, source limitations, and avoid claiming future transaction safety."
        )
    elif kind == "contract":
        parts.append(
            "This is a smart contract check. Explain contract identity, spender role, token permissions, honeypot or contract-specific risks if present."
        )
    elif kind in {"token", "ticker"}:
        parts.append(
            "This is a token lookup. State clearly whether the input was an exact contract/mint address or only a ticker. "
            "For an exact token, explain only the supplied market cap, liquidity, holder, sell-simulation, tax, ownership and code-verification facts. "
            "For a ticker-only lookup, do not call it a token safety result: explain that the ticker identifies an asset and that an exact contract or mint is required for holder, honeypot, liquidity and sellability checks."
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
        "assessment_status": verdict.get("assessment_status"),
        "confirmed_red_flag": bool(verdict.get("confirmed_red_flag")),
        "risk_type": verdict.get("risk_type"),
        "summary": verdict.get("summary"),
        "what_can_happen": verdict.get("what_can_happen"),
        "what_can_be_stolen": verdict.get("what_can_be_stolen"),
        "recommended_action": verdict.get("recommended_action"),
        # Object-specific facts are deliberately included before the generic
        # source list.  This lets the explanation speak about actual token,
        # contract, wallet and domain findings instead of producing a generic
        # disclaimer when the scan has usable enrichment.
        "details": verdict.get("details") or raw.get("details") or {},
        "inspection": verdict.get("inspection") or raw.get("inspection") or {},

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
        "ru": "AI-объяснение временно недоступно. Попробуйте повторить позже.",
        "uk": "AI-пояснення тимчасово недоступне. Спробуйте повторити пізніше.",
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
    """Turn a verified scan into a full, evidence-grounded explanation.

    Vertex Gemini is the production AI provider for Noytrix.  The old OpenAI
    implementation silently broke whenever an OpenAI key was absent, even
    though the project already had a working Vertex service account.  Keep the
    response deterministic and evidence-first if Vertex has a transient issue:
    a completed scan must never degrade into a blank AI card.
    """
    ctx = build_ai_explanation_context(verdict)
    context_json = _compact_context(ctx)

    # An unavailable source is neither a clean result nor proof of a threat.
    # Do not give a model room to turn missing Solana/EVM/URL data into an
    # invented attack story. Confirmed evidence still wins during an outage.
    if (
        str(ctx.get("assessment_status") or "").lower() == "insufficient_data"
        and not bool(ctx.get("confirmed_red_flag"))
    ):
        structured = _insufficient_evidence_explanation(ctx, lang)
        return {
            "available": True,
            "degraded": False,
            "reason": "insufficient_verified_evidence",
            "model": "noytrix_evidence_formatter",
            "language": lang,
            "mode": mode if mode in {"short", "detailed"} else "detailed",
            "cache_hit": False,
            "text": structured["details"],
            "structured": structured,
            "_cache": {"hit": False, "provider": "none"},
        }

    language_rule = {
        "ru": "Answer only in Russian. Every user-facing word must be Russian, except a proper name, domain, wallet address, token symbol, or unavoidable product name. Never insert English sentences, headings, or mixed-language fragments.",
        "uk": "Answer only in Ukrainian. Every user-facing word must be Ukrainian, except a proper name, domain, wallet address, token symbol, or unavoidable product name. Never insert English sentences, headings, or mixed-language fragments.",
        "en": "Answer only in English.",
    }.get(str(lang or "en").lower(), "Answer in English.")

    threat_specific_prompt = build_threat_specific_prompt(ctx)

    system = (
        "You are Noytrix AI Security Analyst for Web3. "
        "Use only the structured backend data provided. "
        "Do not mention third-party provider names such as VirusTotal, Google Safe Browsing, urlscan, Etherscan, BscScan, DexScreener, Honeypot, or CoinGecko in the user-facing text. Treat their data as Noytrix risk intelligence. "
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
        "If confidence is high, explain WHY confidence is high using concrete Noytrix evidence signals and repeated signals. "
        "If confidence is low or mixed, explain WHY uncertainty exists and which signals are missing or incomplete. "
        "Avoid robotic assistant wording. Write like an experienced crypto threat analyst speaking to a real user. "
        "Do not just list risks — connect them into a believable attack narrative. "
        "If evidence suggests phishing or wallet draining, explain the likely real-world consequence to the user in practical terms. "
        "Prioritize clarity over technical jargon, but explain dangerous blockchain behavior accurately when necessary. "
        "Produce a complete, helpful explanation that a normal user can act on. "
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
        "Use the supplied evidence only. short must be a one-sentence bottom line. "
        "details must be at most four short sentences: conclusion, strongest evidence, limitation, next action. "
        "Only fill attack_scenario, hidden_danger, attacker_intent, and loss_scenario when the backend contains direct evidence for that field; otherwise return an empty string. "
        "Return at most four concrete risks and three concrete actions. Each item must be tied to evidence or a practical protective step. Never repeat the same fact. "
    )

    user = (
        "Create a user-facing security explanation from this backend verdict JSON. "
        "The explanation must be clear for a normal crypto user. "
        "Fields: short = one sentence; details = fuller explanation; risks = concrete risks; actions = what user should do; confidence_note = uncertainty/limits; severity_label = user-friendly danger label; next_step_priority = the single most important next action; attack_scenario = likely attack flow; hidden_danger = what user may not see; attacker_intent = what attacker wants; loss_scenario = how user may lose funds/assets/access. "
        "Include every JSON key, but use an empty string or empty array when the backend data does not support a field. "
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

    model = os.getenv("NOYTRIX_GEMINI_TEXT_MODEL", "gemini-2.5-flash")
    cache_key = _cache_key(context_json, str(lang or "en").lower(), mode, model)
    cached = get_cached_ai_explanation(cache_key)

    if cached:
        return cached

    schema = {
        "type": "OBJECT",
        "properties": {
            "short": {"type": "STRING"}, "details": {"type": "STRING"},
            "risks": {"type": "ARRAY", "items": {"type": "STRING"}},
            "actions": {"type": "ARRAY", "items": {"type": "STRING"}},
            "confidence_note": {"type": "STRING"}, "severity_label": {"type": "STRING"},
            "next_step_priority": {"type": "STRING"}, "attack_scenario": {"type": "STRING"},
            "hidden_danger": {"type": "STRING"}, "attacker_intent": {"type": "STRING"},
            "loss_scenario": {"type": "STRING"},
        },
        "required": ["short", "details", "risks", "actions", "confidence_note", "severity_label", "next_step_priority", "attack_scenario", "hidden_danger", "attacker_intent", "loss_scenario"],
    }

    try:
        # GeminiClient is synchronous because it is also used by scheduled
        # workers. Offload it so a live scan does not block FastAPI's event loop.
        from automation_os.gemini_client import GeminiClient
        raw = await asyncio.to_thread(
            GeminiClient().generate_json,
            system,
            user,
            schema,
            operation="security_explanation",
            max_tokens=2600,
        )
        structured = validate_ai_explanation_output(raw, ctx, mode)
        result = {
            "available": True,
            "reason": None,
            "model": model,
            "language": lang,
            "mode": mode,
            "cache_hit": False,
            "text": structured.get("details") or structured.get("short"),
            "structured": structured,
            "_cache": {"hit": False, "provider": "sqlite"},
        }
        save_cached_ai_explanation(cache_key, str(lang or "en").lower(), mode, model, result)
        return result
    except Exception as exc:
        # Keep the already-provisioned OpenAI route as a compatibility fallback
        # while Vertex is retried or its service account is rotated. This is
        # still a real model response, not a canned security conclusion.
        legacy_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if legacy_key:
            try:
                from openai import AsyncOpenAI
                legacy_model = (os.getenv("NOYTRIX_AI_EXPLAINER_MODEL") or "gpt-4o-mini").strip()
                legacy_response = await AsyncOpenAI(api_key=legacy_key).chat.completions.create(
                    model=legacy_model,
                    temperature=0.2,
                    max_tokens=1800,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                )
                raw_text = str(legacy_response.choices[0].message.content or "").strip()
                structured = validate_ai_explanation_output(json.loads(raw_text), ctx, mode)
                result = {
                    "available": True, "reason": None, "model": legacy_model, "language": lang, "mode": mode,
                    "cache_hit": False, "text": structured.get("details") or structured.get("short"), "structured": structured,
                    "_cache": {"hit": False, "provider": "sqlite"},
                }
                save_cached_ai_explanation(cache_key, str(lang or "en").lower(), mode, legacy_model, result)
                return result
            except Exception:
                pass
        # A live provider error must not erase a completed security result. This
        # fallback is constructed solely from the scan's own evidence, rather
        # than a generic fixed "unavailable" message.
        structured = _evidence_grounded_fallback(ctx, lang)
        result = {
            "available": True,
            "degraded": True,
            "reason": str(exc)[:300],
            "model": "noytrix_evidence_formatter",
            "language": lang,
            "mode": mode,
            "cache_hit": False,
            "text": structured["details"],
            "structured": structured,
            "_cache": {"hit": False, "provider": "none"},
        }
        return result


def _evidence_grounded_fallback(ctx: Dict[str, Any], lang: str) -> Dict[str, Any]:
    """Build a truthful readable result from the current scan only.

    This is a resilience path, not a canned answer: every finding comes from
    the actual structured evidence returned for this object.
    """
    language = str(lang or "en").lower()
    language = "uk" if language.startswith(("uk", "ua")) else "ru" if language.startswith("ru") else "en"
    level = str(ctx.get("level") or "suspicious").lower()
    score = ctx.get("score")
    evidence = ctx.get("evidence") or []
    findings = []
    for item in evidence:
        if isinstance(item, dict):
            text = " ".join(str(item.get(key) or "").strip() for key in ("text", "label", "code")).strip()
            if text and text not in findings:
                findings.append(text[:300])
    source_count = len([item for item in (ctx.get("sources") or []) if isinstance(item, dict)])
    copies = {
        "en": {
            "short": f"Current result: {level} (risk score {score if score is not None else 'not available'}).",
            "details": (f"Noytrix found {len(findings)} verified signal(s) across {source_count} completed checks." if findings else f"Noytrix completed {source_count} checks but found no verified threat signal.") + " This is a point-in-time result, not a guarantee.",
            "action": "Do not connect, sign, approve, or send funds until the object is independently verified." if level in {"danger", "critical", "high"} else "Treat this as one point-in-time check and verify every future wallet request separately.",
            "confidence": "The conclusion reflects the evidence available at scan time; missing evidence is not proof of safety.",
        },
        "ru": {
            "short": f"Текущий результат: {level} (оценка риска {score if score is not None else 'недоступна'}).",
            "details": (f"Noytrix нашёл {len(findings)} подтверждённых сигналов в {source_count} завершённых проверках." if findings else f"Noytrix выполнил {source_count} проверок, но не нашёл подтверждённых сигналов угрозы.") + " Это оценка на момент проверки, а не гарантия.",
            "action": "Не подключай кошелёк, не подписывай и не отправляй средства, пока объект не будет проверен независимо." if level in {"danger", "critical", "high"} else "Считай это проверкой на конкретный момент и отдельно проверяй каждый будущий запрос кошелька.",
            "confidence": "Вывод отражает данные на момент проверки; отсутствие сигнала не доказывает безопасность.",
        },
        "uk": {
            "short": f"Поточний результат: {level} (оцінка ризику {score if score is not None else 'недоступна'}).",
            "details": (f"Noytrix виявив {len(findings)} підтверджених сигналів у {source_count} завершених перевірках." if findings else f"Noytrix виконав {source_count} перевірок, але не виявив підтверджених сигналів загрози.") + " Це оцінка на момент перевірки, а не гарантія.",
            "action": "Не підключай гаманець, не підписуй і не надсилай кошти, доки об’єкт не буде перевірено незалежно." if level in {"danger", "critical", "high"} else "Вважай це перевіркою на конкретний момент і окремо перевіряй кожен майбутній запит гаманця.",
            "confidence": "Висновок відображає дані на момент перевірки; відсутність сигналу не доводить безпеку.",
        },
    }
    copy = copies[language]
    return validate_ai_explanation_output({
        "short": copy["short"], "details": copy["details"], "risks": findings[:6], "actions": [copy["action"]],
        "confidence_note": copy["confidence"], "severity_label": level.title(), "next_step_priority": copy["action"],
        "attack_scenario": "", "hidden_danger": "", "attacker_intent": "", "loss_scenario": "",
    }, ctx, "detailed")


def _insufficient_evidence_explanation(ctx: Dict[str, Any], lang: str) -> Dict[str, Any]:
    """Return a short, neutral report when required checks did not complete.

    This deliberately contains no hypothesised attack mechanism. A failed RPC
    must never be translated into claims about minting, freezing, draining, or
    a token being safe.
    """
    language = str(lang or "en").lower()
    language = "uk" if language.startswith(("uk", "ua")) else "ru" if language.startswith("ru") else "en"
    copy = {
        "en": {
            "short": "Verification is incomplete: this is not a safety verdict.",
            "details": "Required security data was unavailable during this check. Noytrix could not confirm either a threat or safety from the completed sources. Recheck before connecting a wallet, signing, or sending funds.",
            "risk": "The unavailable check can hide important token or transaction controls.",
            "action": "Do not connect, sign, approve, or send funds until the check completes.",
            "confidence": "A missing source is not proof of safety or proof of a scam.",
            "label": "Verification incomplete",
        },
        "ru": {
            "short": "Проверка не завершена: это не вердикт безопасности.",
            "details": "Во время проверки были недоступны необходимые данные безопасности. Noytrix не может подтвердить ни угрозу, ни безопасность только по завершённым источникам. Повтори проверку до подключения кошелька, подписи или отправки средств.",
            "risk": "Недоступная проверка может скрывать важные настройки токена или транзакции.",
            "action": "Не подключай кошелёк, не подписывай и не отправляй средства, пока проверка не завершится.",
            "confidence": "Недоступный источник не доказывает ни безопасность, ни мошенничество.",
            "label": "Проверка не завершена",
        },
        "uk": {
            "short": "Перевірка не завершена: це не вердикт безпеки.",
            "details": "Під час перевірки були недоступні необхідні дані безпеки. Noytrix не може підтвердити ані загрозу, ані безпеку лише за завершеними джерелами. Повтори перевірку до підключення гаманця, підпису або надсилання коштів.",
            "risk": "Недоступна перевірка може приховувати важливі налаштування токена або транзакції.",
            "action": "Не підключай гаманець, не підписуй і не надсилай кошти, доки перевірка не завершиться.",
            "confidence": "Недоступне джерело не доводить ані безпеку, ані шахрайство.",
            "label": "Перевірка не завершена",
        },
    }[language]
    return validate_ai_explanation_output({
        "short": copy["short"], "details": copy["details"], "risks": [copy["risk"]],
        "actions": [copy["action"]], "confidence_note": copy["confidence"],
        "severity_label": copy["label"], "next_step_priority": copy["action"],
        "attack_scenario": "", "hidden_danger": "", "attacker_intent": "", "loss_scenario": "",
    }, ctx, "detailed")


def validate_ai_explanation_output(
    structured: Dict[str, Any],
    context: Dict[str, Any],
    mode: str = "detailed",
) -> Dict[str, Any]:
    structured = structured or {}
    context = context or {}

    estimated_loss = (
        (context.get("wallet_drain_simulation") or {}).get("estimated_loss_usd")
    )

    def plain_text(value) -> str:
        """Keep model prose readable even when a provider ignores the no-Markdown rule.

        The UI renders risks, actions and report sections itself. Passing through
        Markdown markers here produces literal asterisks/backticks on mobile,
        web and bot surfaces instead of a security report a person can scan.
        """
        text = str(value or "").replace("\\*", "*").replace("\\`", "`")
        text = re.sub(r"```(?:[A-Za-z0-9_-]+)?\s*", "", text)
        text = re.sub(r"`([^`]*)`", r"\1", text)
        text = re.sub(r"(\*\*|__|~~)", "", text)
        text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
        text = re.sub(r"(?m)^\s*(?:[-*+•]|\d+[.)])\s+", "", text)
        text = re.sub(r"\[([^\]\n]+)\]\([^\)]+\)", r"\1", text)
        return " ".join(text.split()).strip()

    def concise_text(value, max_sentences: int, max_chars: int) -> str:
        text = plain_text(value)
        if not text:
            return ""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        compact = " ".join(sentences[:max_sentences]).strip()
        return compact[:max_chars].rstrip()

    def clean_list(value, max_items: int = 6, max_chars: int = 420):
        if not isinstance(value, list):
            return []
        return [concise_text(x, 1, max_chars) for x in value if str(x or "").strip()][:max_items]

    is_short = str(mode or "detailed").lower() == "short"
    short_text = concise_text(structured.get("short"), 1, 320)
    details = short_text if is_short else concise_text(structured.get("details"), 8, 2400)

    cleaned = {
        "short": short_text,
        "details": details,
        "risks": [] if is_short else clean_list(structured.get("risks")),
        "actions": [] if is_short else clean_list(structured.get("actions")),
        "confidence_note": "" if is_short else concise_text(structured.get("confidence_note"), 3, 700),
        "severity_label": concise_text(structured.get("severity_label"), 1, 160),
        "next_step_priority": "" if is_short else concise_text(structured.get("next_step_priority"), 2, 480),
        "attack_scenario": "" if is_short else concise_text(structured.get("attack_scenario"), 4, 1100),
        "hidden_danger": "" if is_short else concise_text(structured.get("hidden_danger"), 4, 1100),
        "attacker_intent": "" if is_short else concise_text(structured.get("attacker_intent"), 3, 850),
        "loss_scenario": "" if is_short else concise_text(structured.get("loss_scenario"), 4, 1100),
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

    cleaned["_guardrails"] = {
        "applied": True,
        "flags": hallucination_flags,
    }

    return cleaned
