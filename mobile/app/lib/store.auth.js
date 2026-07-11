// app/lib/store.auth.js
import { create } from "zustand";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  getAuthState,
  login as apiLogin,
  registerStart as apiRegisterStart,
  registerVerify as apiRegisterVerify,
  resetStart as apiResetStart,
  resetConfirm as apiResetConfirm,
  clearAuth as apiClearAuth,
  me as apiMe,
} from "./authApi";
import { identifyTikTokUser, logEvent, logoutTikTokUser } from "./analytics";

function enhanceUser(user) {
  if (!user) return null;
  const email = user.email || user.username || "";
  const fallback = email ? email.split("@")[0] : "User";
  return {
    ...user,
    displayName: user.displayName || user.name || fallback,
  };
}

const AVATAR_KEY = "avatar_uri_v1";

export const useAuthStore = create((set, get) => ({
  user: null,
  isAuth: false,
  isReady: false,
  avatarUri: null,

  init: async () => {
    try {
      const [state, avatarUri] = await Promise.all([
        getAuthState(), // { user, access_token, refresh_token }
        AsyncStorage.getItem(AVATAR_KEY),
      ]);

      let user = state?.user ? enhanceUser(state.user) : null;
      const isAuth = !!state?.access_token;

      if (isAuth && !user) {
        try {
          const profile = await apiMe(); 
          if (profile) user = enhanceUser(profile);
        } catch {}
      }

      set({
        user,
        isAuth,
        isReady: true,
        avatarUri: avatarUri || null,
      });
      if (isAuth && user) {
        await identifyTikTokUser(user);
        await logEvent("auth_identify", { email: user.email || "", source: "app_reopen" });
      }
    } catch {
      set({ user: null, isAuth: false, isReady: true, avatarUri: null });
    }
  },

  setAuth: async (user, tokens) => {
    const enhanced = enhanceUser(user);
    set({ user: enhanced, isAuth: !!tokens || !!enhanced });
  },

  login: async ({ email, password }) => {
    await apiLogin({ email, password }); 
    await get().init();
    const user = get().user;
    await identifyTikTokUser(user || { email });
    await logEvent("login_success", { email: user?.email || email || "" });
    return get().user;
  },

  registerStart: async (payload) => apiRegisterStart(payload),

  registerVerify: async (payload) => {
    await apiRegisterVerify(payload); 
    await get().init();
    const user = get().user;
    await identifyTikTokUser(user || { email: payload?.email, nick: payload?.nick });
    await logEvent("registration_success", { email: user?.email || payload?.email || "" });
    return get().user;
  },

  resetStart: async (payload) => apiResetStart(payload),
  resetConfirm: async (payload) => apiResetConfirm(payload),

  refreshMe: async () => {
    const profile = await apiMe();
    const user = profile ? enhanceUser(profile) : null;
    if (user) set({ user, isAuth: true });
    return user;
  },

  logout: async () => {
    await logoutTikTokUser();
    await apiClearAuth(); 
    await AsyncStorage.multiRemove([AVATAR_KEY]);
    set({ user: null, isAuth: false, avatarUri: null });
  },

  setUser: (u) => set({ user: enhanceUser(u) }),
  setIsAuth: (v) => set({ isAuth: !!v }),

  setAvatarUri: async (uri) => {
    set({ avatarUri: uri || null });
    try {
      if (uri) await AsyncStorage.setItem(AVATAR_KEY, uri);
      else await AsyncStorage.removeItem(AVATAR_KEY);
    } catch {}
  },
}));




