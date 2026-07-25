import { OneSignal } from "react-native-onesignal";
import { normalizeLang } from "../i18n/lang";

export async function syncPushLanguageTag(language) {
  const lang = normalizeLang(language);

  // Language restoration can run before the layout effect initializes OneSignal.
  // Calling User.addTag before initWithContext crashes the native SDK on Android.
  if (!globalThis.__NOYTRIX_ONESIGNAL_INITIALIZED__) return false;

  try {
    if (OneSignal?.User?.addTag) {
      await OneSignal.User.addTag("lang", lang);
    } else if (OneSignal?.User?.addTags) {
      await OneSignal.User.addTags({ lang });
    }
    return true;
  } catch (e) {
    console.log("[PUSH] language tag sync error:", e);
    return false;
  }
}
