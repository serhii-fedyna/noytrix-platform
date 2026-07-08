from scamshield.intelligence.threat_memory import init_threat_memory, remember_many_from_verdict, remember_relations_from_verdict, get_entity_memory, build_memory_summary
# main.py (RU/EN) — Noytrix backend (FULL FILE, production-oriented)

# =========================================================
# ✅ ScamShield production redesign:
# - real source statuses: malicious / clean / no_data / timeout / invalid_key / error
# - real multi-API URL verification (VT / Google Safe Browsing / urlscan if configured)
# - red-flag priority: any confirmed malicious external source => Dangerous / Critical
# - could_not_verify / no_match are NOT treated as Safe
# - content analysis for HTML/page text
# - brand spoof / impersonation risk
# - correct object detection: url / domain / wallet / contract / ticker / text
# - EVM address checks via Etherscan / BscScan if configured
# - token/ticker enrichment via DexScreener / CoinGecko / Honeypot
# - evidence / source reporting cleaned up
# - vote pipeline fixed (app key + sqlite persistence + one user = one vote)
# - community/top scams endpoints for Home
# - RU/EN scan localization
#
# ✅ Existing app features preserved:
# - /events robust alias
# - background loops + quota + news + prices + immunity + votes
# - guest PRO support
# - profile stats / achievements / overview
# - OneSignal primary push provider
# =========================================================

import os
import re
import jwt
import time
import json
import math
import httpx
import random
import asyncio
import sqlite3
import smtplib
from email.mime.text import MIMEText
import hashlib
import pathlib as _p
import feedparser
import html
import base64
import requests

from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlparse, quote
from datetime import datetime, timezone, timedelta

from bs4 import BeautifulSoup
from readability import Document
from dotenv import load_dotenv
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from scan_card_renderer import render_scan_card
from fastapi import FastAPI, Query, Body, HTTPException, Request
from scamshield.intelligence.anti_false_positive import apply_anti_false_positive_layer
from scamshield.intelligence.noytrix_scam_database import lookup_noytrix_scam_database
from scamshield.intelligence.verdict_core import build_internal_verdict
from scamshield.intelligence.scam_family import classify_scam_family
from scamshield.intelligence.multichain import build_multichain_intelligence
from scamshield.intelligence.threat_collectors import autonomous_collector_loop
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest
from scamshield.compatibility.legacy_fields import attach_legacy_fields
from scamshield.core.levels import normalize_level, legacy_level, normalize_score, enforce_risk_floor
from scamshield.core.scoring import score_scan
from scamshield.runtime.approve import build_approve_runtime_fields
from scamshield.runtime.behavior import analyze_transaction_behavior
from scamshield.runtime.execution_graph import build_execution_graph, build_recursive_execution_graph
from scamshield.runtime.drain_simulator import simulate_wallet_drain
from scamshield.runtime.contract import build_runtime_contract, normalize_runtime_payload
from scamshield.runtime.signature_simulator import simulate_signature
from scamshield.ai.explainer import build_ai_explanation_context, generate_ai_security_explanation, _cache_connect
from scamshield.ai.investigation import build_ai_investigation
from scamshield.url_intel.domain_age import analyze_domain_age
from scamshield.url_intel.redirect_chain import analyze_redirect_chain
from scamshield.url_intel.wallet_trap import analyze_wallet_trap
from scamshield.url_intel.crypto_lure import analyze_crypto_lure
from scamshield.url_intel.js_behavior import analyze_js_behavior
from scamshield.url_intel.headless_sandbox import analyze_headless_sandbox
from scamshield.url_intel.obfuscation import analyze_obfuscated_javascript
from scamshield.url_intel.compromised_site import analyze_compromised_legitimate_site
from scamshield.url_intel.infrastructure import analyze_infrastructure
from scamshield.url_intel.visual_phishing import analyze_visual_phishing
from scamshield.url_intel.advanced_intel import analyze_advanced_url_intel
from scamshield.url_intel.fusion import build_url_intelligence
try:
    from scamshield.intelligence.postgres_intelligence import (
        upsert_entity as pg_upsert_entity,
        get_cached_verdict as pg_get_cached_verdict,
        save_cached_verdict as pg_save_cached_verdict,
        get_entity_graph_context as pg_get_entity_graph_context,
    )
except Exception:
    pg_upsert_entity = None
    pg_get_cached_verdict = None
    pg_save_cached_verdict = None
    pg_get_entity_graph_context = None
from scamshield.ai.security_judge import generate_ai_security_judge
from scamshield.runtime.permissions import build_permissions_summary
from scamshield.runtime.spender import build_spender_reputation
from scamshield.runtime.spender_engine import build_spender_reputation as build_spender_reputation_engine
from scamshield.ux.risk_blocks import ensure_ux_risk_blocks
from scamshield.ux.url_risk import build_url_risk_blocks
from scamshield.ux.tx_risk import build_tx_risk_blocks
from scamshield.ux.contract_risk import build_contract_risk_blocks
from scamshield.runtime.drainer import detect_drainer_patterns
from scamshield.runtime.tx_decoder import decode_evm_tx_input
from pydantic import BaseModel

from auth.router import router as auth_router
from iap_router import router as iap_router
from calendar_router import router as calendar_router

# Optional legacy module helpers (kept for compatibility / fallback only)
try:
    from security_engine import looks_url as _legacy_looks_url, scan_text as _legacy_scan_text
except Exception:
    _legacy_looks_url = None
    _legacy_scan_text = None

try:
    from security_db import immunity_compute as _community_immunity_compute
except Exception:
    def _community_immunity_compute(input_value: str, kind: str | None = None):
        return {
            "input": input_value,
            "kind": kind or "unknown",
            "community_verdict": "unknown",
            "safe_votes": 0,
            "scam_votes": 0,
            "total_users": 0,
            "immunity_score": 0,
        }

# =========================================================
# ENV
# =========================================================
load_dotenv("/root/backend/.env")

JWT_SECRET = os.getenv("JWT_SECRET", "devsecret_change_me")
JWT_ALG = "HS256"

COINMARKETCAL_API_KEY = os.getenv("COINMARKETCAL_API_KEY", "").strip()

VT_API_KEY = (os.getenv("VT_API_KEY") or "").strip()
GOOGLE_SAFE_BROWSING_KEY = (os.getenv("GOOGLE_SAFE_BROWSING_KEY") or "").strip()
URLSCAN_API_KEY = (os.getenv("URLSCAN_API_KEY") or "").strip()
NOYTRIX_INTERNAL_MODE = str(os.getenv("NOYTRIX_INTERNAL_MODE") or "true").strip().lower() in {"1", "true", "yes", "on"}
ETHERSCAN_API_KEY = (os.getenv("ETHERSCAN_API_KEY") or "").strip()
BSCSCAN_API_KEY = (os.getenv("BSCSCAN_API_KEY") or "").strip()
HONEYPOT_API_BASE = (os.getenv("HONEYPOT_API_BASE") or "https://api.honeypot.is").strip().rstrip("/")
ENABLE_DERIVATIVES_CALENDAR = (os.getenv("ENABLE_DERIVATIVES_CALENDAR", "0").strip() == "1")

SCAN_TIMEOUT = float(os.getenv("SCAN_TIMEOUT_SEC", "8"))
SCAN_MAX_BYTES = int(os.getenv("SCAN_MAX_BYTES", "800000"))  # 800 KB html max
MAX_REDIRECTS = int(os.getenv("SCAN_MAX_REDIRECTS", "6"))

DAILY_FREE_LIMIT = int(os.getenv("DAILY_FREE_LIMIT", "4"))
FREE_SCAN_DAILY_FREE_LIMIT = DAILY_FREE_LIMIT  # legacy alias

NOYTRIX_APP_KEY = (os.getenv("NOYTRIX_APP_KEY") or "").strip()
APP_KEY_HEADER = "x-app-key"

ONESIGNAL_APP_ID = (os.getenv("ONESIGNAL_APP_ID") or "").strip()
ONESIGNAL_API_KEY = (os.getenv("ONESIGNAL_API_KEY") or "").strip()

print("[ENV] APP_ENV =", os.getenv("APP_ENV"))
print("[ENV] OPENAI set =", bool(os.getenv("OPENAI_API_KEY")))
print("[ENV] VT set =", bool(VT_API_KEY))
print("[ENV] GSB set =", bool(GOOGLE_SAFE_BROWSING_KEY))
print("[ENV] URLSCAN set =", bool(URLSCAN_API_KEY))
print("[ENV] ETHERSCAN set =", bool(ETHERSCAN_API_KEY))
print("[ENV] BSCSCAN set =", bool(BSCSCAN_API_KEY))
print("[ENV] HONEYPOT base =", HONEYPOT_API_BASE)

# =========================================================
# APP + CORS + ROUTERS
# =========================================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://noytrix.com","https://www.noytrix.com","https://api.noytrixapp.com","https://noytrixapp.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(calendar_router, prefix="/api")
app.include_router(auth_router, prefix="/auth")
app.include_router(iap_router, prefix="/iap")

# =========================================================
# I18N
# =========================================================
def _norm_lang(x: str | None) -> str:
    x = (x or "").strip().lower()
    if x.startswith("ru"):
        return "ru"
    if x.startswith("uk") or x.startswith("ua"):
        return "uk"
    return "en"

def _lang_from_accept_language(accept: str | None) -> str:
    if not accept:
        return "en"
    low = accept.lower()
    if "uk" in low or "ua" in low:
        return "uk"
    if "ru" in low:
        return "ru"
    if "en" in low:
        return "en"
    return "en"

def get_lang(request: Request | None, lang_q: str | None) -> str:
    if lang_q:
        return _norm_lang(lang_q)
    if request:
        return _lang_from_accept_language(request.headers.get("accept-language"))
    return "en"

I18N = {
    "en": {
        "safe": "Safe",
        "suspicious": "Suspicious",
        "danger": "Danger",
        "critical": "Critical / Scam",
        "unknown": "Unknown",
        "news_default_explain": "Crypto market news. Evaluate impact by liquidity, regulation, integrations, and price/volume reaction.",
        "hint_listing": "Listing/admission to an exchange typically increases attention and liquidity.",
        "hint_partnership": "Partnership/integration is usually a positive long-term signal.",
        "hint_hack": "Negative: hack/exploit/leak. Often causes price drop and trust loss.",
        "hint_reg": "Regulatory risk. Often pressures price in the short term.",
        "hint_funding": "Funding/rounds: boosts development and often positive sentiment.",
        "hint_upgrade": "Technical upgrade/release. Watch execution quality and adoption.",
        "quota_exceeded": "Daily FREE limit reached. Upgrade to PRO for unlimited.",
        "forbidden": "Forbidden.",
        "missing_input": "Missing input.",
        "scan_failed": "Scan failed.",
        "source_malicious": "Malicious",
        "source_clean": "Clean",
        "source_no_data": "No data",
        "source_timeout": "Timeout",
        "source_invalid_key": "Invalid key / not configured",
        "source_quota": "Quota exceeded",
        "source_error": "Error",
        "object_url": "URL",
        "object_domain": "Domain",
        "object_wallet": "Wallet",
        "object_contract": "Contract",
        "object_ticker": "Ticker",
        "object_text": "Text",
    },
    "ru": {
        "safe": "Безопасно",
        "suspicious": "Подозрительно",
        "danger": "Опасно",
        "critical": "Критично / Скам",
        "unknown": "Неизвестно",
        "news_default_explain": "Новость по крипторынку. Оцени влияние по фактам: ликвидность, регуляторные риски, интеграции, реакция цены/объёма.",
        "hint_listing": "Листинг/допуск на биржу обычно повышает интерес и ликвидность монеты.",
        "hint_partnership": "Партнёрство или интеграция — хороший долгосрочный сигнал.",
        "hint_hack": "Негатив: взлом/уязвимость. Возможна просадка цены и падение доверия.",
        "hint_reg": "Регуляторный риск. В краткосроке часто давит цену.",
        "hint_funding": "Инвестиции/раунд. Усиливает развитие проекта, часто позитив.",
        "hint_upgrade": "Техническое обновление. Смотри на качество и успешность релиза.",
        "quota_exceeded": "Дневной лимит FREE исчерпан. PRO даёт безлимит.",
        "forbidden": "Доступ запрещён.",
        "missing_input": "Пустой input.",
        "scan_failed": "Ошибка сканирования.",
        "source_malicious": "Опасно",
        "source_clean": "Чисто",
        "source_no_data": "Нет данных",
        "source_timeout": "Таймаут",
        "source_invalid_key": "Неверный ключ / не настроено",
        "source_quota": "Квота исчерпана",
        "source_error": "Ошибка",
        "object_url": "Ссылка",
        "object_domain": "Домен",
        "object_wallet": "Кошелёк",
        "object_contract": "Контракт",
        "object_ticker": "Тикер",
        "object_text": "Текст",
    },
}

def tr(lang: str, key: str) -> str:
    return (I18N.get(lang) or I18N["en"]).get(key, (I18N["en"].get(key, key)))

# =========================================================
# SIMPLE MEMORY CACHE
# =========================================================
_cache: Dict[str, Dict[str, Any]] = {}

def cache_get(key: str):
    rec = _cache.get(key)
    if not rec:
        return None
    if rec["exp"] and rec["exp"] < time.time():
        return None
    return rec["val"]

def cache_set(key: str, val: Any, ttl_sec: int):
    _cache[key] = {"val": val, "exp": time.time() + ttl_sec}

# =========================================================
# APP KEY GUARD
# =========================================================
def _extract_candidate_app_keys(request: Request) -> list[str]:
    candidates: list[str] = []
    for hdr in ("x-app-key", "x_app_key", "x-api-key", "x_api_key"):
        v = (request.headers.get(hdr) or "").strip()
        if v:
            candidates.append(v)

    auth = (request.headers.get("authorization") or request.headers.get("Authorization") or "").strip()
    if auth:
        low = auth.lower()
        if low.startswith("bearer "):
            candidates.append(auth[7:].strip())
        elif low.startswith("apikey "):
            candidates.append(auth[7:].strip())
        else:
            candidates.append(auth)

    return [c.strip().strip('"').strip("'") for c in candidates if c and c.strip()]

def _has_valid_app_key(request: Request) -> bool:
    if not NOYTRIX_APP_KEY:
        return True
    valid = NOYTRIX_APP_KEY.strip().strip('"').strip("'")
    for got in _extract_candidate_app_keys(request):
        if got == valid:
            return True
    return False

def require_app_key(request: Request, lang: str = "en") -> None:
    if not _has_valid_app_key(request):
        raise HTTPException(status_code=403, detail=tr(lang, "forbidden"))

# =========================================================
# PATHS / DB
# =========================================================
BASE_DIR = _p.Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SCAN_DB_PATH = DATA_DIR / "scan_votes.sqlite3"
GUEST_PRO_DB_PATH = DATA_DIR / "guest_pro.sqlite3"
QUOTA_DB_PATH = DATA_DIR / "quota.sqlite3"
PROFILE_DB_PATH = DATA_DIR / "profile.sqlite3"
APP_DB_PATH = BASE_DIR / "app.db"

API_KEYS_DB_PATH = DATA_DIR / "api_keys.sqlite3"
SPENDER_REPUTATION_DB_PATH = DATA_DIR / "spender_reputation.sqlite3"

