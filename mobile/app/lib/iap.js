import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  fetchProducts,
  finishTransaction,
  getAvailablePurchases,
  initConnection,
  purchaseErrorListener,
  purchaseUpdatedListener,
  requestPurchase,
} from "react-native-iap";
import { logEvent } from "./analytics";

const BACKEND = "https://noytrix.com";
const PACKAGE_NAME = "com.noytrix.app";
const INSTALL_UID_KEY = "noytrix.installUserId";

const PRODUCT_IDS = {
  proSubscription: "pro_access",
  proLifetime: "prolifetime",
  bot: "pro_ai_bot",
};

const PRODUCT_TYPES = {
  [PRODUCT_IDS.proSubscription]: "subs",
  [PRODUCT_IDS.proLifetime]: "inapp",
  [PRODUCT_IDS.bot]: "inapp",
};

const PLAN_PRODUCT = {
  m: PRODUCT_IDS.proSubscription,
  h: PRODUCT_IDS.proSubscription,
  l: PRODUCT_IDS.proSubscription,
  bot: PRODUCT_IDS.bot,
  lifetime: PRODUCT_IDS.proLifetime,
};

let iapConfigured = false;
let cachedProducts = { products: [], subs: [] };
let updateSub = null;
let errorSub = null;
let pendingPurchase = null;

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

async function persistPro(active, meta = {}) {
  if (!active) return;
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
  await AsyncStorage.setItem(
    "iap.lastGooglePlayVerify",
    JSON.stringify({ ...meta, active: true, updatedAt: Date.now() })
  );
}

function productIdOf(purchase) {
  return String(purchase?.productId || purchase?.id || "").trim();
}

function purchaseTokenOf(purchase) {
  return String(purchase?.purchaseToken || purchase?.purchaseTokenAndroid || "").trim();
}

function normalizePurchaseResult(result) {
  if (Array.isArray(result)) return result.find((p) => purchaseTokenOf(p)) || result[0] || null;
  return result || null;
}

function isProProduct(productId) {
  return productId === PRODUCT_IDS.proSubscription || productId === PRODUCT_IDS.proLifetime;
}

function entitlementFromProduct(productId) {
  return {
    proMonthly: isProProduct(productId),
    pro6m: isProProduct(productId),
    proYearly: isProProduct(productId),
    bot: productId === PRODUCT_IDS.bot,
  };
}

