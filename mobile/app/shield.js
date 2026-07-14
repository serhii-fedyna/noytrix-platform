import React, { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { View, Text, TextInput, TouchableOpacity, ScrollView, Modal, Pressable, ActivityIndicator, Share, Platform, InteractionManager } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { BlurView } from "expo-blur";
import { useRouter, useFocusEffect } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import ViewShot from "react-native-view-shot";
import * as Clipboard from "expo-clipboard";
import * as Linking from "expo-linking";
import * as Sharing from "expo-sharing";
import { Ionicons } from "@expo/vector-icons";
import Constants from "expo-constants";

import { useAuthStore } from "./lib/store.auth";
import { useI18n } from "./i18n/useI18n";
import { logEvent } from "./lib/analytics";
import { shareImagePremium } from "./lib/sharePremium";
import { showAppAlert } from "./lib/appAlert";

const BACKEND = "https://noytrix.com";
const AUTH_KEY = "auth_state_v1";
const INSTALL_UID_KEY = "noytrix.installUserId";
const SHIELD_PREFILL_KEY = "shield.prefill";

const APP_KEY =
  Constants?.expoConfig?.extra?.noytrixAppKey ||
  Constants?.expoConfig?.extra?.NOYTRIX_APP_KEY ||
  Constants?.manifest?.extra?.noytrixAppKey ||
  Constants?.manifest?.extra?.NOYTRIX_APP_KEY ||
  Constants?.manifest2?.extra?.expoClient?.extra?.noytrixAppKey ||
  Constants?.manifest2?.extra?.expoClient?.extra?.NOYTRIX_APP_KEY ||
  "";

const GRAD = { start: "#06080f", mid: "#0a1233", end: "#0b1c4f" };

const T = {
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
  neutral: "#6ea8ff",
  panel: "rgba(255,255,255,0.035)",
};

const cardChrome = {
  borderRadius: 22,
  borderWidth: 1,
  borderColor: T.border,
  overflow: "hidden",
  marginBottom: 14,
};

const BlurCard = ({ style, children, intensity = 26 }) => (
  <View style={[cardChrome, style]}>
    <BlurView intensity={intensity} tint="dark" style={{ padding: 16, borderRadius: 22 }}>
      {children}
    </BlurView>
  </View>
);

const PrimaryButton = ({
  title,
  onPress,
  disabled,
  style,
  leftIcon,
  bg = T.accent,
  textColor = T.accentText,
}) => (
  <TouchableOpacity
    activeOpacity={0.9}
    onPress={onPress}
    disabled={disabled}
    style={[
      {
        minHeight: 52,
        borderRadius: 18,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: bg,
        opacity: disabled ? 0.7 : 1,
        flexDirection: "row",
        paddingHorizontal: 18,
        paddingVertical: 12,
      },
      style,
    ]}
  >
    {!!leftIcon && <View style={{ marginRight: 10 }}>{leftIcon}</View>}
    <Text
      style={{ color: textColor, fontWeight: "900", fontSize: 16 }}
      numberOfLines={1}
      adjustsFontSizeToFit
      minimumFontScale={0.85}
    >
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
        minHeight: 52,
        borderRadius: 18,
        alignItems: "center",
        justifyContent: "center",
        borderWidth: 1,
        borderColor: T.border,
        backgroundColor: "rgba(255,255,255,0.04)",
        paddingHorizontal: 18,
        paddingVertical: 12,
        opacity: disabled ? 0.55 : 1,
        flexDirection: "row",
      },
      style,
    ]}
  >
    {!!leftIcon && <View style={{ marginRight: 10 }}>{leftIcon}</View>}
    <Text
      style={{ color: T.text, fontWeight: "800", fontSize: 15 }}
      numberOfLines={1}
      adjustsFontSizeToFit
      minimumFontScale={0.85}
    >
      {title}
    </Text>
  </TouchableOpacity>
);

const reIsHttp = /^https?:\/\//i;
const reIsEth = /^0x[a-f0-9]{40}$/i;
const reTicker = /^[A-Z0-9._-]{2,15}$/i;