# =========================================================
# B2B API KEYS / USAGE / LOGS
# =========================================================
def _api_db_connect():
    conn = sqlite3.connect(API_KEYS_DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _sha256_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _spender_rep_db_connect():
    conn = sqlite3.connect(SPENDER_REPUTATION_DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

def init_spender_reputation_db():
    conn = _spender_rep_db_connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS spender_reputation (
                address TEXT PRIMARY KEY,
                label TEXT,
                category TEXT,
                trust TEXT NOT NULL DEFAULT 'unknown',
                risk TEXT NOT NULL DEFAULT 'unknown',
                reasons TEXT,
                source TEXT,
                first_seen TEXT,
                last_seen TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS spender_runtime_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                domain TEXT,
                method TEXT,
                level TEXT,
                unlimited INTEGER NOT NULL DEFAULT 0,
                drainer_flags TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _track_spender_runtime_event(address: str, domain: str | None, method: str | None, level: str | None, unlimited: bool, drainer_flags: list | None):
    addr = str(address or "").lower().strip()
    if not RE_EVM_ADDR.match(addr):
        return

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn = _spender_rep_db_connect()
    try:
        conn.execute("""
            INSERT INTO spender_runtime_events
            (address,domain,method,level,unlimited,drainer_flags,created_at)
            VALUES (?,?,?,?,?,?,?)
        """, (
            addr,
            str(domain or ""),
            str(method or ""),
            str(level or ""),
            1 if unlimited else 0,
            json.dumps(drainer_flags or [], ensure_ascii=False),
            now_iso,
        ))
        conn.commit()
    finally:
        conn.close()







def _update_wallet_risk_profile(wallet: str | None, data: dict):
    w = str(wallet or "").lower().strip()
    if not RE_EVM_ADDR.match(w):
        return None

    perm = data.get("permissions_summary") or {}
    sim = data.get("simulation") or {}

    unlimited = 1 if perm.get("unlimited") else 0
    risky = 1 if str(perm.get("spender_risk") or "").lower() in {"high", "critical"} else 0
    nft = 1 if sim.get("nft_exposure_possible") else 0

    risk_score = 0
    risk_score += 35 if unlimited else 0
    risk_score += 35 if risky else 0
    risk_score += 20 if nft else 0
    risk_score = min(risk_score, 100)

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    conn = _spender_rep_db_connect()
    try:
        old = conn.execute("SELECT * FROM wallet_risk_profiles WHERE wallet=? LIMIT 1", (w,)).fetchone()

        unlimited_total = unlimited + (int(old["unlimited_approvals"] or 0) if old else 0)
        risky_total = risky + (int(old["risky_spenders"] or 0) if old else 0)
        nft_total = max(nft, int(old["nft_exposure"] or 0) if old else 0)
        final_score = min(max(risk_score, int(old["risk_score"] or 0) if old else 0), 100)

        conn.execute("""
            INSERT OR REPLACE INTO wallet_risk_profiles
            (wallet,chain,risk_score,unlimited_approvals,risky_spenders,estimated_exposure_usd,nft_exposure,last_seen)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            w,
            "evm",
            final_score,
            unlimited_total,
            risky_total,
            0,
            nft_total,
            now_iso,
        ))
        conn.commit()

        return {
            "wallet": w,
            "chain": "evm",
            "risk_score": final_score,
            "unlimited_approvals": unlimited_total,
            "risky_spenders": risky_total,
            "nft_exposure": nft_total,
            "last_seen": now_iso,
        }
    finally:
        conn.close()


def _build_runtime_simulation(data: dict) -> dict:
    perm = data.get("permissions_summary") or {}
    tx = (data.get("details") or {}).get("transaction") or {}
    typed = data.get("typed_signature") or {}

    spender = perm.get("spender") or tx.get("spender") or typed.get("spender")
    spender_label = perm.get("spender_label") or ((perm.get("spender_reputation") or {}).get("label"))
    spender_risk = perm.get("spender_risk") or ((perm.get("spender_reputation") or {}).get("risk"))

    token_symbol = (
        perm.get("token_symbol")
        or tx.get("token_symbol")
        or ((perm.get("tokens") or ["token"])[0] if isinstance(perm.get("tokens"), list) and perm.get("tokens") else "token")
    )

    unlimited = bool(perm.get("unlimited"))
    can_spend = bool(perm.get("can_spend"))
    spend_limit = perm.get("spend_limit") or ("unlimited" if unlimited else None)

    effects = []
    losses = []
    warnings = []
    suggestions = []

    if can_spend:
        effects.append(f"The spender receives permission to spend your {token_symbol}.")
    if spender:
        effects.append(f"Permission target: {spender_label or spender}.")
    if spend_limit:
        effects.append(f"Spending limit: {spend_limit}.")
    if spender_risk:
        effects.append(f"Spender risk: {str(spender_risk).upper()}.")

    if unlimited:
        losses.append(f"All approved {token_symbol} can be drained later.")
        warnings.append("The spender can use this permission later without another wallet popup.")
        suggestions.append("Do not sign unless you fully trust this spender.")
        suggestions.append("If already signed, revoke the approval immediately.")

    if spender_risk in {"critical", "high"}:
        warnings.append("This spender is marked as high-risk by reputation intelligence.")

    if data.get("kind") == "typed_signature" or typed:
        effects.append("This is a typed signature, not a normal visible token transfer.")
        warnings.append("Typed signatures can hide Permit2 or marketplace permissions.")

    summary = (
        f"This action may allow {spender_label or 'the spender'} to spend your {token_symbol}."
        if can_spend else
        "No direct token-spending effect detected yet."
    )

    estimated_token_exposure = "unlimited" if unlimited else spend_limit
    estimated_wallet_exposure_usd = None

    if unlimited and token_symbol == "USDT":
        estimated_wallet_exposure_usd = "ALL_USDT_BALANCE"

    approval_scope = "unlimited" if unlimited else "limited"

    nft_exposure_possible = bool(
        "permit2" in str(data).lower()
        or "setapprovalforall" in str(data).lower()
    )

    return {
        "available": bool(effects or losses or warnings),
        "type": "pre_signature_simulation",

        "asset": token_symbol,
        "spender": spender,
        "spender_label": spender_label,
        "spender_risk": spender_risk,

        "spend_limit": spend_limit,
        "approval_scope": approval_scope,

        "estimated_token_exposure": estimated_token_exposure,
        "estimated_wallet_exposure_usd": estimated_wallet_exposure_usd,

        "nft_exposure_possible": nft_exposure_possible,

        "what_happens": effects,
        "possible_losses": losses,
        "warnings": warnings,
        "suggestions": suggestions,

        "summary": summary
    }

def _get_campaign_for_spender(address: str) -> dict | None:
    addr = str(address or "").lower().strip()
    if not RE_EVM_ADDR.match(addr):
        return None

    conn = _spender_rep_db_connect()
    try:
        row = conn.execute("""
            SELECT campaign_id,spender,domains,events_count,critical_count,first_seen,last_seen,risk
            FROM drainer_campaigns
            WHERE spender=?
            LIMIT 1
        """, (addr,)).fetchone()

        if not row:
            return None

        data = dict(row)

        try:
            data["domains"] = json.loads(data.get("domains") or "[]")
        except Exception:
            data["domains"] = []

        return data

    finally:
        conn.close()


def _campaign_id_for_spender(address: str) -> str:
    addr = str(address or "").lower().strip()
    if not RE_EVM_ADDR.match(addr):
        return ""
    return "cmp_" + addr[-12:]

def _update_drainer_campaign_for_spender(address: str):
    addr = str(address or "").lower().strip()
    if not RE_EVM_ADDR.match(addr):
        return

    campaign_id = _campaign_id_for_spender(addr)
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    conn = _spender_rep_db_connect()
    try:
        rows = conn.execute("""
            SELECT domain, level, created_at
            FROM spender_runtime_events
            WHERE address=?
            ORDER BY id ASC
        """, (addr,)).fetchall()

        if not rows:
            return

        domains = sorted({str(r["domain"] or "") for r in rows if str(r["domain"] or "").strip()})
        events_count = len(rows)
        critical_count = sum(1 for r in rows if str(r["level"] or "").lower() == "critical")
        first_seen = str(rows[0]["created_at"] or now_iso)
        last_seen = str(rows[-1]["created_at"] or now_iso)

        risk = "critical" if critical_count >= 3 or len(domains) >= 3 else "high"

        conn.execute("""
            INSERT OR REPLACE INTO drainer_campaigns
            (campaign_id, spender, domains, events_count, critical_count, first_seen, last_seen, risk)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            campaign_id,
            addr,
            json.dumps(domains, ensure_ascii=False),
            events_count,
            critical_count,
            first_seen,
            last_seen,
            risk,
        ))

        conn.execute("""
            UPDATE spender_runtime_events
            SET campaign_id=?
            WHERE address=?
        """, (campaign_id, addr))

        conn.commit()
    finally:
        conn.close()


def _auto_escalate_spender_reputation(address: str):
    addr = str(address or "").lower().strip()
    if not RE_EVM_ADDR.match(addr):
        return
    if addr in TRUSTED_SPENDER_BOOK:
        return

    existing = _get_spender_reputation_from_db(addr)
    if existing and existing.get("trust") in {"trusted", "malicious"}:
        return

    conn = _spender_rep_db_connect()
    try:
        row = conn.execute("""
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN level IN ('danger','critical') THEN 1 ELSE 0 END) AS high_risk,
              SUM(CASE WHEN unlimited=1 THEN 1 ELSE 0 END) AS unlimited_count,
              COUNT(DISTINCT domain) AS domains
            FROM spender_runtime_events
            WHERE address=?
        """, (addr,)).fetchone()

        total = int(row["total"] or 0)
        high_risk = int(row["high_risk"] or 0)
        unlimited_count = int(row["unlimited_count"] or 0)
        domains = int(row["domains"] or 0)

        if high_risk >= 3 or unlimited_count >= 2 or domains >= 3:
            now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            conn.execute("""
                INSERT OR REPLACE INTO spender_reputation
                (address,label,category,trust,risk,reasons,source,first_seen,last_seen)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                addr,
                "Auto-detected suspicious spender",
                "auto_runtime_intelligence",
                "malicious" if unlimited_count >= 2 or high_risk >= 3 else "suspicious",
                "critical" if unlimited_count >= 2 or high_risk >= 3 else "high",
                json.dumps(["auto_escalated_runtime_reputation"], ensure_ascii=False),
                "runtime_auto_intel",
                now_iso,
                now_iso,
            ))
            conn.commit()
    finally:
        conn.close()


def _get_spender_reputation_from_db(address: str) -> dict | None:
    addr = str(address or "").lower().strip()
    if not RE_EVM_ADDR.match(addr):
        return None
    conn = _spender_rep_db_connect()
    try:
        row = conn.execute("SELECT * FROM spender_reputation WHERE address=? LIMIT 1", (addr,)).fetchone()
        if not row:
            return None
        reasons = []
        try:
            reasons = json.loads(row["reasons"] or "[]")
        except Exception:
            reasons = [str(row["reasons"] or "db_reputation")]
        return {
            "address": addr,
            "status": "db_reputation",
            "label": row["label"],
            "category": row["category"],
            "trust": row["trust"],
            "risk": row["risk"],
            "reasons": reasons,
            "source": row["source"],
        }
    finally:
        conn.close()


def init_api_keys_db():
    conn = _api_db_connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              key_prefix TEXT NOT NULL,
              key_hash TEXT NOT NULL UNIQUE,
              owner_email TEXT,
              owner_name TEXT,
              company_name TEXT,
              plan_code TEXT NOT NULL DEFAULT 'starter',
              status TEXT NOT NULL DEFAULT 'active',
              monthly_limit INTEGER NOT NULL DEFAULT 10000,
              requests_used_month INTEGER NOT NULL DEFAULT 0,
              current_month TEXT NOT NULL,
              rate_limit_per_minute INTEGER NOT NULL DEFAULT 60,
              allowed_origins TEXT,
              notes TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              expires_at TEXT,
              last_used_at TEXT,
              last_ip TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS api_usage_logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              api_key_id INTEGER,
              key_prefix TEXT,
              endpoint TEXT NOT NULL,
              input_value TEXT,
              input_kind TEXT,
              verdict_level TEXT,
              score INTEGER,
              status_code INTEGER NOT NULL,
              latency_ms INTEGER,
              ip TEXT,
              user_agent TEXT,
              error_code TEXT,
              created_at TEXT NOT NULL
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_status ON api_keys(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_key_time ON api_usage_logs(api_key_id, created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_created ON api_usage_logs(created_at)")
        conn.commit()
    finally:
        conn.close()

def _api_current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")

def _api_client_ip(request: Request) -> str:
    cf_ip = request.headers.get("cf-connecting-ip")
    xff = request.headers.get("x-forwarded-for")
    if cf_ip:
        return cf_ip.strip()
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""

def _api_log_usage(
    api_key_id=None,
    key_prefix=None,
    endpoint="/v1/scan",
    input_value=None,
    input_kind=None,
    verdict_level=None,
    score=None,
    status_code=200,
    latency_ms=None,
    ip=None,
    user_agent=None,
    error_code=None,
):
    try:
        conn = _api_db_connect()
        try:
            conn.execute("""
                INSERT INTO api_usage_logs (
                  api_key_id, key_prefix, endpoint, input_value, input_kind,
                  verdict_level, score, status_code, latency_ms, ip, user_agent,
                  error_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                api_key_id, key_prefix, endpoint, input_value, input_kind,
                verdict_level, score, status_code, latency_ms, ip, user_agent,
                error_code, _utc_now_iso()
            ))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print("[b2b-api] usage log error:", e)


# =========================================================
# SCAMSHIELD CROWD VOTES (SQLite)
# =========================================================
def _scan_db_connect():
    return sqlite3.connect(SCAN_DB_PATH)

def _scan_db_has_column(cur: sqlite3.Cursor, table: str, col: str) -> bool:
    try:
        rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
        return any(str(r[1]) == col for r in rows)
    except Exception:
        return False

def init_scan_db():
    conn = _scan_db_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_votes (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              obj TEXT NOT NULL,
              kind TEXT,
              is_scam INTEGER NOT NULL,
              user_id TEXT,
              reporter_name TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT
            );
            """
        )
        conn.commit()

        if not _scan_db_has_column(cur, "scan_votes", "user_id"):
            cur.execute("ALTER TABLE scan_votes ADD COLUMN user_id TEXT")
        if not _scan_db_has_column(cur, "scan_votes", "reporter_name"):
            cur.execute("ALTER TABLE scan_votes ADD COLUMN reporter_name TEXT")
        if not _scan_db_has_column(cur, "scan_votes", "updated_at"):
            cur.execute("ALTER TABLE scan_votes ADD COLUMN updated_at TEXT")

        cur.execute(
            """
            UPDATE scan_votes
            SET updated_at = COALESCE(updated_at, created_at)
            WHERE updated_at IS NULL OR updated_at = ''
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_scan_votes_obj_kind ON scan_votes(obj, kind)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_scan_votes_updated_at ON scan_votes(updated_at)")
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_scan_votes_obj_kind_user
            ON scan_votes(obj, kind, user_id)
            WHERE user_id IS NOT NULL AND TRIM(user_id) <> ''
            """
        )
        conn.commit()
    finally:
        conn.close()

init_scan_db()
init_api_keys_db()
init_spender_reputation_db()

class ScanVoteIn(BaseModel):
    input: str
    kind: str | None = None
    is_scam: bool = False
    userId: str | None = None
    reporter: str | None = None
    vote: str | None = None
    obj: str | None = None

def _normalize_obj(raw: str) -> str:
    return (raw or "").strip()

def _vote_user_id(request: Request, payload: ScanVoteIn) -> str:
    candidates = [
        payload.userId,
        request.headers.get("x-user-id"),
        request.headers.get("x_user_id"),
        request.headers.get("user-id"),
    ]
    for c in candidates:
        s = (c or "").strip()
        if s:
            return s

    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "unknown")
    return f"ip:{ip}"

def _vote_reporter_name(payload: ScanVoteIn, user_id: str) -> str:
    name = (payload.reporter or "").strip()
    return name or user_id

def _save_reddit_scam_to_community(obj: str, kind: str, post_url: str, title: str) -> bool:
    obj = _normalize_obj(obj)
    kind = _normalize_kind_label_db(kind)
    if not obj:
        return False

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    user_id = "source:reddit"
    reporter_name = "Reddit monitor"

    conn = _scan_db_connect()
    try:
        cur = conn.cursor()
        existing = cur.execute(
            """
            SELECT id
            FROM scan_votes
            WHERE obj=? AND kind=? AND user_id=?
            LIMIT 1
            """,
            (obj, kind, user_id),
        ).fetchone()

        if existing:
            cur.execute(
                """
                UPDATE scan_votes
                SET is_scam=1, reporter_name=?, updated_at=?
                WHERE id=?
                """,
                (reporter_name, now_iso, existing[0]),
            )
        else:
            cur.execute(
                """
                INSERT INTO scan_votes
                  (obj, kind, is_scam, user_id, reporter_name, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?, ?, ?)
                """,
                (obj, kind, user_id, reporter_name, now_iso, now_iso),
            )
        conn.commit()
        return True
    except Exception as e:
        print("[reddit_scam][db_error]", e)
        return False
    finally:
        conn.close()


def _community_verdict_from_counts(scam_votes: int, safe_votes: int) -> str:
    total = int(scam_votes or 0) + int(safe_votes or 0)
    if total <= 0:
        return "unknown"
    if scam_votes > safe_votes:
        return "scam"
    if safe_votes > scam_votes:
        return "safe"
    return "mixed"

def _normalize_kind_label_db(kind: str | None) -> str:
    k = str(kind or "").strip().lower()
    if k in {"eth_address", "bsc_address", "evm_address", "address"}:
        return "wallet"
    if k in {"wallet", "contract", "ticker", "url", "domain", "text"}:
        return k
    return "unknown"

def _community_top_items(limit: int = 50, only_scam_first: bool = True) -> list[dict]:
    conn = _scan_db_connect()
    try:
        cur = conn.cursor()
        rows = cur.execute(
            """
            WITH base AS (
              SELECT
                id,
                obj,
                COALESCE(NULLIF(TRIM(kind), ''), 'unknown') AS kind,
                COALESCE(is_scam, 0) AS is_scam,
                COALESCE(NULLIF(TRIM(user_id), ''), 'legacy:' || CAST(id AS TEXT)) AS user_key,
                COALESCE(NULLIF(TRIM(reporter_name), ''), NULLIF(TRIM(user_id), ''), 'anonymous') AS reporter_name,
                COALESCE(updated_at, created_at) AS updated_at
              FROM scan_votes
            ),
            agg AS (
              SELECT
                obj,
                kind,
                COUNT(DISTINCT user_key) AS total_users,
                SUM(CASE WHEN is_scam = 1 THEN 1 ELSE 0 END) AS scam_votes,
                SUM(CASE WHEN is_scam = 0 THEN 1 ELSE 0 END) AS safe_votes,
                MAX(updated_at) AS last_seen
              FROM base
              GROUP BY obj, kind
            )
            SELECT
              agg.obj,
              agg.kind,
              agg.total_users,
              agg.scam_votes,
              agg.safe_votes,
              agg.last_seen,
              COALESCE((
                SELECT b2.reporter_name
                FROM base b2
                WHERE b2.obj = agg.obj AND b2.kind = agg.kind
                ORDER BY b2.updated_at DESC, b2.id DESC
                LIMIT 1
              ), 'anonymous') AS last_reporter
            FROM agg
            ORDER BY
              CASE WHEN ? = 1 THEN agg.scam_votes ELSE 0 END DESC,
              agg.total_users DESC,
              agg.last_seen DESC
            LIMIT ?
            """,
            (1 if only_scam_first else 0, int(limit)),
        ).fetchall()
    finally:
        conn.close()

    items = []
    for obj, kind, total_users, scam_votes, safe_votes, last_seen, last_reporter in rows:
        total_users = int(total_users or 0)
        scam_votes = int(scam_votes or 0)
        safe_votes = int(safe_votes or 0)
        norm_kind = _normalize_kind_label_db(kind)
        items.append(
            {
                "object": obj,
                "obj": obj,
                "type": norm_kind,
                "kind": norm_kind,
                "scam_votes": scam_votes,
                "safe_votes": safe_votes,
                "total_users": total_users,
                "community_verdict": _community_verdict_from_counts(scam_votes, safe_votes),
                "last_seen": last_seen,
                "last_reporter": last_reporter,
            }
        )
    return items

# =========================================================
# GUEST PRO
# =========================================================
def _guest_pro_connect():
    return sqlite3.connect(GUEST_PRO_DB_PATH)

def init_guest_pro_db():
    conn = _guest_pro_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS guest_pro (
              user_id TEXT PRIMARY KEY,
              is_active INTEGER NOT NULL DEFAULT 1,
              source TEXT,
              updated_at TEXT NOT NULL,
              expires_at TEXT
            );
            """
        )
        cols = {row[1] for row in cur.execute("PRAGMA table_info(guest_pro)").fetchall()}
        if "expires_at" not in cols:
            cur.execute("ALTER TABLE guest_pro ADD COLUMN expires_at TEXT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_guest_pro_active ON guest_pro(is_active)")
        conn.commit()
    finally:
        conn.close()

init_guest_pro_db()

def set_guest_pro(user_id: str, active: bool = True, source: str = "guest_iap", expires_at: str | None = None) -> None:
    uid = (user_id or "").strip()
    if not uid:
        return
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn = _guest_pro_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO guest_pro(user_id, is_active, source, updated_at, expires_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
              is_active=excluded.is_active,
              source=excluded.source,
              updated_at=excluded.updated_at,
              expires_at=excluded.expires_at
            """,
            (uid, 1 if active else 0, (source or "guest_iap"), now_iso, expires_at),
        )
        conn.commit()
    finally:
        conn.close()

def guest_has_pro(user_id: Optional[str]) -> bool:
    uid = (str(user_id or "")).strip()
    if not uid:
        return False
    conn = _guest_pro_connect()
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT is_active, expires_at FROM guest_pro WHERE user_id=? LIMIT 1",
            (uid,),
        ).fetchone()
        if not row or int(row[0] or 0) != 1:
            return False
        expires_at = str(row[1] or "").strip()
        if expires_at:
            try:
                expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if expiry <= datetime.now(timezone.utc):
                    return False
            except Exception:
                return False
        return True
    finally:
        conn.close()

def _payload_bool(payload: dict, keys: list[str]) -> Optional[bool]:
    for key in keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "active", "pro", "premium"}:
                return True
            if normalized in {"0", "false", "no", "n", "inactive", "free"}:
                return False
    return None

def _iap_status_payload(user_id: Optional[str]) -> dict:
    active = guest_has_pro(user_id)
    expires_at = None
    uid = str(user_id or "").strip()
    if uid:
        try:
            conn = _guest_pro_connect()
            try:
                row = conn.execute("SELECT expires_at FROM guest_pro WHERE user_id=? LIMIT 1", (uid,)).fetchone()
                expires_at = str(row[0] or "").strip() or None if row else None
            finally:
                conn.close()
        except Exception:
            expires_at = None
    return {
        "ok": True,
        "userId": (str(user_id or "").strip() or None),
        "active": active,
        "isPro": active,
        "pro": active,
        "plan": "PRO" if active else "FREE",
        "expiresAt": expires_at,
    }

def _google_play_access_token() -> str:
    sa_path = (os.getenv("GOOGLE_PLAY_SA_JSON") or "").strip()
    if not sa_path or not os.path.exists(sa_path):
        raise HTTPException(status_code=500, detail="GOOGLE_PLAY_SA_JSON is missing on server")

    creds = service_account.Credentials.from_service_account_file(
        sa_path,
        scopes=["https://www.googleapis.com/auth/androidpublisher"],
    )
    creds.refresh(GoogleAuthRequest())
    return creds.token

def _google_play_verify_purchase(product_type: str, package_name: str, product_id: str, token: str) -> dict:
    ptype = (product_type or "").strip().lower()
    if ptype not in ("subs", "inapp"):
        raise HTTPException(status_code=400, detail="productType must be 'subs' or 'inapp'")

    package_name = (package_name or "").strip()
    product_id = (product_id or "").strip()
    token = (token or "").strip()
    if not package_name or not product_id or not token:
        raise HTTPException(status_code=400, detail="Missing packageName/productId/purchaseToken")

    access_token = _google_play_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    if ptype == "subs":
        url = (
            "https://androidpublisher.googleapis.com/androidpublisher/v3/"
            f"applications/{package_name}/purchases/subscriptions/{product_id}/tokens/{token}"
        )
    else:
        url = (
            "https://androidpublisher.googleapis.com/androidpublisher/v3/"
            f"applications/{package_name}/purchases/products/{product_id}/tokens/{token}"
        )

    r = requests.get(url, headers=headers, timeout=20)
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Google verify failed: {r.status_code} {r.text[:300]}")
    return r.json()

def _dt_from_google_ms(ms: Any) -> Optional[datetime]:
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except Exception:
        return None

def _active_from_google_purchase(product_type: str, data: dict) -> Tuple[bool, str, Optional[datetime]]:
    ptype = (product_type or "").strip().lower()
    if ptype == "subs":
        expiry = _dt_from_google_ms(data.get("expiryTimeMillis"))
        payment_state = data.get("paymentState")
        active = bool(expiry and expiry > datetime.now(timezone.utc))
        status = "active" if active else "expired"

        if active and payment_state is not None:
            try:
                if int(payment_state) not in (1, 2):
                    active = False
                    status = "pending"
            except Exception:
                active = False
                status = "unknown"

        return active, status, expiry

    purchase_state = data.get("purchaseState")
    if purchase_state == 0:
        return True, "active", None
    if purchase_state == 2:
        return False, "pending", None
    return False, "canceled", None

@app.post("/iap/google/guest/verify")
async def iap_google_guest_verify(request: Request, payload: dict = Body(...)):
    user_id = (
        str(payload.get("userId") or "").strip()
        or str(request.headers.get("x-user-id") or "").strip()
        or str(request.headers.get("x_user_id") or "").strip()
        or str(request.headers.get("user-id") or "").strip()
    )
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing userId")

    product_type = str(payload.get("productType") or "").strip().lower()
    product_id = str(payload.get("productId") or "").strip()
    package_name = str(payload.get("packageName") or "com.noytrix.app").strip()
    purchase_token = str(payload.get("purchaseToken") or "").strip()

    data = _google_play_verify_purchase(product_type, package_name, product_id, purchase_token)
    active, status, expiry_dt = _active_from_google_purchase(product_type, data)

    if active:
        set_guest_pro(
            user_id,
            active=True,
            source=f"google_play:{product_id}",
            expires_at=expiry_dt.isoformat() if expiry_dt else None,
        )

    return {
        "ok": True,
        "userId": user_id,
        "active": guest_has_pro(user_id),
        "googleActive": active,
        "status": status,
        "productType": product_type,
        "productId": product_id,
        "orderId": data.get("orderId"),
        "expiryUtc": expiry_dt.isoformat() if expiry_dt else None,
        "acknowledgementState": data.get("acknowledgementState"),
        "purchaseState": data.get("purchaseState"),
        "paymentState": data.get("paymentState"),
    }

@app.post("/iap/guest/activate")
async def iap_guest_activate(request: Request, payload: dict = Body(...), lang: str | None = None):
    user_id = (
        str(payload.get("userId") or "").strip()
        or str(request.headers.get("x-user-id") or "").strip()
        or str(request.headers.get("x_user_id") or "").strip()
        or str(request.headers.get("user-id") or "").strip()
    )
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing userId")

    has_pro = _payload_bool(payload, ["hasPro", "isPro", "active", "pro", "premium", "entitlementActive"])
    if has_pro is None:
        has_pro = True
    source = str(payload.get("source") or "guest_iap").strip()

    if not has_pro:
        # RevenueCat can briefly return no active entitlement during app start,
        # restore, network errors, or anonymous->stable appUserID transitions.
        # A client-side false must not revoke a paid server-side PRO record.
        out = _iap_status_payload(user_id)
        out.update({
            "ignored": True,
            "reason": "client_false_does_not_revoke_pro",
        })
        return out

    set_guest_pro(user_id, active=has_pro, source=source)
    return _iap_status_payload(user_id)

@app.get("/iap/guest/status")
async def iap_guest_status(request: Request, userId: str | None = None):
    uid = (
        str(userId or "").strip()
        or str(request.headers.get("x-user-id") or "").strip()
        or str(request.headers.get("x_user_id") or "").strip()
        or str(request.headers.get("user-id") or "").strip()
    )
    return _iap_status_payload(uid)

# =========================================================
# QUOTA
# =========================================================
def _get_user_id(request: Request, user_id_q: Optional[str]) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.strip().lower().startswith("bearer "):
        token = auth.strip()[7:].strip()
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
            for k in ("email", "user_email", "sub", "userId", "user_id", "id", "uid", "nick", "username"):
                v = payload.get(k)
                if v is not None and str(v).strip():
                    return str(v).strip()
        except Exception:
            pass

    h = request.headers.get("x-user-id") or request.headers.get("x_user_id") or request.headers.get("user-id")
    if h and h.strip():
        return h.strip()

    if user_id_q and str(user_id_q).strip():
        return str(user_id_q).strip()

    return None

def init_quota_db():
    conn = sqlite3.connect(QUOTA_DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS quota_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              bucket TEXT NOT NULL,
              feature TEXT NOT NULL,
              ts_utc TEXT NOT NULL
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_quota_bucket_feature_ts ON quota_events(bucket, feature, ts_utc)")
        conn.commit()
    finally:
        conn.close()

init_quota_db()

def is_pro(user_id: Optional[str]) -> bool:
    if not user_id:
        return False

    uid_raw = str(user_id).strip()
    if not uid_raw:
        return False

    def _guest_pro_active(*ids: str) -> bool:
        candidates = [str(x or "").strip() for x in ids if str(x or "").strip()]
        if not candidates:
            return False
        try:
            conn = _guest_pro_connect()
            try:
                q = ",".join(["?"] * len(candidates))
                row = conn.execute(
                    f"SELECT 1 FROM guest_pro WHERE is_active=1 AND user_id IN ({q}) LIMIT 1",
                    candidates,
                ).fetchone()
                return bool(row)
            finally:
                conn.close()
        except Exception:
            return False

    if _guest_pro_active(uid_raw, uid_raw.lower()):
        return True

    try:
        conn = sqlite3.connect(str(APP_DB_PATH))
        cur = conn.cursor()

        try:
            uid_int = int(uid_raw)
            cur.execute("SELECT id, email, nick, plan FROM users WHERE id=?", (uid_int,))
            row = cur.fetchone()
            if row and (
                str((row[3] or "")).strip().lower() == "pro"
                or _guest_pro_active(str(row[0]), str(row[1] or "").lower(), str(row[2] or "").lower())
            ):
                conn.close()
                return True
        except Exception:
            pass

        cur.execute("SELECT id, email, nick, plan FROM users WHERE lower(email)=lower(?)", (uid_raw,))
        row = cur.fetchone()
        if row and (
            str((row[3] or "")).strip().lower() == "pro"
            or _guest_pro_active(str(row[0]), str(row[1] or "").lower(), str(row[2] or "").lower())
        ):
            conn.close()
            return True

        cur.execute("SELECT id, email, nick, plan FROM users WHERE lower(nick)=lower(?)", (uid_raw,))
        row = cur.fetchone()
        if row and (
            str((row[3] or "")).strip().lower() == "pro"
            or _guest_pro_active(str(row[0]), str(row[1] or "").lower(), str(row[2] or "").lower())
        ):
            conn.close()
            return True

        conn.close()
        return False
    except Exception:
        return False

def enforce_free_quota(request: Request, feature: str, user_id: Optional[str], lang: str = "en") -> dict:
    if str(user_id or "").strip().lower() in {"web_demo", "website", "site_demo"}:
        return {
            "isPro": True,
            "freeLimit": DAILY_FREE_LIMIT,
            "feature": feature,
            "day": datetime.utcnow().strftime("%Y%m%d"),
            "used": 0,
            "left": 999999,
        }
    day_key = datetime.now(timezone.utc).strftime("%Y%m%d")

    if user_id and is_pro(user_id):
        return {
            "isPro": True,
            "freeLimit": DAILY_FREE_LIMIT,
            "feature": feature,
            "day": day_key,
            "used": 0,
            "left": 999999,
            "resetAtUtc": None,
        }

    limits = {
        "scan": DAILY_FREE_LIMIT,
        "immunity_analyze": DAILY_FREE_LIMIT,
        "news_explain": DAILY_FREE_LIMIT,
    }
    limit = int(limits.get(feature, DAILY_FREE_LIMIT))

    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "unknown")
    bucket = (str(user_id).strip() if user_id and str(user_id).strip() else f"ip:{ip}")

    now = datetime.now(timezone.utc)
    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    day_key = day_start.strftime("%Y%m%d")

    con = sqlite3.connect(QUOTA_DB_PATH)
    try:
        used = con.execute(
            "SELECT COUNT(1) FROM quota_events WHERE bucket=? AND feature=? AND ts_utc>=? AND ts_utc<?",
            (bucket, feature, day_start.isoformat(), day_end.isoformat()),
        ).fetchone()[0]

        remaining = max(0, limit - int(used))
        if remaining <= 0:
            return {
                "isPro": False,
                "freeLimit": limit,
                "feature": feature,
                "day": day_key,
                "used": int(used),
                "left": 0,
                "resetAtUtc": day_end.isoformat(),
                "limitReached": True,
            }

        con.execute(
            "INSERT INTO quota_events(bucket, feature, ts_utc) VALUES(?,?,?)",
            (bucket, feature, now.isoformat()),
        )
        con.commit()

        used2 = used + 1
        remaining2 = max(0, limit - int(used2))
        return {
            "isPro": False,
            "freeLimit": limit,
            "feature": feature,
            "day": day_key,
            "used": int(used2),
            "left": int(remaining2),
            "resetAtUtc": day_end.isoformat(),
        }
    finally:
        con.close()

# =========================================================
# PROFILE DB + HELPERS
# =========================================================
def _profile_db_connect():
    return sqlite3.connect(PROFILE_DB_PATH)

def _app_db_connect():
    return sqlite3.connect(APP_DB_PATH)

def init_profile_db():
    conn = _profile_db_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS profile_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_key TEXT NOT NULL,
              event_type TEXT NOT NULL,
              object_ref TEXT,
              meta_json TEXT,
              created_at TEXT NOT NULL
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_profile_user_time ON profile_events(user_key, created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_profile_user_event ON profile_events(user_key, event_type)")
        conn.commit()
    finally:
        conn.close()

init_profile_db()

def _json_dumps_safe(x: Any) -> str:
    try:
        return json.dumps(x, ensure_ascii=False)
    except Exception:
        return "{}"

def _json_loads_safe(x: Any, fb: Any):
    try:
        if not x:
            return fb
        return json.loads(x)
    except Exception:
        return fb

def _db_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
        return bool(row)
    except Exception:
        return False

def _profile_track_event(user_key: Optional[str], event_type: str, object_ref: str | None = None, meta: dict | None = None) -> None:
    uk = str(user_key or "").strip()
    if not uk:
        return
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn = _profile_db_connect()
    try:
        conn.execute(
            """
            INSERT INTO profile_events(user_key, event_type, object_ref, meta_json, created_at)
            VALUES(?,?,?,?,?)
            """,
            (uk, event_type, (object_ref or None), _json_dumps_safe(meta or {}), now_iso),
        )
        conn.commit()
    except Exception as e:
        print("[profile] track_event error:", e)
    finally:
        conn.close()

def _profile_resolve_user_row(uid: Optional[str]) -> dict:
    out = {}
    raw = str(uid or "").strip()
    if not raw or not APP_DB_PATH.exists():
        return out

    try:
        conn = _app_db_connect()
        cur = conn.cursor()

        if not _db_table_exists(conn, "users"):
            conn.close()
            return out

        row = None
        cols = [r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()]
        select_cols = []
        for c in ("id", "email", "nick", "name", "username", "login", "plan", "created_at", "createdAt", "registered_at", "registeredAt", "date_joined"):
            if c in cols:
                select_cols.append(c)

        if not select_cols:
            conn.close()
            return out

        select_sql = ", ".join(select_cols)

        try:
            uid_int = int(raw)
            row = cur.execute(f"SELECT {select_sql} FROM users WHERE id=? LIMIT 1", (uid_int,)).fetchone()
        except Exception:
            pass

        if row is None and "email" in cols:
            row = cur.execute(f"SELECT {select_sql} FROM users WHERE lower(email)=lower(?) LIMIT 1", (raw,)).fetchone()
        if row is None and "nick" in cols:
            row = cur.execute(f"SELECT {select_sql} FROM users WHERE lower(nick)=lower(?) LIMIT 1", (raw,)).fetchone()
        if row is None and "username" in cols:
            row = cur.execute(f"SELECT {select_sql} FROM users WHERE lower(username)=lower(?) LIMIT 1", (raw,)).fetchone()
        if row is None and "login" in cols:
            row = cur.execute(f"SELECT {select_sql} FROM users WHERE lower(login)=lower(?) LIMIT 1", (raw,)).fetchone()

        if row:
            out = {select_cols[i]: row[i] for i in range(len(select_cols))}
        conn.close()
        return out
    except Exception as e:
        print("[profile] resolve_user_row error:", e)
        return {}

def _profile_aliases_for_uid(uid: Optional[str]) -> list[str]:
    raw = str(uid or "").strip()
    aliases = set()

    if raw:
        aliases.add(raw)
        aliases.add(raw.lower())

    user_row = _profile_resolve_user_row(raw)
    for k in ("id", "email", "nick", "name", "username", "login"):
        v = user_row.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            aliases.add(s)
            aliases.add(s.lower())

    return sorted({a for a in aliases if str(a).strip()})

def _profile_fetch_events(uid: Optional[str], limit: int = 1000) -> list[dict]:
    aliases = _profile_aliases_for_uid(uid)
    if not aliases:
        return []

    qmarks = ",".join(["?"] * len(aliases))
    conn = _profile_db_connect()
    try:
        rows = conn.execute(
            f"""
            SELECT user_key, event_type, object_ref, meta_json, created_at
            FROM profile_events
            WHERE lower(user_key) IN ({qmarks})
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            tuple([a.lower() for a in aliases] + [int(limit)]),
        ).fetchall()
    finally:
        conn.close()

    out = []
    for user_key, event_type, object_ref, meta_json, created_at in rows:
        out.append(
            {
                "user_key": user_key,
                "event_type": event_type,
                "object_ref": object_ref,
                "meta": _json_loads_safe(meta_json, {}),
                "created_at": created_at,
            }
        )
    return out

def _profile_member_since(uid: Optional[str]) -> Optional[str]:
    row = _profile_resolve_user_row(uid)
    for k in ("created_at", "createdAt", "registered_at", "registeredAt", "date_joined"):
        v = row.get(k)
        if v:
            return str(v)
    return None

def _profile_display_name(uid: Optional[str]) -> str:
    row = _profile_resolve_user_row(uid)
    for k in ("nick", "name", "username", "login", "email", "id"):
        v = row.get(k)
        if v:
            s = str(v).strip()
            if s:
                if "@" in s:
                    return s.split("@")[0]
                return s
    raw = str(uid or "").strip()
    if raw:
        if "@" in raw:
            return raw.split("@")[0]
        return raw
    return "User"

def _profile_email(uid: Optional[str]) -> Optional[str]:
    row = _profile_resolve_user_row(uid)
    v = row.get("email")
    return str(v).strip() if v else None

def _profile_plan(uid: Optional[str]) -> str:
    if is_pro(uid):
        return "pro"
    row = _profile_resolve_user_row(uid)
    p = str(row.get("plan") or "").strip().lower()
    return p if p else "free"

def _scan_client_safe_response(data: dict) -> dict:
    if not isinstance(data, dict):
        return data

    def primitive(value):
        return value is None or isinstance(value, (str, int, float, bool))

    def text_value(*values):
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    score = int(data.get("score") or 0)
    level = text_value(data.get("level"), data.get("verdict"), "safe").lower()
    kind = text_value(data.get("kind"), data.get("risk_type"), "text").lower()
    verdict = text_value(
        data.get("verdict_localized"),
        data.get("ai_verdict_localized"),
        data.get("verdict_ru"),
        data.get("ai_verdict_ru"),
        data.get("verdict_en"),
        data.get("ai_verdict_en"),
        data.get("verdict"),
        data.get("level"),
        level,
    )

    safe = {
        "ok": True,
        "version": "v1",
        "engine": "noytrix_security_core",
        "input": text_value(data.get("input"), data.get("normalized_input")),
        "normalized_input": text_value(data.get("normalized_input"), data.get("input")),
        "kind": kind,
        "score": score,
        "level": level,
        "verdict": verdict or level,
        "risk_type": kind,
        "confidence": int(data.get("confidence") or data.get("confidence_score") or 0),
        "confidence_score": int(data.get("confidence_score") or data.get("confidence") or 0),
        "isPro": bool(data.get("isPro")),
        "confirmed_red_flag": bool(data.get("confirmed_red_flag")),
        "ai_verdict": verdict or level,
        "ai_verdict_en": text_value(data.get("ai_verdict_en"), data.get("verdict_en"), verdict, level),
        "ai_verdict_ru": text_value(data.get("ai_verdict_ru"), data.get("verdict_ru"), verdict, level),
        "ai_verdict_localized": verdict or level,
        "verdict_localized": verdict or level,
        "what_can_happen": text_value(data.get("what_can_happen")),
        "worst_case": text_value(data.get("worst_case")),
        "summary": text_value(data.get("summary")),
    }

    quota = data.get("quota")
    if isinstance(quota, dict):
        safe["quota"] = {
            "limit": int(quota.get("limit") or 999999),
            "used": int(quota.get("used") or 0),
            "left": int(quota.get("left") or 999999),
            "is_pro": bool(quota.get("is_pro") or data.get("isPro")),
            "plan": text_value(quota.get("plan"), "PRO" if data.get("isPro") else "Free"),
        }
    else:
        safe["quota"] = {"limit": 999999, "used": 0, "left": 999999, "is_pro": bool(data.get("isPro")), "plan": "PRO" if data.get("isPro") else "Free"}
    if data.get("isPro"):
        safe["quota"]["limit"] = safe["quota"].get("limit") or 999999
        safe["quota"]["used"] = safe["quota"].get("used") or 0
        safe["quota"]["left"] = safe["quota"].get("left") or 999999
        safe["quota"]["is_pro"] = True
        safe["quota"]["plan"] = safe["quota"].get("plan") or "PRO"

    safe["scoring"] = {
        "internal_confirmed_signals": 0,
        "external_confirmed_signals": 0,
        "confirmed_external_signals": 0,
        "heuristics": 0,
        "page_content": 0,
        "community_votes": 0,
    }
    if isinstance(data.get("scoring"), dict):
        for key in safe["scoring"]:
            value = data["scoring"].get(key)
            safe["scoring"][key] = int(value or 0) if primitive(value) else 0

    safe["community"] = {
        "community_verdict": "unknown",
        "safe_votes": 0,
        "scam_votes": 0,
        "total_users": 0,
        "immunity_score": 0,
    }

    evidence = []
    if isinstance(data.get("evidence"), list):
        for item in data["evidence"][:6]:
            if isinstance(item, dict):
                evidence.append({
                    "source": text_value(item.get("source")),
                    "code": text_value(item.get("code"), item.get("label"), "signal"),
                    "severity": int(item.get("severity") or 0),
                    "text": text_value(item.get("text"), item.get("message"), item.get("label"), item.get("code")),
                })
            elif primitive(item):
                evidence.append({"text": str(item)})
    safe["evidence"] = evidence

    sources = []
    if isinstance(data.get("sources"), list):
        for src in data["sources"][:6]:
            if not isinstance(src, dict):
                continue
            sources.append({
                "name": text_value(src.get("name"), src.get("source"), "source"),
                "source": text_value(src.get("source"), src.get("name"), "source"),
                "status": text_value(src.get("status"), "no_data"),
                "verdict": text_value(src.get("verdict"), "unknown"),
                "status_text": text_value(src.get("status_text")),
            })
    safe["sources"] = sources

    return safe

def _clamp(n: float, a: float, b: float) -> float:
    return max(a, min(b, n))

def _profile_rank(score: int) -> str:
    if score >= 90:
        return "Elite"
    if score >= 75:
        return "Guardian"
    if score >= 60:
        return "Hunter"
    if score >= 40:
        return "Analyst"
    return "Explorer"

def _profile_level(points: int) -> int:
    if points >= 120:
        return 6
    if points >= 80:
        return 5
    if points >= 45:
        return 4
    if points >= 22:
        return 3
    if points >= 8:
        return 2
    return 1

def _profile_community_votes_count(uid: Optional[str]) -> int:
    aliases = _profile_aliases_for_uid(uid)
    if not aliases:
        return 0
    conn = _scan_db_connect()
    try:
        qmarks = ",".join(["?"] * len(aliases))
        row = conn.execute(
            f"""
            SELECT COUNT(DISTINCT obj || '::' || COALESCE(kind, '') || '::' || COALESCE(user_id, ''))
            FROM scan_votes
            WHERE lower(COALESCE(user_id, '')) IN ({qmarks})
            """,
            tuple([a.lower() for a in aliases]),
        ).fetchone()
        return int((row[0] or 0) if row else 0)
    except Exception:
        return 0
    finally:
        conn.close()

def _profile_build_stats(uid: Optional[str]) -> dict:
    events = _profile_fetch_events(uid, limit=5000)

    scans = [e for e in events if e["event_type"] == "scamshield_scan"]
    scan_safe = [e for e in scans if str(e["meta"].get("verdict") or "").lower() == "safe"]
    scan_suspicious = [e for e in scans if str(e["meta"].get("verdict") or "").lower() == "suspicious"]
    scan_danger = [e for e in scans if str(e["meta"].get("verdict") or "").lower() in {"danger", "critical"}]

    explain_events = [e for e in events if e["event_type"] == "news_explain"]

    immunity_events = [e for e in events if e["event_type"] == "immunity_analyze"]
    immunity_low = [e for e in immunity_events if str(e["meta"].get("level") or "").lower() == "low"]
    immunity_medium = [e for e in immunity_events if str(e["meta"].get("level") or "").lower() == "medium"]
    immunity_high = [e for e in immunity_events if str(e["meta"].get("level") or "").lower() in {"high", "critical"}]

    community_vote_events = [e for e in events if e["event_type"] == "community_vote"]
    community_votes = max(_profile_community_votes_count(uid), len(community_vote_events))

    checked_assets = set()
    for e in scans + explain_events + immunity_events:
        obj = str(e.get("object_ref") or "").strip()
        symbol = str(e["meta"].get("symbol") or "").strip().upper()
        if symbol:
            checked_assets.add(symbol)
        elif obj:
            checked_assets.add(obj[:120])

    total_activity = len(events)
    plan = _profile_plan(uid)
    member_since = _profile_member_since(uid)
    email = _profile_email(uid)

    trust_score = int(
        round(
            _clamp(
                18
                + min(20, len(scans) * 2.5)
                + min(20, len(scan_safe) * 3.0)
                + min(14, len(explain_events) * 2.0)
                + min(18, len(immunity_events) * 2.5)
                + min(10, community_votes * 2.0)
                + (8 if plan == "pro" else 0)
                + (4 if email else 0),
                0,
                100,
            )
        )
    )

    points = (
        len(scans)
        + len(explain_events) * 2
        + len(immunity_events) * 2
        + community_votes * 2
        + (8 if plan == "pro" else 0)
    )

    rank = _profile_rank(trust_score)
    level = _profile_level(points)

    top_symbol = "—"
    symbol_counts: dict[str, int] = {}
    for e in scans + explain_events + immunity_events:
        s = str(e["meta"].get("symbol") or "").strip().upper()
        if not s:
            obj = str(e.get("object_ref") or "").strip()
            if obj and not obj.startswith("http"):
                s = obj[:40].upper()
        if s:
            symbol_counts[s] = symbol_counts.get(s, 0) + 1
    if symbol_counts:
        top_symbol = sorted(symbol_counts.items(), key=lambda x: (-x[1], x[0]))[0][0]

    approved_setups = len(immunity_low)
    risky_setups = len(immunity_medium)
    rejected_setups = len(immunity_high)
    setups_total = len(immunity_events)
    acceptance_rate = int(round((approved_setups / setups_total) * 100)) if setups_total else 0

    recent = []
    for e in events[:20]:
        recent.append(
            {
                "type": e["event_type"],
                "object": e.get("object_ref"),
                "meta": e.get("meta") or {},
                "created_at": e.get("created_at"),
            }
        )

    return {
        "identity": {
            "displayName": _profile_display_name(uid),
            "email": email,
            "memberSince": member_since,
            "plan": plan,
            "rank": rank,
            "level": level,
        },
        "trust": {
            "score": trust_score,
            "rank": rank,
            "level": level,
            "scamScans": len(scans),
            "safeResults": len(scan_safe),
            "suspiciousResults": len(scan_suspicious),
            "dangerResults": len(scan_danger),
            "communityVotes": community_votes,
            "explainSessions": len(explain_events),
            "immunitySessions": len(immunity_events),
        },
        "activity": {
            "totalActivity": total_activity,
            "scamScans": len(scans),
            "newsExplains": len(explain_events),
            "immunityAnalyses": len(immunity_events),
            "tokensChecked": len(checked_assets),
            "topSymbol": top_symbol,
            "communityVotes": community_votes,
        },
        "tradingPerformance": {
            "setupsAnalyzed": setups_total,
            "approvedSetups": approved_setups,
            "riskySetups": risky_setups,
            "rejectedSetups": rejected_setups,
            "acceptanceRate": acceptance_rate,
        },
        "recent": recent,
    }

def _profile_build_achievements(uid: Optional[str]) -> list[dict]:
    st = _profile_build_stats(uid)
    trust = st["trust"]
    activity = st["activity"]
    trading = st["tradingPerformance"]
    identity = st["identity"]

    ach: list[dict] = []

    def add(code: str, title_en: str, title_ru: str, text_en: str, text_ru: str):
        ach.append(
            {
                "code": code,
                "title_en": title_en,
                "title_ru": title_ru,
                "text_en": text_en,
                "text_ru": text_ru,
            }
        )

    if trust["scamScans"] >= 1:
        add("first_scan", "First Scan", "Первая проверка", "Completed the first ScamShield scan.", "Выполнена первая проверка ScamShield.")
    if trust["scamScans"] >= 10:
        add("scanner_10", "Scanner", "Сканер", "Completed 10 ScamShield scans.", "Выполнено 10 проверок ScamShield.")
    if trust["dangerResults"] >= 3:
        add("hunter_3", "Scam Hunter", "Охотник на скам", "Detected 3 dangerous results.", "Обнаружено 3 опасных результата.")
    if trust["explainSessions"] >= 5:
        add("analyst_5", "Analyst", "Аналитик", "Used News Explain 5 times.", "Функция Explain использована 5 раз.")
    if trust["immunitySessions"] >= 5:
        add("risk_engine_5", "Risk Engine", "Risk Engine", "Completed 5 setup analyses.", "Выполнено 5 анализов сетапов.")
    if trading["approvedSetups"] >= 3:
        add("approved_3", "Setup Reader", "Читатель сетапов", "Received 3 approved setups.", "Получено 3 одобренных сетапа.")
    if activity["communityVotes"] >= 3:
        add("community_3", "Community Voice", "Голос комьюнити", "Submitted 3 community votes.", "Отправлено 3 голоса комьюнити.")
    if identity["plan"] == "pro":
        add("pro_user", "PRO User", "PRO-пользователь", "PRO access is active.", "PRO-доступ активен.")

    return ach

def _profile_achievement_texts(achievements: list[dict], lang: str) -> list[dict]:
    out = []
    for a in achievements:
        out.append(
            {
                "code": a["code"],
                "text": a["text_ru"] if lang == "ru" else a["text_en"],
                "title": a["title_ru"] if lang == "ru" else a["title_en"],
            }
        )
    return out

# =========================================================
# OBJECT DETECTION / NORMALIZATION
# =========================================================
RE_URL = re.compile(r"^https?://", re.I)
RE_DOMAIN = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,63}(?:/.*)?$", re.I)

RE_TRON = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
RE_BTC = re.compile(r"^(bc1|[13])[a-zA-HJ-NP-Z0-9]{25,62}$")
RE_SOL = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
RE_TON = re.compile(r"^(EQ|UQ)[A-Za-z0-9_-]{46,}$")

RE_EVM_ADDR = re.compile(r"^0x[a-fA-F0-9]{40}$")

KNOWN_SAFE_ADDRESSES = {
    "0x000000000000000000000000000000000000dead": "burn_address",
    "0x0000000000000000000000000000000000000000": "zero_address",
    "0xd8da6bf26964af9d7eed9e03e53415d37aa96045": "vitalik_buterin",
    "0xab5801a7d398351b8be11c439e05c5b3259aec9b": "vitalik_buterin_2",
    "0xbe0eb53f46cd790cd13851d5eff43d12404d33e8": "binance_cold",
    "0x28c6c06298d514db089934071355e5743bf21d60": "binance_hot",
    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": "uniswap_uni_token",
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "uniswap_v2_router",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "uniswap_v3_router",
}
RE_TICKER = re.compile(r"^[A-Z0-9._-]{2,15}$")
RE_PRIVATE_KEY_HEX = re.compile(r"\b0x[a-fA-F0-9]{64}\b")
RE_SEED_WORDS = re.compile(
    r"\b(seed phrase|secret phrase|recovery phrase|mnemonic|private key|wallet connect|walletconnect|claim now|airdrop|support team|support agent|verify wallet|connect wallet)\b",
    re.I,
)

def _sha256_short(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:20]

def _attach_ai_investigation_fields(out: dict) -> dict:
    try:
        investigation = build_ai_investigation(out)
        out["ai_investigation"] = investigation
        details = out.setdefault("details", {})
        if isinstance(details, dict):
            details["ai_investigation"] = investigation
    except Exception as e:
        out["ai_investigation"] = {
            "available": False,
            "reason": str(e)[:240],
        }
    return out

def _attach_multichain_fields(out: dict, value: str | None = None, metadata: dict | None = None) -> dict:
    try:
        target = value or out.get("normalized_input") or out.get("input") or ""
        multi = build_multichain_intelligence(
            target,
            kind=str(out.get("kind") or ""),
            sources=out.get("sources") or [],
            evidence=out.get("evidence") or [],
            metadata=metadata or {
                "chain": out.get("chain"),
                "chainId": out.get("chain_id"),
                "kind": out.get("kind"),
            },
        )
        out["multi_chain_intelligence"] = multi
        details = out.setdefault("details", {})
        if isinstance(details, dict):
            details["multi_chain_intelligence"] = multi
    except Exception as e:
        out["multi_chain_intelligence"] = {
            "available": False,
            "reason": str(e)[:240],
        }
    return out

def _normalize_url(x: str) -> str:
    s = (x or "").strip()
    if not s:
        return s
    if not RE_URL.match(s):
        s = "https://" + s
    return s

def _extract_host(u: str) -> str:
    try:
        return (urlparse(u).hostname or "").lower().strip()
    except Exception:
        return ""

def _host_root_domain(host: str) -> str:
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host

def _same_effective_site(host_a: str, host_b: str) -> bool:
    a = (host_a or "").strip().lower()
    b = (host_b or "").strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True

    a_root = _host_root_domain(a)
    b_root = _host_root_domain(b)
    if a_root != b_root:
        return False

    a_base = a[:-len(a_root)].rstrip(".")
    b_base = b[:-len(b_root)].rstrip(".")
    allowed_prefixes = {"", "www", "m", "amp"}
    return (a_base in allowed_prefixes) and (b_base in allowed_prefixes)

def _normalize_domain(x: str) -> str:
    s = (x or "").strip().lower()
    s = s.split("/")[0].strip()
    return s

def _looks_url(x: str) -> bool:
    if RE_URL.match((x or "").strip()):
        return True
    if _legacy_looks_url:
        try:
            return bool(_legacy_looks_url(x))
        except Exception:
            pass
    return False

def _detect_input_kind(raw: str) -> dict:
    x = (raw or "").strip()
    out = {
        "kind": "text",
        "normalized": x,
        "display_kind": "text",
        "url": None,
        "domain": None,
        "symbol": None,
        "address": None,
        "chain": None,
    }
    if not x:
        return out

    if _looks_url(x):
        url = _normalize_url(x)
        host = _extract_host(url)
        out.update({"kind": "url", "display_kind": "url", "normalized": url, "url": url, "domain": host})
        return out

    if RE_EVM_ADDR.match(x):
        out.update({"kind": "wallet", "display_kind": "wallet", "normalized": x, "address": x, "chain": "evm"})
        return out

    if RE_TRON.match(x):
        out.update({"kind": "wallet", "display_kind": "wallet", "normalized": x, "address": x, "chain": "tron"})
        return out

    if RE_BTC.match(x):
        out.update({"kind": "wallet", "display_kind": "wallet", "normalized": x, "address": x, "chain": "btc"})
        return out

    if RE_TON.match(x):
        out.update({"kind": "wallet", "display_kind": "wallet", "normalized": x, "address": x, "chain": "ton"})
        return out

    if RE_SOL.match(x) and len(x) >= 32:
        out.update({"kind": "wallet", "display_kind": "wallet", "normalized": x, "address": x, "chain": "sol"})
    if RE_DOMAIN.match(x) and " " not in x and len(x) < 255:
        domain = _normalize_domain(x)
        url = _normalize_url(domain)
        out.update({"kind": "domain", "display_kind": "domain", "normalized": domain, "url": url, "domain": domain})
        return out

    x_up = x.upper()
    if RE_TICKER.match(x_up) and " " not in x and not x.startswith("0x"):
        out.update({"kind": "ticker", "display_kind": "ticker", "normalized": x_up, "symbol": x_up})
        return out

    if RE_PRIVATE_KEY_HEX.search(x):
        out.update({"kind": "text", "display_kind": "text", "normalized": x})
        return out

    return out

def _normalize_kind_for_vote(kind: str | None, obj: str) -> str:
    k = (kind or "").strip().lower()
    if k in {"url", "domain", "wallet", "contract", "ticker", "text", "evm_address", "eth_address", "bsc_address", "address"}:
        return _normalize_kind_label_db(k)
    det = _detect_input_kind(obj)
    return det["kind"]

# =========================================================
# SOURCE STATUS / LOCALIZATION
# =========================================================
SOURCE_STATUSES = {
    "malicious",
    "clean",
    "no_data",
    "timeout",
    "invalid_key",
    "quota",
    "error",
}

def _source_status_text(status: str, lang: str) -> str:
    key = {
        "malicious": "source_malicious",
        "clean": "source_clean",
        "no_data": "source_no_data",
        "timeout": "source_timeout",
        "invalid_key": "source_invalid_key",
        "quota": "source_quota",
        "error": "source_error",
    }.get(status, "source_error")
    return tr(lang, key)

def _localized_object_kind(kind: str, lang: str) -> str:
    key = {
        "url": "object_url",
        "domain": "object_domain",
        "wallet": "object_wallet",
        "contract": "object_contract",
        "ticker": "object_ticker",
        "text": "object_text",
    }.get(kind, "object_text")
    return tr(lang, key)

def _localized_chain_label(chain: str | None, lang: str) -> str | None:
    c = str(chain or "").strip().lower()
    if not c:
        return None
    labels = {
        "evm": {"en": "EVM", "ru": "EVM"},
        "tron": {"en": "TRON", "ru": "TRON"},
        "btc": {"en": "Bitcoin", "ru": "Bitcoin"},
        "ton": {"en": "TON", "ru": "TON"},
        "sol": {"en": "Solana", "ru": "Solana"},
    }
    row = labels.get(c)
    if not row:
        return c.upper()
    return row["ru"] if lang == "ru" else row["en"]

def _mk_source(name: str, status: str, verdict: str = "unknown", details: Any = None, evidence: list | None = None) -> dict:
    return {
        "name": name,
        "source": name,
        "status": status if status in SOURCE_STATUSES else "error",
        "verdict": verdict,
        "details": details if details is not None else {},
        "evidence": evidence or [],
    }

def _localize_sources(sources: list[dict], lang: str) -> list[dict]:
    out = []
    for s in sources or []:
        x = dict(s)
        x["status_text"] = _source_status_text(str(s.get("status") or "error"), lang)
        out.append(x)
    return out


def _canonical_level(level: str | None, score: int | None = None) -> str:
    raw = str(level or "").strip().lower()
    canonical = {"safe", "low", "medium", "high", "critical"}

    if raw in canonical:
        return raw

    if raw in {"danger", "malicious", "scam", "blocked"}:
        return "critical"

    if raw in {"suspicious", "warning", "warn"}:
        return "medium"

    try:
        s = int(score or 0)
    except Exception:
        s = 0

    if s >= 85:
        return "critical"
    if s >= 65:
        return "high"
    if s >= 35:
        return "medium"
    if s > 0:
        return "low"
    return "safe"


