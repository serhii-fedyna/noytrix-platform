import React from "react";
import { TouchableOpacity, Text, ActivityIndicator, StyleSheet } from "react-native";

export default function Button({
  title = "",
  onPress,
  disabled = false,
  loading = false,
  color = "primary",
  style,
  textStyle,
}) {
  const palette = {
    primary: "#FFB321",
    primaryText: "#0A1A24",
    neutral: "#1E3445",
    neutralText: "#E6EDF3",
    danger: "#E84D4D",
    success: "#2ECC71",
  };

  const bg =
    color === "primary" ? palette.primary :
    color === "danger"  ? palette.danger  :
    color === "success" ? palette.success : palette.neutral;

  const fg =
    color === "primary" ? palette.primaryText :
    color === "danger"  ? "#FFFFFF" :
    color === "success" ? "#0A1A24" : palette.neutralText;

  return (
    <TouchableOpacity
      activeOpacity={0.8}
      onPress={onPress}
      disabled={disabled || loading}
      style={[styles.btn, { backgroundColor: bg, opacity: (disabled || loading) ? 0.6 : 1 }, style]}
    >
      {loading
        ? <ActivityIndicator />
        : <Text style={[styles.text, { color: fg }, textStyle]} numberOfLines={1}>{title}</Text>}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  btn: {
    borderRadius: 18,
    paddingVertical: 16,
    paddingHorizontal: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  text: {
    fontSize: 16,
    fontWeight: "800",
  },
});






