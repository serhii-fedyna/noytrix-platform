// app/auth/reset.js
import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Alert } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useAuthStore } from "../../stores/auth/useAuthStore";
export default function Reset() {
  const { t } = useTranslation();
  const router = useRouter();
  const { email } = useLocalSearchParams();
  const resetConfirm = useAuthStore(s=>s.resetConfirm);

  const [code,setCode]=useState("");
  const [newPassword,setNewPassword]=useState("");

  const onConfirm = async () => {
    try {
      await resetConfirm({ email, code, new_password: newPassword });
      showAppAlert(t("auth.common.errorTitle"),t("auth.common.errorBody"));
      router.replace("/(tabs)/profile");
    } catch (e) {
      showAppAlert("",e.message || "");
    }
  };

  return (
    <View style={{ flex:1, backgroundColor:"#0a1322", padding:16 }}>
      <View style={s.card}>
        <Text style={s.title}>{t("auth.reset.title")}</Text>
        <Text style={{ color: "#bcd2ff", marginBottom: 8 }}>{t("auth.reset.subtitle")}</Text>
        <TextInput style={s.input} value={code} onChangeText={setCode} placeholder="" placeholderTextColor={"#bcd2ff"} keyboardType="number-pad"/>
        <TextInput style={s.input} value={newPassword} onChangeText={setNewPassword} placeholder="" placeholderTextColor={"#bcd2ff"} secureTextEntry/>
        <TouchableOpacity style={s.btn} onPress={onConfirm}><Text style={s.btnText}>{t("auth.reset.button")}</Text></TouchableOpacity>
      </View>
    </View>
  );
}
const s=StyleSheet.create({
  card:{ backgroundColor:"rgba(17,29,49,0.9)",borderColor:"#1a2a45",borderWidth:1,borderRadius:16,padding:14 },
  title:{ color:"#e9f0ff",fontSize:22,fontWeight:"900",marginBottom:10 },
  input:{ backgroundColor:"rgba(255,255,255,0.04)", borderColor:"#1a2a45", borderWidth:1, borderRadius:12, paddingHorizontal:12, paddingVertical:10, color:"#e9f0ff", marginTop:8 },
  btn:{ marginTop:14, borderRadius:12, paddingVertical:12, alignItems:"center", backgroundColor:"#63b3ff", borderWidth:1, borderColor:"#1a2a45" },
  btnText:{ color:"#0b1220", fontWeight:"900" }
});

















