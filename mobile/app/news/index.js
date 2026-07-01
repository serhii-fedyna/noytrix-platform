// app/news/index.js

import React, { useEffect, useRef, useState, useCallback } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  ActivityIndicator,
  Modal,
  FlatList,
  ScrollView,
  StyleSheet,
} from "react-native";
import { Stack } from "expo-router";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { useTranslation } from "react-i18next";

const RSS_CT_RU = "https://cointelegraph.com/rss/tag/cryptocurrencies";
const JINA = (url) => `https://r.jina.ai/http://r.jina.ai/http://${url.replace(/^https?:\/\//, "")}`;

const C = {
  text: "#E9ECFF",
  sub: "#A8B4CF",
  accent: "#ffb020",
  card: "rgba(255,255,255,0.065)",
  cardBorder: "rgba(255,255,255,0.11)",
  red: "#ff4d4f",
};

const GRAD = {
  bgStart: "#06080f",
  bgMid: "#0a1233",
  bgEnd: "#0b1c4f",
};

async function fetchWithTimeout(url, options = {}, timeout = 10000, retries = 1) {
  let lastErr;

  for (let i = 0; i <= retries; i += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    try {
      const res = await fetch(url, {
        ...options,
        signal: controller.signal,
      });

      clearTimeout(timer);

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res;
    } catch (e) {
      clearTimeout(timer);
      lastErr = e;
    }
  }

  throw lastErr;
}

function decodeXml(str = "") {
  return String(str)
    .replace(/<!\[CDATA\[(.*?)\]\]>/gs, "$1")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function stripHtml(str = "") {
  return decodeXml(str)
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function parseCT(xml) {
  const items = [];
  const blocks = String(xml || "").match(/<item>[\s\S]*?<\/item>/g) || [];

  blocks.forEach((block, index) => {
    const get = (tag) => {
      const m = block.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, "i"));
      return m ? decodeXml(m[1]).trim() : "";
    };

    const title = stripHtml(get("title"));
    const link = stripHtml(get("link"));
    const pub = stripHtml(get("pubDate"));
    const desc = stripHtml(get("description"));

    if (!title || !link) return;

    items.push({
      id: `${link}-${index}`,
      title,
      link,
      pub,
      preview: desc || title,
    });
  });

  return items;
}

