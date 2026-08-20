import React, { useMemo, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import { BACKEND } from "../lib/backend";
import { getAuthState } from "../lib/authApi";
import { getIdentityUserId, getInstallUserId, identityHeaders } from "../lib/identity";
import { showAppAlert } from "../lib/appAlert";

const COPY = {
  en: {
    title: "Protect 24/7",
    text: "PRO watches this object and alerts you only when the risk really changes.",
    saving: "Adding...",
    readyTitle: "Immunity is active",
    readyText: "Noytrix saved the baseline and will track meaningful security changes.",
    authTitle: "Sign in required",
    authText: "Sign in so Noytrix can protect this object across your devices.",
    proTitle: "PRO required",
    proText: "24/7 Immunity monitoring is available with Noytrix PRO.",
    errorTitle: "Could not add protection",
    errorText: "Try again in a moment.",
  },
  ru: {
    title: "Защитить 24/7",
    text: "PRO следит за объектом и предупреждает только о реальных изменениях риска.",
    saving: "Добавляем...",
    readyTitle: "Immunity включён",
    readyText: "Noytrix сохранил baseline и будет отслеживать важные изменения безопасности.",
    authTitle: "Нужен вход",
    authText: "Войдите в аккаунт, чтобы Noytrix защищал этот объект на всех устройствах.",
    proTitle: "Нужен PRO",
    proText: "24/7 Immunity monitoring доступен с Noytrix PRO.",
    errorTitle: "Не удалось включить защиту",
    errorText: "Попробуйте ещё раз через минуту.",
  },
  uk: {
    title: "Захистити 24/7",
    text: "PRO стежить за об'єктом і попереджає лише про реальні зміни ризику.",
    saving: "Додаємо...",
    readyTitle: "Immunity увімкнено",
    readyText: "Noytrix зберіг baseline і відстежуватиме важливі зміни безпеки.",
    authTitle: "Потрібен вхід",
    authText: "Увійдіть в акаунт, щоб Noytrix захищав цей об'єкт на всіх пристроях.",
    proTitle: "Потрібен PRO",
    proText: "24/7 Immunity monitoring доступний з Noytrix PRO.",
    errorTitle: "Не вдалося увімкнути захист",
    errorText: "Спробуйте ще раз за хвилину.",
  },
};

function langKey(language) {
  const key = String(language || "en").slice(0, 2).toLowerCase();
  return COPY[key] ? key : "en";
}

function targetFrom(result, fallback) {
  return String(
    fallback ||
      result?.details?.page?.final_url ||
      result?.normalized_input ||
      result?.input ||
      result?.target ||
      result?.url ||
      result?.address ||
      ""
  ).trim();
}

export default function Protect24Cta({ result, target, source = "scan", compact = false }) {
  const { i18n } = useTranslation();
  const lang = langKey(i18n?.language);
  const text = COPY[lang];
  const [busy, setBusy] = useState(false);
  const object = useMemo(() => targetFrom(result, target), [result, target]);

  async function addProtection() {
    if (!object || busy) return;
    setBusy(true);
    try {
      const auth = await getAuthState().catch(() => null);
      const identityUserId = await getIdentityUserId().catch(() => null);
      const installUserId = await getInstallUserId().catch(() => null);
      const userId = auth?.user?.id || auth?.user?.email || identityUserId || installUserId || "";
      const headers = await identityHeaders({
        "Content-Type": "application/json",
        ...(userId ? { "X-User-Id": String(userId) } : {}),
      });
      const response = await fetch(`${BACKEND}/workspace/watches?lang=${encodeURIComponent(lang)}`, {
        method: "POST",
        headers,
        body: JSON.stringify({ target: object, scan: result || {}, source, lang }),
      });
      const payload = await response.json().catch(() => ({}));
      const message = payload?.detail?.message || payload?.message;
      if (response.status === 401) {
        showAppAlert(text.authTitle, message || text.authText);
        router.push("/profile");
        return;
      }
      if (response.status === 402) {
        showAppAlert(text.proTitle, message || text.proText);
        router.push("/pro");
        return;
      }
      if (!response.ok || !payload?.ok) throw new Error(message || text.errorText);
      showAppAlert(text.readyTitle, payload?.message || text.readyText);
      router.push("/immunity");
    } catch (error) {
      showAppAlert(text.errorTitle, error?.message || text.errorText);
    } finally {
      setBusy(false);
    }
  }

  if (!object) return null;

  return (
    <View style={[styles.card, compact && styles.compact]}>
      <View style={styles.copy}>
        <Text style={styles.title}>{text.title}</Text>
        {!compact && <Text style={styles.text}>{text.text}</Text>}
      </View>
      <Pressable style={({ pressed }) => [styles.button, pressed && styles.pressed]} onPress={addProtection} disabled={busy}>
        {busy ? <ActivityIndicator color="#071025" /> : <Ionicons name="shield-checkmark" size={18} color="#071025" />}
        <Text style={styles.buttonText}>{busy ? text.saving : text.title}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginTop: 14,
    padding: 16,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(255, 178, 34, 0.42)",
    backgroundColor: "rgba(255, 178, 34, 0.08)",
    gap: 14,
  },
  compact: {
    marginTop: 10,
  },
  copy: {
    gap: 4,
  },
  title: {
    color: "#FFFFFF",
    fontSize: 18,
    fontWeight: "900",
  },
  text: {
    color: "#B7C2D8",
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "700",
  },
  button: {
    minHeight: 52,
    borderRadius: 16,
    backgroundColor: "#FFB21E",
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 8,
  },
  buttonText: {
    color: "#071025",
    fontSize: 16,
    fontWeight: "900",
  },
  pressed: {
    opacity: 0.86,
  },
});
