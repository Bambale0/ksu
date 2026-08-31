"use client";

import { type ReactNode, useEffect, useState } from "react";
import { clearBrowserInitData, getBrowserInitData } from "@/lib/browser-auth-session";
import { getInitDataFallback, initTelegram } from "@/lib/telegram";
import { TelegramBrowserLogin } from "./telegram-browser-login";

async function validateInitData(initData: string): Promise<boolean> {
  try {
    const response = await fetch("/api/v1/me", {
      method: "GET",
      cache: "no-store",
      headers: { "X-Telegram-Init-Data": initData },
    });
    return response.ok;
  } catch {
    return false;
  }
}

export function TelegramAuthBoundary({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    let active = true;
    const tg = initTelegram();
    tg?.ready?.();
    tg?.expand?.();

    const run = async () => {
      const nativeInitData = getInitDataFallback();
      if (nativeInitData) {
        // Native Telegram already enters the existing signed WebApp auth contour.
        // Do not add an eager /me probe here: it would become the first app API
        // request and bypass the shared launch/start-param headers used by routing.
        if (active) {
          setAuthenticated(true);
          setReady(true);
        }
        return;
      }

      const browserInitData = getBrowserInitData();
      if (!browserInitData) {
        if (active) setReady(true);
        return;
      }

      if (tg) {
        // Browser login issues standard WebApp initData. Hydrate only the SDK
        // facade in memory so every existing API client keeps one auth contour.
        tg.initData = browserInitData;
      }

      const valid = await validateInitData(browserInitData);
      if (!active) return;

      if (valid) {
        setAuthenticated(true);
      } else {
        // A stale/expired browser session must not admit the user into an app
        // where every API call will fail with 401.
        clearBrowserInitData();
        if (tg) tg.initData = "";
        setAuthenticated(false);
      }
      setReady(true);
    };

    void run();
    return () => { active = false; };
  }, []);

  if (!ready) {
    return <div className="splash" role="status"><strong>ROXY</strong><small>Открываю ROXY…</small></div>;
  }
  if (!authenticated) return <TelegramBrowserLogin />;
  return <>{children}</>;
}