function fmtDate(date) {
  if (!date) return "";
  const d = new Date(date);
  if (Number.isNaN(d.getTime())) return "";

  return d.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function toPlainNews(raw, titleForDedup = "") {
  let s = String(raw || "");

  const parts = s.split("Markdown Content:");
  if (parts.length > 1) s = parts[1];

  s = s
    .replace(/^Title:[\s\S]*?$/gim, "")
    .replace(/^URL Source:[\s\S]*?$/gim, "")
    .replace(/^Published Time:[\s\S]*?$/gim, "")
    .replace(/={3,}|^-{3,}$/gim, " ")
    .replace(/!\[[^\]]*]\([^)]*\)/g, "")
    .replace(/\[[^\]]*]\([^)]*\)/g, "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/(\*\*|__)(.*?)\1/g, "$2")
    .replace(/[*_`]/g, "")
    .replace(/^\s*>\s*/gm, "")
    .replace(/^\s*[-–—]\s*/gm, "")
    .trim();

  const titleNorm = titleForDedup.toLowerCase().trim();

  let lines = s
    .split("\n")
    .map((ln) => ln.replace(/^\s*[\-*•]\s+/, "").trim())
    .filter(Boolean)
    .filter((ln) => {
      const low = ln.toLowerCase();
      if (titleNorm && low === titleNorm) return false;
      if (/javascript:void/i.test(low)) return false;
      if (/^(russian|markets|telegram|instagram|youtube|usd)$/i.test(ln)) return false;
      if (ln.length < 3) return false;
      return true;
    });

  s = lines.join("\n").replace(/\n{3,}/g, "\n\n").replace(/\s{2,}/g, " ").trim();

  const sentences = s.split(/(?<=[.!?…])\s+/);
  const paras = [];
  let buf = "";
  let count = 0;

  for (const sent of sentences) {
    const next = buf ? `${buf} ${sent}` : sent;

    if (count >= 3 || next.length > 600) {
      if (buf) paras.push(buf);
      buf = sent;
      count = 1;
    } else {
      buf = next;
      count += 1;
    }
  }

  if (buf) paras.push(buf);

  s = paras.join("\n\n");

  if (s.length > 20000) s = `${s.slice(0, 20000)}…`;

  return s.trim();
}

function explainNews(title, body) {
  const text = `${title}\n\n${body}`.toLowerCase();
  const tags = [];
  const affects = [];
  let rating = 0;

  const addTag = (x) => {
    if (!tags.includes(x)) tags.push(x);
  };

  const addAffect = (x) => {
    if (!affects.includes(x)) affects.push(x);
  };

  if (/(etf|spot etf)/i.test(text)) {
    rating += 2;
    addTag("ETF");
  }

  if (/(sec|regulator|fed|fomc|lawsuit|court|санкц|регулятор)/i.test(text)) {
    rating += 2;
    addTag("Regulation");
  }

  if (/(hack|exploit|scam|fraud|phishing|attack|взлом|скам|мошен)/i.test(text)) {
    rating += 3;
    addTag("Security");
  }

  if (/(partnership|integration|launch|listing|airdrop|запуск|листинг)/i.test(text)) {
    rating += 1;
    addTag("Market event");
  }

  if (/(bitcoin|btc|биткоин)/i.test(text)) addAffect("BTC");
  if (/(ethereum|eth|эфир)/i.test(text)) addAffect("ETH");
  if (/(solana|sol)/i.test(text)) addAffect("SOL");
  if (/(xrp|ripple)/i.test(text)) addAffect("XRP");
  if (/(bnb|binance)/i.test(text)) addAffect("BNB");
  if (/(ton|toncoin|тон)/i.test(text)) addAffect("TON");

  if (!affects.length) affects.push("BTC", "ETH");

  const importance = rating >= 4 ? "High" : rating <= 0 ? "Low" : "Medium";

  const action =
    importance === "High"
      ? "Watch market reaction carefully. Do not enter blindly."
      : importance === "Medium"
      ? "Useful news, but wait for confirmation on the chart."
      : "Low impact. Good to know, but not a trading signal.";

  const note =
    importance === "High"
      ? "This can affect volatility, sentiment, or risk."
      : importance === "Medium"
      ? "Can influence short-term attention around related coins."
      : "Mostly informational news.";

  return {
    importance,
    tags,
    affects: affects.slice(0, 4),
    action,
    note,
  };
}

function Card({ children, style }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export default function NewsScreen() {
  const { t } = useTranslation();

  const tt = useCallback(
    (key, fallback) => {
      const value = t(key);
      return value === key ? fallback : value;
    },
    [t]
  );

  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);

  const articleCacheRef = useRef(new Map());
  const explainCacheRef = useRef(new Map());

  const [readModal, setReadModal] = useState({
    open: false,
    title: "",
    text: "",
    loading: false,
  });

  const [expModal, setExpModal] = useState({
    open: false,
    title: "",
    data: null,
    loading: false,
  });

  const load = useCallback(async () => {
    try {
      setLoading(true);

      const r = await fetchWithTimeout(
        RSS_CT_RU,
        { headers: { "Cache-Control": "no-cache" } },
        10000,
        1
      );

      const txt = await r.text();
      setList(parseCT(txt));
    } catch {
      setList([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const getArticle = useCallback(async (it) => {
    const cache = articleCacheRef.current;

    if (cache.has(it.link)) return cache.get(it.link);

    const r = await fetchWithTimeout(JINA(it.link), {}, 10000, 1);
    const raw = await r.text();
    const clean = toPlainNews(raw, it.title);

    cache.set(it.link, clean);
    return clean;
  }, []);

  const openFull = useCallback(
    async (it) => {
      try {
        setReadModal({
          open: true,
          title: it.title,
          text: tt("news:loading", "Loading..."),
          loading: true,
        });

        let clean = articleCacheRef.current.get(it.link);
        if (!clean) clean = await getArticle(it);

        setReadModal({
          open: true,
          title: it.title,
          text: clean || tt("news:openError", "Could not open article."),
          loading: false,
        });
      } catch {
        setReadModal({
          open: true,
          title: it.title,
          text: tt("news:openError", "Could not open article."),
          loading: false,
        });
      }
    },
    [getArticle, tt]
  );

  const openExplain = useCallback(
    async (it) => {
      try {
        setExpModal({
          open: true,
          title: it.title,
          data: null,
          loading: true,
        });

        const cached = explainCacheRef.current.get(it.link);

        if (cached) {
          setExpModal({
            open: true,
            title: it.title,
            data: cached,
            loading: false,
          });
          return;
        }

        let body = "";

        try {
          const clean = await getArticle(it);
          body = clean
            .split(/\n{2,}/)
            .filter((p) => p.trim().length > 0)
            .slice(0, 4)
            .join("\n\n");
        } catch {}

        const data = explainNews(it.title, body);
        explainCacheRef.current.set(it.link, data);

        setExpModal({
          open: true,
          title: it.title,
          data,
          loading: false,
        });
      } catch {
        setExpModal({
          open: true,
          title: it.title,
          data: {
            action: "",
            importance: "Low",
            tags: [],
            affects: [],
            note: "",
          },
          loading: false,
        });
      }
    },
    [getArticle]
  );

  const renderItem = useCallback(
    ({ item: it }) => (
      <Card style={{ marginBottom: 12 }}>
        <Text style={styles.cardTitle}>{it.title}</Text>

        <Text style={styles.date}>{fmtDate(it.pub)}</Text>

        <Text style={styles.preview}>{it.preview}</Text>

        <View style={styles.actionsRow}>
          <TouchableOpacity
            activeOpacity={0.9}
            onPress={() => openFull(it)}
            style={styles.primaryBtn}
          >
            <Text style={styles.primaryBtnText}>
              {tt("news:openFullArticle", "Read full")}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            activeOpacity={0.9}
            onPress={() => openExplain(it)}
            style={styles.ghostBtn}
          >
            <Text style={styles.ghostBtnText}>
              {tt("news:explain", "Explain")}
            </Text>
          </TouchableOpacity>
        </View>
      </Card>
    ),
    [openFull, openExplain, tt]
  );

  return (
    <LinearGradient
      colors={[GRAD.bgStart, GRAD.bgMid, GRAD.bgEnd]}
      style={styles.root}
    >
      <Stack.Screen
        options={{
          title: tt("news:title", "News"),
          headerShown: false,
        }}
      />

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color="#fff" />
          <Text style={styles.loadingText}>{tt("news:loading", "Loading...")}</Text>
        </View>
      ) : (
        <FlatList
          data={list}
          keyExtractor={(it) => it.id}
          renderItem={renderItem}
          contentContainerStyle={styles.listContent}
          ListHeaderComponent={
            <>
              <Text style={styles.title}>{tt("news:headerTitle", "Crypto News")}</Text>
              <Text style={styles.subtitle}>
                {tt("news:headerSubtitle", "Fresh crypto news with quick impact explanation.")}
              </Text>

              {list.length === 0 && (
                <Card>
                  <Text style={{ color: C.sub }}>
                    {tt("news:empty", "No news right now.")}
                  </Text>
                </Card>
              )}
            </>
          }
          initialNumToRender={6}
          windowSize={7}
          removeClippedSubviews
        />
      )}

      <Modal
        visible={readModal.open}
        animationType="slide"
        transparent
        onRequestClose={() => setReadModal((s) => ({ ...s, open: false }))}
      >
        <View style={styles.modalScrim}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeader}>
              <TouchableOpacity
                onPress={() => setReadModal((s) => ({ ...s, open: false }))}
                style={styles.closeBtn}
              >
                <Ionicons name="chevron-down" size={26} color={C.text} />
              </TouchableOpacity>

              <Text numberOfLines={1} style={styles.modalTitle}>
                {readModal.title}
              </Text>
            </View>

            {readModal.loading ? (
              <View style={styles.modalLoading}>
                <ActivityIndicator color="#fff" />
                <Text style={styles.loadingText}>
                  {tt("news:loading", "Loading...")}
                </Text>
              </View>
            ) : (
              <ScrollView contentContainerStyle={styles.modalScroll}>
                {readModal.text
                  .split(/\n{2,}/)
                  .filter((p) => p.trim().length)
                  .map((p, i) => (
                    <Text key={i} style={styles.articleText}>
                      {p}
                    </Text>
                  ))}
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>

      <Modal
        visible={expModal.open}
        animationType="slide"
        transparent
        onRequestClose={() => setExpModal((s) => ({ ...s, open: false }))}
      >
        <View style={styles.modalScrim}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeader}>
              <TouchableOpacity
                onPress={() => setExpModal((s) => ({ ...s, open: false }))}
                style={styles.closeBtn}
              >
                <Ionicons name="chevron-down" size={26} color={C.text} />
              </TouchableOpacity>

              <Text numberOfLines={1} style={styles.modalTitle}>
                {tt("news:explain", "Explain")}
              </Text>
            </View>

            {expModal.loading ? (
              <View style={styles.modalLoading}>
                <ActivityIndicator color="#fff" />
                <Text style={styles.loadingText}>
                  {tt("news:loading", "Loading...")}
                </Text>
              </View>
            ) : (
              <View style={styles.explainWrap}>
                <Card>
                  <Text style={styles.explainTitle}>{expModal.title}</Text>

                  {expModal.data ? (
                    <>
                      <View style={styles.importanceRow}>
                        <MaterialCommunityIcons
                          name={
                            expModal.data.importance === "High"
                              ? "alert-decagram"
                              : expModal.data.importance === "Medium"
                              ? "alert-circle-outline"
                              : "alert"
                          }
                          size={18}
                          color={
                            expModal.data.importance === "High"
                              ? C.red
                              : expModal.data.importance === "Medium"
                              ? C.accent
                              : C.sub
                          }
                        />

                        <Text style={styles.importanceText}>
                          {tt("news:importance", "Importance")}:{" "}
                          <Text
                            style={{
                              color:
                                expModal.data.importance === "High"
                                  ? C.red
                                  : expModal.data.importance === "Medium"
                                  ? C.accent
                                  : C.sub,
                              fontWeight: "900",
                            }}
                          >
                            {expModal.data.importance}
                          </Text>
                        </Text>
                      </View>

                      {!!expModal.data.tags?.length && (
                        <Text style={styles.explainLine}>
                          {tt("news:tags", "Tags")}: {expModal.data.tags.join(", ")}
                        </Text>
                      )}

                      {!!expModal.data.affects?.length && (
                        <Text style={styles.explainLine}>
                          {tt("news:affects", "Affects")}:{" "}
                          {expModal.data.affects.join(", ")}
                        </Text>
                      )}

                      <Text style={styles.actionText}>
                        {tt("news:action", "Action")}:{" "}
                        <Text style={{ fontWeight: "900" }}>
                          {expModal.data.action}
                        </Text>
                      </Text>

                      <Text style={styles.noteText}>{expModal.data.note}</Text>
                    </>
                  ) : (
                    <Text style={styles.noteText}>
                      {tt("news:openError", "Could not explain this news.")}
                    </Text>
                  )}
                </Card>
              </View>
            )}
          </View>
        </View>
      </Modal>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  loadingText: {
    color: C.sub,
    marginTop: 8,
  },
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },
  title: {
    color: C.text,
    fontSize: 28,
    fontWeight: "900",
    marginTop: 8,
    marginBottom: 6,
  },
  subtitle: {
    color: C.sub,
    marginBottom: 16,
    lineHeight: 20,
  },
  card: {
    backgroundColor: C.card,
    borderWidth: 1,
    borderColor: C.cardBorder,
    borderRadius: 18,
    padding: 16,
  },
  cardTitle: {
    color: C.text,
    fontSize: 18,
    fontWeight: "900",
    marginBottom: 6,
    lineHeight: 24,
  },
  date: {
    color: C.sub,
    marginBottom: 8,
  },
  preview: {
    color: C.sub,
    marginBottom: 12,
    lineHeight: 20,
  },
  actionsRow: {
    flexDirection: "row",
    gap: 12,
  },
  primaryBtn: {
    backgroundColor: C.accent,
    paddingHorizontal: 16,
    height: 44,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  primaryBtnText: {
    color: "#0b1220",
    fontWeight: "900",
  },
  ghostBtn: {
    backgroundColor: "rgba(255,255,255,0.06)",
    paddingHorizontal: 16,
    height: 44,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: C.cardBorder,
  },
  ghostBtnText: {
    color: C.text,
    fontWeight: "900",
  },
  modalScrim: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,.55)",
    justifyContent: "flex-end",
  },
  modalSheet: {
    backgroundColor: GRAD.bgEnd,
    maxHeight: "88%",
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    borderWidth: 1,
    borderColor: C.cardBorder,
  },
  modalHeader: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  closeBtn: {
    padding: 6,
    marginRight: 8,
  },
  modalTitle: {
    color: C.text,
    fontWeight: "900",
    fontSize: 18,
    flex: 1,
  },
  modalLoading: {
    alignItems: "center",
    paddingVertical: 24,
  },
  modalScroll: {
    paddingHorizontal: 16,
    paddingBottom: 28,
  },
  articleText: {
    color: C.text,
    lineHeight: 22,
    fontSize: 15,
    marginBottom: 10,
  },
  explainWrap: {
    paddingHorizontal: 16,
    paddingBottom: 24,
  },
  explainTitle: {
    color: C.text,
    fontWeight: "900",
    fontSize: 16,
    marginBottom: 12,
    lineHeight: 22,
  },
  importanceRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 10,
  },
  importanceText: {
    color: C.text,
    marginLeft: 8,
  },
  explainLine: {
    color: C.sub,
    marginBottom: 6,
  },
  actionText: {
    color: C.text,
    marginTop: 8,
    marginBottom: 6,
  },
  noteText: {
    color: C.sub,
    lineHeight: 20,
  },
});