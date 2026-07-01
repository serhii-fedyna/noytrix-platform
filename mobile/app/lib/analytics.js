import analytics from "@react-native-firebase/analytics";
import { Platform } from "react-native";

let lastScreen = null;

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
