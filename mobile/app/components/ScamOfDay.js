import React, { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, Text, TouchableOpacity, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTranslation } from "react-i18next";
import ViewShot from "react-native-view-shot";

import { BACKEND } from "../lib/backend";
import { getAuthState } from "../lib/authApi";
import { getIdentityUserId, getInstallUserId, identityHeaders } from "../lib/identity";
import { shareImagePremium } from "../lib/sharePremium";
import AiVerdictCard from "./AiVerdictCard";

const UI = {
  text: "#E9EEFF",
  dim: "#A8B4CF",
  accent: "#FFB020",
  border: "rgba(255,255,255,0.12)",
  panel: "rgba(255,255,255,0.045)",
  danger: "#FF6B6B",
  good: "#29D37A",
};

function normalizeLang(value) {
  const lang = String(value || "en").toLowerCase();
  if (lang.startsWith("uk") || lang.startsWith("ua")) return "uk";
  return lang.startsWith("ru") ? "ru" : "en";
}

function textFromAnalysis(analysis) {
  const ai = analysis?.ai_explanation_result || {};
  const structured = ai?.structured || {};
  return String(
    ai?.text ||
      analysis?.ai_explanation ||
      structured?.details ||
      structured?.short ||
      ""
  ).trim();
}

function riskColor(level) {
  return String(level || "").toLowerCase() === "critical" ? UI.danger : UI.accent;
}

function riskLabel(level, t) {
  const value = String(level || "risk").toLowerCase();
  const key = ["critical", "danger", "suspicious", "medium", "safe"].includes(value) ? value : "risk";
  return t(`scamOfDay.levels.${key}`);
}

function dateLocale(language) {
  return language === "uk" ? "uk-UA" : language === "ru" ? "ru-RU" : "en-US";
}

