"use client";

import { type ReactNode, useEffect, useState } from "react";
import { clearBrowserInitData, getBrowserInitData } from "@/lib/browser-auth-session";
import { getInitDataFallback, initTelegram, type TelegramWebApp } from "@/lib/telegram";


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

function installBrowserInitDataFacade(browserInitData: string): () => void {
  if (typeof window === "undefined") return () => undefined;
  const namespace = window.Telegram;
  const current = namespace?.WebApp;
  if (!namespace || !current) return () => undefined;

  const facade = new Proxy(current, {
    get(target, property) {
      if (property === "initData") return browserInitData;
      const value = Reflect.get(target, property, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
  }) as TelegramWebApp;

  try {
    namespace.WebApp = facade;
  } catch {
    return () => undefined;
  }

  return () => {
    try {
      if (namespace.WebApp === facade) namespace.WebApp = current;
    } catch {
      // Browser auth remains server-validated even if the SDK namespace is immutable.
    }
  };
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

      // The canonical cookie-backed web account takes precedence over a legacy
      // browser Telegram credential saved in sessionStorage. Otherwise an old
      // credential could silently open a different wallet after email/Yandex login.
      try {
        const response = await fetch("/api/v1/web-auth/me", {
          credentials: "same-origin", cache: "no-store",
        });
        const payload = response.ok ? await response.json() : null;
        if (!active) return;
        const webValid = payload?.authenticated === true;
        window.__ROXY_WEB_SESSION_AUTHENTICATED__ = webValid;
        if (webValid) {
          setAuthenticated(true);
          setReady(true);
          return;
        }
      } catch {
        // Temporary API failure must not disable the existing verified Telegram
        // browser login. That credential is separately checked by /api/v1/me.
      }

      const browserInitData = getBrowserInitData();
      if (!browserInitData) {
        if (active) setReady(true);
        return;
      }

      // Telegram.WebApp.initData is read-only in the real SDK. Keep the SDK object
      // untouched and expose the server-issued browser credential through a small
      // in-memory facade so existing API clients keep using the same auth contour.
      const restoreFacade = installBrowserInitDataFacade(browserInitData);
      const valid = await validateInitData(browserInitData);
      if (!active) {
        restoreFacade();
        return;
      }

      if (valid) {
        setAuthenticated(true);
      } else {
        // A stale/expired browser session must not admit the user into an app
        // where every API call will fail with 401.
        clearBrowserInitData();
        restoreFacade();
        try {
          const response = await fetch("/api/v1/web-auth/me", {
            credentials: "same-origin", cache: "no-store",
          });
          const payload = response.ok ? await response.json() : null;
          const webValid = payload?.authenticated === true;
          window.__ROXY_WEB_SESSION_AUTHENTICATED__ = webValid;
          setAuthenticated(webValid);
        } catch {
          setAuthenticated(false);
        }
      }
      setReady(true);
    };

    void run();
    return () => { active = false; };
  }, []);

  if (!ready) {
    return <div className="splash" role="status"><strong>ROXY</strong><small>Открываю ROXY…</small></div>;
  }
  if (!authenticated) return (
    <main className="splash" aria-label="Вход в ROXY AI STUDIO">
      <strong>ROXY AI STUDIO</strong>
      <p>Войди через почту, Telegram или Яндекс ID, чтобы открыть приложение.</p>
      <a className="primary" href={"/login" + (typeof window !== "undefined" ? window.location.search : "")}>
        Войти в аккаунт
      </a>
    </main>
  );
  return <>{children}</>;
}
