
import React, { useCallback, useMemo, useState, useEffect, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  Platform,
  Share,
} from "react-native";
import { Stack } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import AsyncStorage from "@react-native-async-storage/async-storage";
import ViewShot from "react-native-view-shot";
import * as Sharing from "expo-sharing";
import { Ionicons } from "@expo/vector-icons";
import { useTranslation } from "react-i18next";

import { useAuthStore } from "./lib/store.auth";
import { API } from "./lib/backend";
import { showAppAlert } from "./lib/appAlert";


const GRAD = { bgStart: "#06080f", bgMid: "#0a1233", bgEnd: "#0b1c4f" };
const C = {
  text: "#FFFFFF",
  sub: "#A8B4CF",
  accent: "#FFA500",
  red: "#FF6565",
  green: "#4CD964",
  cardBorder: "rgba(255,255,255,0.10)",
};

const T = {
  text: C.text,
  soft: C.sub,
  acc: "#66B3FF",
  good: "#29D37A",
  bad: "#FF6B6B",
  warn: "#FFB84D",
  gold: "#FFB020",
  logo: "#ffb020",
  accent: "#ffb020",
  accentText: "#0b1220",
  border: "rgba(255,255,255,0.10)",
  borderSoft: "rgba(255,255,255,0.07)",
  dim: "#A8B4CF",
};

const cardChrome = {
  backgroundColor: "rgba(255,255,255,0.04)",
  borderWidth: 1,
  borderColor: C.cardBorder,
  borderRadius: 16,
};

function safeT(t, key, fallback, vars) {
  const v = t(key, { ...vars, defaultValue: fallback });
  if (!v) return fallback;
  if (typeof v === "string" && v.trim() === key) return fallback;
  return v;
}

function sideLabel(t, side) {
  if (side === "long") return safeT(t, "futuresPro.side.long", "LONG");
  if (side === "short") return safeT(t, "futuresPro.side.short", "SHORT");
  return "—";
}


const uidFromUser = (u) =>
  (u?.email || u?.nick || u?.name || u?.login || u?.username || "default")
    .toString()
    .trim()
    .toLowerCase();

const FT_USER = (uid) => `profile.${uid}:futures_trades`;
const PRO_SESSIONS_KEY = (uid) => `profile.${uid}:futures_pro_sessions.v1`;
const PRO_CHECKLIST_KEY = (uid) => `profile.${uid}:futures_pro_checklist.v1`;
const LAST_KEY = "futures:last";


const num = (v, d = 0) => {
  const x =
    typeof v === "number"
      ? v
      : parseFloat(String(v ?? "").replace(/[^0-9.\-]/g, ""));
  return Number.isFinite(x) ? x : d;
};

const usd = (x) => {
  const v = num(x, NaN);
  if (!Number.isFinite(v)) return "—";
  if (v >= 1000) return "$" + v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (v >= 1) return "$" + v.toFixed(2);
  if (v >= 0.1) return "$" + v.toFixed(3);
  if (v >= 0.01) return "$" + v.toFixed(4);
  if (v >= 0.001) return "$" + v.toFixed(5);
  return "$" + v.toFixed(6);
};

const pct = (x) => {
  const v = num(x, NaN);
  if (!Number.isFinite(v)) return "—";
  const s = v >= 0 ? "+" : "";
  return `${s}${v.toFixed(2)}%`;
};

const clamp = (x, a, b) => Math.max(a, Math.min(b, x));

function labelLiquidity(quoteVolUsd) {
  if (!Number.isFinite(quoteVolUsd)) return "unknown";
  if (quoteVolUsd >= 2_000_000_000) return "ultra";
  if (quoteVolUsd >= 700_000_000) return "high";
  if (quoteVolUsd >= 150_000_000) return "mid";
  return "low";
}

function toneFromTrend(plan) {
  if (!plan) return T.dim;
  if (plan.side === "long") return T.good;
  if (plan.side === "short") return T.bad;
  return T.warn;
}

function normalizeSymbol(v) {
  const s = String(v || "")
    .toUpperCase()
    .replace(/\s+/g, "")
    .replace("/", "");
  if (!s) return "";
  if (s.endsWith("USDT")) return s;
  if (/^[A-Z0-9]{2,20}$/.test(s)) return `${s}USDT`;
  return s;
}