function chooseSubscriptionOffer(product, planId) {
  const offers = product?.subscriptionOfferDetailsAndroid || [];
  if (!offers.length) return null;

  const patterns =
    planId === "l"
      ? ["year", "annual", "12", "1y"]
      : planId === "h"
        ? ["6", "half", "six"]
        : ["month", "monthly", "1m"];

  return (
    offers.find((offer) => {
      const haystack = [
        offer?.basePlanId,
        offer?.offerId,
        ...(Array.isArray(offer?.offerTags) ? offer.offerTags : []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return patterns.some((p) => haystack.includes(p));
    }) ||
    offers[0] ||
    null
  );
}

async function serverStatus() {
  const userId = await getRevenueCatAppUserId();
  const response = await fetch(`${BACKEND}/iap/guest/status?userId=${encodeURIComponent(userId)}`, {
    headers: { "X-User-Id": userId },
  });
  return response.json().catch(() => null);
}

async function verifyPurchaseOnServer(purchase, forcedProductId = null) {
  const userId = await getRevenueCatAppUserId();
  const productId = forcedProductId || productIdOf(purchase);
  const purchaseToken = purchaseTokenOf(purchase);
  const productType = PRODUCT_TYPES[productId] || "inapp";

  if (!productId || !purchaseToken) {
    throw new Error("Google Play purchase token is missing. Try restore purchase.");
  }

  const response = await fetch(`${BACKEND}/iap/google/guest/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": userId,
    },
    body: JSON.stringify({
      userId,
      packageName: PACKAGE_NAME,
      productType,
      productId,
      purchaseToken,
    }),
  });

  const body = await response.json().catch(() => null);
  if (!response.ok || !body?.ok) {
    const detail = body?.detail || body?.message || `Google Play verify failed (${response.status})`;
    throw new Error(String(detail));
  }

  if (body.active || body.googleActive) {
    await persistPro(true, { productId, productType, orderId: body.orderId, source: "google_play" });
  }

  return { ...entitlementFromProduct(productId), active: !!(body.active || body.googleActive), server: body };
}

function attachListeners() {
  if (updateSub || errorSub) return;

  updateSub = purchaseUpdatedListener(async (purchase) => {
    try {
      if (pendingPurchase?.resolve) {
        pendingPurchase.resolve(purchase);
        pendingPurchase = null;
      }
    } catch (e) {
      console.log("[IAP] purchaseUpdatedListener error:", e);
    }
  });

  errorSub = purchaseErrorListener((error) => {
    console.log("[IAP] purchase error:", error);
    if (pendingPurchase?.reject) {
      pendingPurchase.reject(error);
      pendingPurchase = null;
    }
  });
}

export async function iapInit() {
  try {
    if (Platform.OS !== "android") {
      console.log("[IAP] iapInit: non-android, skip");
      return false;
    }
    if (!iapConfigured) {
      await initConnection();
      iapConfigured = true;
    }
    attachListeners();
    return true;
  } catch (e) {
    console.log("[IAP] iapInit error:", e);
    return false;
  }
}

async function ensureInit() {
  const ok = await iapInit();
  if (!ok) throw new Error("Google Play Billing is not available on this device.");
}

export async function loadIap() {
  try {
    await ensureInit();
    const [subs, products] = await Promise.all([
      fetchProducts({ skus: [PRODUCT_IDS.proSubscription], type: "subs" }).catch((e) => {
        console.log("[IAP] fetch subs error:", e);
        return [];
      }),
      fetchProducts({ skus: [PRODUCT_IDS.proLifetime, PRODUCT_IDS.bot], type: "in-app" }).catch((e) => {
        console.log("[IAP] fetch products error:", e);
        return [];
      }),
    ]);

    cachedProducts = { products: products || [], subs: subs || [] };
    console.log("[IAP] loadIap:", {
      products: cachedProducts.products.map((p) => p.id || p.productId),
      subs: cachedProducts.subs.map((p) => p.id || p.productId),
    });
    return cachedProducts;
  } catch (e) {
    console.log("[IAP] loadIap error:", e);
    return { products: [], subs: [] };
  }
}

async function waitForPurchaseResult(result) {
  const immediate = normalizePurchaseResult(result);
  if (immediate && purchaseTokenOf(immediate)) return immediate;

  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      if (pendingPurchase?.reject === reject) pendingPurchase = null;
      reject(new Error("Google Play did not return a purchase yet. If payment completed, tap Restore purchase."));
    }, 90000);
    pendingPurchase = {
      resolve: (purchase) => {
        clearTimeout(timeout);
        resolve(purchase);
      },
      reject: (error) => {
        clearTimeout(timeout);
        reject(error);
      },
    };
  });
}

async function buyProduct(productId, planId = "m") {
  await ensureInit();
  if (!cachedProducts.subs.length && !cachedProducts.products.length) {
    await loadIap();
  }

  const productType = PRODUCT_TYPES[productId] || "inapp";
  const isSub = productType === "subs";
  const product = isSub
    ? cachedProducts.subs.find((p) => (p.id || p.productId) === productId)
    : cachedProducts.products.find((p) => (p.id || p.productId) === productId);

  logEvent("google_play_purchase_start", { product_id: productId, product_type: productType, plan: planId });

  const userId = await getRevenueCatAppUserId();
  const request =
    isSub
      ? {
          type: "subs",
          request: {
            android: {
              skus: [productId],
              obfuscatedAccountIdAndroid: userId,
              subscriptionOffers: chooseSubscriptionOffer(product, planId)
                ? [{ sku: productId, offerToken: chooseSubscriptionOffer(product, planId).offerToken }]
                : undefined,
            },
          },
        }
      : {
          type: "in-app",
          request: {
            android: {
              skus: [productId],
              obfuscatedAccountIdAndroid: userId,
            },
          },
        };

  const result = await requestPurchase(request);
  const purchase = await waitForPurchaseResult(result);
  const verified = await verifyPurchaseOnServer(purchase, productId);

  if (verified.active) {
    await finishTransaction({ purchase, isConsumable: false }).catch((e) => {
      console.log("[IAP] finishTransaction error:", e);
    });
  }

  logEvent("google_play_purchase_verified", { product_id: productId, product_type: productType, active: !!verified.active });
  return verified;
}

export async function buyProYearly() {
  return buyProduct(PLAN_PRODUCT.l, "l");
}

export async function buyProMonthly() {
  return buyProduct(PLAN_PRODUCT.m, "m");
}

export async function buyPro6month() {
  return buyProduct(PLAN_PRODUCT.h, "h");
}

export async function buyBot() {
  return buyProduct(PLAN_PRODUCT.bot, "bot");
}

export async function restorePurchases() {
  try {
    await ensureInit();
    logEvent("google_play_restore_start", {});
    const purchases = await getAvailablePurchases();
    let merged = { proMonthly: false, pro6m: false, proYearly: false, bot: false };

    for (const purchase of purchases || []) {
      const productId = productIdOf(purchase);
      if (!PRODUCT_TYPES[productId]) continue;
      try {
        const verified = await verifyPurchaseOnServer(purchase, productId);
        if (verified.active) {
          merged = {
            proMonthly: merged.proMonthly || verified.proMonthly,
            pro6m: merged.pro6m || verified.pro6m,
            proYearly: merged.proYearly || verified.proYearly,
            bot: merged.bot || verified.bot,
          };
          await finishTransaction({ purchase, isConsumable: false }).catch((e) => {
            console.log("[IAP] finish restored transaction error:", e);
          });
        }
      } catch (e) {
        console.log("[IAP] restore verify error:", e);
      }
    }

    const status = await serverStatus().catch(() => null);
    if (status?.active) {
      await persistPro(true, { source: "google_play_restore_server_status" });
      merged = { ...merged, proMonthly: true, pro6m: true, proYearly: true };
    }

    logEvent("google_play_restore_success", merged);
    return merged;
  } catch (e) {
    console.log("[IAP] restorePurchases error:", e);
    logEvent("google_play_restore_error", { err: String(e?.message || e || "error") });
    return { proMonthly: false, pro6m: false, proYearly: false, bot: false };
  }
}

export async function checkEntitlements() {
  try {
    const status = await serverStatus().catch(() => null);
    if (status?.active) {
      await persistPro(true, { source: "server_status" });
      return { proMonthly: true, pro6m: true, proYearly: true, bot: false };
    }

    const restored = await restorePurchases();
    if (restored.proMonthly || restored.pro6m || restored.proYearly || restored.bot) {
      return restored;
    }
  } catch (e) {
    console.log("[IAP] checkEntitlements error:", e);
  }

  return { proMonthly: false, pro6m: false, proYearly: false, bot: false };
}
