import React from "react";
import { ActivityIndicator, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { useTranslation } from "react-i18next";

// Google returns to this in-app route after the user chooses an account.
// AuthSession receives the same callback and finishes the token exchange.
export default function OAuthRedirectScreen() {
  const { t } = useTranslation();

  return (
    <View style={styles.screen}>
      <StatusBar style="light" />
      <View style={styles.loaderShell}>
        <ActivityIndicator size="large" color="#FFB020" />
      </View>
      <Text style={styles.title}>
        {t("auth.oauthRedirectTitle", { defaultValue: "Completing secure sign-in" })}
      </Text>
      <Text style={styles.text}>
        {t("auth.oauthRedirectText", {
          defaultValue: "Your Google account is confirmed. This takes only a moment.",
        })}
      </Text>
    </View>
  );
}

const styles = {
  screen: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 28,
    backgroundColor: "#020413",
  },
  loaderShell: {
    width: 72,
    height: 72,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 22,
    borderWidth: 1,
    borderColor: "rgba(255,176,32,0.35)",
    borderRadius: 36,
    backgroundColor: "rgba(255,176,32,0.12)",
  },
  title: {
    color: "#FFFFFF",
    fontSize: 24,
    fontWeight: "900",
    lineHeight: 30,
    textAlign: "center",
  },
  text: {
    maxWidth: 320,
    marginTop: 10,
    color: "#A8B4CF",
    fontSize: 15,
    fontWeight: "600",
    lineHeight: 22,
    textAlign: "center",
  },
};
