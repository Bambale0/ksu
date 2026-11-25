"use client";

import { useEffect, useState } from "react";

import { clearBrowserInitData, getBrowserInitData } from "@/lib/browser-auth-session";
import { getInitDataFallback, openExternalLink } from "@/lib/telegram";

const WEB_PROFILE_ENTRY = "/login?section=profile";

/** Native Telegram can open the web studio; only a browser session can sign out. */
export function WebProfileLogout() {
  const [sessionKind, setSessionKind] = useState<"native" | "browser" | null>(null);

  const [botUrl, setBotUrl] = useState<string | null>(null);
  const [botLinkFailed, setBotLinkFailed] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const browserCredential = getBrowserInitData();
    const currentInitData = getInitDataFallback();
    const nativeUser = Boolean(window.Telegram?.WebApp?.initDataUnsafe?.user);
    // The browser boundary may expose its credential through an SDK facade.
    const native = nativeUser || Boolean(currentInitData && currentInitData !== browserCredential);
    if (native) setSessionKind("native");
    else if (browserCredential) setSessionKind("browser");
  }, []);

  useEffect(() => {
    if (sessionKind !== "browser") return;
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    setBotLinkFailed(false);
    void fetch("/api/v1/browser-auth/config", { signal: controller.signal, credentials: "omit" })
      .then(async (response) => {
        if (!response.ok) throw new Error("Bot config unavailable");
        const config = await response.json();
        const username = typeof config?.bot_username === "string" ? config.bot_username.replace(/^@/, "") : "";
        if (!/^[A-Za-z0-9_]{5,32}$/.test(username)) throw new Error("Invalid bot username");
        if (active) setBotUrl("https://t.me/" + username);
      })
      .catch(() => { if (active) setBotLinkFailed(true); })
      .finally(() => window.clearTimeout(timeout));
    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [sessionKind, retry]);

  if (!sessionKind) return null;

  const signOut = () => {
    clearBrowserInitData();
    window.location.replace("/login");
  };

  return (
    <section className="web-profile-session panel" aria-label="Веб-сессия">
      <div className="web-profile-session-copy">
        <strong>
          {sessionKind === "browser" ? (
            botUrl ? <a className="web-profile-entry" href={botUrl} target="_blank" rel="noopener noreferrer">
              Открыть Telegram <span aria-hidden="true">↗</span>
            </a> : <span>Telegram</span>
          ) : <a
            className="web-profile-entry"
            href={WEB_PROFILE_ENTRY}
            onClick={(event) => {
              if (sessionKind !== "native") return;
              event.preventDefault();
              // Use only the current origin and a fixed public route; never
              // copy Telegram launch data, credentials, or user IDs into URLs.
              openExternalLink(new URL(WEB_PROFILE_ENTRY, window.location.origin).href);
            }}
          >
            Вход в веб-версию <span aria-hidden="true">↗</span>
          </a>}
        </strong>
        {sessionKind === "browser" && !botUrl && (
          botLinkFailed ? <p className="muted" role="status">Не удалось загрузить ссылку на бота.{" "}
            <button className="secondary" type="button" onClick={() => setRetry(value => value + 1)}>Повторить</button>
          </p> : <p className="muted" role="status">Загружаем ссылку на Telegram…</p>
        )}
        <p className="muted">{sessionKind === "native"
          ? "Открой ROXY в браузере и войди через тот же Telegram-аккаунт."
          : "Открой чат с ботом ROXY. Можно выйти из браузера, не выходя из Telegram."}</p>
      </div>
      {sessionKind === "browser" ? (
        <button type="button" className="secondary web-profile-logout" onClick={signOut}>
          Выйти из аккаунта
        </button>
      ) : null}
    </section>
  );
}
