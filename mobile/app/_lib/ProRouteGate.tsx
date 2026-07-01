import React, { useEffect } from "react";
import { usePathname, useRouter } from "expo-router";
import { usePro } from "./pro-context";
import routes from "./pro-routes.json";


export default function ProRouteGate() {
  const pathname = usePathname();
  const router = useRouter();
  const { isPro } = usePro();

  useEffect(() => {
    if (!pathname) return;
    const clean = pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
    const requiresPro = (routes as string[]).some(p => p === clean || clean.startsWith(p + "/"));
    if (requiresPro && !isPro && clean !== "/pro/paywall") {
      router.replace("/pro/paywall");
    }
  }, [pathname, isPro]);

  return null;
}





