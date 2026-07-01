// app/auth/signup.js
import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
} from "react-native";
import { useRouter } from "expo-router";
import { useAuthStore } from "../../stores/auth/useAuthStore";
import Constants from "expo-constants";
import { useTranslation } from "react-i18next";

const T = {
  bg: "#0a1322",
  card: "rgba(17,29,49,0.9)",
  border: "#1a2a45",
  text: "#e9f0ff",
  soft: "#bcd2ff",
  accent: "#FFA500",
};

const EXTRA = Constants?.expoConfig?.extra ?? {};
const BACKEND = EXTRA?.EXPO_PUBLIC_API || "https://noytrix.com";

export default function SignUp() {
  const { t } = useTranslation();
  const router = useRouter();

  const registerStart =
    useAuthStore.getState?.()?.registerStart ||
    useAuthStore((s) => s.registerStart);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [nick, setNick] = useState("");
  const [loading, setLoading] = useState(false);

  const validate = () => {
    const em = email.trim().toLowerCase();
    const pw = password.trim();
    const n = nick.trim();

    if (!n || n.length < 3)
      throw new Error(t("auth.signup.errors.nickShort"));

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em))
      throw new Error(t("auth.signup.errors.invalidEmail"));

    if (pw.length < 6)
      throw new Error(t("auth.signup.errors.passwordShort"));

    return { em, pw, n };
  };

  const onStart = async () => {
    if (loading) return;

    try {
      const { em, pw, n } = validate();
      setLoading(true);

      if (typeof registerStart === "function") {
        await registerStart({ email: em, password: pw, nick: n });
      } else {
        const r = await fetch(`${BACKEND}/auth/email/signup`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: em,
            password: pw,
            login: n,
            nick: n,
          }),
        });
        if (!r.ok) throw new Error(await r.text());
      }

      showAppAlert(t("auth.signup.alertCodeSentTitle"),t("auth.signup.alertCodeSentText")
      );

      router.push({
        pathname: "/auth/verify",
        params: { email: em, nick: n, password: pw },
      });
    } catch (e) {
      const msg = String(e?.message || e);

      if (msg.toLowerCase().includes("registered")) {
        showAppAlert(t("auth.signup.alertEmailTakenTitle"),t("auth.signup.alertEmailTakenText")
        );
      } else {
        showAppAlert(t("auth.signup.alertErrorTitle"),msg || t("auth.signup.alertErrorText")
        );
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: T.bg, padding: 16 }}>
      <View style={s.card}>
        <Text style={s.title}>{t("auth.signup.title")}</Text>

        <Text style={s.label}>{t("auth.signup.nicknameLabel")}</Text>
        <TextInput
          style={s.input}
          value={nick}
          onChangeText={setNick}
          placeholder={t("auth.signup.nicknamePlaceholder")}
          placeholderTextColor={T.soft}
          autoCapitalize="none"
        />

        <Text style={s.label}>{t("auth.signup.emailLabel")}</Text>
        <TextInput
          style={s.input}
          value={email}
          onChangeText={setEmail}
          placeholder={t("auth.signup.emailPlaceholder")}
          placeholderTextColor={T.soft}
          autoCapitalize="none"
          keyboardType="email-address"
        />

        <Text style={s.label}>{t("auth.signup.passwordLabel")}</Text>
        <TextInput
          style={s.input}
          value={password}
          onChangeText={setPassword}
          placeholder={t("auth.signup.passwordPlaceholder")}
          placeholderTextColor={T.soft}
          secureTextEntry
        />

        <TouchableOpacity
          style={[s.btn, loading && { opacity: 0.6 }]}
          onPress={onStart}
          disabled={loading}
          activeOpacity={0.9}
        >
          <Text style={s.btnText}>
            {loading
              ? t("auth.signup.sending")
              : t("auth.signup.sendCode")}
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  card: {
    backgroundColor: T.card,
    borderColor: T.border,
    borderWidth: 1,
    borderRadius: 16,
    padding: 14,
  },
  title: {
    color: T.text,
    fontSize: 22,
    fontWeight: "900",
    marginBottom: 10,
  },
  label: {
    color: T.soft,
    marginTop: 8,
    marginBottom: 6,
  },
  input: {
    backgroundColor: "rgba(255,255,255,0.04)",
    borderColor: T.border,
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: T.text,
  },
  btn: {
    marginTop: 14,
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: "center",
    backgroundColor: T.accent,
    borderWidth: 1,
    borderColor: T.border,
  },
  btnText: {
    color: "#0b1220",
    fontWeight: "900",
  },
});




