// app/(tabs)/spot.js
import React, { useEffect, useState, useCallback, useRef } from "react";
import {
View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  Platform,
  Pressable,
  Linking,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Stack } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import ViewShot from "react-native-view-shot";
import * as Sharing from "expo-sharing";
import { useI18n } from "./i18n/useI18n";




const n = (v, d = 0) => {
  const x =
    typeof v === "number" ? v : parseFloat(String(v ?? "").replace(/[^0-9.\-]/g, ""));
  return Number.isFinite(x) ? x : d;
};
const pct = (x) => (x || x === 0 ? `${x >= 0 ? "+" : ""}${n(x).toFixed(2)}%` : "");
const usdSmart = (x) => {
  const v = n(x, NaN);
  if (!Number.isFinite(v)) return "";
  if (v >= 1000) return "$" + v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (v >= 1) return "$" + v.toFixed(2);
  if (v >= 0.1) return "$" + v.toFixed(3);
  if (v >= 0.01) return "$" + v.toFixed(4);
  if (v >= 0.001) return "$" + v.toFixed(5);
  return "$" + v.toFixed(6);
};
const capFmt = (x) => {
  const v = n(x, NaN);
  if (!Number.isFinite(v)) return "";
  if (v >= 1e12) return "$" + (v / 1e12).toFixed(2) + "T";
  if (v >= 1e9) return "$" + (v / 1e9).toFixed(2) + "B";
  if (v >= 1e6) return "$" + (v / 1e6).toFixed(2) + "M";
  return "$" + v.toFixed(0);
};
const fmtDate = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;


const EXCLUDE_SYMBOLS = new Set([
  "BTC",
  "ETH",
  "SOL",
  "BNB",
  "USDT",
  "USDC",
  "BUSD",
  "DAI",
  "FDUSD",
  "TUSD",
  "USDE",
  "USDP",
  "USD1",
  "EUROC",
  "EURS",
  "TRYB",
  "BRZ",
  "USDD",
  "USDX",
  "GUSD",
  "LUSD",
  "WBTC",
  "WETH",
  "STETH",
  "WSTETH",
]);
function looksLikeStableOrWrapped(sym, name) {
  const S = (sym || "").toUpperCase();
  const N = (name || "").toLowerCase();
  if (EXCLUDE_SYMBOLS.has(S)) return true;
  if (/usd/i.test(S)) return true;
  if (/wrapped|bridged|peg|tether|usd\s?coin/i.test(N)) return true;
  if (/^.*weth.*$/i.test(S) || /wrapped\s*eth/i.test(N)) return true;
  return false;
}


async function fetchMarkets() {
  const url =
    "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=1&sparkline=false&price_change_percentage=24h,7d";
  const r = await fetch(url, { headers: { accept: "application/json" } });
  if (!r.ok) throw new Error("CoinGecko HTTP " + r.status);
  const arr = await r.json();
  return arr
    .filter((c) => c && c.symbol && c.name)
    .map((c) => ({
      id: c.id,
      name: c.name,
      symbol: (c.symbol || "").toUpperCase(),
      price: n(c.current_price),
      ch24: n(c.price_change_percentage_24h_in_currency),
      ch7: n(c.price_change_percentage_7d_in_currency),
      vol24: n(c.total_volume),
      mcap: n(c.market_cap),
      url: `https://www.coingecko.com/coins/${c.id}`,
    }));
}


