"use client";

import { useEffect, useState } from "react";

import { clearBrowserInitData, getBrowserInitData } from "@/lib/browser-auth-session";
import { getInitDataFallback, isWebSessionAuthenticated } from "@/lib/telegram";

/**
 * Only the verified first-party browser session can be logged out here.
 * Native Telegram Mini App never gets a logout button: its signed WebView
 * session and Telegram account are managed by the messenger.
 */
export function WebProfileLogout() {
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  const [sessionKind, setSessionKind] = useState<"cookie" | "legacy" | null>(null);
  useEffect(() => {
    const browserCredential = getBrowserInitData();
    const currentInitData = getInitDataFallback();
    const nativeUser = Boolean(window.Telegram?.WebApp?.initDataUnsafe?.user);
    if (nativeUser || (currentInitData && currentInitData !== browserCredential)) return;
    if (isWebSessionAuthenticated()) setSessionKind("cookie");
    else if (browserCredential) setSessionKind("legacy");
  }, []);

  if (!sessionKind) return null;

  const logout = async () => {
    if (working) return;
    setWorking(true);
    setError("");
    try {
      if (sessionKind === "legacy") {
        clearBrowserInitData();
        window.location.replace("/mini-app/");
        return;
      }
      const response = await fetch("/api/v1/web-auth/logout", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: "{}",
      });
      if (!response.ok) {
        throw new Error("Сервер не подтвердил выход. Попробуйте ещё раз.");
      }

      // Revoke the cookie-backed session before removing any client credential.
      // Never delete drafts, saved media or other local user-owned content.
      clearBrowserInitData();
      window.__ROXY_WEB_SESSION_AUTHENTICATED__ = false;
      window.location.replace("/login");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось выйти из аккаунта.");
      setWorking(false);
    }
  };

  return (
    <div className="panel web-profile-session" aria-label="Управление веб-сессией">
      <div className="web-profile-session-copy">
        <span className="kicker">Веб-аккаунт</span>
        <p className="muted">Выйти из аккаунта на этом устройстве. Ваш баланс, работы и привязки сохранятся.</p>
      </div>
      <button
        className="secondary web-profile-logout"
        type="button"
        disabled={working}
        aria-busy={working}
        onClick={() => void logout()}
      >
        {working ? "Выходим…" : "Выйти из аккаунта"}
      </button>
      {error ? <p className="web-profile-logout-error" role="alert">{error}</p> : null}
    </div>
  );
}
