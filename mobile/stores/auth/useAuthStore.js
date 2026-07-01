// stores/auth/useAuthStore.js
import { create } from "zustand";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Constants from "expo-constants";


const AUTH_API =
  Constants?.expoConfig?.extra?.EXPO_PUBLIC_AUTH_API ||
  "http://157.173.118.5:8010";


async function api(path, { method = "GET", body, token } = {}) {
  const res = await fetch(`${AUTH_API}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const txt = await res.text();
  let data;
  try { data = txt ? JSON.parse(txt) : {}; } catch { data = { message: txt }; }
  if (!res.ok) {
    const msg =
      data?.detail || data?.message || `HTTP ${res.status} ${res.statusText}`;
    throw new Error(msg);
  }
  return data;
}


function pickTokens(bundle) {
  if (!bundle) return { access: null, refresh: null };
  
  if (bundle.accessToken || bundle.refreshToken) {
    return { access: bundle.accessToken || null, refresh: bundle.refreshToken || null };
  }
  const t = bundle.tokens || {};
  return { access: t.access_token || null, refresh: t.refresh_token || null };
}

export const useAuthStore = create((set, get) => ({
  isAuth: false,
  user: null,
  access: null,
  refresh: null,

  
  hydrate: async () => {
    try {
      const raw = await AsyncStorage.getItem("noytrix:auth");
      if (!raw) return;
      const { user, access, refresh } = JSON.parse(raw);
      set({ user: user || null, access: access || null, refresh: refresh || null, isAuth: !!user });
    } catch {}
  },

  
  persistAuth: async () => {
    const { user, access, refresh } = get();
    try {
      await AsyncStorage.setItem(
        "noytrix:auth",
        JSON.stringify({ user, access, refresh })
      );
    } catch {}
  },

  
  setAuthBundle: async (bundle) => {
    const user = bundle?.user || null;
    const { access, refresh } = pickTokens(bundle);
    set({ user, access, refresh, isAuth: !!user });
    await get().persistAuth();
  },

  
  refreshAccess: async () => {
    const { refresh } = get();
    if (!refresh) return;
    const j = await api("/auth/token/refresh", {
      method: "POST",
      body: { refreshToken: refresh }, 
    });
    const { access, refresh: newRef } = pickTokens(j);
    set({ access: access || null, refresh: newRef || refresh });
    await get().persistAuth();
  },

  
  signOut: async () => {
    set({ isAuth: false, user: null, access: null, refresh: null });
    try {
      await AsyncStorage.multiRemove(["noytrix:auth", "noytrix:user", "noytrix:token", "noytrix:refresh"]);
    } catch {}
  },

  
  registerStart: async ({ email, password, nick }) => {
    return api("/auth/register/start", {
      method: "POST",
      body: { email, password, nick },
    });
  },

  registerVerify: async ({ email, code }) => {
    
    return api("/auth/register/verify", {
      method: "POST",
      body: { email, code },
    });
  },

  registerComplete: async ({ email, nick, password }) => {
    
    const bundle = await api("/auth/register/complete", {
      method: "POST",
      body: { email, nick, password },
    });
    await get().setAuthBundle(bundle);
    return bundle;
  },

  
  loginEmail: async ({ email, password }) => {
    const bundle = await api("/auth/login", {
      method: "POST",
      body: { email, password },
    });
    await get().setAuthBundle(bundle);
    return bundle;
  },

  
  loginGoogle: async ({ access_token }) => {
    const bundle = await api("/auth/google", {
      method: "POST",
      body: { access_token },
    });
    await get().setAuthBundle(bundle);
    return bundle;
  },

  
  resetStart: async ({ email }) => {
    return api("/auth/reset/start", {
      method: "POST",
      body: { email },
    });
  },

  resetConfirm: async ({ email, code, new_password }) => {
    return api("/auth/reset/confirm", {
      method: "POST",
      body: { email, code, newPassword: new_password },
    });
  },
}));





