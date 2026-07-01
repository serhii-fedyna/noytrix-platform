import React from "react";
import { View, Text, StyleSheet } from "react-native";

export default function News({ items = [] }) {
  return (
    <View style={styles.block}>
      <Text style={styles.h2}>News</Text>
      <View style={styles.list}>
        {items.length === 0 ? (
          <View style={styles.stub}>
            <Text style={styles.stubText}>No news yet. Pull down to refresh.</Text>
          </View>
        ) : (
          items.map((item, idx) => (
            <View key={item?.id || item?.url || String(idx)} style={styles.item}>
              <Text style={styles.title}>{item?.title || "Untitled"}</Text>
            </View>
          ))
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  block: { marginTop: 16 },
  h2: { color: "#E6EDF3", fontWeight: "800", fontSize: 20, marginBottom: 10 },
  list: { backgroundColor: "rgba(17,34,48,0.9)", borderRadius: 18 },
  item: { padding: 16, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "rgba(150,170,190,0.2)" },
  title: { color: "#DCE6EE", fontSize: 15, fontWeight: "500" },
  stub: { padding: 18 },
  stubText: { color: "#9AA6B2", fontSize: 14 },
});
