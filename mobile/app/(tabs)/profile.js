// app/(tabs)/profile.js
import React, { useEffect, useMemo, useState, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  Image,
  Modal,
  TextInput,
  Switch,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Stack, useRouter, Link } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { BlurView } from "expo-blur";
import { LinearGradient } from "expo-linear-gradient";
import * as ImagePicker from "expo-image-picker";
import { useTranslation } from "react-i18next";

import { useAuthStore } from "../lib/store.auth";
import SignIn from "../auth/signin";
import { getPushSubscriptionState, setPushNotificationsEnabled } from "../lib/notifications";
import { BACKEND } from "../lib/backend";

const BG = { start: "#06080f", mid: "#0a1233", end: "#0b1c4f" };
const UI = {
  card: "rgba(8,14,36,0.98)",
  border: "rgba(255,255,255,0.12)",
  text: "#E9EEFF",
  dim: "#BFD0FF",
  mute: "rgba(231,238,255,0.70)",
  brand: "#FFB020",
  good: "#29D37A",
  bad: "#FF6B6B",
  warn: "#FF8A3D",
};

const AUTH_KEY = "auth_state_v1";
const AVATAR_SIZE = 64;
const EMPTY_VALUE = "-";

const cardChrome = (extra = {}) => ({
  backgroundColor: UI.card,
  borderRadius: 18,
  borderWidth: 1,
  borderColor: UI.border,
  overflow: "hidden",
  ...extra,
});

const pillBase = {
  borderWidth: 1,
  borderColor: UI.border,
  borderRadius: 999,
  paddingHorizontal: 12,
  paddingVertical: 6,
  backgroundColor: "rgba(255,255,255,0.04)",
};

async function persistAuthUserOnly(nextUser) {
  try {
    const raw = await AsyncStorage.getItem(AUTH_KEY);
    const prev = raw ? JSON.parse(raw) : {};
    const next = {
      user: nextUser ?? null,
      access_token: prev?.access_token ?? null,
      refresh_token: prev?.refresh_token ?? null,
    };
    await AsyncStorage.setItem(AUTH_KEY, JSON.stringify(next));
  } catch {}
}