function scoreCoin(c) {
  if (looksLikeStableOrWrapped(c.symbol, c.name))
    return { score: -1, reasons: ["AB591;/>1Q@B:0 8A:;NG5=K"] };
  if (c.mcap < 40_000_000) return { score: -1, reasons: ["<0;5=L:0O :0?8B0;870F8O"] };
  if (c.vol24 < 2_000_000) return { score: -1, reasons: ["=87:0O ;8:284=>ABL"] };

  const reasons = [];
  const liq = c.vol24 / Math.max(1, c.mcap);
  const liqScore = Math.max(0, Math.min(1, liq / 0.15));
  if (liq > 0.06) reasons.push("E>@>H0O ;8:284=>ABL (> 6%)");

  const mom7 = c.ch7;
  const momScore = Math.max(0, Math.min(1, (mom7 + 10) / 25));
  if (mom7 > 0) reasons.push(`<><5=BC< 74: ${pct(mom7)}`);

  const hot24 = c.ch24 > 12;
  if (hot24) reasons.push("A;8H:>< 3>@OG> 70 24G  @8A:");

  let score = 0.45 * momScore + 0.45 * liqScore + 0.10 * 0;
  if (hot24) score *= 0.6;
  if (c.ch7 < -25) score *= 0.6;

  const expLow = Math.max(2, Math.min(8, 2 + momScore * 7 + liqScore * 4));
  const expHigh = Math.max(expLow + 3, Math.min(25, expLow + 10));

  if (!hot24 && mom7 >= 0) reasons.push("045:20B=K9 @8A:/?>B5=F80;");
  if (c.mcap > 1e9) reasons.push(":@C?=0O/A@54=OO :0?8B0;870F8O");
  else reasons.push("<5=LH0O :0?8B0;870F8O (2KH5 @8A:/?>B5=F80;)");

  return { score, reasons, exp: { low: expLow, high: expHigh } };
}


function pickIdeas(list) {
  const scored = list
    .map((c) => {
      const s = scoreCoin(c);
      return s.score > 0 ? { ...c, _score: s.score, _reasons: s.reasons, _exp: s.exp } : null;
    })
    .filter(Boolean)
    .sort((a, b) => b._score - a._score);

  const out = [];
  const used = new Set();
  const pushIf = (pred) => {
    const i = scored.find((x) => pred(x) && !used.has(x.id));
    if (i) {
      used.add(i.id);
      out.push(i);
    }
  };
  pushIf((x) => x.mcap >= 2e9);
  pushIf((x) => x.mcap >= 4e8 && x.mcap < 2e9);
  pushIf((x) => x.mcap < 4e8);
  for (const c of scored) {
    if (out.length >= 4) break;
    if (!used.has(c.id)) {
      used.add(c.id);
      out.push(c);
    }
  }
  return out.slice(0, 4);
}


function buildDistinctPackages(pool, ideas) {
  const used = new Set(ideas.map((x) => x.id));
  const sortByScore = (a, b) => (b._score || 0) - (a._score || 0);

  const large = pool.filter((x) => x.mcap >= 2e9 && !used.has(x.id)).sort(sortByScore);
  const mid = pool
    .filter((x) => x.mcap >= 5e8 && x.mcap < 2e9 && !used.has(x.id))
    .sort(sortByScore);
  const small = pool.filter((x) => x.mcap < 5e8 && !used.has(x.id)).sort(sortByScore);

  function take(arr, k) {
    const res = [];
    for (const x of arr) {
      if (res.length >= k) break;
      if (!used.has(x.id)) {
        used.add(x.id);
        res.push(x);
      }
    }
    return res;
  }

  const pack100Coins = [...take(large, 2), ...take(mid, 1)].slice(0, 3);
  const pack500Coins = [...take(mid, 3), ...take(small, 1)].slice(0, 4);
  const pack1000Coins = [...take(large, 2), ...take(mid, 3), ...take(small, 2)].slice(0, 6);

  const make = (coins, budget) => {
    const sum = coins.reduce((s, x) => s + (x._score || 0), 0) || 1;
    return coins.map((c) => {
      let min = 0.15,
        max = 0.45;
      if (budget <= 120) {
        min = 0.25;
        max = 0.6;
      } else if (budget >= 900) {
        min = 0.12;
        max = 0.35;
      }
      const raw = (c._score || 0) / sum;
      const part = Math.min(max, Math.max(min, raw));
      const usd = Math.max(5, Math.round(budget * part));
      return {
        id: c.id,
        symbol: c.symbol,
        name: c.name,
        usd,
        price: c.price,
        est: `${Math.round(c._exp.low)}${Math.round(c._exp.high)}%`,
        url: c.url,
      };
    });
  };

  return {
    p100: make(pack100Coins, 100),
    p500: make(pack500Coins, 500),
    p1000: make(pack1000Coins, 1000),
  };
}


async function getStorage() {
  try {
    const AsyncStorage = (await import("@react-native-async-storage/async-storage")).default;
return AsyncStorage;
  } catch {
    const mem = new Map();
    return {
      async getItem(k) {
        return mem.has(k) ? mem.get(k) : null;
      },
      async setItem(k, v) {
        mem.set(k, v);
      },
      async removeItem(k) {
        mem.delete(k);
      },
    };
  }
}
const STORE_NS = "spot_issue_v2__";
const STORE_KEY = (dateStr) => `${STORE_NS}${dateStr}`;


