"use client";

import { useEffect, useState } from "react";

import { clearBrowserInitData, getBrowserInitData } from "@/lib/browser-auth-session";
import { getInitDataFallback, openExternalLink } from "@/lib/telegram";

const WEB_PROFILE_ENTRY = "/login?section=profile";

/** Native Telegram can open the web studio; only a browser session can sign out. */
export function WebProfileLogout() {
  const [sessionKind, setSessionKind] = useState<"native" | "browser" | null>(null);

  useEffect(() => {
    const browserCredential = getBrowserInitData();
    const currentInitData = getInitDataFallback();
    const nativeUser = Boolean(window.Telegram?.WebApp?.initDataUnsafe?.user);
    // The browser boundary may expose its credential through an SDK facade.
    const native = nativeUser || Boolean(currentInitData && currentInitData !== browserCredential);
    if (native) setSessionKind("native");
    else if (browserCredential) setSessionKind("browser");
  }, []);

  if (!sessionKind) return null;

  const signOut = () => {
    clearBrowserInitData();
    window.location.replace("/login");
  };

  return (
    <section className="web-profile-session panel" aria-label="Веб-сессия">
      <div className="web-profile-session-copy">
        <strong>
          <a
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
          </a>
        </strong>
        <p className="muted">{sessionKind === "native"
          ? "Открой ROXY в браузере и войди через тот же Telegram-аккаунт."
          : "Можно выйти из браузера, не выходя из Telegram."}</p>
      </div>
      {sessionKind === "browser" ? (
        <button type="button" className="secondary web-profile-logout" onClick={signOut}>
          Выйти из аккаунта
        </button>
      ) : null}
    </section>
  );
}
