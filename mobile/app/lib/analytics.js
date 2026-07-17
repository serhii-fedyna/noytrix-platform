import analytics from "@react-native-firebase/analytics";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Constants from "expo-constants";
import { NativeModules, Platform } from "react-native";
import { BACKEND } from "./backend";
import { getIdentityUserId, getInstallUserId, identityHeaders } from "./identity";

let lastScreen = null;
let sessionId = null;
const TikTokEvents = NativeModules?.TikTokEvents || null;
const ATTRIBUTION_KEY = "noytrix.installAttribution.v1";

const SERVER_EVENTS = new Set([
  "app_first_open",
  "session_started",
  "signup_started",
  "signup_completed",
  "scan_started",
  "scan_completed",
  "scan_failed",
  "scan_result_viewed",
  "risk_explanation_viewed",
  "paywall_viewed",
  "paywall_value_viewed",
  "paywall_plan_selected",
  "paywall_cta_clicked",
  "paywall_restore_clicked",
  "paywall_restore_completed",
  "paywall_restore_failed",
  "trial_started",
  "purchase_started",
  "purchase_completed",
  "purchase_failed",
  "purchase_cancelled",
  "subscription_renewed",
  "subscription_cancelled",
  "subscription_expired",
  "app_feedback_submitted",
]);

const SENSITIVE_PARTS = [
  "private",
  "seed",
  "mnemonic",
  "password",
  "passphrase",
  "secret",
  "token",
  "authorization",
  "auth",
  "key",
];

function eventId() {
  return `evt_${Date.now()}_${Math.random().toString(36).slice(2, 12)}`;
}