async function shareView(ref, fileName) {
  if (!ref?.current) return;
  const uri = await ref.current.capture?.({
    format: "png",
    quality: 1,
    result: Platform.OS === "web" ? "base64" : "tmpfile",
  });
  if (!uri) return;

  if (Platform.OS === "web") {
    const a = document.createElement("a");
    a.href = `data:image/png;base64,${uri}`;
    a.download = `${fileName}.png`;
    a.click();
    return;
  }
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, {
      dialogTitle: fileName,
      UTI: "public.png",
      mimeType: "image/png",
    });
  }
}


export default function Spot() {
  const header = <Stack.Screen options={{ headerShown: false }} />;
  const { t: i18n } = useI18n();

  const [issueId, setIssueId] = useState(null);
  const [ideas, setIdeas] = useState(null);
  const [packs, setPacks] = useState({ p100: [], p500: [], p1000: [] });
  const [loading, setLoading] = useState(false);

  const issueVisibleRef = useRef(null); // ?@56=89 2848<K9 1;>: (>AB02;O5<)
  const issueShareRef = useRef(null); // A:@KB0O :0@B>G:0 2K?CA:0
  const fmtToday = () => fmtDate(new Date());

  const loadIssue = useCallback(async (forceRebuild = false) => {
    setLoading(true);
    try {
      const store = await getStorage();
      const now = new Date();
      const nowStr = fmtDate(now);

      const isBefore8 = now.getHours() < 8;
      if (!forceRebuild && isBefore8) {
        const y = new Date(now.getTime() - 86400000);
        const yStr = fmtDate(y);
        const prev = await store.getItem(STORE_KEY(yStr));
        if (prev) {
          const j = JSON.parse(prev);
          setIssueId(yStr);
          setIdeas(j.ideas);
          setPacks(j.packs);
          setLoading(false);
          return;
        }
      }

      const saved = !forceRebuild ? await store.getItem(STORE_KEY(nowStr)) : null;
      if (!saved) {
        const markets = await fetchMarkets();
        const clean = markets.filter(
          (c) =>
            !looksLikeStableOrWrapped(c.symbol, c.name) &&
            c.mcap >= 40_000_000 &&
            c.vol24 >= 2_000_000 &&
            c.price > 0
        );
        const scored = clean
          .map((c) => {
            const s = scoreCoin(c);
            return s.score > 0
              ? { ...c, _score: s.score, _reasons: s.reasons, _exp: s.exp }
              : null;
          })
          .filter(Boolean)
          .sort((a, b) => b._score - a._score);

        const dayIdeas = pickIdeas(scored);
        const pkg = buildDistinctPackages(scored, dayIdeas);
        const payload = JSON.stringify({ ideas: dayIdeas, packs: pkg });
        await store.setItem(STORE_KEY(nowStr), payload);

        setIssueId(nowStr);
        setIdeas(dayIdeas);
        setPacks(pkg);
      } else {
        const j = JSON.parse(saved);
        setIssueId(nowStr);
        setIdeas(j.ideas);
        setPacks(j.packs);
      }
    } catch (e) {
      console.warn("Spot issue load error:", e?.message || e);
      setIdeas([]);
      setPacks({ p100: [], p500: [], p1000: [] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadIssue(false);
  }, []);
  useEffect(() => {
    const id = setInterval(() => {
      const now = new Date();
      if (now.getHours() >= 8 && fmtDate(now) !== issueId) {
        loadIssue(true);
      }
    }, 60 * 1000);
    return () => clearInterval(id);
  }, [issueId, loadIssue]);

  const shareIssue = useCallback(() => {
    shareView(issueShareRef, `Spot_${issueId || fmtToday()}`);
  }, [issueId]);

  return (
    <LinearGradient
      colors={["#071022", "#0a1322", "#020915"]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={{ flex: 1 }}
    >
      {header}

      {}
      {ideas && ideas.length > 0 && (
        <ShareIssueCanvas
          ideas={ideas}
          dateStr={issueId || fmtToday()}
          innerRef={issueShareRef}
        />
      )}

      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 24, paddingTop: 24 }}
        refreshControl={
          <RefreshControl
            refreshing={loading}
            onRefresh={() => loadIssue(true)}
            tintColor={"#63b3ff"}
          />
        }
      >
        <ViewShot
          ref={issueVisibleRef}
          style={{ backgroundColor: "transparent" }}
          options={{
            format: "png",
            quality: 1,
            result: Platform.OS === "web" ? "base64" : "tmpfile",
          }}
        >
          {}
          <View style={{ marginBottom: 12, alignItems: "flex-start" }}>
            <Text style={[s.title, { textAlign: "left", color: "#ffb020", marginTop: 16 }]}>
              {i18n("spot.header.title")}
            </Text>
            <Text style={[s.subtitle, { textAlign: "left" }]} numberOfLines={3}>
              {i18n("spot.header.subtitle")}
            </Text>
          </View>

          <Text style={s.h2}>{i18n("spot.sections.ideasTitle")}</Text>
          {!ideas || ideas.length === 0 ? (
            <View style={s.cardMuted}>
              <Text style={s.soft}>{i18n("spot.state.noData")}</Text>
            </View>
          ) : (
            ideas.map((c) => <IdeaCard key={c.id} coin={c} />)
          )}
        </ViewShot>

        {ideas && ideas.length > 0 && (
          <ShareBtn label={i18n("spot.buttons.shareIssue")} onPress={shareIssue} />
        )}

        <Text style={[s.h2, { marginTop: 14 }]}>{i18n("spot.sections.packsTitle")}</Text>
        <PackCard title={i18n("spot.packs.p100Title")} items={packs.p100} />
        <PackCard title={i18n("spot.packs.p500Title")} items={packs.p500} />
        <PackCard title={i18n("spot.packs.p1000Title")} items={packs.p1000} />
      </ScrollView>
    </LinearGradient>
  );
}


function ShareBtn({ label, onPress, small }) {
  return (
    <Pressable
      onPress={onPress}
      style={[s.btnShare, small && { alignSelf: "flex-start", paddingVertical: 8 }]}
    >
      <Ionicons name="share-social" size={16} color="#0b1b36" />
      <Text style={s.btnShareTxt}>{label}</Text>
    </Pressable>
  );
}

function BuyRow({ symbol }) {
  const { t: i18n } = useI18n();
  const sym = (symbol || "").toUpperCase();
  const links = [
    { name: "Bybit", url: `https://www.bybit.com/trade/spot/${sym}/USDT` },
    { name: "OKX", url: `https://www.okx.com/trade-spot/${sym}-USDT` },
    { name: "Binance", url: `https://www.binance.com/en/trade/${sym}_USDT` },
  ];
  const open = (u) => Linking.openURL(u).catch(() => {});
  return (
    <View style={s.buyRow}>
      <Text style={s.buyTitle}>{i18n("spot.buy.title")}</Text>
      <View style={s.buyBtns}>
        {links.map((x) => (
          <Pressable key={x.name} onPress={() => open(x.url)} style={s.buyBtn}>
            <Text style={s.buyBtnTxt}>{x.name}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function ShareIdeaCanvas({ coin, innerRef }) {
  const { t: i18n } = useI18n();

  const tags = [
    { label: i18n("spot.labels.price"), value: usdSmart(coin.price) },
    { label: i18n("spot.labels.ch24"), value: pct(coin.ch24) },
    { label: i18n("spot.labels.ch7"), value: pct(coin.ch7) },
    { label: i18n("spot.labels.mcap"), value: capFmt(coin.mcap) },
    { label: i18n("spot.labels.vol24h"), value: capFmt(coin.vol24) },
    {
      label: i18n("spot.labels.potential"),
      value: `${Math.round(coin._exp.low)}${Math.round(coin._exp.high)}%`,
    },
  ];

  return (
    <ViewShot
      ref={innerRef}
      style={{ position: "absolute", left: -9999, width: 1080, borderRadius: 24 }}
      options={{
        format: "png",
        quality: 1,
        result: Platform.OS === "web" ? "base64" : "tmpfile",
      }}
    >
      <LinearGradient
        colors={["#071022", "#0a1322", "#020915"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={{ padding: 36, borderRadius: 24 }}
      >
        <Text
          style={{ color: "#ffb020", fontWeight: "900", fontSize: 38, marginBottom: 8 }}
        >
          {i18n("spot.canvas.ideaHeader")}
        </Text>
        <View
          style={{
            backgroundColor: "rgba(17,29,49,0.9)",
            borderWidth: 1,
            borderColor: "#1a2a45",
            borderRadius: 20,
            padding: 22,
            marginTop: 10,
          }}
        >
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 12,
              marginBottom: 12,
            }}
          >
            <View
              style={{
                backgroundColor: "rgba(99,179,255,0.18)",
                borderColor: "#1a2a45",
                borderWidth: 1,
                borderRadius: 12,
                paddingHorizontal: 14,
                paddingVertical: 8,
              }}
            >
              <Text
                style={{
                  color: "#e9f0ff",
                  fontWeight: "900",
                  letterSpacing: 0.5,
                  fontSize: 28,
                }}
              >
                {coin.symbol}
              </Text>
            </View>
            <Text style={{ color: "#e9f0ff", fontWeight: "900", fontSize: 32 }}>
              {coin.name}
            </Text>
          </View>

          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
            {tags.map((x, i) => (
              <View
                key={i}
                style={{
                  minWidth: 240,
                  padding: 16,
                  borderWidth: 1,
                  borderColor: "#1a2a45",
                  borderRadius: 14,
                }}
              >
                <Text style={{ color: "#bcd2ff", fontSize: 20, marginBottom: 6 }}>
                  {x.label}
                </Text>
                <Text style={{ color: "#e9f0ff", fontWeight: "900", fontSize: 26 }}>
                  {x.value}
                </Text>
              </View>
            ))}
          </View>

          <View style={{ marginTop: 14 }}>
            {coin._reasons.slice(0, 3).map((r, idx) => (
              <Text key={idx} style={{ color: "#bcd2ff", fontSize: 22, lineHeight: 32 }}>
                " {r}
              </Text>
            ))}
          </View>

          <Text
            style={{
              color: "#bcd2ff",
              marginTop: 16,
              fontSize: 18,
              opacity: 0.8,
            }}
          >
            {fmtDate(new Date())} " {i18n("spot.canvas.generated")}
          </Text>
        </View>

        <Text style={{ color: "#bcd2ff", marginTop: 18, fontSize: 22 }}>
          {i18n("spot.labels.disclaimer")}
        </Text>
      </LinearGradient>
    </ViewShot>
  );
}


function ShareIssueCanvas({ ideas, dateStr, innerRef }) {
  const { t: i18n } = useI18n();

  return (
    <ViewShot
      ref={innerRef}
      style={{ position: "absolute", left: -9999, width: 1080, borderRadius: 24 }}
      options={{
        format: "png",
        quality: 1,
        result: Platform.OS === "web" ? "base64" : "tmpfile",
      }}
    >
      <LinearGradient
        colors={["#071022", "#0a1322", "#020915"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={{ padding: 36, borderRadius: 24 }}
      >
        <Text style={{ color: "#ffb020", fontWeight: "900", fontSize: 40 }}>
          {i18n("spot.canvas.issueHeader")}
        </Text>
        <Text style={{ color: "#bcd2ff", marginTop: 6, fontSize: 22 }}>{dateStr}</Text>

        <View
          style={{
            backgroundColor: "rgba(17,29,49,0.9)",
            borderWidth: 1,
            borderColor: "#1a2a45",
            borderRadius: 20,
            padding: 22,
            marginTop: 16,
          }}
        >
          {ideas.slice(0, 4).map((c) => (
            <View
              key={c.id}
              style={{
                paddingVertical: 14,
                borderTopWidth: 1,
                borderTopColor: "rgba(255,255,255,0.06)",
              }}
            >
              <View
                style={{
                  flexDirection: "row",
                  alignItems: "center",
                  gap: 12,
                  marginBottom: 8,
                }}
              >
                <View
                  style={{
                    backgroundColor: "rgba(99,179,255,0.18)",
                    borderColor: "#1a2a45",
                    borderWidth: 1,
                    borderRadius: 12,
                    paddingHorizontal: 14,
                    paddingVertical: 8,
                  }}
                >
                  <Text style={{ color: "#e9f0ff", fontWeight: "900", fontSize: 26 }}>
                    {c.symbol}
                  </Text>
                </View>
                <Text style={{ color: "#e9f0ff", fontWeight: "900", fontSize: 30 }}>
                  {c.name}
                </Text>
              </View>

              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
                {[
                  { label: i18n("spot.labels.price"), value: usdSmart(c.price) },
                  { label: i18n("spot.labels.ch24"), value: pct(c.ch24) },
                  { label: i18n("spot.labels.ch7"), value: pct(c.ch7) },
                  {
                    label: i18n("spot.labels.potential"),
                    value: `${Math.round(c._exp.low)}${Math.round(c._exp.high)}%`,
                  },
                ].map((x, i) => (
                  <View
                    key={i}
                    style={{
                      minWidth: 220,
                      padding: 14,
                      borderWidth: 1,
                      borderColor: "#1a2a45",
                      borderRadius: 14,
                    }}
                  >
                    <Text style={{ color: "#bcd2ff", fontSize: 18, marginBottom: 6 }}>
                      {x.label}
                    </Text>
                    <Text style={{ color: "#e9f0ff", fontWeight: "900", fontSize: 24 }}>
                      {x.value}
                    </Text>
                  </View>
                ))}
              </View>
            </View>
          ))}
        </View>

        <Text style={{ color: "#bcd2ff", marginTop: 18, fontSize: 22 }}>
          {i18n("spot.labels.disclaimer")}
        </Text>
      </LinearGradient>
    </ViewShot>
  );
}

function IdeaCard({ coin }) {
  const { t: i18n } = useI18n();
  const visibleRef = useRef(null);
  const shareRef = useRef(null);
  const onShare = () => shareView(shareRef, `Idea_${coin.symbol}`);

  const tags = [
    { label: i18n("spot.labels.price"), value: usdSmart(coin.price) },
    {
      label: i18n("spot.labels.ch24"),
      value: pct(coin.ch24),
      tone: coin.ch24 >= 0 ? "good" : "warn",
    },
    {
      label: i18n("spot.labels.ch7"),
      value: pct(coin.ch7),
      tone: coin.ch7 >= 0 ? "good" : "warn",
    },
    { label: i18n("spot.labels.mcap"), value: capFmt(coin.mcap) },
    { label: i18n("spot.labels.vol24h"), value: capFmt(coin.vol24) },
    {
      label: i18n("spot.labels.potential"),
      value: `${Math.round(coin._exp.low)}${Math.round(coin._exp.high)}%`,
      tone: "good",
    },
  ];

  return (
    <>
      <ShareIdeaCanvas coin={coin} innerRef={shareRef} />

      <ViewShot
        ref={visibleRef}
        style={{ backgroundColor: "transparent" }}
        options={{
          format: "png",
          quality: 1,
          result: Platform.OS === "web" ? "base64" : "tmpfile",
        }}
      >
        <View style={s.card} collapsable={false}>
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 10,
              marginBottom: 6,
            }}
          >
            <Badge>{coin.symbol}</Badge>
            <Text style={s.h3}>{coin.name}</Text>
          </View>

          <View style={s.tagRow}>
            {tags.map((x, idx) => (
              <Tag key={idx} label={x.label} value={x.value} tone={x.tone} />
            ))}
          </View>

          <View style={{ marginTop: 8 }}>
            {coin._reasons.slice(0, 3).map((r, i) => (
              <Text key={i} style={s.li}>
                " {r}
              </Text>
            ))}
          </View>

          <View style={{ marginTop: 10, gap: 8 }}>
            <BuyRow symbol={coin.symbol} />
            <ShareBtn label={i18n("spot.buttons.shareIdea")} onPress={onShare} small />
          </View>
        </View>
      </ViewShot>
    </>
  );
}

function PackCard({ title, items }) {
  const { t: i18n } = useI18n();
  const blockRef = useRef(null);
  const onShare = () => shareView(blockRef, title.replace(/\s+/g, "_"));

  return (
    <View style={s.card}>
      <Text style={s.h3}>{title}</Text>

      {(!items || items.length === 0) && (
        <Text style={s.soft}>{i18n("spot.state.packsNoData")}</Text>
      )}

      <ViewShot
        ref={blockRef}
        style={{ backgroundColor: "transparent" }}
        options={{
          format: "png",
          quality: 1,
          result: Platform.OS === "web" ? "base64" : "tmpfile",
        }}
      >
        <View collapsable={false}>
          {items.map((p) => (
            <PackRow key={p.id} p={p} />
          ))}
        </View>
      </ViewShot>

      <ShareBtn
        label={`${i18n("spot.buttons.sharePackPrefix")} ${title}`}
        onPress={onShare}
        small
      />
    </View>
  );
}

function PackRow({ p }) {
  const { t: i18n } = useI18n();

  return (
    <View style={s.packRow}>
      <Badge>{p.symbol}</Badge>
      <View style={{ flex: 1 }}>
        <Text style={s.packLine}>
          <Text style={s.soft}>{i18n("spot.labels.coin")}: </Text>
          {p.symbol}  {p.name}
        </Text>
        <Text style={s.packLine}>
          <Text style={s.soft}>{i18n("spot.labels.amount")}: </Text>
          {usdSmart(p.usd)}{" "}
          <Text style={[s.packGray]}>
            ({usdSmart(p.price)} {i18n("spot.labels.perOne")})
          </Text>
        </Text>
        <Text style={s.packLine}>
          <Text style={s.soft}>{i18n("spot.labels.potentialShort")}: </Text>
          <Text style={{ color: "#2dd783", fontWeight: "700" }}>{p.est}</Text>
        </Text>
      </View>
    </View>
  );
}

function Tag({ label, value, tone }) {
  const toneStyle = tone === "good" ? s.good : tone === "warn" ? s.warn : null;
  return (
    <View style={s.tagBox}>
      <Text style={s.tagLbl}>{label}</Text>
      <Text style={[s.tagVal, toneStyle]}>{value}</Text>
    </View>
  );
}
function Badge({ children }) {
  return (
    <View style={s.badge}>
      <Text style={s.badgeTxt}>{children}</Text>
    </View>
  );
}


const s = StyleSheet.create({
  title: {
    color: "#e9f0ff",
    fontWeight: "900",
    fontSize: 22,
  },
  subtitle: {
    color: "#bcd2ff",
    marginTop: 6,
    lineHeight: 20,
    maxWidth: 560,
  },

  h2: { color: "#e9f0ff", fontWeight: "900", fontSize: 18, marginBottom: 8 },
  h3: { color: "#e9f0ff", fontWeight: "900", fontSize: 16 },

  card: {
    backgroundColor: "rgba(17,29,49,0.9)",
    borderWidth: 1,
    borderColor: "#1a2a45",
    borderRadius: 16,
    padding: 14,
    marginBottom: 12,
  },
  cardMuted: {
    backgroundColor: "rgba(255,255,255,0.06)",
    borderWidth: 1,
    borderColor: "#1a2a45",
    borderRadius: 16,
    padding: 14,
    marginBottom: 12,
  },

  tagRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 },
  tagBox: {
    minWidth: 110,
    padding: 10,
    borderWidth: 1,
    borderColor: "#1a2a45",
    borderRadius: 12,
  },
  tagLbl: { color: "#bcd2ff", fontSize: 12, marginBottom: 4 },
  tagVal: { color: "#e9f0ff", fontWeight: "900" },
  good: { color: "#2dd783" },
  warn: { color: "#ffb84d" },

  li: { color: "#bcd2ff", marginTop: 4, lineHeight: 20 },

  badge: {
    backgroundColor: "rgba(99,179,255,0.18)",
    borderColor: "#1a2a45",
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  badgeTxt: { color: "#e9f0ff", fontWeight: "900", letterSpacing: 0.5 },

  packRow: {
    flexDirection: "row",
    gap: 10,
    alignItems: "flex-start",
    borderTopWidth: 1,
    borderTopColor: "rgba(255,255,255,0.06)",
    paddingTop: 10,
    marginTop: 10,
  },
  packLine: { color: "#e9f0ff", marginBottom: 2 },
  packGray: { color: "#bcd2ff", opacity: 0.8 },

  soft: { color: "#bcd2ff" },

  btnShare: {
    alignSelf: "center",
    backgroundColor: "#ffb020",
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 4,
    marginBottom: 8,
  },
  btnShareTxt: { color: "#0b1b36", fontWeight: "900" },

  buyRow: { marginTop: 2 },
  buyTitle: { color: "#bcd2ff", marginBottom: 6 },
  buyBtns: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  buyBtn: {
    backgroundColor: "rgba(99,179,255,0.18)",
    borderColor: "#1a2a45",
    borderWidth: 1,
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 10,
  },
  buyBtnTxt: { color: "#e9f0ff", fontWeight: "800" },
});






















