// app/immunity.js
// Premium Immunity screen
// Rebuilt clean version
// No Android Alert
// Uses showAppAlert()
// Supports Binance pairs, FREE quota, PRO unlimited, analysis, facts, share image

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Pressable,
  Modal,
  ActivityIndicator,
  Platform,
  Share,
  Linking,
  InteractionManager,
} from "react-native";
import { Stack, useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { BlurView } from "expo-blur";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Ionicons } from "@expo/vector-icons";
import { useTranslation } from "react-i18next";
import { WebView } from "react-native-webview";
import * as Clipboard from "expo-clipboard";
import ViewShot, { captureRef } from "react-native-view-shot";
import * as FileSystem from "expo-file-system";
import * as Sharing from "expo-sharing";

import { showAppAlert } from "./lib/appAlert";
import { logEvent } from "./lib/analytics";

const BINANCE = "https://api.binance.com";
const CG = "https://api.coingecko.com/api/v3";
const NOYTRIX_API = "https://noytrix.com";

const AUTH_KEY = "auth_state_v1";
const INSTALL_UID_KEY = "noytrix.installUserId";

const GRAD = {
  start: "#06080f",
  mid: "#0a1233",
  end: "#0b1c4f",
};

const T = {
  text: "#eef2ff",
  dim: "#A8B4CF",
  soft: "#A8B4CF",
  logo: "#ffb020",
  accent: "#ffb020",
  accentText: "#0b1220",
  good: "#29D37A",
  bad: "#FF6B6B",
  warn: "#FFB84D",
  acc: "#66B3FF",
  border: "rgba(255,255,255,0.10)",
  borderSoft: "rgba(255,255,255,0.07)",
  glass: "rgba(255,255,255,0.035)",
};

const K = {
  analysisHistory: "immunity.analysisHistory",
};

const STATS = {
  shieldCount: "stats.shield.count.v1",
};

const HISTORY_LIMIT = 50;
const FREE_LIMIT = 4;

const PRO_KEYS = [
  "pro.isPro",
  "iap.isPro",
  "user.isPro",
  "isPro",
  "pro.active",
  "noytrix_pro_flag",
];

function normalizeLang(value) {
  const s = String(value || "en").toLowerCase();
  if (s.startsWith("ru")) return "ru";
  if (s.startsWith("uk") || s.startsWith("ua")) return "uk";
  return "en";
}

function pickLang(lang, ru, en, uk) {
  const normalized = normalizeLang(lang);
  if (normalized === "ru") return ru ?? en ?? uk ?? "";
  if (normalized === "uk") return uk ?? en ?? ru ?? "";
  return en ?? ru ?? uk ?? "";
}

function clamp(x, a, b) {
  return Math.max(a, Math.min(b, x));
}

function num(v, d = 0) {
  const x =
    typeof v === "number"
      ? v
      : parseFloat(String(v ?? "").replace(/[^0-9.\-]/g, ""));
  return Number.isFinite(x) ? x : d;
}

function pct(x) {
  const v = num(x, NaN);
  if (!Number.isFinite(v)) return "-";
  const s = v >= 0 ? "+" : "";
  return `${s}${v.toFixed(2)}%`;
}

function fmtPrice(x) {
  const v = num(x, NaN);
  if (!Number.isFinite(v)) return "-";
  if (v >= 1000) return "$" + v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (v >= 1) return "$" + v.toFixed(2);
  if (v >= 0.1) return "$" + v.toFixed(3);
  if (v >= 0.01) return "$" + v.toFixed(4);
  if (v >= 0.001) return "$" + v.toFixed(5);
  return "$" + v.toFixed(6);
}

