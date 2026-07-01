import React from "react";
import { View, Text, StyleSheet } from "react-native";

export default function PriceCard({ symbol = "-", price = 0, dayChange = 0, cap = "-" }) {
  const up = Number(dayChange) >= 0;
  return (
    <View style={styles.card}>
      <Text style={styles.symbol}>{symbol}</Text>
      <Text style={styles.price}>{Number(price || 0).toLocaleString()}</Text>
      <Text style={[styles.change, { color: up ? "#43d17a" : "#ff5c5c" }]}>
        24h: {Number(dayChange || 0).toFixed(2)}%
      </Text>
      <Text style={styles.meta}>Cap: {cap}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { padding: 14, borderRadius: 18, backgroundColor: "rgba(17,34,48,0.9)" },
  symbol: { color: "#E6EDF3", fontWeight: "800", fontSize: 16 },
  price: { color: "#fff", fontWeight: "900", fontSize: 22, marginTop: 6 },
  change: { fontSize: 16, fontWeight: "700", marginTop: 6 },
  meta: { color: "#9AA6B2", marginTop: 4 },
});
