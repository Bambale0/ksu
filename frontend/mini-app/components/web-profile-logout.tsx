"use client";

import { useEffect, useState } from "react";

import { clearBrowserInitData, getBrowserInitData } from "@/lib/browser-auth-session";
import { getInitDataFallback } from "@/lib/telegram";

/**
 * The current public-web login stores a temporary Telegram-backed credential
 * in sessionStorage. Do not offer a website logout inside Telegram's native
 * Mini App, even when its WebView still contains an old browser credential.
 *
 * PR #645 introduces a different server-backed web cookie. Its future
 * sign-out implementation must replace this legacy-only action.
 */
export function WebProfileLogout() {
  const [isBrowserSession, setIsBrowserSession] = useState(false);

  useEffect(() => {
    const browserCredential = getBrowserInitData();
    // The website auth boundary installs this exact credential via its SDK
    // facade. A native Telegram launch has a different, signed initData.
    setIsBrowserSession(Boolean(browserCredential) && getInitDataFallback() === browserCredential);
  }, []);

  if (!isBrowserSession) return null;

  const signOut = () => {
    clearBrowserInitData();
    // A full navigation drops the temporary Telegram SDK facade and its
    // in-memory auth state. The existing /mini-app/ route is the login gate
    // until first-party /login (PR #645) becomes the production route.
    window.location.replace("/mini-app/");
  };

  return (
    <section className="web-profile-session panel" aria-label="Веб-сессия">
      <div className="web-profile-session-copy">
        <strong>Вход в веб-версию</strong>
        <p className="muted">Можно выйти из браузера, не выходя из Telegram.</p>
      </div>
      <button type="button" className="secondary web-profile-logout" onClick={signOut}>
        Выйти из аккаунта
      </button>
    </section>
  );
}
