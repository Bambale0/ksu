"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import styles from "./universal-back-button.module.css";

type TelegramWindow = Window & {
  Telegram?: {
    WebApp?: {
      close?: () => void;
      HapticFeedback?: { impactOccurred?: (style: string) => void };
    };
  };
};

function currentRoute(): string {
  if (typeof window === "undefined") return "home";
  return new URL(window.location.href).searchParams.get("route") || "home";
}

function dispatchRouteChange() {
  window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
}

function replaceWithHome() {
  const url = new URL(window.location.href);
  url.searchParams.set("route", "home");
  url.searchParams.delete("generation");
  url.searchParams.delete("action");
  window.history.replaceState({ roxyRoute: "home" }, "", `${url.pathname}${url.search}${url.hash}`);
  dispatchRouteChange();
  window.scrollTo({ top: 0, behavior: "auto" });
}

function returnToGeneration() {
  const url = new URL(window.location.href);
  const generationId = url.searchParams.get("generation");
  if (!generationId) {
    replaceWithHome();
    return;
  }
  url.searchParams.set("route", "history");
  url.searchParams.set("generation", generationId);
  url.searchParams.delete("action");
  window.location.assign(`${url.pathname}${url.search}${url.hash}`);
}

export function UniversalBackButton() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [route, setRoute] = useState("home");

  const sync = useCallback(() => {
    if (typeof document === "undefined") return;
    setRoute(currentRoute());
    const screen = document.querySelector<HTMLElement>(".main-shell .screen");
    if (!screen) {
      setHost(null);
      return;
    }
    let nextHost = screen.querySelector<HTMLElement>(":scope > [data-roxy-back-host]");
    if (!nextHost) {
      nextHost = document.createElement("div");
      nextHost.dataset.roxyBackHost = "true";
      nextHost.className = styles.host;
      screen.prepend(nextHost);
    }
    setHost(nextHost);
  }, []);

  useEffect(() => {
    sync();
    window.addEventListener("popstate", sync);
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      window.removeEventListener("popstate", sync);
    };
  }, [sync]);

  const goBack = useCallback(() => {
    const tg = (window as TelegramWindow).Telegram?.WebApp;
    tg?.HapticFeedback?.impactOccurred?.("light");
    const activeRoute = currentRoute();

    if (activeRoute === "generation-action") {
      returnToGeneration();
      return;
    }

    if (activeRoute === "home") {
      if (tg?.close) {
        tg.close();
        return;
      }
      if (window.history.length > 1) window.history.back();
      return;
    }

    const state = window.history.state as { roxyRoute?: string } | null;
    if (state?.roxyRoute === activeRoute && window.history.length > 1) {
      window.history.back();
      return;
    }

    replaceWithHome();
  }, []);

  if (!host) return null;

  return createPortal(
    <button className={styles.backButton} type="button" onClick={goBack} aria-label={route === "home" ? "Закрыть ROXY" : "Назад"} data-roxy-back-button>
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="m15 18-6-6 6-6" />
      </svg>
      <span>Назад</span>
    </button>,
    host,
  );
}
