import React from "react";
import { LinearGradient } from "expo-linear-gradient";
import { StyleSheet, View } from "react-native";

export default function GradientBackground({ children }) {
  return (
    <View style={{ flex: 1 }}>
      <LinearGradient
        colors={["#0F1730", "#0B1220"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={StyleSheet.absoluteFill}
      />
      {children}
    </View>
  );
}










