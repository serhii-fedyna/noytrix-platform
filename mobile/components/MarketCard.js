import React from "react";
import { View, Text, StyleSheet } from "react-native";

export default function MarketCard({ ticker, price, dayChange, cap }) {
  const up = (dayChange ?? 0) >= 0;
  return (
    <View style={styles.wrap}>
      <Text style={styles.ticker}>{ticker}</Text>
      <Text numberOfLines={1} style={styles.price}>
        ${price?.toLocaleString("en-US") ?? "-"}
      </Text>
      <Text style={[styles.delta, up ? styles.up : styles.down]}>
        24"0.00"}%
      </Text>
      <Text style={styles.cap} numberOfLines={1}>
        "-"}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    backgroundColor: "rgba(17,34,48,0.9)",
    borderRadius: 20,
    padding: 16,
    margin: 8,
    minWidth: 160,
  },
  ticker: { color: "#9AA6B2", fontSize: 16, fontWeight: "700" },
  price: {
    color: "#E6EDF3",
    fontSize: 24,
    fontWeight: "800",
    marginTop: 6,
  },
  delta: { marginTop: 6, fontSize: 15, fontWeight: "600" },
  up: { color: "#35C759" },
  down: { color: "#FF453A" },
  cap: { color: "#9AA6B2", marginTop: 4, fontSize: 14 },
});








