import { create } from "zustand";

import { BACKEND } from "./backend";
import { identityHeaders } from "./identity";
import { FREE_DAILY_LIMIT, normalizeFreeQuota } from "./quota";

const INITIAL_QUOTA = { used: 0, limit: FREE_DAILY_LIMIT, left: FREE_DAILY_LIMIT, dayKey: "" };

function normalizeServerQuota(payload) {
  if (payload?.isPro === true) {
    return { isPro: true, quota: INITIAL_QUOTA };
  }
  return { isPro: false, quota: normalizeFreeQuota(payload, FREE_DAILY_LIMIT) };
}

// There is one quota source for Home and ScamShield. The server owns the
// counter; this store only mirrors the latest server response for the UI.
export const useScanQuotaStore = create((set, get) => ({
  quota: INITIAL_QUOTA,
  serverSaysPro: false,
  loading: false,

  applyServerQuota: (payload) => {
    const next = normalizeServerQuota(payload);
    set({ quota: next.quota, serverSaysPro: next.isPro });
    return next;
  },

  reset: () => set({ quota: INITIAL_QUOTA, serverSaysPro: false, loading: false }),

  refresh: async ({ userId = "anonymous", accessToken = "", lang = "en" } = {}) => {
    set({ loading: true });
    try {
      const headers = {
        ...(await identityHeaders()),
        "Accept-Language": lang,
        "X-Lang": lang,
        "X-Language": lang,
        "X-User-Id": userId || "anonymous",
      };
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

      const response = await fetch(
        `${BACKEND}/quota/status?feature=scan&userId=${encodeURIComponent(userId || "anonymous")}`,
        { headers },
      );
      if (!response.ok) throw new Error(`quota_status_${response.status}`);
      const payload = await response.json();
      return get().applyServerQuota(payload);
    } finally {
      set({ loading: false });
    }
  },
}));
