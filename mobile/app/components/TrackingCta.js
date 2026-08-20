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
    title: "Track this object",
    text: "PRO rechecks it every 6 hours and alerts you only when a meaningful security change is found.",
    saving: "Starting tracking...",
    readyTitle: "Tracking is active",
    readyText: "The current risk was saved. Noytrix will notify you if something important changes.",
    authTitle: "Sign in to start tracking",
    authText: "Your account keeps tracked objects and alerts available on every device.",
    proTitle: "Tracking requires PRO",
    proText: "Add an object once and Noytrix will keep checking it in the background.",
    errorTitle: "Tracking could not be started",
    errorText: "The object was not added. Please try again in a moment.",
  },
  ru: {
    title: "Добавить в отслеживание",
    text: "PRO перепроверяет объект каждые 6 часов и сообщает только о важных изменениях безопасности.",
    saving: "Включаем отслеживание...",
    readyTitle: "Отслеживание включено",
    readyText: "Текущий риск сохранён. Noytrix сообщит, если произойдёт важное изменение.",
    authTitle: "Войдите для отслеживания",
    authText: "Аккаунт сохранит объекты и уведомления на всех ваших устройствах.",
    proTitle: "Отслеживание доступно в PRO",
    proText: "Добавьте объект один раз, и Noytrix продолжит проверять его в фоне.",
    errorTitle: "Не удалось включить отслеживание",
    errorText: "Объект не добавлен. Попробуйте ещё раз через минуту.",
  },
  uk: {
    title: "Додати до відстеження",
    text: "PRO перевіряє об'єкт кожні 6 годин і повідомляє лише про важливі зміни безпеки.",
    saving: "Вмикаємо відстеження...",
    readyTitle: "Відстеження увімкнено",
    readyText: "Поточний ризик збережено. Noytrix повідомить, якщо станеться важлива зміна.",
    authTitle: "Увійдіть для відстеження",
    authText: "Акаунт збереже об'єкти та сповіщення на всіх ваших пристроях.",
    proTitle: "Відстеження доступне в PRO",
    proText: "Додайте об'єкт один раз, і Noytrix продовжить перевіряти його у фоні.",
    errorTitle: "Не вдалося увімкнути відстеження",
    errorText: "Об'єкт не додано. Спробуйте ще раз за хвилину.",
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

export default function TrackingCta({ result, target, source = "scan", compact = false }) {
  const { i18n } = useTranslation();
  const lang = langKey(i18n?.language);
  const text = COPY[lang];
  const [busy, setBusy] = useState(false);
  const object = useMemo(() => targetFrom(result, target), [result, target]);

  async function startTracking() {
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
        body: JSON.stringify({
          target: object,
          scan: result || {},
          source,
          lang,
          alertSettings: { risk_change: true, critical_only: false },
        }),
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
      router.push({ pathname: "/tracking", params: { watchId: String(payload?.item?.id || "") } });
    } catch (error) {
      showAppAlert(text.errorTitle, error?.message || text.errorText);
    } finally {
      setBusy(false);
    }
  }

  if (!object) return null;

  return (
    <View style={[styles.card, compact && styles.compact]}>
      <View style={styles.iconWrap}>
        <Ionicons name="eye" size={22} color="#FFB21E" />
      </View>
      <View style={styles.copy}>
        <Text style={styles.title}>{text.title}</Text>
        {!compact && <Text style={styles.text}>{text.text}</Text>}
      </View>
      <Pressable style={({ pressed }) => [styles.button, pressed && styles.pressed]} onPress={startTracking} disabled={busy}>
        {busy ? <ActivityIndicator color="#071025" /> : <Ionicons name="add-circle" size={19} color="#071025" />}
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
    borderColor: "rgba(255, 178, 30, 0.42)",
    backgroundColor: "rgba(255, 178, 30, 0.07)",
    gap: 12,
  },
  compact: { marginTop: 10 },
  iconWrap: {
    width: 42,
    height: 42,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255, 178, 30, 0.12)",
    borderWidth: 1,
    borderColor: "rgba(255, 178, 30, 0.28)",
  },
  copy: { gap: 5 },
  title: { color: "#FFFFFF", fontSize: 18, fontWeight: "900" },
  text: { color: "#B7C2D8", fontSize: 14, lineHeight: 20, fontWeight: "700" },
  button: {
    minHeight: 52,
    borderRadius: 16,
    backgroundColor: "#FFB21E",
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 8,
  },
  buttonText: { color: "#071025", fontSize: 15, fontWeight: "900", textAlign: "center", flexShrink: 1 },
  pressed: { opacity: 0.86 },
});
