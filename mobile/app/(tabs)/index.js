// app/(tabs)/index.js
import React, { useCallback, useEffect, useMemo, useState, useRef } from "react";
import {
  SafeAreaView,
  View,
  Text,
  TextInput,
  ScrollView,
  TouchableOpacity,
  Modal,
  Pressable,
  ActivityIndicator,
  Share,
  Platform,
  InteractionManager,
} from "react-native";
import { Ionicons, FontAwesome5 } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { BlurView } from "expo-blur";
import ViewShot from "react-native-view-shot";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Linking from "expo-linking";
import * as Sharing from "expo-sharing";
import { useTranslation } from "react-i18next";

import { logEvent } from "../lib/analytics";
import { showAppAlert } from "../lib/appAlert";
import { recordReviewPromptScan } from "../lib/reviewPrompt";
import { useAuthStore } from "../lib/store.auth";
import NoyBot from "../../components/NoyBot";

const BACKEND = "https://noytrix.com";
const AUTH_KEY = "auth_state_v1";
const INSTALL_UID_KEY = "noytrix.installUserId";
const SHIELD_PREFILL_KEY = "shield.prefill";

const GRAD = { start: "#06080f", mid: "#0a1233", end: "#0b1c4f" };

const C = {
  logo: "#ffb020",
  text: "#e9ecff",
  dim: "#A8B4CF",
  accent: "#ffb020",
  accentText: "#0b1220",
  border: "rgba(255,255,255,0.10)",
  borderSoft: "rgba(255,255,255,0.07)",
  good: "#29d37a",
  warn: "#FFB547",
  bad: "#FF6B6B",
};

const cardChrome = {
  borderRadius: 22,
  borderWidth: 1,
  borderColor: C.border,
  overflow: "hidden",
  shadowColor: "rgba(255,255,255,0.06)",
  shadowOpacity: 1,
  shadowRadius: 14,
  shadowOffset: { width: 0, height: 6 },
  elevation: 3,
};

const BlurCard = ({ children, style, intensity = 26 }) => (
  <View style={[cardChrome, { marginBottom: 14 }, style]}>
    <BlurView intensity={intensity} tint="dark" style={{ padding: 16, borderRadius: 22 }}>
      {children}
    </BlurView>
  </View>
);

const PrimaryButton = ({ title, onPress, disabled, style, leftIcon, bg = C.accent, textColor = C.accentText }) => (
  <TouchableOpacity
    activeOpacity={0.9}
    onPress={onPress}
    disabled={disabled}
    style={[
      {
        height: 54,
        borderRadius: 18,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: bg,
        opacity: disabled ? 0.65 : 1,
        flexDirection: "row",
        paddingHorizontal: 18,
      },
      style,
    ]}
  >
    {!!leftIcon && <View style={{ marginRight: 10 }}>{leftIcon}</View>}
    <Text style={{ color: textColor, fontWeight: "900", fontSize: 16 }} numberOfLines={1}>
      {title}
    </Text>
  </TouchableOpacity>
);

const SecondaryButton = ({ title, onPress, disabled, style, leftIcon }) => (
  <TouchableOpacity
    activeOpacity={0.9}
    onPress={onPress}
    disabled={disabled}
    style={[
      {
        height: 50,
        borderRadius: 17,
        alignItems: "center",
        justifyContent: "center",
        borderWidth: 1,
        borderColor: C.border,
        backgroundColor: "rgba(255,255,255,0.04)",
        paddingHorizontal: 14,
        opacity: disabled ? 0.55 : 1,
        flexDirection: "row",
      },
      style,
    ]}
  >
    {!!leftIcon && <View style={{ marginRight: 8 }}>{leftIcon}</View>}
    <Text style={{ color: C.text, fontWeight: "800", fontSize: 14 }} numberOfLines={1}>
      {title}
    </Text>
  </TouchableOpacity>
);

const reIsHttp = /^https?:\/\//i;
const reIsEth = /^0x[a-f0-9]{40}$/i;
const reTicker = /^[A-Z0-9._-]{2,15}$/i;

function normalizeAppLang(value) {
  const s = String(value || "en").toLowerCase();
  if (s.startsWith("ru")) return "ru";
  if (s.startsWith("uk") || s.startsWith("ua")) return "uk";
  return "en";
}

function pickLang(lang, ru, en, uk) {
  const normalized = normalizeAppLang(lang);
  if (normalized === "ru") return ru;
  if (normalized === "uk") return uk || en;
  return en;
}


function uidFrom(name, email, nick) {
  return (email || nick || name || "").toString().trim().toLowerCase();
}

