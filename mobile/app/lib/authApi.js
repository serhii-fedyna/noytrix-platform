// app/lib/authApi.js
import AsyncStorage from "@react-native-async-storage/async-storage";
import { BACKEND, API as API_BASE } from "./backend";
import { identityHeaders, identifyUser } from "./identity";

const AUTH_KEY = "auth_state_v1";


const API = {
  ...API_BASE,
  me: `${BACKEND}/auth/me`,
  accountProStatus: `${BACKEND}/iap/account-status`,
};

// ================== helpers ==================

function withQuery(url, params = {}) {
  const usp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null) return;
    usp.set(k, String(v));
  });
  const qs = usp.toString();
  if (!qs) return url;
  return url + (url.includes("?") ? "&" : "?") + qs;
}

function firstToken(...values) {
  return values.find((value) => typeof value === "string" && value.trim()) || null;
}

function normalizeAuthState(value, fallback = {}) {
  const source = value && typeof value === "object" ? value : {};
  const secondary = fallback && typeof fallback === "object" ? fallback : {};
  const tokens = source.tokens && typeof source.tokens === "object" ? source.tokens : {};
  const fallbackTokens = secondary.tokens && typeof secondary.tokens === "object" ? secondary.tokens : {};

  return {
    user: source.user || source.profile || source.account || secondary.user || secondary.profile || secondary.account || null,
    access_token: firstToken(
      source.access_token, source.accessToken, source.access, source.token, source.jwt,
      tokens.access_token, tokens.accessToken, tokens.access, tokens.token, tokens.jwt,
      secondary.access_token, secondary.accessToken, secondary.access, secondary.token, secondary.jwt,
      fallbackTokens.access_token, fallbackTokens.accessToken, fallbackTokens.access, fallbackTokens.token, fallbackTokens.jwt
    ),
    refresh_token: firstToken(
      source.refresh_token, source.refreshToken, source.refresh,
      tokens.refresh_token, tokens.refreshToken, tokens.refresh,
      secondary.refresh_token, secondary.refreshToken, secondary.refresh,
      fallbackTokens.refresh_token, fallbackTokens.refreshToken, fallbackTokens.refresh
    ),
  };
}

async function saveAuthState(stateInput = {}) {
  const state = normalizeAuthState(stateInput);
  try {
    await AsyncStorage.setItem(AUTH_KEY, JSON.stringify(state));
  } catch {}
  return state;
}


async function migrateLegacyIfAny() {
  try {
    const [raw, uRaw, tRaw, nUser, nTok] = await Promise.all([
      AsyncStorage.getItem(AUTH_KEY),
      AsyncStorage.getItem("auth_user"),
      AsyncStorage.getItem("auth_tokens"),
      AsyncStorage.getItem("noytrix:user"),
      AsyncStorage.getItem("noytrix:tokens"),
    ]);

    const current = safeJson(raw) || {};
    const legacyUser = safeJson(uRaw) || safeJson(nUser) || null;
    const legacyTokens = safeJson(tRaw) || safeJson(nTok) || {};
    const state = normalizeAuthState(current, { user: legacyUser, ...legacyTokens });

    if (raw || legacyUser || Object.keys(legacyTokens).length) {
      await AsyncStorage.setItem(AUTH_KEY, JSON.stringify(state));
    }

    if (uRaw || tRaw || nUser || nTok) {
      await AsyncStorage.multiRemove([
        "auth_user",
        "auth_tokens",
        "noytrix:user",
        "noytrix:tokens",
      ]);
    }
    return state;
  } catch {}
  return null;
}

function safeJson(s) {
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}


export async function getAuthState() {
  const migrated = await migrateLegacyIfAny();
  if (migrated) return migrated;

  try {
    const raw = await AsyncStorage.getItem(AUTH_KEY);
    if (raw) return normalizeAuthState(safeJson(raw));
  } catch {}

  return { user: null, access_token: null, refresh_token: null };
}

export async function updateAuthUser(user) {
  const current = await getAuthState();
  return saveAuthState({
    ...current,
    user: user || null,
  });
}

