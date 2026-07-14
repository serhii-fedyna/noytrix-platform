

import React, { useEffect, useMemo, useCallback, useState, useRef } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  Modal,
  Pressable,
  Share,
  Platform,
  InteractionManager,
  ActivityIndicator,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { BlurView } from "expo-blur";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Clipboard from "expo-clipboard";
import * as Linking from "expo-linking";
import * as Sharing from "expo-sharing";
import ViewShot from "react-native-view-shot";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import Constants from "expo-constants";

import { useAuthStore } from "./lib/store.auth";
import { useI18n } from "./i18n/useI18n";
import { logEvent } from "./lib/analytics";
import { showAppAlert } from "./lib/appAlert";


const BACKEND = "https://noytrix.com";
const AUTH_KEY = "auth_state_v1";
const APP_KEY =
  Constants?.expoConfig?.extra?.NOYTRIX_APP_KEY ||
  Constants?.expoConfig?.extra?.noytrixAppKey ||
  Constants?.manifest?.extra?.NOYTRIX_APP_KEY ||
  Constants?.manifest?.extra?.noytrixAppKey ||
  Constants?.manifest2?.extra?.expoClient?.extra?.NOYTRIX_APP_KEY ||
  Constants?.manifest2?.extra?.expoClient?.extra?.noytrixAppKey ||
  Constants?.expoConfig?.extra?.EXPO_PUBLIC_NOYTRIX_APP_KEY ||
  Constants?.manifest?.extra?.EXPO_PUBLIC_NOYTRIX_APP_KEY ||
  Constants?.expoConfig?.extra?.APP_KEY ||
  Constants?.manifest?.extra?.APP_KEY ||
  "";