function currentSessionId() {
  if (!sessionId) sessionId = `ses_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  return sessionId;
}

function appVersion() {
  return Constants?.expoConfig?.version || Constants?.manifest?.version || Constants?.nativeAppVersion || "";
}

function canonicalServerEventName(name, params = {}) {
  const n = String(name || "").toLowerCase();
  if (n === "app_open_noytrix") return "app_first_open";
  if (n === "screen_open") return "session_started";
  if (n === "registration_success" || n === "register_success" || n === "sign_up") return "signup_completed";
  if (n === "signup_started" || n === "registration_started") return "signup_started";
  if (n === "scan_submitted") return "scan_started";
  if (n === "scan_result") {
    const status = String(params?.status || params?.result || "").toLowerCase();
    return status.includes("error") || status.includes("fail") ? "scan_failed" : "scan_completed";
  }
  if (n === "pro_screen_open" || n === "pro_opened" || n === "home_open_pro") return "paywall_viewed";
  if (n === "purchase_start" || n === "google_play_purchase_start") return "purchase_started";
  if (n === "purchase_success" || n === "google_play_purchase_verified") return "purchase_completed";
  if (n === "purchase_error" || n === "google_play_restore_error") return "purchase_failed";
  if (n === "purchase_cancelled") return "purchase_cancelled";
  if (n === "review_prompt_feedback_sent") return "app_feedback_submitted";
  return SERVER_EVENTS.has(n) ? n : "";
}

function cleanTikTokParams(params = {}) {
  const out = {};
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      out[key] = value;
    } else {
      out[key] = String(value);
    }
  });
  return out;
}

function isSensitiveKey(key) {
  const low = String(key || "").toLowerCase();
  return SENSITIVE_PARTS.some((part) => low.includes(part));
}

function sanitize(value, depth = 0) {
  if (depth > 4) return String(value || "").slice(0, 500);
  if (Array.isArray(value)) return value.slice(0, 50).map((x) => sanitize(x, depth + 1));
  if (value && typeof value === "object") {
    const out = {};
    Object.entries(value).forEach(([key, item]) => {
      if (isSensitiveKey(key)) return;
      out[String(key).slice(0, 80)] = sanitize(item, depth + 1);
    });
    return out;
  }
  if (typeof value === "string") return value.slice(0, 1000);
  return value;
}

async function getAttribution() {
  try {
    const raw = await AsyncStorage.getItem(ATTRIBUTION_KEY);
    return raw ? JSON.parse(raw) || {} : {};
  } catch {
    return {};
  }
}

export async function setInstallAttribution(attribution = {}) {
  try {
    const existing = await getAttribution();
    const next = {
      ...existing,
      ...sanitize(attribution),
      install_date: existing.install_date || attribution.install_date || new Date().toISOString().slice(0, 10),
    };
    await AsyncStorage.setItem(ATTRIBUTION_KEY, JSON.stringify(next));
    return next;
  } catch {
    return null;
  }
}

function tikTokEventName(name) {
  const n = String(name || "").toLowerCase();
  if (n === "registration_success" || n === "register_success" || n === "sign_up") return "Registration";
  if (n === "login_success" || n === "auth_identify") return "Login";
  if (n === "purchase_success" || n === "google_play_purchase_verified") return "Purchase";
  if (n === "purchase_start" || n === "google_play_purchase_start") return "Subscribe";
  return "";
}

async function logTikTokEvent(name, params = {}) {
  try {
    const mapped = tikTokEventName(name);
    if (!mapped || !TikTokEvents?.trackEvent) return;
    TikTokEvents.trackEvent(mapped, cleanTikTokParams({ ...params, platform: Platform.OS }));
  } catch (e) {
    console.log("[TIKTOK] event error:", e);
  }
}

async function sendServerEvent(name, params = {}) {
  try {
    const eventName = canonicalServerEventName(name, params);
    if (!eventName) return;
    const [anonymousId, identityUserId, attribution] = await Promise.all([
      getInstallUserId(),
      getIdentityUserId(),
      getAttribution(),
    ]);
    const clean = sanitize(params || {});
    fetch(`${BACKEND}/analytics/events`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(await identityHeaders()),
      },
      body: JSON.stringify({
        event_id: eventId(),
        user_id: identityUserId || undefined,
        anonymous_id: anonymousId,
        session_id: currentSessionId(),
        platform: Platform.OS,
        app_version: appVersion(),
        event_name: eventName,
        event_time: new Date().toISOString(),
        country: clean.country || attribution.country || "",
        source: clean.source || attribution.source || attribution.utm_source || "",
        campaign: clean.campaign || attribution.campaign || attribution.utm_campaign || "",
        ad_group: clean.ad_group || attribution.ad_group || attribution.utm_adgroup || "",
        install_date: attribution.install_date || "",
        properties: clean,
      }),
    }).catch(() => null);
  } catch (e) {
    console.log("[ANALYTICS] server event error:", e);
  }
}

export async function identifyTikTokUser(user = {}) {
  try {
    if (!TikTokEvents?.identify) return;
    const email = String(user?.email || user?.username || "").trim().toLowerCase();
    const externalId = String(user?.id || user?.userId || user?._id || email || "").trim();
    const name = String(user?.nick || user?.displayName || user?.name || "").trim();
    if (!externalId && !email) return;
    TikTokEvents.identify(externalId || email, name || null, null, email || null);
  } catch (e) {
    console.log("[TIKTOK] identify error:", e);
  }
}

export async function logoutTikTokUser() {
  try {
    if (TikTokEvents?.logout) TikTokEvents.logout();
  } catch (e) {
    console.log("[TIKTOK] logout error:", e);
  }
}

export async function initAnalytics() {
  try {
    await analytics().setAnalyticsCollectionEnabled(true);
    await analytics().setUserProperty("platform", Platform.OS);
    await analytics().logEvent("app_open_noytrix", { platform: Platform.OS });
  } catch (e) {
    console.log("[ANALYTICS] init error:", e);
  }
  await sendServerEvent("app_open_noytrix", { first_open_source: "init" });
  await sendServerEvent("session_started", {});
}

export async function logEvent(name, params = {}) {
  if (!name) return;
  try {
    await analytics().logEvent(name, {
      ...params,
      platform: Platform.OS,
    });
  } catch (e) {
    console.log("[ANALYTICS] firebase event error:", e);
  }
  try {
    await logTikTokEvent(name, params);
  } catch (e) {
    console.log("[ANALYTICS] tiktok event error:", e);
  }
  try {
    await sendServerEvent(name, params);
  } catch (e) {
    console.log("[ANALYTICS] server event error:", e);
  }
}

export async function trackEvent(name, params = {}) {
  return logEvent(name, params);
}

export async function trackScreen(screenName) {
  try {
    if (!screenName || screenName === lastScreen) return;
    lastScreen = screenName;

    await analytics().logScreenView({
      screen_name: screenName,
      screen_class: screenName,
    });
  } catch (e) {
    console.log("[ANALYTICS] screen error:", e);
  }
}
