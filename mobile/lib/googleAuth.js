import * as AuthSession from "expo-auth-session";
import * as WebBrowser from "expo-web-browser";
import Constants from "expo-constants";
WebBrowser.maybeCompleteAuthSession();

export async function signInWithGoogle() {
  const androidId = Constants.expoConfig?.extra?.googleAndroidClientId
    || Constants.manifest?.extra?.googleAndroidClientId;
  const redirectUri = AuthSession.makeRedirectUri({ scheme: Constants.expoConfig?.scheme || "noytrix" });

  const discovery = {
    authorizationEndpoint: "https://accounts.google.com/o/oauth2/v2/auth",
    tokenEndpoint: "https://oauth2.googleapis.com/token",
  };

  const request = new AuthSession.AuthRequest({
    clientId: androidId,
    redirectUri,
    scopes: ["openid","email","profile"],
    responseType: AuthSession.ResponseType.Token,
  });

  const result = await AuthSession.startAsync({
    authUrl: request.makeAuthUrl(),
    returnUrl: redirectUri,
  });

  if (result.type !== "success" || !result.params?.access_token) return null;

  const res = await fetch("https://www.googleapis.com/oauth2/v3/userinfo", {
    headers: { Authorization: Bearer  },
  });
  const profile = await res.json(); // {sub,email,name,given_name,picture...}
  profile.idToken = result.params.id_token;
  return profile;
}







