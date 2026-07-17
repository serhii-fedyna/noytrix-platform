import { OneSignal } from "react-native-onesignal";
import { normalizeLang } from "../i18n/lang";

export async function syncPushLanguageTag(language) {
  const lang = normalizeLang(language);
  try {
    if (OneSignal?.User?.addTag) {
      await OneSignal.User.addTag("lang", lang);
    } else if (OneSignal?.User?.addTags) {
      await OneSignal.User.addTags({ lang });
    }
  } catch (e) {
    console.log("[PUSH] language tag sync error:", e);
  }
}
