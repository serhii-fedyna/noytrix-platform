import React, { useEffect, useState, useCallback } from "react";
import {
  Alert,
  LayoutAnimation,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  UIManager,
  View,
  SafeAreaView,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { BlurView } from "expo-blur";
import {
  iapInit,
  loadIap,
  buyProMonthly,
  buyPro6month,
  buyProYearly,
  restorePurchases,
  checkEntitlements,
  getRevenueCatAppUserId,
} from "../lib/iap";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useTranslation } from "react-i18next";
import { logEvent } from "../lib/analytics";

const GRAD = { bgStart: "#06080f", bgMid: "#0a1233", bgEnd: "#0b1c4f" };
const C = {
  text: "#FFFFFF",
  sub: "#A8B4CF",
  accent: "#FFA500",
  red: "#FF6565",
  green: "#4CD964",
  cardBorder: "rgba(255,255,255,0.10)",
  cardGlow: "rgba(255,255,255,0.06)",
  soft: "#C9D4E5",
  dim: "#8D9DB5",
  black: "#1B2333",
  blue: "#9DB5FF",
};

const BACKEND = "https://api.noytrixapp.com";

function showAppAlert(title, message) {
  Alert.alert(String(title || ""), String(message || ""));
}

if (Platform.OS === "android" && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

const plans = [
  { id: "m", title: "Month", save: "" },
  { id: "h", title: "6 months", save: "Save 20%" },
  { id: "l", title: "1 year", save: "Annual protection" },
];

const usd = (n) => `$${Number(n).toFixed(2)}`;
const LOCAL_PRICES = { m: 9.99, h: 49.99, l: 199.99 };

async function getOrCreateInstallUserId() {
  return getRevenueCatAppUserId();
}

async function syncLocalProFlags(ent) {
  try {
    const hasPro = !!(ent?.proMonthly || ent?.pro6m || ent?.proYearly);
    if (hasPro) {
      await AsyncStorage.setItem("isPro", "true");
      await AsyncStorage.setItem("noytrix.isPro", "true");
      await AsyncStorage.setItem("pro", "true");
      await AsyncStorage.setItem("proActive", "true");
      await AsyncStorage.setItem("subscription.pro", "true");
      await AsyncStorage.setItem("noytrix_pro_flag", "1");
      await AsyncStorage.setItem("entitlement.pro", "active");
      await AsyncStorage.setItem("entitlement.id", "pro");
      await AsyncStorage.setItem("entitlementId", "pro");
    } else {
      const serverOrManualPro =
        (await AsyncStorage.getItem("noytrix_pro_flag")) === "1" ||
        (await AsyncStorage.getItem("pro.active")) === "true" ||
        (await AsyncStorage.getItem("pro.isPro")) === "true";

      if (!serverOrManualPro) {
        await AsyncStorage.setItem("isPro", "false");
        await AsyncStorage.setItem("noytrix.isPro", "false");
        await AsyncStorage.setItem("pro", "false");
        await AsyncStorage.setItem("proActive", "false");
        await AsyncStorage.setItem("subscription.pro", "false");
        await AsyncStorage.setItem("entitlement.pro", "inactive");
        await AsyncStorage.setItem("entitlement.id", "");
        await AsyncStorage.setItem("entitlementId", "");
      }
    }
  } catch {}
}

async function syncGuestProOnServer(ent) {
  try {
    const hasPro = !!(ent?.proMonthly || ent?.pro6m || ent?.proYearly);
    const userId = await getOrCreateInstallUserId();

    const response = await fetch(`${BACKEND}/iap/guest/activate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": userId,
      },
      body: JSON.stringify({
        userId,
        hasPro,
        source: "google_play_guest",
      }),
    });
    const server = await response.json().catch(() => null);
    if (server?.active) {
      await AsyncStorage.setItem("isPro", "true");
      await AsyncStorage.setItem("noytrix.isPro", "true");
      await AsyncStorage.setItem("pro", "true");
      await AsyncStorage.setItem("proActive", "true");
      await AsyncStorage.setItem("subscription.pro", "true");
      await AsyncStorage.setItem("iap.isPro", "true");
      await AsyncStorage.setItem("entitlement.pro", "active");
      await AsyncStorage.setItem("entitlement.id", "pro");
      await AsyncStorage.setItem("entitlementId", "pro");
      await AsyncStorage.setItem("noytrix_pro_flag", "1");
    }
  } catch (e) {
    console.log("[PRO] syncGuestProOnServer error:", e);
  }
}

export default function ProScreen() {
  const [openFaq, setOpenFaq] = useState(-1);
  const [loading, setLoading] = useState(true);
  const [ent, setEnt] = useState({
    proMonthly: false,
    pro6m: false,
    proYearly: false,
  });
  const [subs, setSubs] = useState([]);

  const { t } = useTranslation();

  const purchased = ent.proMonthly || ent.pro6m || ent.proYearly;

  useEffect(() => {
    logEvent("pro_screen_open", { screen: "pro" });
  }, []);

  const toggleFaq = (i) => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setOpenFaq((prev) => (prev === i ? -1 : i));
  };

  const priceFor = useCallback((planId) => {
    const base = LOCAL_PRICES[planId];
    if (!base) return "";
    return usd(base);
  }, []);

  const cardChrome = useCallback(
    () => ({
      borderRadius: 18,
      borderWidth: 1,
      borderColor: C.cardBorder,
      overflow: "hidden",
      shadowColor: C.cardGlow,
      shadowOpacity: 1,
      shadowRadius: 14,
      shadowOffset: { width: 0, height: 6 },
      elevation: 3,
    }),
    []
  );

  useEffect(() => {
    (async () => {
      try {
        await iapInit();
        const { subs: subsList } = await loadIap();
        setSubs(subsList || []);

        const e = await checkEntitlements();
        setEnt(e);
        await syncLocalProFlags(e);
        await syncGuestProOnServer(e);
      } catch (err) {
        console.log("ProScreen init error", err);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleBuy = async (planId) => {
    try {
      logEvent("purchase_start", { screen: "pro", plan: planId, price_usd: LOCAL_PRICES[planId] || 0, currency: "USD" });
      setLoading(true);

      if (planId === "m") {
        await buyProMonthly();
      } else if (planId === "h") {
        await buyPro6month();
      } else if (planId === "l") {
        await buyProYearly();
      }

      const e = await checkEntitlements();
      setEnt(e);
      await syncLocalProFlags(e);
      await syncGuestProOnServer(e);
      logEvent("purchase_success", { screen: "pro", plan: planId, price_usd: LOCAL_PRICES[planId] || 0, currency: "USD", pro_monthly: !!e?.proMonthly, pro_6m: !!e?.pro6m, pro_yearly: !!e?.proYearly });

      showAppAlert(t("pro.alerts.purchaseTitle"), t("pro.alerts.purchaseBody"));
    } catch (err) {
      console.log("handleBuy error", err);
      logEvent("purchase_error", { screen: "pro", plan: planId, price_usd: LOCAL_PRICES[planId] || 0, currency: "USD", err: String(err?.message || err || "error") });
      showAppAlert(t("pro.alerts.errorTitle"), err?.message || t("pro.alerts.errorFallback"));
    } finally {
      setLoading(false);
    }
  };

  const handleRestore = async () => {
    try {
      logEvent("restore_click", { screen: "pro" });
      setLoading(true);
      const e = await restorePurchases();
      setEnt(e);
      await syncLocalProFlags(e);
      await syncGuestProOnServer(e);
      logEvent("restore_success", { screen: "pro", pro_monthly: !!e?.proMonthly, pro_6m: !!e?.pro6m, pro_yearly: !!e?.proYearly });

      showAppAlert(t("pro.restoreTitle", "Restore"), t("pro.restoreSuccess", "Purchases restored."));
    } catch (err) {
      console.log("handleRestore error", err);
      logEvent("restore_error", { screen: "pro", err: String(err?.message || err || "error") });
      showAppAlert(t("pro.alerts.errorTitle"), err?.message || t("pro.alerts.errorFallback"));
    } finally {
      setLoading(false);
    }
  };

  const labelForPlan = (planId) => {
    if (!purchased) return t("pro.planActions.unlock", "Unlock PRO");
    if (planId === "l" && ent.proYearly) return t("pro.planActions.active", "Active");
    if (planId === "h" && ent.pro6m) return t("pro.planActions.active", "Active");
    if (planId === "m" && ent.proMonthly) return t("pro.planActions.active", "Active");
    if (ent.proYearly) return t("pro.planActions.includedYearly", "Included");
    return t("pro.planActions.available", "Available");
  };

  return (
    <LinearGradient
      colors={[GRAD.bgStart, GRAD.bgMid, GRAD.bgEnd]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={{ flex: 1 }}
    >
      <SafeAreaView style={{ flex: 1 }}>
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={{ padding: 16, paddingBottom: 28 }}
          showsVerticalScrollIndicator={false}
        >
          <View style={{ marginTop: 8, marginBottom: 12 }}>
            <Text style={s.pageTitle}>Noytrix PRO</Text>
            <Text style={s.heroTitle}>
              {t("pro.heroTitle", "DonвЂ™t get rekt. Check before you trust.")}
            </Text>
            <Text style={s.pageSub}>
              {t(
                "pro.heroSubtitle",
                "Avoid losing money in crypto. Noytrix PRO shows risk, detects scams and gives clear actions before you lose funds."
              )}
            </Text>
          </View>

          <View style={[cardChrome(), { marginBottom: 14 }]}>
            <BlurView intensity={30} tint="dark" style={{ borderRadius: 18, padding: 14 }}>
              <View style={s.alertHeader}>
                <Ionicons name="shield-checkmark-outline" size={22} color={C.accent} />
                <Text style={s.title}>
                  {t("pro.moneyTitle", "Protect your money + trade smarter")}
                </Text>
              </View>

              <Text style={s.textStrong}>
                {t(
                  "pro.moneyText",
                  "Scam protection and trading decisions in one app вЂ” before you connect, buy, send or enter a trade."
                )}
              </Text>

              <View style={{ marginTop: 12 }}>
                <Bullet
                  icon="warning-outline"
                  text={t("pro.benefits.tradeRisk", "See if a trade is too risky BEFORE you enter")}
                />
                <Bullet
                  icon="shield-outline"
                  text={t("pro.benefits.scamDetect", "Detect scam links, wallets and suspicious crypto traps")}
                />
                <Bullet
                  icon="analytics-outline"
                  text={t("pro.benefits.mistakes", "Track mistakes and stop losing money on bad decisions")}
                />
              </View>
            </BlurView>
          </View>

          <View style={[cardChrome(), { marginBottom: 14 }]}>
            <BlurView intensity={26} tint="dark" style={{ borderRadius: 18, padding: 14 }}>
              <View style={s.caseBox}>
                <View style={s.caseIcon}>
                  <Ionicons name="alert-circle" size={20} color={C.red} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.caseTitle}>
                    {t("pro.caseTitle", "User almost lost $500 on a scam")}
                  </Text>
                  <Text style={s.caseText}>
                    {t(
                      "pro.caseText",
                      "Noytrix detected suspicious signals before the user trusted the link."
                    )}
                  </Text>
                </View>
              </View>

              <View style={s.fomoRow}>
                <MiniStat
                  icon="flash-outline"
                  text={t("pro.fomo.one", "Most users upgrade after first check")}
                />
                <MiniStat
                  icon="lock-open-outline"
                  text={t("pro.fomo.two", "PRO unlocks full protection")}
                />
              </View>
            </BlurView>
          </View>

          <View style={[cardChrome(), { marginBottom: 14 }]}>
            <BlurView intensity={26} tint="dark" style={{ borderRadius: 18, padding: 14 }}>
              <Text style={s.h2}>{t("pro.tariffsTitle", "Choose your protection")}</Text>

              {plans.map((p, i) => {
                const isActive =
                  (p.id === "l" && ent.proYearly) ||
                  (p.id === "h" && ent.pro6m) ||
                  (p.id === "m" && ent.proMonthly);

                const saveText = t(`pro.plans.${p.id}.save`, p.save);

                return (
                  <View
                    key={p.id}
                    style={[
                      s.planItem,
                      i === plans.length - 1 && { marginBottom: 0 },
                      isActive && { borderColor: "rgba(255,165,0,0.35)" },
                    ]}
                  >
                    <View style={{ flex: 1, paddingRight: 10 }}>
                      <View style={{ flexDirection: "row", alignItems: "center", flexWrap: "wrap" }}>
                        <Text style={s.planTitle}>{t(`pro.plans.${p.id}.title`, p.title)}</Text>

                        {isActive ? (
                          <View style={s.badgeActive}>
                            <Ionicons
                              name="checkmark-circle"
                              size={14}
                              color={C.green}
                              style={{ marginRight: 6 }}
                            />
                            <Text style={s.badgeText}>{t("pro.badges.active", "Active")}</Text>
                          </View>
                        ) : null}
                      </View>

                      <Text style={s.planPrice}>{priceFor(p.id)}</Text>

                      {!!saveText && saveText !== `pro.plans.${p.id}.save` ? (
                        <Text style={s.planSave}>{saveText}</Text>
                      ) : null}

                      <Text style={s.planAnchor}>
                        {t(
                          "pro.priceAnchor",
                          "One bad trade can cost $100+. PRO costs less than your mistake."
                        )}
                      </Text>
                    </View>

                    <TouchableOpacity
                      style={[
                        s.buyBtn,
                        isActive && { backgroundColor: "rgba(255,255,255,0.10)" },
                        loading && { opacity: 0.6 },
                      ]}
                      onPress={() => !loading && handleBuy(p.id)}
                      activeOpacity={0.9}
                      disabled={loading}
                    >
                      <Text style={[s.buyText, isActive ? { color: C.text } : { color: C.black }]}>
                        {labelForPlan(p.id)}
                      </Text>
                    </TouchableOpacity>
                  </View>
                );
              })}

              {!purchased ? (
                <Text style={s.limitText}>
                  {t(
                    "pro.tariffsNote",
                    "Limited free scans per day. Upgrade to unlock full crypto protection."
                  )}
                </Text>
              ) : (
                <Text style={s.limitText}>{t("pro.restoreHint", "Your PRO access is active.")}</Text>
              )}

              <TouchableOpacity
                style={s.restoreBtn}
                onPress={handleRestore}
                activeOpacity={0.85}
                disabled={loading}
              >
                <Ionicons name="refresh-outline" size={15} color={C.sub} style={{ marginRight: 6 }} />
                <Text style={s.restoreText}>{t("pro.restoreButton", "Restore purchase")}</Text>
              </TouchableOpacity>
            </BlurView>
          </View>

          <Text style={s.sectionTitle}>{t("pro.includesSection", "What PRO helps you do")}</Text>

          <View style={[cardChrome(), { marginBottom: 14 }]}>
            <BlurView intensity={24} tint="dark" style={{ borderRadius: 18, padding: 14 }}>
              <Check text={t("pro.includes.protectTitle", "Check before you trust")} />
              <Para>
                {t(
                  "pro.includes.protectDesc",
                  "Scan links, domains, wallets and crypto objects before you send funds or connect."
                )}
              </Para>

              <Spacer />

              <Check text={t("pro.includes.tradeTitle", "Enter trades with more control")} />
              <Para>
                {t(
                  "pro.includes.tradeDesc",
                  "Understand risk, volatility and possible danger before opening a position."
                )}
              </Para>

              <Spacer />

              <Check text={t("pro.includes.actionTitle", "Get clear actions")} />
              <Para>
                {t(
                  "pro.includes.actionDesc",
                  "Not just numbers вЂ” Noytrix explains what to avoid, what to check and what to do next."
                )}
              </Para>

              <Spacer />

              <Check text={t("pro.includes.historyTitle", "Stop repeating bad decisions")} />
              <Para>
                {t(
                  "pro.includes.historyDesc",
                  "Track checks, mistakes and decisions so you can improve instead of losing blindly."
                )}
              </Para>
            </BlurView>
          </View>

          <Text style={s.sectionTitle}>{t("pro.whySection", "Why it is worth it")}</Text>

          <View style={[cardChrome(), { marginBottom: 14 }]}>
            <BlurView intensity={24} tint="dark" style={{ borderRadius: 18, padding: 14 }}>
              <Why icon="cash-outline" title={t("pro.why.money.title", "One mistake can cost more than PRO")}>
                {t(
                  "pro.why.money.text",
                  "A fake link, bad trade or suspicious token can cost much more than a subscription."
                )}
              </Why>

              <Why icon="shield-checkmark-outline" title={t("pro.why.protection.title", "Full protection, not random guessing")}>
                {t(
                  "pro.why.protection.text",
                  "PRO gives deeper checks, stronger signals and clearer risk before you act."
                )}
              </Why>

              <Why icon="trending-up-outline" title={t("pro.why.smarter.title", "Trade smarter, not emotionally")}>
                {t(
                  "pro.why.smarter.text",
                  "Use risk signals and decision history to avoid emotional entries and weak setups."
                )}
              </Why>
            </BlurView>
          </View>

          <Text style={s.sectionTitle}>{t("pro.joinSection", "Unlock full access")}</Text>

          <View style={[cardChrome(), { marginBottom: 8 }]}>
            <BlurView intensity={24} tint="dark" style={{ borderRadius: 18, padding: 14 }}>
              <Text style={s.text}>
                {t(
                  "pro.join.accessText",
                  "Get full ScamShield protection, trading risk tools and decision history in one PRO plan."
                )}
              </Text>

              <View style={s.joinCard}>
                <View style={s.joinHeader}>
                  <Text style={s.joinTitle}>{t("pro.join.proLabel", "Noytrix PRO")}</Text>

                  <View style={s.proPill}>
                    <Text style={s.proPillText}>{t("pro.join.fullAccess", "Full access")}</Text>
                  </View>
                </View>

                <View style={s.joinRow}>
                  <Text style={s.dim}>{t("pro.join.startPriceLabel", "Starts from")}</Text>
                  <Text style={s.priceBold}>
                    {t("pro.join.startPriceValue", { price: priceFor("m") })}
                  </Text>
                </View>

                <View style={s.joinRow}>
                  <Text style={s.dim}>{t("pro.join.valueLabel", "Value")}</Text>
                  <Text style={[s.text, { color: C.green, flex: 1, textAlign: "right" }]}>
                    {t("pro.join.valueText", "Less than one bad crypto mistake")}
                  </Text>
                </View>

                {purchased ? (
                  <View style={[s.ctaBtn, { backgroundColor: "rgba(255,255,255,0.12)" }]}>
                    <Ionicons name="checkmark-done" size={16} color={C.text} style={{ marginRight: 8 }} />
                    <Text style={[s.ctaText, { color: C.text }]}>{t("pro.join.ctaActive", "PRO active")}</Text>
                  </View>
                ) : (
                  <TouchableOpacity
                    style={s.ctaBtn}
                    onPress={() => handleBuy("m")}
                    activeOpacity={0.9}
                    disabled={loading}
                  >
                    <Text style={s.ctaText}>{t("pro.join.ctaBuy", "Get full protection")}</Text>
                  </TouchableOpacity>
                )}

                <Text style={s.disclaimer}>
                  {t(
                    "pro.disclaimer",
                    "PRO does not guarantee profit and does not replace your own decision. It helps you check risk before you act."
                  )}
                </Text>
              </View>
            </BlurView>
          </View>

          <View style={{ height: 10 }} />
        </ScrollView>
      </SafeAreaView>
    </LinearGradient>
  );
}

function RowTitle({ icon, text }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center" }}>
      <Ionicons name={icon} size={20} color={C.accent} style={{ marginRight: 8 }} />
      <Text style={s.title}>{text}</Text>
    </View>
  );
}

function Bullet({ icon, text }) {
  return (
    <View style={s.bulletRow}>
      <Ionicons name={icon} size={18} color={C.accent} style={{ marginTop: 2 }} />
      <Text style={s.text}>{text}</Text>
    </View>
  );
}

function Check({ text }) {
  return (
    <View style={s.bulletRow}>
      <Ionicons name="checkmark-circle" size={18} color={C.green} style={{ marginTop: 2 }} />
      <Text style={s.bold}>{text}</Text>
    </View>
  );
}

function MiniStat({ icon, text }) {
  return (
    <View style={s.miniStat}>
      <Ionicons name={icon} size={15} color={C.accent} style={{ marginRight: 6 }} />
      <Text style={s.miniStatText}>{text}</Text>
    </View>
  );
}

function Para({ children }) {
  return <Text style={s.text}>{children}</Text>;
}

function Why({ icon, title, children }) {
  return (
    <View style={{ marginBottom: 12 }}>
      <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 6 }}>
        <Ionicons name={icon} size={18} color={C.accent} style={{ marginRight: 8 }} />
        <Text style={s.bold}>{title}</Text>
      </View>
      <Text style={s.text}>{children}</Text>
    </View>
  );
}

function Spacer() {
  return <View style={{ height: 10 }} />;
}

const s = StyleSheet.create({
  pageTitle: {
    color: C.accent,
    fontSize: 28,
    fontWeight: "900",
    letterSpacing: 0.2,
  },
  heroTitle: {
    color: C.text,
    fontSize: 30,
    fontWeight: "900",
    lineHeight: 36,
    marginTop: 8,
    letterSpacing: -0.4,
  },
  pageSub: {
    color: C.sub,
    fontSize: 15,
    fontWeight: "700",
    marginTop: 8,
    lineHeight: 21,
  },
  title: { color: C.text, fontSize: 18, fontWeight: "900", flex: 1 },
  h2: { color: C.text, fontSize: 18, fontWeight: "900", marginBottom: 12 },
  sectionTitle: { color: C.text, fontSize: 18, fontWeight: "900", marginBottom: 10 },
  text: { color: C.sub, fontSize: 14, lineHeight: 20 },
  textStrong: { color: C.soft, fontSize: 14, lineHeight: 20, marginTop: 8, fontWeight: "700" },
  bold: { color: C.text, fontSize: 14, fontWeight: "900", marginBottom: 2, flex: 1 },
  dim: { color: C.sub, opacity: 0.8, fontSize: 13 },
  alertHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  bulletRow: { flexDirection: "row", alignItems: "flex-start", gap: 10, marginBottom: 8 },
  caseBox: {
    flexDirection: "row",
    alignItems: "flex-start",
    backgroundColor: "rgba(255,101,101,0.08)",
    borderWidth: 1,
    borderColor: "rgba(255,101,101,0.20)",
    borderRadius: 16,
    padding: 12,
  },
  caseIcon: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255,101,101,0.10)",
    marginRight: 10,
  },
  caseTitle: { color: C.text, fontSize: 15, fontWeight: "900" },
  caseText: { color: C.sub, fontSize: 13, lineHeight: 18, marginTop: 3 },
  fomoRow: {
    marginTop: 10,
    gap: 8,
  },
  miniStat: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "rgba(255,165,0,0.08)",
    borderWidth: 1,
    borderColor: "rgba(255,165,0,0.18)",
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  miniStatText: { color: C.text, fontSize: 12, fontWeight: "800", flex: 1 },
  planItem: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.03)",
    borderWidth: 1,
    borderColor: C.cardBorder,
    borderRadius: 16,
    padding: 12,
    marginBottom: 10,
  },
  planTitle: { color: C.text, fontSize: 15, fontWeight: "900" },
  planPrice: { color: C.green, fontSize: 16, marginTop: 5, fontWeight: "900" },
  planSave: { color: C.accent, fontSize: 12, marginTop: 4, fontWeight: "800" },
  planAnchor: {
    color: C.sub,
    fontSize: 12,
    lineHeight: 16,
    marginTop: 6,
    opacity: 0.95,
  },
  limitText: { color: C.sub, marginTop: 10, fontSize: 13, lineHeight: 18 },
  badgeActive: {
    marginLeft: 10,
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "rgba(76,217,100,0.35)",
    backgroundColor: "rgba(76,217,100,0.08)",
  },
  badgeText: { color: C.text, fontSize: 12, fontWeight: "900" },
  buyBtn: {
    backgroundColor: C.accent,
    borderRadius: 14,
    paddingVertical: 10,
    paddingHorizontal: 14,
    minWidth: 112,
    alignItems: "center",
    justifyContent: "center",
  },
  buyText: { fontWeight: "900", fontSize: 13 },
  restoreBtn: {
    marginTop: 12,
    alignSelf: "center",
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  restoreText: {
    color: C.sub,
    fontSize: 13,
    fontWeight: "800",
  },
  joinCard: {
    marginTop: 12,
    backgroundColor: "rgba(255,255,255,0.03)",
    borderWidth: 1,
    borderColor: C.cardBorder,
    borderRadius: 16,
    padding: 12,
  },
  joinHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 10,
  },
  joinTitle: { color: C.text, fontSize: 16, fontWeight: "900" },
  proPill: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "rgba(255,165,0,0.35)",
    backgroundColor: "rgba(255,165,0,0.08)",
  },
  proPillText: { color: C.text, fontSize: 12, fontWeight: "800", opacity: 0.95 },
  joinRow: { flexDirection: "row", justifyContent: "space-between", marginTop: 8, gap: 10 },
  priceBold: { color: C.text, fontWeight: "900" },
  ctaBtn: {
    marginTop: 14,
    paddingVertical: 12,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    backgroundColor: C.accent,
  },
  ctaText: { color: C.black, fontWeight: "900" },
  disclaimer: {
    marginTop: 10,
    color: C.sub,
    opacity: 0.75,
    fontSize: 12,
    lineHeight: 16,
  },
});


