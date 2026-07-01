import { SafeAreaView } from "react-native";
import { Stack, useLocalSearchParams } from "expo-router";
import { WebView } from "react-native-webview";

const colors = { bg: "#0B1220", text: "#E7EEFF" };

export default function NewsView() {
  const { url, title } = useLocalSearchParams();

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: "transparent" }}>
      <Stack.Screen
        options={{
          title: title ? String(title).slice(0, 40) : "",
          headerStyle: { backgroundColor: "transparent" },
          headerTintColor: colors.text,
          headerShadowVisible: false,
        }}
      />
      <WebView
        source={{ uri: String(url) }}
        startInLoadingState
        allowsBackForwardNavigationGestures
        setSupportMultipleWindows={false}
        incognito
        originWhitelist={["*"]}
        style={{ backgroundColor: "transparent" }}
      />
    </SafeAreaView>
  );
}

























