"use client";

import { useEffect, useRef, useState } from "react";
import { getStartParamFallback } from "@/lib/telegram";

type TelegramLoginUser = {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
};

declare global {
  interface Window {
    onRoxyTelegramAuth?: (user: TelegramLoginUser) => void;
  }
}

function saveBrowserInitData(initData: string): void {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  params.set("tgWebAppData", initData);
  window.location.hash = params.toString();
}

function telegramMiniAppUrl(botUsername: string): string {
  const startParam = getStartParamFallback();
  return startParam
    ? `https://t.me/${botUsername}?startapp=${encodeURIComponent(startParam)}`
    : `https://t.me/${botUsername}?startapp`;
}

export function TelegramBrowserLogin() {
  const widgetRef = useRef<HTMLDivElement | null>(null);
  const [botUsername, setBotUsername] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "signing-in" | "error">("loading");

  useEffect(() => {
    let active = true;

    void fetch("/api/v1/browser-auth/config", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => null) as { bot_username?: string } | null;
        if (!response.ok || !payload?.bot_username) throw new Error("Telegram login unavailable");
        if (!active) return;
        setBotUsername(payload.bot_username.replace(/^@/, ""));
      })
      .catch(() => active && setStatus("error"));

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!botUsername || !widgetRef.current) return;

    const container = widgetRef.current;
    container.replaceChildren();

    window.onRoxyTelegramAuth = async (user: TelegramLoginUser) => {
      setStatus("signing-in");
      try {
        const response = await fetch("/api/v1/browser-auth", {
          method: "POST",
          credentials: "same-origin",
          cache: "no-store",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ telegram_auth: user }),
        });
        const payload = await response.json().catch(() => null) as {
          ok?: boolean;
          init_data?: string;
        } | null;
        if (!response.ok || !payload?.ok || !payload.init_data) throw new Error("Telegram login failed");
        saveBrowserInitData(payload.init_data);
        window.location.reload();
      } catch {
        setStatus("error");
      }
    };

    const script = document.createElement("script");
    script.async = true;
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.setAttribute("data-telegram-login", botUsername);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "14");
    script.setAttribute("data-userpic", "false");
    script.setAttribute("data-onauth", "onRoxyTelegramAuth(user)");
    script.onload = () => setStatus("ready");
    script.onerror = () => setStatus("error");
    container.appendChild(script);

    return () => {
      delete window.onRoxyTelegramAuth;
      container.replaceChildren();
    };
  }, [botUsername]);

  const telegramUrl = botUsername ? telegramMiniAppUrl(botUsername) : "";

  return (
    <main className="splash browser-login-gate" role="main" aria-labelledby="browser-login-title">
      <strong id="browser-login-title">ROXY</strong>
      <small>Продолжите через Telegram — без пароля</small>
      <div ref={widgetRef} className="browser-login-widget" aria-live="polite" />
      {status === "loading" && <small>Готовлю вход…</small>}
      {status === "signing-in" && <small>Вхожу в ROXY…</small>}
      {status === "error" && (
        <div className="browser-login-fallback" role="alert">
          <small>Не получилось войти в браузере.</small>
          {telegramUrl && <a className="secondary" href={telegramUrl} target="_blank" rel="noreferrer">Открыть ROXY в Telegram</a>}
        </div>
      )}
    </main>
  );
}