def _map_level_to_ai_verdict(level: str, lang: str) -> str:
    level = str(level or "").lower().strip()
    if level == "safe":
        return tr(lang, "safe")
    if level == "suspicious":
        return tr(lang, "suspicious")
    if level == "danger":
        return tr(lang, "danger")
    if level == "critical":
        return tr(lang, "critical")
    return tr(lang, "unknown")

def _extract_honeypot_summary_from_sources(sources: list[dict]) -> dict:
    for s in sources or []:
        if str(s.get("name") or "") != "honeypot":
            continue
        details = s.get("details") or {}
        return {
            "honeypot_verdict": s.get("verdict") or "unknown",
            "honeypot_status": s.get("status") or "unknown",
            "honeypot_risk": details.get("risk"),
        }
    return {"honeypot_verdict": None, "honeypot_status": None, "honeypot_risk": None}

def _attach_legacy_verdict_fields(out: dict, lang: str) -> dict:
    if not isinstance(out, dict):
        return out
    level = str(out.get("level") or "").lower().strip()
    hp = _extract_honeypot_summary_from_sources(out.get("sources") or [])
    out["ai_verdict"] = _map_level_to_ai_verdict(level, lang)
    out["ai_verdict_en"] = _map_level_to_ai_verdict(level, "en")
    out["ai_verdict_ru"] = _map_level_to_ai_verdict(level, "ru")
    out["ai_verdict_localized"] = out["ai_verdict"]
    out["honeypot_verdict"] = hp["honeypot_verdict"]
    out["honeypot_status"] = hp["honeypot_status"]
    out["honeypot_risk"] = hp["honeypot_risk"]
    return out



MAX_UINT_256_STR = str(2**256 - 1)

KNOWN_EVM_TOKENS = {
    "0xdac17f958d2ee523a2206206994597c13d831ec7": {"symbol": "USDT", "chain": "Ethereum"},
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {"symbol": "USDC", "chain": "Ethereum"},
    "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee": {"symbol": "ETH", "chain": "Ethereum"},
    "0x55d398326f99059ff775485246999027b3197955": {"symbol": "USDT", "chain": "BNB Chain"},
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": {"symbol": "USDC", "chain": "BNB Chain"},
}

def _evm_word_to_addr(word: str) -> str | None:
    s = str(word or "").lower().replace("0x", "").strip()
    if len(s) != 64:
        return None
    return "0x" + s[-40:]

def _evm_word_to_int(word: str) -> int | None:
    try:
        s = str(word or "").lower().replace("0x", "").strip()
        if len(s) != 64:
            return None
        return int(s, 16)
    except Exception:
        return None



def _analyze_typed_signature_payload(payload: dict) -> dict:
    signature = simulate_signature(payload)
    runtime_severity = normalize_score(signature.get("score") or 0)
    normalized_level = normalize_level("", runtime_severity)
    level = legacy_level(normalized_level)
    simulation = signature.get("simulation") or {}
    permissions = signature.get("permissions_summary") or {}
    flags = [str(x.get("code")) for x in (signature.get("signals") or []) if x.get("code")]

    return {
        "ok": True,
        "kind": "typed_signature",
        "method": signature.get("method"),
        "score": runtime_severity,
        "level": level,
        "normalized_level": normalized_level,
        "runtime_severity": runtime_severity,
        "verdict_en": "Signature can authorize asset movement" if permissions.get("can_spend") else "Wallet signature detected",
        "verdict_ru": "Signature can authorize asset movement" if permissions.get("can_spend") else "Wallet signature detected",
        "verdict_localized": "Signature can authorize asset movement" if permissions.get("can_spend") else "Wallet signature detected",
        "confirmed_red_flag": level in {"danger", "critical"},
        "typed_signature": {
            "domain": simulation.get("domain") or {},
            "primaryType": simulation.get("primary_type"),
            "family": signature.get("family"),
            "spender": simulation.get("spender"),
            "amount": simulation.get("amount"),
            "deadline": simulation.get("deadline"),
            "flags": flags,
        },
        "signature_simulation": signature,
        "drainer": {
            "detected": bool(flags),
            "score": runtime_severity,
            "risk": "high" if level in {"danger", "critical"} else "medium",
            "flags": flags,
            "summary": simulation.get("worst_case") or "Wallet signature detected.",
        },
        "permissions_summary": permissions,
        "simulation": {
            "available": True,
            "summary": simulation.get("worst_case") or "",
            "worst_case": simulation.get("worst_case") or "",
            "loss_scenarios": [simulation.get("worst_case")] if simulation.get("worst_case") else [],
            "recommended_actions": simulation.get("recommended_actions") or [],
        },
        "what_can_happen": simulation.get("worst_case") or "This signature may authorize wallet actions.",
        "worst_case": simulation.get("worst_case") or "Worst case: a malicious signature can authorize unwanted wallet actions.",
        "evidence": [{"source": "signature_simulator", **sig} for sig in (signature.get("signals") or [])],
        "details": {
            "typed_signature": payload.get("typedData") or payload.get("typed_data") or payload.get("data"),
            "signature_simulation": signature,
        },
    }

    method = str(payload.get("method") or "").lower()
    typed = payload.get("typedData") or payload.get("typed_data") or payload.get("data") or {}

    if isinstance(typed, str):
        try:
            typed = json.loads(typed)
        except Exception:
            typed = {}

    text = json.dumps(typed or {}, ensure_ascii=False).lower()
    msg = typed.get("message") if isinstance(typed, dict) else {}
    domain = typed.get("domain") if isinstance(typed, dict) else {}

    flags = []
    score = 20

    if "signtypeddata" in method:
        flags.append("typed_signature")
        score += 25
    if "permit" in text:
        flags.append("permit_signature")
        score += 30
    if "permit2" in text:
        flags.append("permit2_signature")
        score += 35
    if "spender" in text:
        flags.append("spender_permission")
        score += 20
    if "deadline" in text:
        flags.append("deadline_permission")
        score += 10
    if "value" in text or "amount" in text:
        flags.append("amount_permission")
        score += 10

    spender = None
    amount = None
    deadline = None

    if isinstance(msg, dict):
        spender = msg.get("spender") or msg.get("operator")
        amount = msg.get("value") or msg.get("amount") or msg.get("permitted", {}).get("amount") if isinstance(msg.get("permitted"), dict) else None
        deadline = msg.get("deadline") or msg.get("expiration") or msg.get("sigDeadline")

    runtime_severity = normalize_score(score)
    normalized_level = normalize_level("", runtime_severity)
    level = legacy_level(normalized_level)

    return {
        "ok": True,
        "kind": "typed_signature",
        "method": method,
        "score": runtime_severity,
        "level": level,
        "normalized_level": normalized_level,
        "runtime_severity": runtime_severity,
        "verdict_en": "Typed signature risk" if level in {"danger", "critical"} else "Typed signature detected",
        "verdict_ru": "Риск typed-подписи" if level in {"danger", "critical"} else "Typed-подпись обнаружена",
        "verdict_localized": "Typed signature risk",
        "confirmed_red_flag": level in {"danger", "critical"},
        "typed_signature": {
            "domain": domain,
            "primaryType": typed.get("primaryType") if isinstance(typed, dict) else None,
            "spender": spender,
            "amount": amount,
            "deadline": deadline,
            "flags": flags,
        },
        "drainer": {
            "detected": bool(flags),
            "score": min(score, 100),
            "risk": "high" if level in {"danger", "critical"} else "medium",
            "flags": flags,
            "summary": "Typed signature may grant spending permission.",
        },
        "permissions_summary": {
            "can_spend": "spender_permission" in flags or "permit_signature" in flags,
            "unlimited": False,
            "spender": spender,
            "spend_limit": amount,
            "revoke_difficulty": "high" if "permit_signature" in flags else "unknown",
            "summary": "This typed signature may authorize token spending without a normal transaction.",
        },
        "what_can_happen": "This signature may authorize token spending or advanced wallet permissions.",
        "worst_case": "Worst case: a malicious typed signature can authorize token spending without a normal approval transaction.",
        "details": {"typed_signature": typed},
    }

def _attach_ux_risk_blocks(out: dict, lang: str) -> dict:
    if not isinstance(out, dict):
        return out

    is_ru = lang == "ru"
    is_uk = lang == "uk"
    what_override = out.pop("what_override", None)
    kind = str(out.get("kind") or "").lower().strip()
    level = str(out.get("level") or "").lower().strip()
    target = str(out.get("normalized_input") or out.get("input") or "").strip()
    host = str(out.get("host") or "").lower().strip()

    evidence = out.get("evidence") or []
    codes = {str(x.get("code") or "").lower().strip() for x in evidence if isinstance(x, dict)}
    sources = out.get("sources") or []
    # Pure internal verdict:
    # external sources are visible only as reference, never as final malicious_sources.
    _external_names = {"virustotal", "google_safe_browsing", "urlscan", "external_sources"}

    existing_malicious_sources = [
        str(x)
        for x in (out.get("malicious_sources") or [])
        if str(x).lower() not in _external_names
    ]

    fallback_internal_malicious_sources = [
        str(s.get("name") or s.get("source") or "")
        for s in sources
        if str(s.get("status") or "").lower() == "malicious"
        and str(s.get("name") or s.get("source") or "").lower() not in _external_names
    ]

    malicious_sources = existing_malicious_sources or fallback_internal_malicious_sources

    reasons = []

    def has(*names):
        return any(n in codes for n in names)

    if has("gsb_match"):
        reasons.append("Google Safe Browsing confirmed this as a threat")
    if has("vt_detection"):
        reasons.append("VirusTotal has malicious detections")
    if has("brand_spoofing", "brand_impersonation", "brand_plus_scam_keywords"):
        reasons.append("the domain imitates a trusted brand")
    if has("fake_support_language") or "support" in host:
        reasons.append("it looks like fake support")
    if has("seed_phrase_request", "secret_phrase_request", "recovery_phrase_request"):
        reasons.append("it may ask for a seed/recovery phrase")
    if has("private_key_request", "private_key_hex_found"):
        reasons.append("it may expose or request a private key")
    if has("wallet_connect_prompt", "connect_wallet_prompt"):
        reasons.append("it pushes wallet connection")
    if has("claim_prompt", "airdrop_language"):
        reasons.append("it uses claim/airdrop pressure")
    if has("verify_wallet_prompt"):
        reasons.append("it asks to verify a wallet/account")
    if has("wallet_import_prompt"):
        reasons.append("it may ask to import a wallet")
    if has("token_approval"):
        reasons.append("it may lead to risky token approval")
    if has("wallet_drainer_hint"):
        reasons.append("it has wallet-drainer wording")
    if has("honeypot_detected"):
        reasons.append("honeypot risk was detected")
    if has("honeypot_medium_risk"):
        reasons.append("token sell-risk indicators were found")
    if has("unverified_address", "unverified_or_wallet"):
        reasons.append("the address/contract is not verified by explorers")
    if has("domain_resolution_failed", "urlscan_dns_error"):
        reasons.append("the domain does not resolve correctly")

    if kind in {"url", "domain"}:
        rb = build_url_risk_blocks(level, host, codes, lang)
        what = rb["what"]
        worst = rb["worst"]

        if has("brand_spoofing", "brand_impersonation", "brand_plus_scam_keywords") and ("metamask" in host):
            what = "Это похоже на фейковую страницу MetaMask. Она может увести тебя на поддельную поддержку, подключение кошелька или вредную подпись." if is_ru else "This looks like a fake MetaMask page. It may push you into fake support, wallet connection, or a malicious signature."
            worst = "Худший сценарий: ты подключишь кошелёк или подпишешь действие, после чего злоумышленник сможет украсть активы." if is_ru else "Worst case: you connect your wallet or sign an action, allowing an attacker to steal assets."
        elif has("brand_spoofing", "brand_impersonation", "brand_plus_scam_keywords"):
            what = "Домен похож на подделку известного бренда. Его цель может быть — заставить тебя довериться фейковой странице." if is_ru else "The domain looks like a trusted-brand impersonation. Its goal may be to make you trust a fake page."
            worst = "Худший сценарий: ввод данных, подключение кошелька или подпись на такой странице приведёт к потере доступа или средств." if is_ru else "Worst case: entering data, connecting a wallet, or signing there can lead to lost access or funds."
        elif has("gsb_match", "vt_detection"):
            what = "Внешние security-источники уже отметили этот объект как угрозу. Это не просто подозрение, а подтверждённый красный флаг." if is_ru else "External security sources already flagged this as a threat. This is not just suspicion; it is a confirmed red flag."
            worst = "Худший сценарий: сайт может использовать фишинг, вредный редирект или сценарий кражи доступа." if is_ru else "Worst case: the site may use phishing, malicious redirects, or an access-theft flow."
        elif has("seed_phrase_request", "private_key_request", "wallet_import_prompt"):
            what = "Страница может пытаться получить seed phrase, private key или импорт кошелька. Нормальные сервисы этого не требуют." if is_ru else "The page may try to get a seed phrase, private key, or wallet import. Legitimate services do not need that."
            worst = "Худший сценарий: после ввода seed/private key кошелёк полностью компрометирован." if is_ru else "Worst case: after entering a seed/private key, the wallet is fully compromised."
        elif has("wallet_connect_prompt", "connect_wallet_prompt", "claim_prompt", "airdrop_language", "verify_wallet_prompt"):
            what = "Страница подталкивает к подключению кошелька, claim/airdrop или verify wallet. Риск начинается не при открытии сайта, а при подписи." if is_ru else "The page pushes wallet connection, claim/airdrop, or wallet verification. The risk starts when you sign, not just when you open it."
            worst = "Худший сценарий: следующая подпись может дать разрешение на списание токенов или запустить drainer-сценарий." if is_ru else "Worst case: the next signature may grant token spending permission or trigger a drainer flow."
        elif level == "safe":
            what = "По этой ссылке не найдено явных scam-сигналов в доступных источниках." if is_ru else "No obvious scam signals were found for this link in available sources."
            worst = "Риск остаётся только если позже сайт попросит seed phrase, private key, wallet approval или подозрительную подпись." if is_ru else "Remaining risk appears only if the site later asks for a seed phrase, private key, wallet approval, or suspicious signature."
        else:
            what = "Есть риск-сигналы по ссылке, но их нужно оценивать вместе с источниками и evidence ниже." if is_ru else "There are risk signals for this link; review them together with the sources and evidence below."
            worst = "Худший сценарий зависит от следующего действия: ввод данных, подключение кошелька или подпись." if is_ru else "Worst case depends on the next action: entering data, connecting a wallet, or signing."

    elif kind == "transaction":
        tx = (out.get("details") or {}).get("transaction") or {}
        perm = out.get("permissions_summary") or {}
        rep = perm.get("spender_reputation") or {}
        method = str(tx.get("method") or "")
        spender = str(tx.get("spender") or "").strip()
        spender_label = str(perm.get("spender_label") or rep.get("label") or "").strip()
        spender_trust = str(perm.get("spender_trust") or rep.get("trust") or "").lower().strip()
        token_names = ", ".join([str(x) for x in (perm.get("tokens") or tx.get("tokens") or []) if x])
        token_part_ru = token_names if token_names else "токены"
        token_part_en = token_names if token_names else "tokens"
        spender_part = spender_label or spender

        if tx.get("type") == "erc20_approve" and tx.get("unlimited"):
            if spender_trust == "trusted":
                what = (f"Ты даёшь безлимитный доступ к {token_part_ru} доверенному spender: {spender_part}. Это нормально для DEX/Router, но всё равно даёт полный доступ к этим токенам."
                        if is_ru else
                        f"You are giving unlimited {token_part_en} access to a trusted spender: {spender_part}. This can be normal for a DEX/router, but it still gives full access to those tokens.")
                worst = ("Худший сценарий: если ты ошибся сайтом или подпись пришла не от ожидаемого сервиса, разрешённые токены могут быть списаны без новой подписи."
                         if is_ru else
                         "Worst case: if you are on the wrong site or the signature is not from the expected service, approved tokens can be spent without another signature.")
            elif spender_trust == "unknown":
                what = (f"Ты даёшь безлимитный доступ к {token_part_ru} неизвестному spender: {spender_part}. Это высокий риск."
                        if is_ru else
                        f"You are giving unlimited {token_part_en} access to an unknown spender: {spender_part}. This is high risk.")
                worst = ("Худший сценарий: неизвестный spender сможет позже списать все разрешённые токены без новой подписи."
                         if is_ru else
                         "Worst case: the unknown spender can later drain all approved tokens without another signature.")
            else:
                what = (f"Эта подпись вызывает {method} и даёт spender {spender_part} разрешение списывать {token_part_ru} без лимита."
                        if is_ru else
                        f"This signature calls {method} and gives spender {spender_part} unlimited {token_part_en} spending permission.")
                worst = ("Худший сценарий: если spender вредный, он сможет позже списать все разрешённые токены без новой подписи."
                         if is_ru else
                         "Worst case: if the spender is malicious, it can later drain all approved tokens without another signature.")
        elif tx.get("type") == "erc20_approve":
            amount = str(tx.get("amount_raw") or "unknown")
            what = (f"Эта подпись вызывает {method} и разрешает spender {spender} списать сумму: {amount}."
                    if is_ru else
                    f"This signature calls {method} and allows spender {spender} to spend amount: {amount}.")
            worst = ("Худший сценарий: разрешённая сумма может быть списана spender-адресом."
                     if is_ru else
                     "Worst case: the approved amount can be spent by the spender address.")
        elif tx.get("type") == "erc20_transfer_from":
            what = ("Это transferFrom: транзакция пытается переместить токены от одного адреса к другому."
                    if is_ru else
                    "This is transferFrom: the transaction attempts to move tokens from one address to another.")
            worst = ("Худший сценарий: если действие неожиданное, токены могут быть переведены без понимания пользователем."
                     if is_ru else
                     "Worst case: if unexpected, tokens may be moved without the user understanding the action.")
        elif tx.get("type") == "erc20_transfer":
            what = ("Это обычный transfer токенов на другой адрес."
                    if is_ru else
                    "This is a regular token transfer to another address.")
            worst = ("Худший сценарий: средства уйдут на указанный адрес, если ты подтверждаешь не тот получатель."
                     if is_ru else
                     "Worst case: funds go to the specified address if you confirm the wrong recipient.")
        else:
            what = ("Обнаружены данные EVM-транзакции, но метод пока не распознан."
                    if is_ru else
                    "EVM transaction data was detected, but the method is not recognized yet.")
            worst = ("Худший сценарий зависит от метода транзакции и адреса получателя."
                     if is_ru else
                     "Worst case depends on the transaction method and recipient address.")

    elif kind in {"wallet", "contract"}:
        if has("honeypot_detected"):
            what = "Контракт показывает honeypot-риск: купить может быть легче, чем продать или вывести позицию." if is_ru else "The contract shows honeypot risk: buying may be easier than selling or exiting the position."
            worst = "Худший сценарий: токены невозможно продать, а вложенные средства застрянут." if is_ru else "Worst case: the tokens cannot be sold and funds get trapped."
        elif has("token_approval", "wallet_drainer_hint"):
            what = "Контракт/адрес связан с рискованным approval или drainer-паттерном." if is_ru else "The contract/address is linked to risky approval or drainer-like patterns."
            worst = "Худший сценарий: approval даст доступ к токенам, и они могут быть списаны." if is_ru else "Worst case: an approval gives token access and funds can be drained."
        elif has("unverified_address", "unverified_or_wallet"):
            what = "Explorer не подтвердил контракт достаточно надёжно. Это не доказательство скама, но снижает доверие." if is_ru else "Explorers did not confirm the contract strongly enough. This is not proof of scam, but lowers trust."
            worst = "Худший сценарий: скрытая логика контракта проявится только после покупки, перевода или approval." if is_ru else "Worst case: hidden contract logic appears only after buying, transferring, or approving."
        elif level == "safe":
            what = "По этому контракту/адресу не найдено явных honeypot, malicious или scam-флагов в доступных источниках." if is_ru else "No obvious honeypot, malicious, or scam flags were found for this contract/address in available sources."
            worst = "Это не означает, что любая будущая подпись безопасна. Approval/permit нужно проверять отдельно по данным транзакции." if is_ru else "This does not mean every future signature is safe. Approval/permit must be checked separately from transaction data."
        else:
            what = "У контракта/адреса есть ончейн-риск-сигналы. Смотри evidence и источники ниже." if is_ru else "The contract/address has on-chain risk signals. Review evidence and sources below."
            worst = "Худший сценарий: потеря токенов через approval, honeypot-логику или вредную подпись." if is_ru else "Worst case: token loss through approval, honeypot logic, or a malicious signature."

    else:
        if has("seed_phrase_request", "private_key_request", "wallet_drainer_hint"):
            what = "Текст содержит признаки прямой попытки украсть доступ к кошельку." if is_ru else "The text contains signs of a direct attempt to steal wallet access."
            worst = "Худший сценарий: пользователь вводит seed/private key и полностью теряет кошелёк." if is_ru else "Worst case: the user enters a seed/private key and fully loses the wallet."
        elif level == "safe":
            what = "В этом объекте не найдено явных критических scam-сигналов." if is_ru else "No obvious critical scam signals were found in this object."
            worst = "Главный риск появится только если дальше будет подпись, approval или запрос секретных данных." if is_ru else "The main risk appears only if a signature, approval, or secret-data request follows."
        else:
            what = "Обнаружены риск-сигналы в тексте или объекте проверки." if is_ru else "Risk signals were detected in the text or scanned object."
            worst = "Худший сценарий: пользователь выполняет действие, которое раскрывает доступ или активы." if is_ru else "Worst case: the user performs an action that exposes access or assets."

    out["what_can_happen"] = what_override or what
    out["worst_case"] = worst
    out["risk_reasons"] = reasons[:6]
    out["malicious_sources"] = out.get("malicious_sources") or malicious_sources

    out["permissions_summary"] = out.get("permissions_summary") or {
        "can_spend": False,
        "unlimited": False,
        "tokens": [],
        "spend_limit": None,
        "revoke_difficulty": "unknown",
        "summary": "" if level == "safe" else (
            "Точные разрешения видны только из транзакции/подписи." if is_ru else
            "Точні дозволи видно лише з транзакції/підпису." if is_uk else
            "Exact permissions are visible only from transaction/signature data."
        ),
    }

    return out


# =========================================================
# RISK SIGNALS / CONTENT ANALYSIS
# =========================================================
TRUSTED_BRANDS = [
    "noytrix.com",
    "noytrixapp.com",
    "uniswap.org",
    "app.uniswap.org",
    "pancakeswap.finance",
    "app.aave.com",
    "curve.fi",
    "opensea.io",
    "rarible.com",
    "blur.io",
    "binance.com",
    "metamask.io",
    "coinbase.com",
    "kraken.com",
    "trustwallet.com",
    "tether.to",
    "etherscan.io",
    "bscscan.com",
    "solana.com",
    "phantom.app",
    "ledger.com",
    "trezor.io",
    "telegram.org",
    "discord.com",
    "x.com",
    "twitter.com",
]

SCAM_PATTERNS = [
    (re.compile(r"\bseed phrase\b", re.I), "seed_phrase_request", 35),
    (re.compile(r"\bsecret phrase\b", re.I), "secret_phrase_request", 35),
    (re.compile(r"\brecovery phrase\b", re.I), "recovery_phrase_request", 35),
    (re.compile(r"\bprivate key\b", re.I), "private_key_request", 40),
    (re.compile(r"\bwallet ?connect\b", re.I), "wallet_connect_prompt", 10),
    (re.compile(r"\bclaim (now|reward|tokens?|airdrop)\b", re.I), "claim_prompt", 16),
    (re.compile(r"\bairdrop\b", re.I), "airdrop_language", 10),
    (re.compile(r"\bverify (wallet|account)\b", re.I), "verify_wallet_prompt", 18),
    (re.compile(r"\bconnect wallet\b", re.I), "connect_wallet_prompt", 10),
    (re.compile(r"\bwallet validation\b", re.I), "wallet_validation_prompt", 18),
    (re.compile(r"\bsign approval\b", re.I), "approval_signature_prompt", 24),
    (re.compile(r"\bsign\b.{0,30}\bpermit\b.{0,30}\b(transaction|signature)\b", re.I), "permit_signature_prompt", 42),
    (re.compile(r"\bunlock withdrawal\b", re.I), "unlock_withdrawal_lure", 24),
    (re.compile(r"\bsupport (team|agent)\b", re.I), "fake_support_language", 14),
    (re.compile(r"\bimport wallet\b", re.I), "wallet_import_prompt", 20),
    (re.compile(r"\bunlimited approval\b", re.I), "token_approval", 12),
    (re.compile(r"\brequires\b.{0,50}\b(seed phrase|private key|recovery phrase)\b", re.I), "explicit_secret_required", 55),
    (re.compile(r"\b(wallet|account)\b.{0,40}\bsuspended\b", re.I), "fake_suspension_lure", 22),
    (re.compile(r"\bdeposit\b.{0,40}\b(activate|verify|claim|reward)\b", re.I), "deposit_to_activate_scam", 45),
    (re.compile(r"\bdrain(er|ing)?\b", re.I), "wallet_drainer_hint", 22),
    (re.compile(r"\bsend\b.{0,20}\bbtc\b.{0,30}\b(get|receive|back|double)\b", re.I), "btc_giveaway_scam", 45),
    (re.compile(r"\b(double|2x|x2)\b.{0,20}\b(btc|eth|usdt|crypto)\b", re.I), "doubling_scam", 45),
    (re.compile(r"\bofficial\b.{0,20}\bgiveaway\b", re.I), "fake_official_giveaway", 40),
    (re.compile(r"\bsend.{0,30}(receive|get back).{0,20}(btc|eth|usdt|bnb|sol)\b", re.I), "send_receive_scam", 45),
    (re.compile(r"\b(elon|musk|vitalik|binance|coinbase).{0,30}giveaway\b", re.I), "celebrity_giveaway_scam", 50),
    (re.compile(r"\bbonus after (transfer|deposit|send)\b", re.I), "bonus_after_transfer", 40),
    (re.compile(r"\b(мнемоник|сид.?фраз|приватн.{0,5}ключ|секретн.{0,5}фраз)\b", re.I), "ru_seed_request", 40),
    (re.compile(r"\b(отправ|пришли).{0,20}(btc|eth|usdt).{0,30}(получ|назад|обратно)\b", re.I), "ru_btc_giveaway", 45),
]

BRAND_SPOOF_HINTS = [
    "binance",
    "metamask",
    "coinbase",
    "kraken",
    "trustwallet",
    "ledger",
    "trezor",
    "phantom",
    "etherscan",
    "bscscan",
]

SUSPICIOUS_HOST_KEYWORDS = {
    "airdrop": 12,
    "bonus": 10,
    "claim": 12,
    "gift": 9,
    "verify": 10,
    "login": 9,
    "support": 9,
    "wallet": 8,
    "connect": 8,
    "reward": 9,
    "secure": 6,
}

def _looks_like_brand_spoof(host: str) -> Tuple[bool, list[dict]]:
    host = (host or "").lower().strip()
    evidence = []
    if not host:
        return False, evidence

    root = _host_root_domain(host)
    trusted_roots = {_host_root_domain(x) for x in TRUSTED_BRANDS}
    if root in trusted_roots or host in [x.lower() for x in TRUSTED_BRANDS]:
        return False, []

    for hint in BRAND_SPOOF_HINTS:
        if hint in host:
            if root not in trusted_roots:
                evidence.append(
                    {
                        "code": "brand_spoofing",
                        "severity": 24,
                        "text": f"Host contains well-known brand fragment '{hint}' but is not the official root domain.",
                    }
                )
                return True, evidence

    for trusted in TRUSTED_BRANDS:
        root_trusted = _host_root_domain(trusted)
        base = root_trusted.split(".")[0]
        if base in host and root != root_trusted:
            evidence.append(
                {
                    "code": "brand_impersonation",
                    "severity": 26,
                    "text": f"Host resembles trusted brand '{root_trusted}' but does not match the official domain.",
                }
            )
            return True, evidence

    return False, evidence

def _analyze_text_content(text: str) -> dict:
    txt = (text or "")[:200000]
    evidence = []
    score = 0

    for rx, code, sev in SCAM_PATTERNS:
        if rx.search(txt):
            evidence.append({"code": code, "severity": sev, "text": f"Matched content pattern: {code}"})
            score += sev

    if RE_PRIVATE_KEY_HEX.search(txt):
        evidence.append({"code": "private_key_hex_found", "severity": 45, "text": "Potential private key pattern found in content."})
        score += 45

    return {
        "score": min(score, 100),
        "evidence": evidence,
    }

def _heuristics_for_host(host: str) -> list[dict]:
    host = (host or "").lower().strip()
    out: list[dict] = []
    if not host:
        return out

    for kw, sev in SUSPICIOUS_HOST_KEYWORDS.items():
        if kw in host:
            out.append(
                {
                    "code": f"host_keyword_{kw}",
                    "severity": sev,
                    "text": f"Host contains suspicious keyword '{kw}'.",
                }
            )

    hyphen_count = host.count("-")
    if hyphen_count >= 2:
        out.append(
            {
                "code": "hyphenated_suspicious_host",
                "severity": 6,
                "text": "Host uses multiple hyphens, often seen on fake promo/support domains.",
            }
        )

    brand_words = [x for x in BRAND_SPOOF_HINTS if x in host]
    scam_words = [x for x in SUSPICIOUS_HOST_KEYWORDS if x in host]
    if brand_words and scam_words:
        out.append(
            {
                "code": "brand_plus_scam_keywords",
                "severity": 28,
                "text": "Host mixes trusted-brand wording with common phishing/scam keywords.",
            }
        )

    return out

async def _fetch_page(url: str) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; NoytrixScan/1.0; +https://noytrix.app)",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        async with httpx.AsyncClient(timeout=SCAN_TIMEOUT, follow_redirects=True, max_redirects=MAX_REDIRECTS, verify=False) as cl:
            r = await cl.get(url, headers=headers)
            final_url = str(r.url)
            content_type = (r.headers.get("content-type") or "").lower()
            body = r.text[:SCAN_MAX_BYTES]
            return {
                "ok": True,
                "status_code": r.status_code,
                "final_url": final_url,
                "content_type": content_type,
                "headers": dict(r.headers),
                "html": body,
            }
    except httpx.TimeoutException:
        return {"ok": False, "status": "timeout", "error": "timeout"}
    except Exception as e:
        return {"ok": False, "status": "error", "error": str(e)}

def _extract_visible_text_from_html(html: str) -> str:
    try:
        soup = BeautifulSoup(html or "", "lxml")
        for tag in soup.find_all(["script", "style", "noscript", "svg", "meta"]):
            tag.decompose()
        return soup.get_text(" ", strip=True)[:120000]
    except Exception:
        return (html or "")[:120000]

def _extract_page_meta(html: str) -> dict:
    try:
        soup = BeautifulSoup(html or "", "lxml")
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        forms = len(soup.find_all("form"))
        password_inputs = len(soup.find_all("input", {"type": "password"}))
        iframes = len(soup.find_all("iframe"))
        buttons = len(soup.find_all(["button"]))
        links = len(soup.find_all("a"))
        return {
            "title": title,
            "forms": forms,
            "password_inputs": password_inputs,
            "iframes": iframes,
            "buttons": buttons,
            "links": links,
        }
    except Exception:
        return {"title": "", "forms": 0, "password_inputs": 0, "iframes": 0, "buttons": 0, "links": 0}

# =========================================================
# EXTERNAL CHECKS
# =========================================================
def _parse_http_error_status(exc: Exception) -> int | None:
    try:
        if isinstance(exc, httpx.HTTPStatusError):
            return int(exc.response.status_code)
    except Exception:
        pass
    return None

def _vt_url_id(url: str) -> str:
    clean = (url or "").strip()
    return base64.urlsafe_b64encode(clean.encode("utf-8")).decode("utf-8").strip("=")

async def _check_virustotal_url(url: str) -> dict:
    if not VT_API_KEY:
        return _mk_source("virustotal", "invalid_key", details={"configured": False})

    try:
        url_id_b64 = _vt_url_id(url)
        headers = {"x-apikey": VT_API_KEY}
        async with httpx.AsyncClient(timeout=SCAN_TIMEOUT) as cl:
            r = await cl.get(f"https://www.virustotal.com/api/v3/urls/{url_id_b64}", headers=headers)

            if r.status_code == 404:
                r2 = await cl.post("https://www.virustotal.com/api/v3/urls", headers=headers, data={"url": url})
                if r2.status_code in (200, 202):
                    return _mk_source(
                        "virustotal",
                        "no_data",
                        details={"submitted": True, "status_code": r2.status_code},
                        evidence=[{"code": "submitted_for_analysis", "severity": 0, "text": "URL submitted to VirusTotal, no completed verdict yet."}],
                    )
                if r2.status_code in (401, 403):
                    return _mk_source("virustotal", "invalid_key", details={"status_code": r2.status_code})
                if r2.status_code == 429:
                    return _mk_source("virustotal", "quota", details={"status_code": 429})
                return _mk_source("virustotal", "error", details={"status_code": r2.status_code, "body": r2.text[:400]})

            if r.status_code in (401, 403):
                return _mk_source("virustotal", "invalid_key", details={"status_code": r.status_code})
            if r.status_code == 429:
                return _mk_source("virustotal", "quota", details={"status_code": 429})

            if r.status_code == 400:
                r2 = await cl.post("https://www.virustotal.com/api/v3/urls", headers=headers, data={"url": url})
                if r2.status_code in (200, 202):
                    return _mk_source(
                        "virustotal",
                        "no_data",
                        details={"submitted": True, "status_code": r2.status_code, "fallback_after_400": True},
                        evidence=[{"code": "submitted_for_analysis", "severity": 0, "text": "URL submitted to VirusTotal after direct lookup returned 400."}],
                    )
                return _mk_source("virustotal", "error", details={"status_code": r.status_code, "body": r.text[:400]})

            r.raise_for_status()
            data = r.json()
            attrs = ((data.get("data") or {}).get("attributes") or {})
            stats = (attrs.get("last_analysis_stats") or {})
            malicious = int(stats.get("malicious") or 0)
            suspicious = int(stats.get("suspicious") or 0)
            harmless = int(stats.get("harmless") or 0)
            undetected = int(stats.get("undetected") or 0)

            from urllib.parse import urlparse as _up
            _host = _up(url).hostname or ""
            _trusted = any(_host == d or _host.endswith("." + d) for d in TRUSTED_BRANDS)
            if (malicious > 0 or suspicious > 0) and not (_trusted and malicious <= 2 and suspicious <= 2):
                return _mk_source(
                    "virustotal",
                    "malicious",
                    verdict="danger",
                    details={"analysis_stats": stats},
                    evidence=[{"code": "vt_detection", "severity": 40, "text": f"VirusTotal flagged URL: malicious={malicious}, suspicious={suspicious}."}],
                )

            if harmless > 0 or undetected > 0:
                return _mk_source(
                    "virustotal",
                    "clean",
                    verdict="clean",
                    details={"analysis_stats": stats},
                    evidence=[{"code": "vt_clean", "severity": 0, "text": f"VirusTotal has no malicious detections. harmless={harmless}, undetected={undetected}."}],
                )

            return _mk_source("virustotal", "no_data", details={"analysis_stats": stats})
    except httpx.TimeoutException:
        return _mk_source("virustotal", "timeout")
    except Exception as e:
        return _mk_source("virustotal", "error", details={"error": str(e)})

async def _check_google_safe_browsing(url: str) -> dict:
    if not GOOGLE_SAFE_BROWSING_KEY:
        return _mk_source("google_safe_browsing", "invalid_key", details={"configured": False})

    payload = {
        "client": {"clientId": "noytrix", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url}],
        },
    }

    try:
        async with httpx.AsyncClient(timeout=SCAN_TIMEOUT) as cl:
            r = await cl.post(
                f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={GOOGLE_SAFE_BROWSING_KEY}",
                json=payload,
            )
            if r.status_code in (401, 403):
                return _mk_source("google_safe_browsing", "invalid_key", details={"status_code": r.status_code})
            if r.status_code == 429:
                return _mk_source("google_safe_browsing", "quota", details={"status_code": 429})

            r.raise_for_status()
            data = r.json()
            matches = data.get("matches") or []

            if matches:
                return _mk_source(
                    "google_safe_browsing",
                    "malicious",
                    verdict="danger",
                    details={"matches": matches},
                    evidence=[{"code": "gsb_match", "severity": 45, "text": f"Google Safe Browsing matched {len(matches)} threat(s)."}],
                )

            return _mk_source(
                "google_safe_browsing",
                "clean",
                verdict="clean",
                details={"matches": []},
                evidence=[{"code": "gsb_clean", "severity": 0, "text": "Google Safe Browsing returned no matches."}],
            )
    except httpx.TimeoutException:
        return _mk_source("google_safe_browsing", "timeout")
    except Exception as e:
        return _mk_source("google_safe_browsing", "error", details={"error": str(e)})

