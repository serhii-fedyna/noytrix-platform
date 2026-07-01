// app/auth/forgot.js
import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Alert } from "react-native";
import { useRouter } from "expo-router";
import { useAuthStore } from "../../stores/auth/useAuthStore";
export default function Forgot() {
  const { t } = useTranslation();
  const router = useRouter();
  const resetStart = useAuthStore(s=>s.resetStart);
  const [email,setEmail] = useState("");

  const onSend = async () => {
    try {
      await resetStart({ email });
      showAppAlert(t("auth.common.errorTitle"),t("auth.common.errorBody"));
      router.push({ pathname: "/auth/reset", params: { email } });
    } catch (e) {
      showAppAlert("",e.message || "");
    }
  };

  return (
    <View style={{ flex:1, backgroundColor:"#0a1322", padding:16 }}>
      <View style={s.card}>
        <Text style={s.title}>{t("auth.forgot.title")}</Text>
        <TextInput style={s.input} value={email} onChangeText={setEmail} placeholder="you@mail.com" placeholderTextColor={"#bcd2ff"} keyboardType="email-address" autoCapitalize="none"/>
        <TouchableOpacity style={s.btn} onPress={onSend}><Text style={s.btnText}>{t("auth.forgot.button")}</Text></TouchableOpacity>
      </View>
    </View>
  );
}
const s=StyleSheet.create({
  card:{ backgroundColor:"rgba(17,29,49,0.9)",borderColor:"#1a2a45",borderWidth:1,borderRadius:16,padding:14 },
  title:{ color:"#e9f0ff",fontSize:22,fontWeight:"900",marginBottom:10 },
  input:{ backgroundColor:"rgba(255,255,255,0.04)", borderColor:"#1a2a45", borderWidth:1, borderRadius:12, paddingHorizontal:12, paddingVertical:10, color:"#e9f0ff" },
  btn:{ marginTop:14, borderRadius:12, paddingVertical:12, alignItems:"center", backgroundColor:"#63b3ff", borderWidth:1, borderColor:"#1a2a45" },
  btnText:{ color:"#0b1220", fontWeight:"900" }
});

















