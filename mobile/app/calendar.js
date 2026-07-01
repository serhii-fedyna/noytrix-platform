// app/calendar.js
import React, { useMemo, useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  Switch,
  RefreshControl,
} from "react-native";
import { Stack } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { BlurView } from "expo-blur";
import { useTranslation } from "react-i18next";

import { BACKEND } from "./lib/backend";
import { showAppAlert } from "./lib/appAlert";

const API_ROOT = String(BACKEND || "").replace(/\/+$/, "");
const API_BASE = API_ROOT.endsWith("/api")
  ? `${API_ROOT}/calendar`
  : `${API_ROOT}/api/calendar`;

async function safeFetch(url, options = {}, timeoutMs = 15000) {
  const hasAbort = typeof AbortController !== "undefined";
  const ctrl = hasAbort ? new AbortController() : null;

  const id = setTimeout(() => {
    if (ctrl) ctrl.abort();
  }, timeoutMs);

  try {
    const res = await fetch(url, {
      ...options,
      ...(ctrl ? { signal: ctrl.signal } : {}),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res;
  } finally {
    clearTimeout(id);
  }
}

const GRAD = {
  bgStart: "#06080f",
  bgMid: "#09122c",
  bgEnd: "#0b1a46",
};

const T = {
  logo: "#ffb020",
  text: "#eef2ff",
  dim: "#aab5cf",
  accent: "#ffb020",
  accentText: "#0b1220",
  border: "rgba(255,255,255,0.10)",
  borderSoft: "rgba(255,255,255,0.08)",
  glass: "rgba(255,255,255,0.035)",
  glass2: "rgba(255,255,255,0.03)",
  red: "#ff6b6b",
  warn: "#ffb547",
  green: "#29d37a",
  shadow: "rgba(0,0,0,0.28)",
};

const IMPACT_COLORS = {
  low: T.green,
  mid: T.warn,
  high: T.red,
};

const cardChrome = {
  borderRadius: 24,
  borderWidth: 1,
  borderColor: T.border,
  overflow: "hidden",
  marginBottom: 14,
  shadowColor: "#000",
  shadowOpacity: 0.16,
  shadowRadius: 18,
  shadowOffset: { width: 0, height: 8 },
  elevation: 4,
};

const BlurCard = ({ style, children, intensity = 26 }) => (
  <View style={[cardChrome, style]}>
    <BlurView
      intensity={intensity}
      tint="dark"
      style={{
        padding: 16,
        borderRadius: 24,
        backgroundColor: "rgba(7,12,28,0.16)",
      }}
    >
      {children}
    </BlurView>
  </View>
);

const pad = (n) => (n < 10 ? `0${n}` : `${n}`);
const ymd = (d) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function endOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0);
}

function addMonths(date, delta) {
  return new Date(date.getFullYear(), date.getMonth() + delta, 1);
}

function buildMonthMatrix(anchor) {
  const first = startOfMonth(anchor);
  const last = endOfMonth(anchor);
  const jsDow = first.getDay();
  const offset = jsDow === 0 ? 6 : jsDow - 1;
  const daysInPrevMonth = new Date(
    anchor.getFullYear(),
    anchor.getMonth(),
    0
  ).getDate();

  const cells = [];

  for (let i = 0; i < 42; i++) {
    const cellIndex = i - offset + 1;
    let date;
    let inCurrent = true;

    if (cellIndex <= 0) {
      date = new Date(
        anchor.getFullYear(),
        anchor.getMonth() - 1,
        daysInPrevMonth + cellIndex
      );
      inCurrent = false;
    } else if (cellIndex > last.getDate()) {
      date = new Date(
        anchor.getFullYear(),
        anchor.getMonth() + 1,
        cellIndex - last.getDate()
      );
      inCurrent = false;
    } else {
      date = new Date(anchor.getFullYear(), anchor.getMonth(), cellIndex);
    }

    cells.push({ date, inCurrent });
  }

  const rows = [];
  for (let r = 0; r < 6; r++) {
    rows.push(cells.slice(r * 7, r * 7 + 7));
  }

  return rows;
}

function toLocalDayKeyFromTs(ts) {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return null;
  return ymd(d);
}