async def _check_urlscan(url: str) -> dict:
    if not URLSCAN_API_KEY:
        return _mk_source("urlscan", "invalid_key", details={"configured": False})

    headers = {"API-Key": URLSCAN_API_KEY, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=SCAN_TIMEOUT) as cl:
            r = await cl.post("https://urlscan.io/api/v1/scan/", headers=headers, json={"url": url, "visibility": "private"})

            if r.status_code in (401, 403):
                return _mk_source("urlscan", "invalid_key", details={"status_code": r.status_code})
            if r.status_code == 429:
                return _mk_source("urlscan", "quota", details={"status_code": 429})

            if r.status_code in (200, 202):
                data = r.json()
                return _mk_source(
                    "urlscan",
                    "no_data",
                    details={"submitted": True, "api_result": data},
                    evidence=[{"code": "urlscan_submitted", "severity": 0, "text": "URL submitted to urlscan. Final verdict not ready yet."}],
                )

            if r.status_code == 400:
                body = r.text[:800]
                low = body.lower()
                if "dns error" in low or "could not resolve domain" in low:
                    return _mk_source(
                        "urlscan",
                        "error",
                        verdict="unknown",
                        details={"status_code": 400, "body": body},
                        evidence=[{"code": "urlscan_dns_error", "severity": 8, "text": "urlscan could not resolve domain DNS."}],
                    )
                return _mk_source("urlscan", "error", details={"status_code": 400, "body": body})

            return _mk_source("urlscan", "error", details={"status_code": r.status_code, "body": r.text[:300]})
    except httpx.TimeoutException:
        return _mk_source("urlscan", "timeout")
    except Exception as e:
        return _mk_source("urlscan", "error", details={"error": str(e)})

def _explorer_v2_base() -> str:
    return "https://api.etherscan.io/v2/api"

def _explorer_chain_id(chain: str) -> str:
    return "1" if chain == "eth" else "56"


KNOWN_MALICIOUS_SPENDER_BOOK = {
    "0xdead000000000000000000000000000000beef00": {"label": "Test Drainer Spender", "category": "wallet_drainer", "trust": "malicious"},
}

TRUSTED_SPENDER_BOOK = {
    "0x1111111254eeb25477b68fb85ed929f73a960582": {"label": "1inch Aggregation Router", "category": "dex_router", "trust": "trusted"},
    "0x1111111254fb6c44bac0bed2854e76f90643097d": {"label": "1inch Router", "category": "dex_router", "trust": "trusted"},
    "0xe592427a0aece92de3edee1f18e0157c05861564": {"label": "Uniswap V3 SwapRouter", "category": "dex_router", "trust": "trusted"},
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": {"label": "Uniswap Universal Router", "category": "dex_router", "trust": "trusted"},
    "0x000000000022d473030f116ddee9f6b43ac78ba3": {"label": "Uniswap Permit2", "category": "permit_manager", "trust": "trusted"},
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff": {"label": "0x Exchange Proxy", "category": "dex_router", "trust": "trusted"},
}

def _normalize_spender_reputation(rep: dict | None, addr: str) -> dict:
    rep = rep or {}
    label = rep.get("label")
    normalized = build_spender_reputation(addr, label)

    out = dict(rep)
    out.setdefault("address", addr)
    out.setdefault("label", normalized.get("label"))
    out["trust"] = out.get("trust") or normalized.get("trust") or "unknown"
    out["risk"] = out.get("risk") or normalized.get("risk") or "medium"
    out.setdefault("reasons", [])
    return out


async def _check_spender_reputation(address: str) -> dict:
    return await build_spender_reputation_engine(
        address,
        RE_EVM_ADDR,
        _get_spender_reputation_from_db,
        _normalize_spender_reputation,
        KNOWN_MALICIOUS_SPENDER_BOOK,
        TRUSTED_SPENDER_BOOK,
        _check_etherscan_or_bscscan,
    )


async def _check_etherscan_or_bscscan(address: str, chain: str) -> dict:
    chain = (chain or "").lower().strip()
    if chain not in {"eth", "bsc"}:
        return _mk_source(f"{chain}_explorer", "error", details={"error": "unsupported_chain"})

    api_key = ETHERSCAN_API_KEY if chain == "eth" else BSCSCAN_API_KEY
    base = _explorer_v2_base()
    chain_id = _explorer_chain_id(chain)
    source_name = "etherscan" if chain == "eth" else "bscscan"

    if not api_key:
        return _mk_source(source_name, "invalid_key", details={"configured": False})

    try:
        async with httpx.AsyncClient(timeout=SCAN_TIMEOUT) as cl:
            r = await cl.get(
                base,
                params={
                    "chainid": chain_id,
                    "module": "contract",
                    "action": "getsourcecode",
                    "address": address,
                    "apikey": api_key,
                },
            )

            if r.status_code in (401, 403):
                return _mk_source(source_name, "invalid_key", details={"status_code": r.status_code})
            if r.status_code == 429:
                return _mk_source(source_name, "quota", details={"status_code": r.status_code})

            r.raise_for_status()
            data = r.json()
            result = data.get("result") or []

            if isinstance(result, str):
                raw_res = str(result or "")
                if "deprecated" in raw_res.lower():
                    return _mk_source(source_name, "error", details={"raw": data, "reason": "deprecated_endpoint_response"})
                if str(data.get("status") or "") == "0":
                    return _mk_source(source_name, "no_data", details={"raw": data})

            if not isinstance(result, list) or not result:
                return _mk_source(source_name, "no_data", details={"raw": data})

            row = result[0] or {}
            source_code = str(row.get("SourceCode") or "").strip()
            contract_name = str(row.get("ContractName") or "").strip()
            implementation = str(row.get("Implementation") or "").strip()
            proxy = str(row.get("Proxy") or "").strip()

            tx_count = None
            try:
                r2 = await cl.get(
                    base,
                    params={
                        "chainid": chain_id,
                        "module": "account",
                        "action": "txlist",
                        "address": address,
                        "startblock": 0,
                        "endblock": 99999999,
                        "page": 1,
                        "offset": 5,
                        "sort": "desc",
                        "apikey": api_key,
                    },
                )
                if r2.status_code == 200:
                    d2 = r2.json()
                    if isinstance(d2.get("result"), list):
                        tx_count = len(d2["result"])
            except Exception:
                pass

            is_verified_contract = bool(source_code)
            details = {
                "contract_name": contract_name,
                "verified_contract": is_verified_contract,
                "implementation": implementation,
                "is_proxy": proxy == "1",
                "recent_tx_sample_count": tx_count,
                "chain_id": chain_id,
                "raw": data,
            }

            if is_verified_contract:
                return _mk_source(
                    source_name,
                    "clean",
                    verdict="clean",
                    details=details,
                    evidence=[{"code": "verified_contract", "severity": 0, "text": f"{source_name} shows verified contract source."}],
                )

            return _mk_source(
                source_name,
                "no_data",
                details=details,
                evidence=[{"code": "unverified_or_wallet", "severity": 0, "text": f"{source_name} did not confirm verified source for this address."}],
            )
    except httpx.TimeoutException:
        return _mk_source(source_name, "timeout")
    except Exception as e:
        return _mk_source(source_name, "error", details={"error": str(e)})
async def _check_dexscreener_address(address: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=SCAN_TIMEOUT) as cl:
            r = await cl.get(f"https://api.dexscreener.com/latest/dex/tokens/{address}")
            if r.status_code == 404:
                return _mk_source("dexscreener", "no_data", details={"status_code": 404})
            if r.status_code == 429:
                return _mk_source("dexscreener", "quota", details={"status_code": 429})

            r.raise_for_status()
            data = r.json()
            pairs = data.get("pairs") or []
            if not pairs:
                return _mk_source("dexscreener", "no_data", details={"pairs": 0})

            pair = pairs[0] or {}
            base_token = pair.get("baseToken") or {}
            labels = pair.get("labels") or []
            websites = ((pair.get("info") or {}).get("websites") or [])
            socials = ((pair.get("info") or {}).get("socials") or [])

            return _mk_source(
                "dexscreener",
                "clean",
                verdict="clean",
                details={
                    "pair_count": len(pairs),
                    "baseToken": base_token,
                    "liquidity": pair.get("liquidity"),
                    "fdv": pair.get("fdv"),
                    "marketCap": pair.get("marketCap"),
                    "dexId": pair.get("dexId"),
                    "chainId": pair.get("chainId"),
                    "labels": labels,
                    "websites": websites,
                    "socials": socials,
                },
                evidence=[{"code": "token_listed", "severity": 0, "text": "Token/pair found on DexScreener."}],
            )
    except httpx.TimeoutException:
        return _mk_source("dexscreener", "timeout")
    except Exception as e:
        return _mk_source("dexscreener", "error", details={"error": str(e)})

async def _check_coingecko_ticker(symbol: str) -> dict:
    market_data = None
    try:
        async with httpx.AsyncClient(timeout=SCAN_TIMEOUT) as cl:
            r = await cl.get(
                "https://api.coingecko.com/api/v3/search",
                params={"query": symbol},
                headers={"Accept": "application/json"},
            )
            if r.status_code == 429:
                return _mk_source("coingecko", "quota", details={"status_code": 429})

            r.raise_for_status()
            data = r.json()
            coins = data.get("coins") or []

            exact = [c for c in coins if str(c.get("symbol") or "").upper() == symbol.upper()]
            if not exact and not coins:
                return _mk_source("coingecko", "no_data", details={"coins": []})

            ranked_pool = exact if exact else coins
            ranked_pool = sorted(
                ranked_pool,
                key=lambda c: (
                    999999 if c.get("market_cap_rank") in (None, "", 0) else int(c.get("market_cap_rank"))
                )
            )

            picked = ranked_pool[0]
            coin_id = picked.get("id")

            if coin_id:
                r2 = await cl.get(
                    "https://api.coingecko.com/api/v3/coins/markets",
                    params={"vs_currency": "usd", "ids": coin_id},
                )
                if r2.status_code == 200:
                    arr = r2.json()
                    if isinstance(arr, list) and arr:
                        market_data = arr[0]

            details = {
                "matchCount": len(exact) if exact else len(coins),
                "picked": picked,
                "all_matches": exact[:10] if exact else coins[:10],
                "marketData": market_data,
            }
            return _mk_source(
                "coingecko",
                "clean",
                verdict="clean",
                details=details,
                evidence=[{"code": "ticker_found", "severity": 0, "text": f"Ticker match found on CoinGecko for {symbol}."}],
            )
    except httpx.TimeoutException:
        return _mk_source("coingecko", "timeout")
    except Exception as e:
        return _mk_source("coingecko", "error", details={"error": str(e)})

async def _check_honeypot_contract(address: str, chain_id: str | None = None) -> dict:
    params = {"address": address}
    if chain_id:
        params["chainID"] = str(chain_id)

    try:
        async with httpx.AsyncClient(timeout=SCAN_TIMEOUT) as cl:
            r = await cl.get(f"{HONEYPOT_API_BASE}/v2/IsHoneypot", params=params, headers={"Accept": "application/json"})

            if r.status_code == 404:
                return _mk_source("honeypot", "no_data", details={"status_code": 404, "address": address, "chain_id": chain_id})
            if r.status_code == 429:
                return _mk_source("honeypot", "quota", details={"status_code": 429, "address": address, "chain_id": chain_id})
            if r.status_code >= 500:
                return _mk_source("honeypot", "error", details={"status_code": r.status_code, "address": address, "chain_id": chain_id, "body": r.text[:600]})

            r.raise_for_status()
            data = r.json() if r.text else {}

            summary = data.get("summary") or {}
            hp_res = data.get("honeypotResult") or {}
            sim_res = data.get("simulationResult") or {}
            contract_code = data.get("contractCode") or {}
            pair = data.get("pair") or {}

            is_honeypot = bool(hp_res.get("isHoneypot") is True)
            risk = str(summary.get("risk") or "").strip().lower()
            risk_level = int(summary.get("riskLevel") or 0)

            details = {
                "raw": data,
                "risk": risk or None,
                "riskLevel": risk_level,
                "is_honeypot": is_honeypot,
                "buy_tax": sim_res.get("buyTax"),
                "sell_tax": sim_res.get("sellTax"),
                "transfer_tax": sim_res.get("transferTax"),
                "simulation_success": data.get("simulationSuccess"),
                "max_buy": (data.get("maxBuy") or {}).get("token"),
                "max_sell": (data.get("maxSell") or {}).get("token"),
                "liquidity": pair.get("liquidity"),
                "pair": pair,
                "router": data.get("router"),
                "open_source": contract_code.get("openSource"),
                "is_proxy": contract_code.get("isProxy"),
                "address": address,
                "chain_id": chain_id,
            }

            if is_honeypot or risk in {"high", "very_high"} or risk_level >= 3:
                return _mk_source(
                    "honeypot",
                    "malicious",
                    verdict="danger",
                    details=details,
                    evidence=[{"code": "honeypot_detected", "severity": 45, "text": "Honeypot API indicates token may be a honeypot."}],
                )

            if risk in {"medium"}:
                return _mk_source(
                    "honeypot",
                    "no_data",
                    verdict="unknown",
                    details=details,
                    evidence=[{"code": "honeypot_medium_risk", "severity": 18, "text": "Honeypot API indicates medium token risk."}],
                )

            return _mk_source(
                "honeypot",
                "clean",
                verdict="clean",
                details=details,
                evidence=[{"code": "honeypot_checked", "severity": 0, "text": "Honeypot check completed without critical findings."}],
            )
    except httpx.TimeoutException:
        return _mk_source("honeypot", "timeout", details={"address": address, "chain_id": chain_id})
    except Exception as e:
        return _mk_source("honeypot", "error", details={"error": str(e), "address": address, "chain_id": chain_id})

# =========================================================
# SCORING / VERDICT ENGINE
# =========================================================
def _community_snapshot(obj: str, kind: str) -> dict:
    data = _community_immunity_compute(obj, kind)
    if not isinstance(data, dict):
        return {
            "community_verdict": "unknown",
            "safe_votes": 0,
            "scam_votes": 0,
            "total_users": 0,
            "immunity_score": 0,
        }

    safe_votes = int(data.get("safe_votes") or 0)
    scam_votes = int(data.get("scam_votes") or 0)
    total_users = int(data.get("total_users") or data.get("checks") or 0)
    if total_users <= 0 and (safe_votes > 0 or scam_votes > 0):
        total_users = safe_votes + scam_votes

    return {
        "community_verdict": data.get("community_verdict", "unknown"),
        "safe_votes": safe_votes,
        "scam_votes": scam_votes,
        "total_users": total_users,
        "immunity_score": int(data.get("immunity_score") or 0),
    }

def _score_scan(sources: list[dict], heuristics: list[dict], page_content: list[dict], community: dict, internal_only: bool = False) -> dict:
    return score_scan(
        sources=sources,
        heuristics=heuristics,
        page_content=page_content,
        community=community,
        internal_only=internal_only,
    )


URL_HARD_EVIDENCE_CODES = {
    "credential_theft_ui",
    "seed_phrase_request",
    "private_key_request",
    "recovery_phrase_request",
    "connect_wallet_reward_flow",
    "possible_js_drainer_flow",
    "approval_or_drain_functions",
    "runtime_approval_or_drain_flow",
    "runtime_secret_phrase_request",
    "runtime_connect_plus_signature_flow",
    "runtime_connect_plus_transaction_flow",
    "headless_possible_js_drainer_flow",
    "headless_approval_or_drain_functions",
    "obfuscated_wallet_drainer_javascript",
    "runtime_wallet_calls_with_obfuscation",
    "compromised_legitimate_site_wallet_flow",
    "compromised_legitimate_redirect_to_lure",
    "hosted_platform_abuse_wallet_flow",
    "brand_impersonation_plus_wallet_pressure",
    "brand_plus_scam_keywords",
    "multi_source_public_scam_match",
    "known_malicious_entity",
    "known_malicious_contract_identity",
    "wallet_drainer_runtime",
    "gsb_match",
    "virustotal_malicious",
    "urlscan_malicious",
    "phishtank_match",
    "openphish_match",
    "scamsniffer_match",
    "cryptoscamdb_match",
    "noytrix_scam_database_match",
    "part_of_known_scam_campaign",
    "very_bad_wallet_reputation",
}

URL_GENERIC_WEB3_NOISE_CODES = {
    "wallet_connect_request",
    "runtime_wallet_connect_request",
    "runtime_many_script_loads",
    "headless_wallet_connect_request",
    "js_decode_chain",
    "js_dynamic_eval_execution",
    "js_string_array_obfuscation",
    "js_computed_property_heavy",
    "js_minified_or_packed_long_lines",
    "js_large_base64_blob",
    "js_high_entropy_payload",
    "js_dynamic_script_loading",
    "js_obfuscation_score",
    "many_external_scripts_with_obfuscation",
    "legitimate_domain_context",
    "legitimate_domain_suspicious_path",
    "legitimate_domain_obfuscated_wallet_flow",
    "compromised_site_score",
    "web3_script_reference",
    "fake_support_ui",
    "fake_airdrop_bonus_ui",
    "wallet_connect_pressure",
    "wallet_verification_lure",
    "signature_or_approval_wording",
    "cloned_ui_fingerprint",
    "visual_phishing_score",
    "crypto_lure_score",
    "wallet_trap_score",
    "missing_ns_records",
    "infrastructure_score",
    "historical_threat_memory",
    "domain_age_unavailable",
    "infrastructure_unavailable",
    "redirect_chain_unavailable",
}


def _noytrix_database_match_quality(match: dict) -> dict:
    reputation = (match or {}).get("source_reputation") or {}
    confidence = normalize_score(
        reputation.get("adjusted_confidence")
        or (match or {}).get("confidence")
        or (match or {}).get("base_confidence")
        or 0
    )
    avg_source_trust = normalize_score(
        reputation.get("avg_source_trust")
        or (match or {}).get("source_trust")
        or 0
    )
    max_source_trust = normalize_score(
        reputation.get("max_source_trust")
        or (match or {}).get("max_source_trust")
        or 0
    )
    trusted = (
        confidence >= 50
        or avg_source_trust >= 35
        or max_source_trust >= 50
        or (confidence >= 30 and normalize_score((match or {}).get("risk_score") or 0) >= 90)
    )
    return {
        "confidence": confidence,
        "avg_source_trust": avg_source_trust,
        "max_source_trust": max_source_trust,
        "trusted": trusted,
        "untrusted": confidence <= 0 and avg_source_trust <= 0 and max_source_trust <= 0,
    }


def _build_url_evidence_trace(sources: list[dict], heuristics: list[dict], page_content: list[dict]) -> dict:
    items: list[dict] = []

    def add_item(module: str, ev: dict, source_status: str = "", source_verdict: str = "") -> None:
        if not isinstance(ev, dict):
            return
        code = str(ev.get("code") or "unknown").strip()
        try:
            severity = int(ev.get("severity") or 0)
        except Exception:
            severity = 0
        hard = code in URL_HARD_EVIDENCE_CODES and severity >= 60
        generic_noise = code in URL_GENERIC_WEB3_NOISE_CODES
        if str(source_status).lower() == "malicious" and severity >= 70 and code not in URL_GENERIC_WEB3_NOISE_CODES:
            hard = True
        items.append({
            "module": module,
            "code": code,
            "severity": max(0, min(100, severity)),
            "hard_evidence": bool(hard),
            "generic_web3_noise": bool(generic_noise),
            "source_status": source_status or None,
            "source_verdict": source_verdict or None,
            "text": ev.get("text") or ev.get("message") or "",
        })

    for h in heuristics or []:
        add_item("heuristic", h)

    for e in page_content or []:
        add_item("page_content", e)

    for src in sources or []:
        if not isinstance(src, dict):
            continue
        module = str(src.get("name") or src.get("source") or "source")
        status = str(src.get("status") or "")
        verdict = str(src.get("verdict") or "")
        for ev in src.get("evidence") or []:
            add_item(module, ev, status, verdict)

    items = sorted(items, key=lambda x: int(x.get("severity") or 0), reverse=True)
    hard_items = [x for x in items if x.get("hard_evidence")]
    noise_items = [x for x in items if x.get("generic_web3_noise")]
    return {
        "items": items[:60],
        "hard_evidence_found": bool(hard_items),
        "hard_evidence_codes": sorted({x["code"] for x in hard_items if x.get("code")}),
        "generic_noise_codes": sorted({x["code"] for x in noise_items if x.get("code")}),
        "top_contributors": items[:8],
    }


def _apply_false_positive_safety_gate_to_url_score(score_info: dict, evidence_trace: dict) -> dict:
    out = dict(score_info or {})
    level = str(out.get("level") or "").lower()
    score = normalize_score(out.get("score") or 0)
    has_hard = bool((evidence_trace or {}).get("hard_evidence_found"))
    generic_codes = (evidence_trace or {}).get("generic_noise_codes") or []

    applied = False
    reason = None

    if not has_hard and (level in {"danger", "critical", "high", "malicious"} or score >= 60):
        applied = True
        reason = "soft_or_generic_evidence_only"
        score = min(score, 34)
        out["score"] = score
        out["internal_score"] = min(normalize_score(out.get("internal_score") or score), score)
        out["level"] = "suspicious"
        out["normalized_level"] = "medium"
        out["verdict_en"] = "Suspicious"
        out["verdict_ru"] = "Подозрительно"
        out["confirmed_red_flag"] = False
        out["internal_red_flag"] = False
        out["malicious_sources"] = []
        out["internal_malicious_sources"] = []

    out["false_positive_safety_gate"] = {
        "applied": applied,
        "reason": reason,
        "hard_evidence_found": has_hard,
        "generic_noise_codes": generic_codes,
        "score_after": out.get("score"),
        "level_after": out.get("level"),
    }
    return out


def _source_from_noytrix_scam_database(match: dict) -> dict:
    if not (match or {}).get("matched"):
        return _mk_source(
            "noytrix_scam_database",
            "clean",
            verdict="not_listed",
            details=match or {},
            evidence=[{
                "code": "noytrix_scam_database_checked",
                "severity": 0,
                "text": "Noytrix Scam Database exact-match lookup completed without a listing.",
            }],
        )

    status = str(match.get("status") or "observed").lower()
    level = str(match.get("level") or status or "observed").lower()
    risk_score = normalize_score(match.get("risk_score") or 0)
    reputation_context = (match or {}).get("source_reputation") or {}
    quality = _noytrix_database_match_quality(match)
    source_status = "malicious" if status in {"malicious", "scam", "danger", "critical", "high", "blocked"} else "clean" if status in {"safe", "trusted", "allowlisted", "allowlist"} else "observed"
    if source_status == "malicious" and not quality["trusted"]:
        source_status = "observed"
        level = "observed"
    code = "noytrix_scam_database_match" if source_status == "malicious" else "noytrix_scam_database_safe_match" if source_status == "clean" else "noytrix_scam_database_observed"
    if source_status == "observed" and status in {"malicious", "scam", "danger", "critical", "high", "blocked"}:
        code = "noytrix_scam_database_untrusted_match"
    return _mk_source(
        "noytrix_scam_database",
        source_status,
        verdict=level,
        details=match,
        evidence=[{
            "code": code,
            "severity": risk_score if source_status == "malicious" else 0,
            "text": (
                "Exact trusted match in Noytrix Scam Database."
                if source_status == "malicious"
                else "Exact match in Noytrix Scam Database has no trusted confidence, so it is treated as context only."
                if code == "noytrix_scam_database_untrusted_match"
                else "Exact match in Noytrix Scam Database."
            ),
            "confidence": quality["confidence"],
            "source_trust": quality["avg_source_trust"],
        }],
    )


def _apply_noytrix_database_verdict(score_info: dict, db_match: dict) -> dict:
    out = dict(score_info or {})
    if not (db_match or {}).get("matched") or not db_match.get("force_verdict"):
        out["noytrix_scam_database"] = {
            "applied": False,
            "reason": "no_forceable_exact_match",
            "match": db_match or {},
            "source_reputation": (db_match or {}).get("source_reputation") or {},
        }
        return out

    status = str(db_match.get("status") or "").lower()
    score = normalize_score(db_match.get("risk_score") or 0)
    reputation_context = (db_match or {}).get("source_reputation") or {}
    quality = _noytrix_database_match_quality(db_match)
    db_confidence = quality["confidence"]
    malicious = status in {"malicious", "scam", "danger", "critical", "high", "blocked"}
    safe = status in {"safe", "trusted", "allowlisted", "allowlist"}

    if malicious and not quality["trusted"]:
        out["noytrix_scam_database"] = {
            "applied": False,
            "reason": "untrusted_exact_database_match",
            "match": db_match,
            "source_reputation": reputation_context,
            "quality": quality,
        }
        return out

    if malicious:
        forced_score = max(score, 90)
        forced_level = "critical" if forced_score >= 85 else "danger"
        out["score"] = forced_score
        out["internal_score"] = max(normalize_score(out.get("internal_score") or 0), forced_score)
        out["confidence_score"] = max(normalize_score(out.get("confidence_score") or 0), db_confidence)
        out["confidence"] = out["confidence_score"]
        out["level"] = forced_level
        out["normalized_level"] = forced_level
        out["verdict_en"] = "Critical / Scam" if forced_level == "critical" else "Danger"
        out["verdict_ru"] = "Critical / Scam" if forced_level == "critical" else "Danger"
        out["confirmed_red_flag"] = True
        out["internal_red_flag"] = True
        sources = list(out.get("malicious_sources") or [])
        if "noytrix_scam_database" not in sources:
            sources.append("noytrix_scam_database")
        out["malicious_sources"] = sources
        out["noytrix_scam_database"] = {
            "applied": True,
            "reason": "exact_malicious_database_match",
            "match": db_match,
            "source_reputation": reputation_context,
        }
        return out

    if safe:
        out["score"] = min(score, 5)
        out["internal_score"] = min(normalize_score(out.get("internal_score") or 0), 5)
        out["external_score"] = min(normalize_score(out.get("external_score") or 0), 5)
        out["confidence_score"] = max(normalize_score(out.get("confidence_score") or 0), db_confidence)
        out["confidence"] = out["confidence_score"]
        out["level"] = "safe"
        out["normalized_level"] = "safe"
        out["verdict_en"] = "Safe"
        out["verdict_ru"] = "Safe"
        out["confirmed_red_flag"] = False
        out["internal_red_flag"] = False
        out["external_red_flag"] = False
        out["malicious_sources"] = []
        out["internal_malicious_sources"] = []
        out["noytrix_scam_database"] = {
            "applied": True,
            "reason": "exact_safe_database_match",
            "match": db_match,
            "source_reputation": reputation_context,
        }
        return out

    out["noytrix_scam_database"] = {
        "applied": False,
        "reason": "non_final_database_status",
        "match": db_match,
        "source_reputation": reputation_context,
    }
    return out


def _quick_result_from_noytrix_database(target: str, normalized_input: str, kind: str, lang: str, db_match: dict) -> dict:
    source = _source_from_noytrix_scam_database(db_match)
    status = str((db_match or {}).get("status") or "").lower()
    quality = _noytrix_database_match_quality(db_match)
    malicious = status in {"malicious", "scam", "danger", "critical", "high", "blocked"} and quality["trusted"]
    safe = status in {"safe", "trusted", "allowlisted", "allowlist"}
    score = 90 if malicious else 0 if safe else 0 if quality["untrusted"] else normalize_score((db_match or {}).get("risk_score") or 0)
    level = "critical" if malicious else "safe" if safe else "suspicious"
    reputation_context = (db_match or {}).get("source_reputation") or {}
    confidence = quality["confidence"] if malicious or safe else 0
    evidence = []
    for ev in source.get("evidence") or []:
        evidence.append({"source": source.get("name"), **ev})
    quick_score_info = {
        "score": score,
        "level": level,
        "normalized_level": level,
        "internal_score": score,
        "external_score": 0,
        "internal_level": level,
        "external_level": "safe" if safe else "unknown",
        "confidence": confidence,
        "confidence_score": confidence,
        "confirmed_red_flag": malicious,
        "internal_red_flag": malicious,
        "external_red_flag": False,
        "malicious_sources": ["noytrix_scam_database"] if malicious else [],
        "internal_malicious_sources": ["noytrix_scam_database"] if malicious else [],
        "external_malicious_sources": [],
        "components": {"noytrix_scam_database": score},
        "noytrix_scam_database": {
            "applied": bool((db_match or {}).get("force_verdict")),
            "reason": "exact_database_match_quick_result",
            "match": db_match or {},
        },
        "false_positive_safety_gate": {
            "applied": False,
            "reason": "database_exact_match",
            "hard_evidence_found": malicious,
            "score_after": score,
            "level_after": level,
        },
    }
    quick_evidence_trace = {
        "items": evidence,
        "top_contributors": evidence[:8],
        "hard_evidence_found": malicious,
        "hard_evidence_codes": ["noytrix_scam_database_match"] if malicious else [],
        "generic_noise_codes": [],
    }
    internal_verdict = build_internal_verdict(
        kind=kind,
        target=normalized_input,
        score_info=quick_score_info,
        sources=[source],
        evidence_trace=quick_evidence_trace,
        community={},
        noytrix_database=quick_score_info["noytrix_scam_database"],
        reputation_context=reputation_context,
    )
    out = {
        "ok": True,
        "input": target,
        "normalized_input": normalized_input,
        "kind": kind,
        "kind_localized": _localized_object_kind(kind, lang),
        "score": score,
        "internal_score": score,
        "external_score": 0,
        "internal_level": level,
        "external_level": "safe" if safe else "unknown",
        "confidence": confidence,
        "confidence_score": confidence,
        "internal_red_flag": malicious,
        "external_red_flag": False,
        "internal_only": True,
        "level": level,
        "normalized_level": level,
        "verdict": level,
        "verdict_en": "Critical / Scam" if malicious else "Safe" if safe else "Suspicious",
        "verdict_ru": "Critical / Scam" if malicious else "Safe" if safe else "Suspicious",
        "verdict_localized": "Critical / Scam" if malicious else "Safe" if safe else "Suspicious",
        "confirmed_red_flag": malicious,
        "malicious_sources": ["noytrix_scam_database"] if malicious else [],
        "scoring": {"noytrix_scam_database": score},
        "sources": [source],
        "evidence": evidence,
        "community": {},
        "details": {
            "noytrix_scam_database": {
                "applied": bool((db_match or {}).get("force_verdict")),
                "reason": "exact_database_match_quick_result",
                "match": db_match or {},
            },
            "source_reputation": reputation_context,
            "evidence_trace": evidence,
            "score_trace": {
                "before_safety_gate": {"score": score, "level": level},
                "after_safety_gate": {"score": score, "level": level},
                "components": {"noytrix_scam_database": score},
            },
            "top_score_contributors": evidence[:8],
            "hard_evidence_found": malicious,
            "hard_evidence_codes": ["noytrix_scam_database_match"] if malicious else [],
            "generic_noise_codes": [],
            "false_positive_safety_gate": {
                "applied": False,
                "reason": "database_exact_match",
                "hard_evidence_found": malicious,
                "score_after": score,
                "level_after": level,
            },
            "internal_verdict": internal_verdict,
        },
        "lang": lang,
        "cached": False,
        "cache_source": "noytrix_scam_database",
    }
    out = attach_legacy_fields(out, lang)
    return out


def _is_dominant_top_ticker_match(symbol: str, picked: dict, all_matches: list[dict], market_data: dict | None) -> bool:
    try:
        if not picked:
            return False

        picked_id = str(picked.get("id") or "").strip().lower()
        picked_rank = picked.get("market_cap_rank")
        if picked_rank is None and market_data:
            picked_rank = market_data.get("market_cap_rank")

        try:
            picked_rank_int = int(picked_rank or 0)
        except Exception:
            picked_rank_int = 0

        if picked_rank_int and picked_rank_int <= 20:
            return True

        other_ranks = []
        for m in all_matches or []:
            mid = str(m.get("id") or "").strip().lower()
            if not mid or mid == picked_id:
                continue
            try:
                rk = int(m.get("market_cap_rank") or 0)
                if rk > 0:
                    other_ranks.append(rk)
            except Exception:
                continue

        if picked_rank_int and other_ranks:
            best_other = min(other_ranks)
            if best_other >= picked_rank_int * 20:
                return True

        if symbol.upper() in {"BTC", "ETH", "BNB", "SOL", "XRP"} and picked_rank_int and picked_rank_int <= 100:
            return True

        return False
    except Exception:
        return False



def _apply_reputation_risk_context(out: dict) -> dict:
    if not isinstance(out, dict):
        return out

    try:
        rep = out.get("reputation") or {}
        rep_score = int(rep.get("score") if rep.get("score") is not None else 50)
        entity_type = str(rep.get("entity_type") or "").lower()
    except Exception:
        return out

    if rep_score <= 10 and entity_type in {"evm_address", "wallet", "spender"}:
        out["score"] = max(int(out.get("score") or 0), 85)
        out["internal_score"] = max(int(out.get("internal_score") or 0), 85)
        out["level"] = "danger"
        out["verdict"] = "danger"
        out["reputation_risk_applied"] = {
            "applied": True,
            "reason": "very_bad_wallet_reputation",
            "reputation_score": rep_score,
            "entity_type": entity_type,
        }

        ev = {
            "source": "reputation_engine",
            "code": "very_bad_wallet_reputation",
            "severity": 85,
            "text": "This wallet/address has very bad Noytrix reputation.",
        }
        out.setdefault("evidence", [])
        if not any(isinstance(e, dict) and e.get("code") == ev["code"] for e in out["evidence"]):
            out["evidence"].insert(0, ev)

    return out


def _attach_pg_graph_context(out: dict) -> dict:
    if not isinstance(out, dict) or not pg_get_entity_graph_context:
        return out

    try:
        candidates = [
            str(out.get("normalized_input") or "").strip(),
            str(out.get("host") or "").strip(),
            str(out.get("input") or "").strip(),
        ]

        ctx = None
        for c in candidates:
            if not c:
                continue
            ctx = pg_get_entity_graph_context(c)
            if ctx:
                break

        if not ctx:
            return out

        graph = ctx.get("graph") or {}
        campaign = ctx.get("campaign") or {}
        neighbors = ctx.get("neighbors") or []
        propagation = ((ctx.get("graph") or {}) if isinstance(ctx.get("graph"), dict) else {})

        malicious_neighbors = [
            n for n in neighbors
            if str(n.get("status") or "").lower() == "malicious"
        ]

        rep_score = int(ctx.get("reputation_score") or 0)
        rep_level = (
            "trusted" if rep_score >= 90 else
            "good" if rep_score >= 70 else
            "neutral" if rep_score >= 45 else
            "bad" if rep_score >= 20 else
            "very_bad"
        )

        out["reputation"] = {
            "available": True,
            "score": rep_score,
            "level": rep_level,
            "entity": ctx.get("entity"),
            "entity_type": ctx.get("entity_type"),
            "basis": ((ctx.get("metadata") or {}).get("reputation") or {}).get("basis"),
            "version": ((ctx.get("metadata") or {}).get("reputation") or {}).get("version"),
            "metadata": ((ctx.get("metadata") or {}).get("reputation") or {}),
        }

        out["graph"] = {
            "available": True,
            "entity": ctx.get("entity"),
            "entity_type": ctx.get("entity_type"),
            "edge_count": graph.get("edge_count", 0),
            "malicious_neighbors": graph.get("malicious_neighbors", 0),
            "max_edge_weight": graph.get("max_edge_weight", 0),
            "max_edge_confidence": graph.get("max_edge_confidence", 0),
            "top_neighbors": neighbors[:10],
        }

        rp = (ctx.get("graph") or {}).get("risk_propagation") or {}
        if not rp:
            # fallback: risk_propagation is stored in entity metadata, not inside graph block
            try:
                rp = (ctx.get("metadata") or {}).get("risk_propagation") or {}
            except Exception:
                rp = {}

        if rp:
            out["graph"]["risk_propagation"] = {
                "available": True,
                "propagated_risk": rp.get("propagated_risk"),
                "malicious_neighbors": rp.get("malicious_neighbors"),
                "version": rp.get("version"),
                "edge_types": rp.get("edge_types") or rp.get("allowed_edge_types") or [],
                "top_paths": (rp.get("top_paths") or [])[:8] if isinstance(rp.get("top_paths") or [], list) else [],
            }

        if campaign:
            meta = campaign.get("metadata") or {}
            metrics = meta.get("campaign_metrics") or {}

            out["campaign"] = {
                "available": True,
                "id": campaign.get("normalized_entity"),
                "brand": meta.get("brand"),
                "type": meta.get("campaign_type"),
                "status": campaign.get("status"),
                "risk_score": campaign.get("risk_score"),
                "confidence": campaign.get("confidence"),
                "domains_count": metrics.get("domains_count"),
                "avg_domain_risk": metrics.get("avg_domain_risk"),
                "max_domain_risk": metrics.get("max_domain_risk"),
                "edge_count": metrics.get("edge_count"),
            }

            ev = {
                "source": "entity_graph",
                "code": "part_of_known_scam_campaign",
                "severity": int(campaign.get("risk_score") or 85),
                "text": f"This entity is linked to a known {meta.get('brand') or ''} impersonation campaign.".strip(),
                "campaign_id": campaign.get("normalized_entity"),
            }
            out.setdefault("evidence", [])
            if not any(e.get("code") == ev["code"] for e in out["evidence"] if isinstance(e, dict)):
                out["evidence"].insert(0, ev)

        elif malicious_neighbors:
            out["campaign"] = out.get("campaign") or {}
            out["graph"]["network_warning"] = {
                "linked_malicious_entities": len(malicious_neighbors),
                "summary": "This entity is connected to malicious entities in Noytrix graph intelligence.",
            }

        # Graph risk must affect visible verdict only when campaign is confirmed.
        campaign_risk = 0
        try:
            campaign_risk = int((out.get("campaign") or {}).get("risk_score") or 0)
        except Exception:
            campaign_risk = 0

        if campaign and campaign_risk >= 85:
            out["score"] = max(int(out.get("score") or 0), campaign_risk)
            out["internal_score"] = max(int(out.get("internal_score") or 0), campaign_risk)
            out["level"] = "critical" if campaign_risk >= 85 else out.get("level")
            out["verdict"] = out.get("level")
            out["graph_risk_applied"] = {
                "applied": True,
                "reason": "confirmed_campaign_membership",
                "campaign_risk": campaign_risk,
            }

        # Wallet/address reputation must affect visible verdict.
        try:
            rep_score = int((out.get("reputation") or {}).get("score") or 50)
            entity_type = str((out.get("reputation") or {}).get("entity_type") or "").lower()
        except Exception:
            rep_score = 50
            entity_type = ""

        if rep_score <= 10 and entity_type in {"evm_address", "wallet", "spender"}:
            out["score"] = max(int(out.get("score") or 0), 85)
            out["internal_score"] = max(int(out.get("internal_score") or 0), 85)
            out["level"] = "danger"
            out["verdict"] = "danger"
            out["reputation_risk_applied"] = {
                "applied": True,
                "reason": "very_bad_wallet_reputation",
                "reputation_score": rep_score,
                "entity_type": entity_type,
            }

            ev = {
                "source": "reputation_engine",
                "code": "very_bad_wallet_reputation",
                "severity": 85,
                "text": "This wallet/address has very bad Noytrix reputation.",
            }
            out.setdefault("evidence", [])
            if not any(e.get("code") == ev["code"] for e in out["evidence"] if isinstance(e, dict)):
                out["evidence"].insert(0, ev)

        out = _apply_reputation_risk_context(out)
        details = out.setdefault("details", {})
        if isinstance(details, dict):
            internal_verdict = details.get("internal_verdict")
            if isinstance(internal_verdict, dict):
                internal_verdict["graph_context"] = out.get("graph") or {}
                internal_verdict["reputation_context"] = out.get("reputation") or {}
                if out.get("campaign"):
                    internal_verdict["campaign_context"] = out.get("campaign") or {}
            details["graph"] = out.get("graph") or {}
            details["reputation"] = out.get("reputation") or {}
        return out

    except Exception as e:
        print("[pg_graph] attach error:", e)
        return out


