import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { useTranslation } from "react-i18next";
import { BACKEND } from "../lib/backend";
import { authenticatedFetch } from "../lib/authApi";
import { showAppAlert } from "../lib/appAlert";
import { useAuthStore } from "../lib/store.auth";
import { logEvent } from "../lib/analytics";

const COPY = {
  en: {
    title: "Watchlist",
    subtitle: "Your monitored crypto objects. Noytrix alerts you only when security meaningfully changes.",
    protected: "Active objects",
    lastCheck: "Last check",
    changes: "Important changes",
    noCheck: "No checks yet",
    emptyTitle: "Nothing is being tracked yet",
    emptyText: "Run a scan and tap Track this object under the verdict.",
    startScan: "Run first scan",
    proTitle: "Protect what matters, 24/7",
    proText: "Add wallets, tokens, contracts and websites after a check. Noytrix tracks meaningful changes and alerts you only when action may be needed.",
    proBenefitOne: "New threat signals",
    proBenefitTwo: "Risk-score changes",
    proBenefitThree: "Contract or domain changes",
    proBenefitFour: "A clear history of every change",
    openPro: "Unlock PRO monitoring",
    type: "Type",
    score: "Risk score",
    status: "Status",
    protectedStatus: "Tracking",
    pausedStatus: "Paused",
    lastChange: "Last change",
    noChange: "No meaningful change",
    alerts: "Important change alerts",
    criticalOnly: "Critical changes only",
    nextCheck: "Next automatic check",
    activity: "View activity",
    pause: "Pause",
    resume: "Resume",
    recheck: "Recheck now",
    remove: "Remove",
    updated: "Updated",
    removed: "Removed from tracking",
    error: "Tracking error",
    eventsEmpty: "No security events yet.",
  },
  ru: {
    title: "Наблюдение",
    subtitle: "Ваши объекты под наблюдением. Noytrix сообщает только о важных изменениях безопасности.",
    protected: "Активных объектов",
    lastCheck: "Последняя проверка",
    changes: "Важные изменения",
    noCheck: "Проверок ещё нет",
    emptyTitle: "Пока ничего не отслеживается",
    emptyText: "Запустите проверку и нажмите «Добавить в отслеживание» под вердиктом.",
    startScan: "Начать проверку",
    proTitle: "Следите за риском 24/7",
    proText: "Добавляйте кошельки, токены, контракты и сайты после проверки. Noytrix отслеживает важные изменения и предупреждает только тогда, когда может потребоваться действие.",
    proBenefitOne: "Новые сигналы угроз",
    proBenefitTwo: "Изменения уровня риска",
    proBenefitThree: "Изменения контракта или домена",
    proBenefitFour: "Понятная история каждого изменения",
    openPro: "Открыть PRO-наблюдение",
    type: "Тип",
    score: "Риск",
    status: "Статус",
    protectedStatus: "Отслеживается",
    pausedStatus: "Пауза",
    lastChange: "Последнее изменение",
    noChange: "Важных изменений нет",
    alerts: "Важные изменения",
    criticalOnly: "Только критические",
    nextCheck: "Следующая автопроверка",
    activity: "История",
    pause: "Пауза",
    resume: "Возобновить",
    recheck: "Проверить сейчас",
    remove: "Удалить",
    updated: "Обновлено",
    removed: "Удалено из отслеживания",
    error: "Ошибка отслеживания",
    eventsEmpty: "Событий безопасности пока нет.",
  },
  uk: {
    title: "Спостереження",
    subtitle: "Ваші об'єкти під наглядом. Noytrix повідомляє лише про важливі зміни безпеки.",
    protected: "Активних об'єктів",
    lastCheck: "Остання перевірка",
    changes: "Важливі зміни",
    noCheck: "Перевірок ще немає",
    emptyTitle: "Поки нічого не відстежується",
    emptyText: "Запустіть перевірку й натисніть «Додати до відстеження» під вердиктом.",
    startScan: "Почати перевірку",
    proTitle: "Стежте за ризиком 24/7",
    proText: "Додавайте гаманці, токени, контракти й сайти після перевірки. Noytrix відстежує важливі зміни та попереджає лише тоді, коли може знадобитися дія.",
    proBenefitOne: "Нові сигнали загроз",
    proBenefitTwo: "Зміни рівня ризику",
    proBenefitThree: "Зміни контракту або домену",
    proBenefitFour: "Зрозуміла історія кожної зміни",
    openPro: "Відкрити PRO-спостереження",
    type: "Тип",
    score: "Ризик",
    status: "Статус",
    protectedStatus: "Відстежується",
    pausedStatus: "Пауза",
    lastChange: "Остання зміна",
    noChange: "Важливих змін немає",
    alerts: "Важливі зміни",
    criticalOnly: "Лише критичні",
    nextCheck: "Наступна автоперевірка",
    activity: "Історія",
    pause: "Пауза",
    resume: "Відновити",
    recheck: "Перевірити зараз",
    remove: "Видалити",
    updated: "Оновлено",
    removed: "Видалено з відстеження",
    error: "Помилка відстеження",
    eventsEmpty: "Подій безпеки поки немає.",
  },
};