export default function ScamOfDay({ mode = "today", signalId = "", embedded = false }) {
  const { t, i18n } = useTranslation();
  const language = normalizeLang(i18n?.language);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [sharingItem, setSharingItem] = useState(null);
  const openedSignal = useRef("");
  const shareCardRef = useRef(null);

  const identity = useCallback(async () => {
    const state = await getAuthState().catch(() => null);
    const accountId = String(state?.user?.email || state?.user?.id || "").trim();
    const storedId = await getIdentityUserId();
    return accountId || storedId || (await getInstallUserId());
  }, []);

  const request = useCallback(
    async (path, options = {}) => {
      const userId = await identity();
      const headers = await identityHeaders({
        Accept: "application/json",
        "X-User-Id": userId,
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      });
      const separator = path.includes("?") ? "&" : "?";
      const response = await fetch(`${BACKEND}${path}${separator}lang=${encodeURIComponent(language)}&userId=${encodeURIComponent(userId)}`, {
        ...options,
        headers,
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok || body?.ok === false) throw new Error(body?.message || body?.error || "request_failed");
      return body;
    },
    [identity, language]
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const body = await request(mode === "saved" ? "/scam-of-day/saved" : "/scam-of-day");
      setItems(Array.isArray(body?.items) ? body.items : []);
    } catch {
      setError(t("scamOfDay.errors.load"));
    } finally {
      setLoading(false);
    }
  }, [mode, request, t]);

  const openDetails = useCallback(
    async (item) => {
      if (!item?.id) return;
      setSelected(item);
      setAnalysis(null);
      setDetailsLoading(true);
      try {
        const body = await request(`/scam-of-day/${encodeURIComponent(item.id)}/analysis`);
        setAnalysis(body?.analysis || null);
      } catch {
        setAnalysis({ ai_explanation: t("scamOfDay.errors.analysis") });
      } finally {
        setDetailsLoading(false);
      }
    },
    [request, t]
  );

  const react = useCallback(
    async (item, reaction) => {
      const next = item.reaction === reaction ? null : reaction;
      try {
        await request(`/scam-of-day/${encodeURIComponent(item.id)}/reaction`, {
          method: "POST",
          body: JSON.stringify({ reaction: next }),
        });
        setItems((old) => old.map((entry) => (entry.id === item.id ? { ...entry, reaction: next } : entry)));
        if (selected?.id === item.id) setSelected((old) => ({ ...old, reaction: next }));
      } catch {
        setError(t("scamOfDay.errors.action"));
      }
    },
    [request, selected?.id, t]
  );

  const save = useCallback(
    async (item) => {
      const next = !item.saved;
      try {
        await request(`/scam-of-day/${encodeURIComponent(item.id)}/save`, {
          method: "POST",
          body: JSON.stringify({ saved: next }),
        });
        if (mode === "saved" && !next) setItems((old) => old.filter((entry) => entry.id !== item.id));
        else setItems((old) => old.map((entry) => (entry.id === item.id ? { ...entry, saved: next } : entry)));
        if (selected?.id === item.id) setSelected((old) => ({ ...old, saved: next }));
      } catch {
        setError(t("scamOfDay.errors.action"));
      }
    },
    [mode, request, selected?.id, t]
  );

  const share = useCallback(
    async (item) => {
      if (!item) return;
      setSharingItem(item);
      try {
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        await shareImagePremium({
          title: "Noytrix",
          dialogTitle: t("scamOfDay.share"),
          message: t("scamOfDay.shareText", { target: item.target || "Noytrix", risk: riskLabel(item.risk_level, t) }),
          capture: () => shareCardRef.current?.capture?.(),
        });
      } finally {
        setSharingItem(null);
      }
    },
    [t]
  );

  useEffect(() => {
    load();
    const timer = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!signalId || openedSignal.current === signalId || loading) return;
    const item = items.find((entry) => entry.id === signalId);
    if (item) {
      openedSignal.current = signalId;
      openDetails(item);
    }
  }, [items, loading, openDetails, signalId]);

  const heading = mode === "saved" ? t("scamOfDay.savedTitle") : t("scamOfDay.title");
  const empty = mode === "saved" ? t("scamOfDay.savedEmpty") : t("scamOfDay.empty");

  return (
    <View style={{ marginTop: embedded ? 0 : 14 }}>
      {!embedded && (
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <View style={{ flexDirection: "row", alignItems: "center", flex: 1 }}>
            <Ionicons name={mode === "saved" ? "bookmark" : "shield-checkmark"} size={20} color={UI.accent} />
            <Text style={{ color: UI.text, fontSize: 20, fontWeight: "900", marginLeft: 8 }}>{heading}</Text>
          </View>
          <TouchableOpacity accessibilityLabel={t("scamOfDay.refresh")} onPress={load} style={{ padding: 8 }}>
            <Ionicons name="refresh" size={20} color={UI.dim} />
          </TouchableOpacity>
        </View>
      )}

      {loading ? (
        <View style={{ paddingVertical: 18, alignItems: "center" }}><ActivityIndicator color={UI.accent} /></View>
      ) : error ? (
        <View style={{ borderRadius: 10, borderWidth: 1, borderColor: "rgba(255,107,107,0.45)", padding: 14 }}>
          <Text style={{ color: UI.text, fontWeight: "800" }}>{error}</Text>
          <TouchableOpacity onPress={load} style={{ marginTop: 10 }}><Text style={{ color: UI.accent, fontWeight: "900" }}>{t("scamOfDay.retry")}</Text></TouchableOpacity>
        </View>
      ) : items.length === 0 ? (
        <View style={{ borderRadius: 10, borderWidth: 1, borderColor: UI.border, padding: 14, backgroundColor: UI.panel }}>
          <Text style={{ color: UI.dim, lineHeight: 20 }}>{empty}</Text>
        </View>
      ) : (
        items.map((item) => (
          <View key={item.id} style={{ borderRadius: 10, borderWidth: 1, borderColor: UI.border, backgroundColor: UI.panel, padding: 14, marginBottom: 10 }}>
            <Pressable onPress={() => openDetails(item)}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                <View style={{ flex: 1, paddingRight: 10 }}>
                  <Text style={{ color: UI.text, fontWeight: "900", fontSize: 17 }}>{item.title}</Text>
                  <Text style={{ color: UI.accent, marginTop: 5, fontWeight: "800" }} numberOfLines={2}>{item.target}</Text>
                </View>
                <View style={{ borderRadius: 999, borderWidth: 1, borderColor: riskColor(item.risk_level), paddingHorizontal: 9, paddingVertical: 5 }}>
                  <Text style={{ color: riskColor(item.risk_level), fontWeight: "900", fontSize: 12 }}>{riskLabel(item.risk_level, t).toUpperCase()}</Text>
                </View>
              </View>
              <Text style={{ color: UI.dim, lineHeight: 20, marginTop: 9 }}>{item.summary}</Text>
              <Text style={{ color: "rgba(233,238,255,0.62)", marginTop: 9, fontSize: 12 }}>{item.source} - {item.detected_at ? new Date(item.detected_at).toLocaleString(dateLocale(language)) : ""}</Text>
            </Pressable>
            <View style={{ flexDirection: "row", alignItems: "center", marginTop: 10, gap: 7 }}>
              <TouchableOpacity onPress={() => react(item, "like")} style={{ padding: 7 }}><Ionicons name={item.reaction === "like" ? "thumbs-up" : "thumbs-up-outline"} color={item.reaction === "like" ? UI.good : UI.dim} size={19} /></TouchableOpacity>
              <TouchableOpacity onPress={() => react(item, "dislike")} style={{ padding: 7 }}><Ionicons name={item.reaction === "dislike" ? "thumbs-down" : "thumbs-down-outline"} color={item.reaction === "dislike" ? UI.danger : UI.dim} size={19} /></TouchableOpacity>
              <TouchableOpacity onPress={() => save(item)} style={{ padding: 7 }}><Ionicons name={item.saved ? "bookmark" : "bookmark-outline"} color={item.saved ? UI.accent : UI.dim} size={19} /></TouchableOpacity>
              <TouchableOpacity onPress={() => share(item)} style={{ padding: 7 }}><Ionicons name="share-social-outline" color={UI.dim} size={19} /></TouchableOpacity>
            </View>
          </View>
        ))
      )}

      <Modal transparent visible={!!selected} animationType="fade" onRequestClose={() => setSelected(null)}>
        <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.76)", justifyContent: "center", padding: 18 }}>
          <View style={{ maxHeight: "82%", borderRadius: 10, borderWidth: 1, borderColor: UI.border, backgroundColor: "#0A1233", padding: 16 }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Text style={{ color: UI.text, fontSize: 20, fontWeight: "900", flex: 1 }}>{t("scamOfDay.fullTitle")}</Text>
              <TouchableOpacity onPress={() => setSelected(null)} style={{ padding: 5 }}><Ionicons name="close" size={24} color={UI.dim} /></TouchableOpacity>
            </View>
            <ScrollView showsVerticalScrollIndicator={false} style={{ marginTop: 10 }}>
              <Text style={{ color: UI.accent, fontWeight: "900" }}>{selected?.target}</Text>
              {detailsLoading ? <ActivityIndicator style={{ marginVertical: 24 }} color={UI.accent} /> : <AiVerdictCard title={t("scamOfDay.aiVerdict")} text={textFromAnalysis(analysis)} emptyText={t("scamOfDay.errors.analysis")} />}
              {!detailsLoading && analysis?.ai_explanation_result?.structured?.risks?.length > 0 && (
                <View style={{ marginTop: 12 }}>
                  <Text style={{ color: UI.text, fontWeight: "900", marginBottom: 6 }}>{t("scamOfDay.risks")}</Text>
                  {analysis.ai_explanation_result.structured.risks.map((risk, index) => <Text key={`${risk}-${index}`} style={{ color: UI.dim, lineHeight: 20 }}>- {risk}</Text>)}
                </View>
              )}
              {!detailsLoading && analysis?.ai_explanation_result?.structured?.actions?.length > 0 && (
                <View style={{ marginTop: 12 }}>
                  <Text style={{ color: UI.text, fontWeight: "900", marginBottom: 6 }}>{t("scamOfDay.actions")}</Text>
                  {analysis.ai_explanation_result.structured.actions.map((action, index) => <Text key={`${action}-${index}`} style={{ color: UI.dim, lineHeight: 20 }}>- {action}</Text>)}
                </View>
              )}
              <Text style={{ color: UI.dim, marginTop: 16, lineHeight: 20 }}>{t("scamOfDay.sourceNote")}</Text>
            </ScrollView>
          </View>
        </View>
      </Modal>

      {sharingItem && (
        <View pointerEvents="none" style={{ position: "absolute", left: -10000, top: -10000 }}>
          <ViewShot ref={shareCardRef} options={{ format: "png", quality: 1, result: "tmpfile" }}>
            <View style={{ width: 900, minHeight: 1120, padding: 54, backgroundColor: "#07102D", borderWidth: 3, borderColor: riskColor(sharingItem.risk_level) }}>
              <Text style={{ color: UI.accent, fontSize: 40, fontWeight: "900", letterSpacing: 1 }}>NOYTRIX</Text>
              <View style={{ height: 1, backgroundColor: "rgba(233,238,255,0.18)", marginVertical: 28 }} />
              <Text style={{ color: UI.dim, fontSize: 22, fontWeight: "800", letterSpacing: 1 }}>{t("scamOfDay.shareCardKicker").toUpperCase()}</Text>
              <Text style={{ color: riskColor(sharingItem.risk_level), fontSize: 54, lineHeight: 61, fontWeight: "900", marginTop: 12 }}>
                {riskLabel(sharingItem.risk_level, t).toUpperCase()}
              </Text>
              <Text style={{ color: UI.text, fontSize: 34, lineHeight: 43, fontWeight: "900", marginTop: 24 }} numberOfLines={3}>
                {sharingItem.target || sharingItem.title || "Noytrix"}
              </Text>
              <View style={{ height: 14, borderRadius: 99, backgroundColor: riskColor(sharingItem.risk_level), marginTop: 28 }} />
              <View style={{ marginTop: 34, padding: 28, borderRadius: 18, borderWidth: 1, borderColor: "rgba(233,238,255,0.18)", backgroundColor: "rgba(255,255,255,0.05)" }}>
                <Text style={{ color: UI.dim, fontSize: 20, fontWeight: "800", marginBottom: 13 }}>{t("scamOfDay.shareCardSummary")}</Text>
                <Text style={{ color: UI.text, fontSize: 27, lineHeight: 37 }}>{sharingItem.summary}</Text>
              </View>
              <Text style={{ color: UI.dim, fontSize: 19, lineHeight: 28, marginTop: 36 }}>{t("scamOfDay.shareCardFooter")}</Text>
              <Text style={{ color: "rgba(233,238,255,0.58)", fontSize: 17, marginTop: 34 }}>
                {sharingItem.detected_at ? new Date(sharingItem.detected_at).toLocaleDateString(dateLocale(language)) : ""}  |  Noytrix ScamShield
              </Text>
            </View>
          </ViewShot>
        </View>
      )}
    </View>
  );
}