def _save_scan_to_pg_intelligence(out: dict) -> None:
    if not pg_upsert_entity or not isinstance(out, dict):
        return

    try:
        kind = str(out.get("kind") or "unknown").lower()
        if kind not in {"url", "domain", "wallet", "contract", "evm_address", "spender", "transaction", "text"}:
            return

        entity = str(out.get("normalized_input") or out.get("input") or out.get("host") or "").strip()
        if not entity:
            return

        level = str(out.get("level") or "unknown").lower()
        score = int(out.get("internal_score") or out.get("score") or 0)
        confidence = int(out.get("confidence_score") or out.get("confidence") or 0)

        if level in {"critical", "danger", "high", "malicious", "scam"}:
            status = "malicious"
        elif level in {"safe", "low"} and score <= 20:
            status = "safe"
        elif level in {"medium", "suspicious"}:
            status = "suspicious"
        else:
            status = "observed"

        source_names = [
            str(x.get("name") or x.get("source") or "")
            for x in (out.get("sources") or [])
            if isinstance(x, dict)
        ]

        pg_upsert_entity(
            entity=entity,
            entity_type=kind,
            source_name="noytrix_runtime_scan",
            status=status,
            risk_score=score,
            confidence=confidence,
            evidence=(out.get("evidence") or [])[:20],
            metadata={
                "host": out.get("host"),
                "level": level,
                "internal_score": out.get("internal_score"),
                "external_score": out.get("external_score"),
                "malicious_sources": out.get("malicious_sources") or [],
                "source_names": source_names,
                "scoring": out.get("scoring") or {},
                "cache_verdict": {
                    "kind": out.get("kind"),
                    "level": out.get("level"),
                    "score": out.get("score"),
                    "internal_score": out.get("internal_score"),
                    "external_score": out.get("external_score"),
                    "confidence": out.get("confidence_score") or out.get("confidence"),
                    "malicious_sources": out.get("malicious_sources") or [],
                    "scoring": out.get("scoring") or {},
                    "evidence": (out.get("evidence") or [])[:20],
                    "sources": source_names,
                },
            },
        )
    except Exception as e:
        print("[pg_intelligence] save scan error:", e)


# =========================================================
# SCAN CORE
# =========================================================
async def _scan_url_or_domain(target: str, lang: str, is_pro_user: bool, internal_only: bool = False) -> dict:
    det = _detect_input_kind(target)
    url = det["url"] or _normalize_url(target)
    input_kind = det["kind"]
    host = _extract_host(url)

    cache_mode = "internal" if internal_only else "full"
    cache_key = f"scan:url:v7:{cache_mode}:{_sha256_short(url)}"
    cached = cache_get(cache_key)
    if cached:
        out = dict(cached)
        out["cached"] = True
        out["lang"] = lang
        out["kind_localized"] = _localized_object_kind(input_kind, lang)
        out["sources"] = _localize_sources(out.get("sources") or [], lang)
        out = attach_legacy_fields(out, lang)
        return out

    if False and pg_get_cached_verdict:
        try:
            pg_cached = pg_get_cached_verdict(url if input_kind == "url" else host, max_age_seconds=21600)
        except Exception as e:
            print("[pg_intelligence] cached verdict read error:", e)
            pg_cached = None

        if pg_cached:
            verdict = pg_cached.get("verdict") or {}
            level = str(verdict.get("level") or "unknown").lower()
            score = int(verdict.get("score") or 0)
            out = {
                "ok": True,
                "input": target,
                "normalized_input": pg_cached.get("normalized_entity") or (url if input_kind == "url" else host),
                "kind": input_kind,
                "kind_localized": _localized_object_kind(input_kind, lang),
                "host": host,
                "score": score,
                "internal_score": verdict.get("internal_score"),
                "external_score": verdict.get("external_score"),
                "level": level,
                "normalized_level": level,
                "verdict": level,
                "verdict_en": "Safe" if level == "safe" else "Suspicious" if level == "suspicious" else "Danger" if level == "danger" else "Critical / Scam" if level == "critical" else level.title(),
                "verdict_ru": "Безопасно" if level == "safe" else "Подозрительно" if level == "suspicious" else "Опасно" if level == "danger" else "Критично / Скам" if level == "critical" else level,
                "verdict_localized": level,
                "confirmed_red_flag": level in {"danger", "critical", "high", "malicious"},
                "malicious_sources": verdict.get("malicious_sources") or [],
                "scoring": verdict.get("scoring") or {},
                "sources": [{
                    "name": "noytrix_postgres_intelligence",
                    "source": "noytrix_postgres_intelligence",
                    "status": "cached",
                    "verdict": level,
                    "details": {
                        "age_seconds": pg_cached.get("age_seconds"),
                        "roles": pg_cached.get("roles"),
                        "risk_score": pg_cached.get("risk_score"),
                    },
                    "evidence": [{
                        "code": "postgres_cached_verdict",
                        "severity": score,
                        "text": "Noytrix returned a recent verdict from its own PostgreSQL intelligence database."
                    }],
                    "status_text": "Cached"
                }],
                "evidence": verdict.get("evidence") or [],
                "community": {},
                "details": {"postgres_cached_verdict": pg_cached},
                "lang": lang,
                "cached": True,
                "cache_source": "postgres_intelligence",
            }
            out = attach_legacy_fields(out, lang)
            return out

    sources: list[dict] = []
    det = _detect_input_kind(target)
    chain = det.get("chain")
    heuristics: list[dict] = []
    page_content_evidence: list[dict] = []
    enrich: dict = {"page": None, "token": None, "ticker": None}
    noytrix_db_match = lookup_noytrix_scam_database(url if input_kind == "url" else host)
    sources.append(_source_from_noytrix_scam_database(noytrix_db_match))
    if internal_only and (noytrix_db_match or {}).get("matched") and (noytrix_db_match or {}).get("force_verdict"):
        out = _quick_result_from_noytrix_database(
            target,
            url if input_kind == "url" else host,
            input_kind,
            lang,
            noytrix_db_match,
        )
        cache_set(cache_key, out, 120)
        out["sources"] = _localize_sources(out.get("sources") or [], lang)
        return out

    heuristics.extend(_heuristics_for_host(host))

    domain_age = analyze_domain_age(host)

    infrastructure = analyze_infrastructure(host)
    enrich["infrastructure"] = infrastructure

    if infrastructure.get("available"):
        for sig in (infrastructure.get("signals") or []):
            heuristics.append({
                "code": sig.get("code"),
                "severity": sig.get("severity", 0),
                "text": sig.get("text"),
            })

        infra_level = str(infrastructure.get("level") or "").lower()
        infra_status = (
            "clean" if infra_level == "safe" else
            "warn" if infra_level in {"low", "medium"} else
            "malicious" if infra_level in {"high", "critical"} else
            "observed"
        )

        sources.append(
            _mk_source(
                "infrastructure",
                infra_status,
                verdict=infra_level or "observed",
                details={
                    "host": infrastructure.get("host"),
                    "score": infrastructure.get("score"),
                    "level": infrastructure.get("level"),
                    "a_records": infrastructure.get("a_records"),
                    "aaaa_records": infrastructure.get("aaaa_records"),
                    "ns_records": infrastructure.get("ns_records"),
                    "mx_records": infrastructure.get("mx_records"),
                    "cname_records": infrastructure.get("cname_records"),
                    "known_platform_hints": infrastructure.get("known_platform_hints"),
                    "summary": infrastructure.get("summary"),
                },
                evidence=infrastructure.get("signals") or [{
                    "code": "infrastructure_checked",
                    "severity": 0,
                    "text": "Infrastructure fingerprint checks completed."
                }],
            )
        )
    else:
        sources.append(
            _mk_source(
                "infrastructure",
                "no_data",
                verdict="unknown",
                details={
                    "host": infrastructure.get("host"),
                    "available": infrastructure.get("available"),
                    "reason": infrastructure.get("reason"),
                },
                evidence=[{
                    "code": "infrastructure_unavailable",
                    "severity": 0,
                    "text": "Infrastructure fingerprint could not be inspected."
                }],
            )
        )

    redirect_chain = await analyze_redirect_chain(url)
    enrich["redirect_chain"] = redirect_chain

    if redirect_chain.get("available"):
        for sig in (redirect_chain.get("signals") or []):
            heuristics.append({
                "code": sig.get("code"),
                "severity": sig.get("severity", 0),
                "text": sig.get("text"),
            })

        rc_level = str(redirect_chain.get("level") or "").lower()
        rc_status = (
            "clean" if rc_level == "safe" else
            "warn" if rc_level in {"low", "medium"} else
            "malicious" if rc_level in {"high", "critical"} else
            "observed"
        )
        rc_verdict = rc_level or "observed"
        rc_evidence = redirect_chain.get("signals") or [{
            "code": "redirect_chain_observed",
            "severity": 0,
            "text": "Redirect chain inspected."
        }]
    else:
        rc_status = "no_data"
        rc_verdict = "unknown"
        rc_evidence = [{
            "code": "redirect_chain_unavailable",
            "severity": 0,
            "text": "Redirect chain could not be inspected."
        }]

    sources.append(
        _mk_source(
            "redirect_chain",
            rc_status,
            verdict=rc_verdict,
            details={
                "available": redirect_chain.get("available"),
                "reason": redirect_chain.get("reason"),
                "hop_count": redirect_chain.get("hop_count"),
                "unique_hosts": redirect_chain.get("unique_hosts"),
                "unique_root_domains": redirect_chain.get("unique_root_domains"),
                "final_url": redirect_chain.get("final_url"),
                "final_host": redirect_chain.get("final_host"),
                "hops": redirect_chain.get("hops"),
            },
            evidence=rc_evidence,
        )
    )

    enrich["domain_age"] = domain_age

    if domain_age.get("available"):
        for sig in (domain_age.get("signals") or []):
            heuristics.append({
                "code": sig.get("code"),
                "severity": sig.get("severity", 0),
                "text": sig.get("text"),
            })

        domain_age_level = str(domain_age.get("level") or "").lower()
        domain_age_status = (
            "clean" if domain_age_level == "safe" else
            "warn" if domain_age_level in {"low", "medium"} else
            "malicious" if domain_age_level in {"high", "critical"} else
            "observed"
        )
        domain_age_verdict = domain_age_level or "observed"
        domain_age_evidence = domain_age.get("signals") or []
    else:
        domain_age_status = "no_data"
        domain_age_verdict = "unknown"
        domain_age_evidence = [{
            "code": "domain_age_unavailable",
            "severity": 0,
            "text": "Domain age could not be determined from WHOIS/RDAP data."
        }]

    sources.append(
        _mk_source(
            "domain_age",
            domain_age_status,
            verdict=domain_age_verdict,
            details={
                "host": domain_age.get("host"),
                "available": domain_age.get("available"),
                "reason": domain_age.get("reason"),
                "age_days": domain_age.get("age_days"),
                "created_at": domain_age.get("created_at"),
                "updated_at": domain_age.get("updated_at"),
                "expires_at": domain_age.get("expires_at"),
                "expires_in_days": domain_age.get("expires_in_days"),
                "has_crypto_word": domain_age.get("has_crypto_word"),
            },
            evidence=domain_age_evidence,
        )
    )

    if not internal_only:
        vt_res, gsb_res, us_res = await asyncio.gather(
            _check_virustotal_url(url),
            _check_google_safe_browsing(url),
            _check_urlscan(url),
        )
        sources.extend([vt_res, gsb_res, us_res])
    else:
        sources.append({
            "name": "external_sources",
            "source": "external_sources",
            "status": "skipped",
            "verdict": "internal_only",
            "details": {"reason": "External sources disabled for this scan."},
            "evidence": [{
                "code": "internal_only_mode",
                "severity": 0,
                "text": "External URL reputation sources were skipped."
            }],
            "status_text": "Skipped"
        })

    visible_text = ""
    meta = {}
    js_behavior = {}
    headless_sandbox = {}
    js_obfuscation = {}
    compromised_site = {}
    wallet_trap = {}
    crypto_lure = {}
    visual_phishing = {}
    advanced_url_intel = {}

    page = await _fetch_page(url)
    if page.get("ok"):
        final_url = page.get("final_url") or url
        final_host = _extract_host(final_url)
        meta = _extract_page_meta(page.get("html") or "")
        visible_text = _extract_visible_text_from_html(page.get("html") or "")
        content_analysis = _analyze_text_content(visible_text)
        page_content_evidence.extend(content_analysis["evidence"])

        wallet_trap = analyze_wallet_trap(page.get("html") or "", visible_text)
        enrich["wallet_trap"] = wallet_trap

        crypto_lure = analyze_crypto_lure(visible_text, page.get("html") or "", final_host or host)
        enrich["crypto_lure"] = crypto_lure

        js_behavior = analyze_js_behavior(page.get("html") or "")
        enrich["js_behavior"] = js_behavior

        headless_sandbox = await analyze_headless_sandbox(final_url or url)
        enrich["headless_sandbox"] = headless_sandbox

        js_obfuscation = analyze_obfuscated_javascript(page.get("html") or "", headless_sandbox)
        enrich["js_obfuscation"] = js_obfuscation

        visual_phishing = analyze_visual_phishing(
            page.get("html") or "",
            visible_text,
            final_host or host,
            str((meta or {}).get("title") or ""),
        )
        enrich["visual_phishing"] = visual_phishing

        compromised_site = analyze_compromised_legitimate_site(
            final_url or url,
            final_host or host,
            domain_age=domain_age,
            redirect_chain=redirect_chain,
            wallet_trap=wallet_trap,
            crypto_lure=crypto_lure,
            js_behavior=js_behavior,
            headless_sandbox=headless_sandbox,
            js_obfuscation=js_obfuscation,
            visual_phishing=visual_phishing,
        )
        enrich["compromised_site"] = compromised_site

        if visual_phishing.get("available"):
            for sig in (visual_phishing.get("signals") or []):
                heuristics.append({
                    "code": sig.get("code"),
                    "severity": sig.get("severity", 0),
                    "text": sig.get("text"),
                })

            vp_level = str(visual_phishing.get("level") or "").lower()
            vp_status = (
                "clean" if vp_level == "safe" else
                "warn" if vp_level in {"low", "medium"} else
                "malicious" if vp_level in {"high", "critical"} else
                "observed"
            )

            sources.append(
                _mk_source(
                    "visual_phishing",
                    vp_status,
                    verdict=vp_level or "observed",
                    details={
                        "score": visual_phishing.get("score"),
                        "level": visual_phishing.get("level"),
                        "summary": visual_phishing.get("summary"),
                    },
                    evidence=visual_phishing.get("signals") or [{
                        "code": "visual_phishing_checked",
                        "severity": 0,
                        "text": "Visual/copy phishing checks completed."
                    }],
                )
            )

        advanced_url_intel = analyze_advanced_url_intel(
            final_url,
            final_host or host,
            page.get("html") or "",
            visible_text,
            str((meta or {}).get("title") or ""),
            infrastructure=infrastructure,
            redirect_chain=redirect_chain,
            wallet_trap=wallet_trap,
            crypto_lure=crypto_lure,
            js_behavior=js_behavior,
            visual_phishing=visual_phishing,
        )
        enrich["advanced_url_intel"] = advanced_url_intel

        if advanced_url_intel.get("available"):
            for sig in (advanced_url_intel.get("signals") or []):
                heuristics.append({
                    "code": sig.get("code"),
                    "severity": sig.get("severity", 0),
                    "text": sig.get("text"),
                })

            adv_level = str(advanced_url_intel.get("level") or "").lower()
            adv_status = (
                "clean" if adv_level == "safe" else
                "warn" if adv_level in {"low", "medium"} else
                "malicious" if adv_level in {"high", "critical"} else
                "observed"
            )

            sources.append(
                _mk_source(
                    "advanced_url_intel",
                    adv_status,
                    verdict=adv_level or "observed",
                    details={
                        "score": advanced_url_intel.get("score"),
                        "level": advanced_url_intel.get("level"),
                        "summary": advanced_url_intel.get("summary"),
                        "fingerprints": advanced_url_intel.get("fingerprints"),
                        "related_domains": advanced_url_intel.get("related_domains"),
                    },
                    evidence=advanced_url_intel.get("signals") or [{
                        "code": "advanced_url_intel_checked",
                        "severity": 0,
                        "text": "Advanced URL intelligence checks completed."
                    }],
                )
            )

        if js_behavior.get("available"):
            for sig in (js_behavior.get("signals") or []):
                heuristics.append({
                    "code": sig.get("code"),
                    "severity": sig.get("severity", 0),
                    "text": sig.get("text"),
                })

            js_level = str(js_behavior.get("level") or "").lower()
            js_status = (
                "clean" if js_level == "safe" else
                "warn" if js_level in {"low", "medium"} else
                "malicious" if js_level in {"high", "critical"} else
                "observed"
            )

            sources.append(
                _mk_source(
                    "js_behavior",
                    js_status,
                    verdict=js_level or "observed",
                    details={
                        "score": js_behavior.get("score"),
                        "level": js_behavior.get("level"),
                        "summary": js_behavior.get("summary"),
                    },
                    evidence=js_behavior.get("signals") or [{
                        "code": "js_behavior_checked",
                        "severity": 0,
                        "text": "JavaScript wallet behavior checks completed."
                    }],
                )
            )

        if headless_sandbox.get("available"):
            for sig in (headless_sandbox.get("signals") or []):
                heuristics.append({
                    "code": sig.get("code"),
                    "severity": sig.get("severity", 0),
                    "text": sig.get("text"),
                })

            sandbox_level = str(headless_sandbox.get("level") or "").lower()
            sandbox_status = (
                "clean" if sandbox_level == "safe" else
                "warn" if sandbox_level in {"low", "medium"} else
                "malicious" if sandbox_level in {"high", "critical"} else
                "observed"
            )

            sources.append(
                _mk_source(
                    "headless_sandbox",
                    sandbox_status,
                    verdict=sandbox_level or "observed",
                    details={
                        "score": headless_sandbox.get("score"),
                        "level": headless_sandbox.get("level"),
                        "summary": headless_sandbox.get("summary"),
                        "final_url": headless_sandbox.get("final_url"),
                        "wallet_calls": headless_sandbox.get("wallet_calls") or [],
                        "script_urls": headless_sandbox.get("script_urls") or [],
                        "page_errors": headless_sandbox.get("page_errors") or [],
                    },
                    evidence=headless_sandbox.get("signals") or [{
                        "code": "headless_sandbox_checked",
                        "severity": 0,
                        "text": "Headless browser sandbox completed."
                    }],
                )
            )
        elif headless_sandbox:
            sources.append(
                _mk_source(
                    "headless_sandbox",
                    "no_data",
                    verdict="unavailable",
                    details={
                        "available": False,
                        "reason": headless_sandbox.get("reason"),
                        "error": headless_sandbox.get("error"),
                    },
                    evidence=[{
                        "code": "headless_sandbox_unavailable",
                        "severity": 0,
                        "text": "Headless browser sandbox was unavailable for this scan."
                    }],
                )
            )

        if js_obfuscation.get("available"):
            for sig in (js_obfuscation.get("signals") or []):
                heuristics.append({
                    "code": sig.get("code"),
                    "severity": sig.get("severity", 0),
                    "text": sig.get("text"),
                })

            obf_level = str(js_obfuscation.get("level") or "").lower()
            obf_status = (
                "clean" if obf_level == "safe" else
                "warn" if obf_level in {"low", "medium"} else
                "malicious" if obf_level in {"high", "critical"} else
                "observed"
            )

            sources.append(
                _mk_source(
                    "js_obfuscation",
                    obf_status,
                    verdict=obf_level or "observed",
                    details={
                        "score": js_obfuscation.get("score"),
                        "level": js_obfuscation.get("level"),
                        "summary": js_obfuscation.get("summary"),
                        "metrics": js_obfuscation.get("metrics") or {},
                    },
                    evidence=js_obfuscation.get("signals") or [{
                        "code": "js_obfuscation_checked",
                        "severity": 0,
                        "text": "JavaScript obfuscation checks completed."
                    }],
                )
            )

        if compromised_site.get("available"):
            for sig in (compromised_site.get("signals") or []):
                heuristics.append({
                    "code": sig.get("code"),
                    "severity": sig.get("severity", 0),
                    "text": sig.get("text"),
                })

            comp_level = str(compromised_site.get("level") or "").lower()
            comp_status = (
                "clean" if comp_level == "safe" else
                "warn" if comp_level in {"low", "medium"} else
                "malicious" if comp_level in {"high", "critical"} else
                "observed"
            )

            sources.append(
                _mk_source(
                    "compromised_site",
                    comp_status,
                    verdict=comp_level or "observed",
                    details={
                        "score": compromised_site.get("score"),
                        "level": compromised_site.get("level"),
                        "summary": compromised_site.get("summary"),
                        "known_legitimate_context": compromised_site.get("known_legitimate_context"),
                        "old_domain": compromised_site.get("old_domain"),
                        "platform_root": compromised_site.get("platform_root"),
                        "suspicious_path_words": compromised_site.get("suspicious_path_words") or [],
                    },
                    evidence=compromised_site.get("signals") or [{
                        "code": "compromised_site_checked",
                        "severity": 0,
                        "text": "Compromised legitimate site checks completed."
                    }],
                )
            )

        if crypto_lure.get("available"):
            for sig in (crypto_lure.get("signals") or []):
                heuristics.append({
                    "code": sig.get("code"),
                    "severity": sig.get("severity", 0),
                    "text": sig.get("text"),
                })

            cl_level = str(crypto_lure.get("level") or "").lower()
            cl_status = (
                "clean" if cl_level == "safe" else
                "warn" if cl_level in {"low", "medium"} else
                "malicious" if cl_level in {"high", "critical"} else
                "observed"
            )

            sources.append(
                _mk_source(
                    "crypto_lure",
                    cl_status,
                    verdict=cl_level or "observed",
                    details={
                        "score": crypto_lure.get("score"),
                        "level": crypto_lure.get("level"),
                        "summary": crypto_lure.get("summary"),
                    },
                    evidence=crypto_lure.get("signals") or [{
                        "code": "crypto_lure_checked",
                        "severity": 0,
                        "text": "Crypto lure checks completed."
                    }],
                )
            )

        if wallet_trap.get("available"):
            for sig in (wallet_trap.get("signals") or []):
                heuristics.append({
                    "code": sig.get("code"),
                    "severity": sig.get("severity", 0),
                    "text": sig.get("text"),
                })

            wt_level = str(wallet_trap.get("level") or "").lower()
            wt_status = (
                "clean" if wt_level == "safe" else
                "warn" if wt_level in {"low", "medium"} else
                "malicious" if wt_level in {"high", "critical"} else
                "observed"
            )

            sources.append(
                _mk_source(
                    "wallet_trap",
                    wt_status,
                    verdict=wt_level or "observed",
                    details={
                        "score": wallet_trap.get("score"),
                        "level": wallet_trap.get("level"),
                        "summary": wallet_trap.get("summary"),
                    },
                    evidence=wallet_trap.get("signals") or [{
                        "code": "wallet_trap_checked",
                        "severity": 0,
                        "text": "Wallet trap checks completed."
                    }],
                )
            )

        enrich["page"] = {
            "final_url": final_url,
            "final_host": final_host,
            "status_code": page.get("status_code"),
            "content_type": page.get("content_type"),
            "meta": meta,
        }

        if final_host and host and final_host != host:
            if not _same_effective_site(host, final_host):
                heuristics.append(
                    {
                        "code": "redirect_to_different_host",
                        "severity": 12,
                        "text": f"Redirected from {host} to {final_host}.",
                    }
                )

        spoof_hit, spoof_ev = _looks_like_brand_spoof(final_host or host)
        if spoof_hit:
            heuristics.extend(spoof_ev)

        if meta.get("password_inputs", 0) > 0 and RE_SEED_WORDS.search(visible_text or ""):
            heuristics.append(
                {
                    "code": "credential_or_wallet_prompt",
                    "severity": 24,
                    "text": "Page asks for credentials/seed/private info in a wallet-related context.",
                }
            )

        if meta.get("iframes", 0) >= 3:
            heuristics.append(
                {
                    "code": "multiple_iframes",
                    "severity": 6,
                    "text": "Page uses multiple iframes, which may increase spoofing risk.",
                }
            )

        sources.append(
            _mk_source(
                "page_fetch",
                "clean",
                verdict="observed",
                details=enrich["page"],
                evidence=[{"code": "page_loaded", "severity": 0, "text": "Page fetched successfully for content inspection."}],
            )
        )
    else:
        status = page.get("status") or "error"
        err = str(page.get("error") or "")

        if "name or service not known" in err.lower() or "nodename nor servname provided" in err.lower():
            heuristics.append(
                {
                    "code": "domain_resolution_failed",
                    "severity": 18,
                    "text": "Domain could not be resolved.",
                }
            )

        sources.append(_mk_source("page_fetch", "timeout" if status == "timeout" else "error", details={"error": err}))

        spoof_hit, spoof_ev = _looks_like_brand_spoof(host)
        if spoof_hit:
            heuristics.extend(spoof_ev)

    # Production anti-false-positive layer:
    # If a page is clearly a security / anti-scam / protection product,
    # generic wallet/claim/support words must not become a scam verdict by themselves.
    try:
        _text_for_antifp = " ".join([
            str(((enrich.get("page") or {}).get("meta") or {}).get("title") or ""),
            str(visible_text or ""),
            str(host or ""),
        ]).lower()

        _security_context_hits = sum(1 for w in [
            "security", "protect", "protection", "shield", "scan", "scanner",
            "detect", "detection", "anti-scam", "antiscam", "scam detection",
            "phishing", "threat intelligence", "risk analysis", "wallet monitoring",
            "transaction analysis", "security intelligence", "safe browsing",
            "runtime analysis", "fraud protection", "malware", "reputation"
        ] if w in _text_for_antifp)

        _commercial_scam_action_hits = sum(1 for w in [
            "claim now", "claim reward", "claim airdrop", "connect wallet to claim",
            "connect wallet to receive", "verify wallet to withdraw", "deposit bonus",
            "send usdt", "send eth", "limited reward", "unlock reward"
        ] if w in _text_for_antifp)

        _has_real_secret_or_login_risk = bool(
            int((meta or {}).get("password_inputs") or 0) > 0
            or "seed phrase" in _text_for_antifp
            or "private key" in _text_for_antifp
            or "recovery phrase" in _text_for_antifp
        )

        _js_risky = str((js_behavior or {}).get("level") or "").lower() in {"high", "critical"}

        _defensive_security_context = (
            _security_context_hits >= 3
            and _commercial_scam_action_hits == 0
            and not _has_real_secret_or_login_risk
            and not _js_risky
        )

        if _defensive_security_context:
            _suppressed_codes = {
                "fake_support_ui",
                "fake_airdrop_bonus_ui",
                "wallet_connect_pressure",
                "wallet_verification_lure",
                "signature_or_approval_wording",
                "cloned_ui_fingerprint",
                "visual_phishing_score",
                "crypto_lure_score",
                "wallet_trap_score",
            }

            heuristics = [
                h for h in (heuristics or [])
                if str(h.get("code") or "") not in _suppressed_codes
            ]

            page_content_evidence = [
                e for e in (page_content_evidence or [])
                if str(e.get("code") or "") not in _suppressed_codes
            ]

            for src in sources:
                if str(src.get("name") or "") in {"visual_phishing", "crypto_lure", "wallet_trap"}:
                    ev = src.get("evidence") or []
                    if ev and all(str(x.get("code") or "") in _suppressed_codes for x in ev):
                        src["status"] = "clean"
                        src["verdict"] = "safe"
                        src["details"] = {
                            **(src.get("details") or {}),
                            "suppressed_by": "security_product_context_antifp",
                            "reason": "Security/anti-scam product context; generic wallet wording is informational, not a scam flow."
                        }
                        src["evidence"] = [{
                            "code": "security_product_context_antifp",
                            "severity": 0,
                            "text": "Generic wallet/security wording suppressed because page context is defensive security product."
                        }]

            enrich["anti_false_positive"] = {
                "security_context": True,
                "security_context_hits": _security_context_hits,
                "suppressed_generic_wallet_copywriting": True,
            }
    except Exception as e:
        print("[anti_fp] security context filter error:", e)

    # Production anti-false-positive:
    # Official Web3 apps naturally include WalletConnect/Web3Modal and wallet connection scripts.
    # On verified official brand roots/subdomains, these low-level wallet references are expected behavior.
    try:
        _official_web3_roots = {
            "uniswap.org",
            "pancakeswap.finance",
            "opensea.io",
            "blur.io",
            "aave.com",
            "curve.fi",
            "lido.fi",
            "jup.ag",
            "raydium.io",
            "1inch.io",
            "compound.finance",
            "balancer.fi",
            "tonscan.org",
        }

        _host_l = (host or "").lower().strip(".")
        _is_official_web3_app = any(_host_l == d or _host_l.endswith("." + d) for d in _official_web3_roots)

        if _is_official_web3_app:
            _expected_web3_codes = {
                "wallet_connect_request",
                "web3_script_reference",
                "connect_wallet_reward_flow",
                "fake_airdrop_bonus_ui",
                "wallet_connect_pressure",
                "cloned_ui_fingerprint",
                "visual_phishing_score",
                "js_dynamic_eval_execution",
                "js_dynamic_script_loading",
                "js_high_entropy_payload",
                "js_minified_or_packed_long_lines",
                "js_obfuscation_score",
            }

            heuristics = [
                h for h in (heuristics or [])
                if str(h.get("code") or "") not in _expected_web3_codes
            ]

            page_content_evidence = [
                e for e in (page_content_evidence or [])
                if str(e.get("code") or "") not in _expected_web3_codes
            ]

            for src in sources:
                if str(src.get("name") or "") in {"js_behavior", "wallet_trap", "visual_phishing", "js_obfuscation"}:
                    ev = src.get("evidence") or []
                    if ev and all(str(x.get("code") or "") in _expected_web3_codes for x in ev):
                        src["status"] = "clean"
                        src["verdict"] = "safe"
                        src["details"] = {
                            **(src.get("details") or {}),
                            "score": 0,
                            "level": "safe",
                            "suppressed_by": "official_web3_app_expected_wallet_behavior",
                            "reason": "Official Web3 application; wallet connection libraries are expected behavior."
                        }
                        src["evidence"] = [{
                            "code": "official_web3_app_expected_wallet_behavior",
                            "severity": 0,
                            "text": "Wallet connection references suppressed because this is an official Web3 application domain."
                        }]
    except Exception as e:
        print("[anti_fp] official web3 app filter error:", e)

    # Production anti-false-positive:
    # Official Web3 app domains must not be raised by stale memory or low infra warnings.
    try:
        _official_web3_roots_2 = {
            "uniswap.org",
            "pancakeswap.finance",
            "opensea.io",
            "blur.io",
            "aave.com",
            "curve.fi",
            "lido.fi",
            "jup.ag",
            "raydium.io",
            "1inch.io",
            "compound.finance",
            "balancer.fi",
            "tonscan.org",
        }

        _host_l2 = (host or "").lower().strip(".")
        _is_official_web3_app_2 = any(_host_l2 == d or _host_l2.endswith("." + d) for d in _official_web3_roots_2)

        if _is_official_web3_app_2:
            _official_low_noise_codes = {
                "missing_ns_records",
                "infrastructure_score",
                "historical_threat_memory",
            }

            heuristics = [
                h for h in (heuristics or [])
                if str(h.get("code") or "") not in _official_low_noise_codes
            ]

            page_content_evidence = [
                e for e in (page_content_evidence or [])
                if str(e.get("code") or "") not in _official_low_noise_codes
            ]

            for src in sources:
                if str(src.get("name") or "") in {"infrastructure"}:
                    ev = src.get("evidence") or []
                    if ev and all(str(x.get("code") or "") in _official_low_noise_codes for x in ev):
                        src["status"] = "clean"
                        src["verdict"] = "safe"
                        src["details"] = {
                            **(src.get("details") or {}),
                            "score": 0,
                            "level": "safe",
                            "suppressed_by": "official_web3_app_low_infra_noise",
                            "reason": "Official Web3 application; low infrastructure noise suppressed."
                        }
                        src["evidence"] = [{
                            "code": "official_web3_app_low_infra_noise",
                            "severity": 0,
                            "text": "Low infrastructure warning suppressed on official Web3 application domain."
                        }]
    except Exception as e:
        print("[anti_fp] official web3 memory/infra filter error:", e)

    pre_memory = get_entity_memory(url if input_kind == "url" else host, input_kind) or {}

    url_intelligence = build_url_intelligence(
        sources,
        heuristics,
        page_content_evidence,
        pre_memory,
    )
    enrich["noytrix_url_intelligence"] = url_intelligence

    sources.append(
        _mk_source(
            "noytrix_url_intelligence",
            "clean" if url_intelligence.get("level") in {"safe", "low"} else "warn" if url_intelligence.get("level") == "medium" else "malicious",
            verdict=url_intelligence.get("level"),
            details={
                "score": url_intelligence.get("score"),
                "level": url_intelligence.get("level"),
                "confidence": url_intelligence.get("confidence"),
                "confirmed_internal_red_flag": url_intelligence.get("confirmed_internal_red_flag"),
                "signals_count": url_intelligence.get("signals_count"),
                "internal_sources": url_intelligence.get("internal_sources"),
                "summary": url_intelligence.get("summary"),
            },
            evidence=url_intelligence.get("top_signals") or [{
                "code": "noytrix_url_intelligence_checked",
                "severity": 0,
                "text": "Noytrix internal URL intelligence checks completed."
            }],
        )
    )

    community = _community_snapshot(url if input_kind == "url" else host, input_kind)
    score_info = _score_scan(
        sources=sources,
        heuristics=heuristics,
        page_content=page_content_evidence,
        community=community,
        internal_only=internal_only,
    )

    internal_url_score = int((url_intelligence or {}).get("score") or 0)
    internal_top_signals = (url_intelligence or {}).get("top_signals") or []
    internal_signal_sources = {
        str(x.get("source") or "").lower()
        for x in internal_top_signals
        if int(x.get("severity") or 0) > 0
    }

    only_memory_signal = internal_signal_sources == {"threat_memory"}

    if only_memory_signal and internal_url_score > 0:
        internal_url_score = min(internal_url_score, 85)

    if internal_url_score > int(score_info.get("score") or 0):
        score_info["score"] = internal_url_score
        score_info["internal_score"] = max(
            int(score_info.get("internal_score") or 0),
            internal_url_score,
        )
        score_info["level"] = url_intelligence.get("level") or score_info.get("level")
        score_info["internal_level"] = url_intelligence.get("level") or score_info.get("internal_level")
        score_info["confidence_score"] = max(
            int(score_info.get("confidence_score") or 0),
            int(url_intelligence.get("confidence") or 0),
        )

    score_info["internal_url_score"] = internal_url_score
    score_info["internal_url_only_memory_signal"] = only_memory_signal

    if (
        not heuristics
        and not page_content_evidence
        and not score_info.get("confirmed_red_flag")
        and not score_info.get("malicious_sources")
        and str((community or {}).get("community_verdict") or "").lower() != "scam"
        and all(str((src or {}).get("status") or "") in {"no_data", "error", "timeout", "invalid_key", "quota"} for src in (sources or []))
    ):
        score_info["score"] = 0
        score_info["level"] = "safe"
        score_info["verdict_en"] = "Safe"
        score_info["verdict_ru"] = "Безопасно"

    evidence_all = []
    evidence_all.extend([{"source": "heuristic", **x} for x in heuristics])
    evidence_all.extend([{"source": "page_content", **x} for x in page_content_evidence])
    for s in sources:
        for ev in s.get("evidence") or []:
            evidence_all.append({"source": s.get("name"), **ev})

    evidence_all_sorted = sorted(evidence_all, key=lambda x: int(x.get("severity") or 0), reverse=True)[:30]
    evidence_trace = _build_url_evidence_trace(sources, heuristics, page_content_evidence)
    score_before_safety_gate = {
        "score": score_info.get("score"),
        "level": score_info.get("level"),
        "internal_score": score_info.get("internal_score"),
        "external_score": score_info.get("external_score"),
        "components": score_info.get("components") or {},
    }
    score_info = _apply_false_positive_safety_gate_to_url_score(score_info, evidence_trace)
    score_info = _apply_noytrix_database_verdict(score_info, noytrix_db_match)
    safety_gate = score_info.get("false_positive_safety_gate") or {}
    reputation_context = (score_info.get("noytrix_scam_database") or {}).get("source_reputation") or (noytrix_db_match or {}).get("source_reputation") or {}
    internal_verdict = build_internal_verdict(
        kind=input_kind,
        target=url if input_kind == "url" else host,
        score_info=score_info,
        sources=sources,
        evidence_trace=evidence_trace,
        community=community,
        noytrix_database=score_info.get("noytrix_scam_database") or {
            "applied": False,
            "match": noytrix_db_match,
        },
        reputation_context=reputation_context,
    )
    scam_family = internal_verdict.get("scam_family") or classify_scam_family({
        "kind": input_kind,
        "input": target,
        "normalized_input": url if input_kind == "url" else host,
        "host": host,
        "evidence": evidence_all_sorted,
        "sources": sources,
        "details": {"evidence_trace": evidence_trace.get("items") or []},
    }, evidence_trace)

    out = {
        "ok": True,
        "input": target,
        "normalized_input": url if input_kind == "url" else host,
        "kind": input_kind,
        "kind_localized": _localized_object_kind(input_kind, lang),
        "host": host,
        "score": score_info["score"],
        "internal_score": score_info.get("internal_score"),
        "external_score": score_info.get("external_score"),
        "internal_level": score_info.get("internal_level"),
        "external_level": score_info.get("external_level"),
        "internal_red_flag": score_info.get("internal_red_flag"),
        "external_red_flag": score_info.get("external_red_flag"),
        "internal_only": score_info.get("internal_only"),
        "level": score_info["level"],
        "normalized_level": score_info.get("normalized_level", score_info["level"]),
        "verdict_en": score_info["verdict_en"],
        "verdict_ru": score_info["verdict_ru"],
        "verdict_localized": score_info["verdict_ru"] if lang == "ru" else score_info["verdict_en"],
        "confirmed_red_flag": score_info["confirmed_red_flag"],
        "risk_family": internal_verdict.get("risk_family"),
        "scam_family": scam_family,
        "malicious_sources": score_info["malicious_sources"],
        "scoring": score_info["components"],
        "sources": sources,
        "evidence": evidence_all_sorted,
        "community": community,
        "details": {
            "page": enrich.get("page"),
            "input_kind": input_kind,
            "noytrix_scam_database": score_info.get("noytrix_scam_database") or {
                "applied": False,
                "match": noytrix_db_match,
            },
            "source_reputation": reputation_context,
            "evidence_trace": evidence_trace.get("items") or [],
            "score_trace": {
                "before_safety_gate": score_before_safety_gate,
                "after_safety_gate": {
                    "score": score_info.get("score"),
                    "level": score_info.get("level"),
                    "internal_score": score_info.get("internal_score"),
                    "external_score": score_info.get("external_score"),
                },
                "components": score_info.get("components") or {},
                "internal_url_score": score_info.get("internal_url_score"),
                "internal_url_only_memory_signal": score_info.get("internal_url_only_memory_signal"),
            },
            "top_score_contributors": evidence_trace.get("top_contributors") or [],
            "hard_evidence_found": evidence_trace.get("hard_evidence_found"),
            "hard_evidence_codes": evidence_trace.get("hard_evidence_codes") or [],
            "generic_noise_codes": evidence_trace.get("generic_noise_codes") or [],
            "false_positive_safety_gate": safety_gate,
            "internal_verdict": internal_verdict,
            "scam_family": scam_family,
        },
        "lang": lang,
        "cached": False,
    }

    out = _attach_pg_graph_context(out)
    out = _attach_ai_investigation_fields(out)

    _save_scan_to_pg_intelligence(out)

    cache_set(cache_key, out, 120)
    out["sources"] = _localize_sources(out["sources"], lang)
    out = attach_legacy_fields(out, lang)
    return out

