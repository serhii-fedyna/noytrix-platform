// app/(tabs)/_layout.js
import React, { useEffect } from "react";
import { Tabs } from "expo-router";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { StyleSheet, View } from "react-native";
import * as SplashScreen from "expo-splash-screen";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";

SplashScreen.preventAutoHideAsync();

export default function TabsLayout() {
  const insets = useSafeAreaInsets();
  const { t } = useTranslation();

  useEffect(() => {
    const timer = setTimeout(() => {
      SplashScreen.hideAsync();
    }, 3000);
    return () => clearTimeout(timer);
  }, []);

  const ACTIVE = "#FFA500";
  const INACTIVE = "#8D9DB5";

  const LABELS = {
    index: t("tabs.home"),
    pro: t("tabs.pro"),
    spot: t("tabs.spot"),
    profile: t("tabs.profile"),
  };

  const baseHeight = 59;
  const barHeight = baseHeight + Math.max(insets.bottom, 6);

  return (
    <Tabs
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarHideOnKeyboard: true,
        tabBarActiveTintColor: ACTIVE,
        tabBarInactiveTintColor: INACTIVE,

        tabBarBackground: () => (
          <View style={StyleSheet.absoluteFill}>
            <LinearGradient
              colors={["#06080f", "#0b1c4f"]}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={StyleSheet.absoluteFill}
            />
          </View>
        ),

        tabBarStyle: {
          borderTopColor: "rgba(255,255,255,0.08)",
          borderTopWidth: 1,
          backgroundColor: "transparent",
          elevation: 0,
          height: barHeight,
          paddingBottom: Math.max(insets.bottom, 6),
          paddingTop: 6,
        },

        tabBarLabel:
          LABELS[route.name]?.toUpperCase() ??
          route.name.toUpperCase(),

        tabBarLabelStyle: {
          fontSize: 11,
          fontWeight: "700",
          textTransform: "uppercase",
        },

        tabBarItemStyle: { paddingTop: 2 },

        tabBarIcon: ({ focused }) => {
          const color = focused ? ACTIVE : INACTIVE;

          switch (route.name) {
            case "index":
              return <Ionicons name="home" size={22} color={color} />;

            case "pro":
              return (
                <MaterialCommunityIcons
                  name="star"
                  size={22}
                  color={color}
                />
              );

            case "spot":
              return <Ionicons name="cube" size={22} color={color} />;

            case "profile":
              return (
                <Ionicons
                  name="person-circle-outline"
                  size={22}
                  color={color}
                />
              );

            case "trading":
              return (
                <MaterialCommunityIcons
                  name="chart-line"
                  size={22}
                  color={color}
                />
              );

            default:
              return (
                <Ionicons
                  name="ellipse-outline"
                  size={22}
                  color={color}
                />
              );
          }
        },
      })}
    >
      <Tabs.Screen
        name="index"
        options={{ title: t("tabs.home") }}
      />
      <Tabs.Screen
        name="pro"
        options={{ title: t("tabs.pro") }}
      />
      <Tabs.Screen
        name="spot"
        options={{ title: t("tabs.spot") }}
      />
      <Tabs.Screen
        name="trading"
        options={{ href: null }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: t("tabs.profile") }}
      />
    </Tabs>
  );
}




