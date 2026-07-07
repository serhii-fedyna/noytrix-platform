import { Platform } from "react-native";
import Purchases from "react-native-purchases";
import Constants from "expo-constants";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { logEvent } from "./analytics";



const PKG_BOT = "bot_access";
const PKG_PRO_6M = "$rc_six_month";
const PKG_PRO_MONTH = "$rc_monthly";
const PKG_PRO_YEARLY = "$rc_annual";
const INSTALL_UID_KEY = "noytrix.installUserId";

let rcConfigured = false;

function getRcApiKey() {
  const extra = Constants.expoConfig?.extra || Constants.manifest?.extra || {};
  return extra.RC_ANDROID_API_KEY;
}

function makeRandomId() {
  return `guest_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

export async function getRevenueCatAppUserId() {
  try {
    const existing = await AsyncStorage.getItem(INSTALL_UID_KEY);
    if (existing && String(existing).trim()) return String(existing).trim();

    const next = makeRandomId();
    await AsyncStorage.setItem(INSTALL_UID_KEY, next);
    return next;
  } catch {
    return makeRandomId();
  }
}



export async function iapInit() {
  try {
    if (rcConfigured) return true;

    const apiKey = getRcApiKey();

    if (!apiKey) {
      console.log("[RC] No RC_ANDROID_API_KEY in extra");
      return false;
    }

    if (Platform.OS !== "android") {
      console.log("[RC] iapInit: non-android, skip");
      return false;
    }

    console.log("[RC] configure Purchases with key =", apiKey.slice(0, 10) + "...");
    const appUserID = await getRevenueCatAppUserId();
    await Purchases.configure({ apiKey, appUserID });

    rcConfigured = true;
    console.log("[RC] Purchases configured OK", { appUserID });
    return true;
  } catch (e) {
    console.log("[RC] iapInit error:", e);
    return false;
  }
}

async function ensureInit() {
  if (!rcConfigured) {
    await iapInit();
  }
}



async function persistEntitlements(info) {
  try {
    const active = info?.entitlements?.active || {};
    const hasPro = !!active.pro;
    const hasBot = !!active.bot;

    if (hasPro) {
      await AsyncStorage.setItem("isPro", "true");
      await AsyncStorage.setItem("noytrix.isPro", "true");
      await AsyncStorage.setItem("pro", "true");
      await AsyncStorage.setItem("proActive", "true");
      await AsyncStorage.setItem("subscription.pro", "true");
      await AsyncStorage.setItem("iap.isPro", "true");
      await AsyncStorage.setItem("entitlement.pro", "active");
      await AsyncStorage.setItem("entitlement.id", "pro");
      await AsyncStorage.setItem("entitlementId", "pro");
      await AsyncStorage.setItem("noytrix_pro_flag", "1");
    }

    await AsyncStorage.setItem("isBot", hasBot ? "true" : "false");
    await AsyncStorage.setItem("iap.isBot", hasBot ? "true" : "false");
    await AsyncStorage.setItem("entitlement.bot", hasBot ? "active" : "inactive");

    try {
      const debug = {
        hasPro,
        hasBot,
        updatedAt: Date.now(),
        appUserID: info?.originalAppUserId || info?.originalAppUserID || null,
        currentAppUserID: await getRevenueCatAppUserId(),
      };
      await AsyncStorage.setItem("iap.lastCustomerInfo", JSON.stringify(debug));
    } catch {}

    console.log("[RC] persistEntitlements OK:", { hasPro, hasBot });
  } catch (e) {
    console.log("[RC] persistEntitlements error:", e);
  }
}



async function getCurrentOffering() {
  await ensureInit();

  const offerings = await Purchases.getOfferings();
  const current = offerings.current;

  if (!current) {
    throw new Error("No current offering configured in RevenueCat");
  }

  return current;
}



export async function loadIap() {
  try {
    const offering = await getCurrentOffering();
    const available = offering.availablePackages || [];

    const products = [];
    const subs = [];

    available.forEach((pkg) => {
      const sp = pkg.storeProduct || {};

      const obj = {
        productId: sp.identifier,
        price: sp.price,
        localizedPrice: sp.priceString,
        currency: sp.currencyCode,
        rcPackageId: pkg.identifier,
      };

      if (pkg.identifier === PKG_PRO_YEARLY) {
        products.push(obj);
      } else {
        subs.push(obj);
      }
    });

    console.log(
      "[RC] loadIap products:",
      products.map((p) => p.productId)
    );
    console.log(
      "[RC] loadIap subs:",
      subs.map((s) => s.productId)
    );

    return { products, subs };
  } catch (e) {
    console.log("[RC] loadIap error:", e);
    return { products: [], subs: [] };
  }
}



async function buyPackageById(packageId) {
  try {
    const offering = await getCurrentOffering();
    const pkg = (offering.availablePackages || []).find(
      (p) => p.identifier === packageId
    );

    if (!pkg) {
      throw new Error("Package " + packageId + " not found in offering");
    }

    console.log("[RC] purchasePackage:", packageId);
    logEvent("rc_purchase_package_start", { package_id: packageId });
    const res = await Purchases.purchasePackage(pkg);
    console.log("[RC] purchase result:", res);
    logEvent("rc_purchase_package_success", { package_id: packageId });

    const info =
      res?.customerInfo ||
      res?.customerInfoResponse?.customerInfo ||
      res?.purchaserInfo ||
      null;

    if (info) {
      await persistEntitlements(info);
    } else {
      try {
        const ci = await Purchases.getCustomerInfo();
        await persistEntitlements(ci);
      } catch {}
    }

    return res;
  } catch (e) {
    console.log("[RC] purchase error for", packageId, e);
    logEvent("rc_purchase_package_error", { package_id: packageId, err: String(e?.message || e || "error") });
    throw e;
  }
}

// buy pro
export async function buyProYearly() {
  return buyPackageById(PKG_PRO_YEARLY);
}

export async function buyProMonthly() {
  return buyPackageById(PKG_PRO_MONTH);
}

export async function buyPro6month() {
  return buyPackageById(PKG_PRO_6M);
}

export async function buyBot() {
  return buyPackageById(PKG_BOT);
}



function mapCustomerInfoToEntitlements(info) {
  const active = info?.entitlements?.active || {};

  const hasPro = !!active.pro;
  const hasBot = !!active.bot;

  const ent = {
    proMonthly: hasPro,
    pro6m: hasPro,
    proYearly: hasPro,
    bot: hasBot,
  };

  console.log("[RC] mapped entitlements:", ent);
  return ent;
}

export async function restorePurchases() {
  try {
    await ensureInit();
    console.log("[RC] restorePurchases...");
    logEvent("rc_restore_start", {});
    const info = await Purchases.restorePurchases();

    await persistEntitlements(info);
    logEvent("rc_restore_success", {});
    return mapCustomerInfoToEntitlements(info);
  } catch (e) {
    console.log("[RC] restorePurchases error:", e);
    logEvent("rc_restore_error", { err: String(e?.message || e || "error") });

    return {
      proMonthly: false,
      pro6m: false,
      proYearly: false,
      bot: false,
    };
  }
}

export async function checkEntitlements() {
  try {
    await ensureInit();
    const info = await Purchases.getCustomerInfo();

    await persistEntitlements(info);
    return mapCustomerInfoToEntitlements(info);
  } catch (e) {
    console.log("[RC] checkEntitlements error:", e);
    return {
      proMonthly: false,
      pro6m: false,
      proYearly: false,
      bot: false,
    };
  }
}





