import analytics from "@react-native-firebase/analytics";
import { NativeModules, Platform } from "react-native";

let lastScreen = null;
const TikTokEvents = NativeModules?.TikTokEvents || null;

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
}

export async function logEvent(name, params = {}) {
  try {
    if (!name) return;
    await analytics().logEvent(name, {
      ...params,
      platform: Platform.OS,
    });
    await logTikTokEvent(name, params);
  } catch (e) {
    console.log("[ANALYTICS] event error:", e);
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