async function getAuthAccessToken() {
  try {
    const raw = await AsyncStorage.getItem(AUTH_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed?.access_token || null;
  } catch {
    return null;
  }
}

function getScoreTone(score) {
  if (score >= 75) return UI.good;
  if (score >= 45) return UI.brand;
  return UI.bad;
}

function safeNum(v, fb = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fb;
}

export default function ProfileScreen() {
  const header = <Stack.Screen options={{ headerShown: false }} />;
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const rawLang = String(i18n?.language || "en").toLowerCase();
  const currentLang = rawLang.startsWith("ru")
    ? "ru"
    : rawLang.startsWith("uk") || rawLang.startsWith("ua")
    ? "uk"
    : "en";

  const isAuth = useAuthStore((s) => s.isAuth);
  const user = useAuthStore((s) => s.user);
  const logoutStore = useAuthStore((s) => s.logout);
  const avatarUri = useAuthStore((s) => s.avatarUri);
  const setAvatarUri = useAuthStore((s) => s.setAvatarUri);
  const setUserStore = useAuthStore((s) => s.setUser);

  const showSignIn = !isAuth || !user;

  const [nickModalVisible, setNickModalVisible] = useState(false);
  const [nickDraft, setNickDraft] = useState("");

  const [proLocal, setProLocal] = useState(false);
  const [notifEnabled, setNotifEnabled] = useState(false);

  const [profileData, setProfileData] = useState(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileRefreshing, setProfileRefreshing] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const v1 = await AsyncStorage.getItem("noytrix_pro_flag");
        const v2 = await AsyncStorage.getItem("isPro");
        setProLocal(v1 === "1" || v2 === "true");
      } catch {}
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const v = await AsyncStorage.getItem("profile.notifications");
        if (v === "0") {
          setNotifEnabled(false);
        } else if (v === "1") {
          setNotifEnabled(true);
        } else {
          const state = getPushSubscriptionState();
          setNotifEnabled(state.optedIn === true);
        }
      } catch {}
    })();
  }, []);

  const onToggleNotifs = useCallback(async () => {
    let next = !notifEnabled;

    try {
      const state = await setPushNotificationsEnabled(next, { request: next });
      next = next ? state.optedIn === true || !!state.id || !!state.token : false;
    } catch {
      next = false;
    }

    setNotifEnabled(next);
    try {
      await AsyncStorage.setItem("profile.notifications", next ? "1" : "0");
    } catch {}
  }, [notifEnabled]);

  const displayName =
    user?.displayName ||
    user?.login ||
    user?.username ||
    user?.nick ||
    user?.name ||
    (user?.email ? user.email.split("@")[0] : "") ||
    "User";

  const avatarLetter = displayName.slice(0, 1).toUpperCase();

  const fetchProfile = useCallback(
    async (refresh = false) => {
      if (!user) {
        setProfileData(null);
        return;
      }

      try {
        if (refresh) setProfileRefreshing(true);
        else setProfileLoading(true);

        const token = await getAuthAccessToken();
        const userId =
          user?.email ||
          user?.nick ||
          user?.username ||
          user?.login ||
          user?.name ||
          "";

        const qs = new URLSearchParams();
        if (userId) qs.append("userId", userId);
        qs.append("lang", currentLang);

        const resp = await fetch(`${BACKEND}/profile/overview?${qs.toString()}`, {
          method: "GET",
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
        });

        const text = await resp.text();
        let data = null;

        try {
          data = text ? JSON.parse(text) : null;
        } catch {
          data = null;
        }

        if (!resp.ok || !data?.ok) {
          throw new Error(`profile/overview failed: ${resp.status} ${text}`);
        }

        setProfileData(data);

        if (data?.proAccess?.isPro) {
          await AsyncStorage.multiSet([
            ["isPro", "true"],
            ["noytrix.isPro", "true"],
            ["pro", "true"],
            ["proActive", "true"],
            ["subscription.pro", "true"],
            ["iap.isPro", "true"],
            ["entitlement.pro", "active"],
            ["entitlement.id", "pro"],
            ["entitlementId", "pro"],
            ["noytrix_pro_flag", "1"],
          ]);
          setProLocal(true);
        }
      } catch (e) {
        console.log("profile fetch error:", e);
        setProfileData(null);
      } finally {
        if (refresh) setProfileRefreshing(false);
        else setProfileLoading(false);
      }
    },
    [user, currentLang]
  );

  useEffect(() => {
    fetchProfile(false);
  }, [fetchProfile]);

  const handlePickAvatar = useCallback(async () => {
    try {
      const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (status !== "granted") return;

      const res = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.8,
      });

      if (res.canceled) return;
      const uri = res.assets?.[0]?.uri;
      if (uri) await setAvatarUri(uri);
    } catch (e) {
      console.log("pick avatar error:", e);
    }
  }, [setAvatarUri]);

  const openNickModal = useCallback(() => {
    setNickDraft(user?.nick || user?.name || displayName);
    setNickModalVisible(true);
  }, [user, displayName]);

  const handleSaveNick = useCallback(async () => {
    if (!user) {
      setNickModalVisible(false);
      return;
    }

    const n = nickDraft.trim();
    if (!n) {
      setNickModalVisible(false);
      return;
    }

    const updated = { ...user, nick: n, name: n, displayName: n };
    setUserStore(updated);
    await persistAuthUserOnly(updated);
    setNickModalVisible(false);
  }, [nickDraft, user, setUserStore]);

  const handleLogout = useCallback(async () => {
    try {
      try {
        await logoutStore?.();
      } catch (e) {
        console.log("logoutStore error:", e);
      }

      try {
        await AsyncStorage.multiRemove(["noytrix:user", "noytrix:tokens"]);
      } catch (e) {
        console.log("AsyncStorage clear error:", e);
      }
    } finally {
      router.replace("/");
    }
  }, [logoutStore, router]);

  const identity = useMemo(() => {
    const api = profileData?.identity || {};
    return {
      displayName: api?.displayName || displayName,
      email: api?.email || user?.email || EMPTY_VALUE,
      memberSince: formatMemberSince(api?.memberSince),
      level: safeNum(api?.level, 1),
      rank: api?.rank || "Explorer",
      plan: String(api?.plan || user?.plan || "").toLowerCase(),
    };
  }, [profileData, displayName, user]);

  const isPro = useMemo(() => {
    return (
      !!profileData?.proAccess?.isPro ||
      identity.plan === "pro" ||
      String(user?.plan || "").toLowerCase() === "pro" ||
      proLocal
    );
  }, [profileData, identity.plan, user, proLocal]);

  const trust = useMemo(() => {
    const api = profileData?.trust || {};
    const score = safeNum(api?.score, 0);
    return {
      score,
      rank: api?.rank || identity.rank,
      level: safeNum(api?.level, identity.level),
      checks: safeNum(api?.scamScans, 0),
      safeChecks: safeNum(api?.safeResults, 0),
      suspiciousResults: safeNum(api?.suspiciousResults, 0),
      maliciousDetected: safeNum(api?.dangerResults, 0),
      communityVotes: safeNum(api?.communityVotes, 0),
      explainSessions: safeNum(api?.explainSessions, 0),
      immunitySessions: safeNum(api?.immunitySessions, 0),
      tone: getScoreTone(score),
    };
  }, [profileData, identity.rank, identity.level]);

  const activity = useMemo(() => {
    const api = profileData?.activity || {};
    return {
      totalActivity: safeNum(api?.totalActivity, 0),
      scans: safeNum(api?.scamScans, 0),
      explains: safeNum(api?.newsExplains, 0),
      immunityAnalyses: safeNum(api?.immunityAnalyses, 0),
      tokensChecked: safeNum(api?.tokensChecked, 0),
      topSymbol: api?.topSymbol || EMPTY_VALUE,
      communityVotes: safeNum(api?.communityVotes, 0),
      alertsUsed: notifEnabled ? 1 : 0,
    };
  }, [profileData, notifEnabled]);

  const trading = useMemo(() => {
    const api = profileData?.tradingPerformance || {};
    return {
      total: safeNum(api?.setupsAnalyzed, 0),
      approvedSetups: safeNum(api?.approvedSetups, 0),
      riskySetups: safeNum(api?.riskySetups, 0),
      rejectedSetups: safeNum(api?.rejectedSetups, 0),
      acceptanceRate: safeNum(api?.acceptanceRate, 0),
    };
  }, [profileData]);

  const achievements = useMemo(() => {
    return Array.isArray(profileData?.achievements) ? profileData.achievements : [];
  }, [profileData]);

  return (
    <View style={{ flex: 1, backgroundColor: BG.start }}>
      {header}

      <LinearGradient
        colors={[BG.start, BG.mid, BG.end]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={{ position: "absolute", inset: 0 }}
        pointerEvents="none"
      />

      {showSignIn ? (
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 120 }}>
          <HeaderBlock
            title={t("profile.title")}
            subtitle={t("profile.subtitleLoggedOut")}
          />

          <View style={[cardChrome(), { marginTop: 12 }]}>
            <BlurView intensity={18} tint="dark" style={{ padding: 14 }}>
              <SignIn />
            </BlurView>
          </View>
        </ScrollView>
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: 16, paddingBottom: 120 }}
          refreshControl={
            <RefreshControl
              refreshing={profileRefreshing}
              onRefresh={() => fetchProfile(true)}
              tintColor={UI.brand}
            />
          }
        >
          <HeaderBlock
            title={t("profile.title")}
            subtitle={t("profile.subtitleLoggedIn")}
          />

          {profileLoading ? (
            <View style={[cardChrome(), { marginTop: 12 }]}>
              <BlurView intensity={18} tint="dark" style={{ padding: 22 }}>
                <View style={{ alignItems: "center", justifyContent: "center" }}>
                  <ActivityIndicator size="small" color={UI.brand} />
                  <Text style={{ color: UI.mute, marginTop: 10 }}>
                    {t("profile.loading", { defaultValue: "Loading profile..." })}
                  </Text>
                </View>
              </BlurView>
            </View>
          ) : (
            <>
              <View style={[cardChrome(), { marginTop: 12 }]}>
                <BlurView intensity={18} tint="dark" style={{ padding: 14 }}>
                  <View style={{ flexDirection: "row", alignItems: "center" }}>
                    <TouchableOpacity activeOpacity={0.9} onPress={handlePickAvatar}>
                      {avatarUri ? (
                        <Image
                          source={{ uri: avatarUri }}
                          style={{
                            width: AVATAR_SIZE,
                            height: AVATAR_SIZE,
                            borderRadius: 999,
                            borderWidth: 1,
                            borderColor: UI.border,
                          }}
                        />
                      ) : (
                        <View
                          style={{
                            width: AVATAR_SIZE,
                            height: AVATAR_SIZE,
                            borderRadius: 999,
                            borderWidth: 1,
                            borderColor: UI.border,
                            backgroundColor: "rgba(255,255,255,0.06)",
                            alignItems: "center",
                            justifyContent: "center",
                          }}
                        >
                          <Text style={{ color: UI.text, fontWeight: "900", fontSize: 22 }}>
                            {avatarLetter}
                          </Text>
                        </View>
                      )}
                    </TouchableOpacity>

                    <View style={{ flex: 1, marginLeft: 12 }}>
                      <View
                        style={{
                          flexDirection: "row",
                          alignItems: "flex-start",
                          justifyContent: "space-between",
                        }}
                      >
                        <View style={{ flex: 1, paddingRight: 12 }}>
                          <Text style={{ color: UI.text, fontWeight: "900", fontSize: 20 }}>
                            {identity.displayName}
                          </Text>
                          {!!identity.email && (
                            <Text style={{ color: UI.mute, marginTop: 3 }}>{identity.email}</Text>
                          )}
                        </View>

                        <TouchableOpacity onPress={openNickModal} activeOpacity={0.9}>
                          <Text style={{ color: UI.brand, fontWeight: "900", fontSize: 12 }}>
                            {t("profile.nick.change")}
                          </Text>
                        </TouchableOpacity>
                      </View>

                      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
                        <Pill tone="brand">{`${t("profile.identity.level", { defaultValue: "Level" })} ${identity.level}`}</Pill>
                        <Pill>{`${t("profile.identity.memberSince", { defaultValue: "Member since" })} ${identity.memberSince}`}</Pill>
                        {isPro ? <Pill tone="success">PRO</Pill> : <Pill>FREE</Pill>}
                      </View>
                    </View>
                  </View>

                  <View
                    style={{
                      marginTop: 14,
                      paddingTop: 14,
                      borderTopWidth: 1,
                      borderTopColor: "rgba(255,255,255,0.08)",
                      flexDirection: "row",
                      justifyContent: "space-between",
                    }}
                  >
                    <MiniMetric
                      label={t("profile.identity.rankLabel", { defaultValue: "Rank" })}
                      value={identity.rank}
                      align="left"
                    />
                    <MiniMetric
                      label={t("profile.identity.trustLabel", { defaultValue: "Trust" })}
                      value={`${trust.score}/100`}
                      align="center"
                    />
                    <MiniMetric
                      label={t("profile.identity.activityLabel", { defaultValue: "Activity" })}
                      value={String(activity.totalActivity)}
                      align="right"
                    />
                  </View>
                </BlurView>
              </View>
              {!isPro ? (
                <View
                  style={[
                    cardChrome({ borderColor: "rgba(255,176,32,0.55)" }),
                    { marginTop: 12 },
                  ]}
                >
                  <BlurView intensity={18} tint="dark" style={{ padding: 14 }}>
                    <Text style={{ color: UI.brand, fontWeight: "900", marginBottom: 6 }}>
                      {t("profile.proCard.title")}
                    </Text>
                    <Text style={{ color: UI.mute }}>{t("profile.proCard.text")}</Text>

                    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
                      <FeaturePill text={t("profile.pro.features.scamshield", { defaultValue: "ScamShield PRO" })} />
                      <FeaturePill text={t("profile.pro.features.explain", { defaultValue: "Explain PRO" })} />
                      <FeaturePill text={t("profile.pro.features.deepScan", { defaultValue: "Deep scan" })} />
                      <FeaturePill text={t("profile.pro.features.market", { defaultValue: "Market intelligence" })} />
                    </View>

                    <Link href="/pro" asChild>
                      <TouchableOpacity
                        activeOpacity={0.9}
                        style={{
                          marginTop: 12,
                          backgroundColor: UI.brand,
                          borderRadius: 14,
                          paddingVertical: 12,
                          alignItems: "center",
                        }}
                      >
                        <Text style={{ color: "#0b1220", fontWeight: "900" }}>
                          {t("profile.proCard.button")}
                        </Text>
                      </TouchableOpacity>
                    </Link>
                  </BlurView>
                </View>
              ) : (
                <View
                  style={[
                    cardChrome({ borderColor: "rgba(41,211,122,0.55)" }),
                    { marginTop: 12 },
                  ]}
                >
                  <BlurView intensity={18} tint="dark" style={{ padding: 14 }}>
                    <Text style={{ color: UI.good, fontWeight: "900", marginBottom: 6 }}>
                      {t("profile.proActiveCard.title")}
                    </Text>
                    <Text style={{ color: UI.mute, marginBottom: 12 }}>
                      {t("profile.proActiveCard.text")}
                    </Text>

                    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                      <FeaturePill text={t("profile.pro.features.scamshield", { defaultValue: "ScamShield PRO" })} tone="success" />
                      <FeaturePill text={t("profile.pro.features.explain", { defaultValue: "Explain PRO" })} tone="success" />
                      <FeaturePill text={t("profile.pro.features.deepScan", { defaultValue: "Deep scan" })} tone="success" />
                      <FeaturePill text={t("profile.pro.features.market", { defaultValue: "Market intelligence" })} tone="success" />
                    </View>

                    <Link href="/pro" asChild>
                      <TouchableOpacity
                        activeOpacity={0.9}
                        style={{
                          marginTop: 12,
                          backgroundColor: "rgba(41,211,122,0.14)",
                          borderRadius: 14,
                          paddingVertical: 12,
                          alignItems: "center",
                          borderWidth: 1,
                          borderColor: "rgba(41,211,122,0.75)",
                        }}
                      >
                        <Text style={{ color: UI.good, fontWeight: "900" }}>
                          {t("profile.proActiveCard.button")}
                        </Text>
                      </TouchableOpacity>
                    </Link>
                  </BlurView>
                </View>
              )}

              <Section
                title={t("profile.sections.trust", { defaultValue: "Trust Score" })}
                icon="shield-checkmark-outline"
              >
                <View
                  style={{
                    borderRadius: 16,
                    borderWidth: 1,
                    borderColor: "rgba(255,255,255,0.08)",
                    backgroundColor: "rgba(255,255,255,0.03)",
                    padding: 14,
                  }}
                >
                  <View
                    style={{
                      flexDirection: "row",
                      alignItems: "center",
                      justifyContent: "space-between",
                    }}
                  >
                    <View>
                      <Text style={{ color: UI.mute }}>
                        {t("profile.trust.label", { defaultValue: "Trust Score" })}
                      </Text>
                      <Text style={{ color: trust.tone, fontSize: 30, fontWeight: "900", marginTop: 4 }}>
                        {trust.score}
                        <Text style={{ color: UI.dim, fontSize: 18 }}>/100</Text>
                      </Text>
                    </View>

                    <View
                      style={{
                        width: 74,
                        height: 74,
                        borderRadius: 999,
                        borderWidth: 3,
                        borderColor: trust.tone,
                        alignItems: "center",
                        justifyContent: "center",
                        backgroundColor: "rgba(255,255,255,0.03)",
                      }}
                    >
                      <Ionicons name="shield-half-outline" size={28} color={trust.tone} />
                    </View>
                  </View>

                  <Text style={{ color: UI.mute, marginTop: 10, lineHeight: 20 }}>
                    {t("profile.trust.subtitle", {
                      defaultValue:
                        "Calculated from scans, safe activity, community signals, and usage of core product modules.",
                    })}
                  </Text>
                </View>

                <StatsGrid
                  items={[
                    {
                      label: t("profile.trust.scans", { defaultValue: "Scans" }),
                      value: trust.checks,
                    },
                    {
                      label: t("profile.trust.safe", { defaultValue: "Safe" }),
                      value: trust.safeChecks,
                      tone: "good",
                    },
                    {
                      label: t("profile.trust.malicious", { defaultValue: "Danger" }),
                      value: trust.maliciousDetected,
                      tone: trust.maliciousDetected > 0 ? "bad" : "default",
                    },
                    {
                      label: t("profile.trust.community", { defaultValue: "Community" }),
                      value: trust.communityVotes,
                    },
                  ]}
                />
              </Section>

              <Section
                title={t("profile.sections.activity", { defaultValue: "Activity" })}
                icon="pulse-outline"
              >
                <StatsGrid
                  items={[
                    {
                      label: t("profile.activity.scans", { defaultValue: "Scam scans" }),
                      value: activity.scans,
                    },
                    {
                      label: t("profile.activity.explains", { defaultValue: "Explain sessions" }),
                      value: activity.explains,
                    },
                    {
                      label: t("profile.activity.tokens", { defaultValue: "Assets checked" }),
                      value: activity.tokensChecked,
                    },
                    {
                      label: t("profile.activity.alerts", { defaultValue: "Alerts used" }),
                      value: activity.alertsUsed,
                    },
                  ]}
                />

                <View
                  style={{
                    marginTop: 12,
                    borderTopWidth: 1,
                    borderTopColor: "rgba(255,255,255,0.08)",
                    paddingTop: 12,
                  }}
                >
                  <Text style={{ color: UI.text, fontWeight: "900" }}>
                    {t("profile.activity.topSymbolLabel", { defaultValue: "Top asset" })}
                  </Text>
                  <Text style={{ color: UI.mute, marginTop: 4 }}>
                    {activity.topSymbol === EMPTY_VALUE
                      ? t("profile.activity.topSymbolEmpty", {
                          defaultValue: "No dominant asset yet.",
                        })
                      : t("profile.activity.topSymbolValue", {
                          symbol: activity.topSymbol,
                          defaultValue: `Most checked: ${activity.topSymbol}`,
                        })}
                  </Text>
                </View>
              </Section>

              <Section
                title={t("profile.sections.trading", { defaultValue: "Trading Performance" })}
                icon="stats-chart-outline"
              >
                <StatsGrid
                  items={[
                    {
                      label: t("profile.trading.total", { defaultValue: "Setups analyzed" }),
                      value: trading.total || "0",
                    },
                    {
                      label: t("profile.trading.winRate", { defaultValue: "Acceptance rate" }),
                      value: trading.total ? `${trading.acceptanceRate}%` : EMPTY_VALUE,
                      tone: trading.acceptanceRate >= 50 ? "good" : "default",
                    },
                    {
                      label: t("profile.trading.avgRisk", { defaultValue: "Approved" }),
                      value: trading.total ? `${trading.approvedSetups}` : EMPTY_VALUE,
                      tone: trading.approvedSetups > 0 ? "good" : "default",
                    },
                    {
                      label: t("profile.trading.best", { defaultValue: "Rejected" }),
                      value: trading.total ? `${trading.rejectedSetups}` : EMPTY_VALUE,
                      tone: trading.rejectedSetups > 0 ? "bad" : "default",
                    },
                  ]}
                />

                <View style={{ marginTop: 12 }}>
                  <StatRow
                    label={t("profile.trading.bestTrade", { defaultValue: "Approved setups" })}
                    value={String(trading.approvedSetups)}
                    valueColor={trading.approvedSetups > 0 ? UI.good : UI.text}
                  />
                  <StatRow
                    label={t("profile.trading.worstTrade", { defaultValue: "Risky setups" })}
                    value={String(trading.riskySetups)}
                    valueColor={trading.riskySetups > 0 ? UI.brand : UI.text}
                  />
                  <StatRow
                    label={t("profile.trading.rejectedLabel", { defaultValue: "Rejected setups" })}
                    value={String(trading.rejectedSetups)}
                    valueColor={trading.rejectedSetups > 0 ? UI.bad : UI.text}
                  />
                </View>

                <View style={{ marginTop: 14 }}>
                  <Text style={{ color: UI.text, fontWeight: "900", marginBottom: 8 }}>
                    {t("profile.trading.recent", { defaultValue: "Performance summary" })}
                  </Text>
                  <Text style={{ color: UI.mute, lineHeight: 20 }}>
                    {trading.total > 0
                      ? t("profile.trading.summaryValue", {
                          total: trading.total,
                          approved: trading.approvedSetups,
                          risky: trading.riskySetups,
                          rejected: trading.rejectedSetups,
                          defaultValue: `You analyzed ${trading.total} setups. ${trading.approvedSetups} were approved, ${trading.riskySetups} marked risky, and ${trading.rejectedSetups} rejected by the Risk Engine.`,
                        })
                      : t("profile.sections.futuresEmpty", {
                          defaultValue: "No setup analyses recorded yet.",
                        })}
                  </Text>
                </View>
              </Section>

              <Section
                title={t("profile.sections.achievements")}
                icon="trophy-outline"
              >
                {achievements.length === 0 ? (
                  <Text style={{ color: UI.mute }}>
                    {t("profile.sections.achievementsEmpty")}
                  </Text>
                ) : (
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                    {achievements.map((a) => {
                      const rawText = a.text || a.title || a.code;

                      const key =
                        a.code
                          ? `profile.achievements.items.${a.code}`
                          : rawText?.toLowerCase().includes("первая")
                          ? "profile.achievements.items.first_scamshield_scan"
                          : rawText?.toLowerCase().includes("10")
                          ? "profile.achievements.items.ten_scamshield_scans"
                          : rawText?.toLowerCase().includes("3 опас")
                          ? "profile.achievements.items.three_danger_results"
                          : rawText?.toLowerCase().includes("5 анализ")
                          ? "profile.achievements.items.five_setup_analyses"
                          : rawText?.toLowerCase().includes("3 одоб")
                          ? "profile.achievements.items.three_approved_setups"
                          : null;

                      return (
                        <Pill key={a.code || a.text} tone="brand">
                          {key ? t(key, { defaultValue: rawText }) : rawText}
                        </Pill>
                      );
                    })}
                  </View>
                )}
              </Section>

              <Section
                title={t("profile.sections.settingsSecurity", {
                  defaultValue: "Settings & Security",
                })}
                icon="settings-outline"
              >
                <RowCard
                  icon="notifications-outline"
                  title={t("profile.notifications.title")}
                  subtitle={t("profile.notifications.text")}
                  right={
                    <Switch
                      value={notifEnabled}
                      onValueChange={onToggleNotifs}
                      thumbColor={notifEnabled ? UI.brand : "#f4f3f4"}
                      trackColor={{
                        false: "rgba(255,255,255,0.2)",
                        true: "rgba(255,176,32,0.45)",
                      }}
                    />
                  }
                />

                <RowCard
                  icon="mail-outline"
                  title={t("profile.security.email", { defaultValue: "Connected email" })}
                  subtitle={identity.email || EMPTY_VALUE}
                />

                <RowCard
                  icon="shield-checkmark-outline"
                  title={t("profile.security.session", { defaultValue: "Account protection" })}
                  subtitle={
                    isPro
                      ? t("profile.security.protectedPro", {
                          defaultValue: "PRO account protection active.",
                        })
                      : t("profile.security.protected", {
                          defaultValue: "Standard account protection active.",
                        })
                  }
                />

                <TouchableOpacity
                  onPress={handleLogout}
                  activeOpacity={0.9}
                  style={{
                    marginTop: 12,
                    backgroundColor: UI.brand,
                    borderRadius: 14,
                    alignItems: "center",
                    paddingVertical: 12,
                  }}
                >
                  <Text style={{ color: "#0b1220", fontWeight: "900" }}>
                    {t("profile.logout.button")}
                  </Text>
                </TouchableOpacity>
              </Section>
            </>
          )}
        </ScrollView>
      )}

      <Modal visible={nickModalVisible} transparent animationType="fade">
        <View
          style={{
            flex: 1,
            backgroundColor: "rgba(0,0,0,0.75)",
            alignItems: "center",
            justifyContent: "center",
            padding: 16,
          }}
        >
          <View style={[cardChrome({ width: "100%", maxWidth: 520 }), { borderRadius: 20 }]}>
            <BlurView intensity={18} tint="dark" style={{ padding: 16 }}>
              <Text style={{ color: UI.brand, fontSize: 18, fontWeight: "900" }}>
                {t("profile.nick.title")}
              </Text>
              <Text style={{ color: UI.mute, marginTop: 6 }}>
                {t("profile.nick.subtitle")}
              </Text>

              <TextInput
                value={nickDraft}
                onChangeText={setNickDraft}
                placeholder={t("profile.nick.placeholder")}
                placeholderTextColor="rgba(231,238,255,0.45)"
                style={{
                  marginTop: 12,
                  color: UI.text,
                  paddingHorizontal: 12,
                  paddingVertical: 12,
                  fontSize: 16,
                  backgroundColor: "rgba(255,255,255,0.04)",
                  borderWidth: 1,
                  borderColor: UI.border,
                  borderRadius: 14,
                }}
              />

              <TouchableOpacity
                onPress={handleSaveNick}
                activeOpacity={0.9}
                style={{
                  marginTop: 12,
                  backgroundColor: UI.brand,
                  borderRadius: 14,
                  paddingVertical: 12,
                  alignItems: "center",
                }}
              >
                <Text style={{ color: "#0b1220", fontWeight: "900" }}>
                  {t("profile.nick.save")}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => setNickModalVisible(false)}
                activeOpacity={0.9}
                style={{
                  marginTop: 10,
                  borderRadius: 14,
                  paddingVertical: 12,
                  alignItems: "center",
                  backgroundColor: "rgba(255,255,255,0.04)",
                  borderWidth: 1,
                  borderColor: UI.border,
                }}
              >
                <Text style={{ color: UI.text, fontWeight: "900" }}>
                  {t("profile.nick.cancel")}
                </Text>
              </TouchableOpacity>
            </BlurView>
          </View>
        </View>
      </Modal>
    </View>
  );
}

