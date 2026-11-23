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
    const currentInitData = getInitDataFallback();
    const nativeUser = Boolean(window.Telegram?.WebApp?.initDataUnsafe?.user);
    // Main App installs the saved browser credential via an SDK facade.
    // Standalone /account does not have that boundary and may have no SDK
    // initData at all. In both cases, never expose logout for native Telegram.
    setIsBrowserSession(Boolean(browserCredential)
      && !nativeUser
      && (!currentInitData || currentInitData === browserCredential));
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
