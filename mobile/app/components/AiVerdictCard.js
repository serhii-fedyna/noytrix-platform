import React from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

const COLORS = {
  text: "#E9EEFF",
  dim: "#A8B4CF",
  accent: "#FFB020",
  border: "rgba(255,176,32,0.24)",
  panel: "rgba(255,176,32,0.08)",
};

export default function AiVerdictCard({ title, text, emptyText, style }) {
  const body = String(text || "").trim();
  if (!body && !emptyText) return null;

  return (
    <View
      style={[
        {
          marginTop: 12,
          borderRadius: 18,
          borderWidth: 1,
          borderColor: COLORS.border,
          backgroundColor: COLORS.panel,
          padding: 14,
        },
        style,
      ]}
    >
      {!!title && (
        <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 8 }}>
          <Ionicons name="sparkles" size={18} color={COLORS.accent} />
          <Text style={{ color: COLORS.text, fontWeight: "900", marginLeft: 8, fontSize: 15 }}>
            {title}
          </Text>
        </View>
      )}
      <Text style={{ color: COLORS.text, fontSize: 15, lineHeight: 22, fontWeight: "800" }}>
        {body || emptyText}
      </Text>
    </View>
  );
}