function pickLang(lang, ru, en) {
  return String(lang || "en").toLowerCase().startsWith("ru") ? ru : en;
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

async function getAuthAccessToken() {
  try {
    const state = await getAuthStateV1();
    return state?.access_token || null;
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
  if (!s) return "";
  if (s.startsWith("guest_")) return "";
  if (s === "anonymous" || s === "null" || s === "undefined") return "";
  return s;
}

async function getBestKnownUid(user, installUid = "", accessToken = "") {
  const direct = uidFrom(user?.name, user?.email, user?.nick);

  if (
    direct &&
    !direct.startsWith("guest_") &&
    direct !== "anonymous" &&
    direct !== "null" &&
    direct !== "undefined"
  ) {
    return direct;
  }

  const payloadUid = uidFromJwtPayload(parseJwtPayload(accessToken));
  if (payloadUid) return payloadUid;

  try {
    const authState = await getAuthStateV1();
    const authUser = authState?.user || null;

    const stateDirect = uidFrom(authUser?.name, authUser?.email, authUser?.nick);
    if (
      stateDirect &&
      !stateDirect.startsWith("guest_") &&
      stateDirect !== "anonymous" &&
      stateDirect !== "null" &&
      stateDirect !== "undefined"
    ) {
      return stateDirect;
    }

    const stateJwtUid = uidFromJwtPayload(parseJwtPayload(authState?.access_token || ""));
    if (stateJwtUid) return stateJwtUid;
  } catch {}

  if (installUid && String(installUid).trim()) return String(installUid).trim();
  return "anonymous";
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
  if (["url", "domain", "wallet", "contract", "ticker", "text"].includes(k)) return k;
  return detectKind(raw);
}

function levelColor(level) {
  const s = String(level || "").toLowerCase();
  if (s === "critical") return T.bad;
  if (s === "danger") return "#ff7b7b";
  if (s === "suspicious") return T.warn;
  return T.good;
}

function levelBg(level) {
  const s = String(level || "").toLowerCase();
  if (s === "critical") return "rgba(255,107,107,0.14)";
  if (s === "danger") return "rgba(255,123,123,0.12)";
  if (s === "suspicious") return "rgba(255,181,71,0.12)";
  return "rgba(41,211,122,0.12)";
}

function sourceStatusColor(status) {
  const s = String(status || "").toLowerCase();
  if (s === "malicious") return T.bad;
  if (s === "clean") return T.good;
  if (s === "no_data") return T.dim;
  if (["timeout", "quota", "invalid_key", "error"].includes(s)) return T.warn;
  return T.dim;
}

function sourceStatusBg(status) {
  const s = String(status || "").toLowerCase();
  if (s === "malicious") return "rgba(255,107,107,0.14)";
  if (s === "clean") return "rgba(41,211,122,0.14)";
  if (s === "no_data") return "rgba(255,255,255,0.06)";
  if (["timeout", "quota", "invalid_key", "error"].includes(s)) return "rgba(255,181,71,0.14)";
  return "rgba(255,255,255,0.06)";
}

function formatSourceStatusText(status, item, lang) {
  const rawStatusText = String(item?.status_text || "").trim();
  const details = item?.details || {};

  const rawReason =
    [
      details?.message,
      details?.description,
      details?.detail,
      details?.reason,
      details?.error,
      item?.message,
      item?.error,
      item?.detail,
    ]
      .filter(Boolean)
      .join(" ") || "";

  const rawStatusLower = rawStatusText.toLowerCase();
  const rawReasonLower = rawReason.toLowerCase();
  const s = String(status || "").toLowerCase();

  const looksTechnical =
    rawStatusLower.includes("status_code") ||
    rawStatusLower.includes("errno") ||
    rawStatusLower.includes("body") ||
    rawStatusLower.includes("{") ||
    rawStatusLower.includes("}") ||
    rawStatusLower === "error" ||
    rawStatusLower === "";

  if (s === "clean") return pickLang(lang, "Чисто", "Clean");
  if (s === "malicious") return pickLang(lang, "Опасно", "Malicious");
  if (s === "no_data") return pickLang(lang, "Нет данных", "No data");
  if (s === "timeout") return pickLang(lang, "Таймаут сервиса", "Service timeout");
  if (s === "quota") return pickLang(lang, "Лимит сервиса", "Service limit");
  if (s === "invalid_key") return pickLang(lang, "Ключ не настроен", "Key not configured");

  if (
    rawReasonLower.includes("could not resolve domain") ||
    rawReasonLower.includes("domain could not be resolved") ||
    rawReasonLower.includes("name or service not known") ||
    rawReasonLower.includes("dns")
  ) {
    return pickLang(lang, "Домен не найден", "Domain not found");
  }

  if (rawReasonLower.includes("403") || rawReasonLower.includes("forbidden")) {
    return pickLang(lang, "Доступ ограничен", "Access restricted");
  }

  if (rawReasonLower.includes("401") || rawReasonLower.includes("unauthorized")) {
    return pickLang(lang, "Нужна авторизация", "Authorization required");
  }

  if (rawReasonLower.includes("timeout")) {
    return pickLang(lang, "Таймаут сервиса", "Service timeout");
  }

  if (rawReasonLower.includes("quota") || rawReasonLower.includes("rate limit") || rawReasonLower.includes("429")) {
    return pickLang(lang, "Лимит сервиса", "Service limit");
  }

  if (rawReasonLower.includes("invalid key") || rawReasonLower.includes("api key")) {
    return pickLang(lang, "Ключ не настроен", "Key not configured");
  }

  if (s === "error" || looksTechnical) {
    return pickLang(lang, "Не удалось проверить", "Could not verify");
  }

  if (rawStatusText) return rawStatusText;

  return pickLang(lang, "Недоступно", "Unavailable");
}

function prettyTitleFromCode(code, lang) {
  const map = {
    ticker_found: pickLang(lang, "Тикер найден", "Ticker found"),
    honeypot_checked: pickLang(lang, "Honeypot проверен", "Honeypot check completed"),
    honeypot_detected: pickLang(lang, "Высокий риск продажи", "High sell-risk detected"),
    honeypot_medium_risk: pickLang(lang, "Средний риск токена", "Moderate token risk found"),
    vt_detection: pickLang(lang, "Внешний сервис нашёл угрозу", "External threat flags found"),
    vt_clean: pickLang(lang, "Внешняя проверка чистая", "External check is clean"),
    gsb_match: pickLang(lang, "Google подтвердил угрозу", "Google confirmed a threat"),
    gsb_clean: pickLang(lang, "Google не нашёл угроз", "Google found no threat"),
    submitted_for_analysis: pickLang(lang, "Отправлено на анализ", "Submitted for additional analysis"),
    urlscan_submitted: pickLang(lang, "Скан страницы запущен", "External page scan started"),
    urlscan_dns_error: pickLang(lang, "Ошибка DNS", "Domain resolution failed"),
    verified_contract: pickLang(lang, "Контракт верифицирован", "Contract verified by explorer"),
    unverified_or_wallet: pickLang(lang, "Верификация не подтверждена", "No contract verification found"),
    token_listed: pickLang(lang, "Токен найден на рынке", "Token found on the market"),
    page_loaded: pickLang(lang, "Страница загружена", "Page loaded successfully"),
    seed_phrase_request: pickLang(lang, "Запрос seed phrase", "Seed phrase request"),
    secret_phrase_request: pickLang(lang, "Запрос secret phrase", "Secret phrase request"),
    recovery_phrase_request: pickLang(lang, "Запрос recovery phrase", "Recovery phrase request"),
    private_key_request: pickLang(lang, "Запрос private key", "Private key request"),
    private_key_hex_found: pickLang(lang, "Найден private key", "Private key detected"),
    wallet_connect_prompt: pickLang(lang, "Запрос подключения кошелька", "Wallet connection prompt"),
    claim_prompt: pickLang(lang, "Агрессивный claim-призыв", "Aggressive claim prompt"),
    airdrop_language: pickLang(lang, "Подозрительный airdrop-текст", "Suspicious airdrop wording"),
    verify_wallet_prompt: pickLang(lang, "Запрос verify wallet", "Wallet verification request"),
    connect_wallet_prompt: pickLang(lang, "Connect wallet prompt", "Connect wallet prompt"),
    fake_support_language: pickLang(lang, "Похоже на fake support", "Looks like fake support"),
    wallet_import_prompt: pickLang(lang, "Запрос импорта кошелька", "Wallet import prompt"),
    token_approval: pickLang(lang, "Рискованный token approval", "Risky token approval"),
    wallet_drainer_hint: pickLang(lang, "Признаки drainer", "Drainer warning signs"),
    brand_spoofing: pickLang(lang, "Риск подделки бренда", "Brand spoofing risk"),
    brand_impersonation: pickLang(lang, "Имитация известного бренда", "Trusted brand impersonation"),
    brand_plus_scam_keywords: pickLang(lang, "Бренд + scam-маркеры", "Brand mixed with scam markers"),
    host_keyword_airdrop: pickLang(lang, "Подозрительное слово в домене", "Suspicious keyword in domain"),
    host_keyword_bonus: pickLang(lang, "Подозрительное слово в домене", "Suspicious keyword in domain"),
    host_keyword_claim: pickLang(lang, "Подозрительное слово в домене", "Suspicious keyword in domain"),
    host_keyword_gift: pickLang(lang, "Подозрительное слово в домене", "Suspicious keyword in domain"),
    host_keyword_verify: pickLang(lang, "Подозрительное слово в домене", "Suspicious keyword in domain"),
    host_keyword_login: pickLang(lang, "Подозрительное слово в домене", "Suspicious keyword in domain"),
    host_keyword_support: pickLang(lang, "Подозрительное слово в домене", "Suspicious keyword in domain"),
    host_keyword_wallet: pickLang(lang, "Подозрительное слово в домене", "Suspicious keyword in domain"),
    host_keyword_connect: pickLang(lang, "Подозрительное слово в домене", "Suspicious keyword in domain"),
    host_keyword_reward: pickLang(lang, "Подозрительное слово в домене", "Suspicious keyword in domain"),
    host_keyword_secure: pickLang(lang, "Подозрительное слово в домене", "Suspicious keyword in domain"),
    hyphenated_suspicious_host: pickLang(lang, "Подозрительный формат домена", "Suspicious domain format"),
    redirect_to_different_host: pickLang(lang, "Редирект на другой домен", "Redirect to a different domain"),
    credential_or_wallet_prompt: pickLang(lang, "Запрос чувствительных данных", "Sensitive data request"),
    multiple_iframes: pickLang(lang, "Необычная структура страницы", "Unusual page structure"),
    domain_resolution_failed: pickLang(lang, "Домен не отвечает корректно", "Domain did not resolve correctly"),
    unverified_address: pickLang(lang, "Адрес не подтверждён", "Address not verified"),
    ticker_ambiguous: pickLang(lang, "Неоднозначный тикер", "Ticker match is ambiguous"),
    ticker_multiple_matches: pickLang(lang, "Несколько совпадений тикера", "Multiple ticker matches found"),
  };

  if (map[code]) return map[code];

  const pretty = String(code || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());

  return pretty || pickLang(lang, "Сигнал", "Signal");
}

function prettyEvidenceText(item, lang) {
  const code = String(item?.code || "").trim();

  const textMap = {
    ticker_found: pickLang(
      lang,
      "Найдено рыночное совпадение для этого тикера. Базовая идентификация выполнена.",
      "A market match was found for this ticker. Basic identification completed successfully."
    ),
    honeypot_checked: pickLang(
      lang,
      "Проверка модели продажи не показала критических ограничений.",
      "The sell-model check did not show critical restrictions or traps."
    ),
    honeypot_detected: pickLang(
      lang,
      "Есть признаки, что выход из позиции может быть ограничен или рискован.",
      "There are signs that exiting the position may be restricted or risky."
    ),
    honeypot_medium_risk: pickLang(
      lang,
      "Найдены умеренные риск-индикаторы. Нужна осторожность.",
      "Moderate risk indicators were found. Extra caution is advised."
    ),
    vt_detection: pickLang(
      lang,
      "Один из внешних движков отметил объект как опасный.",
      "One of the external engines flagged this object as dangerous."
    ),
    vt_clean: pickLang(
      lang,
      "На момент проверки внешний движок не нашёл опасных флагов.",
      "At the time of the check, the external engine found no dangerous flags."
    ),
    gsb_match: pickLang(
      lang,
      "Google Safe Browsing подтвердил угрозу.",
      "Google Safe Browsing confirmed a threat."
    ),
    gsb_clean: pickLang(
      lang,
      "Google Safe Browsing не нашёл угроз.",
      "Google Safe Browsing found no threats."
    ),
    submitted_for_analysis: pickLang(
      lang,
      "Проверка отправлена во внешний сервис. Финальный результат может появиться позже.",
      "The check was submitted to an external service. The final result may appear later."
    ),
    urlscan_submitted: pickLang(
      lang,
      "Страница отправлена на внешний поведенческий анализ.",
      "The page was submitted for an external behavioral scan."
    ),
    urlscan_dns_error: pickLang(
      lang,
      "Внешний сервис не смог корректно определить домен.",
      "The external service could not resolve the domain correctly."
    ),
    verified_contract: pickLang(
      lang,
      "Контракт показывает признаки верифицированного исходного кода.",
      "The contract shows signs of verified and published source code."
    ),
    unverified_or_wallet: pickLang(
      lang,
      "Проверка не подтвердила публичную верификацию контракта.",
      "The check did not confirm public contract verification."
    ),
    token_listed: pickLang(
      lang,
      "Токен найден в рыночных источниках. Это помогает уточнить идентификацию.",
      "The token was found in market sources, which helps refine identification."
    ),
    page_loaded: pickLang(
      lang,
      "Страница успешно загружена и проанализирована по содержимому.",
      "The page loaded successfully and was analyzed by content."
    ),
    seed_phrase_request: pickLang(
      lang,
      "Страница просит seed phrase. Это сильный риск-сигнал.",
      "The page asks for a seed phrase. This is a strong risk signal."
    ),
    secret_phrase_request: pickLang(
      lang,
      "Найден запрос secret phrase. Это выглядит опасно.",
      "A secret phrase request was detected. This looks dangerous."
    ),
    recovery_phrase_request: pickLang(
      lang,
      "Найден запрос recovery phrase. Для нормального сервиса это подозрительно.",
      "A recovery phrase request was found. This is unusual for a normal service."
    ),
    private_key_request: pickLang(
      lang,
      "Найден запрос private key. Это критический риск-сигнал.",
      "A private key request was found. This is a critical risk signal."
    ),
    private_key_hex_found: pickLang(
      lang,
      "В тексте найден паттерн, похожий на private key.",
      "A pattern similar to a private key was found in the text."
    ),
    wallet_connect_prompt: pickLang(
      lang,
      "Есть сильный призыв подключить кошелёк. Нужна осторожность.",
      "There is a strong wallet connection prompt. Caution is advised."
    ),
    claim_prompt: pickLang(
      lang,
      "Найден агрессивный claim/reward-призыв.",
      "An aggressive “claim now” reward prompt was detected."
    ),
    airdrop_language: pickLang(
      lang,
      "Есть формулировки, часто встречающиеся в подозрительных airdrop-сценариях.",
      "There is wording commonly seen in suspicious airdrop scenarios."
    ),
    verify_wallet_prompt: pickLang(
      lang,
      "Найден запрос verify wallet. Это часто используют phishing-страницы.",
      "A “verify wallet” request was found, which is often used by phishing pages."
    ),
    connect_wallet_prompt: pickLang(
      lang,
      "Страница подталкивает пользователя подключить кошелёк.",
      "The page pushes the user to connect a wallet."
    ),
    fake_support_language: pickLang(
      lang,
      "Формулировки похожи на fake support.",
      "The wording resembles fake support behavior."
    ),
    wallet_import_prompt: pickLang(
      lang,
      "Есть запрос импорта кошелька. Это рискованный сценарий.",
      "There is a prompt to import a wallet. This is a risky scenario."
    ),
    token_approval: pickLang(
      lang,
      "Есть риск небезопасного token approval.",
      "There is a risk of unsafe token approval."
    ),
    wallet_drainer_hint: pickLang(
      lang,
      "Есть косвенные признаки возможного drainer.",
      "There are indirect warning signs of a possible drainer."
    ),
    brand_spoofing: pickLang(
      lang,
      "Домен использует узнаваемый бренд, но не совпадает с официальным адресом.",
      "The domain uses a recognizable brand but does not match the official address."
    ),
    brand_impersonation: pickLang(
      lang,
      "Есть признаки имитации известного бренда.",
      "There are signs of trusted-brand impersonation."
    ),
    brand_plus_scam_keywords: pickLang(
      lang,
      "Адрес смешивает брендовые слова с типичными scam-маркерами.",
      "The address mixes brand-related words with typical scam markers."
    ),
    hyphenated_suspicious_host: pickLang(
      lang,
      "Формат домена выглядит необычно и может использоваться для маскировки.",
      "The domain format looks unusual and may be used for disguise."
    ),
    redirect_to_different_host: pickLang(
      lang,
      "После открытия есть редирект на другой домен.",
      "After opening, there is a redirect to a different domain."
    ),
    credential_or_wallet_prompt: pickLang(
      lang,
      "Страница запрашивает чувствительные данные в контексте кошелька или доступа.",
      "The page requests sensitive data in a wallet or access context."
    ),
    multiple_iframes: pickLang(
      lang,
      "Структура страницы выглядит необычно сложной.",
      "The page structure looks unusually complex."
    ),
    domain_resolution_failed: pickLang(
      lang,
      "Домен не смог корректно ответить во время проверки.",
      "The domain could not respond correctly during the check."
    ),
    unverified_address: pickLang(
      lang,
      "Адрес не получил достаточного подтверждения от explorers.",
      "The address did not receive sufficient confirmation from explorers."
    ),
    ticker_ambiguous: pickLang(
      lang,
      "Найдено совпадение тикера, но оно не выглядит полностью однозначным.",
      "A ticker match was found, but it does not look fully unambiguous."
    ),
    ticker_multiple_matches: pickLang(
      lang,
      "Есть несколько возможных совпадений для этого тикера.",
      "There are multiple possible matches for this ticker."
    ),
  };

  if (textMap[code]) return textMap[code];
  if (item?.text && typeof item.text === "string" && item.text.trim()) return item.text;

  return pickLang(lang, "Больше деталей доступно ниже.", "More details are available below.");
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

function formatKindLabel(kind, localized, lang) {
  if (localized) return localized;

  const k = String(kind || "").toLowerCase();
  if (k === "url") return "URL";
  if (k === "domain") return pickLang(lang, "Домен", "Domain");
  if (k === "wallet") return pickLang(lang, "Кошелёк", "Wallet");
  if (k === "contract") return pickLang(lang, "Контракт", "Contract");
  if (k === "ticker") return pickLang(lang, "Тикер", "Ticker");

  return pickLang(lang, "Текст", "Text");
}

function formatCommunityVerdict(v, lang) {
  const s = String(v || "").toLowerCase();
  if (s === "safe") return "SAFE";
  if (s === "scam") return "SCAM";
  if (s === "mixed") return pickLang(lang, "Смешано", "Mixed");
  return pickLang(lang, "Неизвестно", "Unknown");
}

function formatLevelLabel(level, lang) {
  const s = String(level || "").toLowerCase();
  if (s === "critical") return pickLang(lang, "Критично", "Critical");
  if (s === "danger") return pickLang(lang, "Опасно", "Danger");
  if (s === "suspicious") return pickLang(lang, "Подозрительно", "Suspicious");
  return pickLang(lang, "Безопасно", "Safe");
}

function getAiVerdictText(raw) {
  const result = raw?.ai_explanation_result || {};
  const structured = result?.structured || {};
  return (
    structured.details ||
    structured.short ||
    result.text ||
    raw?.ai_explanation ||
    raw?.human_explanation ||
    ""
  ).toString().trim();
}

function normalizeScanReport(raw, currentLang) {
  if (!raw || typeof raw !== "object") return null;

  const kind = normalizeKind(raw.kind, raw.input || raw.normalized_input || "");
  const score = Number(raw.score || 0) || 0;
  const level = String(raw.level || "safe").toLowerCase();
  const sources = Array.isArray(raw.sources) ? raw.sources : [];
  const evidence = Array.isArray(raw.evidence) ? raw.evidence : [];
  const details = raw.details || {};
  const token = details.token || {};
  const honeypot = token.honeypot || null;
  const topContributors = Array.isArray(details.top_score_contributors) ? details.top_score_contributors : [];

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
      (currentLang === "ru" ? raw.ai_verdict_ru || raw.verdict_ru : raw.ai_verdict_en || raw.verdict_en) ||
      raw.ai_verdict ||
      raw.verdict ||
      raw.level ||
      "",
    aiVerdictLabel:
      raw.ai_verdict_localized ||
      (currentLang === "ru" ? raw.ai_verdict_ru : raw.ai_verdict_en) ||
      raw.ai_verdict ||
      null,
    aiHumanVerdict: getAiVerdictText(raw),
    aiExplanationResult: raw.ai_explanation_result || null,
    sources,
    evidence,
    scoring: raw.scoring || {
      confirmed_external_signals: 0,
      heuristics: 0,
      page_content: 0,
      community_votes: 0,
    },
    community: raw.community || {
      community_verdict: "unknown",
      safe_votes: 0,
      scam_votes: 0,
      total_users: 0,
      immunity_score: 0,
    },
    details,
    backendDetails: {
      database: details.noytrix_scam_database || null,
      safetyGate: details.false_positive_safety_gate || null,
      scoreTrace: details.score_trace || null,
      topContributors,
      hardEvidenceCodes: Array.isArray(details.hard_evidence_codes) ? details.hard_evidence_codes : [],
      hardEvidenceFound: !!details.hard_evidence_found,
    },
    evidenceTrace: Array.isArray(details.evidence_trace) ? details.evidence_trace : [],
    token,
    honeypot,
    honeypot_verdict: raw.honeypot_verdict || null,
    honeypot_status: raw.honeypot_status || null,
    honeypot_risk: raw.honeypot_risk || honeypot?.risk || null,
    quota: raw.quota || null,
    what_can_happen: raw.what_can_happen || "",
    worst_case: raw.worst_case || "",
    permissions_summary: raw.permissions_summary || null,
  };
}

function explainBackendMessage(raw, lang) {
  const s = String(raw || "").toLowerCase();

  if (!s) {
    return pickLang(
      lang,
      "Сервер не вернул данные проверки. Попробуй ещё раз через несколько секунд.",
      "The server did not return data for this check. Try again in a few seconds."
    );
  }

  if (s.includes("429") || s.includes("quota") || s.includes("limit")) {
    return pickLang(
      lang,
      "FREE лимит проверок уже использован. PRO убирает этот лимит.",
      "Your free daily checks are already used up. PRO removes this limit."
    );
  }

  if (s.includes("403") || s.includes("forbidden") || s.includes("app key")) {
    return pickLang(
      lang,
      "Проверка сейчас недоступна из-за ограничения доступа. Перезапусти приложение и попробуй снова.",
      "The check is currently unavailable because of access restrictions. Reopen the app and try again."
    );
  }

  if (s.includes("network request failed") || s.includes("failed to fetch") || s.includes("fetch")) {
    return pickLang(
      lang,
      "Не удалось связаться с сервером. Проверь интернет и попробуй снова.",
      "We could not reach the server. Check your connection and try again."
    );
  }

  if (s.includes("timeout") || s.includes("aborted")) {
    return pickLang(
      lang,
      "Сервер слишком долго отвечал. Попробуй повторить проверку чуть позже.",
      "The server took too long to respond. Please try the check again a bit later."
    );
  }

  if (s.includes("invalid json")) {
    return pickLang(
      lang,
      "Сервер вернул неполный ответ. Запусти проверку ещё раз.",
      "The server returned an incomplete response. Please run the check again."
    );
  }

  if (s.includes("http 500") || s.includes("scan failed")) {
    return pickLang(
      lang,
      "Сервер не смог завершить проверку сейчас. Попробуй позже.",
      "The server could not complete the check right now. Please try again later."
    );
  }

  return pickLang(
    lang,
    "Проверку сейчас не удалось завершить. Попробуй ещё раз через несколько секунд.",
    "The check could not be completed right now. Please try again in a few seconds."
  );
}

const SAMPLES = [
  { h: "https://binance-airdrop-bonus.net", dRu: "Фишинг под Binance", dEn: "Phishing pretending to be Binance" },
  { h: "https://metamask-support-login.com", dRu: "Фейковая поддержка MetaMask", dEn: "Fake MetaMask support" },
  { h: "http://paypal.com.verify-account-security.com", dRu: "Ловушка с поддоменом PayPal", dEn: "PayPal subdomain trap" },
  { h: "0x1111111254EEB25477B68fB85Ed929F73A960582", dRu: "EVM адрес / контракт", dEn: "EVM address / contract" },
  { h: "BTC", dRu: "Проверка тикера", dEn: "Ticker check" },
  { h: "connect wallet to claim reward now enter seed phrase", dRu: "Опасный текст", dEn: "Dangerous text" },
];

const HK = (uid) => `profile.${uid}:history`;

const SHIELD_FREE_DAILY_LIMIT = 4;
const SHIELD_QUOTA_KEY = "shield.quota.v1";

function shieldTodayKey() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

async function loadShieldQuotaLocal() {
  try {
    const raw = await AsyncStorage.getItem(SHIELD_QUOTA_KEY);
    const today = shieldTodayKey();
    if (!raw) return { day: today, used: 0 };
    const j = JSON.parse(raw);
    if (!j?.day || j.day !== today) return { day: today, used: 0 };
    return { day: today, used: Math.max(0, Number(j.used || 0)) };
  } catch {
    return { day: shieldTodayKey(), used: 0 };
  }
}

async function saveShieldQuotaLocal(q) {
  try {
    await AsyncStorage.setItem(SHIELD_QUOTA_KEY, JSON.stringify(q));
  } catch {}
}


async function appendHistory(uid, event) {
  if (!uid) return;

  try {
    const raw = await AsyncStorage.getItem(HK(uid));
    const arr = raw ? JSON.parse(raw) : [];
    const next = [{ ...event }, ...(Array.isArray(arr) ? arr : [])].slice(0, 200);
    await AsyncStorage.setItem(HK(uid), JSON.stringify(next));
  } catch {}
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

  const purchaseToken = await pick([
    "play.purchaseToken",
    "google.play.purchaseToken",
    "iap.purchaseToken",
    "purchaseToken",
    "pro.purchaseToken",
  ]);

  const productId = await pick([
    "play.productId",
    "google.play.productId",
    "iap.productId",
    "productId",
    "pro.productId",
  ]);

  const entitlementId = await pick([
    "entitlement.id",
    "entitlementId",
    "iap.entitlementId",
    "pro.entitlementId",
    "revenuecat.entitlement",
  ]);

  const authState = await getAuthStateV1();

  const accessToken =
    authState?.access_token ||
    (await pick([
      "accessToken",
      "auth.accessToken",
      "user.accessToken",
      "jwt",
      "token",
      "access",
      "auth.access",
      "auth.token",
      "auth.jwt",
      "session.accessToken",
      "auth.session.accessToken",
    ]));

  return {
    purchaseToken,
    productId,
    entitlementId,
    accessToken: accessToken || null,
    authUser: authState?.user || null,
  };
}

const ScoreBar = ({ value, color, height = 8 }) => (
  <View
    style={{
      height,
      borderRadius: 999,
      backgroundColor: "rgba(255,255,255,0.08)",
      overflow: "hidden",
      marginTop: 6,
    }}
  >
    <View
      style={{
        height,
        borderRadius: 999,
        width: `${Math.min(100, Math.max(0, Number(value || 0)))}%`,
        backgroundColor: color,
      }}
    />
  </View>
);

const MetricChip = ({ label, value, full = false }) => (
  <View
    style={{
      width: full ? "100%" : "48.5%",
      borderWidth: 1,
      borderColor: T.border,
      borderRadius: 14,
      padding: 12,
      backgroundColor: "rgba(255,255,255,0.03)",
      marginBottom: 10,
    }}
  >
    <Text style={{ color: T.dim, fontSize: 12, marginBottom: 4 }}>{label}</Text>
    <Text style={{ color: T.text, fontWeight: "900", fontSize: 15 }} numberOfLines={full ? 2 : 1}>
      {safeText(value)}
    </Text>
  </View>
);

const CompactSourceRow = ({ item, currentLang }) => {
  const status = String(item?.status || "").toLowerCase();
  const prettyStatus = formatSourceStatusText(status, item, currentLang);

  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "space-between",
        paddingVertical: 10,
        borderTopWidth: 1,
        borderTopColor: "rgba(255,255,255,0.06)",
      }}
    >
      <Text style={{ color: T.text, fontWeight: "800", fontSize: 14, flex: 1, marginRight: 10 }}>
        {formatSourceName(item?.name, currentLang)}
      </Text>

      <View
        style={{
          paddingHorizontal: 10,
          paddingVertical: 5,
          borderRadius: 999,
          backgroundColor: sourceStatusBg(status),
          borderWidth: 1,
          borderColor: T.border,
        }}
      >
        <Text style={{ color: sourceStatusColor(status), fontWeight: "900", fontSize: 12 }}>
          {prettyStatus}
        </Text>
      </View>
    </View>
  );
};