function formatMemberSince(raw) {
  if (!raw) return EMPTY_VALUE;
  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) {
    const s = String(raw);
    const match = s.match(/\d{4}/);
    return match ? match[0] : EMPTY_VALUE;
  }
  return String(dt.getFullYear());
}

function HeaderBlock({ title, subtitle }) {
  return (
    <View style={{ marginTop: 14 }}>
      <Text
        style={{
          fontSize: 34,
          fontWeight: "900",
          color: UI.brand,
          letterSpacing: 0.3,
        }}
      >
        {title}
      </Text>
      <Text
        style={{
          color: UI.dim,
          fontSize: 16,
          fontWeight: "700",
          marginTop: 6,
          lineHeight: 22,
        }}
      >
        {subtitle}
      </Text>
    </View>
  );
}

function Section({ title, icon, children }) {
  return (
    <View style={[cardChrome(), { marginTop: 12 }]}>
      <BlurView intensity={18} tint="dark" style={{ padding: 14 }}>
        <View
          style={{
            flexDirection: "row",
            alignItems: "center",
            gap: 8,
            marginBottom: 10,
          }}
        >
          <Ionicons name={icon} size={18} color={UI.dim} />
          <Text style={{ color: UI.text, fontWeight: "900", fontSize: 16 }}>{title}</Text>
        </View>
        {children}
      </BlurView>
    </View>
  );
}

