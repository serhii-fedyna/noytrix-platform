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
  Share,
  InteractionManager,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Stack } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import ViewShot from "react-native-view-shot";
import * as Sharing from "expo-sharing";
import { useTranslation } from "react-i18next";
import { BlurView } from "expo-blur";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { showAppAlert } from "../lib/appAlert";

const theme = {
  bgStart: "#06080f",
  bgMid: "#0a1233",
  bgEnd: "#0b1c4f",
  gold: "#ffb020",
  accent: "#ffb020",
  text: "#e9ecff",
  soft: "#A8B4CF",
  cardBg: "rgba(255,255,255,0.06)",
  cardInner: "rgba(8,14,36,0.62)",
  cardStroke: "rgba(255,255,255,0.12)",
};

const STORE_PREFIX = "spot.issue.v2";

const EXCLUDE_SYMBOLS = new Set([
  "BTC", "ETH", "SOL", "BNB", "USDT", "USDC", "BUSD", "DAI", "FDUSD", "TUSD",
  "USDE", "USDP", "USD1", "EUROC", "EURS", "TRYB", "BRZ", "USDD", "USDX",
  "GUSD", "LUSD", "WBTC", "WETH", "STETH", "WSTETH",
]);

const STORE_KEY = (d) => `${STORE_PREFIX}.${d}`;

function fmtDate(d) {
  return d.toISOString().slice(0, 10);
}

async function getStorage() {
  return AsyncStorage;
}

function usdSmart(n) {
  const v = Number(n || 0);
  if (!Number.isFinite(v)) return "$0";
  if (v >= 1) return `$${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  if (v >= 0.01) return `$${v.toFixed(4)}`;
  return `$${v.toPrecision(3)}`;
}

function capFmt(n) {
  const v = Number(n || 0);
  if (!Number.isFinite(v)) return "-";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${Math.round(v)}`;
}