const C = {
  bg: "#061126",
  panel: "rgba(11, 24, 58, 0.82)",
  border: "rgba(126, 154, 210, 0.22)",
  text: "#F5F7FF",
  dim: "#AEB9D3",
  gold: "#FFB21E",
  green: "#36D66B",
  red: "#FF5D6C",
};

function langKey(language) {
  const key = String(language || "en").slice(0, 2).toLowerCase();
  return COPY[key] ? key : "en";
}

function riskColor(score) {
  if (score >= 80) return C.red;
  if (score >= 45) return C.gold;
  return C.green;
}

function kindLabel(kind, lang) {
  const labels = {
    en: { url: "Domain", wallet: "Wallet", contract: "Contract", token: "Token", transaction: "Transaction", text: "Text" },
    ru: { url: "Домен", wallet: "Кошелёк", contract: "Контракт", token: "Токен", transaction: "Транзакция", text: "Текст" },
    uk: { url: "Домен", wallet: "Гаманець", contract: "Контракт", token: "Токен", transaction: "Транзакція", text: "Текст" },
  };
  return labels[lang]?.[kind] || labels[lang]?.text || String(kind || "Object");
}

function formatTime(value, fallback) {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleString();
}

function shortTarget(value) {
  const text = String(value || "");
  return text.length > 34 ? `${text.slice(0, 18)}...${text.slice(-12)}` : text;
}