const INSTALL_UID_KEY = "noytrix.installUserId";


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
  leftIcon,
  style,
  textColor = T.accentText,
  bg = T.accent,
}) => (
  <TouchableOpacity
    activeOpacity={0.9}
    onPress={onPress}
    disabled={disabled}
    style={[
      {
        height: 52,
        borderRadius: 18,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: bg,
        opacity: disabled ? 0.7 : 1,
        flexDirection: "row",
        paddingHorizontal: 18,
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

const SecondaryButton = ({ title, onPress, disabled, leftIcon, style }) => (
  <TouchableOpacity
    activeOpacity={0.9}
    onPress={onPress}
    disabled={disabled}
    style={[
      {
        height: 52,
        borderRadius: 18,
        alignItems: "center",
        justifyContent: "center",
        borderWidth: 1,
        borderColor: T.border,
        backgroundColor: "rgba(255,255,255,0.04)",
        paddingHorizontal: 18,
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


const SAMPLES = [
  { h: "https://binance-airdrop-bonus.net", dRu: "\u0424\u0438\u0448\u0438\u043d\u0433 \u043f\u043e\u0434 Binance", dEn: "Phishing pretending to be Binance" },
  { h: "https://metamask-support-login.com", dRu: "\u0424\u0435\u0439\u043a\u043e\u0432\u0430\u044f \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430 MetaMask", dEn: "Fake MetaMask support" },
  { h: "http://paypal.com.verify-account-security.com", dRu: "\u041f\u043e\u0434\u0434\u043e\u043c\u0435\u043d-\u043b\u043e\u0432\u0443\u0448\u043a\u0430 PayPal", dEn: "PayPal subdomain trap" },
  { h: "0x1111111254EEB25477B68fB85Ed929F73A960582", dRu: "ETH-\u0430\u0434\u0440\u0435\u0441 (\u043f\u0440\u0438\u043c\u0435\u0440)", dEn: "EVM address / contract" },
  { h: "BTC", dRu: "\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u0442\u0438\u043a\u0435\u0440\u0430", dEn: "Ticker check" },
  { h: "PEPE", dRu: "\u0422\u043e\u043a\u0435\u043d + honeypot", dEn: "Token + honeypot" },
];


const reIsHttp = /^https?:\/\//i;
const reIsEth = /^0x[a-f0-9]{40}$/i;
const reTicker = /^[A-Z0-9._-]{2,15}$/i;

function pickLang(lang, ru, en) {
  return String(lang || "en").toLowerCase().startsWith("ru") ? ru : en;
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

const uidFromUser = (u) =>
  (
    u?.email ||
    u?.user?.email ||
    u?.profile?.email ||
    u?.nick ||
    u?.user?.nick ||
    u?.profile?.nick ||
    u?.name ||
    u?.user?.name ||
    u?.profile?.name ||
    u?.id ||
    u?.userId ||
    u?._id ||
    ""
  )
    .toString()
    .trim()
    .toLowerCase();

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
  const direct = uidFromUser(user);
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

    const stateDirect = uidFromUser(authUser);
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

function hasObjectData(v) {
  return !!v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length > 0;
}

function detectKind(raw) {
  const x = String(raw || "").trim();
  if (!x) return "text";
  if (reIsHttp.test(x)) return "url";
  if (reIsEth.test(x)) return "wallet";
  if (reTicker.test(x) && !x.includes(" ")) return "ticker";
  if (x.includes(".") && !x.includes(" ")) return "domain";
  return "text";
}

function normalizeKind(kind, raw) {
  const k = String(kind || "").toLowerCase();
  if (["url", "domain", "wallet", "contract", "transaction", "ticker", "text"].includes(k)) return k;
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

function formatKindLabel(kind, localized, lang) {
  if (localized) return localized;
  const k = String(kind || "").toLowerCase();
  if (k === "url") return "URL";
  if (k === "domain") return pickLang(lang, "", "Domain");
  if (k === "wallet") return pickLang(lang, "", "Wallet");
  if (k === "contract") return pickLang(lang, "\u041a\u043e\u043d\u0442\u0440\u0430\u043a\u0442", "Contract");
  if (k === "transaction") return pickLang(lang, "\u0422\u0440\u0430\u043d\u0437\u0430\u043a\u0446\u0438\u044f", "Transaction");
  if (k === "ticker") return pickLang(lang, "", "Ticker");
  return pickLang(lang, "", "Text");
}

function formatLevelLabel(level, lang) {
  const s = String(level || "").toLowerCase();
  if (s === "critical") return pickLang(lang, "", "Critical");
  if (s === "danger") return pickLang(lang, "", "Danger");
  if (s === "suspicious") return pickLang(lang, "", "Suspicious");
  return pickLang(lang, "", "Safe");
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

function formatSourceVerdict(verdict, lang) {
  const s = String(verdict || "").toLowerCase();
  if (s === "clean") return pickLang(lang, "", "Clean");
  if (s === "malicious") return pickLang(lang, "", "Malicious");
  if (s === "danger") return pickLang(lang, "", "Danger");
  if (s === "safe") return pickLang(lang, "", "Safe");
  if (s === "suspicious") return pickLang(lang, "", "Suspicious");
  if (s === "observed") return pickLang(lang, "", "Observed");
  return pickLang(lang, "", "Unknown");
}

function formatPercent(v) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `${n}%`;
}

function formatMoneyCompact(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  try {
    return new Intl.NumberFormat("en", {
      notation: "compact",
      maximumFractionDigits: 2,
    }).format(n);
  } catch {
    return String(Math.round(n));
  }
}

function yesNo(v, tx, lang) {
  return v ? tx("common.yes", pickLang(lang, "", "Yes")) : tx("common.no", pickLang(lang, "", "No"));
}

function formatCommunityVerdict(v, lang) {
  const s = String(v || "").toLowerCase();
  if (s === "safe") return "SAFE";
  if (s === "scam") return "SCAM";
  if (s === "mixed") return pickLang(lang, "", "Mixed");
  return pickLang(lang, "", "Unknown");
}

function formatCrowdKind(kind, lang) {
  return formatKindLabel(kind, null, lang);
}

function prettyTitleFromCode(code, lang) {
  const map = {
    ticker_found: pickLang(lang, "\u0422\u0438\u043a\u0435\u0440 \u043d\u0430\u0439\u0434\u0435\u043d", "Ticker found"),
    honeypot_checked: pickLang(lang, "\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 honeypot \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430", "Honeypot check completed"),
    honeypot_detected: pickLang(lang, "\u0412\u044b\u0441\u043e\u043a\u0438\u0439 sell-\u0440\u0438\u0441\u043a", "High sell-risk detected"),
    honeypot_medium_risk: pickLang(lang, "\u0421\u0440\u0435\u0434\u043d\u0438\u0439 \u0440\u0438\u0441\u043a \u0442\u043e\u043a\u0435\u043d\u0430", "Moderate token risk found"),
    vt_detection: pickLang(lang, "VirusTotal: \u0435\u0441\u0442\u044c \u0443\u0433\u0440\u043e\u0437\u044b", "VirusTotal threat flags"),
    vt_clean: pickLang(lang, "VirusTotal: \u0447\u0438\u0441\u0442\u043e", "VirusTotal clean"),
    gsb_match: pickLang(lang, "Google: \u0443\u0433\u0440\u043e\u0437\u0430", "Google confirmed a threat"),
    gsb_clean: pickLang(lang, "Google: \u0447\u0438\u0441\u0442\u043e", "Google found no threats"),
    submitted_for_analysis: pickLang(lang, "\u041e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e \u043d\u0430 \u0434\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0439 \u0430\u043d\u0430\u043b\u0438\u0437", "Submitted for additional analysis"),
    urlscan_submitted: pickLang(lang, "urlscan: \u0430\u043d\u0430\u043b\u0438\u0437 \u0437\u0430\u043f\u0443\u0449\u0435\u043d", "urlscan analysis started"),
    urlscan_dns_error: pickLang(lang, "urlscan: DNS-\u043e\u0448\u0438\u0431\u043a\u0430", "urlscan DNS error"),
    verified_contract: pickLang(lang, "\u041a\u043e\u043d\u0442\u0440\u0430\u043a\u0442 \u0432\u0435\u0440\u0438\u0444\u0438\u0446\u0438\u0440\u043e\u0432\u0430\u043d", "Contract verified"),
    unverified_or_wallet: pickLang(lang, "\u041d\u0435\u0442 \u0432\u0435\u0440\u0438\u0444\u0438\u043a\u0430\u0446\u0438\u0438", "No contract verification found"),
    token_listed: pickLang(lang, "\u0422\u043e\u043a\u0435\u043d \u043d\u0430\u0439\u0434\u0435\u043d \u043d\u0430 \u0440\u044b\u043d\u043a\u0435", "Token found on the market"),
    page_loaded: pickLang(lang, "\u0421\u0442\u0440\u0430\u043d\u0438\u0446\u0430 \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u0430", "Page loaded"),
    seed_phrase_request: pickLang(lang, "\u0417\u0430\u043f\u0440\u043e\u0441 seed-\u0444\u0440\u0430\u0437\u044b", "Seed phrase request"),
    secret_phrase_request: pickLang(lang, "\u0417\u0430\u043f\u0440\u043e\u0441 secret phrase", "Secret phrase request"),
    recovery_phrase_request: pickLang(lang, "\u0417\u0430\u043f\u0440\u043e\u0441 recovery phrase", "Recovery phrase request"),
    private_key_request: pickLang(lang, "\u0417\u0430\u043f\u0440\u043e\u0441 private key", "Private key request"),
    private_key_hex_found: pickLang(lang, "\u041d\u0430\u0439\u0434\u0435\u043d private key", "Private key detected"),
    wallet_connect_prompt: pickLang(lang, "\u0417\u0430\u043f\u0440\u043e\u0441 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f \u043a\u043e\u0448\u0435\u043b\u044c\u043a\u0430", "Wallet connection prompt"),
    claim_prompt: pickLang(lang, "\u0410\u0433\u0440\u0435\u0441\u0441\u0438\u0432\u043d\u044b\u0439 claim-\u043f\u0440\u0438\u0437\u044b\u0432", "Aggressive claim prompt"),
    airdrop_language: pickLang(lang, "\u041f\u043e\u0434\u043e\u0437\u0440\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0439 airdrop-\u0442\u0435\u043a\u0441\u0442", "Suspicious airdrop wording"),
    verify_wallet_prompt: pickLang(lang, "\u0417\u0430\u043f\u0440\u043e\u0441 verify wallet", "Wallet verification request"),
    connect_wallet_prompt: pickLang(lang, "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435 \u043a\u043e\u0448\u0435\u043b\u044c\u043a\u0430", "Connect wallet prompt"),
    fake_support_language: pickLang(lang, "\u0424\u0435\u0439\u043a\u043e\u0432\u0430\u044f \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430", "Looks like fake support"),
    wallet_import_prompt: pickLang(lang, "\u0418\u043c\u043f\u043e\u0440\u0442 \u043a\u043e\u0448\u0435\u043b\u044c\u043a\u0430", "Wallet import prompt"),
    token_approval: pickLang(lang, "\u0420\u0438\u0441\u043a\u043e\u0432\u0430\u043d\u043d\u044b\u0439 approval", "Risky token approval"),
    wallet_drainer_hint: pickLang(lang, "\u041f\u0440\u0438\u0437\u043d\u0430\u043a\u0438 drainer", "Drainer warning signs"),
    brand_spoofing: pickLang(lang, "\u0420\u0438\u0441\u043a \u043f\u043e\u0434\u0434\u0435\u043b\u043a\u0438 \u0431\u0440\u0435\u043d\u0434\u0430", "Brand spoofing risk"),
    brand_impersonation: pickLang(lang, "\u0418\u043c\u0438\u0442\u0430\u0446\u0438\u044f \u0438\u0437\u0432\u0435\u0441\u0442\u043d\u043e\u0433\u043e \u0431\u0440\u0435\u043d\u0434\u0430", "Trusted brand impersonation"),
    brand_plus_scam_keywords: pickLang(lang, "\u0411\u0440\u0435\u043d\u0434 + scam-\u043c\u0430\u0440\u043a\u0435\u0440\u044b", "Brand + scam markers"),
    hyphenated_suspicious_host: pickLang(lang, "\u041f\u043e\u0434\u043e\u0437\u0440\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 \u0434\u043e\u043c\u0435\u043d\u0430", "Suspicious domain format"),
    redirect_to_different_host: pickLang(lang, "\u0420\u0435\u0434\u0438\u0440\u0435\u043a\u0442 \u043d\u0430 \u0434\u0440\u0443\u0433\u043e\u0439 \u0434\u043e\u043c\u0435\u043d", "Redirect to a different domain"),
    credential_or_wallet_prompt: pickLang(lang, "\u0417\u0430\u043f\u0440\u043e\u0441 \u0447\u0443\u0432\u0441\u0442\u0432\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0445 \u0434\u0430\u043d\u043d\u044b\u0445", "Sensitive data request"),
    multiple_iframes: pickLang(lang, "\u041d\u0435\u043e\u0431\u044b\u0447\u043d\u0430\u044f \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0430 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u044b", "Unusual page structure"),
    domain_resolution_failed: pickLang(lang, "\u0414\u043e\u043c\u0435\u043d \u043d\u0435 \u043e\u0442\u0432\u0435\u0447\u0430\u0435\u0442", "Domain did not resolve correctly"),
    unverified_address: pickLang(lang, "\u0410\u0434\u0440\u0435\u0441 \u043d\u0435 \u0432\u0435\u0440\u0438\u0444\u0438\u0446\u0438\u0440\u043e\u0432\u0430\u043d", "Address not verified"),
    ticker_ambiguous: pickLang(lang, "\u0422\u0438\u043a\u0435\u0440 \u043d\u0435\u043e\u0434\u043d\u043e\u0437\u043d\u0430\u0447\u0435\u043d", "Ticker match is ambiguous"),
    ticker_multiple_matches: pickLang(lang, "\u041d\u0430\u0439\u0434\u0435\u043d\u043e \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e ticker-\u0441\u043e\u0432\u043f\u0430\u0434\u0435\u043d\u0438\u0439", "Multiple ticker matches found"),
  };

  if (map[code]) return map[code];

  const pretty = String(code || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());

  return pretty || pickLang(lang, "", "Signal");
}

function prettyEvidenceText(item, lang) {
  const code = String(item?.code || "").trim();

  const textMap = {
    ticker_found: pickLang(
      lang,
      "",
      "A market match was found for this ticker. Basic identification completed successfully."
    ),
    honeypot_checked: pickLang(
      lang,
      "",
      "The sell-model check did not show critical restrictions or traps."
    ),
    honeypot_detected: pickLang(
      lang,
      "",
      "There are signs that exiting the position may be restricted or risky."
    ),
    honeypot_medium_risk: pickLang(
      lang,
      "",
      "Moderate risk indicators were found. Extra caution is advised."
    ),
    vt_detection: pickLang(
      lang,
      "",
      "One of the external engines flagged this object as dangerous."
    ),
    vt_clean: pickLang(
      lang,
      "",
      "At the time of the check, the external engine found no dangerous flags."
    ),
    gsb_match: pickLang(
      lang,
      "Google Safe Browsing ",
      "Google Safe Browsing confirmed a threat."
    ),
    gsb_clean: pickLang(
      lang,
      "Google Safe Browsing ",
      "Google Safe Browsing found no threats."
    ),
    submitted_for_analysis: pickLang(
      lang,
      "",
      "The check was submitted to an external service. The final result may appear later."
    ),
    urlscan_submitted: pickLang(
      lang,
      "",
      "The page was submitted for an external behavioral scan."
    ),
    urlscan_dns_error: pickLang(
      lang,
      "",
      "The external service could not resolve the domain correctly."
    ),
    verified_contract: pickLang(
      lang,
      "",
      "The contract shows signs of verified and published source code."
    ),
    unverified_or_wallet: pickLang(
      lang,
      "",
      "The check did not confirm public contract verification."
    ),
    token_listed: pickLang(
      lang,
      "",
      "The token was found in market sources, which helps refine identification."
    ),
    page_loaded: pickLang(
      lang,
      "",
      "The page loaded successfully and was analyzed by content."
    ),
    seed_phrase_request: pickLang(
      lang,
      "",
      "The page asks for a seed phrase. This is a strong risk signal."
    ),
    secret_phrase_request: pickLang(
      lang,
      "",
      "A secret phrase request was detected. This looks dangerous."
    ),
    recovery_phrase_request: pickLang(
      lang,
      "",
      "A recovery phrase request was found. This is unusual for a normal service."
    ),
    private_key_request: pickLang(
      lang,
      "",
      "A private key request was found. This is a critical risk signal."
    ),
    private_key_hex_found: pickLang(
      lang,
      "",
      "A pattern similar to a private key was found in the text."
    ),
    wallet_connect_prompt: pickLang(
      lang,
      "",
      "There is a strong wallet connection prompt. Caution is advised."
    ),
    claim_prompt: pickLang(
      lang,
      "",
      "An aggressive “claim now” reward prompt was detected."
    ),
    airdrop_language: pickLang(
      lang,
      "",
      "There is wording commonly seen in suspicious airdrop scenarios."
    ),
    verify_wallet_prompt: pickLang(
      lang,
      "",
      "A “verify wallet” request was found, which is often used by phishing pages."
    ),
    connect_wallet_prompt: pickLang(
      lang,
      "",
      "The page pushes the user to connect a wallet."
    ),
    fake_support_language: pickLang(
      lang,
      "",
      "The wording resembles fake support behavior."
    ),
    wallet_import_prompt: pickLang(
      lang,
      "",
      "There is a prompt to import a wallet. This is a risky scenario."
    ),
    token_approval: pickLang(
      lang,
      "",
      "There is a risk of unsafe token approval."
    ),
    wallet_drainer_hint: pickLang(
      lang,
      "",
      "There are indirect warning signs of a possible drainer."
    ),
    brand_spoofing: pickLang(
      lang,
      "",
      "The domain uses a recognizable brand but does not match the official address."
    ),
    brand_impersonation: pickLang(
      lang,
      "",
      "There are signs of trusted-brand impersonation."
    ),
    brand_plus_scam_keywords: pickLang(
      lang,
      "",
      "The address mixes brand-related words with typical scam markers."
    ),
    hyphenated_suspicious_host: pickLang(
      lang,
      "",
      "The domain format looks unusual and may be used for disguise."
    ),
    redirect_to_different_host: pickLang(
      lang,
      "",
      "After opening, there is a redirect to a different domain."
    ),
    credential_or_wallet_prompt: pickLang(
      lang,
      "",
      "The page requests sensitive data in a wallet or access context."
    ),
    multiple_iframes: pickLang(
      lang,
      "",
      "The page structure looks unusually complex."
    ),
    domain_resolution_failed: pickLang(
      lang,
      "",
      "The domain could not respond correctly during the check."
    ),
    unverified_address: pickLang(
      lang,
      "",
      "The address did not receive sufficient confirmation from explorers."
    ),
    ticker_ambiguous: pickLang(
      lang,
      "",
      "A ticker match was found, but it does not look fully unambiguous."
    ),
    ticker_multiple_matches: pickLang(
      lang,
      "",
      "There are multiple possible matches for this ticker."
    ),
  };

  if (textMap[code]) return textMap[code];
  if (item?.text && typeof item.text === "string" && item.text.trim()) return item.text;
  return pickLang(lang, "", "More details are available below.");
}

function formatSourceName(name, lang) {
  const map = {
    virustotal: "VirusTotal",
    google_safe_browsing: "Google Safe Browsing",
    urlscan: "urlscan",
    page_fetch: pickLang(lang, "", "Page analysis"),
    etherscan: "Etherscan",
    bscscan: "BscScan",
    dexscreener: "DexScreener",
    coingecko: "CoinGecko",
    text_heuristics: pickLang(lang, "", "Text analysis"),
    honeypot: "Honeypot",
  };
  return map[name] || safeText(name);
}

function explainBackendMessage(raw, lang) {
  const s = String(raw || "").toLowerCase();

  if (!s) {
    return pickLang(
      lang,
      "Сервер не вернул данные для этой проверки. Попробуй еще раз через несколько секунд.",
      "The server did not return data for this check. Try again in a few seconds."
    );
  }

  if (s.includes("429") || s.includes("quota") || s.includes("limit")) {
    return pickLang(
      lang,
      "Сервер вернул лимит проверки. Для PRO этого быть не должно, попробуй открыть профиль и восстановить покупку.",
      "The server unexpectedly returned a rate-limit response. This should not happen for PRO."
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
      "Не удалось подключиться к серверу. Проверь интернет и попробуй снова.",
      "We could not reach the server. Check your connection and try again."
    );
  }

  if (s.includes("timeout") || s.includes("aborted")) {
    return pickLang(
      lang,
      "Сервер отвечал слишком долго. Попробуй еще раз немного позже.",
      "The server took too long to respond. Please try again a bit later."
    );
  }

  if (s.includes("http 500") || s.includes("scan failed")) {
    return pickLang(
      lang,
      "Сервер не смог завершить проверку прямо сейчас. Попробуй еще раз позже.",
      "The server could not complete the check right now. Please try again later."
    );
  }

  if (s.includes("invalid json")) {
    return pickLang(
      lang,
      "Сервер вернул неполный ответ. Запусти проверку еще раз.",
      "The server returned an incomplete response. Please run the check again."
    );
  }

  return pickLang(
    lang,
    "Проверку не удалось завершить прямо сейчас. Попробуй еще раз через несколько секунд.",
    "The check could not be completed right now. Please try again in a few seconds."
  );
}

function normalizeScanReport(raw, currentLang) {
  if (!raw || typeof raw !== "object") return null;

  const inputKind = normalizeKind(raw.kind, raw.input || raw.normalized_input || "");
  const score = Number(raw.score || 0) || 0;
  const level = String(raw.level || "safe").toLowerCase();
  const details = raw.details || {};
  const token = hasObjectData(details.token) ? details.token : null;
  const honeypot = token?.honeypot || null;
  const topContributors = Array.isArray(details.top_score_contributors) ? details.top_score_contributors : [];

  return {
    ...raw,
    kind: inputKind,
    score,
    level,
    kindLabel: formatKindLabel(inputKind, raw.kind_localized, currentLang),
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
    sources: Array.isArray(raw.sources) ? raw.sources : [],
    evidenceList: Array.isArray(raw.evidence) ? raw.evidence : [],
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
	    aiInvestigation: raw.ai_investigation || details.ai_investigation || null,
	    multiChain: raw.multi_chain_intelligence || details.multi_chain_intelligence || null,
	    runtimeContract: raw.runtime_contract || details.runtime_contract || null,
	    graphContext: raw.graph || details.graph || details.internal_verdict?.graph_context || null,
	    reputationContext: raw.reputation || details.reputation || details.internal_verdict?.reputation_context || raw.threat_memory || null,
	    evidenceTrace: Array.isArray(details.evidence_trace) ? details.evidence_trace : [],
    token,
    honeypot,
    quota: raw.quota || null,
    what_can_happen: raw.what_can_happen || "",
    worst_case: raw.worst_case || "",
    permissions_summary: raw.permissions_summary || null,
    risk_reasons: Array.isArray(raw.risk_reasons) ? raw.risk_reasons : [],
    honeypot_verdict: raw.honeypot_verdict || null,
    honeypot_status: raw.honeypot_status || null,
    honeypot_risk: raw.honeypot_risk || honeypot?.risk || null,
    confirmedRedFlag: !!raw.confirmed_red_flag,
  };
}

async function fetchWithTimeout(url, opts = {}, timeoutMs = 18000) {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...opts, signal: ctrl.signal });
  } finally {
    clearTimeout(id);
  }
}

async function fetchJsonTry(urls, opts = {}, timeoutMs = 18000) {
  const list = Array.isArray(urls) ? urls : [urls];
  let lastErr = null;

  for (const u of list) {
    try {
      const res = await fetchWithTimeout(u, opts, timeoutMs);
      if (res.status === 404 || res.status === 405) continue;

      const text = await res.text();
      let json = null;
      try {
        json = text ? JSON.parse(text) : null;
      } catch {
        json = null;
      }

      if (res.ok) return { ok: true, res, json };
      lastErr = new Error(`HTTP ${res.status}`);
      return { ok: false, res, json, error: lastErr };
    } catch (e) {
      lastErr = e;
      continue;
    }
  }

  return { ok: false, res: null, json: null, error: lastErr };
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

  return {
    accessToken: accessToken || null,
    purchaseToken,
    productId,
    entitlementId,
    authUser: authState?.user || null,
  };
}

function buildHeaders({
  currentLang,
  uid,
  access,
  proof,
  includeJson = false,
  includeAppKey = false,
}) {
  const headers = {
    "Accept-Language": currentLang,
    "X-User-Id": uid || "anonymous",
  };

  if (includeJson) headers["Content-Type"] = "application/json";
  if (includeAppKey && APP_KEY) headers["x-app-key"] = APP_KEY;

  const authHeader = access || proof?.accessToken || null;
  if (authHeader) headers["Authorization"] = `Bearer ${authHeader}`;

  if (proof?.productId) headers["X-Play-Product-Id"] = proof.productId;
  if (proof?.purchaseToken) headers["X-Play-Purchase-Token"] = proof.purchaseToken;
  if (proof?.entitlementId) headers["X-Entitlement-Id"] = proof.entitlementId;

  return headers;
}

function summarizeShareText(r, tx, lang) {
  if (!r) return "";
  const verdict = r.verdictLabel || r.verdict_localized || r.verdict_ru || r.verdict_en || r.verdict || r.level || "";
  const obj = r?.details?.page?.final_url || r?.normalized_input || r?.input || "";
  const evidence = (r.evidenceList || [])
    .slice(0, 6)
    .map((x) => prettyTitleFromCode(x?.code, lang))
    .filter(Boolean)
    .join(" • ");

  return `${tx("shieldPro.share.title", "ScamShield PRO")}: ${verdict} (${r.score ?? 0}/100)\n${
    obj ? `${pickLang(lang, "", "Object")}: ${obj}\n` : ""
  }${tx("shieldPro.share.evidence", pickLang(lang, "", "Signals"))}: ${evidence || "—"}`;
}

function formatSourceStatusText(status, item, lang) {
  const serverText = String(item?.status_text || "").trim();
  if (serverText) {
    const lower = serverText.toLowerCase();
    if (
      !lower.includes("status_code") &&
      !lower.includes("errno") &&
      !lower.includes("body") &&
      !lower.includes("{") &&
      !lower.includes("}")
    ) {
      if (lower === "") return pickLang(lang, "", "Unavailable");
      if (lower === "error") return pickLang(lang, "Unavailable", "Unavailable");
      return serverText;
    }
  }

  const s = String(status || "").toLowerCase();
  const details = item?.details || {};
  const raw =
    [
      details?.message,
      details?.error,
      details?.description,
      details?.detail,
      details?.reason,
      details?.status_text,
      item?.message,
      item?.error,
      item?.detail,
    ]
      .filter(Boolean)
      .join(" | ") || "";

  const rawLower = raw.toLowerCase();
  const sourceName = String(item?.name || "").toLowerCase();

  if (s === "clean") return pickLang(lang, "", "Clean");
  if (s === "malicious") return pickLang(lang, "", "Malicious");
  if (s === "no_data") return pickLang(lang, "", "No data");
  if (s === "quota") return pickLang(lang, "", "Service limit");
  if (s === "timeout") return pickLang(lang, "", "Service timeout");

  if (s === "invalid_key") {
    if (sourceName.includes("google")) return pickLang(lang, "", "Key not configured");
    return pickLang(lang, "", "Key required");
  }

  if (rawLower.includes("403") || rawLower.includes("forbidden")) {
    return pickLang(lang, "", "Access restricted");
  }

  if (rawLower.includes("401") || rawLower.includes("unauthorized")) {
    return pickLang(lang, "", "Authorization required");
  }

  if (
    rawLower.includes("could not resolve domain") ||
    rawLower.includes("name or service not known") ||
    rawLower.includes("domain could not be resolved") ||
    rawLower.includes("dns") ||
    rawLower.includes("resolve")
  ) {
    return pickLang(lang, "", "Domain not found");
  }

  if (rawLower.includes("timeout")) {
    return pickLang(lang, "", "Service timeout");
  }

  if (rawLower.includes("quota") || rawLower.includes("rate limit") || rawLower.includes("429")) {
    return pickLang(lang, "", "Service limit");
  }

  if (rawLower.includes("invalid key") || rawLower.includes("api key")) {
    return pickLang(lang, "", "Key not configured");
  }

  if (s === "error") return pickLang(lang, "", "Could not verify");

  return pickLang(lang, "", "Unavailable");
}

function extractPrettySourceDetails(item, lang) {
  const details = item?.details;
  const status = String(item?.status || "").toLowerCase();
  const raw =
    details && typeof details === "object"
      ? [
          details?.message,
          details?.description,
          details?.detail,
          details?.reason,
          details?.error,
        ]
          .filter(Boolean)
          .join(" ")
      : typeof details === "string"
      ? details
      : "";

  const s = String(raw || "").toLowerCase();
  const name = String(item?.name || "").toLowerCase();

  if (!s) return null;

  if (s.includes("malicious") && s.includes("analysis_stats")) {
    return null;
  }

  if (
    s.includes("could not resolve domain") ||
    s.includes("domain could not be resolved") ||
    s.includes("name or service not known") ||
    s.includes("dns") ||
    s.includes("resolve")
  ) {
    return pickLang(
      lang,
      "",
      "The external service could not resolve the domain correctly."
    );
  }

  if (s.includes("403") || s.includes("forbidden")) {
    if (name.includes("google")) {
      return pickLang(
        lang,
        "",
        "A working access key is not configured for this source."
      );
    }
    return pickLang(
      lang,
      "",
      "This source is currently restricting access to the check."
    );
  }

  if (s.includes("401") || s.includes("unauthorized")) {
    return pickLang(
      lang,
      "",
      "This source requires proper authorization."
    );
  }

  if (s.includes("timeout")) {
    return pickLang(
      lang,
      "",
      "The source responded too slowly."
    );
  }

  if (s.includes("quota") || s.includes("rate limit") || s.includes("429")) {
    return pickLang(
      lang,
      "",
      "The source temporarily limited the number of requests."
    );
  }

  if (s.includes("invalid key") || s.includes("api key")) {
    return pickLang(
      lang,
      "",
      "A working access key is not configured for this source."
    );
  }

  if (status === "clean" || status === "malicious" || status === "no_data") {
    return null;
  }

  if (status === "error") {
    return pickLang(
      lang,
      "",
      "The source could not complete the check correctly."
    );
  }

  return null;
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

const SectionHeader = ({ title, icon, expanded, onPress }) => (
  <TouchableOpacity
    onPress={onPress}
    style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}
  >
    <View style={{ flexDirection: "row", alignItems: "center" }}>
      {!!icon && <Ionicons name={icon} size={18} color={T.logo} style={{ marginRight: 8 }} />}
      <Text style={{ color: T.text, fontWeight: "900", fontSize: 16 }}>{title}</Text>
    </View>
    <Ionicons name={expanded ? "chevron-up" : "chevron-down"} size={18} color={T.dim} />
  </TouchableOpacity>
);

const SourceRow = ({ item, currentLang, tx }) => {
  const status = String(item?.status || "").toLowerCase();
  const prettyDetails = extractPrettySourceDetails(item, currentLang);
  const statusText = formatSourceStatusText(status, item, currentLang);

  return (
    <View
      style={{
        paddingVertical: 12,
        borderTopWidth: 1,
        borderTopColor: "rgba(255,255,255,0.06)",
      }}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <Text style={{ color: T.text, fontWeight: "900", fontSize: 15, flex: 1 }}>
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
            {statusText || tx("shieldPro.sources.statusUnknown", pickLang(currentLang, "", "Unknown"))}
          </Text>
        </View>
      </View>

      {!!item?.verdict && item.verdict !== "unknown" && (
        <Text style={{ color: T.dim, marginTop: 6 }}>
          {tx("shieldPro.sources.sourceVerdict", pickLang(currentLang, "", "Source verdict"))}:{" "}
          <Text style={{ color: T.text, fontWeight: "800" }}>{formatSourceVerdict(item.verdict, currentLang)}</Text>
        </Text>
      )}

      {!!prettyDetails && (
        <Text style={{ color: T.dim, marginTop: 4, fontSize: 12, lineHeight: 17 }}>
          {prettyDetails}
        </Text>
      )}

      {!!item?.evidence?.length && (
        <View style={{ marginTop: 8 }}>
          {item.evidence.slice(0, 3).map((ev, i) => (
            <Text key={`${item?.name || "src"}-ev-${i}`} style={{ color: T.dim, lineHeight: 18, marginBottom: 4 }}>
              • {prettyEvidenceText(ev, currentLang)}
            </Text>
          ))}
        </View>
      )}
    </View>
  );
};


const UxRiskBlock = ({ report, currentLang, tx }) => {
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
    whatText = whatText.split("??????").join(tokenText).split("??????").join(tokenText).replace(/tokens/gi, tokenText);
    worstText = worstText.split("??????").join(tokenText).split("??????").join(tokenText).replace(/tokens/gi, tokenText);
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
      title: tx("shieldPro.ux.whatCanHappen", isRu ? "\u0427\u0442\u043e \u043c\u043e\u0436\u0435\u0442 \u043f\u0440\u043e\u0438\u0437\u043e\u0439\u0442\u0438" : "What can happen"),
      text: whatText,
      color: T.warn,
    } : null,

    worstText ? {
      icon: "skull-outline",
      title: tx("shieldPro.ux.worstCase", isRu ? "\u0425\u0443\u0434\u0448\u0438\u0439 \u0441\u0446\u0435\u043d\u0430\u0440\u0438\u0439" : "Worst case"),
      text: worstText,
      color: T.bad,
    } : null,

    ...(hasRealPermissions ? [{
      icon: "key-outline",
      title: tx("shieldPro.ux.permissions", isRu ? "\u0427\u0442\u043e \u0442\u044b \u0440\u0430\u0437\u0440\u0435\u0448\u0430\u0435\u0448\u044c" : "What you are approving"),
      text: String(permissions?.summary || permissions?.note || "").trim(),
      color: T.accent,
      revokeUrl: permissions?.can_spend === true ? "https://revoke.cash/" : "",
      extra: [
        permissions.can_spend === true ? `${isRu ? "\u041c\u043e\u0436\u0435\u0442 \u0441\u043f\u0438\u0441\u044b\u0432\u0430\u0442\u044c" : "Can spend"}: ${isRu ? "\u0434\u0430" : "yes"}` : "",
        permissions.unlimited === true ? `${isRu ? "\u041b\u0438\u043c\u0438\u0442" : "Spend limit"}: \u221e` : "",
        permissions.spend_limit && permissions.spend_limit !== "unknown" && permissions.spend_limit !== "?" ? `${isRu ? "\u041b\u0438\u043c\u0438\u0442" : "Spend limit"}: ${safeText(permissions.spend_limit)}` : "",
        tokens.length ? `${isRu ? "\u0422\u043e\u043a\u0435\u043d\u044b" : "Tokens"}: ${tokens.join(", ")}` : "",
        permissions?.spender_trust ? `${isRu ? "\u0420\u0435\u043f\u0443\u0442\u0430\u0446\u0438\u044f spender" : "Spender reputation"}: ${permissions.spender_trust}` : "",
        permissions?.spender_label ? `${isRu ? "\u041a\u043e\u043c\u0443 \u0434\u0430\u0451\u0448\u044c \u0434\u043e\u0441\u0442\u0443\u043f" : "Spender"}: ${permissions.spender_label}` : permissions?.spender ? `${isRu ? "\u041a\u043e\u043c\u0443 \u0434\u0430\u0451\u0448\u044c \u0434\u043e\u0441\u0442\u0443\u043f" : "Spender"}: ${permissions.spender}` : "",
      ].filter(Boolean),
    }] : []),
  ].filter(Boolean);

  if (!rows.length) return null;

  return (
    <BlurCard style={{ borderColor: "rgba(255,176,32,0.30)" }}>
      <Text style={{ color: T.text, fontWeight: "900", fontSize: 18, marginBottom: 10 }}>
        {tx("shieldPro.ux.title", isRu ? "\u0427\u0442\u043e \u0440\u0435\u0430\u043b\u044c\u043d\u043e \u043c\u043e\u0436\u0435\u0442 \u0441\u043b\u0443\u0447\u0438\u0442\u044c\u0441\u044f" : "What can actually happen")}
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
                <Text key={`ux-extra-${i}`} style={{ color: T.dim, lineHeight: 19, marginTop: 2 }}>{"\u2022"} {x}</Text>
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


const EvidenceRow = ({ ev, currentLang }) => (
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
        {ev?.code ? prettyTitleFromCode(ev?.code, currentLang) : safeText(backendSignalText(ev))}
      </Text>
      <Text style={{ color: T.accent, fontWeight: "900", marginLeft: 8 }}>
        +{safeText(ev?.severity ?? 0)}
      </Text>
    </View>

    {!!ev?.source && (
      <Text style={{ color: T.dim, marginTop: 5, fontSize: 12 }}>
        {pickLang(currentLang, "\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a", "Source")}: {formatSourceName(ev.source, currentLang)}
      </Text>
    )}

    <Text style={{ color: T.dim, marginTop: 8, lineHeight: 18 }}>
      {prettyEvidenceText(ev, currentLang)}
    </Text>
  </View>
);

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
	    investigation: "AI-\u0440\u0430\u0441\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u043d\u0438\u0435",
	    hypothesis: "\u0413\u0438\u043f\u043e\u0442\u0435\u0437\u0430",
	    chain: "\u0421\u0435\u0442\u044c",
	    runtime: "Runtime",
	    reputation: "\u0420\u0435\u043f\u0443\u0442\u0430\u0446\u0438\u044f",
	    attackPath: "\u041a\u0430\u0440\u0442\u0430 \u0430\u0442\u0430\u043a\u0438",
	    evidenceLinks: "Evidence links",
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
	    investigation: "AI-\u0440\u043e\u0437\u0441\u043b\u0456\u0434\u0443\u0432\u0430\u043d\u043d\u044f",
	    hypothesis: "\u0413\u0456\u043f\u043e\u0442\u0435\u0437\u0430",
	    chain: "\u041c\u0435\u0440\u0435\u0436\u0430",
	    runtime: "Runtime",
	    reputation: "\u0420\u0435\u043f\u0443\u0442\u0430\u0446\u0456\u044f",
	    attackPath: "\u041a\u0430\u0440\u0442\u0430 \u0430\u0442\u0430\u043a\u0438",
	    evidenceLinks: "Evidence links",
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
	    investigation: "Investigation map",
	    hypothesis: "Hypothesis",
	    chain: "Chain",
	    runtime: "Runtime",
	    reputation: "Reputation",
	    attackPath: "Attack path",
	    evidenceLinks: "Evidence links",
	    matched: "matched",
	    notListed: "not listed",
	    applied: "applied",
    notApplied: "not applied",
	};

const InvestigationMapCard = ({ report, currentLang, tx, expanded, onPress }) => {
  const investigation = report?.aiInvestigation || {};
  const multi = report?.multiChain || {};
  const runtime = report?.runtimeContract || {};
  const graph = report?.graphContext || {};
  const reputation = report?.reputationContext || {};
  const evidenceLinks = Array.isArray(investigation.evidence_links) ? investigation.evidence_links : [];
  const attackPath = Array.isArray(investigation.attack_path) ? investigation.attack_path : [];
  const hasData =
    investigation.summary ||
    investigation.primary_hypothesis ||
    multi.available ||
    multi.chain_label ||
    runtime.should_warn !== undefined ||
    graph.available ||
    reputation.risk_score ||
    reputation.level ||
    reputation.memory_level;

  if (!hasData) return null;

  return (
    <BlurCard>
      <SectionHeader
        title={tx("shieldPro.investigation.title", backendIntelLabel(currentLang, "investigation"))}
        icon="git-network-outline"
        expanded={expanded}
        onPress={onPress}
      />

      {expanded && (
        <View style={{ marginTop: 12 }}>
          {!!(investigation.primary_hypothesis || investigation.summary) && (
            <View style={{ borderWidth: 1, borderColor: "rgba(255,176,32,0.18)", borderRadius: 16, padding: 12, backgroundColor: "rgba(255,176,32,0.06)", marginBottom: 10 }}>
              <Text style={{ color: T.accent, fontWeight: "900", fontSize: 12, marginBottom: 4 }}>
                {tx("shieldPro.investigation.hypothesis", backendIntelLabel(currentLang, "hypothesis"))}
              </Text>
              <Text style={{ color: T.text, lineHeight: 19 }}>{safeText(investigation.primary_hypothesis || investigation.summary)}</Text>
              {!!evidenceLinks.length && (
                <Text style={{ color: T.dim, marginTop: 6, fontSize: 12 }}>
                  {tx("shieldPro.investigation.evidenceLinks", backendIntelLabel(currentLang, "evidenceLinks"))}: {evidenceLinks.length}
                </Text>
              )}
            </View>
          )}

          <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" }}>
            <MetricChip label={tx("shieldPro.investigation.chain", backendIntelLabel(currentLang, "chain"))} value={multi.chain_label || multi.chain || "—"} />
            <MetricChip label={tx("shieldPro.investigation.runtime", backendIntelLabel(currentLang, "runtime"))} value={runtime.should_block !== undefined ? `block ${runtime.should_block}` : "—"} />
            <MetricChip label={tx("shieldPro.investigation.reputation", backendIntelLabel(currentLang, "reputation"))} value={reputation.level || reputation.memory_level || reputation.risk_level || reputation.risk_score || "—"} />
          </View>

          {!!attackPath.length && (
            <View style={{ marginTop: 10 }}>
              <Text style={{ color: T.accent, fontWeight: "900", fontSize: 12, marginBottom: 6 }}>
                {tx("shieldPro.investigation.attackPath", backendIntelLabel(currentLang, "attackPath"))}
              </Text>
              {attackPath.slice(0, 5).map((step, idx) => (
                <Text key={`attack-path-${idx}`} style={{ color: T.dim, lineHeight: 18, marginBottom: 4 }}>
                  {idx + 1}. {safeText(step)}
                </Text>
              ))}
            </View>
          )}
        </View>
      )}
    </BlurCard>
  );
};
  return (String(lang || "").toLowerCase().startsWith("uk") ? uk : String(lang || "").toLowerCase().startsWith("ru") ? ru : en)[key] || key;
}

const BackendIntelCard = ({ report, currentLang, tx }) => {
  const intel = report?.backendDetails || {};
  const db = intel.database || {};
  const dbMatch = db.match || {};
  const gate = intel.safetyGate || {};
  const rows = [];

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

  (intel.topContributors || []).slice(0, 5).forEach((item, idx) => {
    const text = backendSignalText(item);
    if (text) rows.push({ label: idx === 0 ? backendIntelLabel(currentLang, "evidence") : "", value: text });
  });

  if ((intel.hardEvidenceCodes || []).length) {
    rows.push({ label: backendIntelLabel(currentLang, "hard"), value: intel.hardEvidenceCodes.slice(0, 8).join(", ") });
  }

  if (!rows.length) return null;

  return (
    <BlurCard>
      <View style={{ flexDirection: "row", alignItems: "center" }}>
        <Ionicons name="server-outline" size={18} color={T.logo} style={{ marginRight: 8 }} />
        <Text style={{ color: T.text, fontWeight: "900", fontSize: 16 }}>
          {tx("shieldPro.backendIntel.title", backendIntelLabel(currentLang, "title"))}
        </Text>
      </View>
      <View style={{ marginTop: 12 }}>
        {rows.map((row, idx) => (
          <View
            key={`backend-intel-${idx}`}
            style={{
              borderTopWidth: idx === 0 ? 0 : 1,
              borderTopColor: "rgba(255,255,255,0.06)",
              paddingTop: idx === 0 ? 0 : 10,
              marginBottom: idx === rows.length - 1 ? 0 : 10,
            }}
          >
            {!!row.label && <Text style={{ color: T.accent, fontWeight: "900", fontSize: 12, marginBottom: 4 }}>{row.label}</Text>}
            <Text style={{ color: T.dim, lineHeight: 18 }}>{safeText(row.value)}</Text>
          </View>
        ))}
      </View>
    </BlurCard>
  );
};


export default function ShieldPro() {
  useEffect(() => {
    logEvent("shield_pro_screen_open", { screen: "shield_pro" });
  }, []);
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const access = useAuthStore((s) => s.access);
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

	  const currentLang = useMemo(() => {
	    const v = i18nHook?.lang || i18nHook?.language || i18nHook?.i18n?.language || i18nHook?.locale || "en";
	    const s = String(v || "").toLowerCase();
	    return s.startsWith("ru") ? "ru" : s.startsWith("uk") ? "uk" : "en";
  }, [i18nHook]);

  const authUid = useMemo(() => uidFromUser(user), [user]);
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
      const best = await getBestKnownUid(user || proof?.authUser, installUid, access || proof?.accessToken || "");
      setResolvedUid(best);
    })();
  }, [user, installUid, access]);

  const [proLocal, setProLocal] = useState(false);
  const [checkingPro, setCheckingPro] = useState(true);

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
          const proof = await loadProProof();
          const authHeader = access || proof?.accessToken || null;

          if (authHeader) {
            const bestUid = await getBestKnownUid(user || proof?.authUser, installUid, authHeader);

            const res = await fetchWithTimeout(
              `${BACKEND}/iap/status`,
              {
                headers: buildHeaders({
                  currentLang,
                  uid: bestUid,
                  access,
                  proof,
                }),
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
        }

        setProLocal(!!localPro);
      } catch {
        setProLocal(false);
      } finally {
        setCheckingPro(false);
      }
    })();
  }, [uid, access, currentLang, user, installUid]);

  useEffect(() => {
    if (checkingPro) return;
    if (isPro === false) {
      router.replace("/pro");
    }
  }, [checkingPro, isPro, router]);

  const [input, setInput] = useState("");
  const [out, setOut] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showSamples, setShowSamples] = useState(false);
  const [backendError, setBackendError] = useState("");

  const [voteSending, setVoteSending] = useState(false);
  const [myVote, setMyVote] = useState(null);
  const [crowdItems, setCrowdItems] = useState([]);
  const [crowdLoading, setCrowdLoading] = useState(false);

	  const [expanded, setExpanded] = useState({
	    scoring: true,
	    investigation: true,
	    sources: true,
    evidence: true,
    honeypot: true,
    token: true,
    community: true,
    crowd: false,
  });

  const toggle = (k) => setExpanded((s) => ({ ...s, [k]: !s[k] }));

  const shareShotRef = useRef(null);
  const normalizedOut = useMemo(() => {
    try {
      return normalizeScanReport(out, currentLang);
    } catch {
      if (!out || typeof out !== "object") return null;
      return {
        input: out?.input || input,
        normalized_input: out?.normalized_input || out?.input || input,
        kind: normalizeKind(out?.kind, out?.input || input),
        score: Number(out?.score || 0) || 0,
        level: String(out?.level || "unknown").toLowerCase(),
        kindLabel: formatKindLabel(out?.kind, out?.kind_localized, currentLang),
        levelLabel: formatLevelLabel(out?.level, currentLang),
        verdictLabel: out?.verdictLabel || out?.ai_verdict_localized || out?.verdict_localized || out?.ai_verdict || out?.verdict || "",
        aiVerdictLabel: out?.aiVerdictLabel || out?.ai_verdict_localized || out?.ai_verdict || null,
        aiHumanVerdict: out?.aiHumanVerdict || getAiVerdictText(out),
        aiExplanationResult: out?.aiExplanationResult || out?.ai_explanation_result || null,
        sources: Array.isArray(out?.sources) ? out.sources : [],
        evidenceList: Array.isArray(out?.evidenceList) ? out.evidenceList : Array.isArray(out?.evidence) ? out.evidence : [],
        scoring: out?.scoring || {},
        community: out?.community || {},
        details: out?.details || {},
        backendDetails: out?.backendDetails || {},
        quota: out?.quota || null,
        what_can_happen: out?.what_can_happen || "",
        worst_case: out?.worst_case || "",
        permissions_summary: out?.permissions_summary || null,
        risk_reasons: Array.isArray(out?.risk_reasons) ? out.risk_reasons : [],
        confirmedRedFlag: !!out?.confirmed_red_flag || !!out?.confirmedRedFlag,
      };
    }
  }, [out, currentLang, input]);

  const verdictText = normalizedOut?.verdictLabel || "";
  const verdictColor = levelColor(normalizedOut?.level);
  const verdictBg = levelBg(normalizedOut?.level);

  const targetText = useMemo(() => {
    return (
      normalizedOut?.details?.page?.final_url ||
      normalizedOut?.normalized_input ||
      normalizedOut?.input ||
      (input || "").trim()
    );
  }, [normalizedOut, input]);

  const sourceSummary = useMemo(() => {
    const items = Array.isArray(normalizedOut?.sources) ? normalizedOut.sources : [];
    let malicious = 0;
    let clean = 0;
    let noData = 0;
    let warning = 0;

    items.forEach((x) => {
      const s = String(x?.status || "").toLowerCase();
      if (s === "malicious") malicious += 1;
      else if (s === "clean") clean += 1;
      else if (s === "no_data") noData += 1;
      else warning += 1;
    });

    return { malicious, clean, noData, warning, total: items.length };
  }, [normalizedOut]);

  const topEvidence = useMemo(() => {
    const backendTop = normalizedOut?.backendDetails?.topContributors;
    if (Array.isArray(backendTop) && backendTop.length) return backendTop.slice(0, 3);
    return Array.isArray(normalizedOut?.evidenceList) ? normalizedOut.evidenceList.slice(0, 3) : [];
  }, [normalizedOut]);

  const onCopy = async (text) => {
    try {
      await Clipboard.setStringAsync(text || "");
      showAppAlert(tx("common.copied",pickLang(currentLang, "", "Copied")),
        tx("shieldPro.copied", pickLang(currentLang, "", "Copied to clipboard."))
      );
    } catch {}
  };

  const onOpen = async (url) => {
    try {
      if (!url || !reIsHttp.test(url)) return;
      await Linking.openURL(url);
    } catch {}
  };

  const onShare = async () => {
    if (!normalizedOut) return;

    try {
      logEvent("shield_pro_share_start", { screen: "shield_pro", level: normalizedOut?.level || "n/a", kind: normalizedOut?.kind || "unknown" });
      await new Promise((resolve) => InteractionManager.runAfterInteractions(resolve));
      await new Promise((resolve) => setTimeout(resolve, 220));

      const uri = await shareShotRef.current?.capture?.();

      if (!uri || typeof uri !== "string") {
        throw new Error("capture_empty");
      }

      const canShareFile = await Sharing.isAvailableAsync().catch(() => false);

      if (canShareFile) {
        logEvent("shield_pro_share_success", { screen: "shield_pro", method: "file", level: normalizedOut?.level || "n/a", kind: normalizedOut?.kind || "unknown" });
        await Sharing.shareAsync(uri, {
          mimeType: "image/png",
          UTI: "public.png",
          dialogTitle: tx("shieldPro.share.dialogTitle", pickLang(currentLang, "", "Share")),
        });
        return;
      }

      const message = summarizeShareText(normalizedOut, tx, currentLang);

      logEvent("shield_pro_share_success", { screen: "shield_pro", method: "native", level: normalizedOut?.level || "n/a", kind: normalizedOut?.kind || "unknown" });
      await Share.share({
        title: "Noytrix ScamShield PRO",
        url: uri,
        message: Platform.OS === "ios" ? message : `${message}
${uri}`,
      });
    } catch (e) {
      const raw = String(e?.message || e || "").toLowerCase();

      if (!raw.includes("cancel")) {
        showAppAlert(
          tx("shieldPro.share.errorTitle", pickLang(currentLang, "", "Could not share")),
          tx("shieldPro.share.errorText", pickLang(currentLang, "", "Could not send the image. Please try again."))
        );
      }

      logEvent("shield_pro_share_error", { screen: "shield_pro", err: String(e?.message || e || "error") });
      console.log("[SHIELD PRO SHARE ERROR]", e?.message || e);
    }
  };

  const loadCrowd = useCallback(async () => {
    setCrowdLoading(true);
    try {
      const proof = await loadProProof();
      const bestUid = await getBestKnownUid(user || proof?.authUser, installUid, access || proof?.accessToken || "");

      const tryUrls = [
        `${BACKEND}/community/top-scams?limit=20`,
        `${BACKEND}/community/top?limit=20`,
        `${BACKEND}/community/stats?limit=20`,
        `${BACKEND}/scan/stats?limit=20`,
      ];

      const headers = buildHeaders({
        currentLang,
        uid: bestUid,
        access,
        proof,
        includeAppKey: true,
      });

      const r = await fetchJsonTry(tryUrls, { headers });

      let items = [];
      if (r.ok) {
        if (Array.isArray(r.json)) items = r.json;
        else if (Array.isArray(r.json?.items)) items = r.json.items;
        else if (Array.isArray(r.json?.data)) items = r.json.data;
      }
      setCrowdItems(Array.isArray(items) ? items : []);
    } catch {
      setCrowdItems([]);
    } finally {
      setCrowdLoading(false);
    }
  }, [user, installUid, access, currentLang]);

  useEffect(() => {
    loadCrowd();
  }, [loadCrowd]);

  const onScan = async () => {
    const raw = (input || "").trim();
    if (!raw) return;

    const proof = await loadProProof();
    const effectiveUid = await getBestKnownUid(user || proof?.authUser, installUid, access || proof?.accessToken || "");

    logEvent("scan_submitted", { screen: "shield_pro", lang: currentLang, has_input: true });

    setLoading(true);
    setOut(null);
    setMyVote(null);
    setBackendError("");

    try {
      const url =
        `${BACKEND}/scan?input=${encodeURIComponent(raw)}` +
        `&lang=${encodeURIComponent(currentLang)}` +
        `&userId=${encodeURIComponent(effectiveUid || "anonymous")}`;

      const headers = buildHeaders({
        currentLang,
        uid: effectiveUid,
        access,
        proof,
      });

      const res = await fetchWithTimeout(url, { headers });
      const text = await res.text();

      let backend = null;
      try {
        backend = text ? JSON.parse(text) : null;
      } catch {
        throw new Error("invalid_json");
      }

      if (res.status === 429) {
        throw new Error("429");
      }

      if (!res.ok || !backend) {
        throw new Error(String(backend?.detail || `HTTP ${res.status}`));
      }

      let normalized = null;
      try {
        normalized = normalizeScanReport(backend, currentLang);
      } catch {
        normalized = {
          input: backend?.input || raw,
          normalized_input: backend?.normalized_input || raw,
          kind: detectKind(backend?.kind || backend?.input || raw),
          score: Number(backend?.score || 0) || 0,
          level: String(backend?.level || "unknown").toLowerCase(),
          verdictLabel:
            backend?.ai_verdict_localized ||
            backend?.verdict_localized ||
            backend?.ai_verdict ||
            backend?.verdict ||
            "",
          sources: Array.isArray(backend?.sources) ? backend.sources : [],
          evidenceList: Array.isArray(backend?.evidence) ? backend.evidence : [],
          scoring: backend?.scoring || {},
          community: backend?.community || {},
          details: backend?.details || {},
          backendDetails: {},
          quota: backend?.quota || null,
          what_can_happen: backend?.what_can_happen || "",
          worst_case: backend?.worst_case || "",
          permissions_summary: backend?.permissions_summary || null,
          risk_reasons: Array.isArray(backend?.risk_reasons) ? backend.risk_reasons : [],
          confirmedRedFlag: !!backend?.confirmed_red_flag,
        };
      }
      if (!normalized) throw new Error("empty_scan_result");
      setOut(backend);

      const uv = backend?.user_vote || backend?.vote || null;
      if (uv === "scam" || uv === "safe") setMyVote(uv);

      loadCrowd();

      logEvent("scan_result", {
        screen: "shield_pro",
        lang: currentLang,
        level: normalized?.level || "n/a",
        score: Number(normalized?.score ?? 0),
        kind: normalized?.kind || "text",
        backend_ok: true,
      });
    } catch (e) {
      const msg = explainBackendMessage(String(e?.message || e || ""), currentLang);
      setBackendError(msg);

      showAppAlert(tx("common.error",pickLang(currentLang, "", "Error")), msg);

      logEvent("scan_result", {
        screen: "shield_pro",
        lang: currentLang,
        level: "n/a",
        score: 0,
        kind: detectKind(raw),
        backend_ok: false,
        err: msg,
      });
    } finally {
      setLoading(false);
    }
  };

  const voteObj = useMemo(() => {
    const obj = (
      normalizedOut?.details?.page?.final_url ||
      normalizedOut?.normalized_input ||
      normalizedOut?.input ||
      input ||
      ""
    ).trim();
    const kind = normalizedOut?.kind || detectKind(obj);
    return { obj, kind };
  }, [normalizedOut, input]);

  const sendVote = async (vote) => {
    if (!normalizedOut) return;
    const { obj, kind } = voteObj;
    if (!obj) return;

    const proof = await loadProProof();
    const effectiveUid = await getBestKnownUid(user || proof?.authUser, installUid, access || proof?.accessToken || "");

    if (!APP_KEY) {
      showAppAlert(tx("common.error",pickLang(currentLang, "", "Error")),
        tx(
          "shieldPro.vote.noAppKey",
          pickLang(
            currentLang,
            "",
            "The app key required to send community votes was not found."
          )
        )
      );
      return;
    }

    const title =
      vote === "scam"
        ? tx("shieldPro.vote.confirmScamTitle", pickLang(currentLang, "", "Mark as SCAM?"))
        : tx("shieldPro.vote.confirmSafeTitle", pickLang(currentLang, "", "Mark as SAFE?"));

    const msg =
      vote === "scam"
        ? tx(
            "shieldPro.vote.confirmScamText",
            pickLang(currentLang, "", "Other users will see this. Mark as SCAM only if you are sure.")
          )
        : tx(
            "shieldPro.vote.confirmSafeText",
            pickLang(currentLang, "", "Other users will see this. Mark as SAFE only if you are sure.")
          );

    showAppAlert(title,msg, [
      { text: tx("common.cancel", pickLang(currentLang, "", "Cancel")), style: "cancel" },
      {
        text: tx("common.ok", "OK"),
        onPress: async () => {
          try {
            logEvent("shield_pro_vote_start", { screen: "shield_pro", vote, kind });
            setVoteSending(true);
            setMyVote(vote);

            const body = {
              input: obj,
              obj,
              kind,
              vote,
              is_scam: vote === "scam",
              userId: effectiveUid || "anonymous",
            };

            const headers = buildHeaders({
              currentLang,
              uid: effectiveUid,
              access,
              proof,
              includeJson: true,
              includeAppKey: true,
            });

            const r = await fetchJsonTry([`${BACKEND}/scan/vote`], {
              method: "POST",
              headers,
              body: JSON.stringify(body),
            });

            if (!r.ok) {
              const detail = r?.json?.detail || r?.json?.message || r?.json?.error || "vote failed";
              throw new Error(detail);
            }

            const comm = r?.json?.community || null;
            if (comm) {
              setOut((prev) => {
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

            loadCrowd();

            logEvent("shield_pro_vote_success", { screen: "shield_pro", vote, kind });
            showAppAlert(tx("shieldPro.vote.savedTitle",pickLang(currentLang, "", "Done")),
              tx("shieldPro.vote.savedText", pickLang(currentLang, "", "Your vote has been saved and is visible to everyone."))
            );
          } catch (e) {
            setMyVote(null);
            logEvent("shield_pro_vote_error", { screen: "shield_pro", vote, kind, err: String(e?.message || e || "error") });
            showAppAlert(tx("common.error",pickLang(currentLang, "", "Error")),
              pickLang(currentLang, "", "Could not send the vote. Please try again.")
            );
          } finally {
            setVoteSending(false);
          }
        },
      },
    ]);
  };

  const ShareCard = () => {
    if (!normalizedOut) return null;

    const date = new Date();
    const iso = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

    const objLabel =
      normalizedOut?.details?.page?.final_url ||
      normalizedOut?.normalized_input ||
      normalizedOut?.input ||
      tx("shieldPro.share.objectPlaceholder", pickLang(currentLang, "", "Object"));

    return (
      <LinearGradient colors={[GRAD.start, GRAD.mid, GRAD.end]} style={{ width: 1024, padding: 40, borderRadius: 28 }}>
        <Text style={{ color: T.logo, fontWeight: "900", fontSize: 42, marginBottom: 18 }}>
          {tx("shieldPro.share.title", "ScamShield PRO")}
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
                {String(normalizedOut?.kind || "text").toUpperCase()}
              </Text>
            </View>
            <Text style={{ color: T.text, fontSize: 28, fontWeight: "900", flexShrink: 1 }} numberOfLines={2}>
              {objLabel}
            </Text>
          </View>

          <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" }}>
            <View style={{ width: "48%", borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16, marginBottom: 12 }}>
              <Text style={{ color: T.dim, marginBottom: 6 }}>
                {tx("shieldPro.share.verdictTitle", pickLang(currentLang, "", "Verdict"))}
              </Text>
              <Text style={{ color: levelColor(normalizedOut?.level), fontWeight: "900", fontSize: 22 }}>
                {verdictText}
              </Text>
            </View>

            <View style={{ width: "48%", borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16, marginBottom: 12 }}>
              <Text style={{ color: T.dim, marginBottom: 6 }}>{tx("shieldPro.share.scoreTitle", "Score")}</Text>
              <Text style={{ color: T.text, fontWeight: "900", fontSize: 22 }}>{normalizedOut.score}/100</Text>
            </View>

            <View style={{ width: "48%", borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16, marginBottom: 12 }}>
              <Text style={{ color: T.dim, marginBottom: 6 }}>
                {tx("shieldPro.share.typeTitle", pickLang(currentLang, "", "Type"))}
              </Text>
              <Text style={{ color: T.text, fontWeight: "900", fontSize: 22 }}>{normalizedOut.kindLabel}</Text>
            </View>

            <View style={{ width: "48%", borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16, marginBottom: 12 }}>
              <Text style={{ color: T.dim, marginBottom: 6 }}>
                {tx("shieldPro.share.dateTitle", pickLang(currentLang, "", "Date"))}
              </Text>
              <Text style={{ color: T.text, fontWeight: "900", fontSize: 22 }}>{iso}</Text>
            </View>
          </View>

          <View style={{ marginTop: 18 }}>
            {(normalizedOut.evidenceList || []).slice(0, 4).map((r, i) => (
              <Text key={i} style={{ color: T.dim, fontSize: 18, marginBottom: 6 }}>
                - {prettyTitleFromCode(r?.code, currentLang)}
              </Text>
            ))}
          </View>

          <Text style={{ color: T.dim, marginTop: 18, fontSize: 14 }}>
            {tx("shieldPro.share.footer", "NOYTRIX - ScamShield PRO")}
          </Text>
        </View>
      </LinearGradient>
    );
  };

  if (checkingPro) return null;
  if (!isPro) return null;

  return (
    <LinearGradient colors={[GRAD.start, GRAD.mid, GRAD.end]} style={{ flex: 1, paddingTop: 48 }}>
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 130 }}>
        <Text style={{ color: T.logo, fontWeight: "900", fontSize: 30, marginBottom: 6, letterSpacing: 0.2 }}>
          {tx("shieldPro.title", "ScamShield PRO")}
        </Text>

        <Text style={{ color: T.dim, marginBottom: 14, fontSize: 15, lineHeight: 20 }}>
          {tx(
            "shieldPro.subtitle",
            pickLang(
              currentLang,
              "",
              "Deep multi-API analysis + real source statuses + premium verdict engine."
            )
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
            marginBottom: 14,
          }}
        >
          <Text style={{ color: T.text, fontWeight: "900" }}>
            {tx("shieldPro.unlimited", pickLang(currentLang, "PRO • ", "PRO • unlimited"))}
          </Text>
        </View>

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
              placeholder={tx("shieldPro.input.placeholder", "Paste URL / domain / address / contract / ticker / text")}
              placeholderTextColor={T.dim}
              value={input}
              onChangeText={setInput}
              style={{ color: T.text, minHeight: 70, paddingHorizontal: 14, paddingVertical: 12, fontSize: 16 }}
              multiline
            />
          </View>

          <View style={{ flexDirection: "row", marginTop: 12 }}>
            <View style={{ flex: 1 }}>
              <PrimaryButton
                onPress={onScan}
                disabled={loading}
                title={loading ? tx("shieldPro.buttons.checking", "Checking…") : tx("shieldPro.buttons.check", pickLang(currentLang, "", "Check"))}
                leftIcon={
                  loading ? (
                    <ActivityIndicator color={T.accentText} />
                  ) : (
                    <Ionicons name="shield-checkmark" size={18} color={T.accentText} />
                  )
                }
              />
            </View>
            <View style={{ width: 12 }} />
            <SecondaryButton
              onPress={() => setShowSamples(true)}
              title={tx("shieldPro.buttons.samples", pickLang(currentLang, "", "Samples"))}
              leftIcon={<Ionicons name="sparkles-outline" size={16} color={T.dim} />}
            />
          </View>

          <View style={{ flexDirection: "row", flexWrap: "wrap", marginTop: 10 }}>
            <SecondaryButton
              title={tx("shieldPro.buttons.clear", pickLang(currentLang, "", "Clear"))}
              onPress={() => {
                setInput("");
                setOut(null);
                setMyVote(null);
                setBackendError("");
              }}
              leftIcon={<Ionicons name="close-circle-outline" size={16} color={T.dim} />}
              style={{ marginRight: 10, marginBottom: 10 }}
            />
            <SecondaryButton
              title={tx("shieldPro.buttons.copyInput", pickLang(currentLang, "", "Copy input"))}
              onPress={() => onCopy(input)}
              leftIcon={<Ionicons name="copy-outline" size={16} color={T.dim} />}
              style={{ marginBottom: 10 }}
            />
          </View>
        </BlurCard>

        {!!backendError && (
          <BlurCard style={{ borderColor: "rgba(255,107,107,0.35)" }}>
            <Text style={{ color: T.bad, fontWeight: "900", fontSize: 17, marginBottom: 8 }}>
              {tx("shieldPro.backendError.title", pickLang(currentLang, "", "Check unavailable"))}
            </Text>
            <Text style={{ color: T.dim, lineHeight: 19 }}>{backendError}</Text>
          </BlurCard>
        )}

        {normalizedOut && (
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
                  <Text
                    style={{
                      color: verdictColor,
                      fontWeight: "900",
                      fontSize: 28,
                      textAlign: "center",
                    }}
                  >
                    {verdictText}
                  </Text>

                  {!!targetText && (
                    <Text style={{ color: T.dim, marginTop: 8, textAlign: "center" }} numberOfLines={2}>
                      {targetText}
                    </Text>
                  )}
                </View>

                <View style={{ alignItems: "center", marginBottom: 12 }}>
                  <Text style={{ color: T.text, fontSize: 34, fontWeight: "900" }}>
                    {normalizedOut.score}/100
                  </Text>
                  <View style={{ width: "100%", marginTop: 2 }}>
                    <ScoreBar value={normalizedOut.score} color={verdictColor} height={10} />
                  </View>
                </View>

                {!!normalizedOut.aiHumanVerdict && (
                  <View style={{ marginTop: 12, borderRadius: 16, borderWidth: 1, borderColor: "rgba(255,255,255,0.10)", backgroundColor: "rgba(0,0,0,0.18)", padding: 12 }}>
                    <Text style={{ color: T.text, fontSize: 15, lineHeight: 21, textAlign: "center", fontWeight: "800" }}>
                      {normalizedOut.aiHumanVerdict}
                    </Text>
                  </View>
                )}

                {!!normalizedOut.confirmedRedFlag && (
                  <View
                    style={{
                      marginTop: 8,
                      padding: 12,
                      borderRadius: 14,
                      borderWidth: 1,
                      borderColor: "rgba(255,107,107,0.22)",
                      backgroundColor: "rgba(255,107,107,0.10)",
                    }}
                  >
                    <Text style={{ color: T.bad, fontWeight: "900" }}>
                      {tx("shieldPro.result.confirmedRedFlag", pickLang(currentLang, "", "Confirmed red flag is active"))}
                    </Text>
                  </View>
                )}
              </View>

              <View style={{ flexDirection: "row", flexWrap: "wrap", marginTop: 12 }}>
                <SecondaryButton
                  title={tx("shieldPro.actions.copyReport", pickLang(currentLang, "", "Copy report"))}
                  onPress={() => onCopy(summarizeShareText(normalizedOut, tx, currentLang))}
                  leftIcon={<Ionicons name="copy-outline" size={16} color={T.dim} />}
                  style={{ marginRight: 10, marginBottom: 10 }}
                />
                <SecondaryButton
                  title={tx("shieldPro.actions.open", pickLang(currentLang, "", "Open"))}
                  onPress={() => onOpen(targetText)}
                  leftIcon={<Ionicons name="open-outline" size={16} color={T.dim} />}
                  style={{ marginRight: 10, marginBottom: 10 }}
                />
                <SecondaryButton
                  title={tx("shieldPro.actions.share", pickLang(currentLang, "", "Share"))}
                  onPress={onShare}
                  leftIcon={<Ionicons name="share-social-outline" size={16} color={T.dim} />}
                  style={{ marginBottom: 10 }}
                />
              </View>
            </BlurCard>

            <UxRiskBlock report={normalizedOut} currentLang={currentLang} tx={tx} />

            <BlurCard>
              <Text style={{ color: T.text, fontWeight: "900", fontSize: 16, marginBottom: 10 }}>
                {tx("shieldPro.quickIntel.title", pickLang(currentLang, "Quick intelligence", "Quick intelligence"))}
              </Text>

              <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" }}>
                <MetricChip
                  label={tx("shieldPro.quickIntel.sourcesTotal", pickLang(currentLang, "", "Sources"))}
                  value={sourceSummary.total}
                />
                <MetricChip
                  label={tx("shieldPro.quickIntel.clean", pickLang(currentLang, "", "Clean"))}
                  value={sourceSummary.clean}
                />
                <MetricChip
                  label={tx("shieldPro.quickIntel.malicious", pickLang(currentLang, "", "Malicious"))}
                  value={sourceSummary.malicious}
                />
                <MetricChip
                  label={tx("shieldPro.quickIntel.noData", pickLang(currentLang, "", "No data / warning"))}
                  value={sourceSummary.noData + sourceSummary.warning}
                />
              </View>

              {!!topEvidence.length && (
                <View style={{ marginTop: 6 }}>
                  <Text style={{ color: T.dim, marginBottom: 8 }}>
                    {tx("shieldPro.quickIntel.topSignals", pickLang(currentLang, "", "Top signals"))}
                  </Text>
                  {topEvidence.map((ev, i) => (
                    <Text key={`quick-signal-${i}`} style={{ color: T.text, marginBottom: 6, lineHeight: 18 }}>
                      • {ev?.code ? prettyTitleFromCode(ev?.code, currentLang) : safeText(backendSignalText(ev))}
                    </Text>
                  ))}
                </View>
              )}
            </BlurCard>

	            <BackendIntelCard report={normalizedOut} currentLang={currentLang} tx={tx} />

            <BlurCard>
              <SectionHeader
                title={tx("shieldPro.scoring.title", pickLang(currentLang, "Scoring model", "Scoring model"))}
                icon="analytics-outline"
                expanded={expanded.scoring}
                onPress={() => toggle("scoring")}
              />

              {expanded.scoring && (
                <View style={{ marginTop: 12 }}>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" }}>
                    <MetricChip
                      label={tx("shieldPro.scoring.confirmed", pickLang(currentLang, "Confirmed external", "Confirmed external"))}
                      value={normalizedOut?.scoring?.confirmed_external_signals || 0}
                    />
                    <MetricChip
                      label={tx("shieldPro.scoring.heuristics", pickLang(currentLang, "Heuristics", "Heuristics"))}
                      value={normalizedOut?.scoring?.heuristics || 0}
                    />
                    <MetricChip
                      label={tx("shieldPro.scoring.pageContent", pickLang(currentLang, "Page content", "Page content"))}
                      value={normalizedOut?.scoring?.page_content || 0}
                    />
                    <MetricChip
                      label={tx("shieldPro.scoring.community", pickLang(currentLang, "Community", "Community"))}
                      value={normalizedOut?.scoring?.community_votes || 0}
                    />
                  </View>
                </View>
              )}
            </BlurCard>

            <BlurCard>
              <SectionHeader
                title={tx("shieldPro.sources.title", pickLang(currentLang, "", "Sources"))}
                icon="layers-outline"
                expanded={expanded.sources}
                onPress={() => toggle("sources")}
              />

              {expanded.sources && (
                <View
                  style={{
                    borderWidth: 1,
                    borderColor: T.border,
                    borderRadius: 16,
                    paddingHorizontal: 12,
                    paddingTop: 6,
                    paddingBottom: 10,
                    backgroundColor: "rgba(255,255,255,0.03)",
                    marginTop: 10,
                  }}
                >
                  {((normalizedOut.sources || []).length > 0 && !(normalizedOut?.kind === "transaction" || normalizedOut?.permissions_summary?.can_spend === true)) ? (
                    normalizedOut.sources.map((src, idx) => (
                      <SourceRow key={`${src?.name || "src"}-${idx}`} item={src} currentLang={currentLang} tx={tx} />
                    ))
                  ) : (
                    <Text style={{ color: T.dim, paddingVertical: 10 }}>
                      {(normalizedOut?.kind === "transaction" || normalizedOut?.permissions_summary?.can_spend === true)
                        ? (currentLang === "ru" ? "Источник: анализ транзакции (EVM decoder)" : "Source: transaction analysis (EVM decoder)")
                        : tx("shieldPro.sources.empty", pickLang(currentLang, "", "Server returned no sources."))}
                    </Text>
                  )}
                </View>
              )}
            </BlurCard>

            <BlurCard>
              <SectionHeader
                title={tx("shieldPro.evidence.title", pickLang(currentLang, "", "Signals and explanations"))}
                icon="flash-outline"
                expanded={expanded.evidence}
                onPress={() => toggle("evidence")}
              />

              {expanded.evidence && (
                <View style={{ marginTop: 10 }}>
                  {(normalizedOut.evidenceList || []).length ? (
                    normalizedOut.evidenceList.slice(0, 18).map((ev, i) => (
                      <EvidenceRow key={`ev-${i}`} ev={ev} currentLang={currentLang} />
                    ))
                  ) : (
                    <Text style={{ color: T.dim }}>
                      {tx("shieldPro.evidence.empty", pickLang(currentLang, "", "No explicit signals were found."))}
                    </Text>
                  )}
                </View>
              )}
            </BlurCard>

            {!!(normalizedOut?.honeypot_risk || normalizedOut?.honeypot_status || normalizedOut?.honeypot) && (
              <BlurCard>
                <SectionHeader
                  title={tx("shieldPro.honeypot.title", pickLang(currentLang, "Honeypot ", "Honeypot analysis"))}
                  icon="flask-outline"
                  expanded={expanded.honeypot}
                  onPress={() => toggle("honeypot")}
                />

                {expanded.honeypot && (
                  <View style={{ marginTop: 12 }}>
                    <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" }}>
                      <MetricChip label={tx("shieldPro.honeypot.risk", "Risk")} value={normalizedOut.honeypot_risk || "—"} />
                      <MetricChip label={tx("shieldPro.honeypot.status", "Status")} value={safeText(normalizedOut.honeypot_status || "—")} />
                      <MetricChip
                        label={tx("shieldPro.honeypot.isHoneypot", "Is Honeypot")}
                        value={normalizedOut?.honeypot?.is_honeypot ? tx("common.yes", pickLang(currentLang, "", "Yes")) : tx("common.no", pickLang(currentLang, "", "No"))}
                      />
                      <MetricChip
                        label={tx("shieldPro.honeypot.liquidity", "Liquidity")}
                        value={formatMoneyCompact(normalizedOut?.honeypot?.liquidity)}
                      />
                    </View>

                    <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" }}>
                      <MetricChip label={tx("shieldPro.honeypot.buyTax", "Buy Tax")} value={formatPercent(normalizedOut?.honeypot?.buy_tax)} />
                      <MetricChip label={tx("shieldPro.honeypot.sellTax", "Sell Tax")} value={formatPercent(normalizedOut?.honeypot?.sell_tax)} />
                      <MetricChip label={tx("shieldPro.honeypot.transferTax", "Transfer Tax")} value={formatPercent(normalizedOut?.honeypot?.transfer_tax)} />
                      <MetricChip label={tx("shieldPro.honeypot.openSource", "Open Source")} value={yesNo(normalizedOut?.honeypot?.open_source, tx, currentLang)} />
                    </View>

                    <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" }}>
                      <MetricChip label={tx("shieldPro.honeypot.simulation", "Simulation")} value={yesNo(normalizedOut?.honeypot?.simulation_success, tx, currentLang)} />
                      <MetricChip label={tx("shieldPro.honeypot.chainId", "Chain ID")} value={normalizedOut?.honeypot?.chain_id || "—"} />
                      <MetricChip label={tx("shieldPro.honeypot.maxBuy", "Max Buy")} value={safeText(normalizedOut?.honeypot?.max_buy)} />
                      <MetricChip label={tx("shieldPro.honeypot.maxSell", "Max Sell")} value={safeText(normalizedOut?.honeypot?.max_sell)} />
                    </View>
                  </View>
                )}
              </BlurCard>
            )}

            {hasObjectData(normalizedOut?.token) && (
              <BlurCard>
                <SectionHeader
                  title={tx("shieldPro.token.title", pickLang(currentLang, "", "Token data"))}
                  icon="logo-bitcoin"
                  expanded={expanded.token}
                  onPress={() => toggle("token")}
                />

                {expanded.token && (
                  <View style={{ marginTop: 10 }}>
                    <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" }}>
                      <MetricChip
                        label={tx("shieldPro.token.contract", pickLang(currentLang, "", "Contract"))}
                        value={normalizedOut?.token?.contract || "—"}
                      />
                      <MetricChip
                        label={tx("shieldPro.token.domain", pickLang(currentLang, "", "Domain"))}
                        value={normalizedOut?.token?.domain || "—"}
                      />
                      <MetricChip
                        label={tx("shieldPro.token.holders", pickLang(currentLang, "Holders", "Holders"))}
                        value={normalizedOut?.token?.holders || "—"}
                      />
                      <MetricChip
                        label={tx("shieldPro.token.riskFlags", pickLang(currentLang, "Risk flags", "Risk flags"))}
                        value={(normalizedOut?.token?.token_risk_flags || []).length}
                      />
                    </View>

                    <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" }}>
                      <MetricChip
                        label={tx("shieldPro.token.marketCap", pickLang(currentLang, "Market cap", "Market cap"))}
                        value={formatMoneyCompact(normalizedOut?.token?.market_data?.market_cap)}
                      />
                      <MetricChip
                        label={tx("shieldPro.token.volume24h", pickLang(currentLang, "24h volume", "24h volume"))}
                        value={formatMoneyCompact(normalizedOut?.token?.market_data?.total_volume)}
                      />
                      <MetricChip
                        label={tx("shieldPro.token.price", pickLang(currentLang, "Price", "Price"))}
                        value={safeText(normalizedOut?.token?.market_data?.current_price)}
                      />
                      <MetricChip
                        label={tx("shieldPro.token.rank", pickLang(currentLang, "Rank", "Rank"))}
                        value={safeText(normalizedOut?.token?.market_data?.market_cap_rank)}
                      />
                    </View>
                  </View>
                )}
              </BlurCard>
            )}

            {(normalizedOut?.kind === "wallet" || normalizedOut?.kind === "contract") && (
              <BlurCard>
                <Text style={{ color: T.text, fontWeight: "900", fontSize: 16, marginBottom: 10 }}>
                  {tx("shieldPro.contract.title", pickLang(currentLang, "", "Contract checks"))}
                </Text>

                <Text style={{ color: T.dim, lineHeight: 18 }}>
                  {tx(
                    "shieldPro.contract.note",
                    pickLang(
                      currentLang,
                      "",
                      "For EVM objects, check Etherscan / BscScan / DexScreener / Honeypot in the Sources block above."
                    )
                  )}
                </Text>
              </BlurCard>
            )}

            <BlurCard>
              <SectionHeader
                title={tx("shieldPro.community.title", pickLang(currentLang, "", "Community verdict"))}
                icon="people-outline"
                expanded={expanded.community}
                onPress={() => toggle("community")}
              />

              {expanded.community && (
                <>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", marginTop: 10 }}>
                    <MetricChip
                      label={tx("shieldPro.community.verdict", pickLang(currentLang, "", "Verdict"))}
                      value={formatCommunityVerdict(normalizedOut?.community?.community_verdict, currentLang)}
                    />
                    <MetricChip
                      label={tx("shieldPro.community.scam", pickLang(currentLang, "SCAM votes", "SCAM votes"))}
                      value={normalizedOut?.community?.scam_votes || 0}
                    />
                    <MetricChip
                      label={tx("shieldPro.community.safe", pickLang(currentLang, "SAFE votes", "SAFE votes"))}
                      value={normalizedOut?.community?.safe_votes || 0}
                    />
                    <MetricChip
                      label={tx("shieldPro.community.total", pickLang(currentLang, "Users", "Users"))}
                      value={normalizedOut?.community?.total_users || 0}
                    />
                  </View>

                  <View style={{ flexDirection: "row", marginTop: 8 }}>
                    <View style={{ flex: 1 }}>
                      <PrimaryButton
                        title={
                          voteSending
                            ? tx("shieldPro.vote.sending", pickLang(currentLang, "", "Sending…"))
                            : myVote === "scam"
                            ? "✓ SCAM"
                            : tx("shieldPro.vote.scam", "Mark SCAM")
                        }
                        onPress={() => sendVote("scam")}
                        disabled={voteSending}
                        bg="rgba(255,107,107,0.18)"
                        textColor={T.bad}
                        leftIcon={
                          voteSending ? (
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
                          voteSending
                            ? tx("shieldPro.vote.sending", pickLang(currentLang, "", "Sending…"))
                            : myVote === "safe"
                            ? "✓ SAFE"
                            : tx("shieldPro.vote.safe", "Mark SAFE")
                        }
                        onPress={() => sendVote("safe")}
                        disabled={voteSending}
                        bg="rgba(41,211,122,0.18)"
                        textColor={T.good}
                        leftIcon={
                          voteSending ? (
                            <ActivityIndicator color={T.good} />
                          ) : (
                            <Ionicons name="checkmark-circle-outline" size={18} color={T.good} />
                          )
                        }
                      />
                    </View>
                  </View>

                  {!!myVote && (
                    <Text style={{ color: T.dim, marginTop: 10, fontSize: 12 }}>
                      {tx("shieldPro.vote.youMarked", pickLang(currentLang, "", "Your vote"))}:{" "}
                      <Text style={{ color: myVote === "scam" ? T.bad : T.good, fontWeight: "900" }}>
                        {myVote === "scam" ? "SCAM" : "SAFE"}
                      </Text>
                    </Text>
                  )}
                </>
              )}
            </BlurCard>
          </>
        )}

        <BlurCard>
          <SectionHeader
            title={tx("shieldPro.crowd.title", pickLang(currentLang, "Public reputation feed", "Public reputation feed"))}
            icon="radio-outline"
            expanded={expanded.crowd}
            onPress={() => toggle("crowd")}
          />

          <Text style={{ color: T.dim, marginTop: 8, lineHeight: 18 }}>
            {tx(
              "shieldPro.crowd.subtitle",
              pickLang(currentLang, "", "This shows real community data from the backend.")
            )}
          </Text>

          {expanded.crowd && (
            <>
              <View style={{ marginTop: 10 }}>
                <SecondaryButton
                  title={tx("shieldPro.crowd.refresh", pickLang(currentLang, "", "Refresh"))}
                  onPress={loadCrowd}
                  leftIcon={<Ionicons name="refresh" size={16} color={T.dim} />}
                />
              </View>

              <View style={{ marginTop: 10 }}>
                {crowdLoading ? (
                  <Text style={{ color: T.dim }}>
                    {tx("shieldPro.crowd.loading", pickLang(currentLang, "", "Loading…"))}
                  </Text>
                ) : crowdItems?.length ? (
                  crowdItems.slice(0, 20).map((item, idx) => {
                    const obj = item.obj || item.object || item.input || item.url || item.address || "";
                    const kind = item.kind || item.type || "unknown";
                    const total = Number(item.total_votes || item.total_users || item.total || item.checks || item.count || 0) || 0;
                    const scam = Number(item.scam_votes || item.scam || item.flagged || 0) || 0;
                    const safe = Number(item.safe_votes || item.safe || 0) || 0;
                    const verdict = String(item.community_verdict || "unknown");

                    return (
                      <View
                        key={`${obj}-${idx}`}
                        style={{
                          borderWidth: 1,
                          borderColor: "rgba(255,255,255,0.08)",
                          borderRadius: 16,
                          padding: 12,
                          marginBottom: 10,
                          backgroundColor: scam > safe ? "rgba(255,107,107,0.12)" : "rgba(255,255,255,0.03)",
                        }}
                      >
                        <Text style={{ color: T.text, fontWeight: "900" }} numberOfLines={1}>
                          {obj.length > 60 ? obj.slice(0, 60) + "…" : obj}
                        </Text>

                        <Text style={{ color: T.dim, marginTop: 6, fontSize: 12, lineHeight: 18 }}>
                          {tx("shieldPro.crowd.type", pickLang(currentLang, "", "Type"))}:{" "}
                          <Text style={{ color: T.text, fontWeight: "800" }}>{formatCrowdKind(kind, currentLang)}</Text> ·{" "}
                          {tx("shieldPro.crowd.verdict", pickLang(currentLang, "", "Verdict"))}:{" "}
                          <Text style={{ color: T.text, fontWeight: "800" }}>{formatCommunityVerdict(verdict, currentLang)}</Text> ·{" "}
                          {tx("shieldPro.crowd.votes", pickLang(currentLang, "", "Votes"))}:{" "}
                          <Text style={{ color: T.text, fontWeight: "900" }}>{total}</Text> ·{" "}
                          <Text style={{ color: T.bad, fontWeight: "900" }}>{scam} SCAM</Text> ·{" "}
                          <Text style={{ color: T.good, fontWeight: "900" }}>{safe} SAFE</Text>
                        </Text>

                        <View style={{ flexDirection: "row", marginTop: 10 }}>
                          <View style={{ flex: 1 }}>
                            <SecondaryButton
                              title={tx("shieldPro.crowd.open", pickLang(currentLang, "", "Open"))}
                              onPress={() => {
                                if (reIsHttp.test(obj)) onOpen(obj);
                                else {
                                  setInput(obj);
                                  setExpanded((s) => ({ ...s, crowd: false }));
                                }
                              }}
                              leftIcon={<Ionicons name="open-outline" size={16} color={T.dim} />}
                            />
                          </View>
                          <View style={{ width: 10 }} />
                          <View style={{ flex: 1 }}>
                            <SecondaryButton
                              title={tx("shieldPro.crowd.copy", pickLang(currentLang, "", "Copy"))}
                              onPress={() => onCopy(obj)}
                              leftIcon={<Ionicons name="copy-outline" size={16} color={T.dim} />}
                            />
                          </View>
                        </View>
                      </View>
                    );
                  })
                ) : (
                  <Text style={{ color: T.dim, marginTop: 6 }}>
                    {tx("shieldPro.crowd.empty", pickLang(currentLang, "", "No public stats yet."))}
                  </Text>
                )}
              </View>
            </>
          )}
        </BlurCard>

        <BlurCard>
          <Text style={{ color: T.text, fontWeight: "900", marginBottom: 8, fontSize: 18 }}>
            {tx("shieldPro.how.title", pickLang(currentLang, "How PRO works", "How PRO works"))}
          </Text>
          <Text style={{ color: T.dim, lineHeight: 20 }}>
            {tx(
              "shieldPro.how.text",
              pickLang(
                currentLang,
                "PRO ",
                "PRO shows real source statuses, signal explanations, scoring, AI verdict, community verdict, and honeypot data directly from the backend. The final verdict is built from confirmed external signals, heuristics, page content, and community votes."
              )
            )}
          </Text>
          <Text style={{ color: "rgba(168,180,207,0.85)", marginTop: 10, fontSize: 12, lineHeight: 18 }}>
            {tx(
              "shieldPro.how.disclaimer",
              pickLang(
                currentLang,
                "",
                "Never enter a seed phrase, private key, or connect your wallet to suspicious sites."
              )
            )}
          </Text>
        </BlurCard>
      </ScrollView>

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
              {tx("shieldPro.samples.title", pickLang(currentLang, "", "Samples"))}
            </Text>

            {SAMPLES.map((s, i) => (
              <TouchableOpacity
                key={i}
                onPress={() => {
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
                  {currentLang === "ru" ? s.dRu : s.dEn}
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




