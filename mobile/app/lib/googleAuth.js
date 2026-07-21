import * as AuthSession from "expo-auth-session";
import * as WebBrowser from "expo-web-browser";
import Constants from "expo-constants";
import { Platform } from "react-native";

WebBrowser.maybeCompleteAuthSession();

export async function signInWithGoogle() {
  const extra = Constants.expoConfig?.extra || Constants.manifest?.extra || {};
  const clientId =
    (Platform.OS === "android" ? extra.googleAndroidClientId : extra.googleWebClientId) ||
    extra.googleWebClientId ||
    extra.googleAndroidClientId ||
    extra.googleClientId ||
    "";

  if (!clientId) {
    throw new Error("google_client_id_missing");
  }

  const redirectUri = AuthSession.makeRedirectUri({
    scheme: Constants.expoConfig?.scheme || "noytrix",
  });

  const discovery = {
    authorizationEndpoint: "https://accounts.google.com/o/oauth2/v2/auth",
    tokenEndpoint: "https://oauth2.googleapis.com/token",
  };

  const request = new AuthSession.AuthRequest({
    clientId,
    redirectUri,
    scopes: ["openid", "email", "profile"],
    responseType: AuthSession.ResponseType.Token,
  });

  const authUrl = await request.makeAuthUrlAsync(discovery);

  const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUri);

  if (result.type === "cancel" || result.type === "dismiss") {
    return null;
  }

  if (result.type !== "success" || !result.url) {
    throw new Error("google_auth_not_completed");
  }

  const params = parseGoogleAuthParams(result.url);
  if (params.error) {
    throw new Error(`google_${params.error}`);
  }

  if (!params.access_token) {
    throw new Error("google_access_token_missing");
  }

  return {
    accessToken: params.access_token,
    idToken: params.id_token || null,
  };
}

function parseGoogleAuthParams(url) {
  const out = {};
  const raw = String(url || "");
  const query = raw.includes("?") ? raw.split("?")[1].split("#")[0] : "";
  const hash = raw.includes("#") ? raw.split("#")[1] : "";

  [query, hash].filter(Boolean).forEach((part) => {
    part.split("&").forEach((pair) => {
      const [k, v = ""] = pair.split("=");
      if (!k) return;
      out[decodeURIComponent(k)] = decodeURIComponent(v.replace(/\+/g, " "));
    });
  });

  return out;
}
