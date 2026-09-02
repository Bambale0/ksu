"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { clearStoredLaunchPayload, consumeMiniAppReturnLocation, haptic, initTelegram, syncSafeArea } from "@/lib/telegram";

const STANDALONE_RETURN_KEY = "__roxy_standalone_return_v1";
const STANDALONE_RETURNING_TO_KEY = "__roxy_standalone_returning_to_v1";

function compact(value: unknown): string {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(number);
}

function currentLocation(): string {
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

function safeMiniAppReferrer(): string | null {
  const raw = String(document.referrer || "").trim();
  if (!raw) return null;
  try {
    const referrer = new URL(raw, window.location.origin);
    if (referrer.origin !== window.location.origin) return null;
    const path = referrer.pathname.replace(/\/+$/, "");
    if (path !== "/mini-app" && !path.startsWith("/mini-app/")) return null;
    return `${referrer.pathname}${referrer.search}${referrer.hash}`;
  } catch {
    return null;
  }
}

function repairStandaloneReturnLocation(): void {
  if (typeof window === "undefined") return;
  try {
    const current = currentLocation();
    const returningTo = String(window.sessionStorage.getItem(STANDALONE_RETURNING_TO_KEY) || "");
    if (returningTo) {
      window.sessionStorage.removeItem(STANDALONE_RETURNING_TO_KEY);
      // The previous document can write itself back during pagehide after native
      // Back has already consumed its parent. When we arrive at the requested
      // standalone target, discard that stale child so Back cannot bounce between
      // the same two deep-link pages forever.
      if (returningTo === current) {
        window.sessionStorage.removeItem(STANDALONE_RETURN_KEY);
        return;
      }
    }

    const stored = String(window.sessionStorage.getItem(STANDALONE_RETURN_KEY) || "");
    if (stored !== current) return;

    // AppEntryGate and the managed BackButton can both stamp the newly opened
    // standalone page as the return target. Recover the real same-origin Mini App
    // parent from document.referrer after those setup calls have finished. A cold
    // Telegram launch has no safe Mini App referrer, so it falls back to Home.
    const referrer = safeMiniAppReferrer();
    if (referrer && referrer !== current) window.sessionStorage.setItem(STANDALONE_RETURN_KEY, referrer);
    else window.sessionStorage.removeItem(STANDALONE_RETURN_KEY);
  } catch {
    // sessionStorage/referrer can be unavailable in restrictive WebViews.
  }
}

function returnFromStandalone(returnTo: string | null) {
  haptic("light");
  if (typeof window === "undefined") return;

  const target = returnTo || "/mini-app/?route=home";
  try {
    // Mark the exact destination so its StandaloneShell can discard a stale
    // pagehide write from the child document after this navigation completes.
    window.sessionStorage.setItem(STANDALONE_RETURNING_TO_KEY, target);
  } catch {
    // Navigation still works when storage is unavailable.
  }
  // Standalone tools can be reached through location.replace() from a Telegram
  // deep-link gate, so browser history may point at about:blank or an unrelated
  // page. Use the repaired same-origin Mini App return location instead.
  window.location.replace(target);
}

function openMainRoute(route: "home"): void {
  clearStoredLaunchPayload();
  window.location.assign(`/mini-app/?route=${route}`);
}

function openPayments(): void {
  window.location.assign("/mini-app/payments/");
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
    tg?.ready?.();
    tg?.expand?.();
    tg?.BackButton?.show?.();

    // The generic return tracker and Telegram chrome can write sessionStorage
    // again after this effect. Repair once, then capture and consume the verified
    // parent before registering native Back so late writes can never turn Back
    // into a self-loop.
    repairStandaloneReturnLocation();
    const returnTo = consumeMiniAppReturnLocation();
    const back = () => returnFromStandalone(returnTo);
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
          onClick={openPayments}
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
