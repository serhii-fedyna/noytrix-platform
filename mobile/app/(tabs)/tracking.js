import React, {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";

import { SafeAreaView } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { useTranslation } from "react-i18next";

import { BACKEND } from "../lib/backend";
import { authenticatedFetch } from "../lib/authApi";
import { showAppAlert } from "../lib/appAlert";
import { useAuthStore } from "../lib/store.auth";

const C = {
  bgTop: "#071426",
  bgMid: "#06101F",
  bgBottom: "#040A14",

  panel: "#0B1727",
  panel2: "#0E1C2F",
  panelSoft: "#101F34",

  line: "#1C3048",
  lineSoft: "rgba(125, 154, 190, 0.14)",

  text: "#F7F9FC",
  text2: "#B5C2D4",
  dim: "#74849B",

  orange: "#FFAA18",
  orange2: "#FFB72E",
  orangeSoft: "rgba(255,170,24,0.10)",

  green: "#28D17C",
  greenSoft: "rgba(40,209,124,0.12)",

  red: "#FF5364",
  redSoft: "rgba(255,83,100,0.12)",

  amber: "#FFB020",
  amberSoft: "rgba(255,176,32,0.12)",

  blue: "#5D9CFF",
  blueSoft: "rgba(93,156,255,0.12)",
};

const COPY = {
  ru: {
    title: "Наблюдение",
    subtitle:
      "Мы следим за вашими объектами 24/7 и сообщаем только о важных изменениях.",

    search: "Поиск по объектам",
    filters: "Фильтры",

    activeObjects: "Активные\nобъекты",
    completedChecks: "Проверок\nвыполнено",
    importantChanges: "Важных\nизменений",

    all: "Все",
    wallets: "Кошельки",
    contracts: "Контракты",
    sites: "Сайты",
    transactions: "Транзакции",

    wallet: "Кошелёк",
    contract: "Контракт",
    site: "Сайт",
    transaction: "Транзакция",
    object: "Объект",

    safe: "Безопасно",
    warning: "Внимание",
    danger: "Высокий риск",
    changed: "Изменение",
    checking: "Проверяется",
    paused: "Пауза",
    error: "Ошибка",

    lastCheck: "Последняя проверка",
    risk: "Риск",
    changes: "Изменения",
    alerts: "Уведомления",

    now: "только что",
    never: "ещё не было",
    enabled: "включены",
    disabled: "выключены",

    add: "Добавить объект для отслеживания",

    emptyTitle: "Пока ничего не отслеживается",
    emptyText:
      "Проверьте кошелёк, контракт, сайт или транзакцию и добавьте объект в наблюдение.",

    noResultsTitle: "Ничего не найдено",
    noResultsText: "Измените поиск или выбранный фильтр.",

    onlyActive: "Только активные",
    onlyChanges: "Только с изменениями",
    resetFilters: "Сбросить",
    refresh: "Обновить данные",

    management: "Управление наблюдением",
    notifyChanges: "Сообщать об изменениях риска",
    criticalOnly: "Только критические события",
    history: "История изменений",
    noHistory: "Важных изменений пока не было.",

    recheck: "Проверить сейчас",
    pause: "Приостановить",
    resume: "Возобновить",
    remove: "Удалить",

    updated: "Готово",
    removed: "Объект удалён из наблюдения.",
    rechecked: "Объект проверен повторно.",
    errorMessage: "Не удалось обновить наблюдение.",
  },

  uk: {
    title: "Спостереження",
    subtitle:
      "Ми стежимо за вашими об’єктами 24/7 і повідомляємо лише про важливі зміни.",

    search: "Пошук за об’єктами",
    filters: "Фільтри",

    activeObjects: "Активні\nоб’єкти",
    completedChecks: "Перевірок\nвиконано",
    importantChanges: "Важливих\nзмін",

    all: "Усі",
    wallets: "Гаманці",
    contracts: "Контракти",
    sites: "Сайти",
    transactions: "Транзакції",

    wallet: "Гаманець",
    contract: "Контракт",
    site: "Сайт",
    transaction: "Транзакція",
    object: "Об’єкт",

    safe: "Безпечно",
    warning: "Увага",
    danger: "Високий ризик",
    changed: "Зміна",
    checking: "Перевіряється",
    paused: "Пауза",
    error: "Помилка",

    lastCheck: "Остання перевірка",
    risk: "Ризик",
    changes: "Зміни",
    alerts: "Сповіщення",

    now: "щойно",
    never: "ще не було",
    enabled: "увімкнені",
    disabled: "вимкнені",

    add: "Додати об’єкт для спостереження",

    emptyTitle: "Поки нічого не відстежується",
    emptyText:
      "Перевірте гаманець, контракт, сайт або транзакцію та додайте об’єкт до спостереження.",

    noResultsTitle: "Нічого не знайдено",
    noResultsText: "Змініть пошук або вибраний фільтр.",

    onlyActive: "Лише активні",
    onlyChanges: "Лише зі змінами",
    resetFilters: "Скинути",
    refresh: "Оновити дані",

    management: "Керування спостереженням",
    notifyChanges: "Повідомляти про зміни ризику",
    criticalOnly: "Лише критичні події",
    history: "Історія змін",
    noHistory: "Важливих змін поки не було.",

    recheck: "Перевірити зараз",
    pause: "Призупинити",
    resume: "Відновити",
    remove: "Видалити",

    updated: "Готово",
    removed: "Об’єкт видалено зі спостереження.",
    rechecked: "Об’єкт перевірено повторно.",
    errorMessage: "Не вдалося оновити спостереження.",
  },

  en: {
    title: "Monitoring",
    subtitle:
      "We monitor your objects 24/7 and notify you only about important changes.",

    search: "Search objects",
    filters: "Filters",

    activeObjects: "Active\nobjects",
    completedChecks: "Checks\ncompleted",
    importantChanges: "Important\nchanges",

    all: "All",
    wallets: "Wallets",
    contracts: "Contracts",
    sites: "Sites",
    transactions: "Transactions",

    wallet: "Wallet",
    contract: "Contract",
    site: "Site",
    transaction: "Transaction",
    object: "Object",

    safe: "Safe",
    warning: "Attention",
    danger: "High risk",
    changed: "Changed",
    checking: "Checking",
    paused: "Paused",
    error: "Error",

    lastCheck: "Last check",
    risk: "Risk",
    changes: "Changes",
    alerts: "Alerts",

    now: "just now",
    never: "not yet",
    enabled: "enabled",
    disabled: "disabled",

    add: "Add object to monitoring",

    emptyTitle: "Nothing is being monitored yet",
    emptyText:
      "Scan a wallet, contract, site or transaction and add it to monitoring.",

    noResultsTitle: "Nothing found",
    noResultsText: "Change your search or selected filter.",

    onlyActive: "Active only",
    onlyChanges: "Changes only",
    resetFilters: "Reset",
    refresh: "Refresh data",

    management: "Monitoring controls",
    notifyChanges: "Notify about risk changes",
    criticalOnly: "Critical events only",
    history: "Change history",
    noHistory: "No important changes yet.",

    recheck: "Check now",
    pause: "Pause",
    resume: "Resume",
    remove: "Remove",

    updated: "Done",
    removed: "Object removed from monitoring.",
    rechecked: "Object checked again.",
    errorMessage: "Monitoring could not be updated.",
  },
};

function langKey(value) {
  const key = String(value || "en").slice(0, 2).toLowerCase();
  return COPY[key] ? key : "en";
}

function textValue(value) {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function objectTarget(item) {
  return textValue(
    item?.target ||
      item?.normalizedTarget ||
      item?.normalized_target ||
      item?.input ||
      item?.address ||
      item?.url ||
      ""
  );
}

function normalizedKind(item) {
  const raw = String(
    item?.kind ||
      item?.type ||
      item?.objectType ||
      item?.object_type ||
      ""
  ).toLowerCase();

  const target = objectTarget(item).toLowerCase();

  if (
    raw.includes("transaction") ||
    raw === "tx" ||
    raw.includes("transaction_hash")
  ) {
    return "transaction";
  }

  if (
    raw.includes("contract") ||
    raw.includes("token") ||
    raw.includes("smart_contract")
  ) {
    return "contract";
  }

  if (
    raw.includes("wallet") ||
    raw.includes("address")
  ) {
    return "wallet";
  }

  if (
    raw.includes("url") ||
    raw.includes("site") ||
    raw.includes("domain") ||
    /^https?:\/\//i.test(target) ||
    /^www\./i.test(target)
  ) {
    return "site";
  }

  return "wallet";
}

function kindLabel(kind, t) {
  if (kind === "wallet") return t.wallet;
  if (kind === "contract") return t.contract;
  if (kind === "site") return t.site;
  if (kind === "transaction") return t.transaction;
  return t.object;
}

function kindIcon(kind) {
  if (kind === "wallet") return "wallet-outline";
  if (kind === "contract") return "document-text-outline";
  if (kind === "site") return "globe-outline";
  if (kind === "transaction") return "swap-horizontal-outline";
  return "shield-outline";
}

function shortValue(value, start = 13, end = 9) {
  const raw = textValue(value);

  if (!raw) return "—";

  if (raw.length <= start + end + 5) {
    return raw;
  }

  return `${raw.slice(0, start)}…${raw.slice(-end)}`;
}

function hostFromTarget(value) {
  const raw = textValue(value)
    .replace(/^https?:\/\//i, "")
    .replace(/^www\./i, "");

  return raw.split(/[/?#]/)[0] || raw;
}

function objectName(item, kind, t) {
  const explicit = textValue(
    item?.name ||
      item?.label ||
      item?.title ||
      item?.displayName ||
      item?.display_name
  );

  if (explicit) return explicit;

  const target = objectTarget(item);

  if (kind === "site") {
    return hostFromTarget(target) || t.site;
  }

  return kindLabel(kind, t);
}

function numberValue(...values) {
  for (const value of values) {
    const n = Number(value);

    if (Number.isFinite(n)) {
      return n;
    }
  }

  return 0;
}

function objectScore(item) {
  return Math.max(
    0,
    Math.min(
      100,
      numberValue(
        item?.score,
        item?.riskScore,
        item?.risk_score,
        item?.snapshot?.score,
        item?.snapshot?.risk_score,
        item?.result?.score,
        item?.scan?.score
      )
    )
  );
}

function lastCheckOf(item) {
  return (
    item?.lastCheckedAt ||
    item?.last_checked_at ||
    item?.updatedAt ||
    item?.updated_at ||
    null
  );
}

function checkCountOf(item) {
  const explicit = numberValue(
    item?.checkCount,
    item?.check_count,
    item?.checks,
    item?.checksCompleted,
    item?.checks_completed
  );

  if (explicit > 0) return explicit;

  return lastCheckOf(item) ? 1 : 0;
}

function changesCountOf(item) {
  const explicit = numberValue(
    item?.changesCount,
    item?.changes_count,
    item?.importantChanges,
    item?.important_changes,
    item?.changeCount,
    item?.change_count
  );

  if (explicit > 0) return explicit;

  const type = String(
    item?.lastEventType ||
      item?.last_event_type ||
      ""
  ).toLowerCase();

  if (
    type &&
    !type.includes("stable") &&
    !type.includes("unchanged")
  ) {
    return 1;
  }

  return 0;
}

function hasImportantChange(item) {
  return changesCountOf(item) > 0;
}

function alertSettingsOf(item) {
  return (
    item?.alertSettings ||
    item?.alert_settings ||
    {}
  );
}

function lastErrorOf(item) {
  return textValue(
    item?.lastError ||
      item?.last_error
  );
}

function formatCheckTime(value, lang, t) {
  if (!value) return t.never;

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return t.never;
  }

  const diff = Date.now() - date.getTime();

  if (diff >= 0 && diff < 90 * 1000) {
    return t.now;
  }

  const locale =
    lang === "ru"
      ? "ru-RU"
      : lang === "uk"
      ? "uk-UA"
      : "en-US";

  try {
    return date.toLocaleString(locale, {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return date.toLocaleString();
  }
}

function statusFor(item, t) {
  const score = objectScore(item);
  const lastCheck = lastCheckOf(item);

  if (item?.paused) {
    return {
      key: "paused",
      label: t.paused,
      color: C.dim,
      bg: "rgba(116,132,155,0.13)",
      icon: "pause-circle",
    };
  }

  if (lastErrorOf(item)) {
    return {
      key: "error",
      label: t.error,
      color: C.red,
      bg: C.redSoft,
      icon: "alert-circle",
    };
  }

  if (score >= 80) {
    return {
      key: "danger",
      label: t.danger,
      color: C.red,
      bg: C.redSoft,
      icon: "warning",
    };
  }

  if (hasImportantChange(item)) {
    return {
      key: "changed",
      label: t.changed,
      color: C.red,
      bg: C.redSoft,
      icon: "alert-circle",
    };
  }

  if (score >= 50) {
    return {
      key: "warning",
      label: t.warning,
      color: C.amber,
      bg: C.amberSoft,
      icon: "warning",
    };
  }

  if (!lastCheck) {
    return {
      key: "checking",
      label: t.checking,
      color: C.orange,
      bg: C.orangeSoft,
      icon: "time",
    };
  }

  return {
    key: "safe",
    label: t.safe,
    color: C.green,
    bg: C.greenSoft,
    icon: "shield-checkmark",
  };
}

function riskColor(score) {
  if (score >= 80) return C.red;
  if (score >= 50) return C.amber;
  return C.green;
}

function StatCard({
  icon,
  iconColor,
  iconBg,
  value,
  label,
}) {
  return (
    <View style={styles.statCard}>
      <View
        style={[
          styles.statIcon,
          { backgroundColor: iconBg },
        ]}
      >
        <Ionicons
          name={icon}
          size={18}
          color={iconColor}
        />
      </View>

      <Text style={styles.statValue}>
        {value}
      </Text>

      <Text style={styles.statLabel}>
        {label}
      </Text>
    </View>
  );
}

function Metric({
  label,
  value,
  valueColor,
}) {
  return (
    <View style={styles.metric}>
      <Text
        style={styles.metricLabel}
        numberOfLines={1}
      >
        {label}
      </Text>

      <Text
        style={[
          styles.metricValue,
          valueColor
            ? { color: valueColor }
            : null,
        ]}
        numberOfLines={1}
      >
        {value}
      </Text>
    </View>
  );
}

export default function TrackingScreen() {
  const { watchId } = useLocalSearchParams();
  const { i18n } = useTranslation();

  const refreshMe = useAuthStore(
    (state) => state.refreshMe
  );

  const lang = langKey(i18n?.language);
  const t = COPY[lang];

  const [items, setItems] = useState([]);
  const [events, setEvents] = useState({});

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] =
    useState(false);

  const [busyId, setBusyId] = useState(null);
  const [expanded, setExpanded] =
    useState(null);

  const [query, setQuery] = useState("");
  const [kindFilter, setKindFilter] =
    useState("all");

  const [filterOpen, setFilterOpen] =
    useState(false);

  const [settingsOpen, setSettingsOpen] =
    useState(false);

  const [onlyActive, setOnlyActive] =
    useState(false);

  const [onlyChanges, setOnlyChanges] =
    useState(false);

  const [redirecting, setRedirecting] =
    useState(false);

  const requestWithRecovery = useCallback(
    async (makeRequest) => {
      let response = await makeRequest();

      if (response.status === 401) {
        const restored =
          await refreshMe().catch(() => null);

        if (restored) {
          response = await makeRequest();
        }
      }

      if (response.status === 402) {
        const restored =
          await refreshMe().catch(() => null);

        if (
          restored?.proAccess?.isPro === true
        ) {
          response = await makeRequest();
        }
      }

      return response;
    },
    [refreshMe]
  );

  const handleBlocked = useCallback(
    (response) => {
      if (response.status === 401) {
        setRedirecting(true);
        router.replace("/profile");
        return true;
      }

      if (response.status === 402) {
        setRedirecting(true);
        router.replace("/pro");
        return true;
      }

      return false;
    },
    []
  );

  const load = useCallback(
    async (soft = false) => {
      if (!soft) {
        setLoading(true);
      }

      try {
        const makeRequest = () =>
          authenticatedFetch(
            `${BACKEND}/workspace/watches?lang=${encodeURIComponent(
              lang
            )}`,
            {
              headers: {
                "Content-Type":
                  "application/json",
              },
            }
          );

        const response =
          await requestWithRecovery(makeRequest);

        if (handleBlocked(response)) {
          setItems([]);
          return;
        }

        const payload =
          await response
            .json()
            .catch(() => ({}));

        if (
          !response.ok ||
          !payload?.ok
        ) {
          throw new Error(
            payload?.detail?.message ||
              payload?.message ||
              t.errorMessage
          );
        }

        setItems(
          Array.isArray(payload?.items)
            ? payload.items
            : []
        );
      } catch (error) {
        showAppAlert(
          t.error,
          error?.message || t.errorMessage
        );
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [
      handleBlocked,
      lang,
      requestWithRecovery,
      t.error,
      t.errorMessage,
    ]
  );

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const selected = Number(watchId);

    if (
      selected > 0 &&
      items.some(
        (item) =>
          Number(item?.id) === selected
      )
    ) {
      setExpanded(selected);
    }
  }, [items, watchId]);

  const stats = useMemo(() => {
    const active = items.filter(
      (item) => !item?.paused
    ).length;

    const checks = items.reduce(
      (sum, item) =>
        sum + checkCountOf(item),
      0
    );

    const changes = items.reduce(
      (sum, item) =>
        sum + changesCountOf(item),
      0
    );

    return {
      active,
      checks,
      changes,
    };
  }, [items]);

  const filteredItems = useMemo(() => {
    const normalizedQuery = query
      .trim()
      .toLowerCase();

    return items.filter((item) => {
      const kind = normalizedKind(item);

      if (
        kindFilter !== "all" &&
        kind !== kindFilter
      ) {
        return false;
      }

      if (
        onlyActive &&
        item?.paused
      ) {
        return false;
      }

      if (
        onlyChanges &&
        !hasImportantChange(item)
      ) {
        return false;
      }

      if (!normalizedQuery) {
        return true;
      }

      const haystack = [
        objectName(item, kind, t),
        objectTarget(item),
        kindLabel(kind, t),
        item?.lastEventSummary,
        item?.last_event_summary,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return haystack.includes(
        normalizedQuery
      );
    });
  }, [
    items,
    kindFilter,
    onlyActive,
    onlyChanges,
    query,
    t,
  ]);

  async function patchWatch(
    item,
    body,
    successText = ""
  ) {
    const id = item?.id;

    if (!id) return;

    setBusyId(id);

    try {
      const makeRequest = () =>
        authenticatedFetch(
          `${BACKEND}/workspace/watches/${id}?lang=${encodeURIComponent(
            lang
          )}`,
          {
            method: "PATCH",
            headers: {
              "Content-Type":
                "application/json",
            },
            body: JSON.stringify({
              ...body,
              lang,
            }),
          }
        );

      const response =
        await requestWithRecovery(makeRequest);

      if (handleBlocked(response)) {
        return;
      }

      const payload =
        await response
          .json()
          .catch(() => ({}));

      if (
        !response.ok ||
        !payload?.ok
      ) {
        throw new Error(
          payload?.detail?.message ||
            payload?.message ||
            t.errorMessage
        );
      }

      if (payload?.item) {
        setItems((current) =>
          current.map((row) =>
            String(row?.id) ===
            String(payload.item?.id)
              ? payload.item
              : row
          )
        );
      }

      if (successText) {
        showAppAlert(
          t.updated,
          payload?.message ||
            successText
        );
      }
    } catch (error) {
      showAppAlert(
        t.error,
        error?.message ||
          t.errorMessage
      );
    } finally {
      setBusyId(null);
    }
  }

  async function recheck(item) {
    const id = item?.id;

    if (!id) return;

    setBusyId(id);

    try {
      const makeRequest = () =>
        authenticatedFetch(
          `${BACKEND}/workspace/watches/${id}/recheck`,
          {
            method: "POST",
            headers: {
              "Content-Type":
                "application/json",
            },
            body: JSON.stringify({
              lang,
            }),
          }
        );

      const response =
        await requestWithRecovery(makeRequest);

      if (handleBlocked(response)) {
        return;
      }

      const payload =
        await response
          .json()
          .catch(() => ({}));

      if (
        !response.ok ||
        !payload?.ok
      ) {
        throw new Error(
          payload?.detail?.message ||
            payload?.message ||
            t.errorMessage
        );
      }

      if (payload?.item) {
        setItems((current) =>
          current.map((row) =>
            String(row?.id) ===
            String(payload.item?.id)
              ? payload.item
              : row
          )
        );
      } else {
        await load(true);
      }

      showAppAlert(
        t.updated,
        payload?.message ||
          t.rechecked
      );
    } catch (error) {
      showAppAlert(
        t.error,
        error?.message ||
          t.errorMessage
      );
    } finally {
      setBusyId(null);
    }
  }

  async function loadEvents(item) {
    const id = item?.id;

    if (!id || events[id]) {
      return;
    }

    try {
      const makeRequest = () =>
        authenticatedFetch(
          `${BACKEND}/workspace/watches/${id}/events?lang=${encodeURIComponent(
            lang
          )}`,
          {
            headers: {
              "Content-Type":
                "application/json",
            },
          }
        );

      const response =
        await requestWithRecovery(makeRequest);

      if (handleBlocked(response)) {
        return;
      }

      const payload =
        await response
          .json()
          .catch(() => ({}));

      setEvents((current) => ({
        ...current,
        [id]: Array.isArray(
          payload?.items
        )
          ? payload.items
          : [],
      }));
    } catch {
      setEvents((current) => ({
        ...current,
        [id]: [],
      }));
    }
  }

  async function toggleExpanded(item) {
    const id = Number(item?.id);

    if (!id) return;

    if (expanded === id) {
      setExpanded(null);
      return;
    }

    setExpanded(id);
    await loadEvents(item);
  }

  async function removeWatch(item) {
    const id = item?.id;

    if (!id) return;

    setBusyId(id);

    try {
      const makeRequest = () =>
        authenticatedFetch(
          `${BACKEND}/workspace/watches/${id}?lang=${encodeURIComponent(
            lang
          )}`,
          {
            method: "DELETE",
            headers: {
              "Content-Type":
                "application/json",
            },
          }
        );

      const response =
        await requestWithRecovery(makeRequest);

      if (handleBlocked(response)) {
        return;
      }

      const payload =
        await response
          .json()
          .catch(() => ({}));

      if (
        !response.ok ||
        !payload?.ok
      ) {
        throw new Error(
          payload?.detail?.message ||
            payload?.message ||
            t.errorMessage
        );
      }

      setItems((current) =>
        current.filter(
          (row) =>
            String(row?.id) !==
            String(id)
        )
      );

      setExpanded(null);

      showAppAlert(
        t.updated,
        t.removed
      );
    } catch (error) {
      showAppAlert(
        t.error,
        error?.message ||
          t.errorMessage
      );
    } finally {
      setBusyId(null);
    }
  }

  function resetFilters() {
    setKindFilter("all");
    setOnlyActive(false);
    setOnlyChanges(false);
    setQuery("");
  }

  if (redirecting) {
    return (
      <LinearGradient
        colors={[
          C.bgTop,
          C.bgMid,
          C.bgBottom,
        ]}
        style={styles.background}
      >
        <SafeAreaView style={styles.safe}>
          <View style={styles.fullLoader}>
            <ActivityIndicator
              size="large"
              color={C.orange}
            />
          </View>
        </SafeAreaView>
      </LinearGradient>
    );
  }

  const tabs = [
    {
      key: "all",
      label: t.all,
    },
    {
      key: "wallet",
      label: t.wallets,
    },
    {
      key: "contract",
      label: t.contracts,
    },
    {
      key: "site",
      label: t.sites,
    },
    {
      key: "transaction",
      label: t.transactions,
    },
  ];

  return (
    <LinearGradient
      colors={[
        C.bgTop,
        C.bgMid,
        C.bgBottom,
      ]}
      locations={[0, 0.42, 1]}
      style={styles.background}
    >
      <SafeAreaView
        style={styles.safe}
        edges={["top"]}
      >
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={
            styles.container
          }
          showsVerticalScrollIndicator={
            false
          }
          keyboardShouldPersistTaps="handled"
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              tintColor={C.orange}
              colors={[C.orange]}
              onRefresh={() => {
                setRefreshing(true);
                load(true);
              }}
            />
          }
        >
          <View style={styles.header}>
            <View style={styles.headerCopy}>
              <Text style={styles.title}>
                {t.title}
              </Text>

              <Text
                style={styles.subtitle}
              >
                {t.subtitle}
              </Text>
            </View>

            <Pressable
              onPress={() =>
                setSettingsOpen(
                  (value) => !value
                )
              }
              style={({ pressed }) => [
                styles.settingsButton,
                pressed &&
                  styles.pressed,
              ]}
            >
              <Ionicons
                name="settings-outline"
                size={22}
                color={C.text}
              />
            </Pressable>
          </View>

          {settingsOpen ? (
            <View
              style={
                styles.settingsPanel
              }
            >
              <View
                style={
                  styles.settingsPanelTop
                }
              >
                <View>
                  <Text
                    style={
                      styles.settingsTitle
                    }
                  >
                    {t.management}
                  </Text>

                  <Text
                    style={
                      styles.settingsHint
                    }
                  >
                    {t.filters}
                  </Text>
                </View>

                <Pressable
                  style={
                    styles.smallIconButton
                  }
                  onPress={() =>
                    setSettingsOpen(false)
                  }
                >
                  <Ionicons
                    name="close"
                    size={19}
                    color={C.text2}
                  />
                </Pressable>
              </View>

              <Pressable
                style={styles.settingsRow}
                onPress={() =>
                  setOnlyActive(
                    (value) => !value
                  )
                }
              >
                <View
                  style={
                    styles.settingsRowCopy
                  }
                >
                  <Ionicons
                    name="shield-checkmark-outline"
                    size={19}
                    color={C.green}
                  />
                  <Text
                    style={
                      styles.settingsRowText
                    }
                  >
                    {t.onlyActive}
                  </Text>
                </View>

                <Switch
                  value={onlyActive}
                  onValueChange={
                    setOnlyActive
                  }
                  thumbColor={
                    onlyActive
                      ? C.orange
                      : "#8A95A4"
                  }
                  trackColor={{
                    false: "#273448",
                    true: "#684917",
                  }}
                />
              </Pressable>

              <Pressable
                style={styles.settingsRow}
                onPress={() =>
                  setOnlyChanges(
                    (value) => !value
                  )
                }
              >
                <View
                  style={
                    styles.settingsRowCopy
                  }
                >
                  <Ionicons
                    name="warning-outline"
                    size={19}
                    color={C.red}
                  />
                  <Text
                    style={
                      styles.settingsRowText
                    }
                  >
                    {t.onlyChanges}
                  </Text>
                </View>

                <Switch
                  value={onlyChanges}
                  onValueChange={
                    setOnlyChanges
                  }
                  thumbColor={
                    onlyChanges
                      ? C.orange
                      : "#8A95A4"
                  }
                  trackColor={{
                    false: "#273448",
                    true: "#684917",
                  }}
                />
              </Pressable>

              <Pressable
                style={
                  styles.refreshButton
                }
                onPress={() => {
                  setRefreshing(true);
                  load(true);
                }}
              >
                <Ionicons
                  name="refresh"
                  size={18}
                  color={C.orange}
                />

                <Text
                  style={
                    styles.refreshButtonText
                  }
                >
                  {t.refresh}
                </Text>
              </Pressable>
            </View>
          ) : null}

          <View style={styles.searchRow}>
            <View
              style={
                styles.searchContainer
              }
            >
              <Ionicons
                name="search-outline"
                size={20}
                color={C.dim}
              />

              <TextInput
                value={query}
                onChangeText={setQuery}
                placeholder={t.search}
                placeholderTextColor={
                  C.dim
                }
                style={styles.searchInput}
                autoCapitalize="none"
                autoCorrect={false}
                selectionColor={C.orange}
              />

              {!!query ? (
                <Pressable
                  onPress={() =>
                    setQuery("")
                  }
                  hitSlop={12}
                >
                  <Ionicons
                    name="close-circle"
                    size={18}
                    color={C.dim}
                  />
                </Pressable>
              ) : null}
            </View>

            <Pressable
              onPress={() =>
                setFilterOpen(
                  (value) => !value
                )
              }
              style={({ pressed }) => [
                styles.filterButton,
                filterOpen &&
                  styles.filterButtonActive,
                pressed &&
                  styles.pressed,
              ]}
            >
              <Ionicons
                name="options-outline"
                size={19}
                color={
                  filterOpen
                    ? "#07101D"
                    : C.text
                }
              />

              <Text
                style={[
                  styles.filterButtonText,
                  filterOpen &&
                    styles.filterButtonTextActive,
                ]}
              >
                {t.filters}
              </Text>
            </Pressable>
          </View>

          {filterOpen ? (
            <View style={styles.quickFilters}>
              <Pressable
                onPress={() =>
                  setOnlyChanges(
                    (value) => !value
                  )
                }
                style={[
                  styles.quickFilter,
                  onlyChanges &&
                    styles.quickFilterActive,
                ]}
              >
                <Ionicons
                  name="alert-circle-outline"
                  size={17}
                  color={
                    onlyChanges
                      ? "#07101D"
                      : C.red
                  }
                />

                <Text
                  style={[
                    styles.quickFilterText,
                    onlyChanges &&
                      styles.quickFilterTextActive,
                  ]}
                >
                  {t.onlyChanges}
                </Text>
              </Pressable>

              <Pressable
                onPress={() =>
                  setOnlyActive(
                    (value) => !value
                  )
                }
                style={[
                  styles.quickFilter,
                  onlyActive &&
                    styles.quickFilterActive,
                ]}
              >
                <Ionicons
                  name="shield-checkmark-outline"
                  size={17}
                  color={
                    onlyActive
                      ? "#07101D"
                      : C.green
                  }
                />

                <Text
                  style={[
                    styles.quickFilterText,
                    onlyActive &&
                      styles.quickFilterTextActive,
                  ]}
                >
                  {t.onlyActive}
                </Text>
              </Pressable>

              {(onlyActive ||
                onlyChanges ||
                query ||
                kindFilter !==
                  "all") ? (
                <Pressable
                  onPress={resetFilters}
                  style={
                    styles.resetFilter
                  }
                >
                  <Text
                    style={
                      styles.resetFilterText
                    }
                  >
                    {t.resetFilters}
                  </Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}

          <View style={styles.statsRow}>
            <StatCard
              icon="shield-checkmark"
              iconColor={C.green}
              iconBg={C.greenSoft}
              value={stats.active}
              label={t.activeObjects}
            />

            <StatCard
              icon="time"
              iconColor={C.orange}
              iconBg={C.orangeSoft}
              value={stats.checks}
              label={t.completedChecks}
            />

            <StatCard
              icon="warning"
              iconColor={C.red}
              iconBg={C.redSoft}
              value={stats.changes}
              label={
                t.importantChanges
              }
            />
          </View>

          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={
              false
            }
            contentContainerStyle={
              styles.tabsContent
            }
            style={styles.tabs}
          >
            {tabs.map((tab) => {
              const active =
                kindFilter === tab.key;

              return (
                <Pressable
                  key={tab.key}
                  onPress={() =>
                    setKindFilter(
                      tab.key
                    )
                  }
                  style={[
                    styles.tab,
                    active &&
                      styles.tabActive,
                  ]}
                >
                  <Text
                    style={[
                      styles.tabText,
                      active &&
                        styles.tabTextActive,
                    ]}
                  >
                    {tab.label}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>

          {loading &&
          items.length === 0 ? (
            <View style={styles.loader}>
              <ActivityIndicator
                size="large"
                color={C.orange}
              />

              <Text
                style={styles.loaderText}
              >
                {t.checking}
              </Text>
            </View>
          ) : filteredItems.length ===
            0 ? (
            <View style={styles.emptyCard}>
              <View
                style={
                  styles.emptyIcon
                }
              >
                <Ionicons
                  name={
                    items.length
                      ? "search-outline"
                      : "eye-outline"
                  }
                  size={29}
                  color={C.orange}
                />
              </View>

              <Text
                style={
                  styles.emptyTitle
                }
              >
                {items.length
                  ? t.noResultsTitle
                  : t.emptyTitle}
              </Text>

              <Text
                style={
                  styles.emptyText
                }
              >
                {items.length
                  ? t.noResultsText
                  : t.emptyText}
              </Text>
            </View>
          ) : (
            <View style={styles.cards}>
              {filteredItems.map(
                (item) => {
                  const id = Number(
                    item?.id
                  );

                  const kind =
                    normalizedKind(item);

                  const score =
                    objectScore(item);

                  const status =
                    statusFor(item, t);

                  const target =
                    objectTarget(item);

                  const name =
                    objectName(
                      item,
                      kind,
                      t
                    );

                  const alerts =
                    alertSettingsOf(
                      item
                    );

                  const alertsOn =
                    alerts?.risk_change !==
                    false;

                  const criticalOnly =
                    Boolean(
                      alerts?.critical_only
                    );

                  const isExpanded =
                    expanded === id;

                  const isBusy =
                    String(busyId) ===
                    String(item?.id);

                  const itemEvents =
                    events[item?.id] ||
                    [];

                  return (
                    <View
                      key={String(
                        item?.id ||
                          target
                      )}
                      style={[
                        styles.watchCard,
                        status.key ===
                          "danger" && {
                          borderColor:
                            "rgba(255,83,100,0.32)",
                        },
                        status.key ===
                          "changed" && {
                          borderColor:
                            "rgba(255,83,100,0.28)",
                        },
                      ]}
                    >
                      <Pressable
                        onPress={() =>
                          toggleExpanded(
                            item
                          )
                        }
                        style={({ pressed }) => [
                          styles.cardPressable,
                          pressed && {
                            opacity: 0.93,
                          },
                        ]}
                      >
                        <View
                          style={
                            styles.cardHeader
                          }
                        >
                          <View
                            style={[
                              styles.objectIcon,
                              {
                                backgroundColor:
                                  status.bg,
                              },
                            ]}
                          >
                            <Ionicons
                              name={kindIcon(
                                kind
                              )}
                              size={22}
                              color={
                                status.color
                              }
                            />
                          </View>

                          <View
                            style={
                              styles.objectMain
                            }
                          >
                            <Text
                              style={
                                styles.objectName
                              }
                              numberOfLines={1}
                            >
                              {name}
                            </Text>

                            <View
                              style={
                                styles.objectMetaRow
                              }
                            >
                              <Text
                                style={
                                  styles.objectKind
                                }
                              >
                                {kindLabel(
                                  kind,
                                  t
                                )}
                              </Text>

                              <View
                                style={
                                  styles.metaDot
                                }
                              />

                              <Text
                                numberOfLines={
                                  1
                                }
                                style={
                                  styles.objectTarget
                                }
                              >
                                {shortValue(
                                  target,
                                  kind ===
                                    "site"
                                    ? 24
                                    : 12,
                                  kind ===
                                    "site"
                                    ? 0
                                    : 8
                                )}
                              </Text>
                            </View>
                          </View>

                          <View
                            style={[
                              styles.statusBadge,
                              {
                                backgroundColor:
                                  status.bg,
                              },
                            ]}
                          >
                            <Ionicons
                              name={
                                status.icon
                              }
                              size={13}
                              color={
                                status.color
                              }
                            />

                            <Text
                              style={[
                                styles.statusText,
                                {
                                  color:
                                    status.color,
                                },
                              ]}
                              numberOfLines={1}
                            >
                              {
                                status.label
                              }
                            </Text>
                          </View>
                        </View>

                        <View
                          style={
                            styles.riskBlock
                          }
                        >
                          <View
                            style={
                              styles.riskTop
                            }
                          >
                            <Text
                              style={
                                styles.riskLabel
                              }
                            >
                              {t.risk}
                            </Text>

                            <Text
                              style={[
                                styles.riskValue,
                                {
                                  color:
                                    riskColor(
                                      score
                                    ),
                                },
                              ]}
                            >
                              {score}/100
                            </Text>
                          </View>

                          <View
                            style={
                              styles.riskTrack
                            }
                          >
                            <View
                              style={[
                                styles.riskFill,
                                {
                                  width: `${score}%`,
                                  backgroundColor:
                                    riskColor(
                                      score
                                    ),
                                },
                              ]}
                            />
                          </View>
                        </View>

                        <View
                          style={
                            styles.metricsRow
                          }
                        >
                          <Metric
                            label={
                              t.lastCheck
                            }
                            value={formatCheckTime(
                              lastCheckOf(
                                item
                              ),
                              lang,
                              t
                            )}
                          />

                          <View
                            style={
                              styles.metricDivider
                            }
                          />

                          <Metric
                            label={
                              t.changes
                            }
                            value={String(
                              changesCountOf(
                                item
                              )
                            )}
                            valueColor={
                              hasImportantChange(
                                item
                              )
                                ? C.red
                                : C.text
                            }
                          />

                          <View
                            style={
                              styles.metricDivider
                            }
                          />

                          <Metric
                            label={
                              t.alerts
                            }
                            value={
                              alertsOn
                                ? t.enabled
                                : t.disabled
                            }
                            valueColor={
                              alertsOn
                                ? C.green
                                : C.dim
                            }
                          />
                        </View>

                        <View
                          style={
                            styles.expandRow
                          }
                        >
                          <View
                            style={
                              styles.protectedDotRow
                            }
                          >
                            <View
                              style={[
                                styles.liveDot,
                                {
                                  backgroundColor:
                                    item?.paused
                                      ? C.dim
                                      : C.green,
                                },
                              ]}
                            />

                            <Text
                              style={
                                styles.liveText
                              }
                            >
                              24/7
                            </Text>
                          </View>

                          <Ionicons
                            name={
                              isExpanded
                                ? "chevron-up"
                                : "chevron-down"
                            }
                            size={18}
                            color={C.dim}
                          />
                        </View>
                      </Pressable>

                      {isExpanded ? (
                        <View
                          style={
                            styles.expanded
                          }
                        >
                          <View
                            style={
                              styles.expandedDivider
                            }
                          />

                          <Text
                            style={
                              styles.expandedTitle
                            }
                          >
                            {t.management}
                          </Text>

                          <View
                            style={
                              styles.controlRow
                            }
                          >
                            <View
                              style={
                                styles.controlCopy
                              }
                            >
                              <Text
                                style={
                                  styles.controlTitle
                                }
                              >
                                {
                                  t.notifyChanges
                                }
                              </Text>
                            </View>

                            <Switch
                              value={
                                alertsOn
                              }
                              onValueChange={() =>
                                patchWatch(
                                  item,
                                  {
                                    alertSettings:
                                      {
                                        ...alerts,
                                        risk_change:
                                          !alertsOn,
                                      },
                                  }
                                )
                              }
                              thumbColor={
                                alertsOn
                                  ? C.orange
                                  : "#8A95A4"
                              }
                              trackColor={{
                                false:
                                  "#273448",
                                true:
                                  "#684917",
                              }}
                            />
                          </View>

                          <View
                            style={
                              styles.controlRow
                            }
                          >
                            <View
                              style={
                                styles.controlCopy
                              }
                            >
                              <Text
                                style={
                                  styles.controlTitle
                                }
                              >
                                {
                                  t.criticalOnly
                                }
                              </Text>
                            </View>

                            <Switch
                              value={
                                criticalOnly
                              }
                              onValueChange={() =>
                                patchWatch(
                                  item,
                                  {
                                    alertSettings:
                                      {
                                        ...alerts,
                                        critical_only:
                                          !criticalOnly,
                                      },
                                  }
                                )
                              }
                              thumbColor={
                                criticalOnly
                                  ? C.orange
                                  : "#8A95A4"
                              }
                              trackColor={{
                                false:
                                  "#273448",
                                true:
                                  "#684917",
                              }}
                            />
                          </View>

                          <View
                            style={
                              styles.actionGrid
                            }
                          >
                            <Pressable
                              disabled={
                                isBusy
                              }
                              onPress={() =>
                                recheck(item)
                              }
                              style={({ pressed }) => [
                                styles.actionButton,
                                pressed &&
                                  styles.pressed,
                              ]}
                            >
                              {isBusy ? (
                                <ActivityIndicator
                                  size="small"
                                  color={
                                    C.orange
                                  }
                                />
                              ) : (
                                <Ionicons
                                  name="refresh"
                                  size={18}
                                  color={
                                    C.orange
                                  }
                                />
                              )}

                              <Text
                                style={
                                  styles.actionText
                                }
                              >
                                {
                                  t.recheck
                                }
                              </Text>
                            </Pressable>

                            <Pressable
                              disabled={
                                isBusy
                              }
                              onPress={() =>
                                patchWatch(
                                  item,
                                  {
                                    paused:
                                      !item?.paused,
                                  }
                                )
                              }
                              style={({ pressed }) => [
                                styles.actionButton,
                                pressed &&
                                  styles.pressed,
                              ]}
                            >
                              <Ionicons
                                name={
                                  item?.paused
                                    ? "play"
                                    : "pause"
                                }
                                size={18}
                                color={
                                  C.text2
                                }
                              />

                              <Text
                                style={
                                  styles.actionText
                                }
                              >
                                {item?.paused
                                  ? t.resume
                                  : t.pause}
                              </Text>
                            </Pressable>
                          </View>

                          <View
                            style={
                              styles.history
                            }
                          >
                            <View
                              style={
                                styles.historyTitleRow
                              }
                            >
                              <Ionicons
                                name="time-outline"
                                size={17}
                                color={
                                  C.text2
                                }
                              />

                              <Text
                                style={
                                  styles.historyTitle
                                }
                              >
                                {t.history}
                              </Text>
                            </View>

                            {itemEvents.length ? (
                              itemEvents
                                .slice(0, 4)
                                .map(
                                  (
                                    event,
                                    index
                                  ) => (
                                    <View
                                      key={String(
                                        event?.id ||
                                          index
                                      )}
                                      style={
                                        styles.historyItem
                                      }
                                    >
                                      <View
                                        style={
                                          styles.historyDot
                                        }
                                      />

                                      <View
                                        style={
                                          styles.historyCopy
                                        }
                                      >
                                        <Text
                                          style={
                                            styles.historySummary
                                          }
                                        >
                                          {textValue(
                                            event?.summary ||
                                              event?.message ||
                                              event?.eventType ||
                                              event?.event_type
                                          ) ||
                                            t.changed}
                                        </Text>

                                        <Text
                                          style={
                                            styles.historyTime
                                          }
                                        >
                                          {formatCheckTime(
                                            event?.createdAt ||
                                              event?.created_at,
                                            lang,
                                            t
                                          )}
                                        </Text>
                                      </View>
                                    </View>
                                  )
                                )
                            ) : (
                              <Text
                                style={
                                  styles.noHistory
                                }
                              >
                                {t.noHistory}
                              </Text>
                            )}
                          </View>

                          <Pressable
                            disabled={
                              isBusy
                            }
                            onPress={() =>
                              removeWatch(
                                item
                              )
                            }
                            style={({ pressed }) => [
                              styles.removeButton,
                              pressed &&
                                styles.pressed,
                            ]}
                          >
                            <Ionicons
                              name="trash-outline"
                              size={18}
                              color={C.red}
                            />

                            <Text
                              style={
                                styles.removeText
                              }
                            >
                              {t.remove}
                            </Text>
                          </Pressable>
                        </View>
                      ) : null}
                    </View>
                  );
                }
              )}
            </View>
          )}

          <Pressable
            onPress={() =>
              router.push("/")
            }
            style={({ pressed }) => [
              styles.addButton,
              pressed &&
                styles.addButtonPressed,
            ]}
          >
            <Ionicons
              name="add"
              size={22}
              color={C.orange}
            />

            <Text
              style={
                styles.addButtonText
              }
            >
              {t.add}
            </Text>
          </Pressable>

          <View style={styles.bottomSpace} />
        </ScrollView>
      </SafeAreaView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  background: {
    flex: 1,
  },

  safe: {
    flex: 1,
  },

  scroll: {
    flex: 1,
  },

  container: {
    paddingHorizontal: 18,
    paddingTop: 8,
    paddingBottom: 22,
  },

  header: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 14,
  },

  headerCopy: {
    flex: 1,
    paddingRight: 2,
  },

  title: {
    color: C.orange,
    fontSize: 33,
    lineHeight: 38,
    fontWeight: "900",
    letterSpacing: -0.8,
  },

  subtitle: {
    marginTop: 8,
    color: C.text2,
    fontSize: 13.5,
    lineHeight: 19,
    fontWeight: "600",
    maxWidth: 320,
  },

  settingsButton: {
    width: 44,
    height: 44,
    borderRadius: 14,
    backgroundColor: C.panel2,
    borderWidth: 1,
    borderColor: C.line,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 1,
  },

  settingsPanel: {
    marginTop: 14,
    padding: 15,
    borderRadius: 18,
    backgroundColor: C.panel,
    borderWidth: 1,
    borderColor: C.line,
  },

  settingsPanelTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 8,
  },

  settingsTitle: {
    color: C.text,
    fontSize: 15,
    fontWeight: "900",
  },

  settingsHint: {
    color: C.dim,
    fontSize: 11.5,
    fontWeight: "700",
    marginTop: 3,
  },

  smallIconButton: {
    width: 34,
    height: 34,
    borderRadius: 11,
    backgroundColor: C.panel2,
    alignItems: "center",
    justifyContent: "center",
  },

  settingsRow: {
    minHeight: 50,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderTopWidth: 1,
    borderTopColor: C.lineSoft,
  },

  settingsRowCopy: {
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    flex: 1,
    paddingRight: 12,
  },

  settingsRowText: {
    color: C.text2,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: "700",
    flex: 1,
  },

  refreshButton: {
    marginTop: 8,
    height: 43,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: "rgba(255,170,24,0.30)",
    backgroundColor: C.orangeSoft,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },

  refreshButtonText: {
    color: C.orange,
    fontSize: 13,
    fontWeight: "900",
  },

  searchRow: {
    marginTop: 23,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },

  searchContainer: {
    flex: 1,
    height: 48,
    borderRadius: 15,
    backgroundColor: C.panel,
    borderWidth: 1,
    borderColor: C.line,
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    gap: 9,
  },

  searchInput: {
    flex: 1,
    height: "100%",
    color: C.text,
    fontSize: 13.5,
    fontWeight: "600",
    paddingVertical: 0,
  },

  filterButton: {
    height: 48,
    minWidth: 111,
    borderRadius: 15,
    backgroundColor: C.panel,
    borderWidth: 1,
    borderColor: C.line,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    paddingHorizontal: 13,
  },

  filterButtonActive: {
    backgroundColor: C.orange,
    borderColor: C.orange,
  },

  filterButtonText: {
    color: C.text,
    fontSize: 13,
    fontWeight: "800",
  },

  filterButtonTextActive: {
    color: "#07101D",
  },

  quickFilters: {
    marginTop: 10,
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 8,
  },

  quickFilter: {
    minHeight: 36,
    paddingHorizontal: 11,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: C.line,
    backgroundColor: C.panel,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },

  quickFilterActive: {
    backgroundColor: C.orange,
    borderColor: C.orange,
  },

  quickFilterText: {
    color: C.text2,
    fontSize: 11.5,
    fontWeight: "800",
  },

  quickFilterTextActive: {
    color: "#07101D",
  },

  resetFilter: {
    minHeight: 36,
    justifyContent: "center",
    paddingHorizontal: 8,
  },

  resetFilterText: {
    color: C.dim,
    fontSize: 11.5,
    fontWeight: "800",
  },

  statsRow: {
    marginTop: 18,
    flexDirection: "row",
    gap: 9,
  },

  statCard: {
    flex: 1,
    minHeight: 105,
    borderRadius: 17,
    borderWidth: 1,
    borderColor: C.line,
    backgroundColor: C.panel,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 6,
    paddingVertical: 11,
  },

  statIcon: {
    width: 31,
    height: 31,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 5,
  },

  statValue: {
    color: C.text,
    fontSize: 22,
    lineHeight: 25,
    fontWeight: "900",
    letterSpacing: -0.4,
  },

  statLabel: {
    marginTop: 3,
    color: C.dim,
    fontSize: 10.3,
    lineHeight: 13.5,
    fontWeight: "700",
    textAlign: "center",
  },

  tabs: {
    marginTop: 18,
    marginHorizontal: -18,
  },

  tabsContent: {
    paddingHorizontal: 18,
    gap: 8,
  },

  tab: {
    minHeight: 38,
    paddingHorizontal: 15,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: C.line,
    backgroundColor: C.panel,
    alignItems: "center",
    justifyContent: "center",
  },

  tabActive: {
    backgroundColor: C.orange,
    borderColor: C.orange,
  },

  tabText: {
    color: C.text2,
    fontSize: 12.5,
    fontWeight: "800",
  },

  tabTextActive: {
    color: "#07101D",
  },

  loader: {
    minHeight: 260,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
  },

  loaderText: {
    color: C.dim,
    fontSize: 13,
    fontWeight: "700",
  },

  cards: {
    marginTop: 15,
    gap: 12,
  },

  watchCard: {
    overflow: "hidden",
    borderRadius: 19,
    borderWidth: 1,
    borderColor: C.line,
    backgroundColor: C.panel,
  },

  cardPressable: {
    paddingHorizontal: 15,
    paddingTop: 15,
    paddingBottom: 10,
  },

  cardHeader: {
    flexDirection: "row",
    alignItems: "center",
  },

  objectIcon: {
    width: 45,
    height: 45,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 11,
  },

  objectMain: {
    flex: 1,
    minWidth: 0,
  },

  objectName: {
    color: C.text,
    fontSize: 16,
    lineHeight: 20,
    fontWeight: "900",
    letterSpacing: -0.2,
  },

  objectMetaRow: {
    marginTop: 5,
    flexDirection: "row",
    alignItems: "center",
    minWidth: 0,
  },

  objectKind: {
    color: C.dim,
    fontSize: 10.7,
    fontWeight: "800",
    textTransform: "uppercase",
  },

  metaDot: {
    width: 3,
    height: 3,
    borderRadius: 2,
    backgroundColor: "#526176",
    marginHorizontal: 7,
  },

  objectTarget: {
    color: C.dim,
    fontSize: 10.8,
    fontWeight: "600",
    flex: 1,
  },

  statusBadge: {
    marginLeft: 8,
    minHeight: 28,
    maxWidth: 118,
    paddingHorizontal: 8,
    borderRadius: 10,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
  },

  statusText: {
    fontSize: 10.2,
    lineHeight: 13,
    fontWeight: "900",
    flexShrink: 1,
  },

  riskBlock: {
    marginTop: 14,
  },

  riskTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },

  riskLabel: {
    color: C.dim,
    fontSize: 10.5,
    fontWeight: "800",
    textTransform: "uppercase",
  },

  riskValue: {
    fontSize: 11,
    fontWeight: "900",
  },

  riskTrack: {
    marginTop: 7,
    height: 4,
    borderRadius: 4,
    overflow: "hidden",
    backgroundColor: "#162438",
  },

  riskFill: {
    height: "100%",
    minWidth: 3,
    borderRadius: 4,
  },

  metricsRow: {
    marginTop: 13,
    paddingVertical: 11,
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: C.lineSoft,
    flexDirection: "row",
    alignItems: "center",
  },

  metric: {
    flex: 1,
    minWidth: 0,
  },

  metricLabel: {
    color: C.dim,
    fontSize: 9.4,
    lineHeight: 12,
    fontWeight: "700",
  },

  metricValue: {
    marginTop: 4,
    color: C.text,
    fontSize: 11.3,
    lineHeight: 14,
    fontWeight: "900",
  },

  metricDivider: {
    width: 1,
    height: 25,
    backgroundColor: C.lineSoft,
    marginHorizontal: 8,
  },

  expandRow: {
    height: 31,
    paddingTop: 8,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },

  protectedDotRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },

  liveDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },

  liveText: {
    color: C.dim,
    fontSize: 10.5,
    fontWeight: "900",
  },

  expanded: {
    paddingHorizontal: 15,
    paddingBottom: 15,
  },

  expandedDivider: {
    height: 1,
    backgroundColor: C.lineSoft,
  },

  expandedTitle: {
    marginTop: 13,
    marginBottom: 5,
    color: C.text,
    fontSize: 13,
    fontWeight: "900",
  },

  controlRow: {
    minHeight: 48,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottomWidth: 1,
    borderBottomColor: C.lineSoft,
  },

  controlCopy: {
    flex: 1,
    paddingRight: 12,
  },

  controlTitle: {
    color: C.text2,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: "700",
  },

  actionGrid: {
    marginTop: 12,
    flexDirection: "row",
    gap: 9,
  },

  actionButton: {
    flex: 1,
    minHeight: 43,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: C.line,
    backgroundColor: C.panel2,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    paddingHorizontal: 8,
  },

  actionText: {
    color: C.text2,
    fontSize: 11,
    fontWeight: "800",
    flexShrink: 1,
  },

  history: {
    marginTop: 13,
    padding: 12,
    borderRadius: 14,
    backgroundColor: "#081422",
    borderWidth: 1,
    borderColor: C.lineSoft,
  },

  historyTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    marginBottom: 8,
  },

  historyTitle: {
    color: C.text2,
    fontSize: 11.5,
    fontWeight: "900",
  },

  historyItem: {
    flexDirection: "row",
    paddingVertical: 7,
  },

  historyDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: C.orange,
    marginTop: 6,
    marginRight: 9,
  },

  historyCopy: {
    flex: 1,
  },

  historySummary: {
    color: C.text2,
    fontSize: 11,
    lineHeight: 16,
    fontWeight: "700",
  },

  historyTime: {
    marginTop: 3,
    color: C.dim,
    fontSize: 9.5,
    fontWeight: "700",
  },

  noHistory: {
    color: C.dim,
    fontSize: 11,
    lineHeight: 16,
    fontWeight: "600",
  },

  removeButton: {
    marginTop: 12,
    minHeight: 42,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: "rgba(255,83,100,0.24)",
    backgroundColor: C.redSoft,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
  },

  removeText: {
    color: C.red,
    fontSize: 11.5,
    fontWeight: "900",
  },

  emptyCard: {
    marginTop: 15,
    minHeight: 210,
    borderRadius: 19,
    borderWidth: 1,
    borderColor: C.line,
    backgroundColor: C.panel,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 28,
    paddingVertical: 26,
  },

  emptyIcon: {
    width: 54,
    height: 54,
    borderRadius: 17,
    backgroundColor: C.orangeSoft,
    borderWidth: 1,
    borderColor: "rgba(255,170,24,0.22)",
    alignItems: "center",
    justifyContent: "center",
  },

  emptyTitle: {
    marginTop: 14,
    color: C.text,
    fontSize: 16,
    fontWeight: "900",
    textAlign: "center",
  },

  emptyText: {
    marginTop: 7,
    color: C.dim,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "600",
    textAlign: "center",
  },

  addButton: {
    marginTop: 16,
    minHeight: 55,
    borderRadius: 17,
    borderWidth: 1.5,
    borderColor: C.orange,
    backgroundColor: "rgba(255,170,24,0.025)",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingHorizontal: 18,
  },

  addButtonPressed: {
    backgroundColor: C.orangeSoft,
  },

  addButtonText: {
    color: C.orange,
    fontSize: 13.5,
    lineHeight: 18,
    fontWeight: "900",
    textAlign: "center",
  },

  fullLoader: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },

  pressed: {
    opacity: 0.82,
  },

  bottomSpace: {
    height: 18,
  },
});