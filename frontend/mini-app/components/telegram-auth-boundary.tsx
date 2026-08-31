"use client";

import { type ReactNode, useEffect, useState } from "react";
import { getBrowserInitData } from "@/lib/browser-auth-session";
import { getInitDataFallback, initTelegram } from "@/lib/telegram";
import { TelegramBrowserLogin } from "./telegram-browser-login";

export function TelegramAuthBoundary({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    const tg = initTelegram();
    tg?.ready?.();
    tg?.expand?.();

    const nativeInitData = getInitDataFallback();
    if (nativeInitData) {
      setAuthenticated(true);
      setReady(true);
      return;
    }

    const browserInitData = getBrowserInitData();
    if (browserInitData && tg) {
      // The backend already verified Telegram Login Widget HMAC before issuing
      // this standard WebApp initData. Hydrate only the in-memory SDK facade so
      // every existing ROXY API client continues through the same auth contour.
      tg.initData = browserInitData;
      setAuthenticated(true);
    }
    setReady(true);
  }, []);

  if (!ready) {
    return <div className="splash" role="status"><strong>ROXY</strong><small>Открываю ROXY…</small></div>;
  }
  if (!authenticated) return <TelegramBrowserLogin />;
  return <>{children}</>;
}