export default function TrackingScreen() {
  const { watchId } = useLocalSearchParams();
  const { i18n } = useTranslation();
  const refreshMe = useAuthStore((state) => state.refreshMe);
  const lang = langKey(i18n?.language);
  const t = COPY[lang];
  const [items, setItems] = useState([]);
  const [events, setEvents] = useState({});
  const [expanded, setExpanded] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [gate, setGate] = useState(null);

  const load = useCallback(async (soft = false) => {
    if (!soft) setLoading(true);
    setGate(null);
    try {
      const requestWatches = () => authenticatedFetch(`${BACKEND}/workspace/watches?lang=${encodeURIComponent(lang)}`, {
        headers: { "Content-Type": "application/json" },
      });
      let response = await requestWatches();
      if (response.status === 401) {
        const restoredUser = await refreshMe().catch(() => null);
        if (restoredUser) response = await requestWatches();
      }
      const payload = await response.json().catch(() => ({}));
      if (response.status === 401) {
        setGate("pro");
        setItems([]);
        return;
      }
      if (response.status === 402) {
        setGate("pro");
        setItems([]);
        return;
      }
      if (!response.ok || !payload?.ok) throw new Error(payload?.detail?.message || payload?.message || t.error);
      setItems(Array.isArray(payload.items) ? payload.items : []);
    } catch (error) {
      showAppAlert(t.error, error?.message || t.error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [lang, refreshMe, t.error]);

  useEffect(() => {
    logEvent("tracking_screen_opened", { screen: "tracking", source: watchId ? "push_or_deeplink" : "navigation" });
    load();
  }, [load, watchId]);

  useEffect(() => {
    const selected = Number(watchId);
    if (selected > 0 && items.some((item) => Number(item.id) === selected)) {
      setExpanded(selected);
    }
  }, [items, watchId]);

  const stats = useMemo(() => {
    const active = items.filter((item) => !item.paused);
    const last = items
      .map((item) => item.lastCheckedAt || item.last_checked_at || item.updatedAt || item.createdAt)
      .filter(Boolean)
      .sort()
      .pop();
    const changes = items.filter((item) => item.lastEventType || item.lastEventSummary).length;
    return { active: active.length, last, changes };
  }, [items]);

  async function mutate(item, path, options, successText, eventName = "") {
    setBusyId(item.id);
    try {
      const response = await authenticatedFetch(`${BACKEND}${path}?lang=${encodeURIComponent(lang)}`, {
        ...options,
        headers: { "Content-Type": "application/json" },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload?.ok) throw new Error(payload?.detail?.message || payload?.message || t.error);
      if (payload.item) {
        setItems((current) => current.map((row) => (row.id === payload.item.id ? payload.item : row)));
      }
      if (successText) showAppAlert(t.updated, payload?.message || successText);
      if (eventName) logEvent(`${eventName}_completed`, { screen: "tracking", kind: item?.kind || "unknown" });
    } catch (error) {
      if (eventName) logEvent(`${eventName}_failed`, { screen: "tracking", reason: String(error?.message || "error").slice(0, 120) });
      showAppAlert(t.error, error?.message || t.error);
    } finally {
      setBusyId(null);
    }
  }

  async function loadEvents(item) {
    if (expanded === item.id) {
      setExpanded(null);
      return;
    }
    setExpanded(item.id);
    logEvent("tracking_object_opened", { screen: "tracking", kind: item?.kind || "unknown" });
    if (events[item.id]) return;
    try {
      const response = await authenticatedFetch(`${BACKEND}/workspace/watches/${item.id}/events?lang=${encodeURIComponent(lang)}`, {
        headers: { "Content-Type": "application/json" },
      });
      const payload = await response.json().catch(() => ({}));
      setEvents((current) => ({ ...current, [item.id]: Array.isArray(payload.items) ? payload.items : [] }));
    } catch {
      setEvents((current) => ({ ...current, [item.id]: [] }));
    }
  }

  function recheck(item) {
    logEvent("tracking_recheck_started", { screen: "tracking", kind: item?.kind || "unknown" });
    mutate(item, `/workspace/watches/${item.id}/recheck`, { method: "POST" }, "", "tracking_recheck");
  }

  function togglePause(item) {
    logEvent("tracking_pause_changed", { screen: "tracking", paused: !item.paused, kind: item?.kind || "unknown" });
    mutate(item, `/workspace/watches/${item.id}`, {
      method: "PATCH",
      body: JSON.stringify({ paused: !item.paused }),
    });
  }

  function toggleAlerts(item) {
    logEvent("tracking_alert_settings_changed", { screen: "tracking", setting: "risk_change" });
    const current = item.alertSettings || item.alert_settings || {};
    mutate(item, `/workspace/watches/${item.id}`, {
      method: "PATCH",
      body: JSON.stringify({ alertSettings: { ...current, risk_change: current.risk_change === false } }),
    });
  }

  function toggleCriticalOnly(item) {
    logEvent("tracking_alert_settings_changed", { screen: "tracking", setting: "critical_only" });
    const current = item.alertSettings || item.alert_settings || {};
    mutate(item, `/workspace/watches/${item.id}`, {
      method: "PATCH",
      body: JSON.stringify({ alertSettings: { ...current, critical_only: !current.critical_only } }),
    });
  }

  async function remove(item) {
    setBusyId(item.id);
    try {
      const response = await authenticatedFetch(`${BACKEND}/workspace/watches/${item.id}?lang=${encodeURIComponent(lang)}`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload?.ok) throw new Error(payload?.detail?.message || payload?.message || t.error);
      setItems((current) => current.filter((row) => row.id !== item.id));
      logEvent("tracking_object_removed", { screen: "tracking", kind: item?.kind || "unknown" });
      showAppAlert(t.updated, t.removed);
    } catch (error) {
      showAppAlert(t.error, error?.message || t.error);
    } finally {
      setBusyId(null);
    }
  }

  const proBenefits = [t.proBenefitOne, t.proBenefitTwo, t.proBenefitThree, t.proBenefitFour];

  const gateCard = gate ? (
    <View style={styles.empty}>
      <Ionicons name="shield-checkmark-outline" size={34} color={C.gold} />
      <Text style={styles.emptyTitle}>{t.proTitle}</Text>
      <Text style={styles.emptyText}>{t.proText}</Text>
      <View style={styles.benefitList}>
        {proBenefits.map((benefit) => (
          <View style={styles.benefitRow} key={benefit}>
            <Ionicons name="checkmark-circle" size={18} color="#35dc78" />
            <Text style={styles.benefitText}>{benefit}</Text>
          </View>
        ))}
      </View>
      <Pressable style={styles.primary} onPress={() => router.push("/pro")}>
        <Text style={styles.primaryText}>{t.openPro}</Text>
      </Pressable>
    </View>
  ) : null;

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView
        contentContainerStyle={styles.container}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(true); }} tintColor={C.gold} />}
      >
        <View style={styles.header}>
          <Text style={styles.title}>{t.title}</Text>
          <Text style={styles.subtitle}>{t.subtitle}</Text>
        </View>

        <View style={styles.stats}>
          <Stat icon="shield-checkmark" label={t.protected} value={stats.active} color={C.green} />
          <Stat icon="time-outline" label={t.lastCheck} value={formatTime(stats.last, t.noCheck)} color={C.gold} small />
          <Stat icon="warning-outline" label={t.changes} value={stats.changes} color={stats.changes ? C.red : C.green} />
        </View>

        {loading ? (
          <View style={styles.loading}><ActivityIndicator color={C.gold} /></View>
        ) : gateCard || (items.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="shield-outline" size={36} color={C.gold} />
            <Text style={styles.emptyTitle}>{t.emptyTitle}</Text>
            <Text style={styles.emptyText}>{t.emptyText}</Text>
            <Pressable style={styles.primary} onPress={() => router.push("/")}>
              <Text style={styles.primaryText}>{t.startScan}</Text>
            </Pressable>
          </View>
        ) : (
          <View style={styles.list}>
            {items.map((item) => {
              const score = Number(item.score || 0);
              const itemEvents = events[item.id] || [];
              const alertSettings = item.alertSettings || item.alert_settings || {};
              const alertsOn = alertSettings.risk_change !== false;
              const criticalOnly = Boolean(alertSettings.critical_only);
              return (
                <View key={item.id} style={styles.card}>
                  <View style={styles.cardTop}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.target}>{shortTarget(item.target)}</Text>
                      <Text style={styles.meta}>{t.type}: {kindLabel(item.kind, lang)}</Text>
                    </View>
                    <View style={[styles.score, { borderColor: riskColor(score) }]}>
                      <Text style={[styles.scoreText, { color: riskColor(score) }]}>{score}/100</Text>
                    </View>
                  </View>

                  <View style={styles.row}>
                    <Info label={t.status} value={item.paused ? t.pausedStatus : t.protectedStatus} color={item.paused ? C.gold : C.green} />
                    <Info label={t.lastCheck} value={formatTime(item.lastCheckedAt || item.last_checked_at, t.noCheck)} />
                  </View>
                  <Info label={t.lastChange} value={item.lastEventSummary || t.noChange} color={item.lastEventSummary ? C.red : C.dim} />
                  <Info label={t.nextCheck} value={formatTime(item.nextCheckAt, t.noCheck)} />

                  <View style={styles.switchRow}>
                    <Text style={styles.switchText}>{t.alerts}</Text>
                    <Switch
                      value={alertsOn}
                      onValueChange={() => toggleAlerts(item)}
                      trackColor={{ false: "#1c2744", true: "rgba(54,214,107,0.45)" }}
                      thumbColor={alertsOn ? C.green : C.dim}
                    />
                  </View>

                  <View style={styles.switchRow}>
                    <Text style={styles.switchText}>{t.criticalOnly}</Text>
                    <Switch
                      value={criticalOnly}
                      onValueChange={() => toggleCriticalOnly(item)}
                      disabled={!alertsOn}
                      trackColor={{ false: "#1c2744", true: "rgba(255,178,30,0.45)" }}
                      thumbColor={criticalOnly ? C.gold : C.dim}
                    />
                  </View>

                  <View style={styles.actions}>
                    <Action label={t.activity} icon="list" onPress={() => loadEvents(item)} />
                    <Action label={item.paused ? t.resume : t.pause} icon={item.paused ? "play" : "pause"} onPress={() => togglePause(item)} />
                    <Action label={t.recheck} icon="refresh" onPress={() => recheck(item)} busy={busyId === item.id} />
                    <Action label={t.remove} icon="trash-outline" danger onPress={() => remove(item)} />
                  </View>

                  {expanded === item.id && (
                    <View style={styles.events}>
                      {itemEvents.length === 0 ? (
                        <Text style={styles.eventText}>{t.eventsEmpty}</Text>
                      ) : itemEvents.map((event) => (
                        <Text key={event.id || `${event.created_at}-${event.summary}`} style={styles.eventText}>
                          {formatTime(event.createdAt, "")} - {event.summary || event.eventType}
                        </Text>
                      ))}
                    </View>
                  )}
                </View>
              );
            })}
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

function Stat({ icon, label, value, color, small }) {
  return (
    <View style={styles.stat}>
      <Ionicons name={icon} size={22} color={color} />
      <Text style={styles.statValue} numberOfLines={small ? 2 : 1}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function Info({ label, value, color = C.text }) {
  return (
    <View style={styles.info}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={[styles.infoValue, { color }]} numberOfLines={2}>{value}</Text>
    </View>
  );
}

function Action({ label, icon, onPress, danger, busy }) {
  return (
    <Pressable style={({ pressed }) => [styles.action, danger && styles.dangerAction, pressed && styles.pressed]} onPress={onPress}>
      {busy ? <ActivityIndicator size="small" color={C.gold} /> : <Ionicons name={icon} size={16} color={danger ? C.red : C.gold} />}
      <Text style={[styles.actionText, danger && { color: C.red }]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  container: { padding: 22, paddingBottom: 110 },
  header: { marginTop: 16, marginBottom: 18 },
  title: { color: C.gold, fontSize: 42, fontWeight: "900" },
  subtitle: { color: C.dim, fontSize: 17, lineHeight: 25, fontWeight: "700", marginTop: 8 },
  stats: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginBottom: 18 },
  stat: { flexGrow: 1, flexBasis: "30%", minHeight: 118, borderWidth: 1, borderColor: C.border, backgroundColor: C.panel, borderRadius: 18, padding: 14, justifyContent: "space-between" },
  statValue: { color: C.text, fontSize: 22, fontWeight: "900" },
  statLabel: { color: C.dim, fontSize: 12, fontWeight: "800", textTransform: "uppercase" },
  loading: { minHeight: 260, alignItems: "center", justifyContent: "center" },
  empty: { borderWidth: 1, borderColor: "rgba(255,178,30,0.35)", backgroundColor: C.panel, borderRadius: 22, padding: 22, gap: 12 },
  emptyTitle: { color: C.text, fontSize: 24, fontWeight: "900" },
  emptyText: { color: C.dim, fontSize: 16, lineHeight: 24, fontWeight: "700" },
  benefitList: { gap: 10, marginTop: 4 },
  benefitRow: { flexDirection: "row", alignItems: "center", gap: 9 },
  benefitText: { color: C.text, flex: 1, fontSize: 15, fontWeight: "800", lineHeight: 21 },
  primary: { marginTop: 8, minHeight: 54, borderRadius: 16, backgroundColor: C.gold, alignItems: "center", justifyContent: "center" },
  primaryText: { color: "#071025", fontSize: 16, fontWeight: "900" },
  list: { gap: 14 },
  card: { borderWidth: 1, borderColor: C.border, backgroundColor: C.panel, borderRadius: 22, padding: 18, gap: 14 },
  cardTop: { flexDirection: "row", alignItems: "center", gap: 12 },
  target: { color: C.text, fontSize: 18, fontWeight: "900" },
  meta: { color: C.dim, marginTop: 4, fontSize: 13, fontWeight: "700" },
  score: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7 },
  scoreText: { fontSize: 15, fontWeight: "900" },
  row: { flexDirection: "row", gap: 10 },
  info: { flex: 1, borderWidth: 1, borderColor: "rgba(255,255,255,0.08)", borderRadius: 14, padding: 12, backgroundColor: "rgba(255,255,255,0.03)" },
  infoLabel: { color: C.dim, fontSize: 11, fontWeight: "800", textTransform: "uppercase" },
  infoValue: { marginTop: 5, fontSize: 15, lineHeight: 21, fontWeight: "900" },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  switchText: { color: C.text, fontSize: 15, fontWeight: "900" },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  action: { minHeight: 42, borderRadius: 14, borderWidth: 1, borderColor: "rgba(255,178,30,0.34)", paddingHorizontal: 12, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 7 },
  dangerAction: { borderColor: "rgba(255,93,108,0.34)" },
  actionText: { color: C.text, fontWeight: "900", fontSize: 13 },
  events: { borderTopWidth: 1, borderTopColor: "rgba(255,255,255,0.08)", paddingTop: 12, gap: 8 },
  eventText: { color: C.dim, fontSize: 13, lineHeight: 19, fontWeight: "700" },
  pressed: { opacity: 0.82 },
});
