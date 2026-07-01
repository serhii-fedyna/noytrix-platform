// app/(tabs)/trading.js
import React, { useMemo, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Modal,
  ActivityIndicator,

  TextInput,
  Linking,
  Platform,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import { useTranslation } from "react-i18next";

import { useAuthStore } from "../lib/store.auth";
import { showAppAlert } from "../lib/appAlert";

const SITE_URL = "https://noytrix.com";

const BG = {
  start: "#06080f",
  mid: "#0a1233",
  end: "#0b1c4f",
};

const T = {
  brand: "#ffb020",
  text: "#e9ecff",
  dim: "#A8B4CF",
  soft: "#C8D3F0",
  border: "rgba(255,255,255,0.11)",
  borderStrong: "rgba(255,176,32,0.35)",
  card: "rgba(255,255,255,0.055)",
  card2: "rgba(255,255,255,0.035)",
  dark: "#070b18",
  good: "#29d37a",
  bad: "#ff6b6b",
  blue: "#6ea8ff",
};



function LeadModal({ visible, onClose }) {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);

  const [name, setName] = useState(user?.name || user?.nick || "");
  const [email, setEmail] = useState(user?.email || "");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);

  const sendLead = async () => {
    try {
      setLoading(true);

      const res = await fetch("https://noytrix.com/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          email,
          note,
          product: "Noytrix Trading Center",
          source: "mobile_app_trading_page",
        }),
      });

      if (!res.ok) throw new Error("send_failed");

      showAppAlert(
        t("trading.lead.successTitle", "Request sent"),
        t("trading.lead.successText", "We will contact you with access and setup details.")
      );

      onClose();
    } catch {
      showAppAlert(
        t("trading.lead.errorTitle", "Error"),
        t("trading.lead.errorText", "Could not send request. Try again later.")
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal visible={visible} animationType="fade" transparent onRequestClose={onClose}>
      <View style={s.overlay}>
        <View style={s.leadCard}>
          <View style={s.modalTop}>
            <Text style={s.modalTitle}>{t("trading.lead.title", "Leave request")}</Text>

            <TouchableOpacity onPress={onClose} style={s.closeBtn}>
              <Ionicons name="close" size={20} color={T.text} />
            </TouchableOpacity>
          </View>

          <Text style={s.modalText}>
            {t(
              "trading.lead.text",
              "Leave your contact details. We will send activation, payment and desktop setup instructions."
            )}
          </Text>

          <TextInput
            value={name}
            onChangeText={setName}
            placeholder={t("trading.lead.name", "Name")}
            placeholderTextColor={T.dim}
            style={s.input}
          />

          <TextInput
            value={email}
            onChangeText={setEmail}
            placeholder={t("trading.lead.email", "Email / Telegram")}
            placeholderTextColor={T.dim}
            style={s.input}
            autoCapitalize="none"
          />

          <TextInput
            value={note}
            onChangeText={setNote}
            placeholder={t("trading.lead.note", "Message")}
            placeholderTextColor={T.dim}
            style={[s.input, { minHeight: 90, textAlignVertical: "top" }]}
            multiline
          />

          <TouchableOpacity
            onPress={sendLead}
            disabled={loading}
            style={[s.mainBtn, { marginTop: 14 }]}
            activeOpacity={0.9}
          >
            {loading ? (
              <ActivityIndicator color="#08101f" />
            ) : (
              <>
                <Ionicons name="send" size={18} color="#08101f" />
                <Text style={s.mainBtnText}>{t("trading.lead.send", "Send request")}</Text>
              </>
            )}
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

function Check({ text }) {
  return (
    <View style={s.checkRow}>
      <View style={s.checkIcon}>
        <Ionicons name="checkmark" size={14} color="#08101f" />
      </View>
      <Text style={s.checkText}>{text}</Text>
    </View>
  );
}

function FeatureCard({ icon, title, text }) {
  return (
    <View style={s.featureCard}>
      <View style={s.featureIcon}>{icon}</View>
      <Text style={s.featureTitle}>{title}</Text>
      <Text style={s.featureText}>{text}</Text>
    </View>
  );
}

function CompareRow({ left, right }) {
  return (
    <View style={s.compareRow}>
      <View style={s.compareSide}>
        <Ionicons name="close-circle" size={17} color={T.bad} />
        <Text style={s.compareBad}>{left}</Text>
      </View>

      <View style={s.compareSide}>
        <Ionicons name="checkmark-circle" size={17} color={T.brand} />
        <Text style={s.compareGood}>{right}</Text>
      </View>
    </View>
  );
}

function PriceMini({ title, price, text }) {
  return (
    <View style={s.priceMini}>
      <Text style={s.priceMiniTitle}>{title}</Text>
      <Text style={s.priceMiniPrice}>{price}</Text>
      <Text style={s.priceMiniText}>{text}</Text>
    </View>
  );
}

export default function TradingBot() {
  const { t } = useTranslation();

  const [showLead, setShowLead] = useState(false);

  const openSite = () => {
    Linking.openURL(SITE_URL).catch(() => {});
  };

  const coreFeatures = useMemo(
    () => [
      {
        icon: <Ionicons name="analytics-outline" size={22} color={T.brand} />,
        title: t("trading.cards.market.title", "Market intelligence"),
        text: t(
          "trading.cards.market.text",
          "Scans futures pairs, movement, volatility and trend context before showing trade logic."
        ),
      },
      {
        icon: <MaterialCommunityIcons name="target-variant" size={22} color={T.brand} />,
        title: t("trading.cards.entry.title", "Entry logic"),
        text: t(
          "trading.cards.entry.text",
          "Shows direction, entry zone, stop, targets and confidence instead of random signals."
        ),
      },
      {
        icon: <Ionicons name="shield-checkmark-outline" size={22} color={T.brand} />,
        title: t("trading.cards.risk.title", "Risk Engine"),
        text: t(
          "trading.cards.risk.text",
          "Built around capital protection: leverage, position size, daily loss and trade limits."
        ),
      },
      {
        icon: <Ionicons name="desktop-outline" size={22} color={T.brand} />,
        title: t("trading.cards.runtime.title", "Desktop control"),
        text: t(
          "trading.cards.runtime.text",
          "Start, pause, stop, restart and monitor the live bot runtime from one Windows interface."
        ),
      },
    ],
    [t]
  );

  return (
    <LinearGradient
      colors={[BG.start, BG.mid, BG.end]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={{ flex: 1 }}
    >
      <ScrollView contentContainerStyle={s.scroll}>
        <View style={s.hero}>
          <View style={s.logoRow}>
            <Text style={s.logo}>NOYTRIX</Text>
            <View style={s.statusPill}>
              <View style={s.liveDot} />
              <Text style={s.statusText}>{t("trading.status", "Windows system")}</Text>
            </View>
          </View>

          <Text style={s.title}>{t("trading.title", "Trading Center")}</Text>

          <Text style={s.subtitle}>
            {t(
              "trading.subtitle",
              "Professional desktop system for Binance Futures with market analysis, risk control and semi-auto execution."
            )}
          </Text>

          <View style={s.heroPanel}>
            <LinearGradient
              colors={["rgba(255,176,32,0.18)", "rgba(255,255,255,0.035)"]}
              style={s.heroGlow}
            >
              <View style={s.priceTop}>
                <View>
                  <Text style={s.accessLabel}>{t("trading.access.label", "Desktop access")}</Text>
                  <Text style={s.price}>{t("trading.access.price", "from $25")}</Text>
                </View>

                <View style={s.systemBadge}>
                  <Ionicons name="flash" size={16} color={T.brand} />
                  <Text style={s.systemBadgeText}>{t("trading.access.badge", "Desktop Plans")}</Text>
                </View>
              </View>

              <View style={s.tags}>
                <Text style={s.tag}>Risk Engine</Text>
                <Text style={s.tag}>Binance Futures</Text>
                <Text style={s.tag}>Semi-Auto</Text>
              </View>

              <Text style={s.heroNote}>
                {t(
                  "trading.hero.note",
                  "This is not a Telegram signal bot. It is a desktop trading control center where the operator stays in control."
                )}
              </Text>
            </LinearGradient>
          </View>
        </View>

        <View style={s.section}>
          <Text style={s.sectionTitle}>{t("trading.what.title", "What it does")}</Text>

          <View style={s.grid}>
            {coreFeatures.map((x, i) => (
              <FeatureCard key={i} icon={x.icon} title={x.title} text={x.text} />
            ))}
          </View>
        </View>

        <View style={s.premiumCard}>
          <Text style={s.sectionTitle}>{t("trading.diff.title", "Why itвЂ™s different")}</Text>

          <Text style={s.cardLead}>
            {t(
              "trading.diff.lead",
              "Most bots only send signals. Noytrix gives you a full control layer over trading decisions, risk and execution."
            )}
          </Text>

          <CompareRow
            left={t("trading.compare.1.left", "Signal spam")}
            right={t("trading.compare.1.right", "Full trading workflow")}
          />
          <CompareRow
            left={t("trading.compare.2.left", "No risk control")}
            right={t("trading.compare.2.right", "Daily loss and trade limits")}
          />
          <CompareRow
            left={t("trading.compare.3.left", "Blind entries")}
            right={t("trading.compare.3.right", "Entry / stop / target logic")}
          />
          <CompareRow
            left={t("trading.compare.4.left", "No runtime control")}
            right={t("trading.compare.4.right", "Start / pause / stop system")}
          />
        </View>

        <View style={s.premiumCard}>
          <Text style={s.sectionTitle}>{t("trading.system.title", "System includes")}</Text>

          <Check text={t("trading.system.1", "Binance API connection")} />
          <Check text={t("trading.system.2", "Real-time futures pair monitoring")} />
          <Check text={t("trading.system.3", "Long / Short signal logic")} />
          <Check text={t("trading.system.4", "Entry, stop and target planning")} />
          <Check text={t("trading.system.5", "Leverage and position control")} />
          <Check text={t("trading.system.6", "Daily loss limit and max trades per day")} />
          <Check text={t("trading.system.7", "Live runtime and bot status monitoring")} />
          <Check text={t("trading.system.8", "Manual + semi-auto execution workflow")} />
        </View>

        <View style={s.buyCard}>
          <View style={s.buyHeader}>
            <View style={{ flex: 1 }}>
              <Text style={s.buyKicker}>{t("trading.plans.kicker", "Desktop plans")}</Text>
              <Text style={s.buyTitle}>{t("trading.plans.title", "Choose access on the website")}</Text>
            </View>

            <View style={s.buyPricePill}>
              <Text style={s.buyPriceText}>{t("trading.plans.badge", "3 plans")}</Text>
            </View>
          </View>

          <Text style={s.buyText}>
            {t(
              "trading.plans.text",
              "To order and pay, go to the website and choose the plan that fits you: monthly, 6 months, or 1 year access."
            )}
          </Text>

          <View style={s.priceGrid}>
            <PriceMini
              title={t("trading.plans.month.title", "1 Month")}
              price={t("trading.plans.month.price", "$25")}
              text={t("trading.plans.month.text", "Fast start")}
            />
            <PriceMini
              title={t("trading.plans.six.title", "6 Months")}
              price={t("trading.plans.six.price", "$50")}
              text={t("trading.plans.six.text", "Best value")}
            />
            <PriceMini
              title={t("trading.plans.life.title", "1 Year")}
              price={t("trading.plans.life.price", "$200")}
              text={t("trading.plans.life.text", "Annual access")}
            />
          </View>

          <TouchableOpacity
            onPress={() => setShowLead(true)}
            style={s.secondaryBtn}
            activeOpacity={0.9}
          >
            <Ionicons name="mail-outline" size={19} color={T.text} />
            <Text style={s.secondaryBtnText}>{t("trading.request.button", "Leave request")}</Text>
          </TouchableOpacity>

          <TouchableOpacity onPress={openSite} style={s.mainBtn} activeOpacity={0.9}>
            <Ionicons name="open-outline" size={19} color="#08101f" />
            <Text style={s.mainBtnText}>
              {t("trading.site.button", "Go to website and choose plan")}
            </Text>
          </TouchableOpacity>
        </View>

        <View style={s.warningCard}>
          <Ionicons name="warning-outline" size={20} color={T.brand} />
          <Text style={s.warningText}>
            {t(
              "trading.warning",
              "Trading involves risk. The desktop program is designed for control and analysis, not guaranteed profit. Start with demo or small capital."
            )}
          </Text>
        </View>
      </ScrollView>

      <LeadModal visible={showLead} onClose={() => setShowLead(false)} />
    </LinearGradient>
  );
}

const s = StyleSheet.create({
  scroll: {
    padding: 18,
    paddingBottom: 42,
  },

  hero: {
    paddingTop: 24,
    marginBottom: 18,
  },

  logoRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 16,
  },

  logo: {
    color: T.brand,
    fontWeight: "900",
    letterSpacing: 3,
    fontSize: 15,
  },

  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    borderWidth: 1,
    borderColor: "rgba(41,211,122,0.28)",
    backgroundColor: "rgba(41,211,122,0.08)",
    paddingHorizontal: 11,
    paddingVertical: 7,
    borderRadius: 999,
  },

  liveDot: {
    width: 7,
    height: 7,
    borderRadius: 999,
    backgroundColor: T.good,
  },

  statusText: {
    color: T.soft,
    fontWeight: "800",
    fontSize: 12,
  },

  title: {
    color: T.text,
    fontWeight: "900",
    fontSize: 42,
    lineHeight: 46,
    letterSpacing: -1.3,
  },

  subtitle: {
    color: T.dim,
    fontSize: 16,
    lineHeight: 23,
    fontWeight: "650",
    marginTop: 12,
  },

  heroPanel: {
    marginTop: 18,
    borderRadius: 28,
    borderWidth: 1,
    borderColor: T.borderStrong,
    overflow: "hidden",
    backgroundColor: "rgba(255,255,255,0.04)",
  },

  heroGlow: {
    padding: 18,
  },

  priceTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
  },

  accessLabel: {
    color: T.dim,
    fontSize: 13,
    fontWeight: "800",
    marginBottom: 2,
  },

  price: {
    color: T.text,
    fontWeight: "900",
    fontSize: 38,
    letterSpacing: -1,
  },

  systemBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderRadius: 999,
    paddingHorizontal: 11,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: "rgba(255,176,32,0.36)",
    backgroundColor: "rgba(255,176,32,0.10)",
  },

  systemBadgeText: {
    color: T.text,
    fontWeight: "900",
    fontSize: 12,
  },

  tags: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 16,
  },

  tag: {
    color: T.text,
    fontWeight: "850",
    fontSize: 12,
    borderWidth: 1,
    borderColor: T.border,
    backgroundColor: "rgba(255,255,255,0.055)",
    paddingHorizontal: 11,
    paddingVertical: 7,
    borderRadius: 999,
  },

  heroNote: {
    color: T.soft,
    fontSize: 14,
    lineHeight: 21,
    marginTop: 16,
    fontWeight: "650",
  },

  section: {
    marginBottom: 14,
  },

  sectionTitle: {
    color: T.text,
    fontSize: 21,
    fontWeight: "900",
    marginBottom: 14,
    letterSpacing: -0.3,
  },

  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },

  featureCard: {
    width: "48.5%",
    minHeight: 166,
    borderWidth: 1,
    borderColor: T.border,
    backgroundColor: T.card,
    borderRadius: 24,
    padding: 14,
  },

  featureIcon: {
    width: 42,
    height: 42,
    borderRadius: 15,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(255,176,32,0.28)",
    backgroundColor: "rgba(255,176,32,0.10)",
    marginBottom: 12,
  },

  featureTitle: {
    color: T.text,
    fontSize: 15,
    fontWeight: "900",
    marginBottom: 7,
  },

  featureText: {
    color: T.dim,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: "650",
  },

  premiumCard: {
    borderWidth: 1,
    borderColor: T.border,
    backgroundColor: T.card,
    borderRadius: 28,
    padding: 17,
    marginBottom: 14,
  },

  cardLead: {
    color: T.dim,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: "650",
    marginBottom: 14,
  },

  compareRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 10,
  },

  compareSide: {
    flex: 1,
    borderWidth: 1,
    borderColor: T.border,
    backgroundColor: T.card2,
    borderRadius: 17,
    padding: 11,
    minHeight: 70,
  },

  compareBad: {
    color: T.dim,
    marginTop: 7,
    fontWeight: "800",
    lineHeight: 18,
  },

  compareGood: {
    color: T.text,
    marginTop: 7,
    fontWeight: "900",
    lineHeight: 18,
  },

  checkRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 11,
    marginBottom: 11,
  },

  checkIcon: {
    width: 22,
    height: 22,
    borderRadius: 999,
    backgroundColor: T.brand,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 1,
  },

  checkText: {
    flex: 1,
    color: T.text,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: "800",
  },

  buyCard: {
    borderWidth: 1,
    borderColor: T.borderStrong,
    backgroundColor: "rgba(255,176,32,0.075)",
    borderRadius: 30,
    padding: 18,
    marginBottom: 14,
  },

  buyHeader: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
  },

  buyKicker: {
    color: T.brand,
    fontSize: 12,
    fontWeight: "900",
    letterSpacing: 1.6,
    textTransform: "uppercase",
    marginBottom: 5,
  },

  buyTitle: {
    color: T.text,
    fontSize: 22,
    fontWeight: "900",
    letterSpacing: -0.4,
  },

  buyPricePill: {
    borderRadius: 18,
    backgroundColor: T.brand,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },

  buyPriceText: {
    color: "#08101f",
    fontSize: 14,
    fontWeight: "900",
  },

  buyText: {
    color: T.soft,
    fontSize: 14,
    lineHeight: 21,
    fontWeight: "650",
    marginTop: 12,
    marginBottom: 14,
  },

  priceGrid: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 4,
  },

  priceMini: {
    flex: 1,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
    backgroundColor: "rgba(255,255,255,0.045)",
    borderRadius: 18,
    padding: 11,
  },

  priceMiniTitle: {
    color: T.dim,
    fontSize: 11,
    fontWeight: "900",
    marginBottom: 5,
  },

  priceMiniPrice: {
    color: T.text,
    fontSize: 20,
    fontWeight: "900",
    marginBottom: 4,
  },

  priceMiniText: {
    color: T.soft,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: "700",
  },

  mainBtn: {
    minHeight: 58,
    borderRadius: 20,
    backgroundColor: T.brand,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 9,
    marginTop: 10,
  },

  mainBtnText: {
    color: "#08101f",
    fontWeight: "900",
    fontSize: 16,
  },

  secondaryBtn: {
    minHeight: 56,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: T.border,
    backgroundColor: "rgba(255,255,255,0.045)",
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 9,
    marginTop: 10,
  },

  secondaryBtnText: {
    color: T.text,
    fontWeight: "900",
    fontSize: 16,
  },

  warningCard: {
    borderWidth: 1,
    borderColor: "rgba(255,176,32,0.22)",
    backgroundColor: "rgba(255,176,32,0.07)",
    borderRadius: 22,
    padding: 14,
    flexDirection: "row",
    gap: 10,
    alignItems: "flex-start",
  },

  warningText: {
    color: T.soft,
    flex: 1,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: "650",
  },

  overlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.76)",
    alignItems: "center",
    justifyContent: "center",
    padding: 16,
  },

  leadCard: {
    width: "100%",
    maxWidth: 520,
    borderRadius: 28,
    borderWidth: 1,
    borderColor: T.border,
    backgroundColor: "rgba(8,14,36,0.98)",
    padding: 18,
  },

  modalTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
  },

  modalTitle: {
    color: T.brand,
    fontSize: 22,
    fontWeight: "900",
    textAlign: "center",
  },

  closeBtn: {
    position: "absolute",
    right: 0,
    top: -8,
    width: 42,
    height: 42,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: T.border,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255,255,255,0.04)",
  },

  modalText: {
    color: T.dim,
    fontSize: 14,
    lineHeight: 21,
    textAlign: "center",
    marginTop: 12,
    marginBottom: 8,
    fontWeight: "650",
  },

  input: {
    borderWidth: 1,
    borderColor: T.border,
    borderRadius: 15,
    paddingHorizontal: 13,
    paddingVertical: Platform.OS === "ios" ? 13 : 11,
    color: T.text,
    backgroundColor: "rgba(255,255,255,0.04)",
    marginTop: 10,
    fontWeight: "700",
  },
});