function MiniMetric({ label, value, align = "left" }) {
  return (
    <View style={{ flex: 1 }}>
      <Text
        style={{
          color: UI.mute,
          fontSize: 11,
          textAlign: align,
        }}
      >
        {label}
      </Text>
      <Text
        style={{
          color: UI.text,
          fontWeight: "900",
          marginTop: 4,
          textAlign: align,
        }}
      >
        {value}
      </Text>
    </View>
  );
}

function StatsGrid({ items = [] }) {
  return (
    <View
      style={{
        flexDirection: "row",
        flexWrap: "wrap",
        gap: 10,
        marginTop: 2,
      }}
    >
      {items.map((item, idx) => {
        const toneColor =
          item.tone === "good"
            ? UI.good
            : item.tone === "bad"
            ? UI.bad
            : item.tone === "brand"
            ? UI.brand
            : UI.text;

        return (
          <View
            key={`${item.label}-${idx}`}
            style={{
              width: "47%",
              minWidth: 140,
              borderRadius: 16,
              borderWidth: 1,
              borderColor: "rgba(255,255,255,0.08)",
              backgroundColor: "rgba(255,255,255,0.03)",
              padding: 12,
            }}
          >
            <Text style={{ color: UI.mute, fontSize: 12 }}>{item.label}</Text>
            <Text
              style={{
                color: toneColor,
                fontWeight: "900",
                fontSize: 22,
                marginTop: 8,
              }}
            >
              {item.value}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

function StatRow({ label, value, sub, valueColor }) {
  return (
    <View
      style={{
        borderTopWidth: 1,
        borderTopColor: "rgba(255,255,255,0.08)",
        paddingTop: 10,
        marginTop: 10,
      }}
    >
      <View
        style={{
          flexDirection: "row",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <Text style={{ color: UI.text }}>{label}</Text>
        <Text style={{ color: valueColor || UI.text, fontWeight: "900" }}>{value}</Text>
      </View>
      {!!sub && <Text style={{ color: UI.mute, marginTop: 4 }}>{sub}</Text>}
    </View>
  );
}

function RowCard({ icon, title, subtitle, right = null }) {
  return (
    <View
      style={{
        marginTop: 10,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: "rgba(255,255,255,0.08)",
        backgroundColor: "rgba(255,255,255,0.03)",
        padding: 12,
        flexDirection: "row",
        alignItems: "center",
      }}
    >
      <View
        style={{
          width: 38,
          height: 38,
          borderRadius: 999,
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "rgba(255,255,255,0.05)",
          borderWidth: 1,
          borderColor: "rgba(255,255,255,0.08)",
        }}
      >
        <Ionicons name={icon} size={18} color={UI.dim} />
      </View>

      <View style={{ flex: 1, marginLeft: 12, paddingRight: 10 }}>
        <Text style={{ color: UI.text, fontWeight: "900" }}>{title}</Text>
        {!!subtitle && <Text style={{ color: UI.mute, marginTop: 3 }}>{subtitle}</Text>}
      </View>

      {right}
    </View>
  );
}

function Pill({ children, tone }) {
  const isBrand = tone === "brand";
  const isSuccess = tone === "success";

  return (
    <View
      style={{
        ...pillBase,
        borderColor: isBrand
          ? "rgba(255,176,32,0.65)"
          : isSuccess
          ? "rgba(41,211,122,0.65)"
          : UI.border,
        backgroundColor: isBrand
          ? "rgba(255,176,32,0.14)"
          : isSuccess
          ? "rgba(41,211,122,0.14)"
          : pillBase.backgroundColor,
      }}
    >
      <Text
        style={{
          color: isBrand ? UI.brand : isSuccess ? UI.good : UI.text,
          fontWeight: "900",
          fontSize: 12,
        }}
      >
        {children}
      </Text>
    </View>
  );
}

function FeaturePill({ text, tone }) {
  return <Pill tone={tone === "success" ? "success" : "brand"}>{text}</Pill>;
}