function makeRandomId() {
  return `guest_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

async function getOrCreateInstallUserId() {
  try {
    const existing = await AsyncStorage.getItem(INSTALL_UID_KEY);
    if (existing && String(existing).trim()) return String(existing).trim();
    const next = makeRandomId();
    await AsyncStorage.setItem(INSTALL_UID_KEY, next);
    return next;
  } catch {
    return makeRandomId();
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

function parseJwtPayload(token) {
  try {
    const raw = String(token || "").trim();
    if (!raw || raw.split(".").length < 2) return null;

    const base64 = raw.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);

    let json = "";
    if (typeof atob === "function") {
      json = decodeURIComponent(
        Array.prototype.map
          .call(atob(padded), (c) => `%${("00" + c.charCodeAt(0).toString(16)).slice(-2)}`)
          .join("")
      );
    } else if (typeof global !== "undefined" && global?.Buffer) {
      json = global.Buffer.from(padded, "base64").toString("utf8");
    } else {
      return null;
    }

    return JSON.parse(json);
  } catch {
    return null;
  }
}

function uidFromJwtPayload(payload) {
  if (!payload || typeof payload !== "object") return "";
  const raw =
    payload.email ||
    payload.user_email ||
    payload.preferred_username ||
    payload.username ||
    payload.nick ||
    payload.name ||
    payload.userId ||
    payload.user_id ||
    payload.uid ||
    payload.sub ||
    "";

  const s = String(raw || "").trim().toLowerCase();
  if (!s || s.startsWith("guest_") || s === "anonymous" || s === "null" || s === "undefined") return "";
  return s;
}

async function getBestKnownUid(user, installUid = "", accessToken = "") {
  const direct = uidFrom(user?.name, user?.email, user?.nick);
  if (direct && !direct.startsWith("guest_") && direct !== "anonymous" && direct !== "null" && direct !== "undefined") {
    return direct;
  }

  const payloadUid = uidFromJwtPayload(parseJwtPayload(accessToken));
  if (payloadUid) return payloadUid;

  try {
    const authState = await getAuthStateV1();
    const authUser = authState?.user || null;

    const stateDirect = uidFrom(authUser?.name, authUser?.email, authUser?.nick);
    if (stateDirect && !stateDirect.startsWith("guest_") && stateDirect !== "anonymous") return stateDirect;

    const stateJwtUid = uidFromJwtPayload(parseJwtPayload(authState?.access_token || ""));
    if (stateJwtUid) return stateJwtUid;
  } catch {}

  if (installUid && String(installUid).trim()) return String(installUid).trim();
  return "anonymous";
}

async function loadProProof() {
  const pick = async (keys) => {
    for (const k of keys) {
      try {
        const v = await AsyncStorage.getItem(k);
        if (v != null && String(v).trim() !== "") return String(v);
      } catch {}
    }
    return null;
  };

  const authState = await getAuthStateV1();

  const accessToken =
    authState?.access_token ||
    (await pick(["accessToken", "auth.accessToken", "user.accessToken", "jwt", "token", "access"]));

  return {
    purchaseToken: await pick(["play.purchaseToken", "google.play.purchaseToken", "iap.purchaseToken", "purchaseToken", "pro.purchaseToken"]),
    productId: await pick(["play.productId", "google.play.productId", "iap.productId", "productId", "pro.productId"]),
    entitlementId: await pick(["entitlement.id", "entitlementId", "iap.entitlementId", "pro.entitlementId"]),
    accessToken: accessToken || null,
    authUser: authState?.user || null,
  };
}

async function safeFetchRaw(url, options = {}, timeoutMs = 18000) {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: ctrl.signal });
  } finally {
    clearTimeout(id);
  }
}

function detectKind(raw) {
  const x = String(raw || "").trim();
  if (!x) return "text";
  if (reIsHttp.test(x)) return "url";
  if (reIsEth.test(x)) return "wallet";
  if (x.includes(".") && !x.includes(" ")) return "domain";
  if (reTicker.test(x) && !x.includes(" ")) return "ticker";
  return "text";
}

function normalizeKind(kind, raw) {
  const k = String(kind || "").toLowerCase();
  if (["url", "domain", "wallet", "contract", "transaction", "ticker", "text"].includes(k)) return k;
  return detectKind(raw);
}

function safeText(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v.length ? v : "—";
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

function compactMiddle(text = "", head = 34, tail = 14) {
  const s = String(text || "");
  if (s.length <= head + tail + 3) return s;
  return `${s.slice(0, head)}...${s.slice(-tail)}`;
}

function levelColor(level) {
  const s = String(level || "").toLowerCase();
  if (s === "critical") return C.bad;
  if (s === "danger") return "#ff7b7b";
  if (s === "suspicious") return C.warn;
  return C.good;
}

function levelBg(level) {
  const s = String(level || "").toLowerCase();
  if (s === "critical") return "rgba(255,107,107,0.15)";
  if (s === "danger") return "rgba(255,123,123,0.13)";
  if (s === "suspicious") return "rgba(255,181,71,0.13)";
  return "rgba(41,211,122,0.13)";
}

function formatKindLabel(kind, localized, lang) {
  if (localized) return localized;
  const k = String(kind || "").toLowerCase();
  if (k === "url") return "URL";
  if (k === "domain") return pickLang(lang, "Домен", "Domain", "Домен");
  if (k === "wallet") return pickLang(lang, "Кошелёк", "Wallet", "Гаманець");
  if (k === "contract") return pickLang(lang, "Контракт", "Contract", "Контракт");
  if (k === "ticker") return pickLang(lang, "Тикер", "Ticker", "Тикер");
  return pickLang(lang, "Текст", "Text", "Текст");
}

function formatLevelLabel(level, lang) {
  const s = String(level || "").toLowerCase();
  if (s === "critical") return pickLang(lang, "Критический", "Critical", "Критичний");
  if (s === "danger") return pickLang(lang, "Опасно", "Danger", "Небезпечно");
  if (s === "suspicious") return pickLang(lang, "Подозрительно", "Suspicious", "Підозріло");
  return pickLang(lang, "Безопасно", "Safe", "Безпечно");
}

function getAiVerdictText(raw) {
  const result = raw?.ai_explanation_result || null;
  const structured = result && typeof result === "object" ? result.structured || null : null;
  const chunks = [];
  const add = (value) => {
    if (Array.isArray(value)) {
      value.forEach(add);
      return;
    }
    const text = typeof value === "string" ? value.trim() : "";
    if (text && !chunks.includes(text)) chunks.push(text);
  };

  add(structured?.details);
  add(structured?.attack_scenario);
  add(structured?.hidden_danger);
  add(structured?.attacker_intent);
  add(structured?.loss_scenario);
  add(structured?.risks);
  add(structured?.actions);
  add(structured?.confidence_note);
  add(structured?.short);
  add(result?.text);
  add(raw?.ai_explanation);

  return chunks.join("\n\n").trim();
}

function formatSourceName(name, lang) {
  const map = {
    virustotal: "VirusTotal",
    google_safe_browsing: "Google Safe Browsing",
    urlscan: "urlscan",
    page_fetch: pickLang(lang, "Анализ страницы", "Page analysis"),
    etherscan: "Etherscan",
    bscscan: "BscScan",
    dexscreener: "DexScreener",
    coingecko: "CoinGecko",
    text_heuristics: pickLang(lang, "Анализ текста", "Text analysis"),
    honeypot: "Honeypot",
  };
  return map[name] || safeText(name);
}

function sourceStatusColor(status) {
  const s = String(status || "").toLowerCase();
  if (s === "malicious") return C.bad;
  if (s === "clean") return C.good;
  if (["timeout", "quota", "invalid_key", "error"].includes(s)) return C.warn;
  return C.dim;
}

function sourceStatusBg(status) {
  const s = String(status || "").toLowerCase();
  if (s === "malicious") return "rgba(255,107,107,0.14)";
  if (s === "clean") return "rgba(41,211,122,0.14)";
  if (["timeout", "quota", "invalid_key", "error"].includes(s)) return "rgba(255,181,71,0.14)";
  return "rgba(255,255,255,0.06)";
}

function formatSourceStatusText(status, item, lang) {
  const s = String(status || "").toLowerCase();
  if (s === "clean") return pickLang(lang, "Чисто", "Clean");
  if (s === "malicious") return pickLang(lang, "Опасно", "Malicious");
  if (s === "no_data") return pickLang(lang, "Нет данных", "No data");
  if (s === "timeout") return pickLang(lang, "Таймаут", "Timeout");
  if (s === "quota") return pickLang(lang, "Лимит", "Limit");
  if (s === "invalid_key") return pickLang(lang, "Нет ключа", "No key");
  if (s === "error") return pickLang(lang, "Ошибка", "Error");

  const rawStatusText = String(item?.status_text || "").trim();
  if (rawStatusText && rawStatusText.length < 40) return rawStatusText;
  return pickLang(lang, "Недоступно", "Unavailable");
}

function prettyTitleFromCode(code, lang) {
  const map = {
    vt_detection: pickLang(lang, "Внешний источник нашёл угрозу", "External threat flags"),
    gsb_match: pickLang(lang, "Google подтвердил угрозу", "Google confirmed a threat"),
    seed_phrase_request: pickLang(lang, "Запрос seed phrase", "Seed phrase request"),
    private_key_request: pickLang(lang, "Запрос private key", "Private key request"),
    wallet_connect_prompt: pickLang(lang, "Запрос подключения кошелька", "Wallet connect prompt"),
    claim_prompt: pickLang(lang, "Агрессивный claim prompt", "Aggressive claim prompt"),
    airdrop_language: pickLang(lang, "Подозрительный airdrop текст", "Suspicious airdrop wording"),
    verify_wallet_prompt: pickLang(lang, "Запрос верификации кошелька", "Wallet verification request"),
    fake_support_language: pickLang(lang, "Похоже на fake support", "Fake support signs"),
    wallet_import_prompt: pickLang(lang, "Запрос импорта кошелька", "Wallet import prompt"),
    wallet_drainer_hint: pickLang(lang, "Признаки drainer", "Drainer warning signs"),
    brand_spoofing: pickLang(lang, "Риск подделки бренда", "Brand spoofing risk"),
    brand_impersonation: pickLang(lang, "Имитация бренда", "Brand impersonation"),
    redirect_to_different_host: pickLang(lang, "Редирект на другой домен", "Redirect to different domain"),
    honeypot_detected: pickLang(lang, "Высокий sell-risk", "High sell-risk detected"),
    ticker_found: pickLang(lang, "Тикер найден", "Ticker found"),
    page_loaded: pickLang(lang, "Страница загружена", "Page loaded"),
  };

  if (map[code]) return map[code];

  const pretty = String(code || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());

  return pretty || pickLang(lang, "Сигнал", "Signal");
}

function prettyEvidenceText(item, lang) {
  const code = String(item?.code || "").trim();

  const map = {
    seed_phrase_request: pickLang(lang, "Объект запрашивает seed phrase. Это сильный признак скама.", "The object asks for a seed phrase. This is a strong scam signal."),
    private_key_request: pickLang(lang, "Объект запрашивает private key. Это критический риск.", "The object asks for a private key. This is a critical risk."),
    wallet_connect_prompt: pickLang(lang, "Есть активный призыв подключить кошелёк. Будь осторожен.", "There is a strong wallet connection prompt. Be careful."),
    brand_spoofing: pickLang(lang, "Домен похож на известный бренд, но не совпадает с официальным адресом.", "The domain looks like a known brand but does not match the official address."),
    vt_detection: pickLang(lang, "Один из внешних движков отметил объект как опасный.", "One of the external engines flagged this object as dangerous."),
    gsb_match: pickLang(lang, "Google Safe Browsing подтвердил угрозу.", "Google Safe Browsing confirmed a threat."),
    page_loaded: pickLang(lang, "Страница была загружена и проверена по содержанию.", "The page was loaded and analyzed by content."),
    honeypot_detected: pickLang(lang, "Есть признаки, что продажа может быть ограничена.", "There are signs that selling may be restricted."),
  };

  if (map[code]) return map[code];
  if (item?.text && typeof item.text === "string" && item.text.trim()) return item.text;
  return pickLang(lang, "Детали доступны в полном разборе.", "More details are available in the full report.");
}

function normalizeScanReport(raw, currentLang) {
  if (!raw || typeof raw !== "object") return null;

  const kind = normalizeKind(raw.kind, raw.input || raw.normalized_input || "");
  const score = Number(raw.score || 0) || 0;
  const level = String(raw.level || "safe").toLowerCase();

  return {
    ...raw,
    kind,
    score,
    level,
    kindLabel: formatKindLabel(kind, raw.kind_localized, currentLang),
    levelLabel: formatLevelLabel(level, currentLang),
    verdictLabel:
      raw.ai_verdict_localized ||
      raw.verdict_localized ||
      (currentLang === "ru" ? raw.ai_verdict_ru || raw.verdict_ru : currentLang === "uk" ? raw.ai_verdict_uk || raw.verdict_uk : raw.ai_verdict_en || raw.verdict_en) ||
      raw.ai_verdict ||
      raw.verdict ||
      raw.level ||
      "",
    sources: Array.isArray(raw.sources) ? raw.sources : [],
    evidence: Array.isArray(raw.evidence) ? raw.evidence : [],
    details: raw.details || {},
    what_can_happen: raw.what_can_happen || "",
    worst_case: raw.worst_case || "",
    permissions_summary: raw.permissions_summary || null,
    risk_reasons: Array.isArray(raw.risk_reasons) ? raw.risk_reasons : [],
    quota: raw.quota || null,
    aiHumanVerdict: getAiVerdictText(raw),
    aiExplanationResult: raw.ai_explanation_result || null,
  };
}

function explainBackendMessage(raw, lang) {
  const s = String(raw || "").toLowerCase();

  if (s.includes("429") || s.includes("quota") || s.includes("limit")) {
    return pickLang(lang, "FREE лимит на сегодня уже использован. PRO убирает лимиты.", "Your free daily checks are already used. PRO removes limits.");
  }
  if (s.includes("403") || s.includes("forbidden") || s.includes("app key")) {
    return pickLang(lang, "Проверка временно недоступна из-за ограничения доступа.", "The check is currently unavailable because of access restrictions.");
  }
  if (s.includes("network request failed") || s.includes("failed to fetch") || s.includes("fetch")) {
    return pickLang(lang, "Не удалось подключиться к серверу. Проверь интернет.", "Could not reach the server. Check your connection.");
  }
  if (s.includes("timeout") || s.includes("aborted")) {
    return pickLang(lang, "Сервер слишком долго отвечает. Попробуй ещё раз.", "The server took too long to respond. Try again.");
  }
  if (s.includes("invalid json")) {
    return pickLang(lang, "Сервер вернул неполный ответ. Запусти проверку ещё раз.", "The server returned an incomplete response. Try again.");
  }

  return pickLang(lang, "Проверку не удалось завершить. Попробуй ещё раз.", "The check could not be completed. Try again.");
}

const SAMPLES = [
  { h: "https://binance-airdrop-bonus.net", dRu: "Фишинг под Binance", dEn: "Phishing pretending to be Binance", dUk: "Фішинг під Binance" },
  { h: "https://metamask-support-login.com", dRu: "Фейковая поддержка MetaMask", dEn: "Fake MetaMask support", dUk: "Фейкова підтримка MetaMask" },
  { h: "http://paypal.com.verify-account-security.com", dRu: "Ловушка с поддоменом PayPal", dEn: "PayPal subdomain trap", dUk: "Пастка з піддоменом PayPal" },
  { h: "0x1111111254EEB25477B68fB85Ed929F73A960582", dRu: "EVM адрес / контракт", dEn: "EVM address / contract", dUk: "EVM адреса / контракт" },
  { h: "BTC", dRu: "Проверка тикера", dEn: "Ticker check", dUk: "Перевірка тикера" },
  { h: "connect wallet to claim reward now enter seed phrase", dRu: "Опасный текст", dEn: "Dangerous text", dUk: "Небезпечний текст" },
];

const HK = (uid) => `profile.${uid}:history`;

async function appendHistory(uid, event) {
  if (!uid) return;
  try {
    const raw = await AsyncStorage.getItem(HK(uid));
    const arr = raw ? JSON.parse(raw) : [];
    const next = [{ ...event }, ...arr].slice(0, 200);
    await AsyncStorage.setItem(HK(uid), JSON.stringify(next));
  } catch {}
}


const UxRiskBlock = ({ report, currentLang }) => {
  if (!report) return null;

  const isRu = currentLang === "ru";
  const permissions = report?.permissions_summary || null;
  const tokens = Array.isArray(permissions?.tokens) ? permissions.tokens.filter(Boolean) : [];
  const kind = String(report?.kind || "").toLowerCase();

  let whatText = String(report?.what_can_happen || "").trim();
  let worstText = String(report?.worst_case || "").trim();

  const tokenText =
    tokens.length === 1 ? tokens[0] :
    tokens.length > 1 ? tokens.join(", ") :
    "";

  if (tokenText) {
    whatText = whatText.replace(/tokens/gi, tokenText);
    worstText = worstText.replace(/tokens/gi, tokenText);
  }

  const hasRealPermissions =
    !!permissions &&
    (kind === "wallet" || kind === "contract" || kind === "transaction" || permissions?.can_spend === true) &&
    (
      permissions.can_spend === true ||
      permissions.unlimited === true ||
      tokens.length > 0 ||
      permissions.spender ||
      permissions.spender_label ||
      permissions.spender_trust ||
      (permissions.spend_limit && permissions.spend_limit !== "unknown" && permissions.spend_limit !== "?")
    );

  const rows = [
    whatText ? {
      icon: "flame-outline",
      title: isRu ? "Что может произойти" : "What can happen",
      text: whatText,
      color: C.warn,
    } : null,

    worstText ? {
      icon: "skull-outline",
      title: isRu ? "Худший сценарий" : "Worst case",
      text: worstText,
      color: C.bad,
    } : null,

    ...(hasRealPermissions ? [{
      icon: "key-outline",
      title: pickLang(currentLang, "Что ты подтверждаешь", "What you are approving", "Що ти підтверджуєш"),
      text: String(permissions?.summary || permissions?.note || "").trim(),
      color: C.accent,
      revokeUrl: permissions?.can_spend === true ? "https://revoke.cash/" : "",
      extra: [
        permissions.can_spend === true ? `${pickLang(currentLang, "Может списывать", "Can spend", "Може списувати")}: ${pickLang(currentLang, "да", "yes", "так")}` : "",
        permissions.unlimited === true ? `${pickLang(currentLang, "Лимит списания", "Spend limit", "Ліміт списання")}: ${pickLang(currentLang, "безлимитный", "unlimited", "безлімітний")}` : "",
        permissions.spend_limit && permissions.spend_limit !== "unknown" && permissions.spend_limit !== "?" ? `${pickLang(currentLang, "Лимит списания", "Spend limit", "Ліміт списання")}: ${safeText(permissions.spend_limit)}` : "",
        tokens.length ? `${pickLang(currentLang, "Токены", "Tokens", "Токени")}: ${tokens.join(", ")}` : "",
        permissions?.spender_trust ? `${pickLang(currentLang, "Репутация spender", "Spender reputation", "Репутація spender")}: ${permissions.spender_trust}` : "",
        permissions?.spender_label ? `${pickLang(currentLang, "Кто получает доступ", "Spender", "Хто отримує доступ")}: ${permissions.spender_label}` : permissions?.spender ? `${pickLang(currentLang, "Кто получает доступ", "Spender", "Хто отримує доступ")}: ${permissions.spender}` : "",
      ].filter(Boolean),
    }] : []),
  ].filter(Boolean);

  if (!rows.length) return null;

  return (
    <BlurCard style={{ borderColor: "rgba(255,176,32,0.30)" }}>
      <Text style={{ color: C.text, fontWeight: "900", fontSize: 18, marginBottom: 10, textAlign: "center" }}>
        {pickLang(currentLang, "Что реально может произойти", "What can actually happen", "Що реально може статися")}
      </Text>

      {rows.map((row, idx) => (
        <View key={`home-ux-risk-${idx}`} style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 16, padding: 12, marginBottom: idx === rows.length - 1 ? 0 : 10, backgroundColor: "rgba(255,255,255,0.035)" }}>
          <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 7 }}>
            <Ionicons name={row.icon} size={18} color={row.color} />
            <Text style={{ color: row.color, fontWeight: "900", fontSize: 15, marginLeft: 8, flex: 1 }}>{row.title}</Text>
          </View>

          {!!row.text && <Text style={{ color: C.text, lineHeight: 20, fontWeight: "700" }}>{row.text}</Text>}

          {!!row.extra?.length && (
            <View style={{ marginTop: 10 }}>
              {row.extra.map((x, i) => (
                <Text key={`home-ux-extra-${i}`} style={{ color: C.dim, lineHeight: 19, marginTop: 2 }}>{x}</Text>
              ))}
            </View>
          )}

          {!!row.revokeUrl && (
            <TouchableOpacity
              activeOpacity={0.9}
              onPress={() => Linking.openURL(row.revokeUrl)}
              style={{
                marginTop: 12,
                minHeight: 46,
                borderRadius: 14,
                alignItems: "center",
                justifyContent: "center",
                backgroundColor: "rgba(255,107,107,0.16)",
                borderWidth: 1,
                borderColor: "rgba(255,107,107,0.35)",
                flexDirection: "row",
              }}
            >
              <Ionicons name="close-circle-outline" size={18} color={C.bad} />
              <Text style={{ color: C.bad, fontWeight: "900", fontSize: 15, marginLeft: 8 }}>
                {pickLang(currentLang, "Отозвать approval", "Revoke approval", "Відкликати approval")}
              </Text>
            </TouchableOpacity>
          )}
        </View>
      ))}
    </BlurCard>
  );
};


const ScoreBar = ({ value, color, height = 9 }) => (
  <View style={{ height, borderRadius: 999, backgroundColor: "rgba(255,255,255,0.08)", overflow: "hidden", marginTop: 8 }}>
    <View style={{ height, borderRadius: 999, width: `${Math.min(100, Math.max(0, Number(value || 0)))}%`, backgroundColor: color }} />
  </View>
);

const SmallPill = ({ text, icon, color = C.accent }) => (
  <View
    style={{
      paddingVertical: 7,
      paddingHorizontal: 11,
      borderRadius: 999,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: "rgba(255,255,255,0.045)",
      flexDirection: "row",
      alignItems: "center",
      marginRight: 8,
      marginBottom: 8,
    }}
  >
    {!!icon && <Ionicons name={icon} size={14} color={color} style={{ marginRight: 6 }} />}
    <Text style={{ color: C.text, fontWeight: "900", fontSize: 12 }}>{text}</Text>
  </View>
);

const ToolCard = ({ title, sub, icon, onPress }) => (
  <TouchableOpacity activeOpacity={0.9} onPress={onPress} style={{ width: "48%", marginBottom: 12 }}>
    <View style={cardChrome}>
      <BlurView intensity={24} tint="dark" style={{ padding: 14, borderRadius: 22, minHeight: 112, justifyContent: "center" }}>
        <Ionicons name={icon} size={25} color={C.accent} style={{ marginBottom: 12, alignSelf: "center" }} />
        <Text style={{ color: C.text, fontWeight: "900", fontSize: 15, textAlign: "center" }} numberOfLines={1}>
          {title}
        </Text>
        <Text style={{ color: C.dim, marginTop: 8, fontSize: 12, lineHeight: 17, textAlign: "center" }} numberOfLines={2}>
          {sub}
        </Text>
      </BlurView>
    </View>
  </TouchableOpacity>
);

export default function Home() {
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const isAuth = useAuthStore((s) => s.isAuth);

  const [lang, setLangState] = useState(normalizeAppLang(i18n?.language));
  const [input, setInput] = useState("");
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [backendError, setBackendError] = useState("");

  const [installUid, setInstallUid] = useState("");
  const [resolvedUid, setResolvedUid] = useState("");
  const [authAccess, setAuthAccess] = useState(null);

  const [quota, setQuota] = useState({ used: 0, limit: 4, left: 4, dayKey: "" });
  const [quotaBlocked, setQuotaBlocked] = useState(false);
  const [showQuotaModal, setShowQuotaModal] = useState(false);
  const [quotaMsg, setQuotaMsg] = useState("");

  const [showSamples, setShowSamples] = useState(false);
  const [proLocal, setProLocal] = useState(false);

  const shareShotRef = useRef(null);
  const [sharingNow, setSharingNow] = useState(false);

  const authUid = useMemo(() => uidFrom(user?.name, user?.email, user?.nick), [user?.name, user?.email, user?.nick]);
  const uid = resolvedUid || authUid || installUid || "anonymous";

  const TT = useCallback(
    (key, enText, ruText, ukText) => {
      const val = t(key, { defaultValue: "" });
      if (val && String(val).trim() && val !== key) return val;
      return pickLang(lang, ruText, enText, ukText);
    },
    [t, lang]
  );

  const currentLang = normalizeAppLang(lang);

  useEffect(() => {
    logEvent("screen_open", { screen: "home" });
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const saved = await AsyncStorage.getItem("app.language");
        const initial = normalizeAppLang(saved || i18n?.language);
        if (i18n && initial && initial !== i18n.language) await i18n.changeLanguage(initial);
        setLangState(initial || "en");
      } catch {}
    })();
  }, [i18n]);

  const setLang = useCallback(
    async (lng) => {
      try {
        if (!i18n || typeof i18n.changeLanguage !== "function") return;
        const next = normalizeAppLang(lng);
        if (next === lang) return;
        await i18n.changeLanguage(next);
        setLangState(next);
        await AsyncStorage.setItem("app.language", next);
        logEvent("language_change", { screen: "home", lang: next });
      } catch {}
    },
    [i18n, lang]
  );

  useEffect(() => {
    try {
      useAuthStore.getState().hydrate?.();
    } catch {}
  }, []);

  useEffect(() => {
    (async () => {
      const stable = await getOrCreateInstallUserId();
      setInstallUid(stable);
    })();
  }, []);

  useEffect(() => {
    (async () => {
      const proof = await loadProProof();
      setAuthAccess(proof?.accessToken || null);
      const best = await getBestKnownUid(user || proof?.authUser, installUid, proof?.accessToken || "");
      setResolvedUid(best);
    })();
  }, [user, installUid, isAuth]);

  const hasPro = useMemo(() => {
    const plan = (user?.plan || user?.subscription || user?.tier || user?.entitlement || "").toString().toLowerCase();
    return plan.includes("pro") || user?.isPro === true || user?.pro === true || user?.premium === true || String(user?.status || "").toLowerCase() === "pro";
  }, [user]);

  const isPro = hasPro || proLocal;

  useEffect(() => {
    (async () => {
      try {
        const keys = ["isPro", "noytrix.isPro", "pro", "proActive", "subscription.pro", "iap.isPro", "iap.pro", "entitlement.pro", "noytrix_pro_flag"];
        let localPro = false;

        for (const k of keys) {
          const v = await AsyncStorage.getItem(k);
          const s = String(v || "").toLowerCase();
          if (s === "true" || s === "1" || s === "yes" || s === "active") {
            localPro = true;
            break;
          }
        }

        setProLocal(!!localPro);
      } catch {
        setProLocal(false);
      }
    })();
  }, [uid, authAccess, currentLang, user, installUid]);

  const normalizedReport = useMemo(() => normalizeScanReport(report, currentLang), [report, currentLang]);
  const verdictColor = levelColor(normalizedReport?.level);
  const verdictBg = levelBg(normalizedReport?.level);

  const targetLabel =
    normalizedReport?.details?.page?.final_url ||
    normalizedReport?.normalized_input ||
    normalizedReport?.input ||
    "";

  const topEvidence = useMemo(() => (Array.isArray(normalizedReport?.evidence) ? normalizedReport.evidence.slice(0, 2) : []), [normalizedReport]);
  const compactSources = useMemo(() => (Array.isArray(normalizedReport?.sources) ? normalizedReport.sources.slice(0, 3) : []), [normalizedReport]);

  const quotaPillText = useMemo(() => {
    if (isPro) return pickLang(currentLang, "PRO • безлимит", "PRO • unlimited", "PRO • безліміт");

    const used = Number(quota?.used || 0);
    const limit = Number(quota?.limit || quota?.freeLimit || 4);
    return pickLang(currentLang, `FREE • ${used}/${limit} проверок`, `FREE • ${used}/${limit} checks`, `FREE • ${used}/${limit} перевірок`);
  }, [isPro, quota, currentLang]);

  const onCheck = useCallback(async () => {
    const value = String(input || "").trim();
    if (!value) return;

    const proof = await loadProProof();
    const accessToken = proof?.accessToken || authAccess || null;
    const effectiveUser = user || proof?.authUser || null;
    const effectiveUid = await getBestKnownUid(effectiveUser, installUid, accessToken || "");

    if (!isPro && quotaBlocked) {
      setQuotaMsg(pickLang(currentLang, "FREE лимит на сегодня уже использован. PRO убирает лимиты.", "FREE daily limit reached. PRO removes limits.", "FREE ліміт на сьогодні вже використано. PRO прибирає ліміти."));
      setShowQuotaModal(false);
      return;
    }

    logEvent("scan_submitted", { screen: "home", source: "home_hero", lang: currentLang });

    setLoading(true);
    setBackendError("");
    setReport(null);

    try {
      const headers = {
        "Accept-Language": currentLang,
        "X-Lang": currentLang,
        "X-Language": currentLang,
        "X-User-Id": effectiveUid || "anonymous",
      };

      if (proof?.productId) headers["X-Play-Product-Id"] = proof.productId;
      if (proof?.purchaseToken) headers["X-Play-Purchase-Token"] = proof.purchaseToken;
      if (proof?.entitlementId) headers["X-Entitlement-Id"] = proof.entitlementId;
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

      const res = await safeFetchRaw(
        `${BACKEND}/scan?input=${encodeURIComponent(value)}&lang=${encodeURIComponent(currentLang)}&userId=${encodeURIComponent(effectiveUid || "anonymous")}`,
        { headers }
      );

      const rawText = await res.text();
      let backend = null;

      try {
        backend = rawText ? JSON.parse(rawText) : null;
      } catch {
        throw new Error("invalid_json");
      }

      if (res.status === 429) {
        const detail = backend?.detail || {};
        const qRaw = detail?.quota || backend?.quota || null;

        if (qRaw) {
          const used = Number(qRaw.used || 0);
          const limit = Number(qRaw.freeLimit || qRaw.limit || 4);
          const left = Math.max(0, Number(qRaw.left ?? (limit - used)));

          setQuota({ used, limit, left, dayKey: String(qRaw.day || "") });
        }

        setQuotaMsg(
          detail?.message ||
            pickLang(currentLang, "FREE лимит 4 проверки в день достигнут. PRO убирает лимиты.", "FREE limit of 4 checks per day reached. PRO removes limits.", "FREE ліміт 4 перевірки на день досягнуто. PRO прибирає ліміти.")
        );
        setShowQuotaModal(false);
        setQuotaBlocked(true);
        return;
      }

      if (!res.ok) throw new Error(String(backend?.detail || `http_${res.status}`));

      const final = normalizeScanReport(backend, currentLang);
      setReport(final);

      const quotaFromServer = backend?.quota || final?.quota || null;
      if (isPro) {
        setQuota({ used: 0, limit: 4, left: 4, dayKey: "" });
        setQuotaBlocked(false);
        setShowQuotaModal(false);
      } else if (quotaFromServer) {
        const q = {
          used: Number(quotaFromServer.used || 0),
          limit: Number(quotaFromServer.freeLimit || quotaFromServer.limit || 4),
          left: Math.max(0, Number(quotaFromServer.left ?? ((quotaFromServer.freeLimit || quotaFromServer.limit || 4) - (quotaFromServer.used || 0)))),
          dayKey: String(quotaFromServer.day || ""),
        };
        setQuota(q);
        setQuotaBlocked(q.left <= 0 || q.used >= q.limit);
        setShowQuotaModal(false);
      }

      await appendHistory(effectiveUid || "anonymous", {
        id: Date.now(),
        type: "scamshield",
        title: `ScamShield: ${final?.level} — ${final?.normalized_input || value}`,
        at: Date.now(),
        meta: {
          level: final?.level,
          score: final?.score,
          object: final?.normalized_input || value,
          isScam: final?.level === "danger" || final?.level === "critical",
        },
      });

      logEvent("scan_result", {
        screen: "home",
        lang: currentLang,
        level: final?.level || "n/a",
        score: Number(final?.score ?? 0),
        kind: final?.kind || "text",
        backend_ok: true,
      });
      recordReviewPromptScan({
        screen: "home",
        level: final?.level || "n/a",
        kind: final?.kind || "text",
      });
    } catch (e) {
      const humanMessage = explainBackendMessage(String(e?.message || e || ""), currentLang);
      setReport(null);
      setBackendError(humanMessage);
      showAppAlert(pickLang(currentLang, "Проверка недоступна", "Check unavailable", "Перевірка недоступна"), humanMessage);
    } finally {
      setLoading(false);
    }
  }, [input, authAccess, user, installUid, isPro, quotaBlocked, currentLang]);


  const shareMessage = useMemo(() => {
    if (!normalizedReport) return "";

    return `Noytrix ScamShield: ${normalizedReport.verdictLabel || normalizedReport.levelLabel} (${normalizedReport.score}/100)\n${targetLabel || ""}`;
  }, [normalizedReport, targetLabel]);

  const shareVerdict = useCallback(async () => {
    if (!normalizedReport || sharingNow) return;

    setSharingNow(true);

    try {
      await new Promise((resolve) => InteractionManager.runAfterInteractions(resolve));
      await new Promise((resolve) => setTimeout(resolve, 220));

      const uri = await shareShotRef.current?.capture?.();

      if (!uri || typeof uri !== "string") {
        throw new Error("capture_empty");
      }

      const canShareFile = await Sharing.isAvailableAsync().catch(() => false);

      if (canShareFile) {
        await Sharing.shareAsync(uri, {
          mimeType: "image/png",
          UTI: "public.png",
          dialogTitle: pickLang(currentLang, "Поделиться Noytrix", "Share Noytrix", "Поділитися Noytrix"),
        });
      } else {
        await Share.share({
          title: "Noytrix ScamShield",
          url: uri,
          message: Platform.OS === "ios" ? shareMessage : `${shareMessage}\n${uri}`,
        });
      }

      logEvent("home_share_success", { screen: "home", kind: normalizedReport?.kind || "text" });
    } catch (e) {
      const raw = String(e?.message || e || "").toLowerCase();

      if (!raw.includes("cancel")) {
        showAppAlert(
          pickLang(currentLang, "Не удалось поделиться", "Could not share", "Не вдалося поділитися"),
          pickLang(currentLang, "Не удалось отправить изображение. Попробуй ещё раз.", "Could not share the image. Please try again.", "Не вдалося надіслати зображення. Спробуй ще раз.")
        );
      }

      logEvent("home_share_error", { screen: "home", err: String(e?.message || e || "share_error") });
    } finally {
      setSharingNow(false);
    }
  }, [normalizedReport, sharingNow, currentLang, shareMessage]);

  const ShareCard = () => {
    if (!normalizedReport) return null;

    const color = levelColor(normalizedReport?.level);
    const date = new Date();
    const iso = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

    return (
      <LinearGradient colors={[GRAD.start, GRAD.mid, GRAD.end]} style={{ width: 1024, padding: 40, borderRadius: 28 }}>
        <Text style={{ color: C.logo, fontWeight: "900", fontSize: 42, marginBottom: 18 }}>NOYTRIX</Text>

        <View style={{ backgroundColor: "rgba(8,14,36,0.98)", borderRadius: 24, padding: 28, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ color, fontWeight: "900", fontSize: 34, marginBottom: 10 }}>
            {normalizedReport.verdictLabel || normalizedReport.levelLabel}
          </Text>

          <Text style={{ color: C.dim, fontSize: 20, marginBottom: 18 }} numberOfLines={2}>
            {targetLabel || normalizedReport?.normalized_input || normalizedReport?.input || ""}
          </Text>

          <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" }}>
            <View style={{ width: "48%", borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 16, marginBottom: 12 }}>
              <Text style={{ color: C.dim, marginBottom: 6 }}>Score</Text>
              <Text style={{ color: C.text, fontWeight: "900", fontSize: 24 }}>{normalizedReport.score}/100</Text>
            </View>

            <View style={{ width: "48%", borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 16, marginBottom: 12 }}>
              <Text style={{ color: C.dim, marginBottom: 6 }}>Type</Text>
              <Text style={{ color: C.text, fontWeight: "900", fontSize: 24 }}>{normalizedReport.kindLabel}</Text>
            </View>

            <View style={{ width: "48%", borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 16, marginBottom: 12 }}>
              <Text style={{ color: C.dim, marginBottom: 6 }}>Level</Text>
              <Text style={{ color, fontWeight: "900", fontSize: 24 }}>{normalizedReport.levelLabel}</Text>
            </View>

            <View style={{ width: "48%", borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 16, marginBottom: 12 }}>
              <Text style={{ color: C.dim, marginBottom: 6 }}>Date</Text>
              <Text style={{ color: C.text, fontWeight: "900", fontSize: 24 }}>{iso}</Text>
            </View>
          </View>

          {topEvidence.slice(0, 3).map((r, i) => (
            <Text key={i} style={{ color: C.dim, fontSize: 18, marginTop: 8 }}>
              - {prettyTitleFromCode(r?.code, currentLang)}
            </Text>
          ))}

          <Text style={{ color: C.dim, marginTop: 20, fontSize: 14 }}>NOYTRIX - ScamShield</Text>
        </View>
      </LinearGradient>
    );
  };

  const openShieldFull = useCallback(async () => {
    try {
      const value = targetLabel || normalizedReport?.normalized_input || normalizedReport?.input || input || "";
      if (value && String(value).trim()) await AsyncStorage.setItem(SHIELD_PREFILL_KEY, String(value).trim());
      logEvent("home_open_shield", { screen: "home" });
      router.push("/shield");
    } catch {
      logEvent("home_open_shield", { screen: "home" });
      router.push("/shield");
    }
  }, [router, targetLabel, normalizedReport, input]);

  const openPro = useCallback(() => {
    logEvent("home_open_pro", { screen: "home", is_pro: !!isPro, target: isPro ? "shield_pro" : "pro" });
    router.push(isPro ? "/shield-pro" : "/pro");
  }, [router, isPro]);

  const clearScan = useCallback(() => {
    setInput("");
    setReport(null);
    setBackendError("");
  }, []);

  const showResultBlock = !!normalizedReport && !backendError;

  return (
    <LinearGradient colors={[GRAD.start, GRAD.mid, GRAD.end]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={{ flex: 1 }}>
      <SafeAreaView style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 120 }}>
          <View style={{ paddingTop: 28, paddingBottom: 12 }}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <View style={{ flex: 1, paddingRight: 12 }}>
                <Text style={{ color: C.logo, fontWeight: "900", fontSize: 34, letterSpacing: 0.2, textAlign: "left" }}>
                  NOYTRIX
                </Text>
                <Text style={{ color: C.dim, fontWeight: "800", fontSize: 14, marginTop: 5, textAlign: "left" }} numberOfLines={1}>
                  {TT("home.new.subtitle", "Crypto protection before you click", "Крипто-защита до клика")}
                </Text>
              </View>

              <View style={[cardChrome, { borderRadius: 999 }]}>
                <BlurView intensity={28} tint="dark" style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 7, flexDirection: "row" }}>
                  {["ru", "en", "uk"].map((lng) => (
                    <TouchableOpacity key={lng} onPress={() => setLang(lng)} style={{ paddingHorizontal: 7, paddingVertical: 2, opacity: lang === lng ? 1 : 0.55 }}>
                      <Text style={{ color: lang === lng ? C.accent : C.text, fontWeight: "900", fontSize: 11 }}>{lng.toUpperCase()}</Text>
                    </TouchableOpacity>
                  ))}
                </BlurView>
              </View>
            </View>
          </View>

          <BlurCard style={{ marginTop: 6, borderColor: "rgba(255,176,32,0.24)" }}>
            <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "center", marginBottom: 10 }}>
              <SmallPill text={TT("home.new.pill1", "ScamShield", "Скам Шилд", "Скам Шилд")} icon="shield-checkmark" />
              <SmallPill text={quotaPillText} icon={isPro ? "flash" : "lock-open-outline"} color={isPro ? C.accent : C.dim} />
            </View>

            <Text style={{ color: C.text, fontSize: 28, lineHeight: 35, fontWeight: "900", marginTop: 4, textAlign: "center" }}>
              {currentLang === "ru" ? (
                <>
                  ПРОВЕРЬ <Text style={{ color: C.accent }}>ССЫЛКУ</Text>, КОШЕЛЁК ИЛИ ТЕКСТ ДО ТОГО, КАК ДОВЕРЯТЬ.
                </>
              ) : currentLang === "uk" ? (
                <>
                  ПЕРЕВІР <Text style={{ color: C.accent }}>ПОСИЛАННЯ</Text>, ГАМАНЕЦЬ АБО ТЕКСТ ДО ТОГО, ЯК ДОВІРЯТИ.
                </>
              ) : (
                <>
                  CHECK ANY <Text style={{ color: C.accent }}>CRYPTO LINK</Text>, WALLET OR TEXT BEFORE YOU TRUST IT.
                </>
              )}
            </Text>

            <Text style={{ color: C.dim, fontSize: 15, lineHeight: 22, marginTop: 12, textAlign: "center" }}>
              {currentLang === "ru" ? (
                <>
                  Вставь всё подозрительное. Noytrix даст <Text style={{ color: C.accent, fontWeight: "900" }}>быстрый вердикт</Text> здесь, а полный разбор откроешь в ScamShield.
                </>
              ) : currentLang === "uk" ? (
                <>
                  Встав усе підозріле. Noytrix дасть <Text style={{ color: C.accent, fontWeight: "900" }}>швидкий вердикт</Text> тут, а повний розбір відкриєш у ScamShield.
                </>
              ) : (
                <>
                  Paste anything suspicious. Noytrix gives a <Text style={{ color: C.accent, fontWeight: "900" }}>fast verdict</Text> here, then opens the full ScamShield report.
                </>
              )}
            </Text>

            <View style={{ marginTop: 18, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 20, backgroundColor: "rgba(255,255,255,0.05)" }}>
              <TextInput
                placeholder={TT("home.new.inputPlaceholder", "Paste URL / domain / wallet / contract / ticker / text", "Вставь URL / домен / кошелёк / контракт / тикер / текст", "Встав URL / домен / гаманець / контракт / тикер / текст")}
                placeholderTextColor={C.dim}
                value={input}
                onChangeText={(v) => {
                  setInput(v);
                  if (backendError) setBackendError("");
                }}
                style={{ color: C.text, minHeight: 76, paddingHorizontal: 15, paddingVertical: 13, fontSize: 16, lineHeight: 21, textAlign: "center" }}
                multiline
              />
            </View>

            <View style={{ flexDirection: "row", marginTop: 12 }}>
              <View style={{ flex: 1 }}>
                <PrimaryButton
                  onPress={onCheck}
                  disabled={loading || quotaBlocked}
                  title={loading ? TT("home.new.checking", "Checking…", "Проверка…", "Перевірка...") : TT("home.new.check", "Check now", "Проверить", "Перевірити")}
                  leftIcon={loading ? <ActivityIndicator color={C.accentText} /> : <Ionicons name="shield-checkmark" size={18} color={C.accentText} />}
                />
              </View>
              <View style={{ width: 10 }} />
              <SecondaryButton title={TT("home.new.samples", "Samples", "Примеры", "Приклади")} onPress={() => setShowSamples(true)} leftIcon={<Ionicons name="sparkles-outline" size={16} color={C.dim} />} />
            </View>

            {(!!input || !!normalizedReport || !!backendError) && (
              <View style={{ marginTop: 10 }}>
                <SecondaryButton title={TT("home.new.clear", "Clear", "Очистить", "Очистити")} onPress={clearScan} leftIcon={<Ionicons name="close-circle-outline" size={16} color={C.dim} />} />
              </View>
            )}
          </BlurCard>

          {!!backendError && (
            <BlurCard style={{ borderColor: "rgba(255,107,107,0.38)" }}>
              <Text style={{ color: C.bad, fontWeight: "900", fontSize: 18, marginBottom: 8, textAlign: "center" }}>
                {TT("home.new.errorTitle", "CHECK UNAVAILABLE", "ПРОВЕРКА НЕДОСТУПНА", "ПЕРЕВІРКА НЕДОСТУПНА")}
              </Text>
              <Text style={{ color: C.dim, lineHeight: 20, textAlign: "center" }}>{backendError}</Text>
            </BlurCard>
          )}


          {!isPro && quotaBlocked && (
            <BlurCard style={{ borderColor: "rgba(255,176,32,0.35)" }}>
              <Text style={{ color: C.accent, fontWeight: "900", fontSize: 20, marginBottom: 8, textAlign: "center" }}>
                {TT("home.new.limitTitleInline", "FREE LIMIT REACHED", "FREE ЛИМИТ ДОСТИГНУТ", "FREE ЛІМІТ ВИЧЕРПАНО")}
              </Text>
              <Text style={{ color: C.dim, lineHeight: 21, fontSize: 15, marginBottom: 14, textAlign: "center" }}>
                {TT("home.new.limitTextInline", "You used 4/4 checks today. Upgrade to PRO for unlimited scans.", "Вы использовали 4/4 проверки сегодня. Для безлимитных проверок перейдите на PRO.", "Сьогодні ви використали 4/4 перевірки. Перейдіть на PRO для безлімітних сканів.")}
              </Text>
              <PrimaryButton
                title={TT("home.new.limitProInline", "UPGRADE TO PRO", "ПЕРЕЙТИ НА PRO", "ПЕРЕЙТИ НА PRO")}
                onPress={openPro}
                leftIcon={<Ionicons name="flash" size={18} color={C.accentText} />}
              />
            </BlurCard>
          )}

          {showResultBlock && (
            <BlurCard style={{ borderColor: verdictColor, borderWidth: 2 }}>
              <View style={{ borderRadius: 20, padding: 14, backgroundColor: verdictBg, borderWidth: 1, borderColor: "rgba(255,255,255,0.07)" }}>
                <Text style={{ color: C.dim, fontWeight: "900", fontSize: 12, marginBottom: 6, textAlign: "center" }}>
                  {TT("home.new.quickVerdict", "QUICK VERDICT", "БЫСТРЫЙ ВЕРДИКТ", "ШВИДКИЙ ВЕРДИКТ")}
                </Text>

                <Text style={{ color: verdictColor, fontWeight: "900", fontSize: 31, textAlign: "center" }} numberOfLines={2}>
                  {normalizedReport.verdictLabel || normalizedReport.levelLabel}
                </Text>

                <View style={{ alignItems: "center", marginTop: 14 }}>
                  <View style={{ width: 86, height: 86, borderRadius: 999, borderWidth: 8, borderColor: verdictColor, alignItems: "center", justifyContent: "center" }}>
                    <Text style={{ color: C.text, fontWeight: "900", fontSize: 21 }}>{normalizedReport.score}</Text>
                    <Text style={{ color: C.dim, fontWeight: "900", fontSize: 10 }}>/100</Text>
                  </View>
                </View>

                <ScoreBar value={normalizedReport.score} color={verdictColor} height={10} />

                {!!targetLabel && (
                  <Text style={{ color: C.dim, marginTop: 12, lineHeight: 19, textAlign: "center" }} numberOfLines={2}>
                    {compactMiddle(targetLabel, 36, 16)}
                  </Text>
                )}

                {!!normalizedReport.aiHumanVerdict && (
                  <View style={{ marginTop: 14, borderRadius: 16, borderWidth: 1, borderColor: "rgba(255,255,255,0.10)", backgroundColor: "rgba(0,0,0,0.18)", padding: 12 }}>
                    <Text style={{ color: C.text, fontSize: 15, lineHeight: 21, textAlign: "center", fontWeight: "800" }}>
                      {normalizedReport.aiHumanVerdict}
                    </Text>
                  </View>
                )}
              </View>

              <View style={{ marginTop: 14 }}>
                <PrimaryButton
                  title={TT("home.new.openFull", "OPEN FULL SCAMSHIELD REPORT", "ОТКРЫТЬ ПОЛНЫЙ РАЗБОР SCAMSHIELD", "ВІДКРИТИ ПОВНИЙ РОЗБІР SCAMSHIELD")}
                  onPress={openShieldFull}
                  leftIcon={<Ionicons name="arrow-forward" size={18} color={C.accentText} />}
                />

                <SecondaryButton
                  title={sharingNow ? TT("home.new.sharing", "Sharing…", "Отправка…", "Надсилання...") : TT("home.new.share", "SHARE RESULT", "ПОДЕЛИТЬСЯ", "ПОДІЛИТИСЯ")}
                  onPress={shareVerdict}
                  disabled={sharingNow}
                  leftIcon={<Ionicons name="share-social-outline" size={16} color={C.dim} />}
                  style={{ marginTop: 10 }}
                />
              </View>
            </BlurCard>
          )}

          <BlurCard style={{ borderColor: "rgba(255,176,32,0.25)" }}>
            <Text style={{ color: C.text, fontWeight: "900", fontSize: 22, marginBottom: 8, textAlign: "center" }}>
              {currentLang === "ru" ? (
                <>
                  ОДИН ЭКРАН. ОДНО ДЕЙСТВИЕ. <Text style={{ color: C.accent }}>МЕНЬШЕ РИСКА.</Text>
                </>
              ) : currentLang === "uk" ? (
                <>
                  ОДИН ЕКРАН. ОДНА ДІЯ. <Text style={{ color: C.accent }}>МЕНШЕ РИЗИКУ.</Text>
                </>
              ) : (
                <>
                  ONE SCREEN. ONE ACTION. <Text style={{ color: C.accent }}>LESS RISK.</Text>
                </>
              )}
            </Text>

            <Text style={{ color: C.dim, lineHeight: 21, fontSize: 15, textAlign: "center" }}>
              {TT(
                "home.new.whyText",
                "Noytrix checks links, domains, wallets, contracts, tickers and suspicious text before you click, connect or send funds.",
                "Noytrix проверяет ссылки, домены, кошельки, контракты, тикеры и подозрительный текст до клика, подключения или перевода.",
                "Noytrix перевіряє посилання, домени, гаманці, контракти, тикери й підозрілий текст до кліку, підключення або переказу."
              )}
            </Text>

            <View style={{ marginTop: 14 }}>
              {[
                { icon: "link-outline", en: "Phishing links and fake domains", ru: "Фишинговые ссылки и фейковые домены", uk: "Фішингові посилання та фейкові домени" },
                { icon: "wallet-outline", en: "Wallets, contracts and Web3 risks", ru: "Кошельки, контракты и Web3-риски", uk: "Гаманці, контракти та Web3-ризики" },
                { icon: "warning-outline", en: "Seed phrase, drainer and fake support signals", ru: "Seed phrase, drainer и fake support сигналы", uk: "Seed phrase, drainer і сигнали fake support" },
              ].map((x, i) => (
                <View key={`benefit-${i}`} style={{ flexDirection: "row", alignItems: "center", borderWidth: 1, borderColor: C.borderSoft, borderRadius: 16, padding: 12, backgroundColor: "rgba(255,255,255,0.03)", marginBottom: 10 }}>
                  <Ionicons name={x.icon} size={19} color={C.accent} style={{ marginRight: 10 }} />
                  <Text style={{ color: C.text, fontWeight: "800", flex: 1, lineHeight: 19, textAlign: "center" }}>
                    {pickLang(currentLang, x.ru, x.en, x.uk)}
                  </Text>
                </View>
              ))}
            </View>
          </BlurCard>

          <BlurCard style={{ borderColor: "rgba(255,176,32,0.28)" }}>
            <Text style={{ color: C.text, fontWeight: "900", fontSize: 20, marginBottom: 8, textAlign: "center" }}>
              {isPro ? TT("home.new.proActiveTitle", "PRO IS ACTIVE", "PRO АКТИВЕН") : TT("home.new.proTitle", "NEED UNLIMITED PROTECTION?", "НУЖНА ЗАЩИТА БЕЗ ЛИМИТОВ?")}
            </Text>

            <Text style={{ color: C.dim, lineHeight: 21, fontSize: 15, marginBottom: 14, textAlign: "center" }}>
              {isPro
                ? TT("home.new.proActiveText", "Open ScamShield PRO for deeper analysis.", "Открой ScamShield PRO для более глубокого анализа.")
                : TT("home.new.proText", "PRO removes daily limits and unlocks deeper source details.", "PRO убирает дневные лимиты и открывает более глубокие детали источников.")}
            </Text>

            <PrimaryButton
              title={isPro ? TT("home.new.openPro", "OPEN SCAMSHIELD PRO", "ОТКРЫТЬ SCAMSHIELD PRO") : TT("home.new.upgradePro", "OPEN PRO", "ОТКРЫТЬ PRO")}
              onPress={openPro}
              leftIcon={<Ionicons name={isPro ? "shield-checkmark" : "flash"} size={18} color={C.accentText} />}
            />
          </BlurCard>

          <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", marginTop: 2 }}>
            <ToolCard
              title={TT("home.qt.scan", "SCAMSHIELD", "СКАМ ШИЛД")}
              sub={TT("home.qt.scanSub", "Full anti-scam report", "Полный анти-скам разбор")}
              icon="shield-checkmark"
              onPress={() => { logEvent("home_tool_click", { screen: "home", tool: "shield" }); router.push("/shield"); }}
            />
            <ToolCard
              title={TT("home.qt.immunity", "IMMUNITY", "ИММУНИТЕТ")}
              sub={TT("home.qt.immunitySub", "Your protection score", "Твой уровень защиты")}
              icon="shield-outline"
              onPress={() => { logEvent("home_tool_click", { screen: "home", tool: "immunity" }); router.push("/immunity"); }}
            />
            <ToolCard
              title={TT("home.qt.explain", "EXPLAIN", "EXPLAIN")}
              sub={TT("home.qt.explainSub", "Understand the risk", "Понять риск простыми словами")}
              icon="book"
              onPress={() => { logEvent("home_tool_click", { screen: "home", tool: "explain" }); router.push("/explain"); }}
            />
            <ToolCard
              title={TT("home.qt.calendar", "CALENDAR", "КАЛЕНДАРЬ")}
              sub={TT("home.qt.calendarSub", "Events that move market", "События, которые двигают рынок")}
              icon="calendar"
              onPress={() => { logEvent("home_tool_click", { screen: "home", tool: "calendar" }); router.push("/calendar"); }}
            />
          </View>

          <View style={{ alignItems: "center", marginTop: 18, marginBottom: 80 }}>
            <View style={{ flexDirection: "row", marginBottom: 14 }}>
              <TouchableOpacity onPress={() => { logEvent("home_social_click", { screen: "home", platform: "telegram" }); Linking.openURL("https://t.me/noytrix"); }} activeOpacity={0.9} style={{ marginRight: 18 }}>
                <View style={[cardChrome, { borderRadius: 999 }]}>
                  <BlurView intensity={24} tint="dark" style={{ borderRadius: 999, padding: 10 }}>
                    <FontAwesome5 name="telegram" size={22} color={C.accent} />
                  </BlurView>
                </View>
              </TouchableOpacity>

              <TouchableOpacity onPress={() => { logEvent("home_social_click", { screen: "home", platform: "instagram" }); Linking.openURL("https://www.instagram.com/noytrix?igsh=MTQ1cjhzMDNyMHo5Mw=="); }} activeOpacity={0.9} style={{ marginRight: 18 }}>
                <View style={[cardChrome, { borderRadius: 999 }]}>
                  <BlurView intensity={24} tint="dark" style={{ borderRadius: 999, padding: 10 }}>
                    <Ionicons name="logo-instagram" size={22} color={C.accent} />
                  </BlurView>
                </View>
              </TouchableOpacity>

              <TouchableOpacity onPress={() => { logEvent("home_social_click", { screen: "home", platform: "tiktok" }); Linking.openURL("https://www.tiktok.com/@noytrix3?_r=1&_t=ZM-912hB91BCzz"); }} activeOpacity={0.9} style={{ marginRight: 18 }}>
                <View style={[cardChrome, { borderRadius: 999 }]}>
                  <BlurView intensity={24} tint="dark" style={{ borderRadius: 999, padding: 10 }}>
                    <Ionicons name="logo-tiktok" size={22} color={C.accent} />
                  </BlurView>
                </View>
              </TouchableOpacity>

              <TouchableOpacity onPress={() => { logEvent("home_social_click", { screen: "home", platform: "youtube" }); Linking.openURL("https://www.youtube.com/@Noytrix"); }} activeOpacity={0.9}>
                <View style={[cardChrome, { borderRadius: 999 }]}>
                  <BlurView intensity={24} tint="dark" style={{ borderRadius: 999, padding: 10 }}>
                    <Ionicons name="logo-youtube" size={22} color={C.accent} />
                  </BlurView>
                </View>
              </TouchableOpacity>
            </View>

            <Text style={{ color: C.dim, fontSize: 12, textAlign: "center", lineHeight: 18 }}>
              © 2025 Noytrix •{" "}
              <Text onPress={() => Linking.openURL("https://noytrix.com/privacy")} style={{ textDecorationLine: "underline", color: C.text, fontWeight: "800" }}>
                {TT("home.footer.privacy", "Privacy Policy", "Политика конфиденциальности")}
              </Text>{" "}
              •{" "}
              <Text onPress={() => Linking.openURL("https://noytrix.com/terms")} style={{ textDecorationLine: "underline", color: C.text, fontWeight: "800" }}>
                {TT("home.footer.terms", "Terms of Use", "Условия использования")}
              </Text>{" "}
              •{" "}
              <Text onPress={() => Linking.openURL("https://noytrix.com/disclaimer")} style={{ textDecorationLine: "underline", color: C.text, fontWeight: "800" }}>
                {TT("home.footer.disclaimer", "Disclaimer", "Отказ от ответственности")}
              </Text>
            </Text>
          </View>
        </ScrollView>

        <NoyBot />

        <View style={{ position: "absolute", left: -9999, top: -9999 }}>
          <ViewShot ref={shareShotRef} options={{ format: "png", quality: 1 }}>
            <ShareCard />
          </ViewShot>
        </View>
      </SafeAreaView>

      {!isPro && (
        <Modal visible={showQuotaModal} transparent animationType="fade" onRequestClose={() => setShowQuotaModal(false)}>
          <Pressable onPress={() => setShowQuotaModal(false)} style={{ flex: 1, justifyContent: "center", padding: 24, backgroundColor: "rgba(0,0,0,0.45)" }}>
            <LinearGradient colors={[GRAD.start, GRAD.mid, GRAD.end]} style={{ borderRadius: 22, padding: 16, borderWidth: 1, borderColor: "rgba(255,176,32,0.35)" }}>
              <Text style={{ color: C.text, fontWeight: "900", marginBottom: 10, fontSize: 19, textAlign: "center" }}>
                {TT("home.new.limitTitle", "FREE LIMIT REACHED", "FREE ЛИМИТ ДОСТИГНУТ")}
              </Text>
              <Text style={{ color: C.dim, lineHeight: 20, marginBottom: 14, textAlign: "center" }}>
                {quotaMsg || TT("home.new.limitText", "FREE daily limit reached. PRO removes limits.", "FREE лимит на сегодня использован. PRO убирает лимиты.")}
              </Text>
              <View style={{ flexDirection: "row" }}>
                <View style={{ flex: 1 }}>
                  <PrimaryButton title={TT("home.new.limitPro", "OPEN PRO", "ОТКРЫТЬ PRO")} onPress={() => { setShowQuotaModal(false); router.push("/pro"); }} />
                </View>
                <View style={{ width: 10 }} />
                <View style={{ flex: 1 }}>
                  <SecondaryButton title={TT("home.new.limitOk", "OK", "ОК")} onPress={() => setShowQuotaModal(false)} />
                </View>
              </View>
            </LinearGradient>
          </Pressable>
        </Modal>
      )}

      <Modal visible={showSamples} transparent animationType="fade" onRequestClose={() => setShowSamples(false)}>
        <Pressable onPress={() => setShowSamples(false)} style={{ flex: 1, justifyContent: "center", padding: 24, backgroundColor: "rgba(0,0,0,0.45)" }}>
          <LinearGradient colors={[GRAD.start, GRAD.mid, GRAD.end]} style={{ borderRadius: 22, padding: 16, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ color: C.text, fontWeight: "900", marginBottom: 12, fontSize: 17, textAlign: "center" }}>
              {TT("home.new.samplesTitle", "SAMPLES", "ПРИМЕРЫ")}
            </Text>

            {SAMPLES.map((s, i) => (
              <TouchableOpacity
                key={i}
                activeOpacity={0.88}
                onPress={() => {
                  logEvent("sample_selected", { screen: "home", index: i });
                  setInput(s.h);
                  setShowSamples(false);
                }}
                style={{ borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 12, marginBottom: 10, backgroundColor: "rgba(255,255,255,0.03)" }}
              >
                <Text style={{ color: C.text, fontWeight: "800", textAlign: "center" }} numberOfLines={2}>
                  {s.h}
                </Text>
                <Text style={{ color: C.dim, marginTop: 6, textAlign: "center" }} numberOfLines={2}>
                  {pickLang(currentLang, s.dRu, s.dEn, s.dUk)}
                </Text>
              </TouchableOpacity>
            ))}
          </LinearGradient>
        </Pressable>
      </Modal>
    </LinearGradient>
  );
}
