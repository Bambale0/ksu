"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { clearStoredLaunchPayload, consumeMiniAppReturnLocation, haptic, initTelegram, syncSafeArea } from "@/lib/telegram";

function compact(value: unknown): string {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(number);
}

function returnFromStandalone() {
  haptic("light");
  if (typeof window === "undefined") return;

  const returnTo = consumeMiniAppReturnLocation();
  if (!returnTo) {
    window.location.replace("/mini-app/?route=home");
    return;
  }

  if (window.history.length <= 1) {
    window.location.replace(returnTo);
    return;
  }

  const standaloneUrl = window.location.href;
  let fallback = window.setTimeout(() => {
    if (window.location.href === standaloneUrl) window.location.replace(returnTo);
  }, 350);
  window.addEventListener("pagehide", () => {
    window.clearTimeout(fallback);
    fallback = 0;
  }, { once: true });
  window.history.back();
}

function openMainRoute(route: "home" | "profile"): void {
  clearStoredLaunchPayload();
  window.location.assign(`/mini-app/?route=${route}`);
}

export function StandaloneShell({
  kicker,
  title,
  copy,
  children,
}: {
  kicker: string;
  title: string;
  copy?: string;
  children: ReactNode;
}) {
  const [balance, setBalance] = useState<string | null>(null);

  useEffect(() => {
    const tg = initTelegram();
    const safe = () => syncSafeArea(tg);
    const back = () => returnFromStandalone();
    tg?.ready?.();
    tg?.expand?.();
    tg?.BackButton?.show?.();
    tg?.BackButton?.onClick?.(back);
    tg?.onEvent?.("safeAreaChanged", safe);
    tg?.onEvent?.("contentSafeAreaChanged", safe);
    tg?.onEvent?.("viewportChanged", safe);
    if (tg?.initData) {
      void api.me().then((me) => setBalance(me.balance_rox)).catch(() => setBalance(null));
    }
    return () => {
      tg?.BackButton?.offClick?.(back);
      tg?.BackButton?.hide?.();
      tg?.offEvent?.("safeAreaChanged", safe);
      tg?.offEvent?.("contentSafeAreaChanged", safe);
      tg?.offEvent?.("viewportChanged", safe);
    };
  }, []);

  return (
    <div className="roxy-app standalone-app">
      <header className="topbar">
        <button
          className="brand"
          type="button"
          onClick={() => openMainRoute("home")}
          aria-label="ROXY — главная"
        >
          <span className="roxy-mark" aria-hidden="true"><span>RX</span></span>
          <span className="brand-copy"><strong>ROXY</strong><small>Студия творчества</small></span>
        </button>
        <button
          className="balance-button"
          type="button"
          onClick={() => openMainRoute("profile")}
        >
          <span>Баланс</span><strong>{balance == null ? "—" : `${compact(balance)} ROX`}</strong>
        </button>
      </header>

      <main className="main-shell">
        <section className="screen standalone-screen">
          <header className="screen-head">
            <span className="kicker">{kicker}</span>
            <h1>{title}</h1>
            {copy ? <p>{copy}</p> : null}
          </header>
          {children}
        </section>
      </main>
    </div>
  );
}
