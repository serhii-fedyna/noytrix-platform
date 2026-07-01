import React from "react";
import { StatusBar } from "expo-status-bar";
import { LinearGradient } from "expo-linear-gradient";
import { SafeAreaView, View, StyleSheet } from "react-native";

export default function Screen({ children }) {
  return (
    <View style={styles.root}>
      <LinearGradient
        colors={["#0B1E2C", "#092033"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={StyleSheet.absoluteFill}
      />
      <SafeAreaView style={styles.safe}>
        <StatusBar style="light" />
        {children}
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#0B1E2C" },
  safe: { flex: 1, paddingHorizontal: 20, paddingTop: 8 },
});








