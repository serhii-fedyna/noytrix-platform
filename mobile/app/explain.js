// Premium FREE screen
// + Shield-style quota pill
// + human-friendly errors
// + auth_state_v1 support
// + backend tracking for real profile activity

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  SafeAreaView,
  View,
  Text,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Share,
  InteractionManager,
} from "react-native";
import { Stack, useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { BlurView } from "expo-blur";
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useTranslation } from "react-i18next";
import ViewShot from "react-native-view-shot";
import * as Sharing from "expo-sharing";

import { logEvent } from "./lib/analytics";
import { showAppAlert } from "./lib/appAlert";

const PRO_SCREEN_ROUTE = "/explain-pro";
const PRO_PAYWALL_ROUTE = "/pro";

const BACKEND = "https://noytrix.com";
const AUTH_KEY = "auth_state_v1";
const INSTALL_UID_KEY = "noytrix.installUserId";

const GRAD = { bgStart: "#06080f", bgMid: "#0a1233", bgEnd: "#0b1c4f" };
const C = {
  text: "#FFFFFF",
  sub: "#A8B4CF",
  accent: "#FFA500",
  red: "#FF6565",
  green: "#4CD964",
  warn: "#FFB547",
  cardBorder: "rgba(255,255,255,0.10)",
  cardGlow: "rgba(255,255,255,0.06)",
};

const STORAGE_RECENTS = "explain.recents.v1";
const STORAGE_FAVS = "explain.favs.v1";

const QUOTA_KEY = "explain.quota.v1";
const FREE_DAILY_LIMIT = 4;

const todayKeyLocal = () => {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
};

async function loadQuota() {
  try {
    const raw = await AsyncStorage.getItem(QUOTA_KEY);
    if (!raw) return { day: todayKeyLocal(), used: 0 };

    const j = JSON.parse(raw);
    if (!j?.day || typeof j?.used !== "number") {
      return { day: todayKeyLocal(), used: 0 };
    }

    const td = todayKeyLocal();
    if (j.day !== td) return { day: td, used: 0 };

    return { day: j.day, used: Math.max(0, j.used | 0) };
  } catch {
    return { day: todayKeyLocal(), used: 0 };
  }
}

async function saveQuota(q) {
  try {
    await AsyncStorage.setItem(QUOTA_KEY, JSON.stringify(q));
  } catch {}
}

const clamp = (x, a, b) => Math.max(a, Math.min(b, x));

const num = (v, d = NaN) => {
  const x =
    typeof v === "number"
      ? v
      : parseFloat(String(v ?? "").replace(/[^0-9.\-]/g, ""));
  return Number.isFinite(x) ? x : d;
};

const fmtUsd = (x) => {
  const v = num(x, NaN);
  if (!Number.isFinite(v)) return "вЂ”";

  if (v >= 1000) {
    return (
      "$" +
      v.toLocaleString("en-US", {
        maximumFractionDigits: v >= 100000 ? 0 : 2,
      })
    );
  }

  if (v >= 1) return "$" + v.toFixed(2);
  if (v >= 0.1) return "$" + v.toFixed(3);
  if (v >= 0.01) return "$" + v.toFixed(4);
  if (v >= 0.001) return "$" + v.toFixed(5);

  return "$" + v.toFixed(6);
};

const fmtPct = (x) => {
  const v = num(x, NaN);
  if (!Number.isFinite(v)) return "вЂ”";
  const s = v >= 0 ? "+" : "";
  return `${s}${v.toFixed(2)}%`;
};

const normalizeSymbol = (raw) => {
  let s = String(raw || "").trim().toUpperCase();
  s = s.replace(/[^A-Z0-9]/g, "");
  if (!s) return "";
  if (!s.endsWith("USDT")) s = s + "USDT";
  return s;
};

const cardChrome = (radius = 18) => ({
  borderRadius: radius,
  borderWidth: 1,
  borderColor: C.cardBorder,
  overflow: "hidden",
  shadowColor: C.cardGlow,
  shadowOpacity: 1,
  shadowRadius: 14,
  shadowOffset: { width: 0, height: 6 },
  elevation: 3,
});

function safeT(t, key, fallback) {
  const v = t(key, { defaultValue: fallback });
  if (!v) return fallback;
  if (typeof v === "string" && v.trim() === key) return fallback;
  return v;
}

function humanExplainError(err, t) {
  const raw = String(err?.message || err || "").toLowerCase();

  if (!raw) return safeT(t, "explain.errorGeneric", "Something went wrong.");

  if (raw.includes("network request failed") || raw.includes("failed to fetch")) {
    return safeT(t, "explain.errorNetwork", "Network error. Check your connection.");
  }

  if (raw.includes("http 400")) {
    return safeT(t, "explain.errorBadTicker", "Invalid ticker.");
  }

  if (raw.includes("http 404")) {
    return safeT(t, "explain.errorNotFound", "Ticker not found.");
  }

  if (raw.includes("http 429")) {
    return safeT(t, "explain.errorRateLimit", "Too many requests. Try again later.");
  }

  if (raw.includes("timeout") || raw.includes("aborted")) {
    return safeT(t, "explain.errorTimeout", "Request timed out. Try again.");
  }

  return safeT(t, "explain.error", "Failed to analyze this market.");
}

async function getAuthStateV1() {
  try {
    const raw = await AsyncStorage.getItem(AUTH_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

async function getAccessTokenV1() {
  try {
    const st = await getAuthStateV1();
    return st?.access_token || null;
  } catch {
    return null;
  }
}

function parseJwtPayload(token) {
  try {
    const raw = String(token || "").trim();
    if (!raw || raw.split(".").length < 2) return null;

    const base64 = raw.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);

    if (typeof atob !== "function") return null;

    const json = decodeURIComponent(
      Array.prototype.map
        .call(atob(padded), (c) =>
          "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2)
        )
        .join("")
    );

    return JSON.parse(json);
  } catch {
    return null;
  }
}

async function getOrCreateInstallUserId() {
  try {
    const existing = await AsyncStorage.getItem(INSTALL_UID_KEY);
    if (existing && String(existing).trim()) return String(existing).trim();

    const next = `guest_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    await AsyncStorage.setItem(INSTALL_UID_KEY, next);
    return next;
  } catch {
    return `guest_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  }
}

async function getBestUserIdV1() {
  try {
    const st = await getAuthStateV1();
    const u = st?.user || null;

    const direct = u?.email || u?.nick || u?.username || u?.login || u?.name || "";

    if (String(direct).trim()) return String(direct).trim().toLowerCase();

    const payload = parseJwtPayload(st?.access_token || "");
    const jwtUid =
      payload?.email ||
      payload?.user_email ||
      payload?.preferred_username ||
      payload?.username ||
      payload?.nick ||
      payload?.name ||
      payload?.sub ||
      "";

    if (String(jwtUid).trim()) return String(jwtUid).trim().toLowerCase();
  } catch {}

  try {
    const installId = await getOrCreateInstallUserId();
    if (installId && String(installId).trim()) return String(installId).trim();
  } catch {}

  return "anonymous";
}

async function trackExplainToBackend(payload) {
  try {
    const token = await getAccessTokenV1();
    const userId = await getBestUserIdV1();

    await fetch(`${BACKEND}/explain/track`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        userId,
        ...payload,
      }),
    });
  } catch (e) {
    console.log("[EXPLAIN track] error:", e?.message || e);
  }
}

