import * as AuthSession from "expo-auth-session";
import * as WebBrowser from "expo-web-browser";
import Constants from "expo-constants";
import * as Application from "expo-application";

WebBrowser.maybeCompleteAuthSession();

export async function signInWithGoogle() {
  const extra = Constants.expoConfig?.extra || Constants.manifest?.extra || {};
  // Android uses the OAuth client bound to the package name and Play signing
  // certificate. The authorization-code + PKCE flow is required for native apps.
  const clientId =
    extra.googleAndroidClientId ||
    extra.googleWebClientId ||
    extra.googleClientId ||
    "";

  if (!clientId) {
    throw new Error("google_client_id_missing");
  }

  const redirectUri = AuthSession.makeRedirectUri({
    native: `${Application.applicationId || "com.noytrix.app"}:/oauthredirect`,
  });

  const discovery = {
    authorizationEndpoint: "https://accounts.google.com/o/oauth2/v2/auth",
    tokenEndpoint: "https://oauth2.googleapis.com/token",
  };

  const request = new AuthSession.AuthRequest({
    clientId,
    redirectUri,
    scopes: ["openid", "email", "profile"],
    responseType: AuthSession.ResponseType.Code,
    usePKCE: true,
    extraParams: {
      prompt: "select_account",
    },
  });

  const result = await request.promptAsync(discovery);

  if (result.type === "cancel" || result.type === "dismiss") {
    return null;
  }

  if (result.type !== "success") {
    const error = result.error?.error || result.error?.message || result.errorCode || "google_auth_not_completed";
    throw new Error(String(error));
  }

  const code = result.params?.code;
  if (!code) {
    throw new Error("google_authorization_code_missing");
  }

  const token = await AuthSession.exchangeCodeAsync(
    {
      clientId,
      code,
      redirectUri,
      extraParams: {
        code_verifier: request.codeVerifier,
      },
    },
    discovery
  );

  if (!token?.accessToken) {
    throw new Error("google_access_token_missing");
  }

  return {
    accessToken: token.accessToken,
    idToken: token.idToken || null,
  };
}