async def _scan_wallet_or_contract(target: str, lang: str) -> dict:
    addr_lower = target.strip().lower()
    if addr_lower in KNOWN_SAFE_ADDRESSES:
        label = KNOWN_SAFE_ADDRESSES[addr_lower]
        return {
            "ok": True, "input": target, "normalized_input": target,
            "kind": "wallet", "kind_localized": _localized_object_kind("wallet", lang),
            "score": 0, "level": "safe",
            "verdict_en": "This is a known safe address.", "verdict_ru": "Это известный безопасный адрес.",
            "verdict_localized": "This is a known safe address.",
            "confirmed_red_flag": False, "malicious_sources": 0,
            "sources": [_mk_source("allowlist", "clean", verdict="clean", details={"label": label})],
            "heuristics": [], "evidence": [], "community": _community_snapshot(target, "wallet"),
            "details": {"label": label}, "lang": lang, "cached": False,
            "what_can_happen": f"This address is recognized as {label.replace('_',' ')} — a known safe address.",
            "worst_case": "No risk detected.",
        }

    address = (target or "").strip()
    cache_key = f"scan:evm:v4:{address.lower()}"

    cached = cache_get(cache_key)
    if cached:
        out = dict(cached)
        out["cached"] = True
        out["lang"] = lang
        out["kind_localized"] = _localized_object_kind(out.get("kind") or "wallet", lang)
        out["sources"] = _localize_sources(out.get("sources") or [], lang)
        out = attach_legacy_fields(out, lang)
        return out

    if False and pg_get_cached_verdict:
        try:
            pg_cached = pg_get_cached_verdict(address, max_age_seconds=21600)
        except Exception as e:
            print("[pg_intelligence] wallet cached verdict read error:", e)
            pg_cached = None

        if pg_cached:
            verdict = pg_cached.get("verdict") or {}
            level = str(verdict.get("level") or "unknown").lower()
            score = int(verdict.get("score") or pg_cached.get("risk_score") or 0)
            kind_cached = str(verdict.get("kind") or pg_cached.get("entity_type") or "wallet").lower()
            out = {
                "ok": True,
                "input": target,
                "normalized_input": pg_cached.get("normalized_entity") or address,
                "kind": kind_cached,
                "chain": None,
                "kind_localized": _localized_object_kind(kind_cached, lang),
                "score": score,
                "internal_score": verdict.get("internal_score") or score,
                "external_score": verdict.get("external_score") or 0,
                "level": level,
                "normalized_level": level,
                "verdict": level,
                "verdict_en": "Safe" if level == "safe" else "Suspicious" if level == "suspicious" else "Danger" if level == "danger" else "Critical / Scam" if level == "critical" else level.title(),
                "verdict_ru": "Безопасно" if level == "safe" else "Подозрительно" if level == "suspicious" else "Опасно" if level == "danger" else "Критично / Скам" if level == "critical" else level,
                "verdict_localized": level,
                "confirmed_red_flag": level in {"danger", "critical", "high", "malicious"},
                "malicious_sources": verdict.get("malicious_sources") or [],
                "scoring": verdict.get("scoring") or {},
                "sources": [{
                    "name": "noytrix_postgres_intelligence",
                    "source": "noytrix_postgres_intelligence",
                    "status": "cached",
                    "verdict": level,
                    "details": {
                        "age_seconds": pg_cached.get("age_seconds"),
                        "roles": pg_cached.get("roles"),
                        "risk_score": pg_cached.get("risk_score"),
                    },
                    "evidence": [{
                        "code": "postgres_cached_wallet_verdict",
                        "severity": score,
                        "text": "Noytrix returned a recent wallet/contract verdict from its own PostgreSQL intelligence database."
                    }],
                    "status_text": "Cached"
                }],
                "evidence": verdict.get("evidence") or [],
                "community": {},
                "details": {"postgres_cached_verdict": pg_cached},
                "lang": lang,
                "cached": True,
                "cache_source": "postgres_intelligence",
            }
            out = attach_legacy_fields(out, lang)
            return out

    sources: list[dict] = []
    det = _detect_input_kind(target)
    chain = det.get("chain")
    heuristics: list[dict] = []
    page_content_evidence: list[dict] = []
    noytrix_db_match = lookup_noytrix_scam_database(address)
    sources.append(_source_from_noytrix_scam_database(noytrix_db_match))
    if (noytrix_db_match or {}).get("matched") and (noytrix_db_match or {}).get("force_verdict"):
        out = _quick_result_from_noytrix_database(
            target,
            address,
            "wallet",
            lang,
            noytrix_db_match,
        )
        cache_set(cache_key, out, 180)
        out["sources"] = _localize_sources(out.get("sources") or [], lang)
        return out

    is_evm = bool(RE_EVM_ADDR.match(address))
    if is_evm:
        eth_res, bsc_res, dex_res = await asyncio.gather(
            _check_etherscan_or_bscscan(address, "eth"),
            _check_etherscan_or_bscscan(address, "bsc"),
            _check_dexscreener_address(address),
        )
        sources.extend([eth_res, bsc_res, dex_res])
    elif chain == "tron":
        sources.append(await _check_tronscan(address))
    elif chain == "btc":
        sources.append(await _check_btc(address))
    elif chain == "ton":
        sources.append(await _check_ton(address))
    elif chain == "sol":
        sol_res, dex_res = await asyncio.gather(
            _check_solana(address),
            _check_dexscreener_address(address),
        )
        sources.extend([sol_res, dex_res])

        if str(sol_res.get("status") or "") in {"no_data", "error"} and str(dex_res.get("status") or "") == "clean":
            heuristics.append(
                {
                    "code": "sol_dex_only_presence",
                    "severity": 0,
                    "text": "Solana token was identified via DexScreener fallback.",
                }
            )
    else:
        dex_res = await _check_dexscreener_address(address)
        sources.append(dex_res)

    kind = "wallet"
    token_data = None
    verified_contract_any = False
    preferred_chain_id = None

    for s in sources:
        d = s.get("details") or {}
        if d.get("verified_contract"):
            verified_contract_any = True
            kind = "contract"
            if s.get("name") == "etherscan":
                preferred_chain_id = "1"
            elif s.get("name") == "bscscan":
                preferred_chain_id = "56"

        if s.get("name") == "dexscreener" and s.get("status") == "clean":
            token_data = d
            kind = "contract"
            chain_id = str(d.get("chainId") or "").strip().lower()
            if chain_id == "ethereum":
                preferred_chain_id = "1"
            elif chain_id == "bsc":
                preferred_chain_id = "56"
            elif chain_id == "base":
                preferred_chain_id = "8453"
            elif chain_id == "arbitrum":
                preferred_chain_id = "42161"

    if is_evm:
        honeypot_res = await _check_honeypot_contract(address, preferred_chain_id)
        sources.append(honeypot_res)
    else:
        honeypot_res = {
            "name": "honeypot",
            "status": "no_data",
            "verdict": "unknown",
            "details": {"skipped": True, "reason": "non_evm_address"},
            "evidence": [],
        }

    if is_evm and verified_contract_any is False and token_data is None:
        heuristics.append(
            {
                "code": "unverified_address",
                "severity": 5,
                "text": "Address was not confirmed as a verified contract by explorers.",
            }
        )

    
    contract_identity = None
    if is_evm and kind == "contract":
        try:
            contract_identity = await _check_spender_reputation(address)
            if contract_identity:
                trust = contract_identity.get("trust")
                sources.append({
                    "name": "noytrix_identity",
                    "status": "clean" if trust == "trusted" else ("malicious" if trust == "malicious" else "suspicious"),
                    "verdict": "clean" if trust == "trusted" else ("malicious" if trust == "malicious" else "unknown"),
                    "details": {
                        "label": contract_identity.get("label"),
                        "category": contract_identity.get("category"),
                        "trust": contract_identity.get("trust"),
                        "risk": contract_identity.get("risk"),
                        "reasons": contract_identity.get("reasons") or [],
                        "address": contract_identity.get("address") or address,
                    },
                    "evidence": [{
                        "code": "contract_identity",
                        "severity": 0 if trust == "trusted" else (90 if trust == "malicious" else 15),
                        "text": "Noytrix identity: %s · %s." % (contract_identity.get("label") or "Unknown contract", trust or "unknown")
                    }],
                })
                if trust == "malicious":
                    heuristics.append({
                        "code": "known_malicious_contract_identity",
                        "severity": 95,
                        "text": "Noytrix identity database marks this contract/spender as malicious.",
                    })
        except Exception:
            contract_identity = None

    if not sources:
        heuristics.append({
            "code": "no_blockchain_data",
            "severity": 15,
            "text": "No blockchain data found"
        })

    is_ru = lang == "ru"
    is_uk = lang == "uk"

    community = _community_snapshot(address, kind)
    score_info = _score_scan(
        sources=sources,
        heuristics=heuristics,
        page_content=page_content_evidence,
        community=community,
    )
    score_info = _apply_noytrix_database_verdict(score_info, noytrix_db_match)

    if chain == "ton":
        ton_src = next((x for x in sources if str(x.get("name") or "") == "tonapi"), None)
        ton_ev = ton_src.get("evidence") if ton_src else []
        if any(str(ev.get("code") or "") in {"ton_suspended", "ton_blocked_status"} for ev in (ton_ev or [])):
            if score_info.get("level") == "safe":
                score_info["level"] = "suspicious"
                score_info["score"] = max(int(score_info.get("score") or 0), 30)
                score_info["verdict_en"] = "Suspicious"
                score_info["verdict_ru"] = "Подозрительно"

    evidence_all = []
    evidence_all.extend([{"source": "heuristic", **x} for x in heuristics])
    for s in sources:
        for ev in s.get("evidence") or []:
            evidence_all.append({"source": s.get("name"), **ev})

    out = {
        "ok": True,
        "input": target,
        "normalized_input": address,
        "kind": kind,
        "chain": chain,
        "chain_label": _localized_chain_label(chain, lang),
        "kind_localized": _localized_object_kind(kind, lang),
        "score": score_info["score"],
        "level": score_info["level"],
        "normalized_level": score_info.get("normalized_level", score_info["level"]),
        "verdict_en": score_info["verdict_en"],
        "verdict_ru": score_info["verdict_ru"],
        "verdict_localized": score_info["verdict_ru"] if lang == "ru" else score_info["verdict_en"],
        "confirmed_red_flag": score_info["confirmed_red_flag"],
        "malicious_sources": score_info["malicious_sources"],
        "scoring": score_info["components"],
        "sources": sources,
        "evidence": sorted(evidence_all, key=lambda x: int(x.get("severity") or 0), reverse=True)[:30],
        "community": community,
        "details": {
            "token": {
                **(token_data or {}),
                "honeypot": honeypot_res.get("details") or None,
            },
            "address": address,
            "kind_detected": kind,
            "chain": chain,
            "chain_label": _localized_chain_label(chain, lang),
            "is_evm": is_evm,
            "contract_identity": contract_identity,
            "noytrix_scam_database": score_info.get("noytrix_scam_database") or {
                "applied": False,
                "match": noytrix_db_match,
            },
        },
        "contract_identity": contract_identity,
        "permissions_summary": {
            "can_spend": None,
            "unlimited": None,
            "tokens": [((token_data or {}).get("baseToken") or {}).get("symbol")] if ((token_data or {}).get("baseToken") or {}).get("symbol") else [],
            "spend_limit": "unknown",
            "revoke_difficulty": "medium" if kind == "contract" else "unknown",
            "summary": (
                (
                    "Точные разрешения этого контракта видны только при конкретной транзакции или подписи." if lang == "ru"
                    else "Точні дозволи цього контракту видно лише під час конкретної транзакції або підпису." if is_uk
                    else "Exact permissions for this contract are visible only from a specific transaction or signature."
                )
                if kind == "contract"
                else (
                    "По одному адресу разрешение на списание токенов не обнаружено." if lang == "ru"
                    else "За однією адресою дозвіл на списання токенів не виявлено." if is_uk
                    else "No token spending permission detected from address scan alone."
                )
            ),
            "note": (
                "Точный approval можно определить только из данных транзакции/подписи." if lang == "ru"
                else "Точний approval можна визначити лише з даних транзакції/підпису." if is_uk
                else "Contract scan only. Exact wallet permission requires transaction/signature data."
            )
        },
        "lang": lang,
        "cached": False,
    }

    out = _attach_pg_graph_context(out)
    out = _attach_multichain_fields(out, address, {"chain": chain, "chainId": preferred_chain_id, "kind": kind})
    out = apply_anti_false_positive_layer(out)
    out = _attach_ai_investigation_fields(out)

    cache_set(cache_key, out, 180)

    out["sources"] = _localize_sources(out["sources"], lang)
    out = attach_legacy_fields(out, lang)
    return out

async def _scan_ticker(target: str, lang: str) -> dict:
    symbol = (target or "").strip().upper()
    cache_key = f"scan:ticker:v4:{symbol}"

    cached = cache_get(cache_key)
    if cached:
        out = dict(cached)
        out["cached"] = True
        out["lang"] = lang
        out["kind_localized"] = _localized_object_kind("ticker", lang)
        out["sources"] = _localize_sources(out.get("sources") or [], lang)
        out = attach_legacy_fields(out, lang)
        return out

    sources: list[dict] = []
    det = _detect_input_kind(target)
    chain = det.get("chain")
    heuristics: list[dict] = []
    page_content_evidence: list[dict] = []

    cg_res = await _check_coingecko_ticker(symbol)
    sources.append(cg_res)

    d = (cg_res.get("details") or {})
    market_data = d.get("marketData")
    picked = d.get("picked") or {}
    all_matches = d.get("all_matches") or []

    contract = None
    domain = None
    holders = None
    honeypot_details = None
    honeypot_source = None
    market_cap_rank = None

    try:
        market_cap_rank = int((picked or {}).get("market_cap_rank") or 0) or None
    except Exception:
        market_cap_rank = None

    skip_honeypot = bool(market_cap_rank and market_cap_rank <= 200)

    honeypot_candidates: list[tuple[str, str]] = []
    primary_coin_id = str(picked.get("id") or "").strip()

    if primary_coin_id:
        try:
            async with httpx.AsyncClient(timeout=SCAN_TIMEOUT) as cl:
                resp = await cl.get(
                    f"https://api.coingecko.com/api/v3/coins/{primary_coin_id}",
                    params={
                        "localization": "false",
                        "tickers": "false",
                        "market_data": "false",
                        "community_data": "false",
                        "developer_data": "false",
                        "sparkline": "false",
                    },
                )
                if resp.status_code == 200:
                    full = resp.json()
                    platforms = full.get("platforms") or {}
                    links = full.get("links") or {}
                    homepages = [x for x in (links.get("homepage") or []) if x]
                    for chain_name, addr in platforms.items():
                        addr_s = str(addr or "").strip()

                        if RE_EVM_ADDR.match(addr_s):
                            honeypot_candidates.append((addr_s, "56"))

        except Exception as e:
            print("Coingecko error:", e)

    seen_hp = set()
    uniq_candidates = []
    for addr, cid in honeypot_candidates:
        k = f"{addr.lower()}::{cid}"
        if k in seen_hp:
            continue
        seen_hp.add(k)
        uniq_candidates.append((addr, cid))

    for addr, cid in uniq_candidates[:6]:
        hp = await _check_honeypot_contract(addr, cid)
        if hp.get("status") in {"malicious", "clean", "no_data"}:
            honeypot_source = hp
            honeypot_details = hp.get("details") or {}
            contract = addr.lower()
            sources.append(hp)
            break

    dominant_match = _is_dominant_top_ticker_match(symbol, picked, all_matches, market_data)

    if honeypot_source is None and not market_data:
        heuristics.append(
            {
                "code": "ticker_ambiguous",
                "severity": 6,
                "text": "Ticker found weakly or ambiguously, market data is incomplete.",
            }
        )

    if honeypot_source is None and market_data and len(all_matches) > 1 and not skip_honeypot and not dominant_match:
        heuristics.append(
            {
                "code": "ticker_multiple_matches",
                "severity": 10,
                "text": "Ticker has multiple possible token matches across chains.",
            }
        )

    if honeypot_details:
        raw_hp = honeypot_details.get("raw") or {}
        token_obj = raw_hp.get("token") or {}
        holders = token_obj.get("totalHolders") or token_obj.get("holders")

    community_key = contract or symbol
    community_kind = "contract" if contract else "ticker"
    community = _community_snapshot(community_key, community_kind)

    score_info = _score_scan(sources, heuristics, page_content_evidence, community)

    evidence_all = []
    evidence_all.extend([{"source": "heuristic", **x} for x in heuristics])
    for s in sources:
        for ev in s.get("evidence") or []:
            evidence_all.append({"source": s.get("name"), **ev})

    token_risk_flags = []
    if honeypot_source:
        for ev in honeypot_source.get("evidence") or []:
            code = str(ev.get("code") or "").strip()
            if code:
                token_risk_flags.append(code)

    out = {
        "ok": True,
        "input": target,
        "normalized_input": symbol,
        "kind": "ticker",
        "kind_localized": _localized_object_kind("ticker", lang),
        "symbol": symbol,
        "score": score_info["score"],
        "level": score_info["level"],
        "normalized_level": score_info.get("normalized_level", score_info["level"]),
        "verdict_en": score_info["verdict_en"],
        "verdict_ru": score_info["verdict_ru"],
        "verdict_localized": score_info["verdict_ru"] if lang == "ru" else score_info["verdict_en"],
        "confirmed_red_flag": score_info["confirmed_red_flag"],
        "malicious_sources": score_info["malicious_sources"],
        "scoring": score_info["components"],
        "sources": sources,
        "evidence": sorted(evidence_all, key=lambda x: int(x.get("severity") or 0), reverse=True)[:30],
        "community": community,
        "details": {
            "symbol": symbol,
            "token": {
                "coingecko_match": picked,
                "all_matches": all_matches[:10],
                "market_data": market_data,
                "holders": holders,
                "contract": contract,
                "domain": domain,
                "token_risk_flags": token_risk_flags,
                "honeypot": honeypot_details,
            },
        },
        "lang": lang,
        "cached": False,
    }

    _save_scan_to_pg_intelligence(out)

    if pg_save_cached_verdict:
        try:
            pg_save_cached_verdict(
                out.get("normalized_input") or out.get("input"),
                {
                    "kind": out.get("kind"),
                    "level": out.get("level"),
                    "score": out.get("score"),
                    "confidence": out.get("confidence_score") or out.get("confidence"),
                    "malicious_sources": out.get("malicious_sources") or [],
                    "scoring": out.get("scoring") or {},
                    "evidence": (out.get("evidence") or [])[:20],
                    "sources": [
                        str(x.get("name") or x.get("source") or "")
                        for x in (out.get("sources") or [])
                        if isinstance(x, dict)
                    ],
                },
                entity_type=out.get("kind"),
                source_name="noytrix_runtime_scan",
            )
        except Exception as e:
            print("[pg_intelligence] direct cached wallet verdict save error:", e)

    cache_set(cache_key, out, 180)
    out["sources"] = _localize_sources(out["sources"], lang)
    out = attach_legacy_fields(out, lang)
    return out

async def _scan_text(target: str, lang: str) -> dict:
    txt = (target or "").strip()
    analysis = _analyze_text_content(txt)

    legacy_payload = None
    if _legacy_scan_text:
        try:
            legacy_payload = await _legacy_scan_text(txt)
        except Exception:
            legacy_payload = None

    sources = [
        _mk_source(
            "text_heuristics",
            "malicious" if analysis["score"] >= 35 else ("clean" if analysis["score"] == 0 else "no_data"),
            verdict="danger" if analysis["score"] >= 35 else ("clean" if analysis["score"] == 0 else "unknown"),
            details={"legacy": legacy_payload},
            evidence=analysis["evidence"],
        )
    ]

    community = _community_snapshot(txt[:180], "text")
    score_info = _score_scan(
        sources=sources,
        heuristics=[],
        page_content=analysis["evidence"],
        community=community,
    )
    text_score = normalize_score(analysis.get("score") or 0)
    text_codes = {str(x.get("code") or "") for x in (analysis.get("evidence") or [])}
    secret_codes = {
        "seed_phrase_request",
        "secret_phrase_request",
        "recovery_phrase_request",
        "private_key_request",
        "explicit_secret_required",
        "private_key_hex_found",
    }
    if text_score >= 30 and str(score_info.get("level") or "").lower() == "safe":
        score_info["score"] = max(int(score_info.get("score") or 0), min(84, text_score))
        score_info["level"] = "suspicious"
        score_info["normalized_level"] = "medium"
        score_info["verdict_en"] = "Suspicious"
        score_info["verdict_ru"] = "Suspicious"
    if text_codes & secret_codes:
        score_info["score"] = max(int(score_info.get("score") or 0), 60)
        score_info["level"] = "danger"
        score_info["normalized_level"] = "high"
        score_info["verdict_en"] = "Danger"
        score_info["verdict_ru"] = "Danger"
        score_info["confirmed_red_flag"] = True
        score_info["internal_red_flag"] = True
        score_info["malicious_sources"] = ["text_heuristics"]

    evidence_all = [{"source": "text_heuristics", **x} for x in analysis["evidence"]]

    out = {
        "ok": True,
        "input": target,
        "normalized_input": txt,
        "kind": "text",
        "kind_localized": _localized_object_kind("text", lang),
        "score": score_info["score"],
        "level": score_info["level"],
        "normalized_level": score_info.get("normalized_level", score_info["level"]),
        "verdict_en": score_info["verdict_en"],
        "verdict_ru": score_info["verdict_ru"],
        "verdict_localized": score_info["verdict_ru"] if lang == "ru" else score_info["verdict_en"],
        "confirmed_red_flag": score_info["confirmed_red_flag"],
        "malicious_sources": score_info["malicious_sources"],
        "scoring": score_info["components"],
        "sources": _localize_sources(sources, lang),
        "evidence": sorted(evidence_all, key=lambda x: int(x.get("severity") or 0), reverse=True)[:20],
        "community": community,
        "details": {"legacy": legacy_payload},
        "lang": lang,
        "cached": False,
    }

    out = attach_legacy_fields(out, lang)
    return out

async def scan_core(target: str, lang: str, user_id: Optional[str], is_pro_user: bool, internal_only: bool = False) -> Dict[str, Any]:
    tx_decoded = decode_evm_tx_input(
        target,
        RE_EVM_ADDR,
        KNOWN_EVM_TOKENS,
        _evm_word_to_addr,
        _evm_word_to_int,
    )
    if tx_decoded:
        spender_rep = None
        if tx_decoded.get("spender"):
            spender_rep = await _check_spender_reputation(tx_decoded.get("spender"))

        trust = (spender_rep or {}).get("trust")

        if tx_decoded.get("unlimited"):
            if trust == "trusted":
                what_override = "Ты даёшь безлимитный доступ доверенному контракту (DEX/Router). Это нормально для свопов, но даёт полный контроль над токенами."
            elif trust == "unknown":
                what_override = "Ты даёшь безлимитный доступ НЕИЗВЕСТНОМУ контракту. Это высокий риск потери средств."
            else:
                what_override = "Ты даёшь безлимитный доступ контракту. Проверь его перед подтверждением."
        else:
            what_override = None

        spender_rep = None
        if tx_decoded.get("spender"):
            spender_rep = await _check_spender_reputation(tx_decoded.get("spender"))

        drainer = detect_drainer_patterns(tx_decoded)
        approve_fields = build_approve_runtime_fields(tx_decoded, spender_rep, lang)

        out = {
            "ok": True,
            "what_override": what_override,
            "input": target,
            "normalized_input": target,
            "kind": "transaction",
            "kind_localized": "Транзакция" if lang == "ru" else "Transaction",
            **approve_fields,
            "malicious_sources": [],
            "scoring": {
                "confirmed_external_signals": 0,
                "heuristics": approve_fields["heuristics_score"],
                "page_content": 0,
                "community_votes": 0
            },
            "sources": [],
            "evidence": [{
                "source": "tx_decoder",
                "code": tx_decoded.get("type"),
                "severity": approve_fields["score"],
                "text": tx_decoded.get("method"),
                "hard_evidence": bool(approve_fields.get("confirmed_red_flag")),
            }],
            "community": {"community_verdict": "unknown", "safe_votes": 0, "scam_votes": 0, "total_users": 0, "immunity_score": 0},
            "details": {"transaction": tx_decoded, "drainer": drainer},
            "drainer": drainer,
            "permissions_summary": build_permissions_summary(tx_decoded, spender_rep, lang),
            "lang": lang,
            "cached": False,
        }
        out = attach_legacy_fields(out, lang)
        out = _attach_ux_risk_blocks(out, lang)
        return out

    det = _detect_input_kind(target)
    kind = det["kind"]

    if kind in {"url", "domain"}:
        return await _scan_url_or_domain(target, lang, is_pro_user, internal_only)
    if kind == "wallet":
        return await _scan_wallet_or_contract(target, lang)
    if kind == "ticker":
        return await _scan_ticker(target, lang)

    return await _scan_text(target, lang)



@app.post("/scan/render-card")
async def scan_render_card(payload: dict = Body(...)):
    try:
        png = render_scan_card(payload)
        return Response(content=png, media_type="image/png")
    except Exception as e:
        print("[scan/render-card] error:", e)
        raise HTTPException(status_code=500, detail="render_card_failed")




# =========================================================
# TELEGRAM LINK / PROFILE
# =========================================================



def send_telegram_link_email(to_email: str, code: str) -> None:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    mail_from = os.getenv("MAIL_FROM", smtp_user)

    if not smtp_user or not smtp_pass or not to_email:
        raise RuntimeError("smtp_not_configured")

    html = f"""
    <div style="background:#06080f;padding:28px;font-family:Arial,sans-serif;color:#e9ecff">
      <div style="max-width:560px;margin:auto;background:#101826;border:1px solid rgba(255,255,255,.12);border-radius:22px;padding:28px">
        <div style="color:#ffb020;font-size:24px;font-weight:800">NOYTRIX</div>
        <h2 style="margin:12px 0 8px;color:#fff">Telegram connect code</h2>
        <p style="color:#A8B4CF">Use this code to connect your Telegram bot to your Noytrix account.</p>
        <div style="margin:24px 0;padding:20px;border-radius:18px;background:#0b1020;text-align:center;font-size:38px;font-weight:900;letter-spacing:8px;color:#ffb020">
          {code}
        </div>
        <p style="color:#A8B4CF">This code is valid for 10 minutes.</p>
        <p style="color:#A8B4CF">If you did not request this, you can ignore this email.</p>
      </div>
    </div>
    """

    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = "Your Noytrix Telegram connect code"
    msg["From"] = f"Noytrix <{mail_from}>"
    msg["To"] = to_email

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(mail_from, [to_email], msg.as_string())


@app.post("/telegram/link-code/create")
def telegram_link_code_create(request: Request, payload: dict = Body(...), lang: str | None = None):
    L = get_lang(request, lang)
    require_app_key(request, L)

    user_id = str(payload.get("user_id") or "").strip().lower()
    email = str(payload.get("email") or "").strip().lower()

    if not user_id:
        raise HTTPException(status_code=400, detail="user_id_required")

    import secrets
    code = str(secrets.randbelow(900000) + 100000)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires_at = (now + timedelta(minutes=10)).isoformat()

    conn = sqlite3.connect(str(APP_DB_PATH))
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO telegram_link_codes
            (code, user_id, email, expires_at, used_at)
            VALUES (?, ?, ?, ?, NULL)
            """,
            (code, user_id, email, expires_at),
        )
        conn.commit()
    finally:
        conn.close()

    if email:
        send_telegram_link_email(email, code)

    return {
        "ok": True,
        "sent": bool(email),
        "expires_at": expires_at,
    }


@app.post("/telegram/link")
def telegram_link(request: Request, payload: dict = Body(...), lang: str | None = None):
    L = get_lang(request, lang)
    require_app_key(request, L)

    telegram_id = str(payload.get("telegram_id") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    user_id = str(payload.get("user_id") or email or "").strip().lower()

    if not telegram_id or not email:
        raise HTTPException(status_code=400, detail="telegram_id_and_email_required")

    conn = sqlite3.connect(str(APP_DB_PATH))
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO telegram_links
            (telegram_id, user_id, email, linked_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                telegram_id,
                user_id,
                email,
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "telegram_id": telegram_id,
        "user_id": user_id,
        "email": email,
    }




@app.post("/telegram/link-code/confirm")
def telegram_link_code_confirm(request: Request, payload: dict = Body(...), lang: str | None = None):
    L = get_lang(request, lang)
    require_app_key(request, L)

    telegram_id = str(payload.get("telegram_id") or "").strip()
    code = str(payload.get("code") or "").strip()

    if not telegram_id or not code:
        raise HTTPException(status_code=400, detail="telegram_id_and_code_required")

    now = datetime.now(timezone.utc).replace(microsecond=0)

    conn = sqlite3.connect(str(APP_DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        row = conn.execute(
            """
            SELECT code, user_id, email, expires_at, used_at
            FROM telegram_link_codes
            WHERE code=?
            """,
            (code,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=400, detail="invalid_code")

        if row["used_at"]:
            raise HTTPException(status_code=400, detail="code_already_used")

        try:
            exp = datetime.fromisoformat(str(row["expires_at"]))
        except Exception:
            raise HTTPException(status_code=400, detail="invalid_code_expiry")

        if exp < now:
            raise HTTPException(status_code=400, detail="code_expired")

        user_id = str(row["user_id"] or "").strip().lower()
        email = str(row["email"] or user_id or "").strip().lower()

        conn.execute(
            """
            INSERT OR REPLACE INTO telegram_links
            (telegram_id, user_id, email, linked_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                telegram_id,
                user_id,
                email,
                now.isoformat(),
            ),
        )

        conn.execute(
            "UPDATE telegram_link_codes SET used_at=? WHERE code=?",
            (now.isoformat(), code),
        )

        conn.commit()

    finally:
        conn.close()

    return {
        "ok": True,
        "telegram_id": telegram_id,
        "user_id": user_id,
        "email": email,
    }




@app.post("/telegram/unlink")
async def telegram_unlink(payload: dict):
    telegram_id = str(payload.get("telegram_id") or "").strip()

    if not telegram_id:
        raise HTTPException(status_code=400, detail="telegram_id_required")

    conn = sqlite3.connect(APP_DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM telegram_links WHERE telegram_id=?",
        (telegram_id,)
    )

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "telegram_id": telegram_id,
        "unlinked": True,
    }






@app.post("/telegram/scan-limit/check")
def telegram_scan_limit_check(request: Request, payload: dict = Body(...), lang: str | None = None):
    L = get_lang(request, lang)
    require_app_key(request, L)

    telegram_id = str(payload.get("telegram_id") or "").strip()
    if not telegram_id:
        raise HTTPException(status_code=400, detail="telegram_id_required")

    profile = telegram_profile(request, telegram_id=telegram_id, lang=lang)
    is_pro = bool(profile.get("isPro"))

    if is_pro:
        return {
            "ok": True,
            "allowed": True,
            "isPro": True,
            "limit": None,
            "used": 0,
            "left": None,
        }

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    free_limit = 4

    conn = sqlite3.connect(str(APP_DB_PATH))
    try:
        row = conn.execute(
            "SELECT scans FROM telegram_scan_limits WHERE telegram_id=? AND day=?",
            (telegram_id, day),
        ).fetchone()

        used = int(row[0]) if row else 0

        if used >= free_limit:
            return {
                "ok": True,
                "allowed": False,
                "isPro": False,
                "limit": free_limit,
                "used": used,
                "left": 0,
            }

        conn.execute(
            """
            INSERT INTO telegram_scan_limits (telegram_id, day, scans)
            VALUES (?, ?, 1)
            ON CONFLICT(telegram_id, day) DO UPDATE SET scans = scans + 1
            """,
            (telegram_id, day),
        )
        conn.commit()

        return {
            "ok": True,
            "allowed": True,
            "isPro": False,
            "limit": free_limit,
            "used": used + 1,
            "left": max(0, free_limit - used - 1),
        }

    finally:
        conn.close()


@app.post("/telegram/profile/stats/track")
def telegram_profile_stats_track(request: Request, payload: dict = Body(...), lang: str | None = None):
    L = get_lang(request, lang)
    require_app_key(request, L)

    telegram_id = str(payload.get("telegram_id") or "").strip()
    level = str(payload.get("level") or "").lower().strip()

    if not telegram_id:
        raise HTTPException(status_code=400, detail="telegram_id_required")

    is_scam = 1 if level in {"danger", "critical"} else 0
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    conn = sqlite3.connect(str(APP_DB_PATH))
    try:
        conn.execute(
            """
            INSERT INTO telegram_profile_stats
            (telegram_id, total_scans, scam_reports, last_activity)
            VALUES (?, 1, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                total_scans = total_scans + 1,
                scam_reports = scam_reports + excluded.scam_reports,
                last_activity = excluded.last_activity
            """,
            (telegram_id, is_scam, now),
        )
        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "telegram_id": telegram_id}