const UxRiskBlock = ({ report, currentLang, tx }) => {
  if (!report) return null;

  const uiLang = String(report?.lang || currentLang || "en").toLowerCase().startsWith("ru") ? "ru" : "en";
  const isRu = uiLang === "ru";
  const kind = String(report?.kind || "").toLowerCase();
  const permissions = report?.permissions_summary || null;
  const tokens = Array.isArray(permissions?.tokens) ? permissions.tokens.filter(Boolean) : [];

  let whatText = String(report?.what_can_happen || "").trim();
const worstText = String(report?.worst_case || "").trim();

  const hasRealPermissions =
    permissions &&
    (kind === "wallet" || kind === "contract" || kind === "transaction" || permissions?.can_spend === true) &&
    (
      permissions.can_spend === true ||
      permissions.unlimited === true ||
      tokens.length > 0 ||
      (permissions.spend_limit && permissions.spend_limit !== "unknown" && permissions.spend_limit !== "?")
    );

  
const tokenText =
  Array.isArray(report?.permissions_summary?.tokens) &&
  report.permissions_summary.tokens.length
    ? report.permissions_summary.tokens.join(", ")
    : null;

if (tokenText) {
    whatText = whatText.split("??????").join(tokenText).split("??????").join(tokenText).replace(/tokens/gi, tokenText);
  }
const rows = [

    whatText ? {
      icon: "flame-outline",
      title: tx("shield.ux.whatCanHappen", isRu ? "\u0427\u0442\u043e \u043c\u043e\u0436\u0435\u0442 \u043f\u0440\u043e\u0438\u0437\u043e\u0439\u0442\u0438" : "What can happen"),
      text: whatText,
      color: T.warn,
    } : null,

    worstText ? {
      icon: "skull-outline",
      title: tx("shield.ux.worstCase", isRu ? "\u0425\u0443\u0434\u0448\u0438\u0439 \u0441\u0446\u0435\u043d\u0430\u0440\u0438\u0439" : "Worst case"),
      text: worstText,
      color: T.bad,
    } : null,

    ...(hasRealPermissions ? [{
      icon: "key-outline",
      title: tx("shield.ux.permissions", isRu ? "\u0427\u0442\u043e \u0442\u044b \u0440\u0430\u0437\u0440\u0435\u0448\u0430\u0435\u0448\u044c" : "What you are approving"),
      text: String(permissions?.summary || permissions?.note || "").trim(),
      color: T.accent,
      extra: [
        permissions.can_spend === true ? `${isRu ? "\u041c\u043e\u0436\u0435\u0442 \u0441\u043f\u0438\u0441\u044b\u0432\u0430\u0442\u044c" : "Can spend"}: ${isRu ? "\u0434\u0430" : "yes"}` : "",
        permissions.unlimited === true ? `${isRu ? "\u041b\u0438\u043c\u0438\u0442" : "Spend limit"}: \u221e` : "",
        permissions.spend_limit && permissions.spend_limit !== "unknown" && permissions.spend_limit !== "?" ? `${isRu ? "\u041b\u0438\u043c\u0438\u0442" : "Spend limit"}: ${safeText(permissions.spend_limit)}` : "",
        tokens.length ? `${isRu ? "\u0422\u043e\u043a\u0435\u043d\u044b" : "Tokens"}: ${tokens.join(", ")}` : "",
        permissions?.spender_trust ? `${isRu ? "\u0420\u0435\u043f\u0443\u0442\u0430\u0446\u0438\u044f spender" : "Spender reputation"}: ${permissions.spender_trust}` : "",
permissions?.spender_label ? `${isRu ? "\u041a\u043e\u043c\u0443 \u0434\u0430\u0451\u0448\u044c \u0434\u043e\u0441\u0442\u0443\u043f" : "Spender"}: ${permissions.spender_label}` : permissions?.spender ? `${isRu ? "\u041a\u043e\u043c\u0443 \u0434\u0430\u0451\u0448\u044c \u0434\u043e\u0441\u0442\u0443\u043f" : "Spender"}: ${permissions.spender}` : "",
      ].filter(Boolean),
      revokeUrl: permissions?.can_spend === true ? "https://revoke.cash/" : "",
    }] : []),
  ].filter(Boolean);

  if (!rows.length) return null;

  return (
    <BlurCard style={{ borderColor: "rgba(255,176,32,0.30)" }}>
      <Text style={{ color: T.text, fontWeight: "900", fontSize: 18, marginBottom: 10 }}>
        {tx("shield.ux.title", isRu ? "\u0427\u0442\u043e \u0440\u0435\u0430\u043b\u044c\u043d\u043e \u043c\u043e\u0436\u0435\u0442 \u0441\u043b\u0443\u0447\u0438\u0442\u044c\u0441\u044f" : "What can actually happen")}
      </Text>

      {rows.map((row, idx) => (
        <View key={`ux-risk-${idx}`} style={{ borderWidth: 1, borderColor: T.borderSoft, borderRadius: 16, padding: 12, marginBottom: idx === rows.length - 1 ? 0 : 10, backgroundColor: "rgba(255,255,255,0.035)" }}>
          <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 7 }}>
            <Ionicons name={row.icon} size={18} color={row.color} />
            <Text style={{ color: row.color, fontWeight: "900", fontSize: 15, marginLeft: 8, flex: 1 }}>{row.title}</Text>
          </View>

          {!!row.text && <Text style={{ color: T.text, lineHeight: 20, fontWeight: "700" }}>{row.text}</Text>}

          {!!row.extra?.length && (
            <View style={{ marginTop: 10 }}>
              {row.extra.map((x, i) => (
                <Text key={`ux-extra-${i}`} style={{ color: T.dim, lineHeight: 19, marginTop: 2 }}>{x}</Text>
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
              <Ionicons name="close-circle-outline" size={18} color={T.bad} />
              <Text style={{ color: T.bad, fontWeight: "900", fontSize: 15, marginLeft: 8 }}>
                {isRu ? "\u041e\u0442\u043e\u0437\u0432\u0430\u0442\u044c \u0434\u043e\u0441\u0442\u0443\u043f" : "Revoke approval"}
              </Text>
            </TouchableOpacity>
          )}
        </View>
      ))}
    </BlurCard>
  );
};

const TopSignalRow = ({ item, currentLang }) => {
  const title = item?.code ? prettyTitleFromCode(item?.code, currentLang) : safeText(backendSignalText(item));
  const body = prettyEvidenceText(item, currentLang);

  return (
    <View
      style={{
        borderWidth: 1,
        borderColor: T.borderSoft,
        borderRadius: 14,
        padding: 12,
        marginBottom: 10,
        backgroundColor: "rgba(255,255,255,0.03)",
      }}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <Text style={{ color: T.text, fontWeight: "900", flex: 1, fontSize: 15 }}>
          {title}
        </Text>
        <Text style={{ color: T.accent, fontWeight: "900", marginLeft: 8 }}>
          +{safeText(item?.severity || 0)}
        </Text>
      </View>

      {!!item?.source && (
        <Text style={{ color: T.dim, marginTop: 4, fontSize: 12 }}>
          {pickLang(currentLang, "Источник", "Source")}: {formatSourceName(item.source, currentLang)}
        </Text>
      )}

      <Text style={{ color: T.dim, marginTop: 8, lineHeight: 19 }}>{body}</Text>
    </View>
  );
};

function backendSignalText(item) {
  if (!item || typeof item !== "object") return String(item || "");
  return item.text || item.reason || item.code || item.source || item.label || "";
}

function backendIntelLabel(lang, key) {
  const ru = {
    title: "\u0421\u0435\u0440\u0432\u0435\u0440\u043d\u044b\u0435 \u0434\u0430\u043d\u043d\u044b\u0435",
    db: "Noytrix DB",
    safety: "\u0417\u0430\u0449\u0438\u0442\u0430 \u043e\u0442 \u043b\u043e\u0436\u043d\u044b\u0445 \u0441\u0440\u0430\u0431\u0430\u0442\u044b\u0432\u0430\u043d\u0438\u0439",
    evidence: "\u0421\u0435\u0440\u0432\u0435\u0440\u043d\u044b\u0435 \u0441\u0438\u0433\u043d\u0430\u043b\u044b",
    hard: "\u0416\u0435\u0441\u0442\u043a\u0438\u0435 \u0441\u0438\u0433\u043d\u0430\u043b\u044b",
    matched: "\u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0441\u043e\u0432\u043f\u0430\u0434\u0435\u043d\u0438\u0435",
    notListed: "\u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0432 \u0431\u0430\u0437\u0435",
    applied: "\u0441\u0440\u0430\u0431\u043e\u0442\u0430\u043b\u0430",
    notApplied: "\u043d\u0435 \u0441\u0440\u0430\u0431\u043e\u0442\u0430\u043b\u0430",
  };
  const uk = {
    title: "\u0421\u0435\u0440\u0432\u0435\u0440\u043d\u0456 \u0434\u0430\u043d\u0456",
    db: "Noytrix DB",
    safety: "\u0417\u0430\u0445\u0438\u0441\u0442 \u0432\u0456\u0434 \u0445\u0438\u0431\u043d\u0438\u0445 \u0441\u043f\u0440\u0430\u0446\u044e\u0432\u0430\u043d\u044c",
    evidence: "\u0421\u0435\u0440\u0432\u0435\u0440\u043d\u0456 \u0441\u0438\u0433\u043d\u0430\u043b\u0438",
    hard: "\u0416\u043e\u0440\u0441\u0442\u043a\u0456 \u0441\u0438\u0433\u043d\u0430\u043b\u0438",
    matched: "\u0437\u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0437\u0431\u0456\u0433",
    notListed: "\u043d\u0435 \u0437\u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0432 \u0431\u0430\u0437\u0456",
    applied: "\u0441\u043f\u0440\u0430\u0446\u044e\u0432\u0430\u043b\u0430",
    notApplied: "\u043d\u0435 \u0441\u043f\u0440\u0430\u0446\u044e\u0432\u0430\u043b\u0430",
  };
  const en = {
    title: "Backend intelligence",
    db: "Noytrix DB",
    safety: "Safety gate",
    evidence: "Backend evidence",
    hard: "Hard evidence",
    matched: "matched",
    notListed: "not listed",
    applied: "applied",
    notApplied: "not applied",
  };
  return (String(lang || "").toLowerCase().startsWith("uk") ? uk : String(lang || "").toLowerCase().startsWith("ru") ? ru : en)[key] || key;
}

const BackendIntelCard = ({ report, currentLang, tx }) => {
  const intel = report?.backendDetails || {};
  const rows = [];
  const db = intel.database || {};
  const dbMatch = db.match || {};
  const gate = intel.safetyGate || {};

  if (db.reason || dbMatch.database) {
    rows.push({
      label: backendIntelLabel(currentLang, "db"),
      value: `${dbMatch.status || (dbMatch.matched ? backendIntelLabel(currentLang, "matched") : backendIntelLabel(currentLang, "notListed"))}${db.reason ? ` · ${db.reason}` : ""}`,
    });
  }

  if (typeof gate.applied === "boolean" || gate.reason) {
    rows.push({
      label: backendIntelLabel(currentLang, "safety"),
      value: `${gate.applied ? backendIntelLabel(currentLang, "applied") : backendIntelLabel(currentLang, "notApplied")}${gate.reason ? ` · ${gate.reason}` : ""}`,
    });
  }

  (intel.topContributors || []).slice(0, 3).forEach((item, idx) => {
    const text = backendSignalText(item);
    if (text) rows.push({ label: idx === 0 ? backendIntelLabel(currentLang, "evidence") : "", value: text });
  });

  if ((intel.hardEvidenceCodes || []).length) {
    rows.push({ label: backendIntelLabel(currentLang, "hard"), value: intel.hardEvidenceCodes.slice(0, 5).join(", ") });
  }

  if (!rows.length) return null;

  return (
    <BlurCard>
      <Text style={{ color: T.text, fontWeight: "900", fontSize: 16, marginBottom: 10 }}>
        {tx("shield.backendIntel.title", backendIntelLabel(currentLang, "title"))}
      </Text>
      {rows.map((row, idx) => (
        <View key={`backend-intel-${idx}`} style={{ marginBottom: idx === rows.length - 1 ? 0 : 10 }}>
          {!!row.label && <Text style={{ color: T.accent, fontWeight: "900", fontSize: 12, marginBottom: 3 }}>{row.label}</Text>}
          <Text style={{ color: T.dim, lineHeight: 18 }}>{safeText(row.value)}</Text>
        </View>
      ))}
    </BlurCard>
  );
};

export default function Shield() {
  const i18nHook = useI18n();
  const t0 = i18nHook?.t;

  const tx = useMemo(() => {
    const real = typeof t0 === "function" ? t0 : null;

    return (key, fallback, opts) => {
      try {
        if (real) {
          const v = real(key, opts);
          if (typeof v === "string" && v === key) return fallback != null ? fallback : key;
          if (typeof v === "string" && v.trim() !== "") return v;
          if (v != null && typeof v !== "string") return v;
        }
      } catch {}

      return fallback != null ? fallback : typeof key === "string" ? key : "";
    };
  }, [t0]);

  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const isAuth = useAuthStore((s) => s.isAuth);

  const currentLang = useMemo(() => {
    const v = i18nHook?.lang || i18nHook?.language || i18nHook?.i18n?.language || i18nHook?.locale || "en";
    const s = String(v || "").toLowerCase();
    return s.startsWith("ru") ? "ru" : "en";
  }, [i18nHook]);

  useEffect(() => {
    logEvent("screen_open", { screen: "shield" });
  }, []);

  const authUid = useMemo(() => uidFrom(user?.name, user?.email, user?.nick), [user?.name, user?.email, user?.nick]);

  const [installUid, setInstallUid] = useState("");
  const [resolvedUid, setResolvedUid] = useState("");
  const uid = resolvedUid || authUid || installUid || "anonymous";

  useEffect(() => {
    (async () => {
      const stable = await getOrCreateInstallUserId();
      setInstallUid(stable);
    })();
  }, []);

  useEffect(() => {
    (async () => {
      const proof = await loadProProof();
      const best = await getBestKnownUid(user || proof?.authUser, installUid, proof?.accessToken || "");
      setResolvedUid(best);
    })();
  }, [user, installUid, isAuth]);

  const [input, setInput] = useState("");
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showSamples, setShowSamples] = useState(false);
  const [backendError, setBackendError] = useState("");
  const [submittingVote, setSubmittingVote] = useState(false);

  const [quota, setQuota] = useState({ used: 0, limit: 4, left: 4, dayKey: "" });
  const [quotaBlocked, setQuotaBlocked] = useState(false);
  const [showQuotaModal, setShowQuotaModal] = useState(false);
  const [quotaMsg, setQuotaMsg] = useState("");

  // shield_quota_init_display
  useEffect(() => {
    let alive = true;

    (async () => {
      if (isPro) {
        if (!alive) return;
        setQuota({ used: 0, limit: SHIELD_FREE_DAILY_LIMIT, left: SHIELD_FREE_DAILY_LIMIT, dayKey: shieldTodayKey() });
        setQuotaBlocked(false);
        return;
      }

      const q = await loadShieldQuotaLocal();
      if (!alive) return;

      setQuota({
        used: q.used,
        limit: SHIELD_FREE_DAILY_LIMIT,
        left: Math.max(0, SHIELD_FREE_DAILY_LIMIT - q.used),
        dayKey: q.day,
      });
      setQuotaBlocked(q.used >= SHIELD_FREE_DAILY_LIMIT);
    })();

    return () => {
      alive = false;
    };
  }, [isPro]);

  const [proLocal, setProLocal] = useState(false);
  const [authAccess, setAuthAccess] = useState(null);

  const shareShotRef = useRef(null);
  const [sharingNow, setSharingNow] = useState(false);

  useFocusEffect(
    useCallback(() => {
      let alive = true;

      (async () => {
        try {
          const prefill = await AsyncStorage.getItem(SHIELD_PREFILL_KEY);
          if (!alive) return;

          if (prefill && String(prefill).trim()) {
            setInput(String(prefill).trim());
            await AsyncStorage.removeItem(SHIELD_PREFILL_KEY);
          }
        } catch {}
      })();

      return () => {
        alive = false;
      };
    }, [])
  );

  useEffect(() => {
    (async () => {
      const token = await getAuthAccessToken();
      setAuthAccess(token || null);
    })();
  }, [user, isAuth]);

  const hasPro = useMemo(() => {
    const plan = (user?.plan || user?.subscription || user?.tier || user?.entitlement || "").toString().toLowerCase();
    const u1 = user?.isPro === true || user?.pro === true || user?.premium === true;
    const u2 = String(user?.status || "").toLowerCase() === "pro";
    return plan.includes("pro") || u1 || u2;
  }, [
    user?.plan,
    user?.subscription,
    user?.tier,
    user?.entitlement,
    user?.isPro,
    user?.pro,
    user?.premium,
    user?.status,
  ]);

  const isPro = hasPro || proLocal;

  useEffect(() => {
    (async () => {
      try {
        const keysToCheck = [
          "isPro",
          "noytrix.isPro",
          "pro",
          "proActive",
          "subscription.pro",
          "iap.isPro",
          "iap.pro",
          "entitlement.pro",
          "noytrix_pro_flag",
        ];

        let localPro = false;

        for (const k of keysToCheck) {
          const v = await AsyncStorage.getItem(k);
          const s = String(v || "").toLowerCase();

          if (s === "true" || s === "1" || s === "yes" || s === "active") {
            localPro = true;
            break;
          }
        }

        if (!localPro) {
          try {
            const proof = await loadProProof();
            const authHeader = proof?.accessToken || authAccess || null;
            const bestUid = await getBestKnownUid(user || proof?.authUser, installUid, authHeader || "");

            if (authHeader) {
              const res = await safeFetchRaw(
                `${BACKEND}/iap/status`,
                {
                  headers: {
                    Authorization: `Bearer ${authHeader}`,
                    "Accept-Language": currentLang,
                    "X-User-Id": bestUid || "anonymous",
                  },
                },
                12000
              );

              if (res.ok) {
                const text = await res.text();

                let j = null;
                try {
                  j = text ? JSON.parse(text) : null;
                } catch {
                  j = null;
                }

                const plan = String(j?.plan || "").toLowerCase();

                if (plan === "pro") {
                  localPro = true;
                  try {
                    await AsyncStorage.setItem("isPro", "true");
                  } catch {}
                }
              }
            }
          } catch {}
        }

        setProLocal(!!localPro);
      } catch {
        setProLocal(false);
      }
    })();
  }, [uid, authAccess, currentLang, user, installUid]);

  const normalizedReport = useMemo(() => normalizeScanReport(report, currentLang), [report, currentLang]);

  const verdictLabel = normalizedReport?.verdictLabel || "";
  const verdictColor = levelColor(normalizedReport?.level);
  const verdictBg = levelBg(normalizedReport?.level);

  const targetLabel =
    normalizedReport?.details?.page?.final_url ||
    normalizedReport?.normalized_input ||
    normalizedReport?.input ||
    "";

  const topEvidence = useMemo(() => {
    const backendTop = normalizedReport?.backendDetails?.topContributors;
    if (Array.isArray(backendTop) && backendTop.length) return backendTop.slice(0, 3);
    return Array.isArray(normalizedReport?.evidence) ? normalizedReport.evidence.slice(0, 3) : [];
  }, [normalizedReport]);

  const compactSources = useMemo(() => {
    return Array.isArray(normalizedReport?.sources) ? normalizedReport.sources.slice(0, 4) : [];
  }, [normalizedReport]);

  const samplesI18n = tx("shield.samples.items", null, { returnObjects: true });

  const quotaPillText = useMemo(() => { if (isPro) return pickLang(currentLang, "PRO • безлимит", "PRO • unlimited"); const used = Number(quota?.used || 0); const limit = Number(quota?.limit || quota?.freeLimit || 4); return pickLang(currentLang, `FREE • ${used}/${limit} проверок`, `FREE • ${used}/${limit} checks`); }, [isPro, quota, currentLang]);

  const freeInfoText = useMemo(() => {
    return tx(
      "shield.freeInfo",
      pickLang(
        currentLang,
        "FREE показывает главный вердикт, ключевые сигналы, основные источники и мнение сообщества.",
        "FREE shows the main verdict, key signals, main sources, and community opinion."
      )
    );
  }, [tx, currentLang]);

  const proTeaserItems = useMemo(
    () => [
      tx("shield.proTeaser.items.0", pickLang(currentLang, "Больше деталей по источникам", "Deeper source details")),
      tx("shield.proTeaser.items.1", pickLang(currentLang, "Полный data-heavy интерфейс", "Full data-heavy interface")),
      tx("shield.proTeaser.items.2", pickLang(currentLang, "Безлимитные проверки", "Unlimited scans")),
    ],
    [tx, currentLang]
  );

  const shareMessage = useMemo(() => {
    if (!normalizedReport) return "";

    const title = tx("shield.share.textTitle", "ScamShield");
    const typeTitle = tx("shield.share.typeTitle", pickLang(currentLang, "Тип", "Type"));
    const objectTitle = tx("shield.share.objectTitle", pickLang(currentLang, "Объект", "Object"));

    return (
      title +
      ": " +
      verdictLabel +
      " (" +
      normalizedReport.score +
      "/100)\n" +
      typeTitle +
      ": " +
      normalizedReport.kindLabel +
      "\n" +
      objectTitle +
      ": " +
      (targetLabel || "-")
    );
  }, [normalizedReport, verdictLabel, tx, currentLang, targetLabel]);

  const onCopy = async (text) => {
    try {
      await Clipboard.setStringAsync(text || "");

      showAppAlert(
        tx("common.copied", pickLang(currentLang, "Скопировано", "Copied")),
        tx("shield.copied", pickLang(currentLang, "Скопировано в буфер обмена.", "Copied to clipboard."))
      );
    } catch {}
  };

  const onOpen = async (url) => {
    try {
      if (!url || !reIsHttp.test(url)) return;
      await Linking.openURL(url);
    } catch {}
  };

  const onCheck = async () => {
    const value = (input || "").trim();
    if (!value) return;

    const proof = await loadProProof();
    const accessToken = proof?.accessToken || authAccess || null;
    const effectiveUser = user || proof?.authUser || null;
    const effectiveUid = await getBestKnownUid(effectiveUser, installUid, accessToken || "");
    const stableUserId = String(effectiveUid || uid || installUid || "anonymous").trim() || "anonymous";

    // shield_quota_precheck
    if (!isPro) {
      const q = await loadShieldQuotaLocal();

      setQuota({
        used: q.used,
        limit: SHIELD_FREE_DAILY_LIMIT,
        left: Math.max(0, SHIELD_FREE_DAILY_LIMIT - q.used),
        dayKey: q.day,
      });

      if (q.used >= SHIELD_FREE_DAILY_LIMIT) {
        setQuotaBlocked(true);
        setQuotaMsg(
          tx(
            "shield.quota.exceeded",
            pickLang(currentLang, "FREE лимит 4 проверки в день достигнут. PRO убирает лимиты.", "FREE limit of 4 checks per day reached. PRO removes limits.")
          )
        );
        setShowQuotaModal(false);
        return;
      }

      setQuotaBlocked(false);
    }

    logEvent("scan_submitted", { screen: "shield", lang: currentLang, has_input: true });

    setLoading(true);
    setBackendError("");
    setReport(null);

    try {
      const headers = {
        "Accept-Language": currentLang,
        "X-User-Id": stableUserId,
      };

      if (proof?.productId) headers["X-Play-Product-Id"] = proof.productId;
      if (proof?.purchaseToken) headers["X-Play-Purchase-Token"] = proof.purchaseToken;
      if (proof?.entitlementId) headers["X-Entitlement-Id"] = proof.entitlementId;
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

      const res = await safeFetchRaw(
        `${BACKEND}/scan?input=${encodeURIComponent(value)}&lang=${encodeURIComponent(currentLang)}&userId=${encodeURIComponent(stableUserId)}`,
        { headers }
      );

      const rawText = await res.text();

      let backend = null;
      try {
        backend = rawText ? JSON.parse(rawText) : null;
      } catch {
        throw new Error("invalid_json");
      }

      const serverQuota = backend?.quota || null;

      if (serverQuota && !isPro) {
        const used = Number(serverQuota.used || 0);
        const limit = Number(serverQuota.freeLimit || serverQuota.limit || 4);
        const left = Math.max(0, Number(serverQuota.left ?? (limit - used)));

        setQuota({
          used,
          limit,
          left,
          dayKey: String(serverQuota.day || ""),
        });

        setQuotaBlocked(left <= 0 || used >= limit);
      }

      if (res.status === 429) {
        const msg =
          backend?.detail ||
          tx(
            "shield.quota.exceeded",
            pickLang(currentLang, "FREE лимит 4 проверки в день достигнут. PRO убирает лимиты.", "FREE limit of 4 checks per day reached. PRO removes limits.")
          );

        setQuotaMsg(String(msg));
        setShowQuotaModal(false);
        setQuotaBlocked(true);
        return;
      }

      if (!res.ok) {
        throw new Error(String(backend?.detail || `http_${res.status}`));
      }

      const final = normalizeScanReport(backend, currentLang);
      setReport(final);

      if (isPro) {
        setQuota({ used: 0, limit: SHIELD_FREE_DAILY_LIMIT, left: SHIELD_FREE_DAILY_LIMIT, dayKey: shieldTodayKey() });
        setQuotaBlocked(false);
        setShowQuotaModal(false);
      } else if (serverQuota) {
        const used = Number(serverQuota.used || 0);
        const limit = Number(serverQuota.freeLimit || serverQuota.limit || SHIELD_FREE_DAILY_LIMIT);
        const left = Math.max(0, Number(serverQuota.left ?? (limit - used)));

        setQuota({
          used,
          limit,
          left,
          dayKey: String(serverQuota.day || shieldTodayKey()),
        });

        setQuotaBlocked(left <= 0 || used >= limit);
      } else {
        const q = await loadShieldQuotaLocal();
        const next = {
          day: q.day,
          used: Math.min(SHIELD_FREE_DAILY_LIMIT, q.used + 1),
        };

        await saveShieldQuotaLocal(next);

        setQuota({
          used: next.used,
          limit: SHIELD_FREE_DAILY_LIMIT,
          left: Math.max(0, SHIELD_FREE_DAILY_LIMIT - next.used),
          dayKey: next.day,
        });

        setQuotaBlocked(next.used >= SHIELD_FREE_DAILY_LIMIT);
      }

      const title =
        final?.kind === "url" || final?.kind === "domain"
          ? `ScamShield: ${final.level} — ${final?.details?.page?.final_url || final?.normalized_input || value}`
          : `ScamShield: ${final.level} — ${value.slice(0, 60)}`;

      await appendHistory(stableUserId, {
        id: Date.now(),
        type: "scamshield",
        title,
        at: Date.now(),
        meta: {
          level: final?.level,
          score: final?.score,
          object: final?.normalized_input || value,
          isScam: final?.level === "danger" || final?.level === "critical",
        },
      });

      logEvent("scan_result", {
        screen: "shield",
        lang: currentLang,
        level: final?.level || "n/a",
        score: Number(final?.score ?? 0),
        kind: final?.kind || "text",
        backend_ok: true,
      });
    } catch (e) {
      setReport(null);

      const humanMessage = explainBackendMessage(String(e?.message || e || ""), currentLang);
      setBackendError(humanMessage);

      showAppAlert(
        tx("shield.backendError.title", pickLang(currentLang, "Проверка недоступна", "Check unavailable")),
        humanMessage
      );

      logEvent("scan_result", {
        screen: "shield",
        lang: currentLang,
        level: "n/a",
        score: 0,
        kind: detectKind(value),
        backend_ok: false,
        err: String(e?.message || e || "error"),
      });
    } finally {
      setLoading(false);
    }
  };

  const submitVote = useCallback(
    async (vote) => {
      if (!normalizedReport || submittingVote) return;

      if (!APP_KEY) {
        showAppAlert(
          tx("shield.vote.appKeyMissingTitle", pickLang(currentLang, "Голосование временно недоступно", "Voting temporarily unavailable")),
          tx(
            "shield.vote.appKeyMissingText",
            pickLang(currentLang, "В приложении не найден ключ доступа для отправки голосов.", "The access key required to send votes was not found in the app.")
          )
        );
        return;
      }

      setSubmittingVote(true);

      try {
        const proof = await loadProProof();
        const accessToken = proof?.accessToken || authAccess || null;
        const effectiveUser = user || proof?.authUser || null;
        const effectiveUid = await getBestKnownUid(effectiveUser, installUid, accessToken || "");
    const stableUserId = String(effectiveUid || uid || installUid || "anonymous").trim() || "anonymous";

        const payload = {
          input:
            normalizedReport?.details?.page?.final_url ||
            normalizedReport?.normalized_input ||
            normalizedReport?.input ||
            input.trim(),
          kind: normalizedReport?.kind || detectKind(input),
          vote,
          userId: stableUserId,
        };

        const headers = {
          "Content-Type": "application/json",
          "Accept-Language": currentLang,
          "X-User-Id": stableUserId,
          "x-app-key": APP_KEY,
        };

        if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

        const res = await safeFetchRaw(`${BACKEND}/scan/vote`, {
          method: "POST",
          headers,
          body: JSON.stringify(payload),
        });

        const text = await res.text();

        let json = null;
        try {
          json = text ? JSON.parse(text) : null;
        } catch {
          json = null;
        }

        if (!res.ok) {
          throw new Error(String(json?.detail || json?.error || `HTTP ${res.status}`));
        }

        const comm = json?.community || null;

        if (comm) {
          setReport((prev) => {
            if (!prev) return prev;

            return {
              ...prev,
              community: {
                ...prev.community,
                ...comm,
              },
            };
          });
        }

        logEvent("shield_vote_sent", {
          screen: "shield",
          vote,
          kind: normalizedReport?.kind || "unknown",
        });

        showAppAlert(
          tx("shield.vote.successTitle", pickLang(currentLang, "Голос отправлен", "Vote sent")),
          vote === "scam"
            ? tx("shield.vote.successScam", pickLang(currentLang, "Объект отмечен как SCAM.", "Object marked as SCAM."))
            : tx("shield.vote.successSafe", pickLang(currentLang, "Объект отмечен как SAFE.", "Object marked as SAFE."))
        );
      } catch {
        showAppAlert(
          tx("shield.vote.errorTitle", pickLang(currentLang, "Не удалось отправить голос", "Could not send vote")),
          pickLang(currentLang, "Попробуй ещё раз через несколько секунд.", "Please try again in a few seconds.")
        );
      } finally {
        setSubmittingVote(false);
      }
    },
    [normalizedReport, submittingVote, currentLang, tx, authAccess, user, installUid, input]
  );

  const shareVerdict = async () => {
    if (!normalizedReport || sharingNow) return;

    setSharingNow(true);

    try {
      logEvent("scan_share", {
        screen: "shield",
        level: normalizedReport?.level || "n/a",
        kind: normalizedReport?.kind || "text",
      });

      await new Promise((resolve) => InteractionManager.runAfterInteractions(resolve));
      await new Promise((resolve) => setTimeout(resolve, 250));

      const uri = await shareShotRef.current?.capture?.();

      if (!uri || typeof uri !== "string") {
        throw new Error("capture_empty");
      }

      const canShareFile = await Sharing.isAvailableAsync().catch(() => false);

      if (canShareFile) {
        await Sharing.shareAsync(uri, {
          mimeType: "image/png",
          UTI: "public.png",
          dialogTitle: tx("shield.share.dialogTitle", pickLang(currentLang, "Поделиться", "Share")),
        });
      } else {
        await Share.share({
          title: "Noytrix ScamShield",
          message: Platform.OS === "ios" ? shareMessage : `${shareMessage}\n${uri}`,
          url: uri,
        });
      }

      logEvent("scan_share_success", {
        screen: "shield",
        kind: normalizedReport?.kind || "text",
      });
    } catch (e) {
      const errRaw = String(e?.message || e || "share_error");

      if (!errRaw.toLowerCase().includes("cancel")) {
        showAppAlert(
          tx("shield.share.errorTitle", pickLang(currentLang, "Не удалось поделиться", "Could not share")),
          pickLang(currentLang, "Не удалось отправить изображение. Попробуй ещё раз.", "Could not share the image. Please try again.")
        );
      }

      logEvent("scan_share_error", {
        screen: "shield",
        kind: normalizedReport?.kind || "text",
        err: errRaw,
      });
    } finally {
      setSharingNow(false);
    }
  };
  const openPro = async () => {
    logEvent("pro_opened", { screen: "shield" });

    if (isPro) {
      router.push("/shield-pro");
      return;
    }

    try {
      const v = await AsyncStorage.getItem("isPro");
      if (String(v || "").toLowerCase() === "true") {
        router.push("/shield-pro");
        return;
      }
    } catch {}

    router.push("/pro");
  };

  const ShareCard = () => {
    if (!normalizedReport) return null;

    const date = new Date();
    const iso = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

    return (
      <LinearGradient colors={[GRAD.start, GRAD.mid, GRAD.end]} style={{ width: 1024, padding: 40, borderRadius: 28 }}>
        <Text style={{ color: T.logo, fontWeight: "900", fontSize: 42, marginBottom: 18 }}>
          {tx("shield.share.title", "ScamShield")}
        </Text>

        <View
          style={{
            backgroundColor: "rgba(8,14,36,0.98)",
            borderRadius: 24,
            padding: 28,
            borderWidth: 1,
            borderColor: T.border,
          }}
        >
          <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 16 }}>
            <View
              style={{
                paddingVertical: 6,
                paddingHorizontal: 14,
                borderRadius: 10,
                backgroundColor: "rgba(255,255,255,0.06)",
                borderWidth: 1,
                borderColor: T.border,
                marginRight: 10,
              }}
            >
              <Text style={{ color: T.text, fontWeight: "900" }}>
                {String(normalizedReport?.kind || "text").toUpperCase()}
              </Text>
            </View>

            <Text style={{ color: T.text, fontSize: 28, fontWeight: "900", flexShrink: 1 }} numberOfLines={2}>
              {targetLabel || tx("shield.share.objectPlaceholder", pickLang(currentLang, "Объект", "Object"))}
            </Text>
          </View>

          <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" }}>
            <View style={{ width: "48%", borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16, marginBottom: 12 }}>
              <Text style={{ color: T.dim, marginBottom: 6 }}>
                {tx("shield.share.verdictTitle", pickLang(currentLang, "Вердикт", "Verdict"))}
              </Text>
              <Text style={{ color: verdictColor, fontWeight: "900", fontSize: 22 }}>{verdictLabel}</Text>
            </View>

            <View style={{ width: "48%", borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16, marginBottom: 12 }}>
              <Text style={{ color: T.dim, marginBottom: 6 }}>{tx("shield.share.scoreTitle", "Score")}</Text>
              <Text style={{ color: T.text, fontWeight: "900", fontSize: 22 }}>{normalizedReport.score}/100</Text>
            </View>

            <View style={{ width: "48%", borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16, marginBottom: 12 }}>
              <Text style={{ color: T.dim, marginBottom: 6 }}>
                {tx("shield.share.typeTitle", pickLang(currentLang, "Тип", "Type"))}
              </Text>
              <Text style={{ color: T.text, fontWeight: "900", fontSize: 22 }}>{normalizedReport.kindLabel}</Text>
            </View>

            <View style={{ width: "48%", borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16, marginBottom: 12 }}>
              <Text style={{ color: T.dim, marginBottom: 6 }}>
                {tx("shield.share.dateTitle", pickLang(currentLang, "Дата", "Date"))}
              </Text>
              <Text style={{ color: T.text, fontWeight: "900", fontSize: 22 }}>{iso}</Text>
            </View>
          </View>

          <View style={{ marginTop: 18 }}>
            {topEvidence.map((r, i) => (
              <Text key={i} style={{ color: T.dim, fontSize: 18, marginBottom: 6 }}>- {prettyTitleFromCode(r?.code, currentLang)}</Text>
            ))}
          </View>

          <Text style={{ color: T.dim, marginTop: 18, fontSize: 14 }}>
            {tx("shield.share.footer", "NOYTRIX — ScamShield")}
          </Text>
        </View>
      </LinearGradient>
    );
  };

  const showResultBlock = !!normalizedReport && !backendError;

  return (
    <LinearGradient colors={[GRAD.start, GRAD.mid, GRAD.end]} style={{ flex: 1, paddingTop: 48 }}>
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 120 }}>
        <Text style={{ color: T.logo, fontWeight: "900", fontSize: 34, marginBottom: 6, letterSpacing: 0.2 }}>
          {tx("shield.title", "ScamShield")}
        </Text>

        <Text style={{ color: T.dim, marginBottom: 12, fontSize: 15, lineHeight: 20 }}>
          {tx(
            "shield.subtitle",
            pickLang(currentLang, "Проверь ссылку, адрес, контракт, тикер или текст перед действием.", "Check a link, address, contract, ticker, or text before acting.")
          )}
        </Text>

        <View
          style={{
            alignSelf: "flex-start",
            paddingVertical: 8,
            paddingHorizontal: 14,
            borderRadius: 999,
            borderWidth: 1,
            borderColor: T.border,
            backgroundColor: "rgba(255,255,255,0.04)",
            marginBottom: 10,
          }}
        >
          <Text style={{ color: T.text, fontWeight: "900" }}>{quotaPillText}</Text>
        </View>

        <Text style={{ color: T.dim, marginBottom: 14, fontSize: 13, lineHeight: 18 }}>{freeInfoText}</Text>

        <BlurCard>
          <View
            style={{
              borderWidth: 1,
              borderColor: T.borderSoft,
              borderRadius: 18,
              backgroundColor: "rgba(255,255,255,0.05)",
            }}
          >
            <TextInput
              placeholder={tx("shield.input.placeholder", "Paste URL / domain / address / ticker / text")}
              placeholderTextColor={T.dim}
              value={input}
              onChangeText={(v) => {
                setInput(v);
                if (backendError) setBackendError("");
              }}
              style={{
                color: T.text,
                minHeight: 70,
                paddingHorizontal: 14,
                paddingVertical: 12,
                fontSize: 16,
              }}
              multiline
            />
          </View>

          <View style={{ flexDirection: "row", marginTop: 12 }}>
            <View style={{ flex: 1 }}>
              <PrimaryButton
                onPress={onCheck}
                disabled={loading || quotaBlocked}
                title={loading ? tx("shield.buttons.checking", "Checking…") : tx("shield.buttons.check", pickLang(currentLang, "Проверить", "Check"))}
                leftIcon={loading ? <ActivityIndicator color={T.accentText} /> : <Ionicons name="shield-checkmark" size={18} color={T.accentText} />}
              />
            </View>

            <View style={{ width: 12 }} />

            <SecondaryButton
              onPress={() => setShowSamples(true)}
              title={tx("shield.buttons.samples", pickLang(currentLang, "Примеры", "Samples"))}
              leftIcon={<Ionicons name="sparkles-outline" size={16} color={T.dim} />}
            />
          </View>

          <View style={{ flexDirection: "row", flexWrap: "wrap", marginTop: 10 }}>
            <SecondaryButton
              title={tx("shield.buttons.clear", pickLang(currentLang, "Очистить", "Clear"))}
              onPress={() => {
                setInput("");
                setReport(null);
                setBackendError("");
              }}
              leftIcon={<Ionicons name="close-circle-outline" size={16} color={T.dim} />}
              style={{ marginRight: 10, marginBottom: 10 }}
            />

            <SecondaryButton
              title={tx("shield.buttons.copyInput", pickLang(currentLang, "Копировать", "Copy input"))}
              onPress={() => onCopy(input)}
              leftIcon={<Ionicons name="copy-outline" size={16} color={T.dim} />}
              style={{ marginBottom: 10 }}
            />
          </View>
        </BlurCard>

        {!!backendError && (
          <BlurCard style={{ borderColor: "rgba(255,107,107,0.35)" }}>
            <Text style={{ color: T.bad, fontWeight: "900", fontSize: 17, marginBottom: 8 }}>
              {tx("shield.backendError.title", pickLang(currentLang, "Проверка недоступна", "Check unavailable"))}
            </Text>
            <Text style={{ color: T.dim, lineHeight: 19 }}>{backendError}</Text>
          </BlurCard>
        )}


        {!isPro && quotaBlocked && (
          <BlurCard style={{ borderColor: "rgba(255,176,32,0.35)" }}>
            <Text style={{ color: T.accent, fontWeight: "900", fontSize: 18, marginBottom: 8 }}>
              {tx("shield.quotaEnded.title", pickLang(currentLang, "FREE лимит закончился", "FREE limit reached"))}
            </Text>
            <Text style={{ color: T.dim, lineHeight: 20, marginBottom: 14 }}>
              {tx("shield.quotaEnded.text", pickLang(currentLang, "Вы использовали 4/4 проверки сегодня. Для безлимитных проверок перейдите на Noytrix PRO.", "You used 4/4 checks today. Upgrade to Noytrix PRO for unlimited scans."))}
            </Text>
            <PrimaryButton
              title={tx("shield.quotaEnded.button", pickLang(currentLang, "Перейти на PRO", "Upgrade to PRO"))}
              onPress={openPro}
              leftIcon={<Ionicons name="flash" size={18} color={T.accentText} />}
            />
          </BlurCard>
        )}

        {showResultBlock && (
          <>
            <BlurCard style={{ borderColor: verdictColor, borderWidth: 2 }}>
              <View
                style={{
                  borderRadius: 18,
                  padding: 14,
                  backgroundColor: verdictBg,
                  borderWidth: 1,
                  borderColor: "rgba(255,255,255,0.07)",
                }}
              >
                <View style={{ alignItems: "center", marginBottom: 12 }}>
                  <Text style={{ color: verdictColor, fontWeight: "900", fontSize: 28, textAlign: "center" }}>
                    {verdictLabel}
                  </Text>

                  {!!targetLabel && (
                    <Text style={{ color: T.dim, marginTop: 8, textAlign: "center" }} numberOfLines={2}>
                      {targetLabel}
                    </Text>
                  )}
                </View>

                <View style={{ alignItems: "center", marginBottom: 12 }}>
                  <Text style={{ color: T.text, fontSize: 34, fontWeight: "900" }}>{normalizedReport.score}/100</Text>
                  <View style={{ width: "100%", marginTop: 2 }}>
                    <ScoreBar value={normalizedReport.score} color={verdictColor} height={10} />
                  </View>
                </View>

                {!!normalizedReport.aiHumanVerdict && (
                  <View style={{ marginTop: 12, borderRadius: 16, borderWidth: 1, borderColor: "rgba(255,255,255,0.10)", backgroundColor: "rgba(0,0,0,0.18)", padding: 12 }}>
                    <Text style={{ color: T.text, fontSize: 15, lineHeight: 21, textAlign: "center", fontWeight: "800" }}>
                      {normalizedReport.aiHumanVerdict}
                    </Text>
                  </View>
                )}
              </View>

              <View style={{ flexDirection: "row", flexWrap: "wrap", marginTop: 12 }}>
                <SecondaryButton
                  title={tx("shield.buttons.share", pickLang(currentLang, "Поделиться", "Share"))}
                  onPress={shareVerdict}
                  leftIcon={<Ionicons name="share-social-outline" size={16} color={T.dim} />}
                  style={{ marginRight: 10, marginBottom: 10 }}
                />

                <SecondaryButton
                  title={tx("shield.buttons.copyReport", pickLang(currentLang, "Копировать отчёт", "Copy report"))}
                  onPress={() => onCopy(shareMessage)}
                  leftIcon={<Ionicons name="copy-outline" size={16} color={T.dim} />}
                  style={{ marginRight: 10, marginBottom: 10 }}
                />

                <SecondaryButton
                  title={tx("shield.buttons.open", pickLang(currentLang, "Открыть", "Open"))}
                  onPress={() => onOpen(targetLabel)}
                  leftIcon={<Ionicons name="open-outline" size={16} color={T.dim} />}
                  style={{ marginBottom: 10 }}
                />
              </View>
            </BlurCard>

            <UxRiskBlock report={normalizedReport} currentLang={currentLang} tx={tx} />

            <BlurCard>
              <Text style={{ color: T.text, fontWeight: "900", fontSize: 16, marginBottom: 10 }}>
                {tx("shield.summary.title", pickLang(currentLang, "Главные сигналы", "Top signals"))}
              </Text>

              {topEvidence.length ? (
                topEvidence.map((ev, i) => <TopSignalRow key={`top-ev-${i}`} item={ev} currentLang={currentLang} />)
              ) : (
                <Text style={{ color: T.dim }}>
                  {tx("shield.summary.empty", pickLang(currentLang, "Критических сигналов не найдено.", "No critical signals were found."))}
                </Text>
              )}
            </BlurCard>

            <BackendIntelCard report={normalizedReport} currentLang={currentLang} tx={tx} />

            <BlurCard>
              <Text style={{ color: T.text, fontWeight: "900", fontSize: 16, marginBottom: 10 }}>
                {tx("shield.sources.title", pickLang(currentLang, "Источники проверки", "Verification sources"))}
              </Text>

              {((compactSources || []).length > 0 && normalizedReport?.kind !== "transaction") ? (
                compactSources.map((src, idx) => (
                  <CompactSourceRow key={`${src?.name || "src"}-${idx}`} item={src} currentLang={currentLang} />
                ))
              ) : (
                <Text style={{ color: T.dim }}>
                  {(normalizedReport?.permissions_summary?.can_spend === true)
                    ? (currentLang === "ru"
                        ? "\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a: \u0430\u043d\u0430\u043b\u0438\u0437 \u0442\u0440\u0430\u043d\u0437\u0430\u043a\u0446\u0438\u0438 (EVM decoder)"
                        : "Source: transaction analysis (EVM decoder)")
                    : tx("shield.sources.empty", pickLang(currentLang, "\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u0438 \u0434\u043b\u044f \u044d\u0442\u043e\u0439 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438 \u043f\u043e\u043a\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b.", "No sources are available for this check yet."))}
                </Text>
              )}
            </BlurCard>

            <BlurCard>
              <Text style={{ color: T.text, fontWeight: "900", fontSize: 16, marginBottom: 10 }}>
                {tx("shield.community.title", pickLang(currentLang, "Вердикт сообщества", "Community verdict"))}
              </Text>

              <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" }}>
                <MetricChip
                  label={tx("shield.community.verdict", pickLang(currentLang, "Вердикт", "Verdict"))}
                  value={formatCommunityVerdict(normalizedReport?.community?.community_verdict, currentLang)}
                />
                <MetricChip
                  label={tx("shield.community.users", pickLang(currentLang, "Пользователи", "Users"))}
                  value={normalizedReport?.community?.total_users || 0}
                />
                <MetricChip
                  label={tx("shield.community.safeVotes", pickLang(currentLang, "SAFE голоса", "SAFE votes"))}
                  value={normalizedReport?.community?.safe_votes || 0}
                />
                <MetricChip
                  label={tx("shield.community.scamVotes", pickLang(currentLang, "SCAM голоса", "SCAM votes"))}
                  value={normalizedReport?.community?.scam_votes || 0}
                />
              </View>

              <View style={{ flexDirection: "row", marginTop: 8 }}>
                <View style={{ flex: 1 }}>
                  <PrimaryButton
                    title={
                      submittingVote
                        ? tx("shield.vote.sending", pickLang(currentLang, "Отправка…", "Sending…"))
                        : tx("shield.vote.markScam", "Mark SCAM")
                    }
                    onPress={() => submitVote("scam")}
                    disabled={submittingVote}
                    bg="rgba(255,107,107,0.18)"
                    textColor={T.bad}
                    leftIcon={
                      submittingVote ? (
                        <ActivityIndicator color={T.bad} />
                      ) : (
                        <Ionicons name="warning-outline" size={18} color={T.bad} />
                      )
                    }
                  />
                </View>

                <View style={{ width: 12 }} />

                <View style={{ flex: 1 }}>
                  <PrimaryButton
                    title={
                      submittingVote
                        ? tx("shield.vote.sending", pickLang(currentLang, "Отправка…", "Sending…"))
                        : tx("shield.vote.markSafe", "Mark SAFE")
                    }
                    onPress={() => submitVote("safe")}
                    disabled={submittingVote}
                    bg="rgba(41,211,122,0.18)"
                    textColor={T.good}
                    leftIcon={<Ionicons name="checkmark-circle-outline" size={18} color={T.good} />}
                  />
                </View>
              </View>
            </BlurCard>
          </>
        )}
        <BlurCard style={{ borderColor: "rgba(255,176,32,0.28)" }}>
          <Text style={{ color: T.text, fontWeight: "900", fontSize: 18, marginBottom: 8 }}>
            {tx("shield.proBlock.title", pickLang(currentLang, "Почему PRO важен", "Why PRO matters"))}
          </Text>

          <Text style={{ color: T.dim, lineHeight: 20, marginBottom: 12 }}>
            {tx(
              "shield.proBlock.subtitle",
              pickLang(
                currentLang,
                "FREE даёт быстрый полезный вердикт. PRO открывает больше глубины, больше деталей и работает без лимитов.",
                "FREE gives a fast useful verdict. PRO unlocks more depth, more details, and works without limits."
              )
            )}
          </Text>

          {proTeaserItems.map((item, i) => (
            <Text key={`pro-teaser-${i}`} style={{ color: T.text, marginBottom: 8, lineHeight: 18 }}>
              - {item}
            </Text>
          ))}

          <View style={{ marginTop: 8 }}>
            <PrimaryButton
              onPress={openPro}
              title={
                isPro
                  ? tx("shield.proBlock.buttonPro", pickLang(currentLang, "Перейти в PRO", "Go to PRO"))
                  : tx("shield.proBlock.buttonBuy", pickLang(currentLang, "Открыть PRO", "Open PRO"))
              }
              leftIcon={<Ionicons name={isPro ? "arrow-forward" : "flash"} size={18} color={T.accentText} />}
            />
          </View>
        </BlurCard>

        <BlurCard>
          <Text style={{ color: T.text, fontWeight: "900", marginBottom: 8, fontSize: 18 }}>
            {tx("shield.compare.title", "FREE vs PRO")}
          </Text>

          <Text style={{ color: T.dim, marginBottom: 10, lineHeight: 18 }}>
            {tx(
              "shield.compare.subtitle",
              pickLang(currentLang, "Сравнение FREE и PRO возможностей.", "Compare what’s in FREE vs what unlocks in PRO.")
            )}
          </Text>

          <View
            style={{
              borderWidth: 1,
              borderColor: T.border,
              borderRadius: 18,
              padding: 12,
              backgroundColor: "rgba(255,255,255,0.02)",
            }}
          >
            <View
              style={{
                flexDirection: "row",
                paddingVertical: 6,
                borderBottomWidth: 1,
                borderBottomColor: "rgba(255,255,255,0.06)",
                marginBottom: 4,
              }}
            >
              <Text style={{ flex: 2, color: T.dim, fontWeight: "900", fontSize: 12 }}>
                {tx("shield.compare.header.feature", pickLang(currentLang, "Функция", "Feature"))}
              </Text>
              <Text style={{ flex: 1, color: T.dim, fontWeight: "900", fontSize: 12, textAlign: "center" }}>
                {tx("shield.compare.header.free", "FREE")}
              </Text>
              <Text style={{ flex: 1, color: T.dim, fontWeight: "900", fontSize: 12, textAlign: "center" }}>
                {tx("shield.compare.header.pro", "PRO")}
              </Text>
            </View>

            {[
              {
                k: "fastVerdict",
                name: tx("shield.compare.rows.fastVerdict", pickLang(currentLang, "Быстрый вердикт", "Fast verdict")),
                free: true,
                pro: true,
              },
              {
                k: "mainSignals",
                name: tx("shield.compare.rows.mainSignals", pickLang(currentLang, "Главные риск-сигналы", "Top risk signals")),
                free: true,
                pro: true,
              },
              {
                k: "communityVote",
                name: tx("shield.compare.rows.communityVote", pickLang(currentLang, "SAFE / SCAM голосование", "SAFE / SCAM voting")),
                free: true,
                pro: true,
              },
              {
                k: "deepDetails",
                name: tx("shield.compare.rows.deepDetails", pickLang(currentLang, "Глубокие детали данных", "Deep data details")),
                free: false,
                pro: true,
              },
              {
                k: "dataHeavyUI",
                name: tx("shield.compare.rows.dataHeavyUI", pickLang(currentLang, "Расширенный data-heavy интерфейс", "Extended data-heavy interface")),
                free: false,
                pro: true,
              },
              {
                k: "unlimited",
                name: tx("shield.compare.rows.unlimited", pickLang(currentLang, "Безлимитные проверки", "Unlimited scans")),
                free: false,
                pro: true,
              },
            ].map((row) => (
              <View
                key={row.k}
                style={{
                  flexDirection: "row",
                  paddingVertical: 10,
                  borderTopWidth: 1,
                  borderTopColor: "rgba(255,255,255,0.04)",
                }}
              >
                <Text style={{ flex: 2, color: T.text, fontSize: 13, lineHeight: 18 }}>{row.name}</Text>
                <Text style={{ flex: 1, textAlign: "center", fontSize: 14, fontWeight: "900", color: row.free ? T.good : T.bad }}>
                  {row.free ? "✅" : "❌"}
                </Text>
                <Text style={{ flex: 1, textAlign: "center", fontSize: 14, fontWeight: "900", color: row.pro ? T.good : T.bad }}>
                  {row.pro ? "✅" : "❌"}
                </Text>
              </View>
            ))}
          </View>
        </BlurCard>

        <BlurCard>
          <Text style={{ color: T.text, fontWeight: "900", marginBottom: 8, fontSize: 18 }}>
            {tx("shield.howItWorks.title", pickLang(currentLang, "Как это работает", "How it works"))}
          </Text>

          <Text style={{ color: T.dim, lineHeight: 20 }}>
            {tx(
              "shield.howItWorks.text",
              pickLang(
                currentLang,
                "1) Вставь URL / домен / адрес / контракт / тикер / текст.\n2) FREE показывает главный вердикт, ключевые сигналы и основные статусы источников.\n3) Backend возвращает локализованный вердикт, статус и evidence под выбранный язык.\n4) Вердикт сообщества и SAFE / SCAM голосование работают на этой странице.",
                "1) Paste a URL / domain / address / contract / ticker / text.\n2) FREE shows the main verdict, key signals, and main source statuses.\n3) The backend returns localized verdict/status/evidence for the selected language.\n4) Community verdict and SAFE / SCAM voting also work on this page."
              )
            )}
          </Text>
        </BlurCard>
      </ScrollView>

      {!isPro && (
        <Modal visible={showQuotaModal} transparent animationType="fade" onRequestClose={() => setShowQuotaModal(false)}>
          <Pressable
            onPress={() => setShowQuotaModal(false)}
            style={{ flex: 1, justifyContent: "center", padding: 24, backgroundColor: "rgba(0,0,0,0.35)" }}
          >
            <LinearGradient
              colors={[GRAD.start, GRAD.mid, GRAD.end]}
              style={{ borderRadius: 22, padding: 16, borderWidth: 1, borderColor: "rgba(255,176,32,0.35)" }}
            >
              <Text style={{ color: T.text, fontWeight: "900", marginBottom: 10, fontSize: 18 }}>
                {tx("shield.quota.title", pickLang(currentLang, "FREE лимит достигнут", "FREE limit reached"))}
              </Text>

              <Text style={{ color: T.dim, lineHeight: 18, marginBottom: 14 }}>
                {quotaMsg ||
                  tx(
                    "shield.quota.exceeded",
                    pickLang(currentLang, "FREE лимит проверок достигнут. PRO убирает лимиты.", "FREE daily limit reached. PRO removes limits.")
                  )}
              </Text>

              <View style={{ flexDirection: "row", gap: 12 }}>
                <View style={{ flex: 1 }}>
                  <PrimaryButton
                    title={tx("shield.quota.openPro", pickLang(currentLang, "Открыть PRO", "Open PRO"))}
                    onPress={() => {
                      setShowQuotaModal(false);
                      logEvent("pro_opened", { screen: "shield", source: "quota_modal" });
                      router.push("/pro");
                    }}
                  />
                </View>

                <View style={{ flex: 1 }}>
                  <SecondaryButton
                    title={tx("shield.quota.ok", "OK")}
                    onPress={() => setShowQuotaModal(false)}
                  />
                </View>
              </View>
            </LinearGradient>
          </Pressable>
        </Modal>
      )}

      <Modal visible={showSamples} transparent animationType="fade" onRequestClose={() => setShowSamples(false)}>
        <Pressable
          onPress={() => setShowSamples(false)}
          style={{ flex: 1, justifyContent: "center", padding: 24, backgroundColor: "rgba(0,0,0,0.35)" }}
        >
          <LinearGradient
            colors={[GRAD.start, GRAD.mid, GRAD.end]}
            style={{ borderRadius: 22, padding: 16, borderWidth: 1, borderColor: T.border }}
          >
            <Text style={{ color: T.text, fontWeight: "900", marginBottom: 12, fontSize: 16 }}>
              {tx("shield.samples.title", pickLang(currentLang, "Примеры", "Samples"))}
            </Text>

            {(Array.isArray(samplesI18n) && samplesI18n.length ? samplesI18n : SAMPLES).map((s, i) => (
              <TouchableOpacity
                key={i}
                onPress={() => {
                  logEvent("sample_selected", { screen: "shield", index: i });
                  setInput(s.h);
                  setShowSamples(false);
                }}
                style={{
                  borderWidth: 1,
                  borderColor: T.border,
                  borderRadius: 16,
                  padding: 12,
                  marginBottom: 10,
                  backgroundColor: "rgba(255,255,255,0.03)",
                }}
              >
                <Text style={{ color: T.text, fontWeight: "800" }} numberOfLines={2}>
                  {s.h}
                </Text>

                <Text style={{ color: T.dim, marginTop: 6 }} numberOfLines={2}>
                  {typeof s.d === "string" && s.d
                    ? s.d
                    : currentLang === "ru"
                    ? s.dRu || ""
                    : s.dEn || ""}
                </Text>
              </TouchableOpacity>
            ))}
          </LinearGradient>
        </Pressable>
      </Modal>

      <View style={{ position: "absolute", left: -9999, top: -9999 }}>
        <ViewShot ref={shareShotRef} options={{ format: "png", quality: 1 }}>
          <ShareCard />
        </ViewShot>
      </View>
    </LinearGradient>
  );
}