function fmtNum(x) {
  const v = num(x, NaN);
  if (!Number.isFinite(v)) return "-";
  if (Math.abs(v) >= 1_000_000_000) return (v / 1_000_000_000).toFixed(2) + "B";
  if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toFixed(2) + "M";
  if (Math.abs(v) >= 1_000) return (v / 1_000).toFixed(2) + "K";
  return v.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function scoreToLevel(score) {
  const s = Number(score) || 0;
  if (s >= 80) return "critical";
  if (s >= 60) return "high";
  if (s >= 35) return "medium";
  return "low";
}

function verdictLabel(level, lang = "en") {
  const l = String(level || "").toLowerCase();

  const ru = {
    low: "Низкий риск",
    medium: "Средний риск",
    high: "Высокий риск",
    critical: "Критический риск",
  };

  const en = {
    low: "Low risk",
    medium: "Medium risk",
    high: "High risk",
    critical: "Critical risk",
  };
  const uk = {
    low: "Низький ризик",
    medium: "Середній ризик",
    high: "Високий ризик",
    critical: "Критичний ризик",
  };

  return pickLang(lang, ru[l] || "Риск", en[l] || "Risk", uk[l] || "Ризик");
}

function levelColor(level) {
  const l = String(level || "").toLowerCase();
  if (l === "critical" || l === "high") return T.bad;
  if (l === "medium") return T.warn;
  return T.good;
}

function hasPunycode(url) {
  return String(url || "").toLowerCase().includes("xn--");
}

function isProbablyUrl(value) {
  return /^https?:\/\//i.test(String(value || "").trim());
}

async function safeOpenUrl(url) {
  const u = String(url || "").trim();
  if (!isProbablyUrl(u)) return;

  try {
    const ok = await Linking.canOpenURL(u);
    if (ok) await Linking.openURL(u);
  } catch {}
}

function isJunkFiatLikeBaseAsset(base) {
  const b = String(base || "").toUpperCase();

  const bad = new Set([
    "USDC",
    "FDUSD",
    "TUSD",
    "USDP",
    "DAI",
    "EUR",
    "TRY",
    "BRL",
    "GBP",
    "AUD",
    "BIDR",
    "AEUR",
    "EURI",
    "PAXG",
    "WBTC",
    "WETH",
  ]);

  return bad.has(b);
}

function getLocalizedField(obj, baseKey, lang, fallback = "") {
  if (!obj || typeof obj !== "object") return fallback;

  const localizedKey = `${baseKey}_localized`;
  const ruKey = `${baseKey}_ru`;
  const enKey = `${baseKey}_en`;

  const localizedVal = obj?.[localizedKey];
  if (typeof localizedVal === "string" && localizedVal.trim()) return localizedVal.trim();

  const ruVal = obj?.[ruKey];
  const enVal = obj?.[enKey];

  if (String(lang || "en").toLowerCase().startsWith("ru")) {
    if (typeof ruVal === "string" && ruVal.trim()) return ruVal.trim();
    if (typeof enVal === "string" && enVal.trim()) return enVal.trim();
  } else {
    if (typeof enVal === "string" && enVal.trim()) return enVal.trim();
    if (typeof ruVal === "string" && ruVal.trim()) return ruVal.trim();
  }

  const plainVal = obj?.[baseKey];
  if (typeof plainVal === "string" && plainVal.trim()) return plainVal.trim();

  return fallback;
}

function getLocalizedTextValue(value, lang) {
  if (value == null) return "";
  if (typeof value === "string") return value.trim();

  if (typeof value === "object") {
    const localized =
      getLocalizedField(value, "text", lang) ||
      getLocalizedField(value, "label", lang) ||
      getLocalizedField(value, "title", lang) ||
      getLocalizedField(value, "message", lang) ||
      getLocalizedField(value, "value", lang);

    if (localized) return localized;

    const directRu = value?.ru;
    const directEn = value?.en;

    if (String(lang || "en").toLowerCase().startsWith("ru")) {
      if (typeof directRu === "string" && directRu.trim()) return directRu.trim();
      if (typeof directEn === "string" && directEn.trim()) return directEn.trim();
    } else {
      if (typeof directEn === "string" && directEn.trim()) return directEn.trim();
      if (typeof directRu === "string" && directRu.trim()) return directRu.trim();
    }
  }

  return "";
}

function explainBackendMessage(raw, lang) {
  const s = String(raw || "").toLowerCase();

  if (s.includes("429") || s.includes("quota") || s.includes("limit")) {
    return pickLang(
      lang,
      "FREE лимит на сегодня использован. PRO снимает ограничение.",
      "Your free daily analyses are already used up. PRO removes this limit."
    );
  }

  if (s.includes("network request failed") || s.includes("failed to fetch") || s.includes("fetch")) {
    return pickLang(
      lang,
      "Не удалось подключиться к серверу. Проверь интернет.",
      "We could not reach the server. Check your connection and try again."
    );
  }

  if (s.includes("timeout") || s.includes("aborted")) {
    return pickLang(
      lang,
      "Сервер слишком долго отвечает. Попробуй ещё раз.",
      "The server took too long to respond. Try again."
    );
  }

  return pickLang(
    lang,
    "Анализ сейчас не удалось завершить. Попробуй ещё раз.",
    "The analysis could not be completed right now. Try again."
  );
}

function planCodeLabel(code, lang) {
  const map = {
    SPLIT_ENTRIES: pickLang(lang, "Раздели вход на 2-3 части", "Split the entry into 2-3 parts"),
    DEFINE_INVALIDATION: pickLang(lang, "Определи точку отмены сделки", "Define invalidation before entry"),
    WAIT_CONFIRMATION: pickLang(lang, "Жди подтверждение перед входом", "Wait for confirmation before entering"),
    START_SMALL: pickLang(lang, "Начни с меньшей позиции", "Start with a smaller position"),
    ENTER_IN_PARTS: pickLang(lang, "Входи частями", "Enter in parts, not all at once"),
    AFTER_CONSOLIDATION: pickLang(lang, "Лучше после консолидации", "Prefer entering after consolidation"),
    REASONABLE_IF_LIMITS: pickLang(lang, "Нормально, если держишь риск-лимиты", "Reasonable if you keep risk limits"),
    DONT_CHANGE_MID: pickLang(lang, "Не меняй план по ходу сделки", "Do not change the plan mid-trade"),
    AVOID_AFTER_PUMP: pickLang(lang, "Не входи агрессивно после пампа", "Avoid aggressive entry after a pump"),
    REDUCE_TARGET_OR_EXTEND: pickLang(lang, "Снизь цель или увеличь горизонт", "Reduce the target or extend the horizon"),
    MISMATCH_SIZE_OR_DD: pickLang(lang, "Подгони размер позиции под DD", "Match position size to your DD"),
    FOMO_AFTER_PUMP: pickLang(lang, "Есть риск FOMO после роста", "There is FOMO risk after a strong pump"),
    TARGET_TOO_HIGH: pickLang(lang, "Цель слишком высокая для горизонта", "Target is too high for this horizon"),
    DRAWDOWN_MISMATCH: pickLang(lang, "Обычный шум рынка выше твоего DD", "Normal market noise is above your DD"),
    WIDE_SPREAD: pickLang(lang, "Слишком широкий спред", "Spread is too wide"),
    OVERTRADING_SIGNAL: pickLang(lang, "Есть признаки овертрейдинга", "There are signs of overtrading"),
    NARRATIVE_PRESSURE: pickLang(lang, "Решение похоже на хайп", "Decision is driven by hype"),
    ADD_WHILE_HOT: pickLang(lang, "Добавление к уже горячему активу", "Adding to an already hot asset"),
    BIG_TICKET: pickLang(lang, "Большой размер позиции", "Position size is large"),
  };

  return map[String(code || "").trim()] || String(code || "").replace(/_/g, " ");
}

function localizePlanItem(item, lang) {
  if (!item) return null;

  if (typeof item === "string") {
    const code = item.trim();
    return code ? { code, text: planCodeLabel(code, lang), params: {} } : null;
  }

  if (typeof item === "object") {
    const code = String(item.code || "").trim();
    const directText =
      getLocalizedField(item, "text", lang) ||
      getLocalizedField(item, "title", lang) ||
      getLocalizedField(item, "label", lang);

    if (!code && !directText) return null;

    return {
      ...item,
      code: code || "",
      text: directText || planCodeLabel(code, lang),
      params: item.params && typeof item.params === "object" ? item.params : {},
    };
  }

  return null;
}

function localizePlan(plan, lang) {
  const p = plan && typeof plan === "object" ? plan : {};

  const norm = (arr) =>
    (Array.isArray(arr) ? arr : [])
      .map((x) => localizePlanItem(x, lang))
      .filter(Boolean);

  return {
    now: norm(p.now),
    fixes: norm(p.fixes),
    safer: norm(p.safer),
    reasons: norm(p.reasons),
    probability: getLocalizedField(p, "probability", lang) || p.probability || null,
    pro: p.pro || null,
  };
}

function localizeScenarioItem(item, lang) {
  if (!item || typeof item !== "object") return item || null;

  return {
    ...item,
    title: getLocalizedField(item, "title", lang) || item.title || "",
    note: getLocalizedField(item, "note", lang) || item.note || "",
    advice: getLocalizedField(item, "advice", lang) || item.advice || "",
  };
}

function localizeReview10(review, lang) {
  const r = review && typeof review === "object" ? review : null;
  if (!r) return null;

  const normalizeArray = (arr) =>
    (Array.isArray(arr) ? arr : [])
      .map((x) => getLocalizedTextValue(x, lang) || (typeof x === "string" ? x.trim() : ""))
      .filter(Boolean);

  return {
    ...r,
    kind: r.kind || "mixed",
    title: getLocalizedField(r, "title", lang) || r.title || "",
    summary: getLocalizedField(r, "summary", lang) || r.summary || "",
    probability:
      getLocalizedField(r, "probability", lang) ||
      (typeof r.probability === "string"
        ? r.probability
        : r.probability != null
        ? String(r.probability)
        : null),
    why: normalizeArray(r.why),
    doNow: normalizeArray(r.doNow),
    concrete: normalizeArray(r.concrete),
    pros: normalizeArray(r.pros),
    cons: normalizeArray(r.cons),
    fixes: normalizeArray(r.fixes),
  };
}

function normalizeLiveReview(liveReview, lang) {
  const r = liveReview && typeof liveReview === "object" ? liveReview : null;
  if (!r) return null;

  const verdict = String(
    getLocalizedField(r, "verdict", lang) ||
      r.verdict ||
      r.result ||
      r.status ||
      ""
  )
    .toLowerCase()
    .trim();

  const isBad =
    verdict === "bad" ||
    verdict === "wrong" ||
    verdict === "reject" ||
    verdict === "rejected" ||
    verdict === "high" ||
    verdict === "critical";

  const isGood =
    verdict === "good" ||
    verdict === "ok" ||
    verdict === "correct" ||
    verdict === "approved" ||
    verdict === "low";

  const kind = isBad ? "bad" : isGood ? "good" : "mixed";

  const normalizeBullets = (x) => {
    if (!x) return [];
    if (Array.isArray(x)) {
      return x
        .map((a) => getLocalizedTextValue(a, lang) || (typeof a === "string" ? a.trim() : ""))
        .filter(Boolean)
        .slice(0, 8);
    }
    if (typeof x === "string") {
      return x
        .split("\n")
        .map((s) => s.replace(/^[-•\s]+/, "").trim())
        .filter(Boolean)
        .slice(0, 8);
    }
    return [];
  };

  return {
    kind,
    title:
      getLocalizedField(r, "title", lang) ||
      getLocalizedField(r, "headline", lang) ||
      r.title ||
      r.headline ||
      null,
    summary:
      getLocalizedField(r, "summary", lang) ||
      getLocalizedField(r, "text", lang) ||
      getLocalizedField(r, "message", lang) ||
      r.summary ||
      r.text ||
      r.message ||
      null,
    pros: normalizeBullets(r.pros || r.good || r.strengths || r.whatGood || r.ok),
    cons: normalizeBullets(r.cons || r.bad || r.weaknesses || r.whatBad || r.issues || r.risks),
    fixes: normalizeBullets(r.fixes || r.actions || r.nextSteps || r.howToFix),
  };
}

function uniqCodes(arr) {
  const out = [];
  const set = new Set();

  for (const x of arr || []) {
    const k = String(x?.code || "").trim();
    if (!k || set.has(k)) continue;
    set.add(k);
    out.push(x);
  }

  return out;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 12000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, {
      ...(options || {}),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

async function getAuthStateV1() {
  try {
    const raw = await AsyncStorage.getItem(AUTH_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

async function getAccessTokenV1() {
  try {
    const st = await getAuthStateV1();
    return st?.access_token || null;
  } catch {
    return null;
  }
}

function parseJwtPayload(token) {
  try {
    const raw = String(token || "").trim();
    if (!raw || raw.split(".").length < 2) return null;

    const base64 = raw.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);

    if (typeof atob !== "function") return null;

    const json = decodeURIComponent(
      Array.prototype.map
        .call(atob(padded), (c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );

    return JSON.parse(json);
  } catch {
    return null;
  }
}

async function getOrCreateInstallUserId() {
  try {
    const existing = await AsyncStorage.getItem(INSTALL_UID_KEY);
    if (existing && String(existing).trim()) return String(existing).trim();

    const next = `guest_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    await AsyncStorage.setItem(INSTALL_UID_KEY, next);
    return next;
  } catch {
    return `guest_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  }
}

async function getBestKnownUid() {
  try {
    const st = await getAuthStateV1();
    const u = st?.user || null;

    const direct = u?.email || u?.nick || u?.username || u?.login || u?.name || "";

    if (String(direct).trim()) {
      return String(direct).trim().toLowerCase();
    }

    const payload = parseJwtPayload(st?.access_token || "");
    const jwtUid =
      payload?.email ||
      payload?.user_email ||
      payload?.preferred_username ||
      payload?.username ||
      payload?.nick ||
      payload?.name ||
      payload?.sub ||
      "";

    if (String(jwtUid).trim()) {
      return String(jwtUid).trim().toLowerCase();
    }
  } catch {}

  try {
    const installId = await getOrCreateInstallUserId();
    if (installId && String(installId).trim()) return String(installId).trim();
  } catch {}

  return "anonymous";
}

async function apiPost(path, body, lang = "en", extraHeaders = {}) {
  const token = await getAccessTokenV1();
  const userId = await getBestKnownUid();

  const res = await fetchWithTimeout(
    `${NOYTRIX_API}${path}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "Accept-Language": lang,
        "X-Lang": lang,
        "X-Language": lang,
        "X-User-Id": userId,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(extraHeaders || {}),
      },
      body: JSON.stringify(body),
    },
    12000
  );

  const text = await res.text().catch(() => "");
  let json = null;

  try {
    json = text ? JSON.parse(text) : null;
  } catch {}

  if (!res.ok) {
    const msg = (json && (json.detail || json.error || json?.message)) || text || `HTTP ${res.status}`;
    throw new Error(msg);
  }

  return json;
}

function utcDayKeyYYYYMMDD() {
  const d = new Date();
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  return `${yyyy}${mm}${dd}`;
}

const QUOTA_KEY_IMMUNITY = (uid, feature, dayKey) => `quota.${feature}.${uid}.${dayKey}`;

async function getLocalQuota(uid, feature, freeLimit) {
  const dayKey = utcDayKeyYYYYMMDD();
  const key = QUOTA_KEY_IMMUNITY(uid, feature, dayKey);

  try {
    const raw = await AsyncStorage.getItem(key);
    const used = Number(raw || 0) || 0;
    const limit = Number(freeLimit || FREE_LIMIT) || FREE_LIMIT;
    const left = Math.max(0, limit - used);

    return { dayKey, used, limit, left, key };
  } catch {
    const limit = Number(freeLimit || FREE_LIMIT) || FREE_LIMIT;
    return { dayKey, used: 0, limit, left: limit, key };
  }
}

async function incLocalQuota(uid, feature, freeLimit) {
  const q = await getLocalQuota(uid, feature, freeLimit);
  const nextUsed = q.used + 1;

  try {
    await AsyncStorage.setItem(q.key, String(nextUsed));
  } catch {}

  return {
    ...q,
    used: nextUsed,
    left: Math.max(0, q.limit - nextUsed),
  };
}

async function getIsPro() {
  try {
    for (const k of PRO_KEYS) {
      const v = await AsyncStorage.getItem(k);
      if (!v) continue;

      const s = String(v).toLowerCase().trim();
      if (s === "1" || s === "true" || s === "yes" || s === "pro" || s === "active") {
        return true;
      }
    }

    return false;
  } catch {
    return false;
  }
}

async function incShieldCount() {
  try {
    const raw = await AsyncStorage.getItem(STATS.shieldCount);
    const prev = Number(raw) || 0;
    const next = prev + 1;

    await AsyncStorage.setItem(STATS.shieldCount, String(next));
    return next;
  } catch {
    return null;
  }
}

function tradingViewHtml(symbolTv, theme = "dark", interval = "60", locale = "en") {
  return `
<!doctype html>
<html>
  <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <style>
      html, body { margin:0; padding:0; background: transparent; height:100%; overflow:hidden; }
      #tv { width: 100%; height: 100%; }
    </style>
  </head>
  <body>
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div id="tv" style="height:100%;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
        new TradingView.widget({
          "autosize": true,
          "symbol": "${symbolTv}",
          "interval": "${interval}",
          "timezone": "Etc/UTC",
          "theme": "${theme}",
          "style": "1",
          "locale": "${locale}",
          "enable_publishing": false,
          "hide_side_toolbar": false,
          "allow_symbol_change": false,
          "save_image": false,
          "details": true,
          "calendar": false,
          "studies": [],
          "container_id": "tv"
        });
      </script>
    </div>
  </body>
</html>`;
}

function computeRiskEngine({ market, user, behavior }) {
  let score = 0;
  const reasons = [];

  const change24h = Number(market?.priceChangePercent);
  const vol = Number(market?.vol24hProxy);
  const spreadBps = Number(market?.spreadBps);

  const target = Number(user?.targetPct);
  const dd = Number(user?.maxDrawdownPct);

  if (Number.isFinite(vol) && vol > 0) score += clamp(vol * 1.2, 0, 18);
  if (Number.isFinite(spreadBps) && spreadBps > 0) score += clamp(spreadBps / 6, 0, 6);

  if (Number.isFinite(target) && Number.isFinite(dd) && dd > 0) {
    const ratio = target / dd;

    if (ratio >= 1.6) {
      score += 10;
      reasons.push({
        code: "AGGRESSIVE_TARGET_VS_DD",
        params: { ratio: Number(ratio.toFixed(2)) },
        severity: 6,
      });
    } else if (ratio >= 1.2) {
      score += 6;
      reasons.push({
        code: "TARGET_VS_DD_TIGHT",
        params: { ratio: Number(ratio.toFixed(2)) },
        severity: 5,
      });
    }
  }

  if (Number.isFinite(change24h) && change24h >= 8 && ["1D", "1W"].includes(user?.horizon)) {
    score += 18;
    reasons.push({
      code: "FOMO_AFTER_PUMP",
      params: { change24h: Number(change24h) },
      severity: 8,
    });
  }

  const horizonCap =
    user?.horizon === "1D"
      ? 8
      : user?.horizon === "1W"
      ? 18
      : user?.horizon === "1M"
      ? 35
      : 60;

  if (Number.isFinite(target) && target > horizonCap) {
    score += 22;
    reasons.push({
      code: "TARGET_TOO_HIGH",
      params: { target: Number(target), horizon: user?.horizon },
      severity: 9,
    });
  }

  if (Number.isFinite(vol) && Number.isFinite(dd) && dd > 0 && vol > dd) {
    score += 16;
    reasons.push({
      code: "DRAWDOWN_MISMATCH",
      params: { vol: Number(vol), dd: Number(dd) },
      severity: 8,
    });
  }

  if (Number.isFinite(spreadBps) && spreadBps >= 25) {
    score += 10;
    reasons.push({
      code: "WIDE_SPREAD",
      params: { spreadBps: Number(spreadBps) },
      severity: 6,
    });
  }

  if ((behavior?.analyses24h || 0) >= 6) {
    score += 12;
    reasons.push({
      code: "OVERTRADING_SIGNAL",
      params: { analyses24h: Number(behavior.analyses24h || 0) },
      severity: 7,
    });
  }

  if (user?.reason === "HYPE") {
    score += 14;
    reasons.push({
      code: "NARRATIVE_PRESSURE",
      params: {},
      severity: 7,
    });
  }

  if (user?.alreadyHolding && ["1D", "1W"].includes(user?.horizon)) {
    score += 8;
    reasons.push({
      code: "ADD_WHILE_HOT",
      params: {},
      severity: 5,
    });
  }

  const amount = Number(user?.amountUsdt);

  if (Number.isFinite(amount) && amount >= 5000) {
    score += 8;
    reasons.push({
      code: "BIG_TICKET",
      params: { amountUsdt: Number(amount) },
      severity: 5,
    });
  }

  score = clamp(score, 0, 100);

  const level = scoreToLevel(score);

  const topReasons = reasons
    .slice()
    .sort((a, b) => (b.severity || 0) - (a.severity || 0))
    .slice(0, 3);

  const plan = buildPlanCodes({ level, market, user, topReasons });

  return {
    score,
    level,
    verdict: verdictLabel(level),
    color: levelColor(level),
    topReasons,
    plan,
  };
}

function buildPlanCodes({ level, market, user, topReasons }) {
  const change24h = Number(market?.priceChangePercent);
  const vol = Number(market?.vol24hProxy);
  const target = Number(user?.targetPct);
  const dd = Number(user?.maxDrawdownPct);

  const safer = [];
  const fixes = [];
  const now = [];

  fixes.push({ code: "SPLIT_ENTRIES" });
  fixes.push({ code: "DEFINE_INVALIDATION" });

  if (level === "critical" || level === "high") {
    now.push({ code: "WAIT_CONFIRMATION" });
    safer.push({ code: "START_SMALL" });
  } else if (level === "medium") {
    now.push({ code: "ENTER_IN_PARTS" });
    safer.push({ code: "AFTER_CONSOLIDATION" });
  } else {
    now.push({ code: "REASONABLE_IF_LIMITS" });
    safer.push({ code: "DONT_CHANGE_MID" });
  }

  if (Number.isFinite(change24h) && change24h >= 8) {
    fixes.push({ code: "AVOID_AFTER_PUMP" });
  }

  if (Number.isFinite(target) && Number.isFinite(vol) && vol > 0) {
    if (target > Math.max(10, vol * 1.5)) {
      fixes.push({ code: "REDUCE_TARGET_OR_EXTEND" });
    }
  }

  if (Number.isFinite(vol) && Number.isFinite(dd) && dd > 0 && vol > dd) {
    fixes.push({ code: "MISMATCH_SIZE_OR_DD" });
  }

  return {
    now: uniqCodes(now),
    fixes: uniqCodes(fixes).slice(0, 6),
    safer: uniqCodes(safer).slice(0, 6),
    reasons: (topReasons || []).map((r) => ({
      code: r.code,
      params: r.params || {},
    })),
  };
}

function normalizePlan(plan) {
  const normalizeItem = (x) => {
    if (!x) return null;

    if (typeof x === "string") {
      const code = x.trim();
      return code ? { code, params: {} } : null;
    }

    if (typeof x === "object") {
      const code = String(x.code || "").trim();
      const params = x.params && typeof x.params === "object" ? x.params : {};
      return { ...x, code, params };
    }

    return null;
  };

  const normalizeArr = (arr) => (Array.isArray(arr) ? arr.map(normalizeItem).filter(Boolean) : []);

  const p = plan && typeof plan === "object" ? plan : {};

  return {
    now: normalizeArr(p.now),
    fixes: normalizeArr(p.fixes),
    safer: normalizeArr(p.safer),
    reasons: normalizeArr(p.reasons),
    probability: p.probability || null,
    pro: p.pro || null,
  };
}

function estimateProbability({ level, market, user }) {
  const vol = Number(market?.vol24hProxy);
  const target = Number(user?.targetPct);
  const dd = Number(user?.maxDrawdownPct);

  let p = 0.58;

  if (level === "low") p += 0.08;
  if (level === "medium") p -= 0.08;
  if (level === "high") p -= 0.18;
  if (level === "critical") p -= 0.28;

  if (Number.isFinite(vol) && vol > 0) p -= clamp(vol / 80, 0, 0.18);
  if (Number.isFinite(target) && target > 0) p -= clamp((target - 10) / 200, 0, 0.18);

  if (Number.isFinite(dd) && dd > 0 && Number.isFinite(target)) {
    const ratio = target / dd;
    if (ratio >= 1.6) p -= 0.08;
    if (ratio >= 2.2) p -= 0.12;
  }

  return clamp(p, 0.12, 0.86);
}

function buildScenarios({ market, user, lang = "en" }) {
  const change24h = Number(market?.priceChangePercent);
  const vol = Number(market?.vol24hProxy);
  const target = Number(user?.targetPct);
  const dd = Number(user?.maxDrawdownPct);

  const baseMove = Number.isFinite(vol) ? clamp(vol, 1.2, 18) : 6;

  const bull = {
    title: "BULL",
    note: pickLang(lang, "Импульс продолжается / рынок поддерживает движение.", "Momentum continues / market stays supportive."),
    move: `+${clamp(baseMove * 1.6, 2, 28).toFixed(1)}%`,
    advice: pickLang(lang, "Входи частями. Фиксируй прибыль в 2 зонах.", "Scale in gradually. Take partial profit in 2 zones."),
  };

  const base = {
    title: "BASE",
    note: pickLang(lang, "Боковик / обычный рыночный шум.", "Range / normal market noise."),
    move: `${clamp(baseMove * 0.4, 0.8, 10).toFixed(1)}%`,
    advice: pickLang(lang, "Лучше лимитки. Не догоняй цену.", "Prefer limit orders. Wait for confirmation, don’t chase."),
  };

  const bear = {
    title: "BEAR",
    note: pickLang(lang, "Откат / ликвидность идёт против тебя.", "Pullback / liquidity moves against you."),
    move: `-${clamp(baseMove * 1.3, 2, 24).toFixed(1)}%`,
    advice: pickLang(lang, "Нужна точка отмены. Уменьши размер позиции.", "Invalidation point is mandatory. Reduce position size."),
  };

  const worst = [];

  if (Number.isFinite(change24h) && change24h >= 8) {
    worst.push(pickLang(lang, "После пампа часто бывает откат.", "After a pump, a pullback often follows."));
  }

  if (Number.isFinite(dd) && Number.isFinite(vol) && dd > 0 && vol > dd) {
    worst.push(pickLang(lang, "Твой DD меньше обычного шума рынка.", "Your DD is smaller than normal market noise."));
  }

  if (Number.isFinite(target) && Number.isFinite(vol) && target > Math.max(10, vol * 1.5)) {
    worst.push(pickLang(lang, "Цель слишком амбициозная для текущей волатильности.", "The target is too ambitious for current volatility."));
  }

  if (!worst.length) {
    worst.push(pickLang(lang, "Главный риск - нарушить дисциплину.", "Main risk: breaking discipline and changing the plan mid-trade."));
  }

  return { bull, base, bear, worst };
}
function buildLiveReview10({ market, user, level, topReasons, contractScan, currentLang, isRu }) {
  const lang = normalizeLang(currentLang || (isRu ? "ru" : "en"));
  const reasons = Array.isArray(topReasons) ? topReasons : [];
  const prob = estimateProbability({ level, market, user });
  const probability = `${Math.round(prob * 100)}%`;

  const why = [];
  const concrete = [];
  const fixes = [];

  if (contractScan?.level && ["high", "critical"].includes(String(contractScan.level))) {
    why.push(pickLang(lang, "Есть красные флаги проверки.", "Verification red flags detected."));
  } else {
    why.push(pickLang(lang, "Явных красных флагов по данным нет.", "No obvious red flags from inputs."));
  }

  if ((reasons || []).length) {
    for (const r of reasons.slice(0, 3)) {
      why.push(planCodeLabel(r?.code, lang));
    }
  }

  if (level === "high" || level === "critical") {
    concrete.push(pickLang(lang, "Жди подтверждение/откат.", "Wait for confirmation/pullback."));
    concrete.push(pickLang(lang, "Уменьши размер позиции.", "Reduce position size."));
  } else if (level === "medium") {
    concrete.push(pickLang(lang, "Можно, но входи частями.", "Okay, but scale in with limits."));
  } else {
    concrete.push(pickLang(lang, "Окей, если держишь риск-лимиты.", "Okay if you keep risk limits."));
  }

  concrete.push(pickLang(lang, "Определи стоп/инвалидацию до входа.", "Define stop/invalidation before entry."));
  concrete.push(pickLang(lang, "Раздели вход на 2-3 части.", "Split entry into 2-3 parts."));

  fixes.push(pickLang(lang, "Не меняй план во время сделки.", "Do not change the plan mid-trade."));
  fixes.push(pickLang(lang, "Не догоняй цену после резкого роста.", "Do not chase price after a strong move."));

  const kind = level === "low" ? "good" : level === "medium" ? "mixed" : "bad";

  const title =
    kind === "good"
      ? pickLang(lang, "Выглядит нормально - держи лимиты.", "Looks okay - keep risk limits.")
      : kind === "mixed"
      ? pickLang(lang, "Погранично - можно сделать безопаснее.", "Borderline - can be safer.")
      : pickLang(lang, "Риск высокий - перестрой вход.", "Risk is high - restructure entry.");

  const summary = pickLang(
    lang,
    `Вердикт: ${verdictLabel(level, lang)}`,
    `Verdict: ${verdictLabel(level, lang)}`
  );

  return {
    kind,
    title,
    summary,
    probability,
    why,
    concrete,
    fixes,
    pros: [],
    cons: [],
  };
}

function looksLikeEvmAddress(addr) {
  return /^0x[a-fA-F0-9]{40}$/.test(String(addr || "").trim());
}

function looksLikeSolAddress(addr) {
  return /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(String(addr || "").trim());
}

function looksLikeTronAddress(addr) {
  return /^T[1-9A-HJ-NP-Za-km-z]{33}$/.test(String(addr || "").trim());
}

function buildExplorerUrl(platformKey, addr) {
  const a = String(addr || "").trim();
  if (!a) return null;

  const key = String(platformKey || "").toLowerCase();

  if (key === "ethereum") return `https://etherscan.io/address/${a}`;
  if (key === "binance-smart-chain") return `https://bscscan.com/address/${a}`;
  if (key === "polygon-pos" || key === "polygon") return `https://polygonscan.com/address/${a}`;
  if (key === "arbitrum-one") return `https://arbiscan.io/address/${a}`;
  if (key === "optimism") return `https://optimistic.etherscan.io/address/${a}`;
  if (key === "base") return `https://basescan.org/address/${a}`;
  if (key === "avalanche") return `https://snowtrace.io/address/${a}`;
  if (key === "fantom") return `https://ftmscan.com/address/${a}`;
  if (key === "solana") return `https://solscan.io/token/${a}`;
  if (key === "tron") return `https://tronscan.org/#/token20/${a}`;

  return null;
}

function analyzeContractsAndLinks({ facts, candidates, symbol, lang = "en" }) {
  let score = 0;
  const reasons = [];

  const conflictCount = (candidates || []).filter(
    (c) => String(c?.symbol || "").toUpperCase() === String(symbol || "").toUpperCase()
  ).length;

  if (conflictCount >= 2) {
    score += 25;
    reasons.push(
      pickLang(lang, "Несколько активов имеют такой тикер на CoinGecko.", "Ticker conflict: multiple assets share this symbol on CoinGecko.")
    );
  }

  const homepage = facts?.homepage;
  const twitter = facts?.twitter;
  const telegram = facts?.telegram;
  const links = [homepage, twitter, telegram].filter(Boolean);

  if (links.length === 0) {
    score += 15;
    reasons.push(
      pickLang(lang, "Нет официальных ссылок - сложнее проверить легитимность.", "Missing official links - harder to verify legitimacy.")
    );
  } else {
    if (homepage && hasPunycode(homepage)) {
      score += 20;
      reasons.push(
        pickLang(lang, "Домен содержит punycode xn-- - возможный фишинг.", "Website uses punycode domain - possible phishing.")
      );
    }

    if (homepage && !/^https:\/\//i.test(homepage.trim())) {
      score += 6;
      reasons.push(pickLang(lang, "Сайт не HTTPS.", "Website is not HTTPS."));
    }
  }

  const platforms = facts?.contractsByPlatform || {};
  const entries = Object.entries(platforms).filter(([, addr]) => !!addr);

  if (entries.length >= 3) {
    score += 10;
    reasons.push(
      pickLang(lang, "Много контрактов в разных сетях - проверь правильный.", "Multiple contracts across chains - verify the correct one.")
    );
  }

  for (const [chain, addr] of entries) {
    const a = String(addr || "").trim();
    const chainLow = String(chain || "").toLowerCase();

    let ok = true;

    if (chainLow.includes("solana")) ok = looksLikeSolAddress(a);
    else if (chainLow.includes("tron")) ok = looksLikeTronAddress(a);
    else ok = a.startsWith("0x") ? looksLikeEvmAddress(a) : true;

    if (!ok) {
      score += 14;
      reasons.push(pickLang(lang, "Формат контракта выглядит подозрительно.", "Contract format looks suspicious."));
    }
  }

  score = clamp(score, 0, 100);
  const level = scoreToLevel(score);

  return {
    score,
    level,
    color: levelColor(level),
    reasons,
  };
}

function pickDescriptionShort(enText) {
  const s = String(enText || "")
    .replace(/<[^>]*>/g, "")
    .replace(/\s+/g, " ")
    .trim();

  if (!s) return null;
  return s.length > 240 ? s.slice(0, 240) + "…" : s;
}

async function recordPreventedIfBad({ amountUsd, level }) {
  try {
    const l = String(level || "").toLowerCase();
    if (l !== "high" && l !== "critical") return;

    const amt = Number(amountUsd);
    if (!Number.isFinite(amt) || amt <= 0) return;

    const key = "immunity.last7.preventedUsd";
    const raw = await AsyncStorage.getItem(key);
    const prev = Number(raw || 0) || 0;

    await AsyncStorage.setItem(key, String(Math.round(prev + amt)));
  } catch {}
}

export default function ImmunityScreen() {
  const { t, i18n } = useTranslation();
  const router = useRouter();

  const currentLang = normalizeLang(i18n?.language);
  const isRu = currentLang === "ru";
  const tvLocale = currentLang === "ru" ? "ru" : currentLang === "uk" ? "uk" : "en";

  const tx = useCallback(
    (key, def, params) => t(`immunity.${key}`, { defaultValue: def, ...(params || {}) }),
    [t]
  );

  const tVerdict = useCallback(
    (level) => t(`immunity.verdictLevels.${level}`, { defaultValue: verdictLabel(level, currentLang) }),
    [t, currentLang]
  );

  const [loadingPairs, setLoadingPairs] = useState(true);
  const [pairs, setPairs] = useState([]);
  const [query, setQuery] = useState("");

  const [coinOpen, setCoinOpen] = useState(false);
  const [selected, setSelected] = useState(null);
  const [factsOpen, setFactsOpen] = useState(true);
  const [chartBig, setChartBig] = useState(true);

  const [selectedKlines, setSelectedKlines] = useState([]);
  const [selectedBook, setSelectedBook] = useState(null);

  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);

  const [amountUsdt, setAmountUsdt] = useState("100");
  const [horizon, setHorizon] = useState("1W");
  const [targetPct, setTargetPct] = useState("10");
  const [maxDdPct, setMaxDdPct] = useState("8");
  const [alreadyHolding, setAlreadyHolding] = useState(false);
  const [reason, setReason] = useState("STRATEGY");

  const [analysisRes, setAnalysisRes] = useState(null);
  const [assetFacts, setAssetFacts] = useState(null);
  const [cgCandidates, setCgCandidates] = useState([]);
  const [contractScan, setContractScan] = useState(null);

  const [copiedMsg, setCopiedMsg] = useState("");
  const [behavior, setBehavior] = useState({ analyses24h: 0 });

  const [isPro, setIsProState] = useState(false);
  const [quota, setQuota] = useState({ used: 0, limit: FREE_LIMIT, left: FREE_LIMIT });
  const [uid, setUid] = useState("local");

  const shareCardRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const best = await getBestKnownUid();
        setUid(best || "local");
      } catch {
        setUid("local");
      }
    })();
  }, []);

  useEffect(() => {
    loadBehavior();
    loadTopPairs();

    (async () => {
      const p = await getIsPro();
      setIsProState(p);
    })();

    logEvent("screen_immunity_open");
  }, []);

  useEffect(() => {
    if (!uid) return;

    (async () => {
      const q = await getLocalQuota(uid, "immunity", FREE_LIMIT);
      setQuota({ used: q.used, limit: q.limit, left: q.left });
    })();
  }, [uid, analyzing, isPro]);

  useEffect(() => {
    if (!copiedMsg) return;
    const timer = setTimeout(() => setCopiedMsg(""), 1200);
    return () => clearTimeout(timer);
  }, [copiedMsg]);

  const loadBehavior = useCallback(async () => {
    try {
      const raw = await AsyncStorage.getItem(K.analysisHistory);
      const arr = raw ? JSON.parse(raw) : [];
      const now = Date.now();
      const last24h = (arr || []).filter((x) => now - (x?.createdAt || 0) <= 24 * 3600 * 1000);

      setBehavior({ analyses24h: last24h.length });
    } catch {
      setBehavior({ analyses24h: 0 });
    }
  }, []);

  const loadTopPairs = useCallback(async () => {
    setLoadingPairs(true);

    try {
      const exRes = await fetchWithTimeout(`${BINANCE}/api/v3/exchangeInfo`, {}, 12000);
      const ex = await exRes.json();

      const symbols = (ex?.symbols || [])
        .filter((s) => s?.status === "TRADING" && s?.quoteAsset === "USDT" && !isJunkFiatLikeBaseAsset(s?.baseAsset))
        .map((s) => ({
          symbol: s.symbol,
          baseAsset: s.baseAsset,
          quoteAsset: s.quoteAsset,
        }));

      const tkRes = await fetchWithTimeout(`${BINANCE}/api/v3/ticker/24hr`, {}, 12000);
      const tickers = await tkRes.json();

      const tickerMap = new Map();
      for (const tk of tickers || []) tickerMap.set(tk.symbol, tk);

      const merged = symbols
        .map((s) => {
          const tk = tickerMap.get(s.symbol);
          if (!tk) return null;

          return {
            ...s,
            lastPrice: Number(tk.lastPrice),
            priceChangePercent: Number(tk.priceChangePercent),
            quoteVolume: Number(tk.quoteVolume),
          };
        })
        .filter(Boolean);

      merged.sort((a, b) => (b.quoteVolume || 0) - (a.quoteVolume || 0));
      setPairs(merged.slice(0, 50));
    } catch {
      showAppAlert(
        tx("common.errorTitle", "Error"),
        tx("errors.binanceMarket", "Failed to load Binance market data.")
      );
    } finally {
      setLoadingPairs(false);
    }
  }, [tx]);

  const filteredPairs = useMemo(() => {
    const q = (query || "").trim().toUpperCase();
    if (!q) return pairs;
    return pairs.filter((p) => p.symbol.includes(q) || p.baseAsset.includes(q));
  }, [pairs, query]);

  const filteredPairsShort = useMemo(() => { return (filteredPairs || []).slice(0, 50); }, [filteredPairs]);

  const marketSnapshot = useMemo(() => {
    if (!selected) return null;

    const lastPrice = Number(selected.lastPrice);
    const change24h = Number(selected.priceChangePercent);
    const quoteVolume = Number(selected.quoteVolume);

    let vol = null;

    if (selectedKlines?.length) {
      const vals = [];

      for (const k of selectedKlines) {
        const open = Number(k?.[1]);
        const close = Number(k?.[4]);

        if (!Number.isFinite(open) || !Number.isFinite(close) || open <= 0) continue;
        vals.push((Math.abs(close - open) / open) * 100);
      }

      if (vals.length) vol = (vals.reduce((a, b) => a + b, 0) / vals.length) * 6;
    }

    let spreadBps = null;

    if (selectedBook?.bidPrice && selectedBook?.askPrice) {
      const bid = Number(selectedBook.bidPrice);
      const ask = Number(selectedBook.askPrice);

      if (Number.isFinite(bid) && Number.isFinite(ask) && bid > 0 && ask > 0) {
        const mid = (bid + ask) / 2;
        spreadBps = ((ask - bid) / mid) * 10000;
      }
    }

    return {
      symbol: selected.symbol,
      baseAsset: selected.baseAsset,
      quoteAsset: selected.quoteAsset,
      lastPrice,
      priceChangePercent: change24h,
      quoteVolume,
      vol24hProxy: vol,
      spreadBps,
    };
  }, [selected, selectedKlines, selectedBook]);

  const copyText = useCallback(
    async (value, label) => {
      const v = String(value ?? "").trim();
      if (!v) return;

      try {
        await Clipboard.setStringAsync(v);
        setCopiedMsg(label || tx("copy.copied", "Copied"));
        logEvent("tap_immunity_copy", { kind: String(label || "value").slice(0, 24) });
      } catch {}
    },
    [tx]
  );

  const resetFormDefaults = useCallback(() => {
    setAmountUsdt("100");
    setHorizon("1W");
    setTargetPct("10");
    setMaxDdPct("8");
    setAlreadyHolding(false);
    setReason("STRATEGY");
  }, []);

  const openCoin = useCallback(
    async (p) => {
      logEvent("tap_immunity_open_coin", { symbol: p?.symbol || "" });

      setSelected(p);
      setAssetFacts(null);
      setCgCandidates([]);
      setContractScan(null);
      setAnalysisRes(null);
      resetFormDefaults();
      setFactsOpen(true);
      setChartBig(true);
      setCoinOpen(true);

      try {
        const [ksRes, bookRes] = await Promise.all([
          fetchWithTimeout(`${BINANCE}/api/v3/klines?symbol=${encodeURIComponent(p.symbol)}&interval=1h&limit=48`, {}, 12000),
          fetchWithTimeout(`${BINANCE}/api/v3/ticker/bookTicker?symbol=${encodeURIComponent(p.symbol)}`, {}, 12000),
        ]);

        const ks = await ksRes.json();
        const book = await bookRes.json();

        setSelectedKlines(Array.isArray(ks) ? ks : []);
        setSelectedBook(book || null);
      } catch {
        setSelectedKlines([]);
        setSelectedBook(null);
      }
    },
    [resetFormDefaults]
  );

  const closeCoin = useCallback(() => {
    setCoinOpen(false);
    setAnalysisOpen(false);
  }, []);

  const saveHistory = useCallback(async (item) => {
    try {
      const raw = await AsyncStorage.getItem(K.analysisHistory);
      const arr = raw ? JSON.parse(raw) : [];
      const next = [item, ...(arr || [])].slice(0, HISTORY_LIMIT);

      await AsyncStorage.setItem(K.analysisHistory, JSON.stringify(next));
    } catch {}
  }, []);

  const fetchCoinGeckoFacts = useCallback(async (baseAsset) => {
    const q = String(baseAsset || "").trim();
    if (!q) return { facts: null, candidates: [] };

    const sRes = await fetchWithTimeout(`${CG}/search?query=${encodeURIComponent(q)}`, {}, 12000);
    const search = await sRes.json();

    const coins = (search?.coins || []).map((c) => ({
      id: c?.id,
      name: c?.name,
      symbol: (c?.symbol || "").toUpperCase(),
      market_cap_rank: c?.market_cap_rank ?? null,
    }));

    const sym = q.toLowerCase();
    const best =
      (search?.coins || []).find((c) => String(c?.symbol || "").toLowerCase() === sym) ||
      (search?.coins || [])[0];

    if (!best?.id) return { facts: null, candidates: coins };

    const dRes = await fetchWithTimeout(
      `${CG}/coins/${encodeURIComponent(best.id)}?localization=false&tickers=false&community_data=false&developer_data=false&sparkline=false`,
      {},
      12000
    );

    const data = await dRes.json();

    const facts = {
      id: best.id,
      name: data?.name,
      symbol: data?.symbol?.toUpperCase?.() || q,
      homepage: data?.links?.homepage?.filter(Boolean)?.[0] || null,
      twitter: data?.links?.twitter_screen_name ? `https://twitter.com/${data.links.twitter_screen_name}` : null,
      telegram: data?.links?.telegram_channel_identifier ? `https://t.me/${data.links.telegram_channel_identifier}` : null,
      contractsByPlatform: data?.platforms || {},
      marketCapUsd: data?.market_data?.market_cap?.usd ?? null,
      fdvUsd: data?.market_data?.fully_diluted_valuation?.usd ?? null,
      circSupply: data?.market_data?.circulating_supply ?? null,
      totalSupply: data?.market_data?.total_supply ?? null,
      maxSupply: data?.market_data?.max_supply ?? null,
      descriptionShort: pickDescriptionShort(data?.description?.en),
      lastUpdated: data?.last_updated || null,
    };

    return { facts, candidates: coins };
  }, []);

  const refreshFactsAndScan = useCallback(async () => {
    if (!selected) return;

    try {
      logEvent("tap_immunity_load_facts", { base: selected?.baseAsset || "" });

      const { facts, candidates } = await fetchCoinGeckoFacts(selected.baseAsset);

      setAssetFacts(facts);
      setCgCandidates(candidates || []);

      const scan = analyzeContractsAndLinks({
        facts,
        candidates,
        symbol: selected.baseAsset,
        lang: currentLang,
      });

      setContractScan(scan);
    } catch {
      showAppAlert(tx("common.errorTitle", "Error"), tx("errors.facts", "Failed to load facts."));
    }
  }, [fetchCoinGeckoFacts, selected, tx, currentLang]);

  const tickerConflict = useMemo(() => {
    if (!selected?.baseAsset) return null;

    const sym = String(selected.baseAsset).toUpperCase();
    const hits = (cgCandidates || []).filter((c) => String(c?.symbol || "").toUpperCase() === sym);

    if (hits.length >= 2) return hits.slice(0, 6);
    return null;
  }, [cgCandidates, selected?.baseAsset]);

  const ensureQuotaFresh = useCallback(async () => {
    if (!uid) return { used: 0, limit: FREE_LIMIT, left: FREE_LIMIT };

    const q = await getLocalQuota(uid, "immunity", FREE_LIMIT);
    const q2 = { used: q.used, limit: q.limit, left: q.left };

    setQuota(q2);
    return q2;
  }, [uid]);

  const gotoPro = useCallback(() => {
    logEvent("tap_immunity_goto_pro");
    router.push("/pro");
  }, [router]);

  const runAnalysis = useCallback(async () => {
    if (!selected || !marketSnapshot) return;

    const q = await ensureQuotaFresh();

    if (!isPro && q.used >= q.limit) {
      showAppAlert(
        isRu ? "FREE лимит" : "FREE limit",
        isRu
          ? "FREE: 4 анализа в день. PRO снимает лимит."
          : "FREE: 4 analyses/day. PRO removes this limit.",
        [
          { text: "OK", style: "cancel" },
          { text: isRu ? "Открыть PRO" : "Go PRO", onPress: gotoPro },
        ]
      );
      return;
    }

    const amount = Number(String(amountUsdt).replace(",", "."));
    const tgt = Number(String(targetPct).replace(",", "."));
    const dd = Number(String(maxDdPct).replace(",", "."));

    if (!Number.isFinite(amount) || amount <= 0) {
      showAppAlert(tx("common.checkInput", "Check input"), tx("errors.amountPositive", "Amount must be positive."));
      return;
    }

    if (!Number.isFinite(tgt) || tgt <= 0) {
      showAppAlert(tx("common.checkInput", "Check input"), tx("errors.targetPositive", "Target must be positive."));
      return;
    }

    if (!Number.isFinite(dd) || dd <= 0) {
      showAppAlert(tx("common.checkInput", "Check input"), tx("errors.ddPositive", "Max drawdown must be positive."));
      return;
    }

    logEvent("tap_immunity_run_analyze", { symbol: selected?.symbol || "" });
    setAnalyzing(true);

    try {
      if (!assetFacts) {
        await refreshFactsAndScan();
      }

      const bestUid = await getBestKnownUid();

      const user = {
        amountUsdt: amount,
        horizon,
        targetPct: tgt,
        maxDrawdownPct: dd,
        alreadyHolding,
        reason,
        userId: bestUid,
      };

      const lang = currentLang;

      let live = null;

      const payload = {
        market: marketSnapshot,
        user,
        behavior,
        facts: assetFacts || null,
        contractScan: contractScan || null,
        candidates: cgCandidates || [],
        pair: {
          symbol: selected.symbol,
          baseAsset: selected.baseAsset,
          quoteAsset: selected.quoteAsset,
        },
      };

      const tryPaths = ["/immunity/analyze", "/immunity/analyze/", "/immunity", "/immunity/"];

      for (const p of tryPaths) {
        try {
          live = await apiPost(p, payload, lang);
          if (live) break;
        } catch {
          live = null;
        }
      }

      const local = computeRiskEngine({ market: marketSnapshot, user, behavior });

      const scoreRaw = Number(live?.score ?? local.score ?? 0) || 0;
      const score = Math.round(clamp(scoreRaw, 0, 100));
      const level = String(live?.level ?? local.level ?? scoreToLevel(score)).toLowerCase();

      const mergedPlan = localizePlan(normalizePlan(live?.plan || local.plan), lang);

      const liveReview =
        live?.review || live?.strategyReview || live?.userReview || live?.verdictReview || null;

      const normalizedLiveReview = normalizeLiveReview(liveReview, lang);

      const review10 = localizeReview10(
        normalizedLiveReview ||
          buildLiveReview10({
            market: marketSnapshot,
            user,
            level,
            topReasons: Array.isArray(live?.topReasons) ? live.topReasons : local.topReasons,
            contractScan: contractScan || null,
            currentLang: lang,
            isRu: lang === "ru",
          }),
        lang
      );

      const rawScenarios = live?.scenarios || buildScenarios({ market: marketSnapshot, user, lang });

      const scenarios = {
        bull: localizeScenarioItem(rawScenarios?.bull, lang),
        base: localizeScenarioItem(rawScenarios?.base, lang),
        bear: localizeScenarioItem(rawScenarios?.bear, lang),
        worst: (Array.isArray(rawScenarios?.worst) ? rawScenarios.worst : [])
          .map((x) => getLocalizedTextValue(x, lang) || (typeof x === "string" ? x : ""))
          .filter(Boolean),
      };

      const localizedVerdict =
        getLocalizedField(live || {}, "verdict", lang) ||
        getLocalizedField(live || {}, "verdictLabel", lang) ||
        verdictLabel(level, lang);

      const localizedTopReasons = (Array.isArray(live?.topReasons) ? live.topReasons : local.topReasons || []).map((r) => ({
        ...r,
        text: getLocalizedField(r, "text", lang) || planCodeLabel(r?.code, lang),
      }));

      const finalRes = {
        ...(live || local),
        score,
        level,
        verdict: localizedVerdict,
        color: live?.color || levelColor(level),
        topReasons: localizedTopReasons,
        plan: mergedPlan,
        review10,
        scenarios,
        user,
        marketSnapshot,
        assetFacts: assetFacts || null,
        contractScan: contractScan || null,
        cgCandidates: cgCandidates || [],
        symbol: selected.symbol,
        baseAsset: selected.baseAsset,
        createdAt: Date.now(),
      };

      setAnalysisRes(finalRes);
      setAnalysisOpen(false);

      await saveHistory(finalRes);
      await loadBehavior();

      if (!isPro) {
        const q2 = await incLocalQuota(uid, "immunity", FREE_LIMIT);
        setQuota({ used: q2.used, limit: q2.limit, left: q2.left });
      }

      const nextCount = await incShieldCount();

      await recordPreventedIfBad({
        amountUsd: finalRes?.user?.amountUsdt,
        level: finalRes?.level,
      });

      logEvent("immunity_analyze_success", {
        symbol: selected?.symbol || "",
        level: String(finalRes?.level || ""),
        score: Number(finalRes?.score || 0),
        total: Number(nextCount || 0),
        backend: live ? 1 : 0,
      });
    } catch (e) {
      logEvent("immunity_analyze_error", {
        symbol: selected?.symbol || "",
        msg: String(e?.message || ""),
      });

      showAppAlert(
        tx("common.errorTitle", "Error"),
        explainBackendMessage(e?.message || "", currentLang)
      );
    } finally {
      setAnalyzing(false);
    }
  }, [
    selected,
    marketSnapshot,
    amountUsdt,
    targetPct,
    maxDdPct,
    horizon,
    alreadyHolding,
    reason,
    behavior,
    assetFacts,
    contractScan,
    cgCandidates,
    refreshFactsAndScan,
    saveHistory,
    loadBehavior,
    tx,
    isPro,
    uid,
    ensureQuotaFresh,
    gotoPro,
    isRu,
    currentLang,
  ]);

  const shareAsImage = useCallback(async () => {
    if (!analysisRes) return;

    try {
      logEvent("tap_immunity_share_image", { symbol: analysisRes?.symbol || "" });

      const node = shareCardRef?.current;

      if (!node) {
        showAppAlert(
          isRu ? "Ошибка Share" : "Share error",
          isRu ? "Карточка ещё не готова. Попробуй ещё раз." : "Share card is not ready yet. Try again."
        );
        return;
      }

      await new Promise((resolve) => InteractionManager.runAfterInteractions(resolve));
      await new Promise((resolve) => setTimeout(resolve, 220));

      let uri = null;

      if (typeof node.capture === "function") {
        uri = await node.capture();
      } else {
        uri = await captureRef(node, {
          format: "png",
          quality: 1,
          result: "tmpfile",
        });
      }

      if (!uri || typeof uri !== "string") {
        throw new Error("capture_failed");
      }

      const canShareFile = await Sharing.isAvailableAsync().catch(() => false);

      if (canShareFile) {
        logEvent("immunity_share_success", { method: "file", symbol: analysisRes?.symbol || "" });
        await Sharing.shareAsync(uri, {
          mimeType: "image/png",
          dialogTitle: "NOYTRIX IMMUNITY",
          UTI: "public.png",
        });
        return;
      }

      logEvent("immunity_share_success", { method: "native", symbol: analysisRes?.symbol || "" });
      await Share.share({
        title: "NOYTRIX IMMUNITY",
        url: uri,
        message: Platform.OS === "ios" ? "NOYTRIX IMMUNITY" : `NOYTRIX IMMUNITY
${uri}`,
      });
    } catch (e) {
      const raw = String(e?.message || e || "").toLowerCase();

      if (!raw.includes("cancel")) {
        showAppAlert(
          isRu ? "Ошибка Share" : "Share error",
          isRu ? "Не удалось отправить картинку. Попробуй ещё раз." : "Could not send the image. Please try again."
        );
      }

      logEvent("immunity_share_error", { symbol: analysisRes?.symbol || "", err: String(e?.message || e || "error") });
      console.log("[IMMUNITY SHARE ERROR]", e?.message || e);
    }
  }, [analysisRes, isRu]);

  return (
    <LinearGradient colors={[GRAD.start, GRAD.mid, GRAD.end]} style={{ flex: 1, paddingTop: 48 }}>
      <Stack.Screen options={{ headerShown: false }} />

      {!!copiedMsg && (
        <View style={{ position: "absolute", top: 56, left: 16, right: 16, zIndex: 9999 }}>
          <View
            style={{
              borderWidth: 1,
              borderColor: "rgba(255,176,32,0.35)",
              backgroundColor: "rgba(10,15,30,0.92)",
              borderRadius: 14,
              paddingVertical: 10,
              paddingHorizontal: 12,
              flexDirection: "row",
              gap: 10,
              alignItems: "center",
            }}
          >
            <Ionicons name="copy-outline" size={18} color={T.logo} />
            <Text style={{ color: T.text, fontWeight: "900" }} numberOfLines={1}>
              {copiedMsg}
            </Text>
          </View>
        </View>
      )}

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 130 }}>
        <Text style={{ color: T.logo, fontWeight: "900", fontSize: 34, marginBottom: 6, letterSpacing: 0.2 }} numberOfLines={1}>
          {tx("title", "Immunity")}
        </Text>

        <Text style={{ color: T.dim, marginBottom: 14, fontSize: 15, lineHeight: 20 }}>
          {tx("subtitleNew", "Search a pair → open it → analyze your buy plan with Risk Engine.")}
        </Text>

        <BlurCard style={{ borderColor: "rgba(255,176,32,0.35)" }} intensity={28}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
            <Text style={{ color: T.text, fontWeight: "900", fontSize: 18 }}>
              {tx("pick.title", "Choose a market pair")}
            </Text>

            <View
              style={{
                paddingVertical: 6,
                paddingHorizontal: 10,
                borderRadius: 999,
                borderWidth: 1,
                borderColor: isPro ? "rgba(41,211,122,0.45)" : "rgba(255,176,32,0.35)",
                backgroundColor: isPro ? "rgba(41,211,122,0.10)" : "rgba(255,176,32,0.10)",
              }}
            >
              <Text style={{ color: isPro ? T.good : T.logo, fontWeight: "900", fontSize: 12 }}>
                {isPro ? "PRO" : `FREE • ${quota.used}/${quota.limit} • ${quota.left} left`}
              </Text>
            </View>
          </View>

          <View
            style={{
              marginTop: 12,
              borderWidth: 1,
              borderColor: T.borderSoft,
              borderRadius: 16,
              backgroundColor: "rgba(255,255,255,0.05)",
              flexDirection: "row",
              alignItems: "center",
              paddingHorizontal: 12,
              gap: 10,
            }}
          >
            <Ionicons name="search-outline" size={18} color={T.dim} />

            <TextInput
              placeholder="Search ticker"
              placeholderTextColor={T.dim}
              value={query}
              onChangeText={setQuery}
              autoCapitalize="characters"
              style={{ color: T.text, height: 48, flex: 1, fontSize: 16 }}
              numberOfLines={1}
            />

            {!!query && (
              <Pressable
                onPress={() => {
                  logEvent("tap_immunity_clear_search");
                  setQuery("");
                }}
              >
                <Ionicons name="close-circle" size={18} color={T.dim} />
              </Pressable>
            )}
          </View>

          <View style={{ marginTop: 12 }}>
            {loadingPairs ? (
              <View style={{ paddingVertical: 20, alignItems: "center" }}>
                <ActivityIndicator />
                <Text style={{ color: T.dim, marginTop: 10 }}>
                  {tx("pick.loading", "Loading Binance market…")}
                </Text>
              </View> ) : (
              <View style={{ gap: 8 }}>
                {filteredPairsShort.map((p) => (
                  <Pressable
                    key={p.symbol}
                    onPress={() => openCoin(p)}
                    style={{
                      borderWidth: 1,
                      borderColor: T.border,
                      backgroundColor: "rgba(255,255,255,0.03)",
                      borderRadius: 18,
                      padding: 12,
                      flexDirection: "row",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 10,
                    }}
                  >
                    <View style={{ minWidth: 0, flex: 1 }}>
                      <Text style={{ color: T.text, fontWeight: "900", fontSize: 15 }} numberOfLines={1}>
                        {p.baseAsset}
                        <Text style={{ color: T.dim, fontWeight: "800" }}> / {p.quoteAsset}</Text>
                      </Text>

                      <Text style={{ color: T.dim, marginTop: 2, fontSize: 12 }} numberOfLines={1}>
                        {p.symbol}
                      </Text>
                    </View>

                    <View style={{ alignItems: "flex-end" }}>
                      <Text style={{ color: T.text, fontWeight: "900", fontSize: 14 }}>
                        {fmtPrice(p.lastPrice)}
                      </Text>

                      <Text
                        style={{
                          color: (p.priceChangePercent || 0) >= 0 ? T.good : T.bad,
                          fontWeight: "900",
                          marginTop: 2,
                          fontSize: 12,
                        }}
                      >
                        {pct(p.priceChangePercent)}
                      </Text>
                    </View>
                  </Pressable>
                ))}

                {filteredPairs?.length > 20 && (
                  <Text style={{ color: T.dim, fontSize: 12, marginTop: 6 }}>
                    {tx("pick.showing", "Showing first 20 results. Refine search to find more.")}
                  </Text>
                )}
              </View>
            )}
          </View>
        </BlurCard>

        <InfoCard
          title={isRu ? "Зачем нужен Immunity" : "Why Immunity exists"}
          text={
            isRu
              ? "Immunity оценивает логику входа, риск, горизонт и рынок. Он помогает не входить на эмоциях."
              : "Immunity evaluates your entry logic, risk, horizon, behavior and market context. It helps avoid FOMO and discipline mistakes."
          }
        />

        <InfoCard
          title={isRu ? "Как использовать" : "How to use"}
          text={
            isRu
              ? "1) Найди пару. 2) Открой монету. 3) Проверь факты. 4) Запусти Risk Engine."
              : "1) Search and open a pair. 2) Check facts. 3) Run Risk Engine. 4) Follow the concrete plan."
          }
        />
      </ScrollView>

      <Modal visible={coinOpen} animationType="slide" transparent>
        <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.55)" }}>
          <View style={{ flex: 1, paddingTop: 48 }}>
            <LinearGradient colors={[GRAD.start, GRAD.mid, GRAD.end]} style={{ flex: 1 }}>
              <View
                style={{
                  paddingHorizontal: 16,
                  paddingBottom: 14,
                  flexDirection: "row",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <Pressable
                  onPress={() => {
                    logEvent("tap_immunity_close_coin");
                    closeCoin();
                  }}
                  style={{ padding: 8 }}
                >
                  <Ionicons name="chevron-down" size={26} color={T.text} />
                </Pressable>

                <View style={{ alignItems: "center", flex: 1 }}>
                  <Text style={{ color: T.text, fontWeight: "900", fontSize: 16 }} numberOfLines={1}>
                    {selected?.baseAsset} / {selected?.quoteAsset}
                  </Text>

                  <Text style={{ color: T.dim, fontWeight: "800", fontSize: 12 }} numberOfLines={1}>
                    {selected?.symbol}
                  </Text>
                </View>

                <Pressable
                  onPress={() => {
                    logEvent("tap_immunity_toggle_chart");
                    setChartBig((v) => !v);
                  }}
                  style={{ padding: 8 }}
                >
                  <Ionicons name={chartBig ? "contract-outline" : "expand-outline"} size={22} color={T.text} />
                </Pressable>
              </View>

              <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 140 }}>
                {!!selected && (
                  <>
                    <BlurCard intensity={26}>
                      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                        <View style={{ minWidth: 0, flex: 1 }}>
                          <Text style={{ color: T.text, fontWeight: "900", fontSize: 22 }} numberOfLines={1}>
                            {selected.baseAsset}
                            <Text style={{ color: T.dim, fontWeight: "800", fontSize: 16 }}> / {selected.quoteAsset}</Text>
                          </Text>

                          <Text style={{ color: T.dim, marginTop: 4 }} numberOfLines={1}>
                            {isRu ? "Данные рынка: Binance" : "Market data: Binance"}
                          </Text>
                        </View>

                        <View style={{ alignItems: "flex-end" }}>
                          <Text style={{ color: T.text, fontWeight: "900", fontSize: 18 }}>
                            {fmtPrice(marketSnapshot?.lastPrice)}
                          </Text>

                          <Text
                            style={{
                              color: (marketSnapshot?.priceChangePercent || 0) >= 0 ? T.good : T.bad,
                              fontWeight: "900",
                              marginTop: 2,
                            }}
                          >
                            {pct(marketSnapshot?.priceChangePercent)}
                          </Text>
                        </View>
                      </View>

                      <View
                        style={{
                          marginTop: 14,
                          borderWidth: 1,
                          borderColor: T.borderSoft,
                          borderRadius: 18,
                          overflow: "hidden",
                          backgroundColor: "rgba(255,255,255,0.03)",
                          height: chartBig ? 520 : 360,
                        }}
                      >
                        <WebView
                          originWhitelist={["*"]}
                          source={{
                            html: tradingViewHtml(`BINANCE:${selected.symbol}`, "dark", "60", tvLocale),
                          }}
                          javaScriptEnabled
                          domStorageEnabled
                          style={{ backgroundColor: "transparent" }}
                        />
                      </View>

                      <View style={{ flexDirection: "row", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
                        <MetaBox
                          label="24h Volume"
                          value={fmtNum(marketSnapshot?.quoteVolume)}
                          onCopy={() => copyText(String(marketSnapshot?.quoteVolume ?? ""))}
                        />

                        <MetaBox
                          label="Volatility"
                          value={marketSnapshot?.vol24hProxy != null ? pct(marketSnapshot.vol24hProxy) : "-"}
                          onCopy={() => copyText(String(marketSnapshot?.vol24hProxy ?? ""))}
                        />

                        <MetaBox
                          label="Spread"
                          value={marketSnapshot?.spreadBps != null ? `${marketSnapshot.spreadBps.toFixed(0)} bps` : "-"}
                          onCopy={() => copyText(String(marketSnapshot?.spreadBps ?? ""))}
                        />
                      </View>

                      <View style={{ flexDirection: "row", gap: 12, marginTop: 14 }}>
                        <View style={{ flex: 1, minWidth: 0 }}>
                          <PrimaryButton
                            title={isRu ? "Analyze" : "Analyze buy plan"}
                            icon="sparkles-outline"
                            onPress={() => {
                              logEvent("tap_immunity_open_analyze");
                              setAnalysisOpen(true);
                            }}
                          />
                        </View>

                        <View style={{ flex: 1, minWidth: 0 }}>
                          <SecondaryButton
                            title={factsOpen ? (isRu ? "Скрыть факты" : "Hide facts") : (isRu ? "Факты" : "Show facts")}
                            icon={factsOpen ? "chevron-up-outline" : "chevron-down-outline"}
                            onPress={() => {
                              logEvent("tap_immunity_toggle_facts");
                              setFactsOpen((v) => !v);
                            }}
                          />
                        </View>
                      </View>
                    </BlurCard>

                    {factsOpen && (
                      <BlurCard>
                        <Text style={{ color: T.text, fontWeight: "900", fontSize: 18 }}>
                          {isRu ? "Факты и проверка" : "Facts & verification"}
                        </Text>

                        <Text style={{ color: T.dim, marginTop: 6, lineHeight: 19 }}>
                          {isRu ? "Данные CoinGecko + Binance." : "Powered by CoinGecko + Binance."}
                        </Text>

                        <View style={{ marginTop: 12 }}>
                          <SecondaryButton
                            title={assetFacts ? (isRu ? "Обновить факты" : "Refresh facts") : (isRu ? "Загрузить факты" : "Load facts")}
                            icon="download-outline"
                            onPress={refreshFactsAndScan}
                          />
                        </View>

                        {assetFacts ? (
                          <View style={{ marginTop: 12, gap: 10 }}>
                            <CopyRow label="CoinGecko ID" value={assetFacts.id || "-"} onCopy={() => copyText(assetFacts.id, "ID copied")} />
                            <CopyRow label="Name" value={assetFacts.name || "-"} onCopy={() => copyText(assetFacts.name, "Copied")} />
                            <CopyRow label="Market Cap" value={fmtNum(assetFacts.marketCapUsd)} onCopy={() => copyText(String(assetFacts.marketCapUsd ?? ""), "Copied")} />
                            <CopyRow label="FDV" value={fmtNum(assetFacts.fdvUsd)} onCopy={() => copyText(String(assetFacts.fdvUsd ?? ""), "Copied")} />

                            {tickerConflict && (
                              <AlertBox
                                title={isRu ? "⚠️ Возможный конфликт тикера" : "⚠️ Possible ticker conflict"}
                                text={isRu ? "Несколько активов имеют такой тикер." : "Multiple assets share this ticker. Verify exact ID + contract."}
                                color={T.warn}
                              />
                            )}

                            {contractScan && (
                              <AlertBox
                                title={`Contract Scan: ${tVerdict(contractScan.level)} • ${Math.round(contractScan.score)}/100`}
                                text={
                                  (contractScan.reasons || []).join("\n• ").trim()
                                    ? `• ${(contractScan.reasons || []).join("\n• ")}`
                                    : isRu
                                    ? "Сильных красных флагов нет."
                                    : "No major red flags detected."
                                }
                                color={contractScan.color}
                              />
                            )}

                            <LinkRow
                              label="Official website"
                              value={assetFacts.homepage || "-"}
                              onCopy={() => copyText(assetFacts.homepage, "Copied")}
                              onOpen={() => safeOpenUrl(assetFacts.homepage)}
                            />

                            {!!assetFacts.twitter && (
                              <LinkRow
                                label="Twitter"
                                value={assetFacts.twitter}
                                onCopy={() => copyText(assetFacts.twitter, "Copied")}
                                onOpen={() => safeOpenUrl(assetFacts.twitter)}
                              />
                            )}

                            {!!assetFacts.telegram && (
                              <LinkRow
                                label="Telegram"
                                value={assetFacts.telegram}
                                onCopy={() => copyText(assetFacts.telegram, "Copied")}
                                onOpen={() => safeOpenUrl(assetFacts.telegram)}
                              />
                            )}

                            <View
                              style={{
                                borderWidth: 1,
                                borderColor: T.border,
                                borderRadius: 16,
                                padding: 12,
                                backgroundColor: "rgba(255,255,255,0.03)",
                              }}
                            >
                              <Text style={{ color: T.dim, fontWeight: "800" }}>
                                {isRu ? "Контракты" : "Contracts"}
                              </Text>
                              {renderContractsPro(assetFacts.contractsByPlatform, copyText, currentLang)}
                            </View>
                          </View>
                        ) : (
                          <Text style={{ color: T.dim, marginTop: 12 }}>
                            {isRu ? "Факты ещё не загружены." : "No facts loaded yet."}
                          </Text>
                        )}
                      </BlurCard>
                    )}

                    {analysisRes && (
                      <>
                        <ViewShot
                          ref={shareCardRef}
                          options={{ format: "png", quality: 1, result: "tmpfile" }}
                          style={{
                            borderWidth: 1,
                            borderColor: "rgba(255,176,32,0.35)",
                            borderRadius: 22,
                            overflow: "hidden",
                            marginBottom: 14,
                            backgroundColor: "rgba(10,15,30,0.88)",
                          }}
                        >
                          <BlurView intensity={26} tint="dark" style={{ padding: 16 }}>
                            <Text style={{ color: T.logo, fontWeight: "900", fontSize: 14 }} numberOfLines={1}>
                              NOYTRIX IMMUNITY
                            </Text>

                            <View
                              style={{
                                marginTop: 10,
                                flexDirection: "row",
                                alignItems: "center",
                                justifyContent: "space-between",
                                gap: 10,
                              }}
                            >
                              <View style={{ flex: 1, minWidth: 0 }}>
                                <Text style={{ color: T.text, fontWeight: "900", fontSize: 18 }} numberOfLines={1}>
                                  {analysisRes.baseAsset} / {selected?.quoteAsset}
                                </Text>

                                <Text style={{ color: T.dim, fontWeight: "800" }} numberOfLines={1}>
                                  {analysisRes.symbol}
                                </Text>
                              </View>

                              <View style={{ alignItems: "flex-end" }}>
                                <Text style={{ color: analysisRes.color, fontWeight: "900", fontSize: 14 }}>
                                  {tVerdict(analysisRes.level)}
                                </Text>

                                <Text style={{ color: T.text, fontWeight: "900", marginTop: 2 }}>
                                  {Math.round(analysisRes.score)}/100
                                </Text>
                              </View>
                            </View>

                            <View style={{ marginTop: 12, flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
                              <Chip label={`Price: ${fmtPrice(analysisRes.marketSnapshot?.lastPrice)}`} />
                              <Chip label={`24h: ${pct(analysisRes.marketSnapshot?.priceChangePercent)}`} accent />
                              <Chip label={`Amount: $${fmtNum(analysisRes.user?.amountUsdt)}`} />
                              <Chip label={`Horizon: ${String(analysisRes.user?.horizon || "-")}`} />
                              <Chip label={`Target: ${pct(analysisRes.user?.targetPct)}`} accent />
                              <Chip label={`Max DD: ${pct(analysisRes.user?.maxDrawdownPct)}`} />
                            </View>

                            <View style={{ flexDirection: "row", gap: 12, marginTop: 14 }}>
                              <View style={{ flex: 1, minWidth: 0 }}>
                                <SecondaryButton title={isRu ? "Share" : "Share"} icon="share-outline" onPress={shareAsImage} />
                              </View>

                              {!isPro && (
                                <View style={{ flex: 1, minWidth: 0 }}>
                                  <PrimaryButton title={isRu ? "PRO" : "Go PRO"} icon="flash-outline" onPress={gotoPro} />
                                </View>
                              )}
                            </View>
                          </BlurView>
                        </ViewShot>

                        <BlurCard>
                          <Text style={{ color: T.text, fontWeight: "900", fontSize: 20 }}>
                            {isRu ? "Live review" : "Live review"}
                          </Text>

                          <Text style={{ color: T.dim, marginTop: 6, lineHeight: 19 }}>
                            {isRu
                              ? `Оценочная вероятность с дисциплиной: ~${analysisRes.review10?.probability || "-"}.`
                              : `Estimated probability with discipline: ~${analysisRes.review10?.probability || "-"}.`}
                          </Text>

                          <Text style={{ color: T.text, fontWeight: "900", marginTop: 10, fontSize: 16 }}>
                            {analysisRes.review10?.title || (isRu ? "Держи риск-лимиты." : "Keep risk limits.")}
                          </Text>

                          {!!analysisRes.review10?.summary && (
                            <Text style={{ color: T.dim, marginTop: 8, lineHeight: 19 }}>
                              {analysisRes.review10.summary}
                            </Text>
                          )}

                          <View
                            style={{
                              marginTop: 12,
                              borderWidth: 1,
                              borderColor: T.border,
                              borderRadius: 16,
                              padding: 12,
                              backgroundColor: "rgba(255,255,255,0.03)",
                            }}
                          >
                            <Text style={{ color: T.logo, fontWeight: "900" }}>
                              {isRu ? "Почему" : "Why"}
                            </Text>

                            <View style={{ marginTop: 10, gap: 8 }}>
                              {(analysisRes.review10?.why || []).map((x, i) => (
                                <RowBullet key={`why-${i}`} icon="chatbubble-ellipses-outline" color={T.logo} text={x} />
                              ))}
                            </View>
                          </View>

                          <View
                            style={{
                              marginTop: 12,
                              borderWidth: 1,
                              borderColor: "rgba(255,176,32,0.22)",
                              borderRadius: 16,
                              padding: 12,
                              backgroundColor: "rgba(255,176,32,0.08)",
                            }}
                          >
                            <Text style={{ color: T.logo, fontWeight: "900" }}>
                              {isRu ? "Что делать" : "What to do"}
                            </Text>

                            <View style={{ marginTop: 10, gap: 8 }}>
                              {(analysisRes.review10?.concrete || []).map((x, i) => (
                                <RowBullet key={`do-${i}`} icon="construct-outline" color={T.logo} text={x} />
                              ))}
                            </View>
                          </View>
                        </BlurCard>

                        {!!(
                          analysisRes.plan?.now?.length ||
                          analysisRes.plan?.fixes?.length ||
                          analysisRes.plan?.safer?.length
                        ) && (
                          <BlurCard>
                            <Text style={{ color: T.text, fontWeight: "900", fontSize: 18 }}>
                              {isRu ? "План действий" : "Action plan"}
                            </Text>

                            {!!analysisRes.plan?.now?.length && (
                              <PlanSection
                                title={isRu ? "Сейчас" : "Now"}
                                color={T.logo}
                                items={analysisRes.plan.now}
                                currentLang={currentLang}
                              />
                            )}

                            {!!analysisRes.plan?.fixes?.length && (
                              <PlanSection
                                title={isRu ? "Исправить" : "Fix"}
                                color={T.warn}
                                items={analysisRes.plan.fixes}
                                currentLang={currentLang}
                              />
                            )}

                            {!!analysisRes.plan?.safer?.length && (
                              <PlanSection
                                title={isRu ? "Безопаснее" : "Safer"}
                                color={T.good}
                                items={analysisRes.plan.safer}
                                currentLang={currentLang}
                              />
                            )}
                          </BlurCard>
                        )}

                        <BlurCard>
                          <Text style={{ color: T.text, fontWeight: "900", fontSize: 18 }}>
                            {isRu ? "Сценарии" : "Scenarios"}
                          </Text>

                          <Text style={{ color: T.dim, marginTop: 6, lineHeight: 19 }}>
                            {isRu ? "Это не прогноз, а рамка действий." : "Not a prediction. A frame: what to do if market moves."}
                          </Text>

                          <View style={{ marginTop: 12, gap: 10 }}>
                            <ScenarioCard s={analysisRes.scenarios?.bull} />
                            <ScenarioCard s={analysisRes.scenarios?.base} />
                            <ScenarioCard s={analysisRes.scenarios?.bear} />
                          </View>

                          <View
                            style={{
                              marginTop: 12,
                              borderWidth: 1,
                              borderColor: `${T.bad}33`,
                              borderRadius: 16,
                              padding: 12,
                              backgroundColor: `${T.bad}12`,
                            }}
                          >
                            <Text style={{ color: T.bad, fontWeight: "900" }}>
                              {isRu ? "Worst case" : "Worst case"}
                            </Text>

                            <View style={{ marginTop: 10, gap: 8 }}>
                              {(analysisRes.scenarios?.worst || []).map((x, i) => (
                                <RowBullet key={`w-${i}`} icon="warning-outline" color={T.bad} text={x} />
                              ))}
                            </View>
                          </View>
                        </BlurCard>
                      </>
                    )}
                  </>
                )}
              </ScrollView>

              <Modal visible={analysisOpen} animationType="slide" transparent>
                <View
                  style={{
                    flex: 1,
                    backgroundColor: "rgba(0,0,0,0.55)",
                    padding: 16,
                    justifyContent: "flex-end",
                  }}
                >
                  <View
                    style={{
                      borderRadius: 22,
                      borderWidth: 1,
                      borderColor: "rgba(255,176,32,0.35)",
                      overflow: "hidden",
                      backgroundColor: "rgba(12,16,28,0.95)",
                    }}
                  >
                    <BlurView intensity={26} tint="dark" style={{ padding: 16 }}>
                      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
                        <Text style={{ color: T.text, fontWeight: "900", fontSize: 18 }}>
                          {isRu ? "Analyze buy plan" : "Analyze buy plan"}
                        </Text>

                        <Pressable
                          onPress={() => {
                            logEvent("tap_immunity_close_analyze");
                            setAnalysisOpen(false);
                          }}
                        >
                          <Ionicons name="close" size={22} color={T.dim} />
                        </Pressable>
                      </View>

                      <Text style={{ color: T.dim, marginTop: 6, lineHeight: 19 }}>
                        {selected?.baseAsset} ({selected?.symbol})
                      </Text>

                      <View style={{ marginTop: 12, gap: 10 }}>
                        <Field label="Amount (USDT)" value={amountUsdt} onChangeText={setAmountUsdt} keyboardType="decimal-pad" placeholder="100" />

                        <Text style={{ color: T.dim, fontWeight: "800", marginTop: 4 }}>Horizon</Text>

                        <View style={{ flexDirection: "row", gap: 10 }}>
                          <Pill active={horizon === "1D"} title="1D" onPress={() => { logEvent("immunity_filter_horizon", { value: "1D" }); setHorizon("1D"); }} icon="time-outline" />
                          <Pill active={horizon === "1W"} title="1W" onPress={() => { logEvent("immunity_filter_horizon", { value: "1W" }); setHorizon("1W"); }} icon="calendar-outline" />
                          <Pill active={horizon === "1M"} title="1M" onPress={() => { logEvent("immunity_filter_horizon", { value: "1M" }); setHorizon("1M"); }} icon="calendar-number-outline" />
                          <Pill active={horizon === "6M"} title="6M" onPress={() => { logEvent("immunity_filter_horizon", { value: "6M" }); setHorizon("6M"); }} icon="trending-up-outline" />
                        </View>

                        <View style={{ flexDirection: "row", gap: 10 }}>
                          <View style={{ flex: 1, minWidth: 0 }}>
                            <Field label="Target profit (%)" value={targetPct} onChangeText={setTargetPct} keyboardType="decimal-pad" placeholder="10" />
                          </View>

                          <View style={{ flex: 1, minWidth: 0 }}>
                            <Field label="Max drawdown (%)" value={maxDdPct} onChangeText={setMaxDdPct} keyboardType="decimal-pad" placeholder="8" />
                          </View>
                        </View>

                        <Text style={{ color: T.dim, fontWeight: "800", marginTop: 4 }}>Reason</Text>

                        <View style={{ flexDirection: "row", gap: 10, flexWrap: "wrap" }}>
                          <Pill active={reason === "NEWS"} title="News" onPress={() => { logEvent("immunity_filter_reason", { value: "NEWS" }); setReason("NEWS"); }} icon="newspaper-outline" />
                          <Pill active={reason === "CHART"} title="Chart" onPress={() => { logEvent("immunity_filter_reason", { value: "CHART" }); setReason("CHART"); }} icon="analytics-outline" />
                          <Pill active={reason === "HYPE"} title="Hype" onPress={() => { logEvent("immunity_filter_reason", { value: "HYPE" }); setReason("HYPE"); }} icon="flame-outline" />
                          <Pill active={reason === "STRATEGY"} title="Strategy" onPress={() => { logEvent("immunity_filter_reason", { value: "STRATEGY" }); setReason("STRATEGY"); }} icon="checkbox-outline" />
                        </View>

                        <Pressable
                          onPress={() => { logEvent("immunity_toggle_holding", { next: !alreadyHolding }); setAlreadyHolding((v) => !v); }}
                          style={{
                            borderWidth: 1,
                            borderColor: alreadyHolding ? "rgba(255,176,32,0.55)" : T.border,
                            backgroundColor: alreadyHolding ? "rgba(255,176,32,0.12)" : "rgba(255,255,255,0.04)",
                            paddingVertical: 10,
                            paddingHorizontal: 12,
                            borderRadius: 16,
                            flexDirection: "row",
                            gap: 8,
                            alignItems: "center",
                            justifyContent: "space-between",
                          }}
                        >
                          <Text style={{ color: T.text, fontWeight: "900" }}>
                            {isRu ? "Уже держишь актив?" : "Already holding this asset?"}
                          </Text>

                          <Ionicons
                            name={alreadyHolding ? "checkmark-circle-outline" : "ellipse-outline"}
                            size={20}
                            color={alreadyHolding ? T.logo : T.dim}
                          />
                        </Pressable>
                      </View>

                      <View style={{ flexDirection: "row", gap: 12, marginTop: 14 }}>
                        <View style={{ flex: 1, minWidth: 0 }}>
                          <SecondaryButton title={isRu ? "Cancel" : "Cancel"} icon="close-outline" onPress={() => setAnalysisOpen(false)} />
                        </View>

                        <View style={{ flex: 1, minWidth: 0 }}>
                          <PrimaryButton
                            title={analyzing ? "Analyzing…" : "Analyze"}
                            icon="sparkles-outline"
                            onPress={runAnalysis}
                            disabled={analyzing}
                          />
                        </View>
                      </View>

                      {analyzing && (
                        <View style={{ marginTop: 10, flexDirection: "row", alignItems: "center", gap: 10 }}>
                          <ActivityIndicator />
                          <Text style={{ color: T.dim }}>Risk Engine + verification…</Text>
                        </View>
                      )}
                    </BlurView>
                  </View>
                </View>
              </Modal>
            </LinearGradient>
          </View>
        </View>
      </Modal>
    </LinearGradient>
  );
}

function BlurCard({ children, style, intensity = 24 }) {
  return (
    <View
      style={[
        {
          borderWidth: 1,
          borderColor: T.border,
          borderRadius: 22,
          overflow: "hidden",
          marginBottom: 14,
          backgroundColor: "rgba(255,255,255,0.035)",
        },
        style,
      ]}
    >
      <BlurView intensity={intensity} tint="dark" style={{ padding: 16 }}>
        {children}
      </BlurView>
    </View>
  );
}

function PrimaryButton({ title, icon, onPress, disabled }) {
  return (
    <TouchableOpacity
      activeOpacity={0.9}
      onPress={disabled ? undefined : onPress}
      style={{
        opacity: disabled ? 0.6 : 1,
        backgroundColor: T.logo,
        borderRadius: 16,
        paddingVertical: 13,
        paddingHorizontal: 14,
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
      }}
    >
      {!!icon && <Ionicons name={icon} size={17} color={T.accentText} />}
      <Text style={{ color: T.accentText, fontWeight: "900" }}>{title}</Text>
    </TouchableOpacity>
  );
}

function SecondaryButton({ title, icon, onPress }) {
  return (
    <TouchableOpacity
      activeOpacity={0.9}
      onPress={onPress}
      style={{
        borderWidth: 1,
        borderColor: T.border,
        backgroundColor: "rgba(255,255,255,0.05)",
        borderRadius: 16,
        paddingVertical: 13,
        paddingHorizontal: 14,
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
      }}
    >
      {!!icon && <Ionicons name={icon} size={17} color={T.text} />}
      <Text style={{ color: T.text, fontWeight: "900" }}>{title}</Text>
    </TouchableOpacity>
  );
}

function Pill({ active, title, icon, onPress }) {
  return (
    <Pressable
      onPress={onPress}
      style={{
        flexGrow: 1,
        borderWidth: 1,
        borderColor: active ? "rgba(255,176,32,0.55)" : T.border,
        backgroundColor: active ? "rgba(255,176,32,0.12)" : "rgba(255,255,255,0.04)",
        paddingVertical: 10,
        paddingHorizontal: 12,
        borderRadius: 999,
        flexDirection: "row",
        gap: 7,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {!!icon && <Ionicons name={icon} size={16} color={active ? T.logo : T.dim} />}
      <Text style={{ color: active ? T.logo : T.dim, fontWeight: "900", fontSize: 12 }}>{title}</Text>
    </Pressable>
  );
}

function InfoCard({ title, text }) {
  return (
    <BlurCard>
      <Text style={{ color: T.text, fontWeight: "900", fontSize: 18 }}>{title}</Text>
      <Text style={{ color: T.dim, marginTop: 8, lineHeight: 19 }}>{text}</Text>
    </BlurCard>
  );
}

function Chip({ label, accent }) {
  return (
    <View
      style={{
        paddingVertical: 8,
        paddingHorizontal: 12,
        borderRadius: 999,
        borderWidth: 1,
        borderColor: accent ? "rgba(255,176,32,0.40)" : "rgba(255,255,255,0.10)",
        backgroundColor: accent ? "rgba(255,176,32,0.10)" : "rgba(255,255,255,0.03)",
      }}
    >
      <Text style={{ color: accent ? T.logo : T.text, fontWeight: "900", fontSize: 12 }}>{label}</Text>
    </View>
  );
}

function RowBullet({ icon, color, text }) {
  return (
    <View style={{ flexDirection: "row", gap: 10, alignItems: "flex-start" }}>
      <Ionicons name={icon} size={18} color={color || T.logo} style={{ marginTop: 1 }} />
      <Text style={{ color: T.text, fontWeight: "800", lineHeight: 19, flex: 1 }}>{text}</Text>
    </View>
  );
}

function PlanSection({ title, color, items, currentLang }) {
  return (
    <View style={{ marginTop: 14 }}>
      <Text style={{ color, fontWeight: "900", marginBottom: 8 }}>{title}</Text>
      <View style={{ gap: 8 }}>
        {(items || []).map((item, idx) => (
          <RowBullet
            key={`${title}-${idx}`}
            icon="flash-outline"
            color={color}
            text={item?.text || planCodeLabel(item?.code, currentLang)}
          />
        ))}
      </View>
    </View>
  );
}

function ScenarioCard({ s }) {
  if (!s) return null;

  return (
    <View
      style={{
        borderWidth: 1,
        borderColor: T.border,
        borderRadius: 16,
        padding: 12,
        backgroundColor: "rgba(255,255,255,0.03)",
      }}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
        <Text style={{ color: T.logo, fontWeight: "900" }}>{s.title}</Text>
        <Text style={{ color: T.text, fontWeight: "900" }}>{s.move}</Text>
      </View>

      <Text style={{ color: T.dim, marginTop: 6, lineHeight: 18 }}>{s.note}</Text>
      <Text style={{ color: T.text, marginTop: 8, fontWeight: "800", lineHeight: 18 }}>{s.advice}</Text>
    </View>
  );
}

function Field({ label, value, onChangeText, placeholder, keyboardType = "default" }) {
  return (
    <View>
      <Text style={{ color: T.dim, fontWeight: "800", marginBottom: 6 }}>{label}</Text>

      <View
        style={{
          borderWidth: 1,
          borderColor: T.borderSoft,
          borderRadius: 16,
          backgroundColor: "rgba(255,255,255,0.05)",
          paddingHorizontal: 12,
        }}
      >
        <TextInput
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor={T.dim}
          keyboardType={keyboardType}
          style={{ color: T.text, height: 48, fontSize: 16 }}
        />
      </View>
    </View>
  );
}

function MetaBox({ label, value, onCopy }) {
  return (
    <Pressable
      onPress={onCopy}
      style={{
        flexGrow: 1,
        minWidth: 160,
        borderWidth: 1,
        borderColor: T.border,
        borderRadius: 16,
        padding: 12,
        backgroundColor: "rgba(255,255,255,0.03)",
      }}
    >
      <Text style={{ color: T.dim, marginBottom: 6 }}>{label}</Text>

      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <Text style={{ color: T.text, fontWeight: "900" }}>{String(value ?? "-")}</Text>
        <Ionicons name="copy-outline" size={16} color={T.dim} />
      </View>
    </Pressable>
  );
}

function CopyRow({ label, value, onCopy }) {
  return (
    <Pressable
      onPress={onCopy}
      style={{
        borderWidth: 1,
        borderColor: T.border,
        borderRadius: 16,
        padding: 12,
        backgroundColor: "rgba(255,255,255,0.03)",
      }}
    >
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <Text style={{ color: T.dim, fontWeight: "800" }}>{label}</Text>
        <Ionicons name="copy-outline" size={16} color={T.dim} />
      </View>

      <Text style={{ color: T.text, fontWeight: "800", marginTop: 6, lineHeight: 18, fontSize: 14 }}>
        {String(value ?? "-")}
      </Text>
    </Pressable>
  );
}

function LinkRow({ label, value, onCopy, onOpen }) {
  const canOpen = isProbablyUrl(value);

  return (
    <View
      style={{
        borderWidth: 1,
        borderColor: T.border,
        borderRadius: 16,
        padding: 12,
        backgroundColor: "rgba(255,255,255,0.03)",
        gap: 10,
      }}
    >
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <Text style={{ color: T.dim, fontWeight: "800" }}>{label}</Text>

        <View style={{ flexDirection: "row", gap: 10, alignItems: "center" }}>
          <Pressable onPress={onCopy} style={{ padding: 6 }}>
            <Ionicons name="copy-outline" size={16} color={T.dim} />
          </Pressable>

          <Pressable onPress={canOpen ? onOpen : undefined} style={{ padding: 6, opacity: canOpen ? 1 : 0.35 }}>
            <Ionicons name="open-outline" size={16} color={T.dim} />
          </Pressable>
        </View>
      </View>

      <Text
        style={{
          color: T.text,
          fontWeight: "800",
          lineHeight: 18,
          fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
          fontSize: 12,
        }}
      >
        {String(value ?? "-")}
      </Text>
    </View>
  );
}

function AlertBox({ title, text, color, children }) {
  return (
    <View
      style={{
        borderWidth: 1,
        borderColor: color ? `${color}66` : T.border,
        backgroundColor: color ? `${color}14` : "rgba(255,255,255,0.03)",
        borderRadius: 16,
        padding: 12,
      }}
    >
      <Text style={{ color: color || T.logo, fontWeight: "900", fontSize: 14 }}>{title}</Text>

      {!!text && (
        <Text style={{ color: T.text, fontWeight: "800", marginTop: 8, lineHeight: 18 }}>
          {String(text)}
        </Text>
      )}

      {children}
    </View>
  );
}

function renderContractsPro(platforms, copyTextFn, lang = "en") {
  const entries = Object.entries(platforms || {}).filter(([, addr]) => !!addr);

  if (!entries.length) {
    return (
      <Text style={{ color: T.dim, marginTop: 8 }}>
        {pickLang(lang, "Контракт не указан или это native coin.", "No contract or native coin.")}
      </Text>
    );
  }

  return (
    <View style={{ marginTop: 8, gap: 8 }}>
      {entries.slice(0, 10).map(([chain, addr]) => {
        const explorer = buildExplorerUrl(chain, addr);

        return (
          <View
            key={chain}
            style={{
              borderWidth: 1,
              borderColor: T.borderSoft,
              borderRadius: 14,
              padding: 10,
              backgroundColor: "rgba(255,255,255,0.04)",
              gap: 8,
            }}
          >
            <Text style={{ color: T.dim, fontWeight: "800" }}>{chain}</Text>

            <Pressable onPress={() => copyTextFn(String(addr), pickLang(lang, "Контракт скопирован", "Contract copied"))}>
              <Text
                style={{
                  color: T.text,
                  fontWeight: "900",
                  fontSize: 12,
                  fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
                }}
                numberOfLines={2}
              >
                {String(addr)}
              </Text>
            </Pressable>

            <View style={{ flexDirection: "row", gap: 10 }}>
              <Pressable
                onPress={() => copyTextFn(String(addr), pickLang(lang, "Контракт скопирован", "Contract copied"))}
                style={{
                  paddingVertical: 8,
                  paddingHorizontal: 10,
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: T.border,
                  backgroundColor: "rgba(255,255,255,0.03)",
                  flexDirection: "row",
                  gap: 8,
                  alignItems: "center",
                }}
              >
                <Ionicons name="copy-outline" size={16} color={T.dim} />
                <Text style={{ color: T.text, fontWeight: "900", fontSize: 12 }}>
                  {pickLang(lang, "Copy", "Copy")}
                </Text>
              </Pressable>

              <Pressable
                onPress={explorer ? () => safeOpenUrl(explorer) : undefined}
                style={{
                  paddingVertical: 8,
                  paddingHorizontal: 10,
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: explorer ? "rgba(255,176,32,0.45)" : T.border,
                  backgroundColor: explorer ? "rgba(255,176,32,0.10)" : "rgba(255,255,255,0.03)",
                  flexDirection: "row",
                  gap: 8,
                  alignItems: "center",
                  opacity: explorer ? 1 : 0.35,
                }}
              >
                <Ionicons name="open-outline" size={16} color={explorer ? T.logo : T.dim} />

                <Text style={{ color: explorer ? T.logo : T.dim, fontWeight: "900", fontSize: 12 }}>
                  {pickLang(lang, "Verify", "Verify")}
                </Text>
              </Pressable>
            </View>
          </View>
        );
      })}
    </View>
  );
}



