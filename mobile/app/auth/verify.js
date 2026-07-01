import React from "react";
import { View, Text, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { showAppAlert } from "../lib/appAlert";

export default function Verify() {
  const router = useRouter();
  const loading = false;

  const onConfirm = () => {
    showAppAlert("Error", "Verification is not available here.");
  };

  return (
    <View style={{ flex: 1, backgroundColor: "#06080f", justifyContent: "center", padding: 20 }}>
      <Text style={{ color: "#e9ecff", fontSize: 24, fontWeight: "900", marginBottom: 12 }}>
        Verification
      </Text>
      <Text style={{ color: "#A8B4CF", marginBottom: 20 }}>
        Open registration again and enter the code from email.
      </Text>
      <TouchableOpacity onPress={onConfirm} style={{ backgroundColor: "#ffb020", padding: 14, borderRadius: 16 }}>
        <Text style={{ color: "#0b1220", fontWeight: "900", textAlign: "center" }}>
          {loading ? "Loading..." : "Confirm"}
        </Text>
      </TouchableOpacity>
    </View>
  );
}
