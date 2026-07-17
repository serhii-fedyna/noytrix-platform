import AsyncStorage from "@react-native-async-storage/async-storage";
import { BACKEND } from "./backend";

export const INSTALL_UID_KEY = "noytrix.installUserId";
const IDENTITY_KEY = "noytrix.identityUserId";

function makeInstallId() {
  return `guest_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

export async function getInstallUserId() {
  try {
    const existing = await AsyncStorage.getItem(INSTALL_UID_KEY);
    if (existing && String(existing).trim()) return String(existing).trim();
    const next = makeInstallId();
    await AsyncStorage.setItem(INSTALL_UID_KEY, next);
    return next;
  } catch {
    return makeInstallId();
  }
}

export async function getIdentityUserId() {
  try {
    return (await AsyncStorage.getItem(IDENTITY_KEY)) || null;
  } catch {
    return null;
  }
}

export async function identityHeaders(extra = {}) {
  const installUserId = await getInstallUserId();
  const identityUserId = await getIdentityUserId();
  return {
    "X-Install-User-Id": installUserId,
    "X-Guest-Id": installUserId,
    "X-RevenueCat-App-User-Id": installUserId,
    ...(identityUserId ? { "X-Noytrix-User-Id": identityUserId } : {}),
    ...extra,
  };
}

export async function identifyUser(extra = {}) {
  const installUserId = await getInstallUserId();
  const payload = {
    installUserId,
    guestId: installUserId,
    revenueCatAppUserId: installUserId,
    ...extra,
  };

  const response = await fetch(`${BACKEND}/identity/identify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(await identityHeaders()),
    },
    body: JSON.stringify(payload),
  });

  const body = await response.json().catch(() => null);
  if (!response.ok || !body?.ok) return null;
  const userId = body.user_id || body.userId || null;
  if (userId) {
    await AsyncStorage.setItem(IDENTITY_KEY, String(userId));
  }
  return body;
}
