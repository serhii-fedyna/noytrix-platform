import * as AuthSession from "expo-auth-session";
import * as WebBrowser from "expo-web-browser";
import Constants from "expo-constants";

WebBrowser.maybeCompleteAuthSession();

export async function signInWithGoogle() {
  const extra = Constants.expoConfig?.extra || Constants.manifest?.extra || {};
  const clientId =
    extra.googleAndroidClientId ||
    extra.googleWebClientId ||
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

  const result = await AuthSession.startAsync({
    authUrl,
    returnUrl: redirectUri,
  });

  if (result.type !== "success" || !result.params?.access_token) {
    return null;
  }

  return {
    accessToken: result.params.access_token,
    idToken: result.params.id_token || null,
  };
}
