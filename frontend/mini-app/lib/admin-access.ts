"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { initTelegram } from "@/lib/telegram";

type AdminAccessState = "checking" | "admin" | "customer";

const RETRY_DELAYS_MS = [180, 650, 1600] as const;

let resolvedAdmin: boolean | null = null;
let inFlight: Promise<boolean> | null = null;

async function resolveAdminAccess(force = false): Promise<boolean> {
  if (!force && resolvedAdmin !== null) return resolvedAdmin;
  if (inFlight) return inFlight;

  // Some iOS Telegram WebViews mount client islands before telegram-web-app.js
  // has fully hydrated WebApp.initData. Prime the SDK/fallback snapshot before
  // asking /me instead of treating that startup race as "not an admin".
  initTelegram();
  inFlight = api.me()
    .then((me) => {
      const isAdmin = Boolean(me.is_admin);
      resolvedAdmin = isAdmin;
      return isAdmin;
    })
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

export function useAdminAccess(): AdminAccessState {
  const [state, setState] = useState<AdminAccessState>(() => (
    resolvedAdmin === true ? "admin" : resolvedAdmin === false ? "customer" : "checking"
  ));

  useEffect(() => {
    let alive = true;
    let settled = resolvedAdmin !== null;
    let attempt = 0;
    let timer = 0;

    const check = (force = false) => {
      if (!alive || settled) return;
      void resolveAdminAccess(force)
        .then((isAdmin) => {
          if (!alive) return;
          settled = true;
          setState(isAdmin ? "admin" : "customer");
        })
        .catch(() => {
          if (!alive || settled) return;
          const delay = RETRY_DELAYS_MS[attempt];
          if (delay === undefined) return;
          attempt += 1;
          timer = window.setTimeout(() => check(true), delay);
        });
    };

    const retryWhenVisible = () => {
      if (!alive || settled || document.visibilityState !== "visible") return;
      if (timer) window.clearTimeout(timer);
      attempt = 0;
      check(true);
    };

    check();
    window.addEventListener("focus", retryWhenVisible);
    document.addEventListener("visibilitychange", retryWhenVisible);
    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
      window.removeEventListener("focus", retryWhenVisible);
      document.removeEventListener("visibilitychange", retryWhenVisible);
    };
  }, []);

  return state;
}
