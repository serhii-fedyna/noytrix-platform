import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { logEvent } from "./analytics";
import { BACKEND } from "./backend";
import { useI18n } from "../i18n/useI18n";
import { pickLang } from "../i18n/lang";

const PACKAGE_ID = "com.noytrix.app";
const PLAY_STORE_URL = `market://details?id=${PACKAGE_ID}`;
const PLAY_WEB_URL = `https://play.google.com/store/apps/details?id=${PACKAGE_ID}`;

const STATE_KEY = "noytrix.reviewPrompt.v1";
const INSTALL_UID_KEY = "noytrix.installUserId";
const MIN_APP_OPENS = 2;
const MIN_TOTAL_MS_BEFORE_PROMPT = 2 * 60 * 1000;
const TARGET_USAGE_MS = 5 * 60 * 1000;
const TARGET_SCAN_COUNT = 3;
const TARGET_DAYS_AFTER_INSTALL = 7;
const SNOOZE_MS = 3 * 24 * 60 * 60 * 1000;

function nowMs() {
  return Date.now();
}

function safeJson(raw, fallback) {
  try {
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function defaultState(ts = nowMs()) {
  return {
    firstSeenAt: ts,
    appOpens: 0,
    totalUsageMs: 0,
    scanCount: 0,
    lastSessionStartedAt: 0,
    lastPromptAt: 0,
    postponedUntil: 0,
    completed: false,
    playOpenedAt: 0,
  };
}

async function readState() {
  const state = { ...defaultState(), ...safeJson(await AsyncStorage.getItem(STATE_KEY), {}) };
  if (!state.firstSeenAt) state.firstSeenAt = nowMs();
  return state;
}

async function writeState(next) {
  await AsyncStorage.setItem(STATE_KEY, JSON.stringify(next));
  return next;
}

async function patchState(patch) {
  const current = await readState();
  return writeState({ ...current, ...patch });
}

async function ensureInstallUid() {
  try {
    const existing = await AsyncStorage.getItem(INSTALL_UID_KEY);
    if (existing) return existing;
    const next = `app_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    await AsyncStorage.setItem(INSTALL_UID_KEY, next);
    return next;
  } catch {
    return "unknown";
  }
}

export async function recordReviewPromptScan(meta = {}) {
  try {
    const current = await readState();
    if (current.completed) return current;
    const next = {
      ...current,
      scanCount: Number(current.scanCount || 0) + 1,
      lastScanAt: nowMs(),
      lastScanMeta: {
        screen: meta.screen || "",
        level: meta.level || "",
        kind: meta.kind || "",
      },
    };
    await writeState(next);
    logEvent("review_prompt_scan_progress", {
      scans: next.scanCount,
      screen: meta.screen || "",
      level: meta.level || "",
    });
    return next;
  } catch (e) {
    console.log("[REVIEW PROMPT] record scan error:", e);
    return null;
  }
}

function shouldShowPrompt(state) {
  const ts = nowMs();
  if (!state || state.completed) return false;
  if (Number(state.appOpens || 0) < MIN_APP_OPENS) return false;
  if (Number(state.postponedUntil || 0) > ts) return false;
  if (Number(state.lastPromptAt || 0) && ts - Number(state.lastPromptAt || 0) < SNOOZE_MS) return false;

  const ageDays = (ts - Number(state.firstSeenAt || ts)) / (24 * 60 * 60 * 1000);
  const usageOk = Number(state.totalUsageMs || 0) >= TARGET_USAGE_MS;
  const scansOk = Number(state.scanCount || 0) >= TARGET_SCAN_COUNT;
  const daysOk = ageDays >= TARGET_DAYS_AFTER_INSTALL;
  const warmedUp = Number(state.totalUsageMs || 0) >= MIN_TOTAL_MS_BEFORE_PROMPT || scansOk || daysOk;

  return warmedUp && (usageOk || scansOk || daysOk);
}

function tcopy(lang) {
  return {
    title: pickLang(lang, "Вам нравится Noytrix?", "Do you like Noytrix?", "Вам подобається Noytrix?"),
    subtitle: pickLang(
      lang,
      "Ваш ответ поможет сделать защиту от крипто-скама точнее.",
      "Your answer helps us make crypto scam protection sharper.",
      "Ваша відповідь допоможе зробити захист від крипто-скаму точнішим."
    ),
    yes: pickLang(lang, "Да, нравится", "Yes, I like it", "Так, подобається"),
    no: pickLang(lang, "Не совсем", "Not really", "Не зовсім"),
    later: pickLang(lang, "Позже", "Later", "Пізніше"),
    close: pickLang(lang, "Закрыть", "Close", "Закрити"),
    playTitle: pickLang(lang, "Оцените Noytrix в Google Play", "Rate Noytrix on Google Play", "Оцініть Noytrix у Google Play"),
    playText: pickLang(
      lang,
      "Если приложение помогает вам избегать риска, короткая оценка очень поддержит развитие Noytrix.",
      "If the app helps you avoid risk, a quick rating really supports Noytrix development.",
      "Якщо застосунок допомагає вам уникати ризику, коротка оцінка дуже підтримає розвиток Noytrix."
    ),
    openPlay: pickLang(lang, "Открыть Google Play", "Open Google Play", "Відкрити Google Play"),
    afterPlay: pickLang(lang, "Я оценил, продолжить", "I rated it, continue", "Я оцінив, продовжити"),
    usefulTitle: pickLang(lang, "Что оказалось самым полезным?", "What was most useful?", "Що було найкориснішим?"),
    nextTitle: pickLang(lang, "Какую одну функцию добавить первой?", "What one feature should we add first?", "Яку одну функцію додати першою?"),
    npsTitle: pickLang(
      lang,
      "Насколько вероятно, что вы порекомендуете Noytrix другу?",
      "How likely are you to recommend Noytrix to a friend?",
      "Наскільки ймовірно, що ви порадите Noytrix другу?"
    ),
    badTitle: pickLang(lang, "Что не понравилось?", "What did not work for you?", "Що не сподобалося?"),
    dailyTitle: pickLang(
      lang,
      "Что нужно изменить, чтобы вы пользовались Noytrix каждый день?",
      "What should change so you would use Noytrix every day?",
      "Що потрібно змінити, щоб ви користувалися Noytrix щодня?"
    ),
    commentPlaceholder: pickLang(lang, "Напишите коротко...", "Write a short answer...", "Напишіть коротко..."),
    submit: pickLang(lang, "Отправить", "Send", "Надіслати"),
    thanksTitle: pickLang(lang, "Спасибо!", "Thank you!", "Дякуємо!"),
    thanksText: pickLang(
      lang,
      "Мы сохранили ваш ответ. Это поможет сделать Noytrix лучше.",
      "We saved your answer. It will help make Noytrix better.",
      "Ми зберегли вашу відповідь. Це допоможе зробити Noytrix кращим."
    ),
    sending: pickLang(lang, "Отправка...", "Sending...", "Надсилання..."),
    other: pickLang(lang, "Другое", "Other", "Інше"),
    problemOther: pickLang(lang, "Другое", "Other", "Інше"),
  };
}

function positiveOptions(lang) {
  return [
    pickLang(lang, "ScamShield проверки", "ScamShield checks", "ScamShield перевірки"),
    pickLang(lang, "AI объяснения", "AI explanations", "AI пояснення"),
    pickLang(lang, "Анализ токенов", "Token analysis", "Аналіз токенів"),
    pickLang(lang, "Анализ кошельков", "Wallet analysis", "Аналіз гаманців"),
    pickLang(lang, "Крипто-календарь", "Crypto calendar", "Крипто-календар"),
    pickLang(lang, "PRO защита", "PRO protection", "PRO захист"),
  ];
}

function negativeOptions(lang) {
  return [
    pickLang(lang, "Сложно разобраться", "Hard to understand", "Складно розібратися"),
    pickLang(lang, "Не хватает функций", "Missing features", "Бракує функцій"),
    pickLang(lang, "Медленно работает", "Works slowly", "Працює повільно"),
    pickLang(lang, "Есть ошибки", "There are bugs", "Є помилки"),
    pickLang(lang, "Цена", "Price", "Ціна"),
  ];
}

async function submitFeedback(payload) {
  const uid = await ensureInstallUid();
  const body = {
    ...payload,
    installUserId: uid,
    platform: Platform.OS,
    app: "noytrix_mobile",
    createdAt: new Date().toISOString(),
  };

  const response = await fetch(`${BACKEND}/api/app-feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`feedback_http_${response.status}`);
  }
  return response.json().catch(() => ({ ok: true }));
}

function OptionButton({ active, label, onPress }) {
  return (
    <Pressable onPress={onPress} style={[styles.option, active && styles.optionActive]}>
      <Text style={[styles.optionText, active && styles.optionTextActive]}>{label}</Text>
    </Pressable>
  );
}

function NpsRow({ value, onChange }) {
  return (
    <View style={styles.npsRow}>
      {Array.from({ length: 11 }, (_, n) => (
        <Pressable key={n} onPress={() => onChange(n)} style={[styles.nps, value === n && styles.npsActive]}>
          <Text style={[styles.npsText, value === n && styles.npsTextActive]}>{n}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export function ReviewPromptHost() {
  const { lang } = useI18n();
  const copy = useMemo(() => tcopy(lang), [lang]);
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState("ask");
  const [sending, setSending] = useState(false);
  const [mostUseful, setMostUseful] = useState("");
  const [feature, setFeature] = useState("");
  const [problem, setProblem] = useState("");
  const [dailyChange, setDailyChange] = useState("");
  const [nps, setNps] = useState(null);
  const sessionStartedRef = useRef(nowMs());
  const visibleRef = useRef(false);

  useEffect(() => {
    visibleRef.current = visible;
  }, [visible]);

  useEffect(() => {
    let cancelled = false;

    const boot = async () => {
      try {
        const current = await readState();
        const ts = nowMs();
        await writeState({
          ...current,
          firstSeenAt: current.firstSeenAt || ts,
          appOpens: Number(current.appOpens || 0) + 1,
          lastSessionStartedAt: ts,
        });
      } catch (e) {
        console.log("[REVIEW PROMPT] boot error:", e);
      }
    };

    const tick = async () => {
      try {
        const current = await readState();
        const ts = nowMs();
        const elapsed = Math.max(0, ts - sessionStartedRef.current);
        sessionStartedRef.current = ts;
        const next = await writeState({
          ...current,
          totalUsageMs: Number(current.totalUsageMs || 0) + elapsed,
        });
        if (!cancelled && !visibleRef.current && shouldShowPrompt(next)) {
          await patchState({ lastPromptAt: ts });
          logEvent("review_prompt_shown", {
            scans: Number(next.scanCount || 0),
            app_opens: Number(next.appOpens || 0),
            usage_ms: Number(next.totalUsageMs || 0),
          });
          setStep("ask");
          setVisible(true);
        }
      } catch (e) {
        console.log("[REVIEW PROMPT] tick error:", e);
      }
    };

    boot().then(() => {
      setTimeout(tick, 12000);
    });
    const interval = setInterval(tick, 30000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const closeLater = async () => {
    await patchState({ postponedUntil: nowMs() + SNOOZE_MS, lastPromptAt: nowMs() }).catch(() => {});
    logEvent("review_prompt_later", { step });
    setVisible(false);
  };

  const finish = async () => {
    await patchState({ completed: true, completedAt: nowMs() }).catch(() => {});
    setStep("thanks");
    setTimeout(() => setVisible(false), 1200);
  };

  const openGooglePlay = async () => {
    await patchState({ playOpenedAt: nowMs() }).catch(() => {});
    logEvent("review_prompt_open_google_play", {});
    try {
      await Linking.openURL(PLAY_STORE_URL);
    } catch {
      await Linking.openURL(PLAY_WEB_URL).catch(() => {});
    }
    setStep("positive");
  };

  const sendPositive = async () => {
    if (sending) return;
    setSending(true);
    try {
      await submitFeedback({
        flow: "positive",
        language: lang,
        mostUseful,
        requestedFeature: feature.trim(),
        nps,
      });
      logEvent("review_prompt_feedback_sent", { flow: "positive", nps: nps ?? -1 });
      await finish();
    } catch (e) {
      console.log("[REVIEW PROMPT] positive submit error:", e);
      await finish();
    } finally {
      setSending(false);
    }
  };

  const sendNegative = async () => {
    if (sending) return;
    setSending(true);
    try {
      await submitFeedback({
        flow: "negative",
        language: lang,
        problem,
        dailyChange: dailyChange.trim(),
        requestedFeature: feature.trim(),
        nps,
      });
      logEvent("review_prompt_feedback_sent", { flow: "negative", nps: nps ?? -1 });
      await finish();
    } catch (e) {
      console.log("[REVIEW PROMPT] negative submit error:", e);
      await finish();
    } finally {
      setSending(false);
    }
  };

  const renderBody = () => {
    if (step === "play") {
      return (
        <>
          <Text style={styles.title}>{copy.playTitle}</Text>
          <Text style={styles.subtitle}>{copy.playText}</Text>
          <Pressable style={styles.primary} onPress={openGooglePlay}>
            <Text style={styles.primaryText}>{copy.openPlay}</Text>
          </Pressable>
          <Pressable style={styles.secondary} onPress={() => setStep("positive")}>
            <Text style={styles.secondaryText}>{copy.afterPlay}</Text>
          </Pressable>
        </>
      );
    }

    if (step === "positive") {
      return (
        <>
          <Text style={styles.title}>{copy.usefulTitle}</Text>
          <View style={styles.optionWrap}>
            {positiveOptions(lang).map((x) => (
              <OptionButton key={x} label={x} active={mostUseful === x} onPress={() => setMostUseful(x)} />
            ))}
            <OptionButton label={copy.other} active={mostUseful === copy.other} onPress={() => setMostUseful(copy.other)} />
          </View>

          <Text style={styles.question}>{copy.nextTitle}</Text>
          <TextInput
            value={feature}
            onChangeText={setFeature}
            placeholder={copy.commentPlaceholder}
            placeholderTextColor="#65708c"
            style={styles.input}
            multiline
          />

          <Text style={styles.question}>{copy.npsTitle}</Text>
          <NpsRow value={nps} onChange={setNps} />

          <Pressable style={styles.primary} onPress={sendPositive} disabled={sending}>
            {sending ? <ActivityIndicator color="#0b1220" /> : <Text style={styles.primaryText}>{copy.submit}</Text>}
          </Pressable>
        </>
      );
    }

    if (step === "negative") {
      return (
        <>
          <Text style={styles.title}>{copy.badTitle}</Text>
          <View style={styles.optionWrap}>
            {negativeOptions(lang).map((x) => (
              <OptionButton key={x} label={x} active={problem === x} onPress={() => setProblem(x)} />
            ))}
            <OptionButton label={copy.problemOther} active={problem === copy.problemOther} onPress={() => setProblem(copy.problemOther)} />
          </View>

          <Text style={styles.question}>{copy.dailyTitle}</Text>
          <TextInput
            value={dailyChange}
            onChangeText={setDailyChange}
            placeholder={copy.commentPlaceholder}
            placeholderTextColor="#65708c"
            style={styles.input}
            multiline
          />

          <Text style={styles.question}>{copy.nextTitle}</Text>
          <TextInput
            value={feature}
            onChangeText={setFeature}
            placeholder={copy.commentPlaceholder}
            placeholderTextColor="#65708c"
            style={styles.input}
            multiline
          />

          <Text style={styles.question}>{copy.npsTitle}</Text>
          <NpsRow value={nps} onChange={setNps} />

          <Pressable style={styles.primary} onPress={sendNegative} disabled={sending}>
            {sending ? <ActivityIndicator color="#0b1220" /> : <Text style={styles.primaryText}>{copy.submit}</Text>}
          </Pressable>
        </>
      );
    }

    if (step === "thanks") {
      return (
        <>
          <Text style={styles.title}>{copy.thanksTitle}</Text>
          <Text style={styles.subtitle}>{copy.thanksText}</Text>
        </>
      );
    }

    return (
      <>
        <Text style={styles.title}>{copy.title}</Text>
        <Text style={styles.subtitle}>{copy.subtitle}</Text>
        <View style={styles.choiceRow}>
          <Pressable
            style={[styles.choice, styles.choiceYes]}
            onPress={() => {
              logEvent("review_prompt_answer", { answer: "yes" });
              setStep("play");
            }}
          >
            <Text style={styles.choiceTextDark}>{copy.yes}</Text>
          </Pressable>
          <Pressable
            style={styles.choice}
            onPress={() => {
              logEvent("review_prompt_answer", { answer: "no" });
              setStep("negative");
            }}
          >
            <Text style={styles.choiceText}>{copy.no}</Text>
          </Pressable>
        </View>
      </>
    );
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={closeLater}>
      <View style={styles.backdrop}>
        <View style={styles.card}>
          <Pressable style={styles.close} onPress={closeLater}>
            <Text style={styles.closeText}>x</Text>
          </Pressable>
          <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scroll}>
            {renderBody()}
            {step !== "thanks" && (
              <Pressable style={styles.later} onPress={closeLater}>
                <Text style={styles.laterText}>{copy.later}</Text>
              </Pressable>
            )}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.74)",
    justifyContent: "center",
    padding: 18,
  },
  card: {
    maxHeight: "88%",
    borderRadius: 24,
    backgroundColor: "#081020",
    borderColor: "rgba(255,176,32,0.34)",
    borderWidth: 1,
    shadowColor: "#ffb020",
    shadowOpacity: 0.22,
    shadowRadius: 22,
    elevation: 10,
  },
  scroll: {
    padding: 22,
    paddingTop: 28,
  },
  close: {
    position: "absolute",
    right: 14,
    top: 12,
    zIndex: 5,
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255,255,255,0.07)",
  },
  closeText: {
    color: "#aeb8d6",
    fontSize: 18,
    fontWeight: "900",
  },
  title: {
    color: "#f6f7ff",
    fontSize: 24,
    lineHeight: 30,
    fontWeight: "900",
    marginBottom: 10,
  },
  subtitle: {
    color: "#aeb8d6",
    fontSize: 15,
    lineHeight: 22,
    marginBottom: 18,
  },
  choiceRow: {
    flexDirection: "row",
    gap: 12,
    marginTop: 4,
  },
  choice: {
    flex: 1,
    minHeight: 54,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 12,
    backgroundColor: "#111a31",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
  },
  choiceYes: {
    backgroundColor: "#ffb020",
    borderColor: "#ffb020",
  },
  choiceText: {
    color: "#eef2ff",
    fontSize: 16,
    fontWeight: "900",
    textAlign: "center",
  },
  choiceTextDark: {
    color: "#081020",
    fontSize: 16,
    fontWeight: "900",
    textAlign: "center",
  },
  primary: {
    minHeight: 54,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#ffb020",
    marginTop: 16,
    paddingHorizontal: 16,
  },
  primaryText: {
    color: "#081020",
    fontWeight: "900",
    fontSize: 16,
    textAlign: "center",
  },
  secondary: {
    minHeight: 48,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#111a31",
    marginTop: 10,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
  },
  secondaryText: {
    color: "#eef2ff",
    fontWeight: "800",
    textAlign: "center",
  },
  question: {
    color: "#eef2ff",
    fontSize: 15,
    lineHeight: 21,
    fontWeight: "900",
    marginTop: 16,
    marginBottom: 10,
  },
  optionWrap: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 4,
  },
  option: {
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: "#111a31",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
  },
  optionActive: {
    backgroundColor: "rgba(255,176,32,0.16)",
    borderColor: "rgba(255,176,32,0.76)",
  },
  optionText: {
    color: "#aeb8d6",
    fontWeight: "800",
  },
  optionTextActive: {
    color: "#ffcf7a",
  },
  input: {
    minHeight: 90,
    borderRadius: 18,
    padding: 14,
    color: "#eef2ff",
    backgroundColor: "#111a31",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
    textAlignVertical: "top",
  },
  npsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
  },
  nps: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#111a31",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
  },
  npsActive: {
    backgroundColor: "#ffb020",
    borderColor: "#ffb020",
  },
  npsText: {
    color: "#aeb8d6",
    fontWeight: "900",
    fontSize: 12,
  },
  npsTextActive: {
    color: "#081020",
  },
  later: {
    alignSelf: "center",
    marginTop: 16,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  laterText: {
    color: "#8e9abb",
    fontWeight: "800",
  },
});