async function getKlines(symbol, interval = "1h", limit = 300) {
  const url = `https://api.binance.com/api/v3/klines?symbol=${encodeURIComponent(
    symbol
  )}&interval=${interval}&limit=${limit}`;
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

async function getTickerLast(symbol) {
  const r = await fetch(
    `https://api.binance.com/api/v3/ticker/price?symbol=${encodeURIComponent(symbol)}`
  );
  if (!r.ok) throw new Error("HTTP " + r.status);
  const j = await r.json();
  return num(j.price);
}

async function getTicker24h(symbol) {
  const url = `https://api.binance.com/api/v3/ticker/24hr?symbol=${encodeURIComponent(symbol)}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error("HTTP " + r.status);
  const j = await r.json();
  return {
    ch24: num(j.priceChangePercent, NaN),
    quoteVol: num(j.quoteVolume, NaN),
    high: num(j.highPrice, NaN),
    low: num(j.lowPrice, NaN),
  };
}


function ema(values, period) {
  const p = Math.max(1, period | 0);
  const out = [];
  const k = 2 / (p + 1);
  let prev = null;
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
  let g = 0,
    l = 0;
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
  const list = [];
  for (let i = 0; i < hlc.length; i++) {
    const h = hlc[i].high,
      lw = hlc[i].low;
    const pc = i > 0 ? hlc[i - 1].close : h;
    const tr = Math.max(h - lw, Math.abs(h - pc), Math.abs(lw - pc));
    list.push(tr);
    if (list.length > period) list.shift();
    if (list.length === period) out[i] = list.reduce((a, b) => a + b, 0) / period;
  }
  return out;
}

function swingLevels(c, lookback = 30) {
  if (!c?.length) return { sup: NaN, res: NaN };
  const t = c.slice(-lookback);
  return {
    sup: Math.min(...t.map((x) => x.low)),
    res: Math.max(...t.map((x) => x.high)),
  };
}


function buildPlan(candles) {
  if (!candles?.length) return null;
  const closes = candles.map((c) => c.close);
  const hlc = candles.map((c) => ({ high: c.high, low: c.low, close: c.close }));
  const e20 = ema(closes, 20);
  const e50 = ema(closes, 50);
  const r = rsi(closes, 14);
  const a = atr(hlc, 14);
  const last = candles[candles.length - 1];

  const ema20Last = e20[e20.length - 1];
  const ema50Last = e50[e50.length - 1];

  let trendKey = "flat";
  if (ema20Last > ema50Last) trendKey = "up";
  else if (ema20Last < ema50Last) trendKey = "down";

  const side = trendKey === "down" ? "short" : "long";
  const { sup, res } = swingLevels(candles, 30);
  const lastAtr = a[a.length - 1] || 0;

  const buyMin = Math.max(0, ema20Last - 0.5 * lastAtr);
  const buyMax = ema20Last + 0.3 * lastAtr;

  const stop =
    side === "long"
      ? Math.min(sup, buyMin - 0.8 * lastAtr)
      : Math.max(res, buyMax + 0.8 * lastAtr);

  const t1 =
    side === "long"
      ? Math.min(res, last.close + 1.0 * lastAtr)
      : Math.max(sup, last.close - 1.0 * lastAtr);
  const t2 =
    side === "long"
      ? Math.min(res * 1.01, last.close + 1.8 * lastAtr)
      : Math.max(sup * 0.99, last.close - 1.8 * lastAtr);

  const atrPct =
    Number.isFinite(lastAtr) && Number.isFinite(last?.close)
      ? (lastAtr / last.close) * 100
      : NaN;

  return {
    last: last.close,
    side,
    trendKey,
    e20: ema20Last,
    e50: ema50Last,
    rsi: r[r.length - 1],
    atr: lastAtr,
    atrPct,
    sup,
    res,
    zone: [buyMin, buyMax],
    stop,
    t1,
    t2,
  };
}

function scoreFromSignals({ trendKey, rsiVal, atrPct, ch24 }) {
  let s = 50;

  if (trendKey === "up") s += 10;
  if (trendKey === "down") s -= 10;

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


function backtestEMA(candles) {
  if (!candles || candles.length < 60) return null;
  const closes = candles.map((c) => c.close);
  const e20 = ema(closes, 20);
  const e50 = ema(closes, 50);

  let pos = null,
    entry = 0,
    pnl = 0,
    trades = 0;
  for (let i = 50; i < closes.length; i++) {
    if (!pos && e20[i] > e50[i]) {
      pos = "long";
      entry = closes[i];
      trades++;
    }
    if (pos === "long" && e20[i] < e50[i]) {
      pnl += ((closes[i] - entry) / entry) * 100;
      pos = null;
    }
  }
  if (pos === "long") {
    pnl += ((closes[closes.length - 1] - entry) / entry) * 100;
  }
  return { pnl: Number(pnl.toFixed(2)), trades };
}


const TOP = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "TONUSDT", "ADAUSDT", "LINKUSDT", "TRXUSDT"];


async function captureShare(ref, fileName) {
  if (!ref?.current) return null;
  const uri = await ref.current.capture?.({
    format: "png",
    quality: 1,
    result: Platform.OS === "web" ? "base64" : "tmpfile",
  });
  if (!uri) return null;

  if (Platform.OS === "web") {
    const a = document.createElement("a");
    a.href = `data:image/png;base64,${uri}`;
    a.download = `${fileName}.png`;
    a.click();
    return uri;
  }

  return uri;
}


const defaultChecklist = {
  risk: false,
  liquidity: false,
  news: false,
  plan: false,
  size: false,
};

export default function FuturesPro() {
  const user = useAuthStore((s) => s.user);
  const uid = useMemo(() => uidFromUser(user), [user]);
  const { t } = useTranslation();

  const [symbol, setSymbol] = useState("BTCUSDT");
  const [symbolInput, setSymbolInput] = useState("");
  const [interval, setIntervalState] = useState("1h");

  const [candles, setCandles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [plan, setPlan] = useState(null);
  const [err, setErr] = useState("");
  const [hasAnalyzed, setHasAnalyzed] = useState(false);

  const [tfOverview, setTfOverview] = useState(null);

  const [pos, setPos] = useState(null);
  const [lastPrice, setLastPrice] = useState(null);

  const [account, setAccount] = useState("");
  const [riskPct, setRiskPct] = useState("1");
  const [levText, setLevText] = useState("10");

  const [newsHint, setNewsHint] = useState(null);
  const [newsLoading, setNewsLoading] = useState(false);

  const [refreshing, setRefreshing] = useState(false);
  const [ticker24, setTicker24] = useState(null);
  const [score, setScore] = useState(null);

  const [sessions, setSessions] = useState([]);
  const [showHistory, setShowHistory] = useState(true);

  const [checklist, setChecklist] = useState(defaultChecklist);

  const [compareSym, setCompareSym] = useState("ETHUSDT");
  const [compareData, setCompareData] = useState(null);
  const [compareLoading, setCompareLoading] = useState(false);

  const shareShotRef = useRef(null);

  useEffect(() => {
    AsyncStorage.getItem(LAST_KEY).then((v) => {
      if (!v) return;
      try {
        const j = JSON.parse(v);
        if (j?.symbol) {
          setSymbol(j.symbol);
          setSymbolInput(j.symbol.replace("USDT", ""));
        }
        if (j?.interval) setIntervalState(j.interval);
      } catch {}
    });
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const rawS = await AsyncStorage.getItem(PRO_SESSIONS_KEY(uid));
        const list = rawS ? JSON.parse(rawS) : [];
        setSessions(Array.isArray(list) ? list : []);
      } catch {
        setSessions([]);
      }

      try {
        const rawC = await AsyncStorage.getItem(PRO_CHECKLIST_KEY(uid));
        const c = rawC ? JSON.parse(rawC) : null;
        setChecklist({ ...defaultChecklist, ...(c && typeof c === "object" ? c : {}) });
      } catch {
        setChecklist(defaultChecklist);
      }
    })();
  }, [uid]);

  const persistChecklist = useCallback(
    async (next) => {
      setChecklist(next);
      try {
        await AsyncStorage.setItem(PRO_CHECKLIST_KEY(uid), JSON.stringify(next));
      } catch {}
    },
    [uid]
  );

  const toggleCheck = useCallback(
    (k) => {
      const next = { ...checklist, [k]: !checklist[k] };
      persistChecklist(next);
    },
    [checklist, persistChecklist]
  );

  const effectiveSymbol = useMemo(() => {
    const manual = normalizeSymbol(symbolInput);
    return manual || symbol;
  }, [symbolInput, symbol]);

  const load = useCallback(async () => {
    const finalSymbol = normalizeSymbol(symbolInput) || symbol;
    if (!finalSymbol) {
      showAppAlert(safeT(t,"futuresPro.alert.errorTitle", "Error"),
        safeT(t, "futuresPro.enterPairFirst", "Enter pair first.")
      );
      return;
    }

    try {
      setErr("");
      setLoading(true);
      setCompareData(null);
      setHasAnalyzed(true);

      setSymbol(finalSymbol);
      await AsyncStorage.setItem(LAST_KEY, JSON.stringify({ symbol: finalSymbol, interval })).catch(() => {});

      const [ks, tk24] = await Promise.all([
        getKlines(finalSymbol, interval, 300),
        getTicker24h(finalSymbol).catch(() => null),
      ]);

      const p = buildPlan(ks);
      setCandles(ks);
      setPlan(p);
      setTicker24(tk24);

      if (p) {
        const sc = scoreFromSignals({
          trendKey: p.trendKey,
          rsiVal: p.rsi,
          atrPct: p.atrPct,
          ch24: tk24?.ch24,
        });
        setScore(sc);
      } else {
        setScore(null);
      }

      const frames = ["1h", "4h", "1d"];
      const ctx = {};
      await Promise.all(
        frames.map(async (tf) => {
          try {
            const data = tf === interval ? ks : await getKlines(finalSymbol, tf, 200);
            const p2 = buildPlan(data);
            if (p2) ctx[tf] = { trendKey: p2.trendKey, side: p2.side };
          } catch {}
        })
      );
      setTfOverview(ctx);

      if (p) {
        const item = makeSessionItem({
          symbol: finalSymbol,
          interval,
          plan: p,
          tk24,
          score: scoreFromSignals({
            trendKey: p.trendKey,
            rsiVal: p.rsi,
            atrPct: p.atrPct,
            ch24: tk24?.ch24,
          }),
        });
        await pushSession(uid, item, setSessions);
      }
    } catch (e) {
      setErr(safeT(t, "futuresPro.errorLoadPair", "Failed to load the pair."));
      setCandles([]);
      setPlan(null);
      setTfOverview(null);
      setTicker24(null);
      setScore(null);
    } finally {
      setLoading(false);
    }
  }, [symbolInput, symbol, interval, t, uid]);

  const onRefresh = useCallback(async () => {
    if (!hasAnalyzed) return;
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load, hasAnalyzed]);

  const closes = useMemo(() => candles.slice(-60).map((c) => c.close), [candles]);
  const bt = useMemo(() => backtestEMA(candles.slice(-240)), [candles]);

  const scoreTone = useMemo(() => {
    const s = num(score, NaN);
    if (!Number.isFinite(s)) return { color: C.sub, border: "rgba(255,255,255,0.14)", bg: "rgba(255,255,255,0.06)" };
    if (s >= 70) return { color: T.good, border: "rgba(41,211,122,0.35)", bg: "rgba(41,211,122,0.10)" };
    if (s >= 50) return { color: C.accent, border: "rgba(255,165,0,0.35)", bg: "rgba(255,165,0,0.10)" };
    return { color: T.bad, border: "rgba(255,107,107,0.35)", bg: "rgba(255,107,107,0.10)" };
  }, [score]);

  const liq = useMemo(() => labelLiquidity(ticker24?.quoteVol), [ticker24?.quoteVol]);

  const riskBlock = useMemo(() => {
    if (!plan) return null;
    const balance = num(account, 0);
    const rPct = num(riskPct, 1);
    if (!balance || !rPct) return { balance: 0, rPct, entry: plan.last, stop: plan.stop };

    const entry = plan.last;
    const stop = plan.stop;
    const diffAbs = Math.abs(entry - stop);
    if (!diffAbs) return { balance, rPct, entry, stop };

    const riskMoney = (balance * rPct) / 100;
    const qty = riskMoney / diffAbs;
    const notional = qty * entry;

    let lev = num(levText, 10);
    if (!lev || lev < 1) lev = 1;
    if (lev > 125) lev = 125;

    const margin = notional / lev;
    const rr1 = Math.abs(plan.t1 - entry) / diffAbs;
    const rr2 = Math.abs(plan.t2 - entry) / diffAbs;
    const stopPct = (diffAbs / entry) * 100;

    let modeKey = "moderate";
    if (rPct <= 0.5 && lev <= 5) modeKey = "veryConservative";
    else if (rPct > 1.5 || lev >= 20) modeKey = "high";

    const warning =
      margin > balance ? safeT(t, "futuresPro.risk.warningNotEnoughBalance", "Not enough margin: reduce size/leverage.") : "";

    return { balance, rPct, entry, stop, riskMoney, qty, notional, lev, margin, rr1, rr2, stopPct, modeKey, warning };
  }, [plan, account, riskPct, levText, t]);

  const stopInfo = useMemo(() => {
    if (!plan) return null;
    const entry = plan.last;
    const stop = plan.stop;
    const distAbs = Math.abs(entry - stop);
    const pctV = entry ? (distAbs / entry) * 100 : 0;
    return { entry, stop, distAbs, pct: pctV };
  }, [plan]);

  const rangeInfo = useMemo(() => {
    if (!plan || !candles.length) return null;
    const slice = candles.slice(-60);
    const highs = slice.map((c) => c.high);
    const lows = slice.map((c) => c.low);
    const maxH = Math.max(...highs);
    const minL = Math.min(...lows);
    const range = Math.max(1e-9, maxH - minL);
    const last = plan.last;
    const pos01 = (last - minL) / range;

    let zoneKey = "middle";
    if (pos01 >= 0.8) zoneKey = "top";
    else if (pos01 <= 0.2) zoneKey = "bottom";

    return { maxH, minL, pos: pos01, zoneKey };
  }, [plan, candles]);

  useEffect(() => {
    if (!plan) {
      setNewsHint(null);
      return;
    }
    let cancelled = false;

    const run = async () => {
      try {
        setNewsLoading(true);
        setNewsHint(null);

        const base = symbol.replace(/USDT|BUSD|USDC|USD/gi, "").toUpperCase();
        const now = new Date();
        const d1 = now.toISOString();
        const d2 = new Date(now.getTime() + 60 * 60 * 1000).toISOString();

        const url = API + "/events?d1=" + encodeURIComponent(d1) + "&d2=" + encodeURIComponent(d2);
        const resp = await fetch(url);
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const j = await resp.json();

        let list = [];
        if (Array.isArray(j)) list = j;
        else if (Array.isArray(j.events)) list = j.events;
        else if (Array.isArray(j.items)) list = j.items;
        else if (Array.isArray(j.data)) list = j.data;

        const relevant = (list || []).filter((ev) => {
          try {
            const txt = JSON.stringify(ev || {}).toUpperCase();
            return txt.includes(base);
          } catch {
            return false;
          }
        });

        if (cancelled) return;

        if (relevant.length > 0) {
          setNewsHint(
            safeT(t, "futuresPro.news.withEvents", "There are events for {{base}} within the next hour.", { base })
          );
        } else {
          setNewsHint(
            safeT(t, "futuresPro.news.noEvents", "No events found for {{base}} within the next hour.", { base })
          );
        }
      } catch {
        if (!cancelled) setNewsHint(safeT(t, "futuresPro.news.error", "Failed to check events."));
      } finally {
        if (!cancelled) setNewsLoading(false);
      }
    };

    run();
    return () => {
      cancelled = true;
    };
  }, [plan, symbol, t]);

  const openPosition = async () => {
    if (!plan) return;
    try {
      const last = await getTickerLast(symbol);
      setPos({ side: plan.side, entry: last, time: Date.now() });
      showAppAlert(safeT(t,"futuresPro.alert.positionOpened.title", "Position marked"),
        safeT(t, "futuresPro.alert.positionOpened.body", "{{side}} at {{price}}", {
          side: sideLabel(t, plan.side),
          price: usd(last),
        })
      );
    } catch {
      showAppAlert(safeT(t,"futuresPro.alert.errorTitle", "Error"),
        safeT(t, "futuresPro.alert.errorGetEntryPrice", "Failed to get entry price.")
      );
    }
  };

  const refreshPrice = async () => {
    try {
      const p = await getTickerLast(symbol);
      setLastPrice(p);
    } catch {
      showAppAlert(safeT(t,"futuresPro.alert.errorTitle", "Error"),
        safeT(t, "futuresPro.alert.errorGetPrice", "Failed to get price.")
      );
    }
  };

  const closePosition = async () => {
    if (!pos) {
      showAppAlert(safeT(t,"futuresPro.alert.noPositionTitle", "No position"),
        safeT(t, "futuresPro.alert.noPositionBody", "Mark entry first.")
      );
      return;
    }
    if (!Number.isFinite(lastPrice)) {
      showAppAlert(safeT(t,"futuresPro.alert.noPriceTitle", "No price"),
        safeT(t, "futuresPro.alert.noPriceBody", "Refresh price first.")
      );
      return;
    }

    const pnlPct =
      pos.side === "long" ? ((lastPrice - pos.entry) / pos.entry) * 100 : ((pos.entry - lastPrice) / pos.entry) * 100;

    try {
      if (uid) {
        const key = FT_USER(uid);
        let list = [];
        const raw = await AsyncStorage.getItem(key);
        if (raw) {
          try {
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) list = parsed;
          } catch {}
        }

        const trade = {
          id: Date.now().toString(),
          symbol,
          side: pos.side,
          entry: pos.entry,
          exit: lastPrice,
          pnlPct: Number(pnlPct.toFixed(2)),
          frame: interval,
          riskPct: num(riskPct, 0),
          at: new Date().toISOString(),
        };

        list.unshift(trade);
        if (list.length > 50) list = list.slice(0, 50);
        await AsyncStorage.setItem(key, JSON.stringify(list));
      }
    } catch {}

    showAppAlert(safeT(t,"futuresPro.alert.positionClosed.title", "Position closed"),
      safeT(t, "futuresPro.alert.positionClosed.body", "Entry {{entry}} → Exit {{exit}} ({{pnl}})", {
        entry: usd(pos.entry),
        exit: usd(lastPrice),
        pnl: `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%`,
      })
    );

    setPos(null);
    setLastPrice(null);
  };

  const advise = useMemo(() => {
    if (!plan) return "";

    const lines = [
      safeT(t, "futuresPro.advise.line1", "Trend: {{trend}} | EMA20 {{ema20}} / EMA50 {{ema50}} | RSI {{rsi}}", {
        trend: safeT(t, `futuresPro.trend.${plan.trendKey}`, plan.trendKey),
        ema20: usd(plan.e20),
        ema50: usd(plan.e50),
        rsi: Number.isFinite(plan.rsi) ? plan.rsi.toFixed(1) : "—",
      }),
      safeT(t, "futuresPro.advise.line2", "ATR {{atr}} | Support {{sup}} | Resistance {{res}}", {
        atr: usd(plan.atr),
        sup: usd(plan.sup),
        res: usd(plan.res),
      }),
      safeT(t, "futuresPro.advise.line3", "Entry zone {{zoneMin}}–{{zoneMax}} | Stop {{stop}}", {
        zoneMin: usd(plan.zone[0]),
        zoneMax: usd(plan.zone[1]),
        stop: usd(plan.stop),
      }),
      safeT(t, "futuresPro.advise.line4", "Targets: T1 {{t1}} | T2 {{t2}}", {
        t1: usd(plan.t1),
        t2: usd(plan.t2),
      }),
    ];

    if (pos) {
      lines.push("");
      lines.push(
        safeT(t, "futuresPro.advise.positionLine", "{{side}} entry {{entry}} • {{trendComment}}", {
          side: sideLabel(t, pos.side),
          entry: usd(pos.entry),
          trendComment:
            pos.side === plan.side
              ? safeT(t, "futuresPro.advise.trendSame", "Trend still aligned")
              : safeT(t, "futuresPro.advise.trendChanged", "Trend changed vs entry"),
        })
      );
    }

    return lines.join("\n");
  }, [plan, pos, t]);

  const sharePlan = useCallback(async () => {
    if (!plan) return;

    const shareText =
      `${safeT(t, "futuresPro.title", "Explain")}: ${symbol.replace("USDT", "/USDT")} • ${interval.toUpperCase()}\n` +
      `${safeT(t, "futuresPro.score", "Score")}: ${Number.isFinite(score) ? `${score}/100` : "—"}\n` +
      `${safeT(t, "futuresPro.trendLabel", "Trend") || safeT(t, "futuresPro.trendTitle", "Trend") || "Trend"}: ${safeT(t, `futuresPro.trend.${plan.trendKey}`, plan.trendKey)} • ${sideLabel(t, plan.side)}\n` +
      `${safeT(t, "futuresPro.entryZone", "Entry zone")}: ${usd(plan.zone[0])} – ${usd(plan.zone[1])}\n` +
      `${safeT(t, "futuresPro.stop", "Stop")}: ${usd(plan.stop)}\n` +
      `${safeT(t, "futuresPro.targets", "Targets")}: T1 ${usd(plan.t1)} • T2 ${usd(plan.t2)}`;

    try {
      if (!(await Sharing.isAvailableAsync())) {
        await Share.share({ message: shareText });
        return;
      }

      const fileName = `ExplainPRO_${symbol}_${interval.toUpperCase()}`;
      const uri = await captureShare(shareShotRef, fileName);

      if (uri) {
        await Sharing.shareAsync(uri, {
          dialogTitle: fileName,
          UTI: "public.png",
          mimeType: "image/png",
        });
        return;
      }

      await Share.share({ message: shareText });
    } catch {
      await Share.share({ message: shareText });
    }
  }, [plan, symbol, interval, score, t]);

  const manualSaveSession = useCallback(async () => {
    if (!plan) return;
    const item = makeSessionItem({ symbol, interval, plan, tk24: ticker24, score });
    await pushSession(uid, item, setSessions);
    showAppAlert(safeT(t,"futuresPro.history.savedTitle", "Saved"),
      safeT(t, "futuresPro.history.savedBody", "Session saved to history.")
    );
  }, [plan, symbol, interval, uid, ticker24, score, t]);

  const restoreSession = useCallback(
    async (it) => {
      if (!it?.symbol || !it?.interval) return;
      setSymbol(it.symbol);
      setSymbolInput(it.symbol.replace("USDT", ""));
      setIntervalState(it.interval);
      if (typeof it?.riskPct === "string") setRiskPct(it.riskPct);
      if (typeof it?.levText === "string") setLevText(it.levText);
      if (typeof it?.account === "string") setAccount(it.account);
      showAppAlert(safeT(t,"futuresPro.history.restoredTitle", "Restored"),
        safeT(t, "futuresPro.history.restoredBody", "Session restored. Tap Analyze to refresh.")
      );
    },
    [t]
  );

  const removeSession = useCallback(
    async (id) => {
      const next = sessions.filter((x) => x.id !== id);
      setSessions(next);
      try {
        await AsyncStorage.setItem(PRO_SESSIONS_KEY(uid), JSON.stringify(next));
      } catch {}
    },
    [sessions, uid]
  );

  const runCompare = useCallback(async () => {
    const a = symbol;
    const b = compareSym;

    if (!a || !b || a === b) {
      showAppAlert(safeT(t,"futuresPro.compare.errorTitle", "Compare"),
        safeT(t, "futuresPro.compare.errorBody", "Pick a different second ticker.")
      );
      return;
    }

    try {
      setCompareLoading(true);
      setCompareData(null);

      const [ksA, ksB, tkA, tkB] = await Promise.all([
        getKlines(a, interval, 260),
        getKlines(b, interval, 260),
        getTicker24h(a).catch(() => null),
        getTicker24h(b).catch(() => null),
      ]);

      const pA = buildPlan(ksA);
      const pB = buildPlan(ksB);

      if (!pA || !pB) throw new Error("no plan");

      const scA = scoreFromSignals({ trendKey: pA.trendKey, rsiVal: pA.rsi, atrPct: pA.atrPct, ch24: tkA?.ch24 });
      const scB = scoreFromSignals({ trendKey: pB.trendKey, rsiVal: pB.rsi, atrPct: pB.atrPct, ch24: tkB?.ch24 });

      setCompareData({
        a: { symbol: a, plan: pA, tk24: tkA, score: scA },
        b: { symbol: b, plan: pB, tk24: tkB, score: scB },
      });
    } catch {
      showAppAlert(safeT(t,"futuresPro.compare.errorTitle", "Compare"),
        safeT(t, "futuresPro.compare.loadFail", "Failed to load comparison. Try again.")
      );
    } finally {
      setCompareLoading(false);
    }
  }, [symbol, compareSym, interval, t]);

  return (
    <View style={{ flex: 1, backgroundColor: GRAD.bgEnd }}>
      <Stack.Screen options={{ headerShown: false }} />

      <LinearGradient
        colors={[GRAD.bgStart, GRAD.bgMid, GRAD.bgEnd]}
        style={{ flex: 1 }}
        start={{ x: 0, y: 0 }}
        end={{ x: 0, y: 1 }}
      >
        <ScrollView
          contentContainerStyle={{ padding: 14, paddingBottom: 40 }}
          refreshControl={<RefreshControl tintColor="#fff" refreshing={refreshing} onRefresh={onRefresh} />}
          showsVerticalScrollIndicator={false}
        >
          <View style={s.topTitleWrap}>
            <Text style={s.pageTitle}>{safeT(t, "futuresPro.title", "Explain")}</Text>
            <Text style={s.pageSub}>
              {safeT(t, "futuresPro.subtitle", "Choose a pair first, then get the setup.")}
            </Text>
          </View>

          <View style={s.card}>
            <Text style={s.blockTitle}>
              {safeT(t, "futuresPro.pairSelectionTitle", "Pair selection")}
            </Text>
            <Text style={s.blockSub}>
              {safeT(
                t,
                "futuresPro.pairSelectionSubtitle",
                "Choose from quick pairs or enter your own ticker manually."
              )}
            </Text>

            <View style={s.compactInputWrap}>
              <Ionicons name="search-outline" size={16} color={C.sub} />
              <TextInput
                value={symbolInput}
                onChangeText={setSymbolInput}
                placeholder={safeT(t, "futuresPro.pairInputPlaceholder", "BTC / ETH / SOL / XRP ...")}
                placeholderTextColor="#5f6a86"
                autoCapitalize="characters"
                autoCorrect={false}
                style={s.compactInput}
              />
              {!!effectiveSymbol ? (
                <View style={s.inputSymbolPill}>
                  <Text style={s.inputSymbolPillTxt}>{effectiveSymbol}</Text>
                </View>
              ) : null}
            </View>

            <View style={[s.chipsRow, { marginTop: 10 }]}>
              {TOP.map((p) => (
                <TouchableOpacity
                  key={p}
                  onPress={() => {
                    setSymbol(p);
                    setSymbolInput(p.replace("USDT", ""));
                  }}
                  activeOpacity={0.9}
                  style={[s.chip, effectiveSymbol === p && { backgroundColor: T.acc, borderColor: T.acc }]}
                >
                  <Text style={[s.chipTxt, effectiveSymbol === p && { color: "#08122a" }]}>
                    {p.replace("USDT", "/USDT")}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={[s.smallSectionLabel, { marginTop: 14 }]}>
              {safeT(t, "futuresPro.timeframe", "Timeframe")}
            </Text>
            <View style={s.chipsRow}>
              {["1h", "4h", "1d"].map((iv) => (
                <TouchableOpacity
                  key={iv}
                  onPress={() => setIntervalState(iv)}
                  activeOpacity={0.85}
                  style={[s.chip, interval === iv && { backgroundColor: T.acc, borderColor: T.acc }]}
                >
                  <Text style={[s.chipTxt, interval === iv && { color: "#08122a" }]}>{iv.toUpperCase()}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <View style={s.topActionRow}>
              <TouchableOpacity onPress={load} activeOpacity={0.9} style={s.controlBtnMain}>
                {loading ? <ActivityIndicator color="#0B1220" /> : <Ionicons name="search" size={16} color="#0B1220" />}
                <Text style={s.controlBtnMainTxt}>
                  {safeT(t, "futuresPro.btnAnalyze", "Analyze")}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity onPress={manualSaveSession} activeOpacity={0.9} style={s.controlBtnAlt} disabled={!plan}>
                <Ionicons name="bookmark-outline" size={16} color={C.accent} />
                <Text style={s.controlBtnAltTxt}>
                  {safeT(t, "futuresPro.btnSaveSession", "Save session")}
                </Text>
              </TouchableOpacity>
            </View>

            {!!err && <Text style={s.errText}>{err}</Text>}
          </View>

          {hasAnalyzed && plan ? (
            <>
              <View style={[s.card, { marginTop: 12, padding: 12 }]}>
                <View style={s.summaryTopRow}>
                  <View>
                    <Text style={s.summaryPair}>{symbol.replace("USDT", "/USDT")}</Text>
                    <Text style={s.summaryMeta}>
                      {interval.toUpperCase()} • {safeT(t, `futuresPro.trend.${plan.trendKey}`, plan.trendKey)}
                    </Text>
                  </View>

                  <View style={[s.scoreBadge, { borderColor: scoreTone.border, backgroundColor: scoreTone.bg }]}>
                    <Text style={[s.scoreBadgeTxt, { color: scoreTone.color }]}>
                      {safeT(t, "futuresPro.score", "Score")} • {Number.isFinite(score) ? `${score}/100` : "—"}
                    </Text>
                  </View>
                </View>

                <View style={s.miniStatsRow}>
                  <MiniStatBox label={safeT(t, "futuresPro.price", "Price")} value={usd(plan.last)} />
                  <MiniStatBox
                    label={safeT(t, "futuresPro.change24h", "24h")}
                    value={pct(ticker24?.ch24)}
                    valueColor={num(ticker24?.ch24, 0) >= 0 ? T.good : T.bad}
                  />
                  <MiniStatBox
                    label={safeT(t, "futuresPro.sideLabel", "Side")}
                    value={sideLabel(t, plan.side)}
                    valueColor={plan.side === "long" ? T.good : T.bad}
                  />
                  <MiniStatBox
                    label={safeT(t, "futuresPro.liquidity", "Liquidity")}
                    value={safeT(t, `futuresPro.liq.${liq}`, liq)}
                    valueColor={liq === "low" ? T.bad : liq === "mid" ? T.warn : T.good}
                  />
                </View>
              </View>

              <View style={[s.card, { marginTop: 12 }]}>
                <SectionHeader
                  title={safeT(t, "futuresPro.planTitle", "Plan")}
                  subtitle={safeT(t, "futuresPro.planSubtitle", "Compact setup overview.")}
                  right={
                    <PillSmall
                      label={`${safeT(t, "futuresPro.liquidity", "Liquidity")}: ${safeT(t, `futuresPro.liq.${liq}`, liq)}`}
                      tone={liq === "low" ? "bad" : liq === "mid" ? "warn" : "good"}
                    />
                  }
                />

                <View style={s.compactGrid}>
                  <CompactMetric title={safeT(t, "futuresPro.current", "Current")} value={usd(plan.last)} accent />
                  <CompactMetric
                    title={safeT(t, "futuresPro.trendLabel", "Trend") || safeT(t, "futuresPro.compare.trend", "Trend")}
                    value={`${safeT(t, `futuresPro.trend.${plan.trendKey}`, plan.trendKey)} • ${sideLabel(t, plan.side)}`}
                    valueColor={plan.side === "long" ? T.good : T.bad}
                  />
                  <CompactMetric title={safeT(t, "futuresPro.indicators.rsi", "RSI")} value={Number.isFinite(plan.rsi) ? plan.rsi.toFixed(1) : "—"} />
                  <CompactMetric
                    title={safeT(t, "futuresPro.indicators.atr", "ATR")}
                    value={`${usd(plan.atr)} • ${Number.isFinite(plan.atrPct) ? plan.atrPct.toFixed(2) + "%" : "—"}`}
                  />
                </View>

                {tfOverview && (
                  <View style={s.inlinePanel}>
                    <Text style={s.inlinePanelTitle}>
                      {safeT(t, "futuresPro.tfContextTitle", "Timeframe context")}
                    </Text>
                    <View style={s.contextRowCompact}>
                      {["1h", "4h", "1d"].map((tf) => {
                        const data = tfOverview[tf];
                        if (!data) return null;
                        const pretty = tf === "1h" ? "H1" : tf === "4h" ? "H4" : "1D";
                        const color = data.side === "long" ? T.good : data.side === "short" ? T.bad : T.soft;
                        return (
                          <View key={tf} style={s.contextCompactItem}>
                            <Text style={s.contextCompactTop}>{pretty}</Text>
                            <Text style={[s.contextCompactBottom, { color }]}>
                              {safeT(t, `futuresPro.trend.${data.trendKey}`, data.trendKey)}
                            </Text>
                          </View>
                        );
                      })}
                    </View>
                  </View>
                )}

                <View style={s.inlinePanel}>
                  <MiniSparkline closes={closes} />

                  <View style={s.planLevelGridCompact}>
                    <PlanBoxCompact title={safeT(t, "futuresPro.entryZone", "Entry zone")} value={`${usd(plan.zone[0])} – ${usd(plan.zone[1])}`} />
                    <PlanBoxCompact title={safeT(t, "futuresPro.stop", "Stop")} value={usd(plan.stop)} />
                    <PlanBoxCompact title={safeT(t, "futuresPro.target1", "Target 1")} value={usd(plan.t1)} />
                    <PlanBoxCompact title={safeT(t, "futuresPro.target2", "Target 2")} value={usd(plan.t2)} />
                  </View>

                  <View style={s.infoCapsuleRow}>
                    <InfoCapsule label={safeT(t, "futuresPro.indicators.ema20", "EMA20")} value={usd(plan.e20)} />
                    <InfoCapsule label={safeT(t, "futuresPro.indicators.ema50", "EMA50")} value={usd(plan.e50)} />
                    <InfoCapsule label={safeT(t, "futuresPro.levels.support", "Support")} value={usd(plan.sup)} />
                    <InfoCapsule label={safeT(t, "futuresPro.levels.resistance", "Resistance")} value={usd(plan.res)} />
                  </View>

                  {bt && (
                    <View style={[s.note, { marginTop: 10 }]}>
                      <Text style={s.noteTxt}>
                        {safeT(t, "futuresPro.backtestSummary", "Backtest ({{tf}}): {{trades}} trades • PnL {{pnl}}%", {
                          tf: interval.toUpperCase(),
                          trades: bt.trades,
                          pnl: `${bt.pnl >= 0 ? "+" : ""}${bt.pnl}`,
                        })}
                      </Text>
                    </View>
                  )}
                </View>

                <View style={s.actionRowCompact}>
                  <TouchableOpacity activeOpacity={0.9} onPress={openPosition} style={s.btnPrimary}>
                    <Text style={s.btnPrimaryTxt}>
                      {safeT(t, "futuresPro.btnEntered", "Mark entry")}
                    </Text>
                  </TouchableOpacity>

                  <TouchableOpacity activeOpacity={0.9} onPress={refreshPrice} style={s.btnGhost}>
                    <Text style={s.btnGhostTxt}>
                      {safeT(t, "futuresPro.btnRefreshPrice", "Refresh price")}
                    </Text>
                  </TouchableOpacity>

                  <TouchableOpacity activeOpacity={0.9} onPress={closePosition} style={s.btnWarn}>
                    <Text style={s.btnWarnTxt}>
                      {safeT(t, "futuresPro.btnClosed", "Close (log)")}
                    </Text>
                  </TouchableOpacity>
                </View>

                <ShareBtn label={safeT(t, "futuresPro.btnSharePlan", "Share plan")} onPress={sharePlan} />
              </View>

              <View style={[s.row2, { marginTop: 12 }]}>
                <View style={[s.card, s.row2Col]}>
                  <SectionHeader
                    title={safeT(t, "futuresPro.checklist.title", "Checklist")}
                    subtitle={safeT(t, "futuresPro.checklist.subtitle", "Before entry.")}
                    right={
                      <PillSmall
                        label={`${countDone(checklist)}/5`}
                        tone={countDone(checklist) >= 4 ? "good" : countDone(checklist) >= 2 ? "warn" : "bad"}
                      />
                    }
                  />

                  <View style={s.checklistCompact}>
                    <CheckRowCompact
                      checked={checklist.risk}
                      onPress={() => toggleCheck("risk")}
                      label={safeT(t, "futuresPro.checklist.riskTitle", "Risk rules")}
                    />
                    <CheckRowCompact
                      checked={checklist.liquidity}
                      onPress={() => toggleCheck("liquidity")}
                      label={safeT(t, "futuresPro.checklist.liqTitle", "Liquidity")}
                    />
                    <CheckRowCompact
                      checked={checklist.news}
                      onPress={() => toggleCheck("news")}
                      label={
                        newsLoading
                          ? safeT(t, "futuresPro.hints.eventsLoading", "Checking events…")
                          : newsHint || safeT(t, "futuresPro.checklist.newsTitle", "News/events")
                      }
                    />
                    <CheckRowCompact
                      checked={checklist.plan}
                      onPress={() => toggleCheck("plan")}
                      label={safeT(t, "futuresPro.checklist.planTitle", "Plan clarity")}
                    />
                    <CheckRowCompact
                      checked={checklist.size}
                      onPress={() => toggleCheck("size")}
                      label={safeT(t, "futuresPro.checklist.sizeTitle", "Position size")}
                    />
                  </View>
                </View>

                <View style={[s.card, s.row2Col]}>
                  <SectionHeader
                    title={safeT(t, "futuresPro.riskBlockTitle", "Position sizing")}
                    subtitle={safeT(t, "futuresPro.positionSizingSubtitle", "Compact calculator.")}
                  />

                  <View style={s.inputsGridCompact}>
                    <SmallInput
                      label={safeT(t, "futuresPro.input.depositLabel", "Deposit")}
                      value={account}
                      onChangeText={setAccount}
                      placeholder={safeT(t, "futuresPro.input.depositPlaceholder", "e.g. 500")}
                    />
                    <SmallInput
                      label={safeT(t, "futuresPro.input.riskLabel", "Risk %")}
                      value={riskPct}
                      onChangeText={setRiskPct}
                      placeholder="1"
                    />
                    <SmallInput
                      label={safeT(t, "futuresPro.input.leverageLabel", "Leverage")}
                      value={levText}
                      onChangeText={setLevText}
                      placeholder="10"
                    />
                  </View>

                  {riskBlock && riskBlock.balance > 0 ? (
                    <>
                      <View style={s.compactGrid}>
                        <CompactMetric title={safeT(t, "futuresPro.input.riskLabel", "Risk %")} value={`${usd(riskBlock.riskMoney)} • ${riskBlock.rPct.toFixed(2)}%`} valueColor={C.accent} />
                        <CompactMetric title={safeT(t, "futuresPro.risk.summaryQtyLabel", "Qty")} value={Number.isFinite(riskBlock.qty) ? `${riskBlock.qty.toFixed(4)}` : "—"} />
                        <CompactMetric title={safeT(t, "futuresPro.positionSizingNotional", "Notional")} value={usd(riskBlock.notional)} />
                        <CompactMetric title={safeT(t, "futuresPro.positionSizingMargin", "Margin")} value={`${usd(riskBlock.margin)} • x${riskBlock.lev.toFixed(0)}`} />
                      </View>

                      <View style={[s.note, { marginTop: 10 }]}>
                        <Text style={s.noteTxt}>
                          {safeT(t, "futuresPro.risk.summaryStop", "Stop distance {{stopPct}}% • RR1 {{rr1}} • RR2 {{rr2}}", {
                            stopPct: Number.isFinite(riskBlock.stopPct) ? riskBlock.stopPct.toFixed(2) : "—",
                            rr1: Number.isFinite(riskBlock.rr1) ? riskBlock.rr1.toFixed(2) : "—",
                            rr2: Number.isFinite(riskBlock.rr2) ? riskBlock.rr2.toFixed(2) : "—",
                          })}
                        </Text>
                        <Text
                          style={[
                            s.noteTxt,
                            {
                              marginTop: 4,
                              color:
                                riskBlock.modeKey === "high"
                                  ? T.bad
                                  : riskBlock.modeKey === "veryConservative"
                                  ? T.good
                                  : T.soft,
                            },
                          ]}
                        >
                          {safeT(t, `futuresPro.risk.mode.${riskBlock.modeKey}`, riskBlock.modeKey)}
                        </Text>
                        {!!riskBlock.warning && <Text style={[s.noteTxt, { color: T.bad, marginTop: 4 }]}>{riskBlock.warning}</Text>}
                      </View>
                    </>
                  ) : (
                    <Text style={s.p}>
                      {safeT(t, "futuresPro.risk.enterToSee", "Enter deposit to see position size.")}
                    </Text>
                  )}
                </View>
              </View>

              <View style={[s.card, { marginTop: 12 }]}>
                <SectionHeader
                  title={safeT(t, "futuresPro.compare.title", "Compare")}
                  subtitle={safeT(t, "futuresPro.compare.hint", "Compare this setup with another pair.")}
                  right={
                    <TouchableOpacity onPress={runCompare} activeOpacity={0.9} style={s.btnCompare}>
                      {compareLoading ? <ActivityIndicator color="#0B1220" /> : <Text style={s.btnCompareTxt}>{safeT(t, "futuresPro.compare.btn", "Compare")}</Text>}
                    </TouchableOpacity>
                  }
                />

                <View style={s.chipsRow}>
                  {TOP.filter((x) => x !== symbol).map((p) => (
                    <TouchableOpacity
                      key={p}
                      onPress={() => setCompareSym(p)}
                      activeOpacity={0.9}
                      style={[s.chip, compareSym === p && { backgroundColor: T.acc, borderColor: T.acc }]}
                    >
                      <Text style={[s.chipTxt, compareSym === p && { color: "#08122a" }]}>{p.replace("USDT", "/USDT")}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                {!!compareData && <View style={{ marginTop: 10 }}><CompareGrid a={compareData.a} b={compareData.b} /></View>}
              </View>

              <View style={[s.row2, { marginTop: 12 }]}>
                <View style={[s.card, s.row2Col]}>
                  <SectionHeader
                    title={safeT(t, "futuresPro.textExplainTitle", "Text explanation")}
                    subtitle={safeT(t, "futuresPro.textExplainSubtitle", "Text summary.")}
                  />
                  <Text style={s.mono}>{advise}</Text>

                  <View style={s.compactGridSingle}>
                    <CompactMetric title={safeT(t, "futuresPro.levels.support", "Support")} value={usd(plan.sup)} />
                    <CompactMetric title={safeT(t, "futuresPro.levels.resistance", "Resistance")} value={usd(plan.res)} />
                    <CompactMetric
                      title={safeT(t, "futuresPro.stopDistance", "Stop distance")}
                      value={stopInfo && Number.isFinite(stopInfo.pct) ? `${stopInfo.pct.toFixed(2)}%` : "—"}
                      valueColor={T.warn}
                    />
                    <CompactMetric
                      title={safeT(t, "futuresPro.range.title", "Range position")}
                      value={rangeInfo ? safeT(t, `futuresPro.range.${rangeInfo.zoneKey}`, rangeInfo.zoneKey) : "—"}
                      valueColor={
                        rangeInfo?.zoneKey === "top"
                          ? T.bad
                          : rangeInfo?.zoneKey === "bottom"
                          ? T.good
                          : C.sub
                      }
                    />
                  </View>
                </View>

                <View style={[s.card, s.row2Col]}>
                  <TouchableOpacity
                    activeOpacity={0.85}
                    onPress={() => setShowHistory((v) => !v)}
                    style={s.historyHeader}
                  >
                    <View>
                      <Text style={s.blockTitle}>{safeT(t, "futuresPro.history.title", "History")}</Text>
                      <Text style={s.blockSub}>{safeT(t, "futuresPro.history.hint", "Saved sessions.")}</Text>
                    </View>
                    <Ionicons name={showHistory ? "chevron-up" : "chevron-down"} size={18} color={C.sub} />
                  </TouchableOpacity>

                  {showHistory && (
                    <View style={{ marginTop: 10 }}>
                      {sessions.length === 0 ? (
                        <Text style={s.p}>{safeT(t, "futuresPro.history.empty", "No sessions yet.")}</Text>
                      ) : (
                        sessions.slice(0, 8).map((it) => (
                          <HistoryRow
                            key={it.id}
                            item={it}
                            onRestore={() => restoreSession(it)}
                            onRemove={() => removeSession(it.id)}
                          />
                        ))
                      )}
                    </View>
                  )}
                </View>
              </View>
            </>
          ) : hasAnalyzed && !loading && !plan ? (
            <View style={[s.card, { marginTop: 12 }]}>
              <Text style={s.blockTitle}>{safeT(t, "futuresPro.noDataTitle", "No data")}</Text>
              <Text style={s.blockSub}>
                {safeT(t, "futuresPro.noDataSubtitle", "Could not build setup for this pair.")}
              </Text>
            </View>
          ) : null}

          <Text style={s.footer}>
            {safeT(t, "futuresPro.hints.disclaimer", "Important: analytics only, not financial advice. Use risk management.")}
          </Text>
        </ScrollView>

        <View style={{ position: "absolute", left: -9999, top: -9999 }}>
          <ViewShot ref={shareShotRef} options={{ format: "png", quality: 1 }}>
            <ShareCard symbol={symbol} interval={interval} plan={plan} score={score} ticker24={ticker24} />
          </ViewShot>
        </View>
      </LinearGradient>
    </View>
  );
}


function makeSessionItem({ symbol, interval, plan, tk24, score }) {
  return {
    id: Date.now().toString(),
    at: new Date().toISOString(),
    symbol,
    interval,
    score: Number.isFinite(score) ? score : null,
    trendKey: plan?.trendKey || null,
    side: plan?.side || null,
    last: plan?.last ?? null,
    zone: plan?.zone ?? null,
    stop: plan?.stop ?? null,
    t1: plan?.t1 ?? null,
    t2: plan?.t2 ?? null,
    rsi: plan?.rsi ?? null,
    atrPct: plan?.atrPct ?? null,
    ch24: tk24?.ch24 ?? null,
    quoteVol: tk24?.quoteVol ?? null,
  };
}

async function pushSession(uid, item, setSessions) {
  try {
    const key = PRO_SESSIONS_KEY(uid);
    const raw = await AsyncStorage.getItem(key);
    let list = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(list)) list = [];
    list.unshift(item);
    if (list.length > 60) list = list.slice(0, 60);
    await AsyncStorage.setItem(key, JSON.stringify(list));
    setSessions(list);
  } catch {}
}


function SectionHeader({ title, subtitle, right }) {
  return (
    <View style={s.sectionHeader}>
      <View style={{ flex: 1 }}>
        <Text style={s.blockTitle}>{title}</Text>
        {!!subtitle && <Text style={s.blockSub}>{subtitle}</Text>}
      </View>
      {!!right && <View style={{ marginLeft: 10 }}>{right}</View>}
    </View>
  );
}

function MiniStatBox({ label, value, valueColor }) {
  return (
    <View style={s.miniStatBox}>
      <Text style={s.miniStatLabel}>{label}</Text>
      <Text style={[s.miniStatValue, valueColor ? { color: valueColor } : null]} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

function CompactMetric({ title, value, valueColor, accent }) {
  return (
    <View style={[s.compactMetric, accent ? s.compactMetricAccent : null]}>
      <Text style={s.compactMetricTitle}>{title}</Text>
      <Text style={[s.compactMetricValue, valueColor ? { color: valueColor } : null]} numberOfLines={2}>
        {value}
      </Text>
    </View>
  );
}

function PlanBoxCompact({ title, value }) {
  return (
    <View style={s.planBoxCompact}>
      <Text style={s.planBoxCompactTitle}>{title}</Text>
      <Text style={s.planBoxCompactValue}>{value}</Text>
    </View>
  );
}

function InfoCapsule({ label, value }) {
  return (
    <View style={s.infoCapsule}>
      <Text style={s.infoCapsuleLabel}>{label}</Text>
      <Text style={s.infoCapsuleValue}>{value}</Text>
    </View>
  );
}

function SmallInput({ label, value, onChangeText, placeholder }) {
  return (
    <View style={s.smallInputWrap}>
      <Text style={s.smallInputLabel}>{label}</Text>
      <View style={s.smallInputBox}>
        <TextInput
          value={value}
          onChangeText={onChangeText}
          keyboardType="numeric"
          placeholder={placeholder}
          placeholderTextColor="#5f6a86"
          style={s.smallInput}
        />
      </View>
    </View>
  );
}

function MiniSparkline({ closes }) {
  if (!closes?.length) return null;
  const arr = closes.slice(-60);
  const max = Math.max(...arr);
  const min = Math.min(...arr);
  const range = Math.max(1e-9, max - min);
  return (
    <View style={s.sparkWrap}>
      {arr.map((v, i) => {
        const h = ((v - min) / range) * 28 + 2;
        return <View key={i} style={[s.sparkBar, { height: h }]} />;
      })}
    </View>
  );
}

function ShareBtn({ label, onPress }) {
  return (
    <TouchableOpacity onPress={onPress} activeOpacity={0.9} style={s.btnShare}>
      <Ionicons name="share-social" size={16} color="#0b1b36" />
      <Text style={s.btnShareTxt}>{label}</Text>
    </TouchableOpacity>
  );
}

function PillSmall({ label, tone = "warn" }) {
  const map = {
    good: { col: T.good, br: "rgba(41,211,122,0.35)", bg: "rgba(41,211,122,0.10)" },
    warn: { col: T.warn, br: "rgba(255,184,77,0.35)", bg: "rgba(255,184,77,0.10)" },
    bad: { col: T.bad, br: "rgba(255,107,107,0.35)", bg: "rgba(255,107,107,0.10)" },
  };
  const v = map[tone] || map.warn;
  return (
    <View style={[s.pillSmall, { borderColor: v.br, backgroundColor: v.bg }]}>
      <Text style={[s.pillSmallTxt, { color: v.col }]}>{label}</Text>
    </View>
  );
}

function CheckRowCompact({ checked, onPress, label }) {
  return (
    <TouchableOpacity activeOpacity={0.85} onPress={onPress} style={s.checkRowCompact}>
      <Ionicons name={checked ? "checkmark-circle" : "ellipse-outline"} size={18} color={checked ? T.good : C.sub} />
      <Text style={s.checkRowCompactTxt}>{label}</Text>
    </TouchableOpacity>
  );
}

function countDone(checklist) {
  return Object.values(checklist || {}).filter(Boolean).length;
}

function HistoryRow({ item, onRestore, onRemove }) {
  const { t } = useTranslation();

  const dt = (() => {
    try {
      const d = new Date(item.at);
      return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    } catch {
      return "";
    }
  })();

  return (
    <View style={s.historyRow}>
      <View style={{ flex: 1 }}>
        <Text style={s.historyTitle}>{item.symbol?.replace("USDT", "/USDT")} • {item.interval?.toUpperCase()}</Text>
        <Text style={s.historySub}>{dt}</Text>
        <Text style={s.historySub}>
          {safeT(t, "futuresPro.history.zone", "Zone")} {usd(item.zone?.[0])} – {usd(item.zone?.[1])}
        </Text>
      </View>

      <View style={{ gap: 8, marginLeft: 10 }}>
        <TouchableOpacity onPress={onRestore} activeOpacity={0.9} style={s.historyBtn}>
          <Ionicons name="arrow-undo" size={15} color={C.text} />
        </TouchableOpacity>
        <TouchableOpacity onPress={onRemove} activeOpacity={0.9} style={[s.historyBtn, { borderColor: "rgba(255,107,107,0.35)" }]}>
          <Ionicons name="trash" size={15} color={T.bad} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

function CompareGrid({ a, b }) {
  const { t } = useTranslation();

  const row = (label, left, right) => (
    <View style={s.compareRow}>
      <Text style={s.compareLabel}>{label}</Text>
      <View style={s.compareVals}>
        <Text style={s.compareVal}>{left}</Text>
        <Text style={s.compareVal}>{right}</Text>
      </View>
    </View>
  );

  return (
    <View style={s.compareWrap}>
      <View style={s.compareHead}>
        <Text style={[s.compareHeadTxt, { flex: 1 }]}>{safeT(t, "futuresPro.compare.metric", "Metric")}</Text>
        <Text style={[s.compareHeadTxt, { width: 90, textAlign: "center" }]}>{a.symbol.replace("USDT", "/USDT")}</Text>
        <Text style={[s.compareHeadTxt, { width: 90, textAlign: "center" }]}>{b.symbol.replace("USDT", "/USDT")}</Text>
      </View>

      {row(safeT(t, "futuresPro.compare.score", "Score"), Number.isFinite(a.score) ? `${a.score}/100` : "—", Number.isFinite(b.score) ? `${b.score}/100` : "—")}
      {row(safeT(t, "futuresPro.compare.trend", "Trend"), safeT(t, `futuresPro.trend.${a.plan.trendKey}`, a.plan.trendKey), safeT(t, `futuresPro.trend.${b.plan.trendKey}`, b.plan.trendKey))}
      {row(safeT(t, "futuresPro.compare.side", "Side"), sideLabel(t, a.plan.side), sideLabel(t, b.plan.side))}
      {row(safeT(t, "futuresPro.compare.zone", "Entry zone"), `${usd(a.plan.zone[0])}–${usd(a.plan.zone[1])}`, `${usd(b.plan.zone[0])}–${usd(b.plan.zone[1])}`)}
      {row(safeT(t, "futuresPro.compare.stop", "Stop"), usd(a.plan.stop), usd(b.plan.stop))}
      {row(safeT(t, "futuresPro.compare.ch24", "24h change"), pct(a.tk24?.ch24), pct(b.tk24?.ch24))}
      {row(safeT(t, "futuresPro.compare.vol", "Volatility (ATR%)"), Number.isFinite(a.plan.atrPct) ? a.plan.atrPct.toFixed(2) + "%" : "—", Number.isFinite(b.plan.atrPct) ? b.plan.atrPct.toFixed(2) + "%" : "—")}
    </View>
  );
}

function ShareCard({ symbol, interval, plan, score, ticker24 }) {
  const { t } = useTranslation();

  if (!plan) return null;

  const date = new Date();
  const iso = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  const pairLabel = symbol.replace("USDT", "/USDT");

  const reasons = [
    `${safeT(t, "futuresPro.entryZone", "Entry zone")}: ${usd(plan.zone?.[0])} – ${usd(plan.zone?.[1])}`,
    `${safeT(t, "futuresPro.stop", "Stop")}: ${usd(plan.stop)}`,
    `${safeT(t, "futuresPro.targets", "Targets")}: ${usd(plan.t1)} • ${usd(plan.t2)}`,
    `RSI ${Number.isFinite(plan.rsi) ? plan.rsi.toFixed(1) : "—"} • ${safeT(t, "futuresPro.indicators.atr", "ATR")} ${usd(plan.atr)}`,
  ];

  return (
    <LinearGradient colors={[GRAD.bgStart, GRAD.bgMid, GRAD.bgEnd]} style={{ width: 1024, padding: 40, borderRadius: 28 }}>
      <Text style={{ color: T.logo, fontWeight: "900", fontSize: 42, marginBottom: 18 }}>
        {safeT(t, "futuresPro.title", "Explain")}
      </Text>

      <View
        style={{
          backgroundColor: "rgba(8,14,36,0.98)",
          borderRadius: 24,
          padding: 28,
          borderWidth: 1,
          borderColor: T.border,
        }}
      >
        <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 16, gap: 10 }}>
          <View
            style={{
              paddingVertical: 6,
              paddingHorizontal: 14,
              borderRadius: 10,
              backgroundColor: "rgba(255,255,255,0.06)",
              borderWidth: 1,
              borderColor: T.border,
            }}
          >
            <Text style={{ color: T.text, fontWeight: "900" }}>{interval.toUpperCase()}</Text>
          </View>

          <Text style={{ color: T.text, fontSize: 28, fontWeight: "900", flexShrink: 1 }} numberOfLines={2}>
            {pairLabel}
          </Text>
        </View>

        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 16 }}>
          <ShareMetric title={safeT(t, "futuresPro.compare.trend", "Trend")} value={`${safeT(t, `futuresPro.trend.${plan.trendKey}`, plan.trendKey)} • ${sideLabel(t, plan.side)}`} valueColor={toneFromTrend(plan)} />
          <ShareMetric title={safeT(t, "futuresPro.score", "Score")} value={Number.isFinite(score) ? `${score}/100` : "—"} />
          <ShareMetric title={safeT(t, "futuresPro.current", "Current")} value={usd(plan.last)} />
          <ShareMetric title={safeT(t, "futuresPro.change24h", "24h")} value={pct(ticker24?.ch24)} valueColor={num(ticker24?.ch24, 0) >= 0 ? T.good : T.bad} />
          <ShareMetric title={safeT(t, "futuresPro.entryZone", "Entry zone")} value={`${usd(plan.zone?.[0])} – ${usd(plan.zone?.[1])}`} />
          <ShareMetric title={safeT(t, "futuresPro.stop", "Stop")} value={usd(plan.stop)} />
          <ShareMetric title={safeT(t, "futuresPro.targets", "Targets")} value={`${usd(plan.t1)} • ${usd(plan.t2)}`} />
          <ShareMetric title={safeT(t, "futuresPro.date", "Date")} value={iso} />
        </View>

        <View style={{ marginTop: 18 }}>
          {reasons.map((r, i) => (
            <Text key={i} style={{ color: T.dim, fontSize: 18, marginBottom: 6 }}>
              • {r}
            </Text>
          ))}
        </View>

        <Text style={{ color: T.dim, marginTop: 18, fontSize: 14 }}>
          NOYTRIX — {safeT(t, "futuresPro.title", "Explain")}
        </Text>
      </View>
    </LinearGradient>
  );
}

function ShareMetric({ title, value, valueColor }) {
  return (
    <View
      style={{
        flexGrow: 1,
        minWidth: 220,
        borderWidth: 1,
        borderColor: T.border,
        borderRadius: 16,
        padding: 16,
      }}
    >
      <Text style={{ color: T.dim, marginBottom: 6 }}>{title}</Text>
      <Text style={{ color: valueColor || T.text, fontWeight: "900", fontSize: 22 }}>{value}</Text>
    </View>
  );
}


const s = StyleSheet.create({
  topTitleWrap: {
    marginBottom: 10,
  },
  pageTitle: {
    color: C.accent,
    fontSize: 30,
    fontWeight: "900",
    marginTop: 10,
    marginBottom: 6,
  },
  pageSub: {
    color: C.sub,
    lineHeight: 20,
    fontSize: 14,
  },

  card: {
    ...cardChrome,
    borderRadius: 22,
    padding: 14,
    backgroundColor: "rgba(255,255,255,0.045)",
  },

  sectionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 10,
    marginBottom: 10,
  },

  blockTitle: {
    color: C.text,
    fontWeight: "900",
    fontSize: 16,
  },
  blockSub: {
    color: C.sub,
    lineHeight: 18,
    marginTop: 4,
    fontSize: 13,
  },

  compactInputWrap: {
    marginTop: 10,
    borderWidth: 1,
    borderColor: C.cardBorder,
    borderRadius: 14,
    backgroundColor: "rgba(255,255,255,0.06)",
    paddingHorizontal: 12,
    minHeight: 48,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  compactInput: {
    flex: 1,
    color: C.text,
    fontSize: 15,
    paddingVertical: 10,
  },
  inputSymbolPill: {
    borderWidth: 1,
    borderColor: "rgba(255,165,0,0.20)",
    backgroundColor: "rgba(255,165,0,0.08)",
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  inputSymbolPillTxt: {
    color: C.accent,
    fontWeight: "900",
    fontSize: 11,
  },

  chipsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  chip: {
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: C.cardBorder,
    backgroundColor: "rgba(255,255,255,0.04)",
  },
  chipTxt: {
    color: C.sub,
    fontWeight: "800",
    fontSize: 12,
  },

  smallSectionLabel: {
    color: C.text,
    fontWeight: "800",
    fontSize: 13,
    marginBottom: 8,
  },

  topActionRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 14,
    flexWrap: "wrap",
  },
  controlBtnMain: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: C.accent,
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 14,
  },
  controlBtnMainTxt: {
    color: "#0B1220",
    fontWeight: "900",
    fontSize: 15,
  },
  controlBtnAlt: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    borderWidth: 1,
    borderColor: "rgba(255,165,0,0.25)",
    backgroundColor: "rgba(255,165,0,0.07)",
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 14,
  },
  controlBtnAltTxt: {
    color: C.accent,
    fontWeight: "900",
    fontSize: 15,
  },
  errText: {
    color: T.bad,
    marginTop: 10,
    fontWeight: "700",
  },

  summaryTopRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 10,
    alignItems: "center",
  },
  summaryPair: {
    color: C.text,
    fontSize: 22,
    fontWeight: "900",
  },
  summaryMeta: {
    color: C.sub,
    marginTop: 2,
    fontSize: 13,
  },
  scoreBadge: {
    borderWidth: 1,
    borderRadius: 999,
    paddingVertical: 7,
    paddingHorizontal: 12,
  },
  scoreBadgeTxt: {
    fontWeight: "900",
    fontSize: 12,
  },

  miniStatsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 10,
  },
  miniStatBox: {
    flex: 1,
    minWidth: 72,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.03)",
    paddingVertical: 10,
    paddingHorizontal: 10,
  },
  miniStatLabel: {
    color: C.sub,
    fontSize: 11,
    fontWeight: "700",
  },
  miniStatValue: {
    color: C.text,
    fontSize: 14,
    fontWeight: "900",
    marginTop: 4,
  },

  compactGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  compactGridSingle: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 10,
  },
  compactMetric: {
    flexBasis: "48%",
    flexGrow: 1,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.03)",
    padding: 12,
    minHeight: 76,
  },
  compactMetricAccent: {
    borderColor: "rgba(255,165,0,0.20)",
    backgroundColor: "rgba(255,165,0,0.06)",
  },
  compactMetricTitle: {
    color: C.sub,
    fontSize: 11,
    fontWeight: "700",
  },
  compactMetricValue: {
    color: C.text,
    marginTop: 8,
    fontSize: 15,
    fontWeight: "900",
    lineHeight: 19,
  },

  inlinePanel: {
    marginTop: 10,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.025)",
    padding: 10,
  },
  inlinePanelTitle: {
    color: C.text,
    fontSize: 14,
    fontWeight: "800",
    marginBottom: 8,
  },

  contextRowCompact: {
    flexDirection: "row",
    gap: 8,
  },
  contextCompactItem: {
    flex: 1,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
    backgroundColor: "rgba(255,255,255,0.03)",
    paddingVertical: 10,
    paddingHorizontal: 10,
  },
  contextCompactTop: {
    color: C.sub,
    fontSize: 11,
    fontWeight: "700",
    marginBottom: 4,
  },
  contextCompactBottom: {
    fontSize: 13,
    fontWeight: "900",
  },

  sparkWrap: {
    height: 48,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: C.cardBorder,
    backgroundColor: "rgba(255,255,255,0.03)",
    paddingHorizontal: 4,
    flexDirection: "row",
    alignItems: "flex-end",
    overflow: "hidden",
    gap: 2,
    marginBottom: 10,
  },
  sparkBar: {
    width: 3,
    backgroundColor: "#66B3FF",
    borderTopLeftRadius: 3,
    borderTopRightRadius: 3,
  },

  planLevelGridCompact: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  planBoxCompact: {
    flexBasis: "48%",
    flexGrow: 1,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.03)",
    padding: 12,
  },
  planBoxCompactTitle: {
    color: C.sub,
    fontSize: 11,
    fontWeight: "700",
    marginBottom: 6,
  },
  planBoxCompactValue: {
    color: C.text,
    fontSize: 15,
    fontWeight: "900",
    lineHeight: 19,
  },

  infoCapsuleRow: {
    marginTop: 8,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  infoCapsule: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.03)",
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  infoCapsuleLabel: {
    color: C.sub,
    fontSize: 10,
    fontWeight: "700",
  },
  infoCapsuleValue: {
    color: C.text,
    marginTop: 2,
    fontSize: 12,
    fontWeight: "900",
  },

  actionRowCompact: {
    flexDirection: "row",
    gap: 8,
    flexWrap: "wrap",
    marginTop: 10,
  },
  btnPrimary: {
    backgroundColor: C.accent,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 14,
  },
  btnPrimaryTxt: { color: "#0B1220", fontWeight: "900", fontSize: 14 },

  btnGhost: {
    borderWidth: 1,
    borderColor: C.cardBorder,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 14,
    backgroundColor: "rgba(255,255,255,0.06)",
  },
  btnGhostTxt: { color: C.text, fontWeight: "900", fontSize: 14 },

  btnWarn: {
    backgroundColor: "#1f2a44",
    borderWidth: 1,
    borderColor: "#ffb02066",
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 14,
  },
  btnWarnTxt: { color: "#FFB020", fontWeight: "900", fontSize: 14 },

  btnShare: {
    marginTop: 10,
    alignSelf: "stretch",
    flexDirection: "row",
    gap: 8,
    backgroundColor: "#ffb020",
    paddingVertical: 12,
    paddingHorizontal: 12,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  btnShareTxt: { color: "#0b1b36", fontWeight: "900", fontSize: 14 },

  row2: {
    flexDirection: "row",
    gap: 12,
    flexWrap: "wrap",
  },
  row2Col: {
    flex: 1,
    minWidth: 300,
  },

  checklistCompact: {
    gap: 8,
  },
  checkRowCompact: {
    minHeight: 42,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
    backgroundColor: "rgba(255,255,255,0.025)",
    paddingHorizontal: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  checkRowCompactTxt: {
    color: C.text,
    fontSize: 13,
    fontWeight: "700",
    flex: 1,
  },

  inputsGridCompact: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  smallInputWrap: {
    flex: 1,
    minWidth: 92,
  },
  smallInputLabel: {
    color: C.sub,
    fontSize: 11,
    fontWeight: "700",
    marginBottom: 5,
  },
  smallInputBox: {
    borderWidth: 1,
    borderColor: C.cardBorder,
    borderRadius: 12,
    backgroundColor: "rgba(255,255,255,0.06)",
  },
  smallInput: {
    color: C.text,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
  },

  note: {
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.10)",
    borderRadius: 14,
    padding: 10,
    backgroundColor: "rgba(255,255,255,0.03)",
  },
  noteTxt: {
    color: C.sub,
    fontStyle: "italic",
    lineHeight: 18,
    fontSize: 13,
  },

  pillSmall: {
    borderWidth: 1,
    borderRadius: 999,
    paddingVertical: 6,
    paddingHorizontal: 10,
  },
  pillSmallTxt: {
    fontWeight: "900",
    fontSize: 11,
  },

  compareWrap: {
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.10)",
    backgroundColor: "rgba(255,255,255,0.03)",
    borderRadius: 16,
    overflow: "hidden",
  },
  compareHead: {
    flexDirection: "row",
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: "rgba(255,255,255,0.04)",
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255,255,255,0.06)",
  },
  compareHeadTxt: {
    color: C.sub,
    fontWeight: "900",
    fontSize: 12,
  },
  compareRow: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255,255,255,0.06)",
  },
  compareLabel: {
    color: C.text,
    fontWeight: "800",
    marginBottom: 6,
    fontSize: 13,
  },
  compareVals: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 8,
  },
  compareVal: {
    color: C.sub,
    fontWeight: "800",
    width: 90,
    textAlign: "center",
    fontSize: 12,
  },

  btnCompare: {
    backgroundColor: C.accent,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    minWidth: 90,
  },
  btnCompareTxt: {
    color: "#0B1220",
    fontWeight: "900",
    fontSize: 13,
  },

  mono: {
    color: C.sub,
    fontSize: 13,
    lineHeight: 19,
    fontFamily: Platform.select({
      ios: "Menlo",
      android: "monospace",
      default: "monospace",
    }),
  },

  historyHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 10,
  },
  historyRow: {
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.10)",
    backgroundColor: "rgba(255,255,255,0.03)",
    borderRadius: 14,
    padding: 10,
    marginBottom: 8,
    flexDirection: "row",
    gap: 10,
  },
  historyTitle: {
    color: C.text,
    fontWeight: "900",
    fontSize: 13,
  },
  historySub: {
    color: C.sub,
    marginTop: 4,
    fontSize: 12,
    lineHeight: 16,
  },
  historyBtn: {
    width: 34,
    height: 34,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
    backgroundColor: "rgba(255,255,255,0.04)",
    alignItems: "center",
    justifyContent: "center",
  },

  p: {
    color: C.sub,
    lineHeight: 18,
    fontSize: 13,
  },

  footer: {
    color: "rgba(168,180,207,0.85)",
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 18,
    textAlign: "center",
    marginTop: 14,
    marginBottom: 10,
  },
});