function ema(values, period) {
  const p = Math.max(1, period | 0);
  const k = 2 / (p + 1);
  let prev = null;
  const out = [];

  for (let i = 0; i < values.length; i++) {
    const v = num(values[i], NaN);

    if (!Number.isFinite(v)) {
      out.push(NaN);
      continue;
    }

    prev = prev == null ? v : v * k + prev * (1 - k);
    out.push(prev);
  }

  return out;
}

function rsi(values, period = 14) {
  const p = Math.max(2, period | 0);
  const out = new Array(values.length).fill(NaN);
  let g = 0;
  let l = 0;

  for (let i = 1; i < values.length; i++) {
    const ch = values[i] - values[i - 1];

    if (i <= p) {
      if (ch > 0) g += ch;
      else l -= ch;

      if (i === p) {
        const avgG = g / p;
        const avgL = l / p;
        const rs = avgL === 0 ? 100 : avgG / avgL;
        out[i] = 100 - 100 / (1 + rs);
      }
    } else {
      const curG = ch > 0 ? ch : 0;
      const curL = ch < 0 ? -ch : 0;

      g = (g * (p - 1) + curG) / p;
      l = (l * (p - 1) + curL) / p;

      const rs = l === 0 ? 100 : g / l;
      out[i] = 100 - 100 / (1 + rs);
    }
  }

  return out;
}

function atr(hlc, period = 14) {
  const out = new Array(hlc.length).fill(NaN);
  const buf = [];

  for (let i = 0; i < hlc.length; i++) {
    const h = hlc[i].high;
    const lo = hlc[i].low;
    const pc = i > 0 ? hlc[i - 1].close : h;
    const tr = Math.max(h - lo, Math.abs(h - pc), Math.abs(lo - pc));

    buf.push(tr);
    if (buf.length > period) buf.shift();

    if (buf.length === period) {
      out[i] = buf.reduce((a, b) => a + b, 0) / period;
    }
  }

  return out;
}

function swingLevels(candles, lookback = 60) {
  if (!candles?.length) return { sup: NaN, res: NaN };

  const t = candles.slice(-lookback);

  return {
    sup: Math.min(...t.map((x) => x.low)),
    res: Math.max(...t.map((x) => x.high)),
  };
}

async function getTicker24h(symbol) {
  const url = `https://api.binance.com/api/v3/ticker/24hr?symbol=${encodeURIComponent(
    symbol
  )}`;

  const r = await fetch(url);
  if (!r.ok) throw new Error("HTTP " + r.status);

  const j = await r.json();

  return {
    last: num(j.lastPrice),
    ch24: num(j.priceChangePercent),
    quoteVol: num(j.quoteVolume),
    high: num(j.highPrice),
    low: num(j.lowPrice),
  };
}

async function getKlines(symbol, interval = "1h", limit = 260) {
  const url =
    `https://api.binance.com/api/v3/klines?symbol=${encodeURIComponent(symbol)}` +
    `&interval=${interval}&limit=${limit}`;

  const r = await fetch(url);
  if (!r.ok) throw new Error("HTTP " + r.status);

  const j = await r.json();

  return j.map((k) => ({
    time: k[0],
    open: num(k[1]),
    high: num(k[2]),
    low: num(k[3]),
    close: num(k[4]),
    vol: num(k[5]),
  }));
}

function scoreFromSignals({ emaBias, rsiVal, atrPct, ch24 }) {
  let s = 50;

  if (emaBias === "bull") s += 10;
  if (emaBias === "bear") s -= 10;

  if (Number.isFinite(rsiVal)) {
    const dist = Math.abs(rsiVal - 50);
    s += clamp(10 - dist * 0.6, -10, 10);
  }

  if (Number.isFinite(atrPct)) {
    if (atrPct < 0.8) s += 6;
    else if (atrPct < 1.6) s += 2;
    else if (atrPct < 2.6) s -= 4;
    else s -= 9;
  }

  if (Number.isFinite(ch24)) {
    const a = Math.abs(ch24);
    if (a < 2) s += 4;
    else if (a < 5) s += 1;
    else if (a < 9) s -= 4;
    else s -= 8;
  }

  return clamp(Math.round(s), 0, 100);
}

function labelLiquidity(quoteVolUsd) {
  if (!Number.isFinite(quoteVolUsd)) return "unknown";
  if (quoteVolUsd >= 2_000_000_000) return "ultra";
  if (quoteVolUsd >= 700_000_000) return "high";
  if (quoteVolUsd >= 150_000_000) return "mid";
  return "low";
}

async function getIsProActive() {
  const keys = [
    "pro.active",
    "proActive",
    "isPro",
    "premium",
    "subscriptionActive",
    "iap.pro",
    "noytrix.pro.active",
    "user.isPro",
    "noytrix_pro_flag",
  ];

  try {
    for (const k of keys) {
      const v = await AsyncStorage.getItem(k);
      if (!v) continue;

      const s = String(v).toLowerCase();
      if (s === "true" || s === "1" || s === "active" || s === "yes") {
        return true;
      }
    }
  } catch {}

  if (globalThis?.NOYTRIX_PRO === true) return true;

  return false;
}

