
import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { OneSignal } from "react-native-onesignal";

const ONESIGNAL_APP_ID = "844ce644-cdb6-4d24-b07e-4e1f117e247d";
const KEY_IDX = "@notif_ids_by_event";

function initOneSignal() {
  try {
    OneSignal.initialize(ONESIGNAL_APP_ID);
  } catch (e) {
    console.log("[notify] OneSignal init error:", e);
  }
}

function logPushState(label = "state") {
  try {
    const sub = OneSignal.User.pushSubscription;
    const id = sub?.getId?.() ?? null;
    const token = sub?.getToken?.() ?? null;
    const optedIn = sub?.getOptedIn?.() ?? null;

    console.log(`[notify] ${label}`, {
      platform: Platform.OS,
      id,
      token,
      optedIn,
    });

    return { id, token, optedIn };
  } catch (e) {
    console.log("[notify] logPushState error:", e);
    return { id: null, token: null, optedIn: null };
  }
}


export async function ensureAndroidChannel() {
  try {
    initOneSignal();
    try {
      OneSignal.User.pushSubscription.optIn();
    } catch (e) {
      console.log("[notify] optIn error:", e);
    }
    logPushState("ensureAndroidChannel");
  } catch (e) {
    console.log("[notify] ensureAndroidChannel error:", e);
  }
}


export async function askPermissions() {
  try {
    initOneSignal();

    let granted = false;
    try {
      granted = await OneSignal.Notifications.requestPermission(true);
    } catch (e) {
      console.log("[notify] requestPermission error:", e);
    }

    try {
      OneSignal.User.pushSubscription.optIn();
    } catch (e) {
      console.log("[notify] optIn after permission error:", e);
    }

    await new Promise((resolve) => setTimeout(resolve, 1500));
    const state = logPushState("askPermissions");

    return !!(granted || state?.optedIn);
  } catch (e) {
    console.log("[notify] askPermissions error:", e);
    return false;
  }
}


async function loadIndex() {
  try {
    const s = await AsyncStorage.getItem(KEY_IDX);
    return s ? JSON.parse(s) : {};
  } catch {
    return {};
  }
}

async function saveIndex(map) {
  try {
    await AsyncStorage.setItem(KEY_IDX, JSON.stringify(map));
  } catch {}
}


export async function cancelEventNotifs(eventId) {
  try {
    const idx = await loadIndex();
    delete idx[eventId];
    await saveIndex(idx);
    return true;
  } catch (e) {
    console.log("[notify] cancelEventNotifs error:", e);
    return false;
  }
}


export async function scheduleEventNotif(event, utcISO) {
  try {
    console.log("[notify] scheduleEventNotif skipped (OneSignal/server mode)", {
      eventId: event?.id ?? null,
      title: event?.title ?? null,
      utcISO: utcISO ?? null,
    });

    const idx = await loadIndex();
    if (!idx[event?.id]) idx[event?.id] = [];
    await saveIndex(idx);

    return null;
  } catch (e) {
    console.log("[notify] scheduleEventNotif error:", e);
    return null;
  }
}


export async function scheduleMany(events) {
  try {
    if (!Array.isArray(events) || !events.length) return 0;

    let n = 0;
    for (const ev of events) {
      try {
        await cancelEventNotifs(ev?.id);
        await scheduleEventNotif(ev, ev?.utc);
      } catch (e) {
        console.log("[notify] scheduleMany item error:", e);
      }
    }

    return n;
  } catch (e) {
    console.log("[notify] scheduleMany error:", e);
    return 0;
  }
}