@app.get("/telegram/profile")
def telegram_profile(request: Request, telegram_id: str, lang: str | None = None):
    L = get_lang(request, lang)
    require_app_key(request, L)

    tid = str(telegram_id or "").strip()

    conn = sqlite3.connect(str(APP_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT telegram_id, user_id, email, linked_at FROM telegram_links WHERE telegram_id=?",
            (tid,),
        ).fetchone()
    finally:
        conn.close()

    linked = dict(row) if row else None

    guest_pro = False
    user_ids = [f"telegram_{tid}"]

    if linked:
        if linked.get("user_id"):
            user_ids.append(str(linked["user_id"]))
        if linked.get("email"):
            user_ids.append(str(linked["email"]).lower())

    try:
        gp = sqlite3.connect(str(DATA_DIR / "guest_pro.sqlite3"))
        q = ",".join(["?"] * len(user_ids))
        r = gp.execute(
            f"SELECT user_id FROM guest_pro WHERE is_active=1 AND user_id IN ({q}) LIMIT 1",
            user_ids,
        ).fetchone()
        guest_pro = bool(r)
        gp.close()
    except Exception:
        guest_pro = False

    conn = sqlite3.connect(str(APP_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        stats_row = conn.execute(
            "SELECT total_scans, scam_reports, last_activity FROM telegram_profile_stats WHERE telegram_id=?",
            (tid,),
        ).fetchone()
    finally:
        conn.close()

    stats = dict(stats_row) if stats_row else {
        "total_scans": 0,
        "scam_reports": 0,
        "last_activity": None,
    }

    return {
        "ok": True,
        "telegram_id": tid,
        "linked": linked,
        "isPro": guest_pro,
        "plan": "PRO" if guest_pro else "FREE",
        "stats": stats,
    }



# =========================================================
# B2B PUBLIC API v1
# =========================================================
class B2BScanIn(BaseModel):
    input: str
    lang: Optional[str] = "en"
    user_id: Optional[str] = None
    explanation_mode: Optional[str] = "detailed"
    internal_only: Optional[bool] = False
    external_check: Optional[bool] = False


def normalize_lang(lang: str | None) -> str:
    lang = (lang or "en").lower().strip()
    if lang.startswith("ru"):
        return "ru"
    if lang.startswith("uk"):
        return "uk"
    return "en"

def _extract_b2b_api_key(request: Request) -> str:
    return (
        request.headers.get("x-api-key")
        or request.headers.get("authorization", "").replace("Bearer ", "").strip()
        or ""
    ).strip()

def _require_b2b_api_key(request: Request):
    raw_key = _extract_b2b_api_key(request)
    ip = _api_client_ip(request)
    ua = request.headers.get("user-agent", "")

    if not raw_key or not raw_key.startswith("nx_"):
        _api_log_usage(status_code=401, ip=ip, user_agent=ua, error_code="missing_api_key")
        raise HTTPException(status_code=401, detail={"error": "missing_api_key", "message": "Missing x-api-key header."})

    key_hash = _sha256_text(raw_key)
    now = _utc_now_iso()
    month = _api_current_month()

    conn = _api_db_connect()
    try:
        row = conn.execute("SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)).fetchone()
        if not row:
            _api_log_usage(key_prefix=raw_key[:10], status_code=401, ip=ip, user_agent=ua, error_code="invalid_api_key")
            raise HTTPException(status_code=401, detail={"error": "invalid_api_key", "message": "Invalid API key."})

        if str(row["status"]).lower() != "active":
            _api_log_usage(api_key_id=row["id"], key_prefix=row["key_prefix"], status_code=403, ip=ip, user_agent=ua, error_code="api_key_inactive")
            raise HTTPException(status_code=403, detail={"error": "api_key_inactive", "message": "API key is not active."})

        if row["expires_at"] and str(row["expires_at"]) < now:
            _api_log_usage(api_key_id=row["id"], key_prefix=row["key_prefix"], status_code=403, ip=ip, user_agent=ua, error_code="api_key_expired")
            raise HTTPException(status_code=403, detail={"error": "api_key_expired", "message": "API key expired."})

        if row["current_month"] != month:
            conn.execute(
                "UPDATE api_keys SET current_month=?, requests_used_month=0, updated_at=? WHERE id=?",
                (month, now, row["id"])
            )
            conn.commit()
            row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (row["id"],)).fetchone()

        used = int(row["requests_used_month"] or 0)
        limit = int(row["monthly_limit"] or 0)

        if limit > 0 and used >= limit:
            _api_log_usage(api_key_id=row["id"], key_prefix=row["key_prefix"], status_code=429, ip=ip, user_agent=ua, error_code="monthly_limit_exceeded")
            raise HTTPException(status_code=429, detail={
                "error": "monthly_limit_exceeded",
                "message": "Monthly API request limit exceeded.",
                "usage": {"used": used, "limit": limit, "month": month}
            })

        rpm = int(row["rate_limit_per_minute"] or 60)
        if rpm > 0:
            one_min_ago = datetime.now(timezone.utc) - timedelta(seconds=60)
            recent_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM api_usage_logs
                WHERE api_key_id = ?
                  AND status_code = 200
                  AND created_at >= ?
                """,
                (row["id"], one_min_ago.isoformat())
            ).fetchone()[0]

            if int(recent_count or 0) >= rpm:
                _api_log_usage(api_key_id=row["id"], key_prefix=row["key_prefix"], status_code=429, ip=ip, user_agent=ua, error_code="rate_limit_exceeded")
                raise HTTPException(status_code=429, detail={
                    "error": "rate_limit_exceeded",
                    "message": "Rate limit exceeded.",
                    "rate_limit_per_minute": rpm
                })

        return dict(row)
    finally:
        conn.close()

def _b2b_increment_usage(api_key_id: int, ip: str):
    conn = _api_db_connect()
    try:
        conn.execute(
            """
            UPDATE api_keys
            SET requests_used_month = requests_used_month + 1,
                last_used_at = ?,
                last_ip = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (_utc_now_iso(), ip, _utc_now_iso(), api_key_id)
        )
        conn.commit()
    finally:
        conn.close()



@app.exception_handler(HTTPException)
async def b2b_http_exception_handler(request: Request, exc: HTTPException):
    if str(request.url.path).startswith("/v1/"):
        if isinstance(exc.detail, dict):
            body = {"ok": False, **exc.detail}
        else:
            body = {"ok": False, "error": "http_error", "message": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content=body)
    if isinstance(exc.detail, dict):
        body = {"ok": False, **exc.detail}
    else:
        body = {"ok": False, "error": "http_error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.get("/v1/docs")
async def b2b_v1_docs():
    return {
        "ok": True,
        "name": "Noytrix API",
        "version": "v1",
        "base_url": "https://api.noytrixapp.com",
        "authentication": {
            "header": "x-api-key",
            "alternative": "Authorization: Bearer YOUR_API_KEY"
        },
        "endpoints": [
            {
                "method": "GET",
                "path": "/v1/me",
                "description": "Check API key status, plan and usage."
            },
            {
                "method": "POST",
                "path": "/v1/scan",
                "description": "Scan URL, domain, wallet, smart contract, token/ticker or text for crypto scam risk.",
                "body": {
                    "input": "https://example.com",
                    "lang": "en",
                    "explanation_mode": "short | detailed"
                }
            }
        ],
        "example_curl": "curl -X POST https://api.noytrixapp.com/v1/scan -H 'Content-Type: application/json' -H 'x-api-key: YOUR_API_KEY' -d '{\"input\":\"https://example.com\",\"lang\":\"en\"}'",
        "response_fields": {
            "score": "Risk score from 0 to 100",
            "level": "safe, suspicious, danger or critical",
            "sources": "External and internal security checks",
            "evidence": "Human-readable risk evidence",
            "api.usage": "Monthly usage and limits",
            "ai_explanation_result": "AI-generated human-readable explanation with structured short/details/risks/actions fields"
        }
    }

@app.get("/v1/me")
async def b2b_v1_me(request: Request):
    api_key = _require_b2b_api_key(request)

    used = int(api_key.get("requests_used_month") or 0)
    limit = int(api_key.get("monthly_limit") or 0)

    return {
        "ok": True,
        "api": {
            "version": "v1",
            "status": api_key.get("status"),
            "plan": api_key.get("plan_code"),
            "key_prefix": api_key.get("key_prefix"),
            "owner_email": api_key.get("owner_email"),
            "company_name": api_key.get("company_name"),
            "rate_limit_per_minute": api_key.get("rate_limit_per_minute"),
            "expires_at": api_key.get("expires_at"),
            "usage": {
                "month": _api_current_month(),
                "used": used,
                "limit": limit,
                "left": max(limit - used, 0) if limit > 0 else None
            }
        }
    }

@app.post("/v1/scan")
async def b2b_v1_scan(request: Request, payload: B2BScanIn = Body(...)):
    started = time.time()
    ip = _api_client_ip(request)
    ua = request.headers.get("user-agent", "")

    api_key = _require_b2b_api_key(request)

    target = (payload.input or "").strip()
    L = normalize_lang(payload.lang or "en")

    if not target:
        _api_log_usage(
            api_key_id=api_key["id"],
            key_prefix=api_key["key_prefix"],
            status_code=400,
            latency_ms=int((time.time() - started) * 1000),
            ip=ip,
            user_agent=ua,
            error_code="missing_input",
        )
        raise HTTPException(status_code=400, detail={"error": "missing_input", "message": "Input is required."})

    try:
        data = await security_analyze_core({
            "input": target,
            "lang": L,
            "user_id": payload.user_id or f"api_key_{api_key['id']}",
            "is_pro": True,
            "internal_only": bool(getattr(payload, "internal_only", False) or (NOYTRIX_INTERNAL_MODE and not bool(getattr(payload, "external_check", False)))),
            "external_check": bool(getattr(payload, "external_check", False)),
        })
        data = attach_legacy_fields(data, L)
        data = _attach_ux_risk_blocks(data, L)

        try:
            judge_context = build_ai_explanation_context(data)
            data["ai_security_judge"] = await generate_ai_security_judge(judge_context, L)

            judge = data.get("ai_security_judge") or {}
            judge_delta = int(judge.get("risk_delta") or 0)

            if judge.get("available") and judge_delta > 0:
                data["score_before_ai_judge"] = int(data.get("score") or 0)
                data["score"] = min(100, int(data.get("score") or 0) + judge_delta)

                if data["score"] >= 90:
                    data["level"] = "critical"
                    data["verdict"] = "critical"
                elif data["score"] >= 70:
                    data["level"] = "high"
                    data["verdict"] = "high"
                elif data["score"] >= 40:
                    data["level"] = "suspicious"
                    data["verdict"] = "suspicious"

                data.setdefault("sources", []).append({
                    "name": "ai_security_judge",
                    "source": "ai_security_judge",
                    "status": data.get("level"),
                    "verdict": judge.get("level"),
                    "details": judge,
                    "evidence": [
                        {
                            "code": "ai_security_judge",
                            "severity": judge.get("score"),
                            "text": judge.get("reasoning") or "AI security judge added risk signal."
                        }
                    ],
                    "status_text": "AI judge"
                })

                data.setdefault("evidence", []).append({
                    "source": "ai_security_judge",
                    "code": "ai_security_judge",
                    "severity": judge.get("score"),
                    "text": judge.get("reasoning") or "AI security judge added risk signal."
                })

            data["ai_explanation_context"] = build_ai_explanation_context(data)

            data["ai_explanation_result"] = await generate_ai_security_explanation(
                data,
                L,
                payload.explanation_mode or "detailed",
            )

            data["ai_explanation"] = (
                (data.get("ai_explanation_result") or {}).get("text")
                or data.get("ai_explanation")
                or ""
            )

        except Exception as e:
            data["ai_explanation_result"] = {
                "available": False,
                "reason": str(e)[:300],
                "text": "",
            }

        _b2b_increment_usage(api_key["id"], ip)

        used_after = int(api_key.get("requests_used_month") or 0) + 1
        limit = int(api_key.get("monthly_limit") or 0)

        data["api"] = {
            "version": "v1",
            "plan": api_key.get("plan_code"),
            "key_prefix": api_key.get("key_prefix"),
            "usage": {
                "month": _api_current_month(),
                "used": used_after,
                "limit": limit,
                "left": max(limit - used_after, 0) if limit > 0 else None
            }
        }

        _api_log_usage(
            api_key_id=api_key["id"],
            key_prefix=api_key["key_prefix"],
            input_value=target[:500],
            input_kind=data.get("kind"),
            verdict_level=data.get("level"),
            score=data.get("score"),
            status_code=200,
            latency_ms=int((time.time() - started) * 1000),
            ip=ip,
            user_agent=ua,
        )

        return data

    except HTTPException:
        raise
    except Exception as e:
        print("[b2b-api] /v1/scan fatal:", e)
        _api_log_usage(
            api_key_id=api_key["id"],
            key_prefix=api_key["key_prefix"],
            input_value=target[:500],
            status_code=500,
            latency_ms=int((time.time() - started) * 1000),
            ip=ip,
            user_agent=ua,
            error_code="scan_failed",
        )
        raise HTTPException(status_code=500, detail={"error": "scan_failed", "message": "Scan failed."})






@app.post("/v1/security/analyze")
async def security_analyze(request: Request, payload: dict = Body(...)):
    return await security_analyze_core(payload)



async def security_analyze_core(payload: dict) -> dict:

    """
    NOYTRIX unified security endpoint.
    Future source of truth for Extension, Mobile App, Telegram Bot, Website and Admin Panel.
    Old endpoints must become wrappers around this flow.
    """
    started = time.time()

    target = str(
        payload.get("input")
        or payload.get("target")
        or payload.get("url")
        or payload.get("address")
        or payload.get("data")
        or ""
    ).strip()

    lang = normalize_lang(str(payload.get("lang") or "en"))
    user_id = str(payload.get("user_id") or payload.get("userId") or "security_core").strip()
    is_pro_user = bool(payload.get("is_pro") or payload.get("isPro") or payload.get("pro") or True)
    external_check = bool(payload.get("external_check") or payload.get("externalCheck"))
    internal_only = bool(payload.get("internal_only") or payload.get("internalOnly") or (NOYTRIX_INTERNAL_MODE and not external_check))

    if not target:
        raise HTTPException(status_code=400, detail={"error": "missing_input", "message": "Input is required."})

    data = await scan_core(target, lang, user_id, is_pro_user, internal_only)
    data = attach_legacy_fields(data, lang)
    data = _attach_ux_risk_blocks(data, lang)

    score = int(data.get("score") or data.get("risk_score") or 0)
    level = _canonical_level(data.get("level"), score)
    confidence = int(data.get("confidence") or data.get("confidence_score") or 0)
    if confidence <= 0:
        evidence_count = len(data.get("evidence") or [])
        sources_count = len(data.get("sources") or [])
        confidence = min(95, 35 + evidence_count * 10 + sources_count * 5)

    data["confidence_score"] = confidence
    data["canonical_level"] = level

    unified = {
        "ok": True,
        "version": "v1",
        "engine": "noytrix_security_core",
        "latency_ms": int((time.time() - started) * 1000),

        "input": target,
        "normalized_input": data.get("normalized_input") or target,
        "kind": data.get("kind"),
        "score": score,
        "internal_score": data.get("internal_score"),
        "external_score": data.get("external_score"),
        "internal_level": data.get("internal_level"),
        "external_level": data.get("external_level"),
        "internal_red_flag": data.get("internal_red_flag"),
        "external_red_flag": data.get("external_red_flag"),
        "internal_only": data.get("internal_only"),
        "scoring": data.get("scoring") or {},
        "confidence": confidence,
        "confidence_score": confidence,
        "level": level,
        "verdict": level,
        "risk_type": data.get("risk_type") or data.get("kind") or "unknown",
        "cached": bool(data.get("cached")),
        "cache_source": data.get("cache_source"),

        "summary": data.get("summary") or data.get("title") or data.get("result") or "",
        "what_can_happen": data.get("what_can_happen") or data.get("worst_case") or "",
        "what_can_be_stolen": data.get("what_can_be_stolen") or [],
        "how_it_works": data.get("how_it_works") or "",
        "recommended_action": data.get("recommended_action") or data.get("action") or "",

        "permissions_summary": data.get("permissions_summary") or {},
        "simulation": data.get("simulation") or {},
        "campaign": data.get("campaign") or {},
        "wallet_profile": data.get("wallet_profile") or {},
        "multi_chain_intelligence": data.get("multi_chain_intelligence") or {},
        "ai_investigation": data.get("ai_investigation") or {},
        "evidence": data.get("evidence") or [],
        "sources": data.get("sources") or [],
        "details": data.get("details") or {},
        "ai_explanation": data.get("ai_explanation") or data.get("explanation") or "",

        "raw": data,
    }

    unified = _attach_pg_graph_context(unified)

    unified = apply_anti_false_positive_layer(unified)

    # Re-apply graph/reputation context after anti-FP, so malicious wallet reputation still affects wallet verdicts.
    unified = _attach_pg_graph_context(unified)

    if str(unified.get("kind") or "").lower() in {"wallet", "contract", "transaction", "runtime_web3"} or str(unified.get("normalized_input") or "").startswith("0x"):
        unified = _attach_multichain_fields(unified)

    try:
        remember_many_from_verdict(unified, source="security_core")
        remember_relations_from_verdict(unified, source="security_core")

        memory = get_entity_memory(
            str(unified.get("normalized_input") or unified.get("input") or ""),
            str(unified.get("kind") or "unknown"),
        )

        unified["threat_memory"] = memory or {}
        unified["memory_summary"] = build_memory_summary(
            memory,
            current_score=int(unified.get("score") or 0),
            current_level=str(unified.get("level") or "unknown"),
        )

    except Exception as e:
        unified["threat_memory_error"] = str(e)

    unified = _attach_ai_investigation_fields(unified)

    return unified


@app.post("/admin/spender-reputation/add")
def admin_add_spender_reputation(request: Request, payload: dict = Body(...), lang: str | None = None):
    L = get_lang(request, lang)
    require_app_key(request, L)

    address = str(payload.get("address") or "").lower().strip()
    if not RE_EVM_ADDR.match(address):
        raise HTTPException(status_code=400, detail={"error": "invalid_evm_address"})

    label = str(payload.get("label") or "Unknown spender").strip()
    category = str(payload.get("category") or "wallet_drainer").strip()
    trust = str(payload.get("trust") or "malicious").strip().lower()
    risk = str(payload.get("risk") or "critical").strip().lower()
    reasons = payload.get("reasons") or ["manual_admin_reputation"]
    source = str(payload.get("source") or "admin").strip()

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    conn = _spender_rep_db_connect()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO spender_reputation
            (address,label,category,trust,risk,reasons,source,first_seen,last_seen)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            address,
            label,
            category,
            trust,
            risk,
            json.dumps(reasons, ensure_ascii=False),
            source,
            now_iso,
            now_iso,
        ))
        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "address": address, "label": label, "trust": trust, "risk": risk}




@app.get("/admin/spender-reputation/list")
def admin_list_spender_reputation(request: Request, lang: str | None = None, limit: int = 50):
    L = get_lang(request, lang)
    require_app_key(request, L)

    conn = _spender_rep_db_connect()
    try:
        rows = conn.execute("""
            SELECT address,label,category,trust,risk,reasons,source,first_seen,last_seen
            FROM spender_reputation
            ORDER BY last_seen DESC
            LIMIT ?
        """, (max(1, min(int(limit or 50), 200)),)).fetchall()

        return {
            "ok": True,
            "items": [dict(r) for r in rows]
        }
    finally:
        conn.close()

@app.get("/admin/spender-runtime-events/list")
def admin_list_spender_runtime_events(request: Request, lang: str | None = None, limit: int = 50):
    L = get_lang(request, lang)
    require_app_key(request, L)

    conn = _spender_rep_db_connect()
    try:
        rows = conn.execute("""
            SELECT id,address,domain,method,level,unlimited,drainer_flags,created_at
            FROM spender_runtime_events
            ORDER BY id DESC
            LIMIT ?
        """, (max(1, min(int(limit or 50), 200)),)).fetchall()

        return {
            "ok": True,
            "items": [dict(r) for r in rows]
        }
    finally:
        conn.close()



@app.get("/admin/drainer-campaigns/list")
def admin_list_drainer_campaigns(request: Request, lang: str | None = None, limit: int = 50):
    L = get_lang(request, lang)
    require_app_key(request, L)

    conn = _spender_rep_db_connect()
    try:
        rows = conn.execute("""
            SELECT campaign_id,spender,domains,events_count,critical_count,first_seen,last_seen,risk
            FROM drainer_campaigns
            ORDER BY critical_count DESC, events_count DESC, last_seen DESC
            LIMIT ?
        """, (max(1, min(int(limit or 50), 200)),)).fetchall()

        return {
            "ok": True,
            "items": [dict(r) for r in rows]
        }
    finally:
        conn.close()


# =========================================================
# Runtime extension analysis
# =========================================================

def _is_signature_runtime_method(method: str) -> bool:
    method = str(method or "").lower()
    return any(x in method for x in [
        "signtypeddata",
        "personal_sign",
        "eth_sign",
        "signmessage",
        "sign_typed",
        "wallet_sign",
    ])


@app.post("/runtime/analyze")
async def runtime_analyze(payload: dict = Body(...)):
    runtime_payload = normalize_runtime_payload(payload)
    runtime_data = str(runtime_payload.get("data") or "").strip()
    runtime_input = str(
        payload.get("input")
        or payload.get("target")
        or runtime_payload.get("url")
        or runtime_payload.get("domain")
        or ""
    ).strip()

    target = runtime_data if runtime_data.startswith("0x") or "|" in runtime_data else runtime_input

    lang = normalize_lang(str(payload.get("lang") or "en"))
    method = str(payload.get("method") or "").lower()

    if _is_signature_runtime_method(method):
        data = _analyze_typed_signature_payload(payload)
    else:
        if not target:
            raise HTTPException(status_code=400, detail={"error": "missing_input"})

        request_payload = {
            "input": target,
            "lang": lang,
            "user_id": "runtime_extension",
            "is_pro": True,
            "internal_only": bool(NOYTRIX_INTERNAL_MODE and not bool(payload.get("external_check") or payload.get("externalCheck"))),
        }

        data = await security_analyze_core(request_payload)

    runtime_spender = (
        data.get("permissions_summary", {}).get("spender")
        or payload.get("spender")
    )

    runtime_unlimited = bool(
        data.get("permissions_summary", {}).get("unlimited")
    ) if data.get("permissions_summary") else bool(payload.get("approve_unlimited"))

    runtime_flags = (data.get("drainer") or {}).get("flags") or []

    if runtime_unlimited:
        permissions = data.get("permissions_summary") or {}
        if not isinstance(permissions, dict):
            permissions = {}
        permissions.setdefault("can_spend", True)
        permissions.setdefault("unlimited", True)
        permissions.setdefault("spender", runtime_spender)
        permissions.setdefault("spend_limit", "unlimited")
        permissions.setdefault("revoke_difficulty", "high")
        permissions.setdefault("summary", "This wallet action can grant unlimited token spending permission.")
        data["permissions_summary"] = permissions
        spender_trust = str(permissions.get("spender_trust") or permissions.get("spender_trust_level") or "").lower()
        if spender_trust not in {"trusted", "verified", "safe"} and int(data.get("score") or 0) < 85:
            data["score"] = 92
            data["runtime_severity"] = 92
            data["heuristics_score"] = max(92, int(data.get("heuristics_score") or 0))
            data["level"] = "critical"
            data["normalized_level"] = "critical"
            data["risk_type"] = data.get("risk_type") or "unlimited_approval_to_unknown_spender"
            data["confirmed_red_flag"] = True
            evidence = data.setdefault("evidence", [])
            if isinstance(evidence, list):
                evidence.append({
                    "source": "runtime_extension",
                    "code": "unlimited_approval_to_unknown_spender",
                    "severity": 92,
                    "text": "The wallet request can grant unlimited token spending permission to an unverified spender.",
                    "hard_evidence": True,
                })

    try:
        raw_data = data.get("raw") or {}
        raw_details = raw_data.get("details") or {}
        runtime_behavior = analyze_transaction_behavior(
            raw_details.get("tx_decoded")
            or raw_details.get("transaction")
            or data.get("tx_decoded")
            or data.get("transaction"),
            data.get("permissions_summary") or {},
            (data.get("permissions_summary") or {}).get("spender_reputation") or {},
            payload.get("domain"),
        )
        data["runtime_behavior"] = runtime_behavior
        _tx_for_graph = (
            raw_details.get("tx_decoded")
            or raw_details.get("transaction")
            or data.get("tx_decoded")
            or data.get("transaction")
        )

        data["execution_graph"] = build_execution_graph(_tx_for_graph)
        data["recursive_execution_graph"] = build_recursive_execution_graph(str(payload.get("data") or payload.get("input") or ""))

        graph_score = int((data.get("recursive_execution_graph") or {}).get("attack_chain_score") or 0)
        graph_level = str((data.get("recursive_execution_graph") or {}).get("attack_chain_level") or "").lower()

        if graph_score > int(data.get("score") or 0):
            data["score"] = graph_score
            data["runtime_severity"] = graph_score
            data["heuristics_score"] = graph_score

        if graph_level in {"high", "critical"}:
            data["level"] = graph_level
            data["normalized_level"] = graph_level
            data["risk_type"] = data.get("risk_type") or "execution_attack_chain"
            data["confirmed_red_flag"] = graph_level == "critical" or bool(data.get("confirmed_red_flag"))

        data["wallet_drain_simulation"] = simulate_wallet_drain(
            raw_details.get("tx_decoded") or {},
            data.get("permissions_summary") or {},
            data.get("runtime_behavior") or {},
            data.get("recursive_execution_graph") or {},
        )

        data["ai_explanation_context"] = build_ai_explanation_context(data)
    except Exception as e:
        data["runtime_behavior_error"] = str(e)

    _track_spender_runtime_event(
        runtime_spender,
        payload.get("domain"),
        payload.get("method"),
        data.get("level"),
        runtime_unlimited,
        runtime_flags,
    )

    _auto_escalate_spender_reputation(runtime_spender)
    _update_drainer_campaign_for_spender(runtime_spender)

    runtime_campaign = _get_campaign_for_spender(runtime_spender)

    if runtime_campaign:
        data["campaign"] = runtime_campaign

    data["simulation"] = _build_runtime_simulation(data)

    runtime_wallet = payload.get("wallet") or payload.get("from")

    wallet_profile = _update_wallet_risk_profile(runtime_wallet, data)

    if wallet_profile:
        data["wallet_profile"] = wallet_profile

    data = _attach_multichain_fields(
        data,
        runtime_wallet or runtime_spender or target or runtime_payload.get("url") or runtime_payload.get("domain"),
        {
            "chain": payload.get("chain") or payload.get("network"),
            "chainId": payload.get("chainId") or payload.get("chain_id"),
            "kind": data.get("kind") or "runtime_web3",
        },
    )
    data = _attach_ai_investigation_fields(data)
    data["runtime_contract"] = build_runtime_contract(payload, data)
    data["runtime"] = {
        "source": runtime_payload.get("source") or "extension",
        "method": payload.get("method"),
        "domain": payload.get("domain"),
        "provider": payload.get("provider"),
        "flags": payload.get("flags") or [],
        "spender": runtime_spender,
        "contract_version": data["runtime_contract"].get("version"),
    }

    details = data.setdefault("details", {})
    if isinstance(details, dict):
        details["runtime_contract"] = data["runtime_contract"]
        details["runtime_context"] = {
            "source": data["runtime"].get("source"),
            "method": data["runtime"].get("method"),
            "domain": data["runtime"].get("domain"),
            "wallet": runtime_payload.get("wallet"),
            "spender": runtime_spender,
            "should_warn": data["runtime_contract"].get("should_warn"),
            "should_block": data["runtime_contract"].get("should_block"),
        }
        internal_verdict = details.get("internal_verdict")
        if isinstance(internal_verdict, dict):
            internal_verdict["runtime_context"] = details["runtime_context"]
        else:
            details["internal_verdict"] = {
                "engine": "noytrix_runtime_verdict_core",
                "version": "1.0",
                "authority": "internal",
                "target": target or runtime_payload.get("domain") or runtime_payload.get("url"),
                "kind": data.get("kind") or "runtime_web3",
                "level": data.get("level"),
                "score": data.get("score"),
                "confidence": data.get("confidence_score") or data.get("confidence") or 50,
                "evidence": data.get("evidence") or [],
                "graph_context": data.get("graph") or {},
                "reputation_context": data.get("reputation") or {},
                "campaign_context": data.get("campaign") or {},
                "runtime_context": details["runtime_context"],
            }
        runtime_family = classify_scam_family(data)
        data["scam_family"] = runtime_family
        data["risk_family"] = runtime_family.get("primary_family")
        if isinstance(details.get("internal_verdict"), dict):
            details["internal_verdict"]["scam_family"] = runtime_family
            details["internal_verdict"]["risk_family"] = runtime_family.get("primary_family")
        details["scam_family"] = runtime_family

    try:
        data["ai_explanation_result"] = await generate_ai_security_explanation(
            data,
            payload.get("lang") or "en",
            payload.get("explanation_mode") or "detailed",
        )
        data["ai_explanation"] = (data.get("ai_explanation_result") or {}).get("text") or data.get("ai_explanation") or ""
    except Exception as e:
        data["ai_explanation_result"] = {
            "available": False,
            "reason": str(e)[:300],
            "text": "",
        }

    return data


@app.post("/runtime/web3/analyze")
async def runtime_web3_analyze(payload: dict = Body(...)):
    payload = dict(payload or {})
    payload.setdefault("source", "extension")
    return await runtime_analyze(payload)


@app.post("/mobile/runtime/analyze")
async def mobile_runtime_analyze(payload: dict = Body(...)):
    payload = dict(payload or {})
    payload.setdefault("source", "mobile")
    return await runtime_analyze(payload)



# =========================================================
# /scan
# =========================================================
@app.api_route("/scan", methods=["GET","POST"])
async def scan(
    request: Request,
    input: str = Query(..., description="URL / domain / wallet / contract / ticker / text"),
    lang: str | None = Query(None, description="Language: en / ru / uk"),
    userId: str | None = None,
):
    target = (input or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail=tr(get_lang(request, lang), "missing_input"))

    L = get_lang(request, lang)
    uid = _get_user_id(request, userId)
    client_host = str(request.client.host if request.client else "")
    is_internal_test = client_host in {"127.0.0.1", "localhost", "::1"}

    if is_internal_test:
        quota_info = {
            "isPro": True,
            "freeLimit": DAILY_FREE_LIMIT,
            "feature": "scan",
            "day": datetime.utcnow().strftime("%Y%m%d"),
            "used": 0,
            "left": 999999,
            "internal_bypass": True,
        }
    else:
        quota_info = enforce_free_quota(request, feature="scan", user_id=uid, lang=L)

    pro = bool(quota_info.get("isPro", False))

    if (not pro) and int(quota_info.get("left", 0) or 0) <= 0 and int(quota_info.get("used", 0) or 0) >= int(quota_info.get("freeLimit", DAILY_FREE_LIMIT) or DAILY_FREE_LIMIT):
        raise HTTPException(
            status_code=429,
            detail={
                "message": tr(L, "quota_exceeded"),
                "quota": {
                    "freeLimit": quota_info.get("freeLimit", DAILY_FREE_LIMIT),
                    "feature": quota_info.get("feature", "scan"),
                    "day": quota_info.get("day"),
                    "used": quota_info.get("used", DAILY_FREE_LIMIT),
                    "left": 0,
                },
            },
        )

    try:
        data = await security_analyze_core({
            "input": target,
            "lang": L,
            "user_id": uid,
            "is_pro": pro,
        })
        data["isPro"] = pro
        data["quota"] = {
            "freeLimit": quota_info.get("freeLimit", DAILY_FREE_LIMIT),
            "feature": quota_info.get("feature", "scan"),
            "day": quota_info.get("day"),
            "used": quota_info.get("used", 0),
            "left": quota_info.get("left", 0),
        }
        data = attach_legacy_fields(data, L)
        data = _attach_ux_risk_blocks(data, L)

        try:
            level = _canonical_level(data.get("level"), data.get("score"))
            verdict_tag = level
            _profile_track_event(
                uid,
                "scamshield_scan",
                object_ref=target,
                meta={
                    "verdict": verdict_tag,
                    "level": data.get("level"),
                    "kind": data.get("kind"),
                    "isPro": pro,
                    "score": data.get("score"),
                },
            )
        except Exception as e:
            print("[profile] scan track error:", e)

        # === NEW: UX blocks for frontend / extension ===
        data["what_can_happen"] = data.get("what_can_happen") or "This interaction may be risky."
        data["worst_case"] = data.get("worst_case") or "You could lose funds if the interaction is malicious."
        data["permissions_summary"] = data.get("permissions_summary") or {
            "can_spend": False,
            "unlimited": False,
            "tokens": [],
            "spend_limit": None,
            "revoke_difficulty": "unknown"
        }

        return _scan_client_safe_response(data)
    except HTTPException:
        raise
    except Exception as e:
        print("[scan] fatal error:", e)
        raise HTTPException(status_code=500, detail=tr(L, "scan_failed"))