export default function Explain() {
  const { t } = useTranslation();
  const router = useRouter();

  const [query, setQuery] = useState("BTC");
  const [interval, setInterval] = useState("1h");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [recents, setRecents] = useState([]);
  const [favs, setFavs] = useState([]);

  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const inputRef = useRef(null);

  const [isPro, setIsPro] = useState(false);
  const [quotaUsed, setQuotaUsed] = useState(0);

  const quotaLimit = FREE_DAILY_LIMIT;
  const [limitReached, setLimitReached] = useState(false);

  useEffect(() => {
    logEvent("screen_open", { screen: "explain" });
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await getOrCreateInstallUserId();

        const [r, f] = await Promise.all([
          AsyncStorage.getItem(STORAGE_RECENTS),
          AsyncStorage.getItem(STORAGE_FAVS),
        ]);

        setRecents(r ? JSON.parse(r) : []);
        setFavs(f ? JSON.parse(f) : []);
      } catch {
        setRecents([]);
        setFavs([]);
      }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      const pro = await getIsProActive();
      setIsPro(pro);

      const q = await loadQuota();
      setQuotaUsed(q.used);
      setLimitReached(!pro && q.used >= FREE_DAILY_LIMIT);
    })();
  }, []);

  const saveRecents = useCallback(async (arr) => {
    setRecents(arr);

    try {
      await AsyncStorage.setItem(STORAGE_RECENTS, JSON.stringify(arr));
    } catch {}
  }, []);

  const saveFavs = useCallback(async (arr) => {
    setFavs(arr);

    try {
      await AsyncStorage.setItem(STORAGE_FAVS, JSON.stringify(arr));
    } catch {}
  }, []);

  const isFav = useMemo(() => {
    const sym = normalizeSymbol(query);
    return !!sym && favs.includes(sym);
  }, [query, favs]);

  const toggleFav = useCallback(() => {
    const sym = normalizeSymbol(query);
    if (!sym) return;

    logEvent("explain_fav_toggle", {
      screen: "explain",
      sym,
      action: isFav ? "remove" : "add",
    });

    const next = isFav
      ? favs.filter((x) => x !== sym)
      : [sym, ...favs].slice(0, 24);

    saveFavs(next);
  }, [query, isFav, favs, saveFavs]);

  const ensureQuotaOrBlock = useCallback(
    async (symForLog) => {
      if (isPro) return { ok: true };

      const q = await loadQuota();
      setQuotaUsed(q.used);

      if (q.used >= FREE_DAILY_LIMIT) {
        setLimitReached(true);

        logEvent("explain_quota_blocked", {
          screen: "explain",
          sym: symForLog || "",
          used: q.used,
          limit: FREE_DAILY_LIMIT,
        });

        return { ok: false };
      }

      const next = { day: q.day, used: q.used + 1 };
      await saveQuota(next);

      setQuotaUsed(next.used);
      setLimitReached(next.used >= FREE_DAILY_LIMIT);

      logEvent("explain_quota_consume", {
        screen: "explain",
        sym: symForLog || "",
        used: next.used,
        limit: FREE_DAILY_LIMIT,
      });

      return { ok: true };
    },
    [isPro]
  );

  const build = useCallback(
    async (raw) => {
      const sym = normalizeSymbol(raw);

      if (!sym) {
        showAppAlert(
          safeT(t, "explain.alertBadTickerTitle", "Invalid ticker"),
          safeT(t, "explain.alertBadTickerText", "Enter a valid trading pair.")
        );
        return;
      }

      const gate = await ensureQuotaOrBlock(sym);
      if (!gate.ok) return;

      setError("");
      setLoading(true);

      logEvent("explain_analyze", { screen: "explain", sym, interval });

      try {
        const [tk, ks] = await Promise.all([
          getTicker24h(sym),
          getKlines(sym, interval, 260),
        ]);

        const closes = ks.map((c) => c.close);
        const hlc = ks.map((c) => ({
          high: c.high,
          low: c.low,
          close: c.close,
        }));

        const e20 = ema(closes, 20);
        const e50 = ema(closes, 50);
        const r = rsi(closes, 14);
        const a = atr(hlc, 14);

        const last = ks[ks.length - 1];
        const ema20Last = e20[e20.length - 1];
        const ema50Last = e50[e50.length - 1];
        const rsiLast = r[r.length - 1];
        const atrLast = a[a.length - 1];

        const { sup, res } = swingLevels(ks, 80);

        const emaBias =
          ema20Last > ema50Last
            ? "bull"
            : ema20Last < ema50Last
            ? "bear"
            : "flat";

        const atrPct =
          Number.isFinite(atrLast) && Number.isFinite(last?.close)
            ? (atrLast / last.close) * 100
            : NaN;

        const liq = labelLiquidity(tk.quoteVol);

        const risk = !Number.isFinite(atrPct)
          ? "unknown"
          : atrPct < 1.2
          ? "low"
          : atrPct < 2.2
          ? "mid"
          : "high";

        const momentum = !Number.isFinite(rsiLast)
          ? "unknown"
          : rsiLast >= 60
          ? "strongUp"
          : rsiLast <= 40
          ? "strongDown"
          : "neutral";

        const score = scoreFromSignals({
          emaBias,
          rsiVal: rsiLast,
          atrPct,
          ch24: tk.ch24,
        });

        const biasText =
          emaBias === "bull"
            ? safeT(t, "explain.biasBull", "Bullish")
            : emaBias === "bear"
            ? safeT(t, "explain.biasBear", "Bearish")
            : safeT(t, "explain.biasFlat", "Flat");

        const marketToneText =
          score >= 70
            ? safeT(t, "explain.marketToneStrong", "Market tone looks strong.")
            : score >= 50
            ? safeT(t, "explain.marketToneBalanced", "Market tone is balanced.")
            : safeT(t, "explain.marketToneWeak", "Market tone is weak.");

        const rsiLabel = !Number.isFinite(rsiLast)
          ? safeT(t, "explain.na", "вЂ”")
          : rsiLast >= 70
          ? safeT(t, "explain.rsiOverbought", "Overbought")
          : rsiLast <= 30
          ? safeT(t, "explain.rsiOversold", "Oversold")
          : safeT(t, "explain.rsiNormal", "Normal");

        const liqText =
          liq === "ultra"
            ? safeT(t, "explain.liqUltra", "Ultra")
            : liq === "high"
            ? safeT(t, "explain.liqHigh", "High")
            : liq === "mid"
            ? safeT(t, "explain.liqMid", "Medium")
            : liq === "low"
            ? safeT(t, "explain.liqLow", "Low")
            : safeT(t, "explain.liqUnknown", "Unknown");

        const riskText =
          risk === "low"
            ? safeT(t, "explain.riskLow", "Low")
            : risk === "mid"
            ? safeT(t, "explain.riskMid", "Medium")
            : risk === "high"
            ? safeT(t, "explain.riskHigh", "High")
            : safeT(t, "explain.riskUnknown", "Unknown");

        const momText =
          momentum === "strongUp"
            ? safeT(t, "explain.momUp", "Strong up")
            : momentum === "strongDown"
            ? safeT(t, "explain.momDown", "Strong down")
            : momentum === "neutral"
            ? safeT(t, "explain.momNeutral", "Neutral")
            : safeT(t, "explain.momUnknown", "Unknown");

        const nextResult = {
          sym,
          tk,
          ks,
          lastClose: last?.close,
          ema20Last,
          ema50Last,
          rsiLast,
          atrLast,
          atrPct,
          sup,
          res,
          emaBias,
          biasText,
          marketToneText,
          rsiLabel,
          liqText,
          riskText,
          momText,
          score,
          risk,
          momentum,
        };

        setResult(nextResult);

        await trackExplainToBackend({
          symbol: sym,
          interval,
          score,
          emaBias,
          risk,
          momentum,
        });

        logEvent("explain_result", {
          screen: "explain",
          sym,
          interval,
          score,
          emaBias,
          risk,
          momentum,
        });

        const nextRecents = [sym, ...recents.filter((x) => x !== sym)].slice(0, 12);
        saveRecents(nextRecents);
      } catch (e) {
        console.log("[EXPLAIN] error:", e);
        setResult(null);
        setError(humanExplainError(e, t));

        logEvent("explain_error", { screen: "explain", sym, interval });
      } finally {
        setLoading(false);
      }
    },
    [interval, t, recents, saveRecents, ensureQuotaOrBlock]
  );

  const onAnalyze = useCallback(() => {
    inputRef.current?.blur?.();
    build(query);
  }, [build, query]);

  const onRefresh = useCallback(async () => {
    if (!result?.sym) return;

    setRefreshing(true);

    logEvent("explain_refresh", {
      screen: "explain",
      sym: result.sym,
      interval,
      source: "pull",
    });

    try {
      await build(result.sym);
    } finally {
      setRefreshing(false);
    }
  }, [build, result?.sym, interval]);

  const quickSet = (sym) => {
    logEvent("explain_quick_select", { screen: "explain", sym, interval });
    setQuery(sym.replace("USDT", ""));
    setTimeout(() => build(sym), 0);
  };

  const scoreColor = (score) => {
    if (score >= 70) return C.green;
    if (score >= 50) return C.accent;
    return C.red;
  };

  const openPro = useCallback(async () => {
    logEvent("pro_opened", { screen: "explain", source: "explain" });

    const active = await getIsProActive();
    setIsPro(active);

    router.push(active ? PRO_SCREEN_ROUTE : PRO_PAYWALL_ROUTE);
  }, [router]);


  const shareShotRef = useRef(null);

  const shareExplain = useCallback(async () => {
    if (!result) return;

    try {
      logEvent("explain_share_image", { screen: "explain", sym: result?.sym || "" });

      await new Promise((resolve) => InteractionManager.runAfterInteractions(resolve));
      await new Promise((resolve) => setTimeout(resolve, 220));

      const uri = await shareShotRef.current?.capture?.();

      if (!uri || typeof uri !== "string") {
        throw new Error("capture_empty");
      }

      const canShareFile = await Sharing.isAvailableAsync().catch(() => false);

      if (canShareFile) {
        await Sharing.shareAsync(uri, {
          mimeType: "image/png",
          UTI: "public.png",
          dialogTitle: "Share Noytrix Explain",
        });
        return;
      }

      await Share.share({
        title: "Noytrix Explain",
        url: uri,
        message: Platform.OS === "ios" ? "Noytrix Explain" : `Noytrix Explain\n${uri}`,
      });
    } catch (e) {
      const raw = String(e?.message || e || "").toLowerCase();

      if (!raw.includes("cancel")) {
        showAppAlert(
          safeT(t, "explain.shareErrorTitle", "Could not share"),
          safeT(t, "explain.shareErrorText", "Could not send the image. Please try again.")
        );
      }

      console.log("[EXPLAIN SHARE ERROR]", e?.message || e);
    }
  }, [result, t]);


  const howText = safeT(t, "explain.howBody", "");

  return (
    <LinearGradient
      colors={[GRAD.bgStart, GRAD.bgMid, GRAD.bgEnd]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={{ flex: 1 }}
    >
      <Stack.Screen options={{ headerShown: false }} />

      <SafeAreaView style={{ flex: 1 }}>
        <KeyboardAvoidingView
          style={{ flex: 1 }}
          behavior={Platform.OS === "ios" ? "padding" : "height"}
          keyboardVerticalOffset={Platform.OS === "ios" ? 10 : 0}
        >
          <ScrollView
            contentContainerStyle={{ padding: 20, paddingBottom: 120 }}
            refreshControl={
              <RefreshControl
                refreshing={refreshing}
                onRefresh={onRefresh}
                tintColor={C.accent}
              />
            }
            keyboardShouldPersistTaps="handled"
          >
            <View style={{ paddingTop: 18, paddingBottom: 10 }}>
              <Text style={s.h1}>{safeT(t, "explain.title", "Explain")}</Text>

              <Text style={s.hSub}>{safeT(t, "explain.subtitle2", "")}</Text>

              {!isPro && (
                <View style={s.quotaPillShield}>
                  <Text style={s.quotaTextShield}>{`FREE • ${quotaUsed}/${quotaLimit}`}</Text>
                </View>
              )}
            </View>

            <View style={[cardChrome(18), { marginTop: 10 }]}>
              <BlurView intensity={24} tint="dark" style={{ padding: 16 }}>
                <Text style={s.cardTitle}>{safeT(t, "explain.inputTitle", "")}</Text>

                <Text style={s.cardText}>
                  {safeT(t, "explain.inputTextPairsOnly", "")}
                </Text>

                <View style={{ marginTop: 14 }}>
                  <View style={s.searchWrap}>
                    <Ionicons name="search" size={18} color={C.sub} />

                    <TextInput
                      ref={inputRef}
                      value={query}
                      onChangeText={setQuery}
                      placeholder={safeT(t, "explain.searchPlaceholder", "")}
                      placeholderTextColor={C.sub}
                      autoCapitalize="characters"
                      autoCorrect={false}
                      style={s.searchInput}
                      returnKeyType="search"
                      onSubmitEditing={onAnalyze}
                    />

                    <TouchableOpacity
                      onPress={toggleFav}
                      activeOpacity={0.85}
                      style={{ padding: 6, marginLeft: 2 }}
                    >
                      <Ionicons
                        name={isFav ? "star" : "star-outline"}
                        size={18}
                        color={isFav ? C.accent : C.sub}
                      />
                    </TouchableOpacity>
                  </View>

                  <View style={{ flexDirection: "row", gap: 10, marginTop: 12 }}>
                    <TouchableOpacity
                      activeOpacity={0.9}
                      onPress={onAnalyze}
                      style={s.btnMain}
                      disabled={loading}
                    >
                      {loading ? (
                        <ActivityIndicator color="#0B1220" />
                      ) : (
                        <Text style={s.btnMainText}>
                          {safeT(t, "explain.btnAnalyze", "")}
                        </Text>
                      )}
                    </TouchableOpacity>

                    <View style={{ flexDirection: "row", gap: 8 }}>
                      {["1h", "4h", "1d"].map((iv) => (
                        <TouchableOpacity
                          key={iv}
                          activeOpacity={0.9}
                          onPress={() => {
                            logEvent("explain_interval_change", {
                              screen: "explain",
                              interval_from: interval,
                              interval_to: iv,
                            });
                            setInterval(iv);
                          }}
                          style={[
                            s.chip,
                            interval === iv && {
                              borderColor: C.accent,
                              backgroundColor: "rgba(255,165,0,0.14)",
                            },
                          ]}
                        >
                          <Text
                            style={[
                              s.chipText,
                              interval === iv && { color: C.accent },
                            ]}
                          >
                            {iv.toUpperCase()}
                          </Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>

                  {!isPro && limitReached && (
                    <View style={[s.limitCard, { marginTop: 14 }]}>
                      <Text style={s.limitTitle}>
                        {safeT(t, "shield.limitTitle", "FREE limit reached")}
                      </Text>

                      <Text style={s.limitBody}>
                        {safeT(t, "shield.limitBody", "You used 4/4 checks today. Upgrade to PRO for unlimited analysis.")}
                      </Text>

                      <TouchableOpacity
                        activeOpacity={0.9}
                        onPress={() => {
                          logEvent("pro_opened", {
                            screen: "explain",
                            source: "limit_card",
                          });
                          router.push(PRO_PAYWALL_ROUTE);
                        }}
                        style={s.limitBtn}
                      >
                        <Text style={s.limitBtnText}>
                          {safeT(t, "shield.openPro", "Upgrade to PRO")}
                        </Text>
                      </TouchableOpacity>
                    </View>
                  )}

                  {(favs.length > 0 || recents.length > 0) && (
                    <View style={{ marginTop: 14 }}>
                      {favs.length > 0 && (
                        <>
                          <Text style={s.miniLabel}>
                            {safeT(t, "explain.favs", "")}
                          </Text>

                          <View style={s.quickRow}>
                            {favs.slice(0, 6).map((x) => (
                              <TouchableOpacity
                                key={x}
                                activeOpacity={0.9}
                                onPress={() => quickSet(x)}
                                style={s.quickChip}
                              >
                                <Text style={s.quickText}>
                                  {x.replace("USDT", "")}
                                </Text>
                              </TouchableOpacity>
                            ))}
                          </View>
                        </>
                      )}

                      {recents.length > 0 && (
                        <>
                          <Text
                            style={[
                              s.miniLabel,
                              { marginTop: favs.length ? 10 : 0 },
                            ]}
                          >
                            {safeT(t, "explain.recents", "")}
                          </Text>

                          <View style={s.quickRow}>
                            {recents.slice(0, 8).map((x) => (
                              <TouchableOpacity
                                key={x}
                                activeOpacity={0.9}
                                onPress={() => quickSet(x)}
                                style={s.quickChipAlt}
                              >
                                <Text style={s.quickTextAlt}>
                                  {x.replace("USDT", "")}
                                </Text>
                              </TouchableOpacity>
                            ))}
                          </View>
                        </>
                      )}
                    </View>
                  )}
                </View>
              </BlurView>
            </View>

            <View style={[cardChrome(18), { marginTop: 12 }]}>
              <BlurView intensity={24} tint="dark" style={{ padding: 16 }}>
                <Text style={s.cardTitle}>{safeT(t, "explain.howTitle", "")}</Text>
                <Text style={s.cardText}>{howText}</Text>
              </BlurView>
            </View>
            {!!error && (
              <View style={[cardChrome(16), { marginTop: 12 }]}>
                <BlurView intensity={24} tint="dark" style={{ padding: 14 }}>
                  <Text style={{ color: C.red, fontWeight: "900" }}>
                    {safeT(t, "explain.errorTitle", "Error")}
                  </Text>

                  <Text style={{ color: C.sub, marginTop: 6, lineHeight: 18 }}>
                    {error}
                  </Text>
                </BlurView>
              </View>
            )}

            {result && (
              <>
                <View
                  style={{
                    marginTop: 16,
                    flexDirection: "row",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <Text style={s.sectionTitle}>
                    {safeT(t, "explain.resultTitle", "")} •{" "}
                    {result.sym.replace("USDT", "/USDT")}
                  </Text>

                  <View style={{ flexDirection: "row", gap: 10, alignItems: "center" }}>
                    <View style={[s.scorePill, { borderColor: scoreColor(result.score) }]}>
                      <Text style={[s.scoreText, { color: scoreColor(result.score) }]}>
                        {safeT(t, "explain.score", "")} {result.score}/100
                      </Text>
                    </View>


                    <TouchableOpacity
                      activeOpacity={0.9}
                      onPress={shareExplain}
                      style={s.iconBtn}
                    >
                      <Ionicons name="share-social-outline" size={18} color={C.text} />
                    </TouchableOpacity>

                    <TouchableOpacity
                      activeOpacity={0.9}
                      onPress={() => {
                        logEvent("explain_refresh", {
                          screen: "explain",
                          sym: result.sym,
                          interval,
                          source: "icon",
                        });
                        build(result.sym);
                      }}
                      style={s.iconBtn}
                    >
                      <Ionicons name="refresh" size={18} color={C.text} />
                    </TouchableOpacity>
                  </View>
                </View>

                <View style={[cardChrome(18), { marginTop: 10 }]}>
                  <BlurView intensity={24} tint="dark" style={{ padding: 16 }}>
                    <View
                      style={{
                        flexDirection: "row",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                      }}
                    >
                      <View style={{ flex: 1 }}>
                        <Text style={s.bigPrice}>{fmtUsd(result.tk?.last)}</Text>

                        <Text style={s.smallLine}>
                          {safeT(t, "explain.biasLabel", "")}:{" "}
                          <Text style={{ color: C.text, fontWeight: "900" }}>
                            {result.biasText}
                          </Text>
                        </Text>

                        <Text style={[s.smallLine, { marginTop: 6 }]}>
                          {result.marketToneText}
                        </Text>
                      </View>

                      <View style={{ alignItems: "flex-end" }}>
                        <Text
                          style={{
                            fontWeight: "900",
                            color: (result.tk?.ch24 ?? 0) >= 0 ? C.green : C.red,
                            fontSize: 16,
                          }}
                        >
                          {fmtPct(result.tk?.ch24)}
                        </Text>

                        <Text style={s.smallLine}>
                          {safeT(t, "explain.change24h", "")}
                        </Text>
                      </View>
                    </View>

                    <View style={{ marginTop: 12, flexDirection: "row", gap: 10 }}>
                      <View style={[s.kpiCard, { flex: 1 }]}>
                        <Text style={s.kpiLabel}>
                          {safeT(t, "explain.range24h", "")}
                        </Text>

                        <Text style={s.kpiValue}>
                          {fmtUsd(result.tk?.high)} / {fmtUsd(result.tk?.low)}
                        </Text>
                      </View>

                      <View style={[s.kpiCard, { flex: 1 }]}>
                        <Text style={s.kpiLabel}>
                          {safeT(t, "explain.volume24h", "")}
                        </Text>

                        <Text style={s.kpiValue}>
                          {Number.isFinite(result.tk?.quoteVol)
                            ? "$" + Math.round(result.tk.quoteVol).toLocaleString("en-US")
                            : "вЂ”"}
                        </Text>
                      </View>
                    </View>

                    <View style={{ marginTop: 12, flexDirection: "row", gap: 10 }}>
                      <Tag
                        label={safeT(t, "explain.liquidity", "")}
                        value={result.liqText}
                        tone="soft"
                      />

                      <Tag
                        label={safeT(t, "explain.risk", "")}
                        value={result.riskText}
                        tone={
                          result.riskText === safeT(t, "explain.riskHigh", "High")
                            ? "bad"
                            : "ok"
                        }
                      />

                      <Tag
                        label={safeT(t, "explain.momentum", "")}
                        value={result.momText}
                        tone="soft"
                      />
                    </View>
                  </BlurView>
                </View>

                <View style={[cardChrome(18), { marginTop: 12 }]}>
                  <BlurView intensity={24} tint="dark" style={{ padding: 16 }}>
                    <Text style={s.cardTitle}>
                      {safeT(t, "explain.signalsTitle", "")}
                    </Text>

                    <View style={s.table}>
                      <Row
                        left={safeT(t, "explain.ema", "EMA20 / EMA50")}
                        right={`${fmtUsd(result.ema20Last)} / ${fmtUsd(result.ema50Last)}`}
                        rightColor={
                          result.emaBias === "bull"
                            ? C.green
                            : result.emaBias === "bear"
                            ? C.red
                            : C.sub
                        }
                        sub={
                          result.emaBias === "bull"
                            ? safeT(t, "explain.emaBull", "")
                            : result.emaBias === "bear"
                            ? safeT(t, "explain.emaBear", "")
                            : safeT(t, "explain.emaFlat", "")
                        }
                      />

                      <Row
                        left={safeT(t, "explain.rsi", "RSI(14)")}
                        right={Number.isFinite(result.rsiLast) ? result.rsiLast.toFixed(1) : "вЂ”"}
                        rightColor={
                          Number.isFinite(result.rsiLast)
                            ? result.rsiLast >= 60
                              ? C.green
                              : result.rsiLast <= 40
                              ? C.red
                              : C.accent
                            : C.sub
                        }
                        sub={result.rsiLabel}
                      />

                      <Row
                        left={safeT(t, "explain.atr", "ATR(14)")}
                        right={
                          Number.isFinite(result.atrLast)
                            ? `${fmtUsd(result.atrLast)} (${
                                Number.isFinite(result.atrPct)
                                  ? result.atrPct.toFixed(2) + "%"
                                  : "вЂ”"
                              })`
                            : "вЂ”"
                        }
                        rightColor={C.sub}
                        sub={safeT(t, "explain.atrHint", "ATR")}
                      />

                      <Row
                        left={safeT(t, "explain.levels", "")}
                        right={
                          Number.isFinite(result.sup) && Number.isFinite(result.res)
                            ? `${safeT(t, "explain.support", "")} ${fmtUsd(
                                result.sup
                              )} • ${safeT(t, "explain.resistance", "")} ${fmtUsd(
                                result.res
                              )}`
                            : "вЂ”"
                        }
                        rightColor={C.sub}
                        sub={safeT(t, "explain.levelsHint", "")}
                      />
                    </View>
                  </BlurView>
                </View>

                <View style={[cardChrome(18), { marginTop: 12 }]}>
                  <BlurView intensity={24} tint="dark" style={{ padding: 16 }}>
                    <Text style={s.cardTitle}>
                      {safeT(t, "explain.miniGlossaryTitle", "")}
                    </Text>

                    <GlossItem
                      title="EMA20 / EMA50"
                      text={safeT(t, "explain.gEma", "EMA shows trend direction.")}
                    />

                    <GlossItem
                      title="RSI(14)"
                      text={safeT(t, "explain.gRsi", "RSI shows market momentum.")}
                    />

                    <GlossItem
                      title="ATR(14)"
                      text={safeT(t, "explain.gAtr", "ATR shows volatility.")}
                    />

                    <GlossItem
                      title={safeT(t, "explain.levels", "")}
                      text={safeT(t, "explain.gLevels", "")}
                    />
                  </BlurView>
                </View>

                <View style={[cardChrome(18), { marginTop: 12 }]}>
                  <BlurView intensity={24} tint="dark" style={{ padding: 16 }}>
                    <Text style={s.cardTitle}>
                      {safeT(t, "explain.priceAction", "")}
                    </Text>

                    <MiniSparkline candles={result.ks} />

                    <Text style={[s.cardText, { marginTop: 8 }]}>
                      {safeT(t, "explain.sparkHint", "")}
                    </Text>
                  </BlurView>
                </View>
              </>
            )}

            <View style={[cardChrome(18), { marginTop: 14 }]}>
              <BlurView intensity={24} tint="dark" style={{ padding: 16 }}>
                <Text style={s.sectionTitle}>
                  {safeT(t, "explain.proTitle", "Explain PRO")}
                </Text>

                <View style={[s.proCard, { marginTop: 12 }]}>
                  <Text style={s.proTitle}>
                    {safeT(t, "explain.proTitle", "Explain PRO")}
                  </Text>

                  <Text style={s.proBody}>{safeT(t, "explain.proBody", "")}</Text>

                  <TouchableOpacity
                    activeOpacity={0.9}
                    onPress={() => {
                      logEvent("pro_opened", {
                        screen: "explain",
                        source: "pro_block",
                      });
                      openPro();
                    }}
                    style={s.proBtn}
                  >
                    <Text style={s.proBtnText}>
                      {safeT(t, "explain.proBtn", "")}
                    </Text>
                    <Ionicons name="arrow-forward" size={18} color="#0B1220" />
                  </TouchableOpacity>
                </View>

                <View style={{ marginTop: 14 }}>
                  <Text style={s.compareBlockTitle}>
                    {safeT(t, "explain.compareTitle", "")}
                  </Text>

                  <Text style={s.compareBlockSubtitle}>
                    {safeT(t, "explain.compareHint", "PRO")}
                  </Text>

                  <CompareTable t={t} />
                </View>
              </BlurView>
            </View>

            <View style={{ marginTop: 14, marginBottom: 10 }}>
              <Text style={s.disclaimer}>
                {safeT(t, "explain.disclaimer", "")}
              </Text>
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </LinearGradient>
  );
}

function Tag({ label, value, tone = "soft" }) {
  const bg =
    tone === "bad"
      ? "rgba(255,101,101,0.10)"
      : tone === "ok"
      ? "rgba(76,217,100,0.10)"
      : "rgba(255,255,255,0.06)";

  const brd =
    tone === "bad"
      ? "rgba(255,101,101,0.35)"
      : tone === "ok"
      ? "rgba(76,217,100,0.35)"
      : "rgba(255,255,255,0.10)";

  const col = tone === "bad" ? C.red : tone === "ok" ? C.green : C.text;

  return (
    <View
      style={{
        flex: 1,
        borderWidth: 1,
        borderColor: brd,
        backgroundColor: bg,
        borderRadius: 14,
        paddingVertical: 10,
        paddingHorizontal: 12,
      }}
    >
      <Text style={{ color: C.sub, fontWeight: "800", fontSize: 12 }}>{label}</Text>
      <Text style={{ color: col, fontWeight: "900", marginTop: 4 }}>{value}</Text>
    </View>
  );
}

function Row({ left, right, sub, rightColor = C.text }) {
  return (
    <View style={{ paddingVertical: 10 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 12 }}>
        <Text style={{ color: C.text, fontWeight: "900", flex: 1 }}>{left}</Text>
        <Text style={{ color: rightColor, fontWeight: "900", textAlign: "right" }}>
          {right}
        </Text>
      </View>

      {!!sub && <Text style={{ color: C.sub, marginTop: 6, lineHeight: 18 }}>{sub}</Text>}

      <View style={{ marginTop: 10, height: 1, backgroundColor: "rgba(255,255,255,0.06)" }} />
    </View>
  );
}

function GlossItem({ title, text }) {
  return (
    <View style={{ marginTop: 12 }}>
      <Text style={{ color: C.text, fontWeight: "900" }}>{title}</Text>

      <Text style={{ color: C.sub, marginTop: 6, lineHeight: 18, fontWeight: "600" }}>
        {text}
      </Text>

      <View style={{ marginTop: 10, height: 1, backgroundColor: "rgba(255,255,255,0.06)" }} />
    </View>
  );
}

function MiniSparkline({ candles }) {
  if (!candles?.length) return null;

  const closes = candles.slice(-72).map((c) => c.close);
  const max = Math.max(...closes);
  const min = Math.min(...closes);
  const range = Math.max(1e-9, max - min);

  return (
    <View
      style={{
        marginTop: 10,
        height: 62,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: "rgba(255,255,255,0.10)",
        backgroundColor: "rgba(255,255,255,0.03)",
        paddingHorizontal: 6,
        flexDirection: "row",
        alignItems: "flex-end",
        overflow: "hidden",
        gap: 2,
      }}
    >
      {closes.map((v, i) => {
        const h = ((v - min) / range) * 48 + 4;

        return (
          <View
            key={i}
            style={{
              width: 3,
              height: h,
              backgroundColor: "rgba(255,165,0,0.85)",
              borderTopLeftRadius: 3,
              borderTopRightRadius: 3,
            }}
          />
        );
      })}
    </View>
  );
}

function CompareTable({ t }) {
  const headFeature = safeT(t, "explain.compareFeature", "Feature");
  const headFree = safeT(t, "explain.compareFree", "FREE");
  const headPro = safeT(t, "explain.comparePro", "PRO");

  const rows = [
    {
      label: safeT(t, "explain.compareF1", "Market snapshot (trend/risk/momentum)"),
      free: true,
      pro: true,
    },
    {
      label: safeT(t, "explain.compareF2", "Indicators (EMA/RSI/ATR) + swing levels"),
      free: true,
      pro: true,
    },
    {
      label: safeT(t, "explain.compareF3", "Favorites + recents"),
      free: true,
      pro: true,
    },
    {
      label: safeT(t, "explain.compareF4", "Entry zone + stop + targets (scenarios)"),
      free: false,
      pro: true,
    },
    {
      label: safeT(t, "explain.compareF5", "Checklist (risk/news/liquidity) for discipline"),
      free: false,
      pro: true,
    },
    {
      label: safeT(t, "explain.compareF6", "History of PRO sessions"),
      free: false,
      pro: true,
    },
    {
      label: safeT(t, "explain.compareF7", "Compare tickers inside PRO"),
      free: false,
      pro: true,
    },
  ];

  return (
    <View style={s.compareBlockOuter}>
      <View style={s.compareTableCardClone}>
        <View style={s.compareHeadClone}>
          <Text style={s.compareHeadFeatureClone}>{headFeature}</Text>
          <Text style={s.compareHeadCellClone}>{headFree}</Text>
          <Text style={s.compareHeadCellClone}>{headPro}</Text>
        </View>

        {rows.map((row) => (
          <View key={row.label} style={s.compareRowClone}>
            <Text style={s.compareLabelClone}>{row.label}</Text>

            <Text style={[s.compareValueClone, { color: row.free ? C.green : C.red }]}>
              {row.free ? "✓" : "✕"}
            </Text>

            <Text style={[s.compareValueClone, { color: row.pro ? C.green : C.red }]}>
              {row.pro ? "✓" : "✕"}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const s = {
  h1: {
    color: C.accent,
    fontSize: 34,
    fontWeight: "900",
    letterSpacing: 0.3,
    marginTop: 8,
  },
  hSub: {
    color: C.sub,
    fontSize: 15,
    fontWeight: "700",
    marginTop: 6,
    lineHeight: 20,
  },

  quotaPillShield: {
    marginTop: 12,
    alignSelf: "flex-start",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
    backgroundColor: "rgba(255,255,255,0.06)",
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  quotaTextShield: {
    color: C.text,
    fontWeight: "900",
    fontSize: 13,
    opacity: 0.95,
  },

  sectionTitle: {
    color: C.text,
    fontSize: 16,
    fontWeight: "900",
  },

  cardTitle: {
    color: C.text,
    fontSize: 16,
    fontWeight: "900",
  },
  cardText: {
    color: C.sub,
    marginTop: 8,
    lineHeight: 20,
    fontWeight: "600",
  },

  searchWrap: {
    borderWidth: 1,
    borderColor: C.cardBorder,
    backgroundColor: "rgba(255,255,255,0.04)",
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: Platform.OS === "android" ? 10 : 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  searchInput: {
    flex: 1,
    color: C.text,
    fontSize: 16,
    fontWeight: "800",
  },

  btnMain: {
    flex: 1,
    backgroundColor: C.accent,
    borderRadius: 16,
    paddingVertical: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  btnMainText: {
    color: "#0B1220",
    fontWeight: "900",
    fontSize: 16,
  },

  chip: {
    borderWidth: 1,
    borderColor: C.cardBorder,
    backgroundColor: "rgba(255,255,255,0.04)",
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  chipText: {
    color: C.sub,
    fontWeight: "900",
    fontSize: 12,
  },

  miniLabel: {
    color: C.sub,
    fontWeight: "900",
    fontSize: 12,
    marginBottom: 8,
  },

  quickRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  quickChip: {
    borderWidth: 1,
    borderColor: "rgba(255,165,0,0.35)",
    backgroundColor: "rgba(255,165,0,0.10)",
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  quickText: {
    color: C.accent,
    fontWeight: "900",
    fontSize: 12,
  },
  quickChipAlt: {
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
    backgroundColor: "rgba(255,255,255,0.05)",
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  quickTextAlt: {
    color: C.text,
    fontWeight: "900",
    fontSize: 12,
  },

  scorePill: {
    borderWidth: 1,
    borderRadius: 999,
    paddingVertical: 6,
    paddingHorizontal: 10,
    backgroundColor: "rgba(255,255,255,0.04)",
  },
  scoreText: {
    fontWeight: "900",
    fontSize: 12,
  },

  iconBtn: {
    borderWidth: 1,
    borderColor: C.cardBorder,
    backgroundColor: "rgba(255,255,255,0.05)",
    borderRadius: 999,
    padding: 8,
  },

  bigPrice: {
    color: C.text,
    fontSize: 30,
    fontWeight: "900",
    marginBottom: 4,
  },
  smallLine: {
    color: C.sub,
    fontWeight: "700",
    marginTop: 2,
  },

  kpiCard: {
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.10)",
    backgroundColor: "rgba(255,255,255,0.03)",
    borderRadius: 14,
    padding: 12,
  },
  kpiLabel: {
    color: C.sub,
    fontWeight: "900",
    fontSize: 12,
  },
  kpiValue: {
    color: C.text,
    fontWeight: "900",
    marginTop: 6,
  },

  table: {
    marginTop: 8,
  },

  disclaimer: {
    color: "rgba(168,180,207,0.85)",
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 18,
    textAlign: "center",
  },

  proCard: {
    borderWidth: 1,
    borderColor: "rgba(255,165,0,0.25)",
    backgroundColor: "rgba(255,165,0,0.10)",
    borderRadius: 16,
    padding: 14,
  },
  proTitle: {
    color: C.accent,
    fontWeight: "900",
    fontSize: 16,
  },
  proBody: {
    color: C.text,
    opacity: 0.9,
    marginTop: 8,
    lineHeight: 20,
    fontWeight: "700",
  },
  proBtn: {
    marginTop: 12,
    backgroundColor: C.accent,
    borderRadius: 14,
    paddingVertical: 12,
    paddingHorizontal: 14,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
  },
  proBtnText: {
    color: "#0B1220",
    fontWeight: "900",
    fontSize: 15,
  },

  compareBlockTitle: {
    color: C.text,
    fontSize: 18,
    fontWeight: "900",
    marginBottom: 8,
  },
  compareBlockSubtitle: {
    color: C.sub,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: "700",
    marginBottom: 14,
  },

  compareBlockOuter: {
    marginTop: 2,
  },
  compareTableCardClone: {
    borderWidth: 1,
    borderColor: C.cardBorder,
    borderRadius: 18,
    padding: 12,
    backgroundColor: "rgba(255,255,255,0.02)",
  },
  compareHeadClone: {
    flexDirection: "row",
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255,255,255,0.06)",
    marginBottom: 4,
  },
  compareHeadFeatureClone: {
    flex: 2,
    color: C.sub,
    fontWeight: "900",
    fontSize: 12,
  },
  compareHeadCellClone: {
    flex: 1,
    color: C.sub,
    fontWeight: "900",
    fontSize: 12,
    textAlign: "center",
  },
  compareRowClone: {
    flexDirection: "row",
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: "rgba(255,255,255,0.04)",
  },
  compareLabelClone: {
    flex: 2,
    color: C.text,
    fontSize: 13,
    lineHeight: 18,
  },
  compareValueClone: {
    flex: 1,
    textAlign: "center",
    fontSize: 14,
    fontWeight: "900",
  },

  limitCard: {
    borderWidth: 1,
    borderColor: "rgba(255,165,0,0.25)",
    backgroundColor: "rgba(255,165,0,0.10)",
    borderRadius: 16,
    padding: 14,
  },
  limitTitle: {
    color: C.text,
    fontWeight: "900",
    fontSize: 16,
  },
  limitBody: {
    color: C.sub,
    marginTop: 8,
    lineHeight: 20,
    fontWeight: "700",
  },
  limitBtn: {
    marginTop: 12,
    backgroundColor: C.accent,
    borderRadius: 14,
    paddingVertical: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  limitBtnText: {
    color: "#0B1220",
    fontWeight: "900",
    fontSize: 15,
  },
};

