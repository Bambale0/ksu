"use client";

import { type ReactNode, useEffect, useState } from "react";
import { getInitDataFallback, initTelegram } from "@/lib/telegram";
import { TelegramBrowserLogin } from "./telegram-browser-login";

export function TelegramAuthBoundary({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    const tg = initTelegram();
    tg?.ready?.();
    tg?.expand?.();
    setAuthenticated(Boolean(getInitDataFallback()));
    setReady(true);
  }, []);

  if (!ready) {
    return <div className="splash" role="status"><strong>ROXY</strong><small>Открываю ROXY…</small></div>;
  }
  if (!authenticated) return <TelegramBrowserLogin />;
  return <>{children}</>;
}
