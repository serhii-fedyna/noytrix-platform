// app/lib/notifications.js
import { Platform } from "react-native";
import { OneSignal } from "react-native-onesignal";

const ONESIGNAL_APP_ID = "844ce644-cdb6-4d24-b07e-4e1f117e247d";

function initOneSignalSafe() {
  try {
    OneSignal.initialize(ONESIGNAL_APP_ID);
  } catch (e) {
    console.log("[PUSH] OneSignal.initialize skipped/error:", e);
  }
}

export function getPushSubscriptionState() {
  try {
    initOneSignalSafe();
    const sub = OneSignal.User.pushSubscription;
    return {
      id: sub?.getId?.() ?? null,
      token: sub?.getToken?.() ?? null,
      optedIn: sub?.getOptedIn?.() ?? null,
    };
  } catch (e) {
    console.log("[PUSH] getPushSubscriptionState error:", e);
    return { id: null, token: null, optedIn: null };
  }
}

export async function setPushNotificationsEnabled(enabled, { request = false } = {}) {
  try {
    initOneSignalSafe();

    if (!enabled) {
      try {
        OneSignal.User.pushSubscription.optOut();
      } catch (e) {
        console.log("[PUSH] optOut error:", e);
      }
      return { ...getPushSubscriptionState(), enabled: false };
    }

    if (request) {
      try {
        await OneSignal.Notifications.requestPermission(true);
      } catch (e) {
        console.log("[PUSH] requestPermission error:", e);
      }
    }

    try {
      OneSignal.User.pushSubscription.optIn();
    } catch (e) {
      console.log("[PUSH] optIn error:", e);
    }

    await new Promise((resolve) => setTimeout(resolve, 1500));
    return { ...getPushSubscriptionState(), enabled: true };
  } catch (e) {
    console.log("[PUSH] setPushNotificationsEnabled error:", e);
    return { id: null, token: null, optedIn: null, enabled: false };
  }
}


export async function ensurePushReady({ request = false } = {}) {
  try {
    console.log("[PUSH] ensurePushReady CALLED. request =", request);
    console.log("[PUSH] platform =", Platform.OS);

    initOneSignalSafe();

    const logState = (label = "state") => {
      try {
        const sub = OneSignal.User.pushSubscription;
        const id = sub?.getId?.() ?? null;
        const token = sub?.getToken?.() ?? null;
        const optedIn = sub?.getOptedIn?.() ?? null;

        console.log(`[PUSH] ${label}`, {
          id,
          token,
          optedIn,
          platform: Platform.OS,
        });

        return { id, token, optedIn };
      } catch (e) {
        console.log("[PUSH] logState error:", e);
        return { id: null, token: null, optedIn: null };
      }
    };

    logState("before_permission");

    if (request) {
      try {
        const accepted = await OneSignal.Notifications.requestPermission(true);
        console.log("[PUSH] requestPermission result =", accepted);
      } catch (e) {
        console.log("[PUSH] requestPermission error:", e);
      }
    }

    try {
      OneSignal.User.pushSubscription.optIn();
      console.log("[PUSH] optIn called");
    } catch (e) {
      console.log("[PUSH] optIn error:", e);
    }

    await new Promise((resolve) => setTimeout(resolve, 2000));

    const state2 = logState("after_2s");

    if (state2?.id && state2?.optedIn) {
      return state2.id;
    }

    await new Promise((resolve) => setTimeout(resolve, 3000));

    const state5 = logState("after_5s");

    if (state5?.id && state5?.optedIn) {
      return state5.id;
    }

    console.log("[PUSH] subscription is not ready");
    return null;
  } catch (e) {
    console.log("[PUSH] ensurePushReady error:", e);
    return null;
  }
}




