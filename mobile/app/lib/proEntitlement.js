import AsyncStorage from "@react-native-async-storage/async-storage";

// Legacy device-wide flags could leak one account's PRO state to another.
export const LEGACY_PRO_DEVICE_KEYS = [
  "isPro",
  "noytrix.isPro",
  "pro",
  "proActive",
  "subscription.pro",
  "iap.isPro",
  "iap.pro",
  "entitlement.pro",
  "entitlement.id",
  "entitlementId",
  "noytrix_pro_flag",
  "iap.activePlan",
];

export async function clearLegacyProDeviceFlags() {
  try {
    await AsyncStorage.multiRemove(LEGACY_PRO_DEVICE_KEYS);
  } catch {}
}

export function hasAccountProAccess(user) {
  return user?.proAccess?.isPro === true;
}
