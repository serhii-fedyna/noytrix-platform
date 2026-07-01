import { Share, Platform } from "react-native";
import * as Sharing from "expo-sharing";
import * as FileSystem from "expo-file-system";

export async function shareImagePremium({
  capture,
  message = "",
  title = "Noytrix",
  dialogTitle = "Share",
}) {
  try {
    const uri = await capture?.();

    if (!uri) {
      return Share.share({ title, message });
    }

    const fileUri = uri.startsWith(FileSystem.cacheDirectory)
      ? uri
      : `${FileSystem.cacheDirectory}noytrix-share-${Date.now()}.png`;

    if (fileUri !== uri) {
      await FileSystem.copyAsync({ from: uri, to: fileUri });
    }

    const available = await Sharing.isAvailableAsync();

    if (available && Platform.OS !== "web") {
      return Sharing.shareAsync(fileUri, {
        mimeType: "image/png",
        dialogTitle,
        UTI: "public.png",
      });
    }

    return Share.share({ title, message, url: fileUri });
  } catch (e) {
    return Share.share({ title, message });
  }
}