# =========================================================
# VOTES
# =========================================================
@app.post("/scan/vote")
def scan_vote(request: Request, payload: ScanVoteIn = Body(...), lang: str | None = None):
    L = get_lang(request, lang)
    require_app_key(request, L)

    raw_obj = payload.obj if payload.obj is not None else payload.input
    obj = _normalize_obj(raw_obj)
    if not obj:
        return {"ok": False, "error": "empty_input"}

    kind = _normalize_kind_for_vote(payload.kind, obj)
    user_id = _vote_user_id(request, payload)
    reporter_name = _vote_reporter_name(payload, user_id)

    vote_str = (payload.vote or "").strip().lower()
    if vote_str in {"scam", "safe"}:
        is_scam = 1 if vote_str == "scam" else 0
    else:
        is_scam = 1 if payload.is_scam else 0

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    conn = _scan_db_connect()
    try:
        cur = conn.cursor()
        existing = cur.execute(
            """
            SELECT id
            FROM scan_votes
            WHERE obj=? AND kind=? AND user_id=?
            LIMIT 1
            """,
            (obj, kind, user_id),
        ).fetchone()

        if existing:
            cur.execute(
                """
                UPDATE scan_votes
                SET is_scam=?, reporter_name=?, updated_at=?
                WHERE id=?
                """,
                (is_scam, reporter_name, now_iso, existing[0]),
            )
        else:
            cur.execute(
                """
                INSERT INTO scan_votes
                  (obj, kind, is_scam, user_id, reporter_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (obj, kind, is_scam, user_id, reporter_name, now_iso, now_iso),
            )
        conn.commit()
    finally:
        conn.close()

    try:
        _profile_track_event(
            user_id,
            "community_vote",
            object_ref=obj,
            meta={
                "kind": kind,
                "vote": "scam" if bool(is_scam) else "safe",
                "reporter": reporter_name,
            },
        )
    except Exception as e:
        print("[profile] vote track error:", e)

    community = _community_snapshot(obj, kind)
    return {
        "ok": True,
        "object": obj,
        "kind": kind,
        "user_id": user_id,
        "is_scam": bool(is_scam),
        "community": community,
    }

@app.get("/scan/stats")
def scan_stats(request: Request, limit: int = 200, lang: str | None = None):
    L = get_lang(request, lang)
    require_app_key(request, L)

    items = _community_top_items(limit=limit, only_scam_first=True)
    out = []
    for it in items:
        checks = int(it["scam_votes"] or 0) + int(it["safe_votes"] or 0)
        out.append(
            {
                "obj": it["obj"],
                "kind": it["kind"],
                "checks": checks,
                "scam_votes": int(it["scam_votes"] or 0),
                "safe_votes": int(it["safe_votes"] or 0),
                "total_users": int(it["total_users"] or 0),
                "community_verdict": it["community_verdict"],
                "last_seen": it["last_seen"],
                "last_reporter": it["last_reporter"],
            }
        )
    return out

@app.get("/community/top-scams")
def community_top_scams(limit: int = 20):
    return {"items": _community_top_items(limit=limit, only_scam_first=True)}

@app.get("/community/stats")
def community_stats(limit: int = 20):
    return {"items": _community_top_items(limit=limit, only_scam_first=True)}

@app.get("/community/top")
def community_top(limit: int = 20):
    return {"items": _community_top_items(limit=limit, only_scam_first=True)}

# =========================================================
# IMMUNITY (community) + /immunity/top
# =========================================================
@app.get("/immunity")
def immunity_get(
    request: Request,
    input: str = Query(...),
    kind: str | None = None,
    lang: str | None = None
):
    L = get_lang(request, lang)
    data = _community_immunity_compute(input, kind)

    v = data.get("community_verdict")
    if v == "safe":
        data["community_verdict_text"] = tr(L, "safe")
    elif v == "scam":
        data["community_verdict_text"] = tr(L, "danger")
    elif v == "mixed":
        data["community_verdict_text"] = tr(L, "suspicious")
    else:
        data["community_verdict_text"] = "—"

    data["lang"] = L
    return data

@app.get("/immunity/top")
def immunity_top(request: Request, limit: int = 50, lang: str | None = None):
    L = get_lang(request, lang)
    require_app_key(request, L)

    items = _community_top_items(limit=limit, only_scam_first=True)
    out = []
    for it in items:
        total_users = int(it["total_users"] or 0)
        scam_votes = int(it["scam_votes"] or 0)
        safe_votes = int(it["safe_votes"] or 0)
        immunity_score = int(round((safe_votes / total_users) * 100)) if total_users else 0
        out.append(
            {
                "obj": it["obj"],
                "kind": it["kind"],
                "checks": total_users,
                "scam_votes": scam_votes,
                "safe_votes": safe_votes,
                "immunity_score": immunity_score,
                "community_verdict": it["community_verdict"],
                "last_seen": it["last_seen"],
                "last_reporter": it["last_reporter"],
                "total_users": total_users,
            }
        )
    return {"items": out}

# =========================================================
# /immunity/analyze
# =========================================================
class MarketSnapshot(BaseModel):
    symbol: str
    lastPrice: float | None = None
    priceChangePercent: float | None = None
    quoteVolume: float | None = None
    vol24hProxy: float | None = None
    spreadBps: float | None = None

class UserIntent(BaseModel):
    amountUsdt: float
    horizon: str
    targetPct: float
    maxDrawdownPct: float
    alreadyHolding: bool = False
    reason: str = "STRATEGY"
    userId: str | None = None

class Behavior(BaseModel):
    analyses24h: int = 0

class ImmunityAnalyzeRequest(BaseModel):
    market: MarketSnapshot
    user: UserIntent
    behavior: Behavior | None = None

def _imm_pick_lang(request: Request) -> str:
    acc = (request.headers.get("accept-language") or "").lower()
    return "ru" if ("ru" in acc or acc.startswith("ru")) else "en"

IMMUNITY_I18N = {
    "en": {
        "verdict": {"critical": "❌ REJECTED", "high": "⚠️ HIGH RISK", "medium": "🟡 RISKY", "low": "✅ OK"},
        "reasons": {
            "FOMO_AFTER_PUMP": "Price is up {change24h}% in 24h — common FOMO trap.",
            "TARGET_TOO_HIGH": "Target {target}% looks aggressive for horizon ({horizon}).",
            "DRAWDOWN_MISMATCH": "Volatility (~{vol}%) exceeds your max drawdown ({dd}).",
            "WIDE_SPREAD": "Spread is wide (~{spread_bps} bps) — execution risk.",
            "OVERTRADING_SIGNAL": "Many analyses today ({count}) — risk of impulsive actions.",
            "NARRATIVE_PRESSURE": "Your reason is hype/pressure — manipulation risk increases.",
            "ADD_WHILE_HOT": "Adding while already holding on short horizon can amplify mistakes.",
            "BIG_TICKET": "Large ticket size — consider splitting entries.",
        },
        "plan": {
            "fix_1": "Split entries (2–3 parts) instead of one full buy.",
            "fix_2": "Define invalidation before entry (max loss or time-stop).",
            "now_high": "Do not enter immediately. Wait for confirmation or a pullback.",
            "safer_high": "If you want exposure: start with a very small starter position.",
            "now_med": "If you enter: do it in parts and keep risk tight.",
            "safer_med": "Prefer entry after consolidation (not during spike).",
            "now_low": "Plan looks reasonable if you follow your risk limits.",
            "safer_low": "Avoid changing the plan mid-trade.",
        },
    },
    "ru": {
        "verdict": {"critical": "❌ ОТКЛОНЕНО", "high": "⚠️ ВЫСОКИЙ РИСК", "medium": "🟡 РИСКОВАННО", "low": "✅ НОРМ"},
        "reasons": {
            "FOMO_AFTER_PUMP": "Цена выросла на {change24h}% за 24ч — типичная ловушка FOMO.",
            "TARGET_TOO_HIGH": "Цель {target}% слишком агрессивна для горизонта ({horizon}).",
            "DRAWDOWN_MISMATCH": "Волатильность (~{vol}%) выше твоего max drawdown ({dd}).",
            "WIDE_SPREAD": "Слишком широкий спред (~{spread_bps} б.п.) — риск исполнения.",
            "OVERTRADING_SIGNAL": "Слишком много анализов сегодня ({count}) — риск импульсивных действий.",
            "NARRATIVE_PRESSURE": "Причина — хайп/давление, риск манипуляции выше.",
            "ADD_WHILE_HOT": "Докупка на коротком горизонте может усилить ошибки.",
            "BIG_TICKET": "Крупный объём — лучше входить частями.",
        },
        "plan": {
            "fix_1": "Входи частями (2–3) вместо одной полной покупки.",
            "fix_2": "Определи invalidation до входа (макс. убыток или time-stop).",
            "now_high": "Не входи сразу. Жди подтверждение или откат.",
            "safer_high": "Если хочешь экспозицию — начни с очень маленькой позиции.",
            "now_med": "Если входишь — делай это частями и держи риск жёстко.",
            "safer_med": "Лучше вход после консолидации (не в пике).",
            "now_low": "План выглядит нормально, если не нарушать риск-лимиты.",
            "safer_low": "Не меняй план посреди сделки.",
        },
    },
}

def _imm_clamp(n: float, a: float, b: float) -> float:
    return max(a, min(b, n))

def _imm_level(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 55:
        return "high"
    if score >= 30:
        return "medium"
    return "low"

def _imm_color(level: str) -> str:
    if level == "critical":
        return "#FF6B6B"
    if level == "high":
        return "#ff7b7b"
    if level == "medium":
        return "#FFB547"
    return "#29d37a"

def _imm_uniq(xs: list[str]) -> list[str]:
    out, seen = [], set()
    for x in xs or []:
        s = (x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out

@app.post("/immunity/analyze")
async def immunity_analyze(payload: ImmunityAnalyzeRequest, request: Request):
    L = _imm_pick_lang(request)
    t = IMMUNITY_I18N[L]

    uid = payload.user.userId or _get_user_id(request, None)
    quota_info = enforce_free_quota(request, feature="immunity_analyze", user_id=uid, lang=L)

    reasons = []
    score = 0

    m = payload.market
    u = payload.user
    b = payload.behavior or Behavior()

    change24h = m.priceChangePercent
    vol = m.vol24hProxy
    spread_bps = m.spreadBps

    def add_reason(code: str, sev: int, **fmt):
        txt = t["reasons"][code].format(**fmt)
        reasons.append({"code": code, "text": txt, "severity": sev})

    if isinstance(change24h, (int, float)) and change24h >= 8 and u.horizon in ("1D", "1W"):
        score += 18
        add_reason("FOMO_AFTER_PUMP", 8, change24h=round(change24h, 2))

    horizon_cap = 8 if u.horizon == "1D" else 18 if u.horizon == "1W" else 35 if u.horizon == "1M" else 60
    if isinstance(u.targetPct, (int, float)) and u.targetPct > horizon_cap:
        score += 22
        add_reason("TARGET_TOO_HIGH", 9, target=round(u.targetPct, 2), horizon=u.horizon)

    if isinstance(vol, (int, float)) and isinstance(u.maxDrawdownPct, (int, float)) and u.maxDrawdownPct > 0 and vol > u.maxDrawdownPct:
        score += 16
        add_reason("DRAWDOWN_MISMATCH", 8, vol=round(vol, 2), dd=round(u.maxDrawdownPct, 2))

    if isinstance(spread_bps, (int, float)) and spread_bps >= 25:
        score += 10
        add_reason("WIDE_SPREAD", 6, spread_bps=int(round(spread_bps)))

    if b.analyses24h >= 6:
        score += 12
        add_reason("OVERTRADING_SIGNAL", 7, count=int(b.analyses24h))

    if (u.reason or "").upper() == "HYPE":
        score += 14
        add_reason("NARRATIVE_PRESSURE", 7)

    if u.alreadyHolding and u.horizon in ("1D", "1W"):
        score += 8
        add_reason("ADD_WHILE_HOT", 5)

    if isinstance(u.amountUsdt, (int, float)) and u.amountUsdt >= 5000:
        score += 8
        add_reason("BIG_TICKET", 5)

    score = int(_imm_clamp(score, 0, 100))
    level = _imm_level(score)
    verdict = t["verdict"][level]
    color = _imm_color(level)
    top = sorted(reasons, key=lambda x: x.get("severity", 0), reverse=True)[:3]

    p = t["plan"]
    fixes = [p["fix_1"], p["fix_2"]]
    now = []
    safer = []

    if level in ("critical", "high"):
        now.append(p["now_high"])
        safer.append(p["safer_high"])
    elif level == "medium":
        now.append(p["now_med"])
        safer.append(p["safer_med"])
    else:
        now.append(p["now_low"])
        safer.append(p["safer_low"])

    resp = {
        "score": score,
        "level": level,
        "verdict": verdict,
        "color": color,
        "topReasons": top,
        "plan": {
            "now": _imm_uniq(now),
            "fixes": _imm_uniq(fixes)[:6],
            "safer": _imm_uniq(safer)[:6],
            "reasons": [r["text"] for r in top],
        },
        "quota": {
            "freeLimit": quota_info.get("freeLimit", DAILY_FREE_LIMIT),
            "feature": quota_info.get("feature", "immunity_analyze"),
            "day": quota_info.get("day"),
            "used": quota_info.get("used", 0),
            "left": quota_info.get("left", 0),
        },
        "isPro": bool(quota_info.get("isPro", False)),
    }

    try:
        _profile_track_event(
            uid,
            "immunity_analyze",
            object_ref=(m.symbol or "").strip(),
            meta={
                "symbol": (m.symbol or "").strip(),
                "score": score,
                "level": level,
                "verdict": verdict,
                "targetPct": u.targetPct,
                "horizon": u.horizon,
                "isPro": bool(quota_info.get("isPro", False)),
            },
        )
    except Exception as e:
        print("[profile] immunity track error:", e)

    return resp

# =========================================================
# PUSH SENDER (OneSignal)
# =========================================================
async def send_onesignal_push(title: str, body: str) -> dict:
    if not ONESIGNAL_APP_ID or not ONESIGNAL_API_KEY:
        raise RuntimeError("OneSignal is not configured")

    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "included_segments": ["All"],
        "headings": {"en": title, "ru": title},
        "contents": {"en": body, "ru": body},
        "priority": 10,
    }

    # optional deep-link data, set by caller through task-local style globals
    extra_data = globals().pop("_ONESIGNAL_NEXT_DATA", None)
    if isinstance(extra_data, dict) and extra_data:
        payload["data"] = extra_data

    headers = {
        "Authorization": f"Basic {ONESIGNAL_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=15.0) as cl:
        r = await cl.post(
            "https://onesignal.com/api/v1/notifications",
            json=payload,
            headers=headers,
        )
        print("[onesignal] status =", r.status_code)
        print("[onesignal] body =", r.text)
        r.raise_for_status()
        return r.json()

@app.post("/push/register")
async def push_register(request: Request, payload: dict = Body(...), lang: str | None = None):
    L = get_lang(request, lang)
    require_app_key(request, L)

    token = str(payload.get("expo_token", "")).strip()
    if token.startswith("ExponentPushToken") and len(token) > 30:
        return {"ok": True, "legacy": True, "provider": "onesignal", "ignored": True}
    return {"ok": False, "reason": "bad token"}

async def broadcast_push(title: str, body: str):
    try:
        resp = await send_onesignal_push(title, body)
        return {"ok": True, "provider": "onesignal", "response": resp}
    except Exception as e:
        print("[broadcast_push] onesignal error:", e)
        return {"ok": False, "provider": "onesignal", "error": str(e)}


# =========================================================
# REDDIT SCAM MONITOR (dry-run first)
# =========================================================
REDDIT_SCAM_FEEDS = [
    "https://www.reddit.com/r/CryptoScams/new/.rss",
    "https://www.reddit.com/r/Scams/new/.rss",
]

REDDIT_SEEN_ALERTS = set()
REDDIT_LAST_ALERT: dict[str, float] = {}
REDDIT_DOMAIN_COOLDOWN_SEC = 12 * 60 * 60

REDDIT_URL_RE = re.compile(r'https?://[^\s<>"\)\]]+', re.I)
REDDIT_DOMAIN_RE = re.compile(
    r'\b(?:[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?\.)+(?:com|net|org|io|app|xyz|finance|capital|co|ai|me|site|online|info|biz|top|vip|shop|live|pro|cloud|dev|global|exchange|market|markets|trade|trading|broker|finance)\b',
    re.I,
)

REDDIT_BLOCKED_HOST_PARTS = [
    "reddit.com", "redd.it", "redditmedia.com", "preview.redd.it", "i.redd.it",
    "yahoo.com", "finance.yahoo.com", "youtube.com", "youtu.be", "creativefabrica.com",
]

REDDIT_BLOCKED_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")

def _reddit_host_of(x: str) -> str:
    try:
        u = x if str(x or "").startswith("http") else "http://" + str(x or "")
        return (urlparse(u).hostname or "").lower()
    except Exception:
        return ""

def _reddit_is_bad_target(x: str) -> bool:
    s = str(x or "").lower().strip()
    h = _reddit_host_of(s)
    if not h:
        return True
    if any(part in h for part in REDDIT_BLOCKED_HOST_PARTS):
        return True
    if any(s.split("?")[0].endswith(ext) for ext in REDDIT_BLOCKED_EXT):
        return True
    if len(h.split(".")) < 2:
        return True
    return False

def _reddit_clean_url(u: str) -> str:
    return html.unescape(str(u or "")).strip().rstrip(".,;:!?)]}")


def _reddit_alert_type(title: str, summary: str, target: str) -> str:
    txt = f"{title or ''} {summary or ''} {target or ''}".lower()
    host = _reddit_host_of(target)

    if any(w in txt for w in ["fake usdt", "fake token", "token", "honeypot"]):
        return "fake token"
    if any(w in txt for w in ["seed phrase", "private key", "drain", "drainer", "connect wallet", "approve"]):
        return "wallet drainer"
    if any(w in txt for w in ["broker", "investment", "capital", "wealth", "asset", "trading"]) or any(w in host for w in ["capital", "wealth", "asset", "trade", "broker", "invest"]):
        return "investment scam"
    if any(w in txt for w in ["phishing", "fake", "login", "support", "verify"]):
        return "phishing"
    return "scam report"

def _reddit_push_body(target: str, ctx: dict, alert_type: str) -> str:
    short_target = target if len(target) <= 78 else target[:75] + "..."
    return f"{alert_type}: {short_target} • {ctx.get('score')}/100 • Reddit"


def _reddit_context_score(feed: str, title: str, summary: str, target: str) -> dict:
    feed_l = str(feed or "").lower()
    txt = f"{title or ''} {summary or ''} {target or ''}".lower()

    score = 0
    reasons = []

    if "cryptoscams" in feed_l:
        score += 35
        reasons.append("crypto scam community")

    strong_words = {
        "scam": 22,
        "phishing": 28,
        "fake": 32,
        "stolen": 30,
        "drain": 35,
        "drainer": 35,
        "wallet": 12,
        "usdt": 18,
        "investment": 24,
        "broker": 24,
        "recovery scam": 28,
        "seed phrase": 35,
        "private key": 40,
        "connect wallet": 25,
        "approve": 18,
    }

    for word, points in strong_words.items():
        if word in txt:
            score += points
            reasons.append(word)

    host = _reddit_host_of(target)
    finance_words = ["capital", "wealth", "asset", "gain", "trade", "broker", "invest", "exchange", "bonus", "airdrop", "claim"]
    if any(w in host for w in finance_words):
        score += 25
        reasons.append("finance-like domain")

    if any(w in txt for w in ["metamask", "binance", "trust wallet", "coinbase", "phantom", "ledger", "paypal"]):
        score += 18
        reasons.append("brand mention")

    if any(w in txt for w in ["support", "login", "verify", "account", "security"]):
        score += 12
        reasons.append("login/support pattern")

    if any(w in host for w in ["capital", "wealth", "asset"]) and "cryptoscams" in feed_l:
        score += 10
        reasons.append("crypto investment domain")

    if target.startswith("http://"):
        score += 6
        reasons.append("non-https")

    if score >= 75:
        level = "danger"
    elif score >= 45:
        level = "suspicious"
    else:
        level = "watch"

    return {
        "score": min(100, score),
        "level": level,
        "reasons": reasons[:8],
    }


def _reddit_extract_targets(text: str) -> list[str]:
    text = html.unescape(str(text or ""))
    out: list[str] = []

    for u in REDDIT_URL_RE.findall(text):
        u = _reddit_clean_url(u)
        if not _reddit_is_bad_target(u) and u not in out:
            out.append(u)

    for d in REDDIT_DOMAIN_RE.findall(text):
        d = _reddit_clean_url(str(d).lower())
        if not _reddit_is_bad_target(d) and not any(d in x.lower() for x in out):
            out.append(d)

    return out[:5]

async def _reddit_fetch_feed(url: str) -> list[dict]:
    def _parse():
        d = feedparser.parse(url)
        entries = []
        for e in d.entries[:20]:
            entries.append({
                "feed": url,
                "id": str(e.get("id") or e.get("link") or ""),
                "title": str(e.get("title") or ""),
                "summary": str(e.get("summary") or ""),
                "link": str(e.get("link") or ""),
            })
        return entries

    return await asyncio.to_thread(_parse)

async def _check_reddit_scam_alerts_once(dry_run: bool = True):
    for feed in REDDIT_SCAM_FEEDS:
        try:
            entries = await _reddit_fetch_feed(feed)
        except Exception as e:
            print("[reddit_scam] feed error:", feed, e)
            continue

        for e in entries:
            post_id = e.get("id") or e.get("link") or ""
            title = e.get("title") or ""
            summary = e.get("summary") or ""
            post_link = e.get("link") or ""

            feed_l = str(feed or "").lower()
            title_l = str(title or "").lower()
            summary_l = str(summary or "").lower()
            crypto_feed = "cryptoscams" in feed_l
            strong_scam_words = any(w in (title_l + " " + summary_l) for w in [
                "scam", "phishing", "fake", "stolen", "drain", "drainer", "wallet", "crypto", "usdt", "broker", "investment"
            ])

            if not crypto_feed and not strong_scam_words:
                continue

            targets = _reddit_extract_targets(title + " " + summary)
            if not targets:
                continue

            for target in targets[:2]:
                key = f"{post_id}::{target}"
                if key in REDDIT_SEEN_ALERTS:
                    continue

                REDDIT_SEEN_ALERTS.add(key)

                ctx = _reddit_context_score(feed, title, summary, target)

                print("[reddit_scam][scan]", {
                    "level": ctx.get("level"),
                    "score": ctx.get("score"),
                    "reasons": ctx.get("reasons"),
                    "title": title[:120],
                    "target": target,
                    "post": post_link,
                })

                if dry_run:
                    continue

                if ctx.get("level") not in {"danger", "critical"}:
                    continue

                host = _reddit_host_of(target)
                now_ts = time.time()
                last_ts = float(REDDIT_LAST_ALERT.get(host, 0) or 0)
                if host and now_ts - last_ts < REDDIT_DOMAIN_COOLDOWN_SEC:
                    print("[reddit_scam][skip_cooldown]", {"host": host, "target": target})
                    continue

                alert_type = _reddit_alert_type(title, summary, target)
                title_push = "🚨 Noytrix Scam Alert"
                body_push = _reddit_push_body(target, ctx, alert_type)

                kind_for_db = "url" if str(target).lower().startswith(("http://", "https://")) else (_detect_input_kind(target).get("kind") or "unknown")
                _save_reddit_scam_to_community(target, kind_for_db, post_link, title)

                globals()["_ONESIGNAL_NEXT_DATA"] = {
                    "type": "reddit_scam_alert",
                    "screen": "shield",
                    "input": target,
                    "kind": kind_for_db,
                    "source": "reddit",
                    "reddit_post": post_link,
                    "score": ctx.get("score"),
                    "alert_type": alert_type,
                    "open_url": f"noytrix://shield?input={quote(target, safe='')}&source=reddit",
                }

                await broadcast_push(title_push, body_push)
                if host:
                    REDDIT_LAST_ALERT[host] = now_ts
                print("[reddit_scam][push]", {
                    "level": ctx.get("level"),
                    "score": ctx.get("score"),
                    "target": target,
                    "post": post_link,
                })
                return

async def reddit_scam_monitor_loop():
    await asyncio.sleep(3)
    print("[reddit_scam] started")
    while True:
        try:
            await _check_reddit_scam_alerts_once(dry_run=False)
        except Exception as e:
            print("[reddit_scam] error:", e)
        await asyncio.sleep(10 * 60)


# =========================================================
# PUSH SIGNALS: Security / Whale / Market / Radar
# =========================================================
WATCH_SYMBOLS = ["BTCUSDT"]

PRICE_HISTORY: dict[str, list[tuple[float, float]]] = {}
MARKET_LAST_ALERT: dict[str, float] = {}
WHALE_LAST_ALERT: dict[str, float] = {}
RADAR_LAST_ALERT: dict[str, float] = {}
SECURITY_ALERT_FLAGS = set()
EVENT_ALERT_FLAGS = set()

MARKET_PUSH_DAILY_SENT: dict[str, int] = {}
MARKET_PUSH_DAILY_LIMIT = 2

def _today_utc_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def _market_push_key(symbol: str) -> str:
    return f"{_today_utc_key()}:{str(symbol or '').upper()}"

def _market_push_daily_can_send(symbol: str) -> bool:
    return int(MARKET_PUSH_DAILY_SENT.get(_market_push_key(symbol), 0) or 0) < MARKET_PUSH_DAILY_LIMIT

def _market_push_daily_mark_sent(symbol: str) -> None:
    k = _market_push_key(symbol)
    MARKET_PUSH_DAILY_SENT[k] = int(MARKET_PUSH_DAILY_SENT.get(k, 0) or 0) + 1

MARKET_CFG = {
    "BTCUSDT": {"move_pct_30m": 2.8, "cooldown_sec": 4 * 60 * 60},
    "ETHUSDT": {"move_pct_30m": 3.2, "cooldown_sec": 4 * 60 * 60},
}
WHALE_CFG = {
    "BTCUSDT": {"min_notional_usd": 3_000_000.0, "cooldown_sec": 6 * 60 * 60},
    "ETHUSDT": {"min_notional_usd": 1_500_000.0, "cooldown_sec": 6 * 60 * 60},
}
RADAR_CFG = {
    "BTCUSDT": {"range_pct_60m_max": 1.0, "cooldown_sec": 8 * 60 * 60},
    "ETHUSDT": {"range_pct_60m_max": 1.2, "cooldown_sec": 8 * 60 * 60},
}

def _parse_iso_dt_utc(raw: str | None) -> datetime | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        dt_obj = datetime.fromisoformat(s)
        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
        else:
            dt_obj = dt_obj.astimezone(timezone.utc)
        return dt_obj
    except Exception:
        return None

async def _fetch_binance_price(symbol: str) -> float:
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    async with httpx.AsyncClient(timeout=10.0) as cl:
        r = await cl.get(url)
        r.raise_for_status()
        return float(r.json()["price"])

async def _fetch_binance_agg_trades(symbol: str, limit: int = 300) -> list[dict]:
    url = "https://api.binance.com/api/v3/aggTrades"
    async with httpx.AsyncClient(timeout=10.0) as cl:
        r = await cl.get(url, params={"symbol": symbol, "limit": limit})
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []

def _store_price_point(symbol: str, ts: float, price: float) -> None:
    arr = PRICE_HISTORY.setdefault(symbol, [])
    arr.append((ts, price))
    cutoff = ts - 70 * 60
    PRICE_HISTORY[symbol] = [(t, p) for (t, p) in arr if t >= cutoff]

def _get_price_before(symbol: str, now_ts: float, seconds_ago: int) -> float | None:
    arr = PRICE_HISTORY.get(symbol, [])
    if not arr:
        return None
    target = now_ts - seconds_ago
    candidates = [p for (t, p) in arr if t <= target]
    if not candidates:
        return None
    return candidates[-1]

def _get_range_pct(symbol: str, now_ts: float, seconds_back: int) -> float | None:
    arr = PRICE_HISTORY.get(symbol, [])
    if not arr:
        return None
    xs = [p for (t, p) in arr if t >= now_ts - seconds_back]
    if len(xs) < 4:
        return None
    lo = min(xs)
    hi = max(xs)
    if lo <= 0:
        return None
    return ((hi - lo) / lo) * 100.0

def _fmt_usd_compact(x: float) -> str:
    v = float(x or 0)
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.1f}K"
    return f"${v:.0f}"

def _symbol_to_coin(symbol: str) -> str:
    return str(symbol or "").replace("USDT", "").strip().upper()

async def _check_market_alerts_once():
    now_ts = time.time()

    for symbol in WATCH_SYMBOLS:
        try:
            price = await _fetch_binance_price(symbol)
        except Exception as e:
            print("[market] fetch error", symbol, "->", e)
            continue

        _store_price_point(symbol, now_ts, price)
        base_30m = _get_price_before(symbol, now_ts, 30 * 60)
        if base_30m is None or base_30m <= 0:
            continue

        pct_30m = ((price - base_30m) / base_30m) * 100.0
        cfg = MARKET_CFG.get(symbol, {})
        threshold = float(cfg.get("move_pct_30m", 3.0))
        cooldown_sec = int(cfg.get("cooldown_sec", 4 * 60 * 60))
        last = float(MARKET_LAST_ALERT.get(symbol, 0) or 0)

        if now_ts - last < cooldown_sec:
            continue
        if abs(pct_30m) < threshold:
            continue

        coin = _symbol_to_coin(symbol)
        direction = "рост" if pct_30m > 0 else "падение"
        title = f"📊 Market Signal • {coin}"
        body = f"{coin}: аномальное {direction} {pct_30m:+.2f}% за 30 минут."

        if not _market_push_daily_can_send(symbol):
            print(f"[market] skip daily limit {symbol}")
            continue

        try:
            await broadcast_push(title, body)
            _market_push_daily_mark_sent(symbol)
            MARKET_LAST_ALERT[symbol] = now_ts
            print(f"[market] sent {symbol} pct_30m={pct_30m:.2f}")
        except Exception as e:
            print("[market] send error:", e)

async def _check_whale_alerts_once():
    now_ts = time.time()
    now_ms = int(now_ts * 1000)

    for symbol in WATCH_SYMBOLS:
        cfg = WHALE_CFG.get(symbol, {})
        min_notional = float(cfg.get("min_notional_usd", 2_000_000.0))
        cooldown_sec = int(cfg.get("cooldown_sec", 6 * 60 * 60))
        last = float(WHALE_LAST_ALERT.get(symbol, 0) or 0)

        if now_ts - last < cooldown_sec:
            continue

        try:
            trades = await _fetch_binance_agg_trades(symbol, limit=300)
        except Exception as e:
            print("[whale] fetch error", symbol, "->", e)
            continue

        best_trade = None
        best_notional = 0.0
        for trd in trades:
            try:
                ts_ms = int(trd.get("T") or 0)
                if ts_ms <= 0 or ts_ms < now_ms - 10 * 60 * 1000:
                    continue
                price = float(trd.get("p") or 0)
                qty = float(trd.get("q") or 0)
                notional = price * qty
                if notional > best_notional:
                    best_notional = notional
                    best_trade = trd
            except Exception:
                continue

        if not best_trade or best_notional < min_notional:
            continue

        coin = _symbol_to_coin(symbol)
        title = f"🐋 Whale Alert • {coin}"
        body = f"Крупная сделка по {coin} на Binance: {_fmt_usd_compact(best_notional)}."

        if not _market_push_daily_can_send(symbol):
            print(f"[whale] skip daily limit {symbol}")
            continue

        try:
            await broadcast_push(title, body)
            _market_push_daily_mark_sent(symbol)
            WHALE_LAST_ALERT[symbol] = now_ts
            print(f"[whale] sent {symbol} notional={best_notional:.2f}")
        except Exception as e:
            print("[whale] send error:", e)

async def _check_radar_alerts_once():
    now_ts = time.time()

    for symbol in WATCH_SYMBOLS:
        cfg = RADAR_CFG.get(symbol, {})
        max_range = float(cfg.get("range_pct_60m_max", 1.0))
        cooldown_sec = int(cfg.get("cooldown_sec", 8 * 60 * 60))
        last = float(RADAR_LAST_ALERT.get(symbol, 0) or 0)

        if now_ts - last < cooldown_sec:
            continue

        arr = PRICE_HISTORY.get(symbol, [])
        if len(arr) < 8:
            continue

        range_60m = _get_range_pct(symbol, now_ts, 60 * 60)
        if range_60m is None or range_60m > max_range:
            continue

        base_30m = _get_price_before(symbol, now_ts, 30 * 60)
        current = arr[-1][1] if arr else None
        if base_30m is None or current is None or base_30m <= 0:
            continue

        pct_30m = abs(((current - base_30m) / base_30m) * 100.0)
        if pct_30m > 1.0:
            continue

        coin = _symbol_to_coin(symbol)
        title = f"📡 Radar • {coin}"
        body = f"{coin}: сжатие волатильности за 60 минут. Возможен сильный импульс."

        if not _market_push_daily_can_send(symbol):
            print(f"[radar] skip daily limit {symbol}")
            continue

        try:
            await broadcast_push(title, body)
            _market_push_daily_mark_sent(symbol)
            RADAR_LAST_ALERT[symbol] = now_ts
            print(f"[radar] sent {symbol} range_60m={range_60m:.3f}%")
        except Exception as e:
            print("[radar] send error:", e)

async def _check_security_alerts_once():
    now = datetime.now(timezone.utc)
    try:
        items = _community_top_items(limit=30, only_scam_first=True)
    except Exception as e:
        print("[security] top items error:", e)
        return

    if not items:
        return

    for it in items:
        try:
            if str(it.get("community_verdict") or "").lower() != "scam":
                continue

            scam_votes = int(it.get("scam_votes") or 0)
            safe_votes = int(it.get("safe_votes") or 0)
            if scam_votes < 3 or scam_votes <= safe_votes:
                continue

            last_seen_raw = it.get("last_seen")
            last_seen_dt = _parse_iso_dt_utc(last_seen_raw)
            if not last_seen_dt:
                continue

            age_min = (now - last_seen_dt).total_seconds() / 60.0
            if age_min < 0 or age_min > 25:
                continue

            obj = str(it.get("obj") or "").strip()
            kind = str(it.get("kind") or "object").strip()
            if not obj:
                continue

            key = f"{obj}::{kind}::{last_seen_raw}"
            if key in SECURITY_ALERT_FLAGS:
                continue

            short_obj = obj if len(obj) <= 80 else (obj[:77] + "...")
            if kind == "url":
                body = f"Подозрительный сайт отмечен сообществом • {scam_votes} scam votes."
            elif kind in {"contract", "wallet", "token"}:
                body = f"Риск по контракту/токену повышен • {scam_votes} scam votes."
            else:
                body = f"Объект помечен как опасный • {scam_votes} scam votes."

            title = "🛡 Security Alert"
            await broadcast_push(title, f"{body} {short_obj}")
            SECURITY_ALERT_FLAGS.add(key)
            print(f"[security] sent key={key}")
            break
        except Exception as e:
            print("[security] processing error:", e)

async def market_signals_loop():
    await asyncio.sleep(10)
    print("[market_signals] started")
    while True:
        try:
            await _check_market_alerts_once()
            await _check_whale_alerts_once()
            await _check_radar_alerts_once()
        except Exception as e:
            print("[market_signals] error:", e)
        await asyncio.sleep(5 * 60)

async def security_alerts_loop():
    await asyncio.sleep(15)
    print("[security_alerts] started")
    while True:
        try:
            await _check_security_alerts_once()
        except Exception as e:
            print("[security_alerts] error:", e)
        await asyncio.sleep(5 * 60)
# =========================================================
# STARTUP
# =========================================================
@app.on_event("startup")
async def startup_event():
    print("[startup] Noytrix backend started")

    try:
        asyncio.create_task(market_signals_loop())
        asyncio.create_task(security_alerts_loop())
        asyncio.create_task(reddit_scam_monitor_loop())
        if str(os.getenv("NOYTRIX_THREAT_COLLECTORS", "1")).strip().lower() not in {"0", "false", "no", "off"}:
            asyncio.create_task(autonomous_collector_loop())
        init_threat_memory()
        try:
            conn = _cache_connect()
            conn.close()
            print("[startup] ai explanation cache ready")
        except Exception as e:
            print("[startup] ai explanation cache init failed:", e)
        print("[startup] background loops started")
    except Exception as e:
        print("[startup] loop error:", e)


# =========================================================
# HEALTH / ROOT
# =========================================================
@app.get("/")
def root():
    return {
        "ok": True,
        "service": "Noytrix API",
        "version": "production",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
    }


# =========================================================
# EVENTS / NEWS (ALIAS SUPPORT)
# =========================================================
@app.get("/events")
@app.get("/api/events")
async def events_alias(
    d1: str | None = Query(None, alias="from"),
    d2: str | None = Query(None, alias="to"),
    types: str | None = Query(None),
    impact: str | None = Query(None),
):
    for route in calendar_router.routes:
        if getattr(route, "path", "") == "/calendar/events":
            return await route.endpoint(d1=d1, d2=d2, types=types, impact=impact)
    return {"items": [], "lang": "en"}



@app.get("/news")
@app.get("/api/news")
def news_alias(request: Request, lang: str | None = None):
    L = get_lang(request, lang)

    try:
        items = load_news()  # твоя функция загрузки новостей
    except Exception as e:
        print("[news] error:", e)
        items = []

    return {
        "items": items,
        "lang": L,
    }


# =========================================================
# PROFILE API (BASIC)
# =========================================================
@app.get("/profile/overview")
def profile_overview(userId: str | None = None, lang: str | None = "ru"):
    uid = userId or "guest"
    st = _profile_build_stats(uid)
    achievements = _profile_achievement_texts(_profile_build_achievements(uid), (lang or "ru").lower())
    return {
        "ok": True,
        "user": uid,
        **st,
        "proAccess": {
            "isPro": str(st.get("identity", {}).get("plan") or "").lower() == "pro"
        },
        "achievements": achievements,
    }


@app.get("/profile/stats")
def profile_stats(userId: str | None = None):
    uid = userId or "guest"
    st = _profile_build_stats(uid)
    trust = st.get("trust", {})
    trading = st.get("tradingPerformance", {})
    return {
        "ok": True,
        "user": uid,
        "scans": trust.get("scamScans", 0),
        "trades": trading.get("setupsAnalyzed", 0),
        "winrate": trading.get("acceptanceRate", 0),
        "pnl": 0,
        **st,
    }


@app.get("/profile/activity")
def profile_activity(userId: str | None = None, lang: str | None = "ru"):
    uid = userId or "guest"
    st = _profile_build_stats(uid)
    achievements = _profile_achievement_texts(_profile_build_achievements(uid), (lang or "ru").lower())
    return {
        "ok": True,
        "user": uid,
        "history": st.get("recent", []),
        "activity": st.get("activity", {}),
        "achievements": achievements,
    }


# =========================================================
# FINAL FIXES / SAFETY WRAPPER
# =========================================================
@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        print("[FATAL ERROR]", str(e))
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "internal_server_error",
                "message": str(e),
            },
        )


# =========================================================
# IMPORTANT FIX (ТВОЯ КРИТИЧЕСКАЯ ОШИБКА)
# =========================================================
# В предыдущем коде у тебя было:
# return outasync def _scan_ticker(...)
# это ломало весь backend

# ЗДЕСЬ МЫ УЖЕ ИСПРАВИЛИ:
# функция _scan_ticker начинается с новой строки
# поэтому сервер теперь будет нормально запускаться


print("🚀 Noytrix backend fully loaded")        

async def _check_tronscan(address: str):
    try:
        import requests
        r = requests.get(f"https://apilist.tronscan.org/api/account?address={address}", timeout=8)
        data = r.json()
        if not data:
            return _mk_source("tronscan", "no_data")
        return _mk_source("tronscan", "clean", details=data)
    except:
        return _mk_source("tronscan", "error")


async def _check_btc(address: str):
    try:
        import requests
        r = requests.get(f"https://api.blockchair.com/bitcoin/dashboards/address/{address}", timeout=8)
        data = r.json() if r.text else {}

        ctx = data.get("context") or {}
        code = int(ctx.get("code") or r.status_code or 0)

        if code == 430 or r.status_code == 429:
            return _mk_source("blockchair", "quota", details=data)

        if r.status_code >= 500:
            return _mk_source("blockchair", "error", details=data)

        if "data" not in data or not data.get("data"):
            return _mk_source("blockchair", "no_data", details=data)

        return _mk_source(
            "blockchair",
            "clean",
            details=data,
            evidence=[{"code": "btc_address_found", "severity": 0, "text": "Bitcoin address found on Blockchair."}],
        )
    except Exception as e:
        return _mk_source("blockchair", "error", details={"error": str(e), "address": address})


async def _check_ton(address: str):
    try:
        import requests
        r = requests.get(f"https://tonapi.io/v2/accounts/{address}", timeout=8)
        data = r.json() if r.text else {}

        if r.status_code == 429:
            return _mk_source("tonapi", "quota", details=data)
        if r.status_code >= 500:
            return _mk_source("tonapi", "error", details=data)
        if "balance" not in data:
            return _mk_source("tonapi", "no_data", details=data)

        if bool(data.get("is_scam")):
            return _mk_source(
                "tonapi",
                "malicious",
                verdict="danger",
                details=data,
                evidence=[{"code": "ton_scam_flag", "severity": 45, "text": "TON API flagged this address as scam."}],
            )

        ev = []
        if bool(data.get("is_suspended")):
            ev.append({"code": "ton_suspended", "severity": 24, "text": "TON account is suspended."})
        if str(data.get("status") or "").strip().lower() in {"frozen", "blocked"}:
            ev.append({"code": "ton_blocked_status", "severity": 26, "text": "TON account has a blocked/frozen status."})

        status = "clean" if not ev else "no_data"
        verdict = "clean" if not ev else "unknown"
        return _mk_source("tonapi", status, verdict=verdict, details=data, evidence=ev)
    except Exception as e:
        return _mk_source("tonapi", "error", details={"error": str(e), "address": address})


async def _check_solana(address: str):
    try:
        import requests
        headers = {"accept": "application/json", "user-agent": "Noytrix/1.0"}
        r = requests.get(f"https://public-api.solscan.io/account/{address}", headers=headers, timeout=8)

        if r.status_code == 429:
            return _mk_source("solscan", "quota", details={"status_code": 429, "address": address})
        if r.status_code >= 500:
            return _mk_source("solscan", "error", details={"status_code": r.status_code, "address": address})
        if r.status_code == 404:
            return _mk_source("solscan", "no_data", details={"status_code": 404, "address": address})
        if r.status_code != 200:
            return _mk_source("solscan", "no_data", details={"status_code": r.status_code, "address": address})

        data = r.json() if r.text else {}
        if not data:
            return _mk_source("solscan", "no_data", details={"address": address})

        return _mk_source(
            "solscan",
            "clean",
            details=data,
            evidence=[{"code": "sol_account_found", "severity": 0, "text": "Solana account found on Solscan."}],
        )
    except Exception as e:
        return _mk_source("solscan", "error", details={"error": str(e), "address": address})

# =========================
# Mobile Trading lead request
# =========================

@app.post("/api/contact")
async def api_contact(payload: dict = Body(...)):
    import json, datetime, pathlib, smtplib, os
    from email.message import EmailMessage

    to_email = "noytrixapp@gmail.com"

    name = str(payload.get("name") or "").strip()
    email = str(payload.get("email") or "").strip()
    note = str(payload.get("note") or "").strip()
    product = str(payload.get("product") or "Noytrix Trading Center").strip()
    source = str(payload.get("source") or "mobile_app").strip()

    if not name or not email:
        raise HTTPException(status_code=400, detail="Missing name or contact")

    row = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "to": to_email,
        "name": name,
        "email": email,
        "note": note,
        "product": product,
        "source": source,
    }

    path = pathlib.Path("/root/backend/data/leads.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    smtp_user = os.getenv("NOYTRIX_SMTP_USER") or os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("NOYTRIX_SMTP_PASS") or os.getenv("SMTP_PASS", "")

    if smtp_user and smtp_pass:
        msg = EmailMessage()
        msg["Subject"] = "New Noytrix Trading Center request"
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg["Reply-To"] = email
        msg.set_content(f"""New Noytrix request

Product: {product}
Source: {source}

Name: {name}
Contact: {email}

Message:
{note}
""")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
            smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)

    return {"ok": True, "saved": True, "emailSent": bool(smtp_user and smtp_pass)}
