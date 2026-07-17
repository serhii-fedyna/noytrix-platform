// app/_layout.js
import i18n from "./i18n";

import React, { useEffect, useRef, useState } from "react";
import { Stack, router } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import {
  View,
  Text,
  ActivityIndicator,
  TouchableOpacity,
  Platform,
  Modal,
} from "react-native";
import * as LocalAuthentication from "expo-local-authentication";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { OneSignal, LogLevel } from "react-native-onesignal";

import { useAuthStore } from "./lib/store.auth";
import { getAuthState } from "./lib/authApi";
import { setAppAlertHandler } from "./lib/appAlert";
import { initAnalytics } from "./lib/analytics";
import { ReviewPromptHost } from "./lib/reviewPrompt";
import { normalizeLang } from "./i18n/lang";

const ONESIGNAL_APP_ID = "844ce644-cdb6-4d24-b07e-4e1f117e247d";
const NOTIFICATIONS_PREF_KEY = "profile.notifications";

function PremiumAlert({ alert, onClose }) {
  return (
    <Modal visible={!!alert} transparent animationType="fade" onRequestClose={onClose}>
      <View
        style={{
          flex: 1,
          backgroundColor: "rgba(0,0,0,0.72)",
          justifyContent: "center",
          alignItems: "center",
          padding: 22,
        }}
      >
        <View
          style={{
            width: "100%",
            maxWidth: 420,
            backgroundColor: "#0b1220",
            borderRadius: 22,
            padding: 20,
            borderWidth: 1,
            borderColor: "rgba(255,176,32,0.35)",
          }}
        >
          <Text style={{ color: "#ffb020", fontSize: 18, fontWeight: "900", marginBottom: 8 }}>
            {alert?.title || "Noytrix"}
          </Text>

          {!!alert?.message && (
            <Text style={{ color: "#A8B4CF", fontSize: 15, lineHeight: 21 }}>
              {alert.message}
            </Text>
          )}

          <TouchableOpacity
            onPress={onClose}
            activeOpacity={0.85}
            style={{
              marginTop: 18,
              backgroundColor: "#ffb020",
              paddingVertical: 13,
              borderRadius: 16,
              alignItems: "center",
            }}
          >
            <Text style={{ color: "#0b1220", fontWeight: "900" }}>OK</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

function AppShell({ children, appAlert, setAppAlert }) {
  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      {children}
      <PremiumAlert alert={appAlert} onClose={() => setAppAlert(null)} />
      <ReviewPromptHost />
    </SafeAreaProvider>
  );
}

export default function RootLayout() {
  const init = useAuthStore((s) => s.init);
  const isReady = useAuthStore((s) => s.isReady);
  const isAuth = useAuthStore((s) => s.isAuth);
  const logout = useAuthStore((s) => s.logout);

  const [hasToken, setHasToken] = useState(false);
  const [appAlert, setAppAlert] = useState(null);

  const [bioChecked, setBioChecked] = useState(false);
  const [bioOk, setBioOk] = useState(false);
  const [bioError, setBioError] = useState(false);

  const oneSignalInitDone = useRef(false);

  useEffect(() => {
    setAppAlertHandler(setAppAlert);

    initAnalytics();

    try {
      if (typeof init === "function") init();
    } catch (e) {
      console.log("[LAYOUT] init error:", e);
    }
  }, [init]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const saved = await AsyncStorage.getItem("app.language");
        const legacy = saved ? null : await AsyncStorage.getItem("app_lang").catch(() => null);
        const next = normalizeLang(saved || legacy || i18n.language);
        await AsyncStorage.multiSet([
          ["app.language", next],
          ["app_lang", next],
        ]);
        if (!cancelled && next !== normalizeLang(i18n.language)) {
          await i18n.changeLanguage(next);
        }
      } catch (e) {
        console.log("[i18n] restore language error:", e);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const state = await getAuthState();
        if (!cancelled) setHasToken(!!state?.access_token);
      } catch {
        if (!cancelled) setHasToken(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isReady, isAuth]);

  useEffect(() => {
    if (oneSignalInitDone.current) return;
    oneSignalInitDone.current = true;

    const logSubscriptionState = (label = "state") => {
      try {
        const sub = OneSignal.User.pushSubscription;
        const id = sub?.getId?.() ?? null;
        const token = sub?.getToken?.() ?? null;
        const optedIn = sub?.getOptedIn?.() ?? null;

        console.log(`[ONESIGNAL] ${label}`, {
          platform: Platform.OS,
          id,
          token,
          optedIn,
        });
      } catch (e) {
        console.log("[ONESIGNAL] logSubscriptionState error:", e);
      }
    };

    const initOneSignal = async () => {
      try {
        OneSignal.Debug.setLogLevel(LogLevel.Verbose);
        OneSignal.initialize(ONESIGNAL_APP_ID);

        console.log("[ONESIGNAL] initialized");

        try {
          OneSignal.Notifications.addClickListener(async (event) => {
            try {
              console.log("[ONESIGNAL] notification clicked:", JSON.stringify(event));

              const data = event?.notification?.additionalData || {};
              const input = data?.input || data?.url || "";
              const screen = data?.screen || "shield";

              if (input) {
                console.log("[PUSH NAV] open scan:", input);

                try {
                  await AsyncStorage.setItem("shield.prefill", String(input));
                } catch (e) {
                  console.log("[PUSH NAV] prefill save error:", e);
                }

                router.push({
                  pathname: screen === "shield_pro" || screen === "shield-pro" ? "/shield-pro" : "/shield",
                  params: { input: String(input), source: data?.source || "push" },
                });
              }
            } catch (e) {
              console.log("[ONESIGNAL] click handler error:", e);
            }
          });
        } catch (e) {
          console.log("[ONESIGNAL] addClickListener error:", e);
        }

        try {
          OneSignal.Notifications.addForegroundLifecycleListener({
            onWillDisplay: (event) => {
              console.log("[ONESIGNAL] foreground will display:", JSON.stringify(event));
              event?.notification?.display?.();
            },
          });
        } catch (e) {
          console.log("[ONESIGNAL] addForegroundLifecycleListener error:", e);
        }

        try {
          OneSignal.Notifications.addPermissionObserver((granted) => {
            console.log("[ONESIGNAL] permission changed:", granted);
            logSubscriptionState("permission_changed");
          });
        } catch (e) {
          console.log("[ONESIGNAL] addPermissionObserver error:", e);
        }

        try {
          OneSignal.User.pushSubscription.addObserver((state) => {
            console.log("[ONESIGNAL] pushSubscription changed:", JSON.stringify(state));
            logSubscriptionState("push_observer");
          });
        } catch (e) {
          console.log("[ONESIGNAL] pushSubscription observer error:", e);
        }

        let notificationsEnabled = true;
        try {
          const savedPref = await AsyncStorage.getItem(NOTIFICATIONS_PREF_KEY);
          notificationsEnabled = savedPref !== "0";
        } catch (e) {
          console.log("[ONESIGNAL] read notification pref error:", e);
        }

        if (!notificationsEnabled) {
          try {
            OneSignal.User.pushSubscription.optOut();
            console.log("[ONESIGNAL] optOut called from saved preference");
          } catch (e) {
            console.log("[ONESIGNAL] optOut error:", e);
          }
          logSubscriptionState("disabled_by_user");
          return;
        }

        try {
          OneSignal.User.pushSubscription.optIn();
          console.log("[ONESIGNAL] optIn called from saved preference");
        } catch (e) {
          console.log("[ONESIGNAL] optIn error:", e);
        }

        logSubscriptionState("before_permission");

        try {
          const accepted = await OneSignal.Notifications.requestPermission(true);
          console.log("[ONESIGNAL] requestPermission result:", accepted);
        } catch (e) {
          console.log("[ONESIGNAL] requestPermission error:", e);
        }

        try {
          OneSignal.User.pushSubscription.optIn();
          console.log("[ONESIGNAL] optIn called after permission");
        } catch (e) {
          console.log("[ONESIGNAL] optIn after permission error:", e);
        }

        setTimeout(() => logSubscriptionState("after_2s"), 2000);
        setTimeout(() => logSubscriptionState("after_5s"), 5000);
        setTimeout(() => logSubscriptionState("after_10s"), 10000);
      } catch (e) {
        console.log("[ONESIGNAL] init error:", e);
      }
    };

    initOneSignal();
  }, []);

  useEffect(() => {
    if (!isReady) return;

    if (!isAuth || !hasToken) {
      setBioChecked(true);
      setBioOk(true);
      setBioError(false);
      return;
    }

    let cancelled = false;

    const run = async () => {
      try {
        setBioChecked(false);
        setBioOk(false);
        setBioError(false);

        const hasHardware = await LocalAuthentication.hasHardwareAsync();
        const isEnrolled = await LocalAuthentication.isEnrolledAsync();

        if (!hasHardware || !isEnrolled) {
          if (!cancelled) {
            setBioOk(true);
            setBioChecked(true);
          }
          return;
        }

        const result = await LocalAuthentication.authenticateAsync({
          promptMessage: "Unlock Noytrix",
          fallbackLabel: "Use passcode",
          cancelLabel: "Cancel",
        });

        if (cancelled) return;

        if (result.success) {
          setBioOk(true);
          setBioChecked(true);
          setBioError(false);
        } else {
          setBioOk(false);
          setBioChecked(true);
          setBioError(true);
        }
      } catch (e) {
        console.log("[LAYOUT] biometric error:", e);

        if (!cancelled) {
          setBioOk(false);
          setBioChecked(true);
          setBioError(true);
        }
      }
    };

    run();

    return () => {
      cancelled = true;
    };
  }, [isReady, isAuth, hasToken]);

  if (!isReady) return null;

  if (isAuth && hasToken && !bioOk && bioChecked) {
    return (
      <AppShell appAlert={appAlert} setAppAlert={setAppAlert}>
        <View
          style={{
            flex: 1,
            backgroundColor: "#020413",
            alignItems: "center",
            justifyContent: "center",
            paddingHorizontal: 24,
          }}
        >
          <Text
            style={{
              color: "#ffffff",
              fontSize: 18,
              textAlign: "center",
              marginBottom: 16,
              fontWeight: "800",
            }}
          >
            Could not unlock Noytrix
          </Text>

          <Text
            style={{
              color: "#9ca3af",
              fontSize: 14,
              textAlign: "center",
              marginBottom: 24,
              lineHeight: 20,
            }}
          >
            You can sign in again using your email and password.
          </Text>

          <TouchableOpacity
            onPress={async () => {
              try {
                if (typeof logout === "function") await logout();
              } catch (e) {
                console.log("[LAYOUT] logout error:", e);
              }
            }}
            activeOpacity={0.85}
            style={{
              paddingHorizontal: 24,
              paddingVertical: 10,
              borderRadius: 999,
              borderWidth: 1,
              borderColor: "#fbbf24",
            }}
          >
            <Text style={{ color: "#fbbf24", fontSize: 16, fontWeight: "800" }}>
              Sign in again
            </Text>
          </TouchableOpacity>
        </View>
      </AppShell>
    );
  }

  if (isAuth && hasToken && !bioChecked) {
    return (
      <AppShell appAlert={appAlert} setAppAlert={setAppAlert}>
        <View
          style={{
            flex: 1,
            backgroundColor: "#020413",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <ActivityIndicator />
          <Text style={{ color: "#ffffff", marginTop: 12, fontSize: 16 }}>
            Unlocking Noytrix…
          </Text>
        </View>
      </AppShell>
    );
  }

  return (
    <AppShell appAlert={appAlert} setAppAlert={setAppAlert}>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="calculator" />
        <Stack.Screen name="futures" />
      </Stack>
    </AppShell>
  );
}
