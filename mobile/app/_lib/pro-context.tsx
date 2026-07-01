import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Alert } from "react-native";




type Ctx = {
  isPro: boolean;
  products: { id: string; title: string; price: string }[];
  buyPro: () => Promise<void>;
  restorePurchases: () => Promise<void>;
  setProDevOnly: (v: boolean) => Promise<void>; 
};

const ProCtx = createContext<Ctx>({
  isPro: false,
  products: [],
  buyPro: async () => {},
  restorePurchases: async () => {},
  setProDevOnly: async () => {}
});

export function ProProvider({ children }: { children: React.ReactNode }) {
  const [isPro, setIsPro] = useState(false);
  const [products, setProducts] = useState<{ id: string; title: string; price: string }[]>([]);

  useEffect(() => {
    (async () => {
      const cached = await AsyncStorage.getItem(K.PRO);
      setIsPro(cached === "1");

      try {
        await initIAP();
        const list = await getProducts();
        setProducts((list || []).map(p => ({ id: p.productId, title: p.title ?? "PRO", price: p.price ?? "" })));
      } catch (e) {
        // noop
      }
    })();

    return () => { endIAP(); };
  }, []);

  const buyPro = useCallback(async () => {
    try {
      const sku = ANDROID_SKUS[0];
      await buy(sku);
      
      const ok = await restoreAndValidate();
      if (ok) {
        await AsyncStorage.setItem(K.PRO, "1");
        setIsPro(true);
        showAppAlert("","PRO активирован.");
      } else {
        showAppAlert("","");
      }
    } catch (e) {
      showAppAlert("","");
    }
  }, []);

  const restorePurchases = useCallback(async () => {
    try {
      const ok = await restoreAndValidate();
      await AsyncStorage.setItem(K.PRO, ok ? "1" : "0");
      setIsPro(ok);
      showAppAlert("",ok ? "" : "");
    } catch {
      showAppAlert("","");
    }
  }, []);

  const setProDevOnly = useCallback(async (v: boolean) => {
    await AsyncStorage.setItem(K.PRO, v ? "1" : "0");
    setIsPro(v);
  }, []);

  return (
    <ProCtx.Provider value={{ isPro, products, buyPro, restorePurchases, setProDevOnly }}>
      {children}
    </ProCtx.Provider>
  );
}

export function usePro() { return useContext(ProCtx); }