function pct(n) {
  const v = Number(n || 0);
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

function looksLikeStableOrWrapped(sym, name) {
  const S = (sym || "").toUpperCase();
  const N = (name || "").toLowerCase();
  if (EXCLUDE_SYMBOLS.has(S)) return true;
  if (/usd/i.test(S)) return true;
  if (/wrapped|bridged|peg|tether|usd\s?coin/i.test(N)) return true;
  if (/^.*weth.*$/i.test(S) || /wrapped\s*eth/i.test(N)) return true;
  return false;
}

function scoreCoin(c) {
  if (looksLikeStableOrWrapped(c.symbol, c.name)) {
    return { score: -1, reasons: ["Excluded stable/wrapped asset"] };
  }
  if (c.mcap < 40_000_000) {
    return { score: -1, reasons: ["Market cap too small"] };
  }
  if (c.vol24 < 2_000_000) {
    return { score: -1, reasons: ["Volume too low"] };
  }

  const reasons = [];
  const liq = c.vol24 / Math.max(1, c.mcap);
  const liqScore = Math.max(0, Math.min(1, liq / 0.15));
  if (liq > 0.06) reasons.push("Good liquidity");

  const mom7 = Number(c.ch7 || 0);
  const momScore = Math.max(0, Math.min(1, (mom7 + 10) / 25));
  if (mom7 > 0) reasons.push("Positive 7d momentum");

  const hot24 = Number(c.ch24 || 0) > 25;
  if (hot24) reasons.push("Hot 24h move");

  let score = 0.45 * momScore + 0.45 * liqScore + 0.1;
  if (hot24) score *= 0.6;
  if (c.ch7 < -25) score *= 0.6;

  const expLow = Math.max(2, Math.min(8, 2 + momScore * 7 + liqScore * 4));
  const expHigh = Math.max(expLow + 3, Math.min(25, expLow + 10));

  return { score, reasons, exp: { low: expLow, high: expHigh } };
}

async function fetchMarkets() {
  const url =
    "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=volume_desc&per_page=250&page=1&sparkline=false&price_change_percentage=24h,7d";

  const res = await fetch(url);
  if (!res.ok) throw new Error(`CoinGecko ${res.status}`);

  const json = await res.json();

  return json.map((x) => ({
    id: x.id,
    symbol: String(x.symbol || "").toUpperCase(),
    name: x.name || "",
    price: Number(x.current_price || 0),
    mcap: Number(x.market_cap || 0),
    vol24: Number(x.total_volume || 0),
    ch24: Number(x.price_change_percentage_24h || 0),
    ch7: Number(x.price_change_percentage_7d_in_currency || 0),
  }));
}

function pickIdeas(scored) {
  return scored.slice(0, 6);
}

function buildPackage(scored, amount, skipIds = new Set()) {
  const picked = scored.filter((x) => !skipIds.has(x.id)).slice(0, 4);
  const weights = [0.35, 0.3, 0.2, 0.15];

  return picked.map((c, i) => ({
    ...c,
    usd: amount * weights[i],
    est: `${Math.round(c._exp?.low ?? 0)}-${Math.round(c._exp?.high ?? 0)}%`,
  }));
}

function buildDistinctPackages(scored, ideas) {
  const used = new Set((ideas || []).map((x) => x.id));
  const p100 = buildPackage(scored, 100, used);
  p100.forEach((x) => used.add(x.id));

  const p500 = buildPackage(scored, 500, used);
  p500.forEach((x) => used.add(x.id));

  const p1000 = buildPackage(scored, 1000, used);

  return { p100, p500, p1000 };
}

async function shareView(ref, name, tr) {
  try {
    if (!ref?.current?.capture) {
      showAppAlert(
        tr ? tr("common.error", "Error") : "Error",
        tr ? tr("spot.shareNotReady", "Share image is not ready yet. Try again.") : "Share image is not ready yet. Try again."
      );
      return;
    }

    await new Promise((resolve) => InteractionManager.runAfterInteractions(resolve));
    await new Promise((resolve) => setTimeout(resolve, 220));

    const uri = await ref.current.capture();

    if (!uri || typeof uri !== "string") {
      throw new Error("capture_empty");
    }

    const title = name || "Noytrix Spot";
    const canShareFile = await Sharing.isAvailableAsync().catch(() => false);

    if (canShareFile) {
      await Sharing.shareAsync(uri, {
        mimeType: "image/png",
        dialogTitle: tr ? tr("spot.shareDialog", "Share Noytrix result") : "Share Noytrix result",
        UTI: "public.png",
      });
      return;
    }

    await Share.share({
      title,
      url: uri,
      message: Platform.OS === "ios" ? title : `${title}
${uri}`,
    });
  } catch (e) {
    const raw = String(e?.message || e || "").toLowerCase();

    if (!raw.includes("cancel")) {
      showAppAlert(
        tr ? tr("spot.shareErrorTitle", "Could not share") : "Could not share",
        tr ? tr("spot.shareErrorText", "Could not send the image. Please try again.") : "Could not send the image. Please try again."
      );
    }

    console.log("[SPOT SHARE ERROR]", e?.message || e);
  }
}

function GlassCard({ children, style }) {
  return (
    <View style={[s.cardWrap, style]}>
      <BlurView intensity={22} tint="dark" style={s.cardBlur}>
        <View style={s.cardInner}>{children}</View>
      </BlurView>
    </View>
  );
}

function ShareBtn({ label, onPress, small }) {
  return (
    <Pressable onPress={onPress} style={[s.btnShare, small && s.btnShareSmall]}>
      <Ionicons name="share-social-outline" size={17} color="#0b1b36" />
      <Text style={s.btnShareTxt}>{label}</Text>
    </Pressable>
  );
}

function BuyRow({ symbol, tr }) {
  const BINANCE_REF_LINK = "https://www.binance.com/referral/earn-together/refer2earn-usdc/claim?hl=ru&ref=GRO_28502_CT2JM&utm_source=referral_entrance";
  const open = (url) => Linking.openURL(url).catch(() => {});

  return (
    <View style={s.buyRow}>
      <Text style={s.buyTitle}>{tr("Open market", "Open market")}</Text>
      <View style={s.buyBtns}>
        <Pressable
          style={s.buyBtn}
          onPress={() => open(BINANCE_REF_LINK)}
        >
          <Text style={s.buyBtnTxt}>Binance</Text>
        </Pressable>

        <Pressable
          style={s.buyBtn}
          onPress={() => open("https://okx.com/join/68561548")}
        >
          <Text style={s.buyBtnTxt}>OKX</Text>
        </Pressable>
      </View>
    </View>
  );
}

function ShareIssueCanvas({ ideas, dateStr, innerRef, tr }) {
  return (
    <ViewShot
      ref={innerRef}
      options={{
        format: "png",
        quality: 1,
        result: Platform.OS === "web" ? "base64" : "tmpfile",
      }}
      style={{ position: "absolute", opacity: 0, pointerEvents: "none" }}
    >
      <LinearGradient
        colors={[theme.bgMid, theme.bgEnd]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={s.shareCanvas}
      >
        <Text style={[s.title, { color: theme.gold, textAlign: "left" }]}>
          {tr("spot.titleToday", "TodayвЂ™s Spot Ideas")}
        </Text>
        <Text style={[s.soft, { marginBottom: 10 }]}>
          {tr("spot.issueLabel", "Issue")} - {dateStr}
        </Text>

        {ideas.slice(0, 4).map((c) => (
          <View key={c.id} style={[s.shareCard, { marginBottom: 10 }]}>
            <Text style={s.itemTitle}>
              {c.symbol} <Text style={s.soft}>/ {c.name}</Text>
            </Text>

            <Text style={s.itemLine}>
              {tr("spot.price", "Price")}:{" "}
              <Text style={s.valGold}>{usdSmart(c.price)}</Text> -{" "}
              {tr("spot.change24h", "24h")}: {pct(c.ch24)} -{" "}
              {tr("spot.change7d", "7d")}: {pct(c.ch7)}
            </Text>

            <Text style={s.itemLine}>
              {tr("spot.marketCapShort", "MCap")}:{" "}
              <Text style={s.valGold}>{capFmt(c.mcap)}</Text> -{" "}
              {tr("spot.volumeShort", "Volume")}:{" "}
              <Text style={s.valGold}>{capFmt(c.vol24)}</Text>
            </Text>

            <Text style={[s.itemLine, { marginTop: 6, color: theme.soft }]}>
              {tr("spot.potential", "Potential")}:{" "}
              <Text style={s.valGold}>
                {Math.round(c._exp?.low ?? 0)}-{Math.round(c._exp?.high ?? 0)}%
              </Text>
            </Text>
          </View>
        ))}

        <Text style={[s.footNote, { marginTop: 6 }]}>
          {tr("spot.smartPicks", "Noytrix - smart picks")}
        </Text>
      </LinearGradient>
    </ViewShot>
  );
}

function SharePackageCanvas({ title, dateStr, items, innerRef, tr }) {
  return (
    <ViewShot
      ref={innerRef}
      options={{
        format: "png",
        quality: 1,
        result: Platform.OS === "web" ? "base64" : "tmpfile",
      }}
      style={{ position: "absolute", opacity: 0, pointerEvents: "none" }}
    >
      <LinearGradient
        colors={[theme.bgMid, theme.bgEnd]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={s.shareCanvas}
      >
        <Text style={[s.title, { color: theme.gold, textAlign: "left" }]}>
          {title}
        </Text>
        <Text style={[s.soft, { marginBottom: 10 }]}>
          {tr("spot.selectionLabel", "Selection")} - {dateStr}
        </Text>

        {(!items || items.length === 0) && (
          <View style={s.cardMuted}>
            <Text style={s.soft}>{tr("spot.noData", "No data")}</Text>
          </View>
        )}

        {items?.map((it, idx) => (
          <View
            key={`${it.id || "item"}-${idx}`}
            style={[s.shareCard, { marginBottom: 10 }]}
          >
            <Text style={s.itemTitle}>
              {it.symbol} <Text style={s.soft}>/ {it.name}</Text>
            </Text>

            <Text style={s.itemLine}>
              {tr("spot.allocation", "Allocation")}:{" "}
              <Text style={s.valGold}>{usdSmart(it.usd)}</Text> -{" "}
              {tr("spot.price", "Price")}:{" "}
              <Text style={s.valGold}>{usdSmart(it.price)}</Text>
            </Text>

            <Text style={s.itemLine}>
              {tr("spot.expectation", "Expectation")}:{" "}
              <Text style={s.valGold}>{it.est}</Text>
            </Text>
          </View>
        ))}

        <Text style={[s.footNote, { marginTop: 6 }]}>
          Noytrix - {tr("spot.packageStrategy", "package strategy")}
        </Text>
      </LinearGradient>
    </ViewShot>
  );
}
function IdeaCard({ coin, tr }) {
  return (
    <GlassCard style={{ marginBottom: 12 }}>
      <View style={s.cardTopRow}>
        <View style={{ flex: 1 }}>
          <Text style={s.itemTitle}>
            {coin.symbol} <Text style={s.soft}>/ {coin.name}</Text>
          </Text>
          <Text style={s.mini}>{tr("spot.ideaRange", "Smart spot idea")}</Text>
        </View>

        <View style={s.scorePill}>
          <Ionicons name="sparkles" size={14} color={theme.gold} />
          <Text style={s.scoreTxt}>{Math.round((coin._score || 0) * 100)}</Text>
        </View>
      </View>

      <View style={s.sep} />

      <Text style={s.itemLine}>
        {tr("spot.price", "Price")}:{" "}
        <Text style={s.valGold}>{usdSmart(coin.price)}</Text> -{" "}
        {tr("spot.change24h", "24h")}: {pct(coin.ch24)} -{" "}
        {tr("spot.change7d", "7d")}: {pct(coin.ch7)}
      </Text>

      <Text style={s.itemLine}>
        {tr("spot.marketCap", "Market cap")}:{" "}
        <Text style={s.valGold}>{capFmt(coin.mcap)}</Text> -{" "}
        {tr("spot.volume24h", "24h volume")}:{" "}
        <Text style={s.valGold}>{capFmt(coin.vol24)}</Text>
      </Text>

      <Text style={[s.itemLine, { marginTop: 6, color: theme.soft }]}>
        {tr("spot.potential", "Potential")}:{" "}
        <Text style={s.valGold}>
          {Math.round(coin._exp?.low ?? 0)}-{Math.round(coin._exp?.high ?? 0)}%
        </Text>
      </Text>

      <BuyRow symbol={coin.symbol} tr={tr} />
    </GlassCard>
  );
}

function PackCard({ title, items, tr }) {
  return (
    <GlassCard style={{ marginBottom: 10 }}>
      <View style={s.packHeader}>
        <Text style={s.packHeaderTitle}>{title}</Text>
        <View style={s.packBadge}>
          <Text style={s.packBadgeTxt}>
            {tr("spot.packageStrategy", "Strategy")}
          </Text>
        </View>
      </View>

      {(!items || items.length === 0) && (
        <Text style={s.soft}>{tr("spot.noData", "No data")}</Text>
      )}

      {items?.map((it, idx) => (
        <View key={`${it.id || "pack"}-${idx}`} style={s.packRow}>
          <View style={{ flex: 1 }}>
            <Text style={s.packTitle}>
              {it.symbol} <Text style={s.soft}>/ {it.name}</Text>
            </Text>

            <Text style={s.packLine}>
              {tr("spot.allocation", "Allocation")}:{" "}
              <Text style={s.valGold}>{usdSmart(it.usd)}</Text> -{" "}
              {tr("spot.price", "Price")}:{" "}
              <Text style={s.valGold}>{usdSmart(it.price)}</Text> -{" "}
              {tr("spot.expectation", "Expectation")}:{" "}
              <Text style={s.valGold}>{it.est}</Text>
            </Text>
          </View>

          <View style={s.usdPill}>
            <Text style={s.usdPillTxt}>{usdSmart(it.usd)}</Text>
          </View>
        </View>
      ))}
    </GlassCard>
  );
}

function Spot() {
  const header = <Stack.Screen options={{ headerShown: false }} />;
  const { t: tr } = useTranslation();

  const [issueId, setIssueId] = useState(null);
  const [ideas, setIdeas] = useState(null);
  const [packs, setPacks] = useState({ p100: [], p500: [], p1000: [] });
  const [loading, setLoading] = useState(false);

  const issueVisibleRef = useRef(null);
  const issueShareRef = useRef(null);

  const p100ShareRef = useRef(null);
  const p500ShareRef = useRef(null);
  const p1000ShareRef = useRef(null);

  const fmtToday = () => fmtDate(new Date());

  const loadIssue = useCallback(async (forceRebuild = false) => {
    setLoading(true);
    try {
      const store = await getStorage();
      const now = new Date();
      const nowStr = fmtDate(now);

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
            const s0 = scoreCoin(c);
            return s0.score > 0
              ? { ...c, _score: s0.score, _reasons: s0.reasons, _exp: s0.exp }
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
      console.log("[SPOT LOAD ERROR]", e?.message || e);
      setIdeas([]);
      setPacks({ p100: [], p500: [], p1000: [] });

      showAppAlert(
        tr("spot.loadErrorTitle", "Could not load Spot ideas"),
        tr("spot.loadErrorText", "Market data is temporarily unavailable. Please try again later.")
      );
    } finally {
      setLoading(false);
    }
  }, [tr]);

  useEffect(() => {
    loadIssue(false);
  }, [loadIssue]);

  const shareIssue = useCallback(() => {
    shareView(issueShareRef, `Spot_${issueId || fmtToday()}`, tr);
  }, [issueId]);

  const shareP100 = useCallback(() => {
    shareView(p100ShareRef, `Spot_${issueId || fmtToday()}_Pack_100`, tr);
  }, [issueId]);

  const shareP500 = useCallback(() => {
    shareView(p500ShareRef, `Spot_${issueId || fmtToday()}_Pack_500`, tr);
  }, [issueId]);

  const shareP1000 = useCallback(() => {
    shareView(p1000ShareRef, `Spot_${issueId || fmtToday()}_Pack_1000`, tr);
  }, [issueId]);

  return (
    <LinearGradient
      colors={[theme.bgStart, theme.bgMid, theme.bgEnd]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={{ flex: 1 }}
    >
      {header}

      {ideas && ideas.length > 0 && (
        <ShareIssueCanvas
          ideas={ideas}
          dateStr={issueId || fmtToday()}
          innerRef={issueShareRef}
          tr={tr}
        />
      )}

      {packs?.p100?.length > 0 && (
        <SharePackageCanvas
          title={tr("spot.pack100Title", "$100 Spot Pack")}
          dateStr={issueId || fmtToday()}
          items={packs.p100}
          innerRef={p100ShareRef}
          tr={tr}
        />
      )}

      {packs?.p500?.length > 0 && (
        <SharePackageCanvas
          title={tr("spot.pack500Title", "$500 Spot Pack")}
          dateStr={issueId || fmtToday()}
          items={packs.p500}
          innerRef={p500ShareRef}
          tr={tr}
        />
      )}

      {packs?.p1000?.length > 0 && (
        <SharePackageCanvas
          title={tr("spot.pack1000Title", "$1000 Spot Pack")}
          dateStr={issueId || fmtToday()}
          items={packs.p1000}
          innerRef={p1000ShareRef}
          tr={tr}
        />
      )}

      <ScrollView
        contentContainerStyle={{
          padding: 16,
          paddingBottom: 24,
          paddingTop: 24,
        }}
        refreshControl={
          <RefreshControl
            refreshing={loading}
            onRefresh={() => loadIssue(true)}
            tintColor={theme.accent}
          />
        }
        showsVerticalScrollIndicator={false}
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
          <View style={{ marginBottom: 12, alignItems: "flex-start" }}>
            <Text style={[s.pageTitle, { marginTop: 6 }]}>
              {tr("spot.titleToday", "Spot Ideas")}
            </Text>
            <Text style={s.subtitle} numberOfLines={3}>
              {tr("spot.subtitle", "Daily spot picks based on liquidity, momentum and market structure.")}
            </Text>
          </View>

          <Text style={s.h2}>{tr("spot.ideasTitle", "Ideas for today")}</Text>

          {!ideas || ideas.length === 0 ? (
            <View style={s.cardMuted}>
              <Text style={s.soft}>
                {loading
                  ? tr("spot.loading", "Loading...")
                  : tr("spot.noDataIdeas", "No ideas right now. Pull down to refresh.")}
              </Text>
            </View>
          ) : (
            ideas.map((c) => <IdeaCard key={c.id} coin={c} tr={tr} />)
          )}
        </ViewShot>

        {ideas && ideas.length > 0 && (
          <ShareBtn label={tr("spot.shareIssue", "Share ideas")} onPress={shareIssue} />
        )}

        <Text style={[s.h2, { marginTop: 14 }]}>
          {tr("spot.packagesTitle", "Ready spot packs")}
        </Text>

        <PackCard title={tr("spot.pack100Title", "$100 Spot Pack")} items={packs.p100} tr={tr} />
        <ShareBtn small label={tr("spot.sharePack100", "Share $100 pack")} onPress={shareP100} />

        <PackCard title={tr("spot.pack500Title", "$500 Spot Pack")} items={packs.p500} tr={tr} />
        <ShareBtn small label={tr("spot.sharePack500", "Share $500 pack")} onPress={shareP500} />

        <PackCard title={tr("spot.pack1000Title", "$1000 Spot Pack")} items={packs.p1000} tr={tr} />
        <ShareBtn small label={tr("spot.sharePack1000", "Share $1000 pack")} onPress={shareP1000} />
      </ScrollView>
    </LinearGradient>
  );
}

const s = StyleSheet.create({
  pageTitle: {
    fontSize: 28,
    fontWeight: "900",
    color: theme.gold,
    letterSpacing: 0.2,
  },
  title: {
    fontSize: 22,
    fontWeight: "800",
    color: theme.text,
    letterSpacing: 0.3,
  },
  subtitle: {
    fontSize: 14,
    color: theme.soft,
    lineHeight: 20,
    marginTop: 8,
    fontWeight: "600",
    opacity: 0.95,
  },
  h2: {
    fontSize: 18,
    color: theme.text,
    fontWeight: "900",
    marginTop: 4,
    marginBottom: 10,
  },
  cardWrap: {
    borderRadius: 18,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: theme.cardStroke,
    backgroundColor: theme.cardBg,
    shadowColor: "rgba(0,0,0,0.35)",
    shadowOpacity: 1,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 8 },
    elevation: 3,
  },
  cardBlur: {
    borderRadius: 18,
  },
  cardInner: {
    padding: 14,
    backgroundColor: theme.cardInner,
  },
  cardMuted: {
    backgroundColor: "rgba(8,14,36,0.35)",
    borderWidth: 1,
    borderColor: theme.cardStroke,
    borderRadius: 18,
    padding: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  cardTopRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  scorePill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "rgba(255,165,0,0.35)",
    backgroundColor: "rgba(255,165,0,0.10)",
  },
  scoreTxt: {
    color: theme.text,
    fontWeight: "900",
    fontSize: 12,
  },
  sep: {
    height: 1,
    backgroundColor: "rgba(255,255,255,0.08)",
    marginVertical: 10,
  },
  itemTitle: {
    fontSize: 16,
    color: theme.text,
    fontWeight: "900",
    marginBottom: 2,
  },
  mini: {
    color: theme.soft,
    fontSize: 12,
    fontWeight: "700",
    opacity: 0.9,
  },
  itemLine: {
    fontSize: 13.5,
    color: theme.text,
    opacity: 0.92,
    lineHeight: 19,
  },
  soft: {
    color: theme.soft,
  },
  valGold: {
    color: theme.gold,
    fontWeight: "900",
  },
  buyRow: {
    marginTop: 12,
  },
  buyTitle: {
    fontSize: 12.5,
    color: theme.soft,
    marginBottom: 8,
    fontWeight: "700",
  },
  buyBtns: {
    flexDirection: "row",
    gap: 8,
    flexWrap: "wrap",
  },
  buyBtn: {
    paddingVertical: 7,
    paddingHorizontal: 12,
    backgroundColor: "rgba(255,165,0,0.12)",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255,165,0,0.35)",
  },
  buyBtnTxt: {
    color: theme.text,
    fontSize: 12.5,
    fontWeight: "800",
  },
  btnShare: {
    marginTop: 10,
    alignSelf: "stretch",
    flexDirection: "row",
    gap: 8,
    backgroundColor: theme.gold,
    paddingVertical: 12,
    paddingHorizontal: 12,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  btnShareSmall: {
    alignSelf: "flex-start",
    marginTop: 10,
    marginBottom: 4,
    paddingVertical: 10,
    paddingHorizontal: 14,
  },
  btnShareTxt: {
    color: "#0b1b36",
    fontWeight: "900",
    fontSize: 14,
  },
  shareCanvas: {
    width: 1080,
    padding: 48,
    borderRadius: 24,
  },
  shareCard: {
    backgroundColor: "rgba(255,255,255,0.06)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.10)",
    borderRadius: 16,
    padding: 12,
  },
  footNote: {
    fontSize: 12.5,
    color: theme.soft,
    textAlign: "left",
    opacity: 0.9,
    fontWeight: "700",
  },
  packHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 8,
    gap: 10,
  },
  packHeaderTitle: {
    fontSize: 16,
    color: theme.text,
    fontWeight: "900",
  },
  packBadge: {
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.10)",
    backgroundColor: "rgba(255,255,255,0.04)",
  },
  packBadgeTxt: {
    color: theme.soft,
    fontSize: 12,
    fontWeight: "800",
  },
  packRow: {
    flexDirection: "row",
    gap: 10,
    alignItems: "center",
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: "rgba(255,255,255,0.06)",
  },
  packTitle: {
    fontSize: 15,
    color: theme.text,
    fontWeight: "900",
  },
  packLine: {
    fontSize: 13.5,
    color: theme.text,
    opacity: 0.92,
    marginTop: 3,
    lineHeight: 19,
  },
  usdPill: {
    backgroundColor: "rgba(255,255,255,0.04)",
    borderColor: "rgba(255,255,255,0.10)",
    borderWidth: 1,
    borderRadius: 12,
    paddingVertical: 7,
    paddingHorizontal: 10,
  },
  usdPillTxt: {
    color: theme.gold,
    fontSize: 12,
    fontWeight: "900",
  },
});

export default Spot;




