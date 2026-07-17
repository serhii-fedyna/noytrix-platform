import React, { useEffect, useState } from "react";
import { View, Text, Pressable, Modal } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Ionicons } from "@expo/vector-icons";

const LANG_KEY = "app.language";

function normalizeLang(value) {
  const raw = String(value || "en").toLowerCase();
  if (raw.startsWith("ru")) return "ru";
  if (raw.startsWith("uk") || raw.startsWith("ua")) return "uk";
  return "en";
}

export default function LanguageBar({ onChange }) {
  const [lang, setLang] = useState("en");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(LANG_KEY).then(async (v) => {
      const legacy = v ? null : await AsyncStorage.getItem("app_lang").catch(() => null);
      const val = normalizeLang(v || legacy || "en");
      setLang(val);
      onChange?.(val);
    });
  }, []);

  const choose = async (v) => {
    const next = normalizeLang(v);
    setLang(next);
    await AsyncStorage.setItem(LANG_KEY, next);
    await AsyncStorage.setItem("app_lang", next);
    onChange?.(next);
    setOpen(false);
  };

  return (
    <View style={{ position: "absolute", right: 12, top: 12, flexDirection: "row", gap: 10 }}>
      {}
      <Pressable
        onPress={() => alert("")}
        style={{
          backgroundColor: "rgba(255,255,255,0.08)",
          paddingHorizontal: 12,
          height: 40,
          borderRadius: 12,
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <Ionicons name="notifications-outline" size={18} color="#fff" />
      </Pressable>

      {}
      <Pressable
        onPress={() => setOpen(true)}
        style={{
          backgroundColor: "rgba(255,255,255,0.08)",
          paddingHorizontal: 14,
          height: 40,
          borderRadius: 12,
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <Text style={{ color: "#fff", fontWeight: "700" }}>{lang.toUpperCase()}</Text>
      </Pressable>

      <Modal transparent animationType="fade" visible={open} onRequestClose={() => setOpen(false)}>
        <Pressable style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.4)" }} onPress={() => setOpen(false)}>
          <View
            style={{
              position: "absolute",
              right: 12,
              top: 64,
              backgroundColor: "#142034",
              borderRadius: 14,
              padding: 8,
              width: 160,
            }}
          >
            {["en", "ru", "uk"].map((v) => (
              <Pressable
                key={v}
                onPress={() => choose(v)}
                style={{
                  paddingVertical: 10,
                  paddingHorizontal: 12,
                  borderRadius: 10,
                  backgroundColor: lang === v ? "rgba(255,255,255,0.08)" : "transparent",
                }}
              >
                <Text style={{ color: "#fff", fontWeight: "700" }}>{v.toUpperCase()}</Text>
              </Pressable>
            ))}
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}