function eventDayKey(ev) {
  if (ev?.all_day && ev?.event_date) return String(ev.event_date);

  if (ev?.start_ts) {
    const localKey = toLocalDayKeyFromTs(ev.start_ts);
    if (localKey) return localKey;
  }

  if (ev?.event_date) return String(ev.event_date);
  return null;
}

function hasExactEventTime(ev) {
  if (ev?.has_time === false) return false;
  if (ev?.all_day === true) return false;
  if (!ev?.start_ts) return false;

  const d = new Date(ev.start_ts);
  return !Number.isNaN(d.getTime());
}

function formatClock(ts) {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return null;

  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

function formatEventTime(ev) {
  if (!hasExactEventTime(ev)) return "TBA";

  const start = formatClock(ev?.start_ts);
  const end = formatClock(ev?.end_ts);

  if (start && end && start !== end) return `${start}–${end}`;
  if (start) return start;

  return "TBA";
}

function normalizeEventType(ev, t) {
  const raw = String(ev?.type || ev?.category || ev?.kind || "")
    .trim()
    .toLowerCase();
  const title = String(ev?.title || "").trim().toLowerCase();
  const source = `${raw} ${title}`;

  if (
    source.includes("listing") ||
    source.includes("launchpool listing") ||
    source.includes("exchange listing")
  ) {
    return t("calendar.type.listing", { defaultValue: "Listing" });
  }

  if (
    source.includes("unlock") ||
    source.includes("vesting") ||
    source.includes("cliff")
  ) {
    return t("calendar.type.unlock", { defaultValue: "Unlock" });
  }

  if (
    source.includes("vote") ||
    source.includes("proposal") ||
    source.includes("governance") ||
    source.includes("bip")
  ) {
    return t("calendar.type.governance", { defaultValue: "Governance" });
  }

  if (source.includes("tokenomics")) {
    return t("calendar.type.tokenomics", { defaultValue: "Tokenomics" });
  }

  if (
    source.includes("network") ||
    source.includes("mainnet") ||
    source.includes("testnet")
  ) {
    return t("calendar.type.network", { defaultValue: "Network" });
  }

  if (source.includes("macro")) {
    return t("calendar.type.macro", { defaultValue: "Macro" });
  }

  if (source.includes("airdrop")) {
    return t("calendar.type.airdrop", { defaultValue: "Airdrop" });
  }

  if (
    source.includes("derivatives") ||
    source.includes("futures") ||
    source.includes("options")
  ) {
    return t("calendar.type.derivatives", {
      defaultValue: "Derivatives",
    });
  }

  if (
    source.includes("conference") ||
    source.includes("summit") ||
    source.includes("event")
  ) {
    return t("calendar.type.event", { defaultValue: "Event" });
  }

  if (!raw && ev?.title) {
    return t("calendar.type.event", { defaultValue: "Event" });
  }

  const cleaned = String(ev?.type || ev?.category || "Event")
    .replace(/[_-]+/g, " ")
    .trim();

  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

function sortDayEvents(list = []) {
  const impactRank = { high: 3, mid: 2, low: 1 };

  return list.slice().sort((a, b) => {
    const aHasTime = hasExactEventTime(a) ? 1 : 0;
    const bHasTime = hasExactEventTime(b) ? 1 : 0;

    if (aHasTime !== bHasTime) return bHasTime - aHasTime;

    if (aHasTime && bHasTime) {
      const at = new Date(a?.start_ts || "").getTime();
      const bt = new Date(b?.start_ts || "").getTime();

      if (!Number.isNaN(at) && !Number.isNaN(bt) && at !== bt) {
        return at - bt;
      }
    }

    const ai = impactRank[a?.impact] || 0;
    const bi = impactRank[b?.impact] || 0;

    if (bi !== ai) return bi - ai;

    return String(a?.title || "").localeCompare(String(b?.title || ""));
  });
}

async function apiGetEvents(d1, d2, types, impact) {
  const t = types || "Network,Listing,Tokenomics,Macro,Airdrop,Derivatives";
  const imp = impact || "high,mid";

  const url = `${API_BASE}/events?d1=${encodeURIComponent(
    d1
  )}&d2=${encodeURIComponent(d2)}&types=${encodeURIComponent(
    t
  )}&impact=${encodeURIComponent(imp)}`;

  const r = await safeFetch(url);
  const j = await r.json();

  return Array.isArray(j.items) ? j.items : [];
}

export default function CalendarScreen() {
  const { t } = useTranslation();

  const [cursor, setCursor] = useState(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });

  const [selected, setSelected] = useState(() => new Date());
  const [onlyHighMid, setOnlyHighMid] = useState(true);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [events, setEvents] = useState({});

  const matrix = useMemo(() => buildMonthMatrix(cursor), [cursor]);

  const WEEKDAYS_RAW = t("calendar.weekdays", { returnObjects: true });
  const MONTHS_RAW = t("calendar.months", { returnObjects: true });

  const WEEKDAYS = Array.isArray(WEEKDAYS_RAW)
    ? WEEKDAYS_RAW
    : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  const MONTHS = Array.isArray(MONTHS_RAW)
    ? MONTHS_RAW
    : [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
      ];

  const loadMonth = useCallback(
    async (abortFlag = { dead: false }) => {
      try {
        setLoading(true);

        const from = new Date();
        from.setUTCDate(from.getUTCDate() - 7);

        const to = new Date();
        to.setUTCDate(to.getUTCDate() + 180);
        to.setUTCHours(23, 59, 59, 0);

        const items = await apiGetEvents(
          from.toISOString(),
          to.toISOString(),
          undefined,
          onlyHighMid ? "high,mid" : "high,mid,low"
        );

        if (abortFlag.dead) return;

        const map = {};

        for (const ev of items) {
          const key = eventDayKey(ev);
          if (!key) continue;

          if (!Array.isArray(map[key])) map[key] = [];
          map[key].push(ev);
        }

        Object.keys(map).forEach((k) => {
          map[k] = sortDayEvents(map[k]);
        });

        setEvents(map);
      } catch (e) {
        console.log("calendar load error", e);

        showAppAlert(
          t("calendar.errorTitle", { defaultValue: "Error" }),
          t("calendar.errorLoad", {
            defaultValue: "Failed to load calendar.",
          })
        );
      } finally {
        if (!abortFlag.dead) setLoading(false);
      }
    },
    [onlyHighMid, t]
  );

  useEffect(() => {
    const guard = { dead: false };

    loadMonth(guard);

    return () => {
      guard.dead = true;
    };
  }, [cursor, onlyHighMid, loadMonth]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadMonth();
    setRefreshing(false);
  }, [loadMonth]);

  const selectedKey = ymd(selected);

  const monthLabel = MONTHS[cursor.getMonth()]
    ? `${MONTHS[cursor.getMonth()]} ${cursor.getFullYear()}`
    : `${cursor.getMonth() + 1}/${cursor.getFullYear()}`;

  const dayEvents = Array.isArray(events[selectedKey])
    ? sortDayEvents(events[selectedKey])
    : [];

  function dayEventsForCell(date) {
    const key = ymd(date);
    return Array.isArray(events[key]) ? events[key] : [];
  }

  function topImpactForList(list) {
    if (list.find((e) => e?.impact === "high")) return "high";
    if (list.find((e) => e?.impact === "mid")) return "mid";
    if (list.length > 0) return "low";
    return null;
  }

  return (
    <View style={{ flex: 1 }}>
      <Stack.Screen options={{ headerShown: false }} />

      <LinearGradient
        colors={[GRAD.bgStart, GRAD.bgMid, GRAD.bgEnd]}
        style={{ flex: 1 }}
      >
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={{
            paddingBottom: 28,
            paddingTop: 48,
            paddingHorizontal: 16,
          }}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor={T.dim}
              colors={[T.accent]}
            />
          }
          keyboardShouldPersistTaps="handled"
        >
          <View style={s.heroWrap}>
            <Text style={s.title}>
              {t("calendar.title", { defaultValue: "Calendar" })}
            </Text>

            <Text style={s.subTitle}>
              {t("calendar.headerSubtitle", {
                defaultValue: "Track real crypto events and important dates",
              })}
            </Text>

            <Text style={s.noteLine}>
              {t("calendar.notAdvice", {
                defaultValue: "Informational only. Always verify before acting.",
              })}
            </Text>
          </View>

          <BlurCard style={{ marginTop: 10 }}>
            <View style={s.filtersRow}>
              <View style={s.filterPill}>
                <View style={s.filterLeft}>
                  <Ionicons
                    name="funnel-outline"
                    size={15}
                    color={T.accent}
                  />

                  <Text style={s.filterText}>
                    {t("calendar.filterHighMedium", {
                      defaultValue: "Only High / Medium impact",
                    })}
                  </Text>
                </View>

                <Switch
                  value={onlyHighMid}
                  onValueChange={setOnlyHighMid}
                  trackColor={{
                    false: "rgba(255,255,255,0.16)",
                    true: "rgba(255,176,32,0.45)",
                  }}
                  thumbColor={onlyHighMid ? T.accent : "#d8def0"}
                />
              </View>
            </View>
          </BlurCard>

          <BlurCard intensity={28}>
            <View style={s.header}>
              <TouchableOpacity
                onPress={() => setCursor((d) => addMonths(d, -1))}
                style={s.navBtn}
                activeOpacity={0.85}
              >
                <Ionicons name="chevron-back" size={22} color={T.text} />
              </TouchableOpacity>

              <Text style={s.monthTitle} numberOfLines={1}>
                {monthLabel}
              </Text>

              <TouchableOpacity
                onPress={() => setCursor((d) => addMonths(d, 1))}
                style={s.navBtn}
                activeOpacity={0.85}
              >
                <Ionicons name="chevron-forward" size={22} color={T.text} />
              </TouchableOpacity>
            </View>

            <View style={s.calendarShell}>
              <View style={s.weekHeader}>
                {WEEKDAYS.map((w, idx) => (
                  <Text key={idx} style={s.weekLabel}>
                    {w}
                  </Text>
                ))}
              </View>

              {matrix.map((row, ri) => (
                <View key={`r-${ri}`} style={s.weekRow}>
                  {row.map(({ date, inCurrent }, ci) => {
                    const key = ymd(date);
                    const list = dayEventsForCell(date);
                    const hasEvent = list.length > 0;
                    const topLevel = topImpactForList(list);
                    const isSelected = key === selectedKey;
                    const isToday = key === ymd(new Date());

                    return (
                      <TouchableOpacity
                        key={`c-${ri}-${ci}`}
                        style={s.dayCell}
                        onPress={() => setSelected(date)}
                        activeOpacity={0.9}
                      >
                        <View
                          style={[
                            s.dayBubble,
                            isSelected && s.dayBubbleSelected,
                            isToday && !isSelected && s.dayBubbleToday,
                            !inCurrent && s.dayBubbleMuted,
                          ]}
                        >
                          <Text
                            style={[
                              s.dayNumber,
                              isSelected && s.dayNumberSelected,
                              isToday && !isSelected && s.dayNumberToday,
                            ]}
                          >
                            {date.getDate()}
                          </Text>

                          {hasEvent && (
                            <View
                              style={[
                                s.dot,
                                topLevel === "high" && {
                                  backgroundColor: IMPACT_COLORS.high,
                                },
                                topLevel === "mid" && {
                                  backgroundColor: IMPACT_COLORS.mid,
                                },
                                topLevel === "low" && {
                                  backgroundColor: IMPACT_COLORS.low,
                                },
                              ]}
                            />
                          )}
                        </View>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              ))}
            </View>
          </BlurCard>

          <BlurCard intensity={30}>
            <View style={s.eventsHead}>
              <View>
                <Text style={s.eventsTitle}>
                  {t("calendar.eventsTitle", {
                    defaultValue: "Events for the day",
                  })}
                </Text>

                <Text style={s.eventsSub}>
                  {selected.getDate()}{" "}
                  {MONTHS[selected.getMonth()] || selected.getMonth() + 1}
                </Text>
              </View>

              {loading && (
                <View style={s.loadingChip}>
                  <ActivityIndicator size="small" color={T.accent} />

                  <Text style={s.loadingChipText}>
                    {t("calendar.refreshing", {
                      defaultValue: "Refreshing...",
                    })}
                  </Text>
                </View>
              )}
            </View>

            {dayEvents.length === 0 ? (
              <View style={s.emptyBox}>
                <Ionicons name="calendar-outline" size={22} color={T.dim} />

                <Text style={s.noEvents}>
                  {t("calendar.noEvents", {
                    defaultValue: "No events for this day.",
                  })}
                </Text>
              </View>
            ) : (
              <View style={{ gap: 12 }}>
                {dayEvents.map((ev, i) => {
                  const impact = ev?.impact || "low";
                  const color = IMPACT_COLORS[impact] || T.green;

                  const levelName = t(`calendar.level.${impact}`, {
                    defaultValue:
                      impact === "high"
                        ? "High"
                        : impact === "mid"
                        ? "Medium"
                        : "Low",
                  });

                  const timeLabel = formatEventTime(ev);
                  const displayType = normalizeEventType(ev, t);
                  const hasTime = hasExactEventTime(ev);

                  return (
                    <View
                      key={`${selectedKey}-${ev?.id || ev?.title || i}-${i}`}
                      style={s.eventItem}
                    >
                      <View style={s.eventTopRow}>
                        <View style={[s.eventTag, { borderColor: color }]}>
                          <Text style={[s.eventTagText, { color }]}>
                            {displayType}
                          </Text>
                        </View>

                        <View style={[s.timePill, !hasTime && s.timePillTba]}>
                          <Ionicons
                            name={hasTime ? "time-outline" : "hourglass-outline"}
                            size={13}
                            color={hasTime ? T.text : T.accent}
                          />

                          <Text
                            style={[
                              s.timePillText,
                              !hasTime && s.timePillTextTba,
                            ]}
                          >
                            {timeLabel}
                          </Text>
                        </View>
                      </View>

                      <Text style={s.eventText}>{ev?.title || "—"}</Text>

                      <View style={s.metaRow}>
                        <View style={s.metaPill}>
                          <View
                            style={[
                              s.levelDot,
                              {
                                backgroundColor: color,
                              },
                            ]}
                          />

                          <Text style={s.metaPillText}>
                            {t("calendar.importance", {
                              defaultValue: "Importance",
                            })}
                            : {levelName}
                          </Text>
                        </View>

                        {!!ev?.asset && (
                          <View style={s.metaPill}>
                            <Text style={s.metaPillText}>{ev.asset}</Text>
                          </View>
                        )}
                      </View>

                      {!!ev?.summary && <Text style={s.note}>{ev.summary}</Text>}
                    </View>
                  );
                })}
              </View>
            )}
          </BlurCard>

          <BlurCard intensity={22}>
            <Text style={s.helpTitle}>
              {t("calendar.howTitle", { defaultValue: "How to use" })}
            </Text>

            <Text style={s.helpText}>
              {t("calendar.howP1", {
                defaultValue: "Use the calendar to track important crypto events.",
              })}
            </Text>

            <Text style={s.helpText}>
              {t("calendar.howP2", {
                defaultValue: "TBA means the exact event time is not confirmed yet.",
              })}
            </Text>

            <Text style={s.helpText}>
              {t("calendar.howP3", {
                defaultValue: "Timed events are shown in your local timezone.",
              })}
            </Text>

            <Text style={s.helpText}>
              {t("calendar.howP4", {
                defaultValue: "Always verify event details before trading decisions.",
              })}
            </Text>
          </BlurCard>
        </ScrollView>
      </LinearGradient>
    </View>
  );
}

const s = StyleSheet.create({
  heroWrap: {
    marginBottom: 4,
  },

  title: {
    color: T.logo,
    fontWeight: "900",
    fontSize: 34,
    letterSpacing: 0.2,
    marginBottom: 6,
  },
  subTitle: {
    color: T.dim,
    fontSize: 15,
    lineHeight: 20,
    marginBottom: 6,
  },
  noteLine: {
    color: T.dim,
    fontSize: 12,
    lineHeight: 16,
  },

  filtersRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "flex-start",
  },
  filterPill: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderColor: T.borderSoft,
    backgroundColor: T.glass,
    borderRadius: 18,
    paddingHorizontal: 12,
    paddingVertical: 10,
    width: "100%",
    justifyContent: "space-between",
    gap: 10,
  },
  filterLeft: {
    flexDirection: "row",
    alignItems: "center",
    flex: 1,
  },
  filterText: {
    color: T.text,
    fontWeight: "800",
    fontSize: 13,
    flex: 1,
    marginLeft: 8,
  },

  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  navBtn: {
    width: 46,
    height: 46,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: T.border,
    backgroundColor: T.glass,
  },
  monthTitle: {
    flex: 1,
    textAlign: "center",
    color: T.text,
    fontWeight: "900",
    fontSize: 17,
  },

  calendarShell: {
    marginTop: 14,
    borderWidth: 1,
    borderColor: T.borderSoft,
    backgroundColor: T.glass,
    borderRadius: 20,
    padding: 10,
  },
  weekHeader: {
    flexDirection: "row",
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255,255,255,0.06)",
    marginBottom: 8,
  },
  weekLabel: {
    flex: 1,
    textAlign: "center",
    color: T.dim,
    fontSize: 11,
    fontWeight: "900",
    letterSpacing: 0.2,
  },
  weekRow: {
    flexDirection: "row",
    marginBottom: 6,
  },
  dayCell: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 4,
  },
  dayBubble: {
    width: 42,
    height: 42,
    borderRadius: 15,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.02)",
  },
  dayBubbleSelected: {
    backgroundColor: "rgba(255,176,32,0.16)",
    borderColor: "rgba(255,176,32,0.70)",
  },
  dayBubbleToday: {
    borderColor: "rgba(255,255,255,0.20)",
    backgroundColor: "rgba(255,255,255,0.05)",
  },
  dayBubbleMuted: {
    opacity: 0.35,
  },
  dayNumber: {
    color: T.text,
    fontSize: 13,
    fontWeight: "800",
  },
  dayNumberSelected: {
    color: T.accent,
    fontWeight: "900",
  },
  dayNumberToday: {
    color: "#ffffff",
    fontWeight: "900",
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 999,
    marginTop: 4,
  },

  eventsHead: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
    marginBottom: 8,
  },
  eventsTitle: {
    color: T.text,
    fontWeight: "900",
    fontSize: 19,
  },
  eventsSub: {
    color: T.dim,
    marginTop: 6,
    fontSize: 12,
  },
  loadingChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    borderWidth: 1,
    borderColor: T.borderSoft,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 7,
    backgroundColor: T.glass,
  },
  loadingChipText: {
    color: T.dim,
    fontSize: 12,
    fontWeight: "800",
  },

  emptyBox: {
    marginTop: 4,
    borderWidth: 1,
    borderColor: T.borderSoft,
    borderRadius: 18,
    padding: 16,
    backgroundColor: T.glass,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  noEvents: {
    color: T.dim,
    lineHeight: 18,
    textAlign: "center",
  },

  eventItem: {
    borderWidth: 1,
    borderColor: T.border,
    borderRadius: 20,
    padding: 14,
    backgroundColor: T.glass,
  },
  eventTopRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    marginBottom: 12,
  },
  eventTag: {
    alignSelf: "flex-start",
    borderWidth: 1,
    borderRadius: 999,
    paddingVertical: 4,
    paddingHorizontal: 10,
    backgroundColor: "rgba(255,255,255,0.02)",
  },
  eventTagText: {
    fontWeight: "900",
    fontSize: 12,
  },
  timePill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
    borderColor: T.borderSoft,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: T.glass,
  },
  timePillTba: {
    borderColor: "rgba(255,176,32,0.30)",
    backgroundColor: "rgba(255,176,32,0.08)",
  },
  timePillText: {
    color: T.text,
    fontSize: 12,
    fontWeight: "800",
  },
  timePillTextTba: {
    color: T.accent,
  },
  eventText: {
    color: T.text,
    fontWeight: "900",
    fontSize: 15,
    lineHeight: 20,
    marginBottom: 10,
  },

  metaRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 2,
  },
  metaPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
    borderColor: T.borderSoft,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: T.glass,
  },
  metaPillText: {
    color: T.dim,
    fontSize: 12,
    fontWeight: "800",
  },
  levelDot: {
    width: 8,
    height: 8,
    borderRadius: 999,
  },

  note: {
    color: T.dim,
    marginTop: 10,
    lineHeight: 18,
    fontSize: 12,
  },

  helpTitle: {
    color: T.text,
    fontWeight: "900",
    marginBottom: 10,
    fontSize: 18,
  },
  helpText: {
    color: T.dim,
    lineHeight: 20,
    marginBottom: 8,
  },
});