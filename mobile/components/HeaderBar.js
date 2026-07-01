import { View, Text, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

const COLORS = { bg:"#0B1220", text:"#E7EEFF" };

export default function HeaderBar({ title="" }) {
  const router = useRouter();
  return (
    <View style={{ backgroundColor: "transparent", paddingHorizontal:16, paddingVertical:12, flexDirection:"row", alignItems:"center" }}>
      <TouchableOpacity onPress={() => router.back()} style={{ padding:6, marginRight:8 }}>
        <Ionicons name="chevron-back" size={26} color={COLORS.text} />
      </TouchableOpacity>
      <Text numberOfLines={1} style={{ color: COLORS.text, fontSize:22, fontWeight:"800", flex:1 }}>{title}</Text>
    </View>
  );
}