export async function getAuthenticatedHeaders(extraHeaders = {}, tokenOverride = null) {
  const state = await getAuthState();
  const token = tokenOverride || state?.access_token || null;
  const idHeaders = await identityHeaders();

  return {
    ...idHeaders,
    ...extraHeaders,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export async function authenticatedFetch(url, options = {}) {
  const { headers: extraHeaders = {}, ...requestOptions } = options;
  const state = await getAuthState();

  async function request(token) {
    return fetch(url, {
      ...requestOptions,
      headers: await getAuthenticatedHeaders(extraHeaders, token),
    });
  }

  const response = await request(state?.access_token || null);
  if (response.status !== 401 || !state?.refresh_token) return response;

  try {
    const refreshed = await refreshAccessToken(state.refresh_token);
    const accessToken =
      refreshed?.access_token ||
      refreshed?.accessToken ||
      refreshed?.tokens?.access_token ||
      null;
    const refreshToken =
      refreshed?.refresh_token ||
      refreshed?.refreshToken ||
      refreshed?.tokens?.refresh_token ||
      state.refresh_token;

    if (!accessToken) return response;

    await saveAuthState({
      user: state?.user || null,
      access_token: accessToken,
      refresh_token: refreshToken,
    });
    return request(accessToken);
  } catch {
    return response;
  }
}


async function refreshAccessToken(refresh_token) {
  if (!refresh_token) throw new Error("No refresh token");

  const url = withQuery(API.tokenRefresh, { token: refresh_token });

  
  return await rawJsonFetch(url, { method: "POST" });
}

async function rawJsonFetch(url, { method = "GET", body, token } = {}) {
  const idHeaders = await identityHeaders();
  const res = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...idHeaders,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { message: text };
  }

  if (!res.ok) {
    const msg =
      data?.detail || data?.message || `HTTP ${res.status} ${res.statusText}`;
    const err = new Error(msg);
    err.status = res.status;
    err.data = data;
    throw err;
  }

  return data;
}

async function jsonFetch(url, { method = "GET", body, token, _retried } = {}) {
  try {
    return await rawJsonFetch(url, { method, body, token });
  } catch (e) {
    
    if (e?.status === 401 && !_retried) {
      const state = await getAuthState();
      const rt = state?.refresh_token || null;
      if (!rt) throw e;

      try {
        const refreshed = await refreshAccessToken(rt);

        const newAccess =
          refreshed?.access_token ||
          refreshed?.accessToken ||
          refreshed?.tokens?.access_token ||
          null;

        const newRefresh =
          refreshed?.refresh_token ||
          refreshed?.refreshToken ||
          refreshed?.tokens?.refresh_token ||
          rt;

        if (!newAccess) throw e;

        await saveAuthState({
          user: state?.user || null,
          access_token: newAccess,
          refresh_token: newRefresh,
        });

        
        return await rawJsonFetch(url, {
          method,
          body,
          token: newAccess,
        });
      } catch {
        throw e;
      }
    }

    throw e;
  }
}

// ================== API ==================

export async function login({ email, password }) {
  const data = await jsonFetch(API.login, {
    method: "POST",
    body: {
      email: String(email || "").trim().toLowerCase(),
      password,
    },
  });

  const user = data?.user || null;
  const access =
    data?.access_token || data?.accessToken || data?.tokens?.access_token || null;
  const refresh =
    data?.refresh_token ||
    data?.refreshToken ||
    data?.tokens?.refresh_token ||
    null;

  await saveAuthState({ user, access_token: access, refresh_token: refresh });
  await identifyUser({ email: user?.email || email, authUserId: user?.id });
  return data;
}

export async function loginGoogle({ accessToken }) {
  const token = String(accessToken || "").trim();
  if (!token) throw new Error("google_access_token_missing");

  const data = await jsonFetch(API.googleLogin, {
    method: "POST",
    body: { access_token: token },
  });

  const user = data?.user || null;
  const access =
    data?.access_token || data?.accessToken || data?.tokens?.access_token || null;
  const refresh =
    data?.refresh_token ||
    data?.refreshToken ||
    data?.tokens?.refresh_token ||
    null;

  await saveAuthState({ user, access_token: access, refresh_token: refresh });
  await identifyUser({ email: user?.email, authUserId: user?.id, google: true });
  return data;
}

export async function registerStart({ email, password, nick }) {
  const normalizedEmail = String(email || "").trim().toLowerCase();
  await identifyUser({ email: normalizedEmail });
  return jsonFetch(API.registerStart, {
    method: "POST",
    body: {
      email: normalizedEmail,
      password,
      nick: String(nick || "").trim(),
    },
  });
}

export async function registerVerify({ email, code, nick, password }) {
  const normalizedEmail = String(email || "").trim().toLowerCase();
  const normalizedCode = String(code || "").trim();

  
  
  const verifyData = await jsonFetch(API.registerVerify, {
    method: "POST",
    body: { email: normalizedEmail, code: normalizedCode },
  });

  const verifyUser = verifyData?.user || null;
  const verifyAccess =
    verifyData?.access_token ||
    verifyData?.accessToken ||
    verifyData?.tokens?.access_token ||
    null;
  const verifyRefresh =
    verifyData?.refresh_token ||
    verifyData?.refreshToken ||
    verifyData?.tokens?.refresh_token ||
    null;

  
  if (verifyUser && verifyAccess) {
    await saveAuthState({
      user: verifyUser,
      access_token: verifyAccess,
      refresh_token: verifyRefresh,
    });
    await identifyUser({ email: verifyUser?.email || normalizedEmail, authUserId: verifyUser?.id });

    
    
    if (nick && password) {
      try {
        const completeData = await jsonFetch(API.registerDone, {
          method: "POST",
          body: {
            email: normalizedEmail,
            nick: String(nick || "").trim(),
            password,
          },
        });

        const completeUser = completeData?.user || null;
        const completeAccess =
          completeData?.access_token ||
          completeData?.accessToken ||
          completeData?.tokens?.access_token ||
          null;
        const completeRefresh =
          completeData?.refresh_token ||
          completeData?.refreshToken ||
          completeData?.tokens?.refresh_token ||
          null;

        
        if (completeUser || completeAccess || completeRefresh) {
          await saveAuthState({
            user: completeUser || verifyUser,
            access_token: completeAccess || verifyAccess,
            refresh_token: completeRefresh || verifyRefresh,
          });
          await identifyUser({ email: (completeUser || verifyUser)?.email || normalizedEmail, authUserId: (completeUser || verifyUser)?.id });
          return completeData;
        }
      } catch {
        
      }
    }

    return verifyData;
  }

  
  
  const completeData = await jsonFetch(API.registerDone, {
    method: "POST",
    body: {
      email: normalizedEmail,
      nick: String(nick || "").trim(),
      password,
    },
  });

  const completeUser = completeData?.user || null;
  const completeAccess =
    completeData?.access_token ||
    completeData?.accessToken ||
    completeData?.tokens?.access_token ||
    null;
  const completeRefresh =
    completeData?.refresh_token ||
    completeData?.refreshToken ||
    completeData?.tokens?.refresh_token ||
    null;

  await saveAuthState({
    user: completeUser,
    access_token: completeAccess,
    refresh_token: completeRefresh,
  });
  await identifyUser({ email: completeUser?.email || normalizedEmail, authUserId: completeUser?.id });

  return completeData;
}

export async function resetStart({ email }) {
  return jsonFetch(API.resetStart, {
    method: "POST",
    body: { email: String(email || "").trim().toLowerCase() },
  });
}

export async function resetConfirm({ email, code, new_password }) {
  return jsonFetch(API.resetConfirm, {
    method: "POST",
    body: {
      email: String(email || "").trim().toLowerCase(),
      code: String(code || "").trim(),
      new_password,
    },
  });
}

export async function clearAuth() {
  try {
    await AsyncStorage.multiRemove([
      AUTH_KEY,
      
      "auth_user",
      "auth_tokens",
      "noytrix:user",
      "noytrix:tokens",
      "avatar_uri_v1",
    ]);
  } catch {}
}

export async function me() {
  const state = await getAuthState();
  const token = state?.access_token || null;
  // A persisted refresh token is still a valid recoverable session. Let jsonFetch
  // refresh it after the first 401 instead of treating the user as logged out.
  if (!token && !state?.refresh_token) return null;

  try {
    const profile = await jsonFetch(API.me, { method: "GET", token });
    if (profile) await updateAuthUser(profile);
    return profile;
  } catch (e) {
    console.log("[authApi.me] error:", e?.message || e);
    return null;
  }
}


export async function authLogin(payload) {
  return login(payload);
}

export async function accountProStatus() {
  const state = await getAuthState();
  const token = state?.access_token || null;
  if (!token) {
    return { ok: true, active: false, isPro: false, plan: "FREE" };
  }

  return jsonFetch(API.accountProStatus, { method: "GET", token });
}
export async function authGoogleLogin(payload) {
  return loginGoogle(payload);
}
export async function authRegisterStart(payload) {
  return registerStart(payload);
}
export async function authRegisterVerify(payload) {
  return registerVerify(payload);
}
export async function authResetStart(payload) {
  return resetStart(payload);
}
export async function authResetConfirm(payload) {
  return resetConfirm(payload);
}




