// components/NoyBot.js
import React, { useEffect, useRef, useState } from "react";
import { Animated, Easing, Pressable, View, Text } from "react-native";
import { useRouter } from "expo-router";
import { askAIQuickTip } from "../app/lib/ai";


const BUBBLE_BG = "rgba(11,28,79,0.95)";
const BUBBLE_TXT = "#E9ECFF";
const BOT_BG = "#ffb020";

const EMOJIS = ["","","","","","",""];

export default function NoyBot({ talkativeness = "medium" }) {
  const router = useRouter();

  
  const x = useRef(new Animated.Value(24)).current;
  const y = useRef(new Animated.Value(140)).current;
  const scale = useRef(new Animated.Value(1)).current;
  const rotate = useRef(new Animated.Value(0)).current; 

  const [face, setFace] = useState("");
  const [thought, setThought] = useState(null);

  
  function wander() {
    const nx = 16 + Math.random() * 280;
    const ny = 100 + Math.random() * 460;
    Animated.parallel([
      Animated.timing(x, { toValue: nx, duration: 2400, easing: Easing.inOut(Easing.quad), useNativeDriver: false }),
      Animated.timing(y, { toValue: ny, duration: 2400, easing: Easing.inOut(Easing.quad), useNativeDriver: false }),
    ]).start();
  }
  useEffect(() => {
    const id = setInterval(wander, 3000);
    return () => clearInterval(id);
  }, []);

  
  function emote(nextFace) {
    setFace(nextFace);
    Animated.sequence([
      Animated.parallel([
        Animated.timing(scale, { toValue: 1.1, duration: 180, easing: Easing.out(Easing.quad), useNativeDriver: true }),
        Animated.timing(rotate, { toValue: 1, duration: 180, easing: Easing.out(Easing.quad), useNativeDriver: true }),
      ]),
      Animated.parallel([
        Animated.timing(scale, { toValue: 1, duration: 220, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
        Animated.timing(rotate, { toValue: 0, duration: 220, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
      ]),
    ]).start();
  }

  
  useEffect(() => {
    const mins = talkativeness === "high" ? 3 : talkativeness === "low" ? 12 : 6;
    const id = setInterval(async () => {
      try {
        const tip = await askAIQuickTip();
        if (tip) {
          setThought(`“${tip}”`);
          emote(EMOJIS[Math.floor(Math.random() * EMOJIS.length)]);
          setTimeout(() => setThought(null), 7000);
          return;
        }
      } catch {}
      const local = [
        "«",
        "«",
        "«",
        "«",
      ];
      setThought(local[Math.floor(Math.random() * local.length)]);
      emote(EMOJIS[Math.floor(Math.random() * EMOJIS.length)]);
      setTimeout(() => setThought(null), 6000);
    }, mins * 60 * 1000);
    return () => clearInterval(id);
  }, [talkativeness]);

  const rotateDeg = rotate.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "6deg"] });

  return (
    <Animated.View style={{ position: "absolute", left: x, top: y, zIndex: 99, transform: [{ rotate: rotateDeg }] }}>
      {thought && (
        <View style={{ backgroundColor: BUBBLE_BG, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 12, marginBottom: 6, maxWidth: 280 }}>
          <Text style={{ color: BUBBLE_TXT, fontSize: 12 }}>{thought}</Text>
        </View>
      )}

      <Pressable
        onPress={() => router.push("/ai-chat")}
        hitSlop={12}
        style={{ borderRadius: 28, padding: 2, backgroundColor: "rgba(255,255,255,0.08)" }}
      >
        <Animated.View
          style={{
            width: 56, height: 56, borderRadius: 28, alignItems: "center", justifyContent: "center",
            backgroundColor: BOT_BG, transform: [{ scale }],
            shadowColor: "#000", shadowOpacity: 0.25, shadowRadius: 8, shadowOffset: { width: 0, height: 2 },
            elevation: 6,
          }}
        >
          <Text style={{ fontSize: 28 }}>{face}</Text>
        </Animated.View>
      </Pressable>
    </Animated.View>
  );
}







