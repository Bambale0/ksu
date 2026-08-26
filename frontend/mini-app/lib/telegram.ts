import type { TelegramUser } from "./types";

type BackButton = {
  show?: () => void;
  hide?: () => void;
  onClick?: (callback: () => void) => void;
  offClick?: (callback: () => void) => void;
};

type HapticFeedback = {
  impactOccurred?: (style?: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
  notificationOccurred?: (type: "error" | "success" | "warning") => void;
  selectionChanged?: () => void;
};

export type TelegramWebApp = {
  initData?: string;
  initDataUnsafe?: { user?: TelegramUser; start_param?: string };
  initParams?: { tgWebAppStartParam?: string };
  colorScheme?: "light" | "dark";
  viewportStableHeight?: number;
  safeAreaInset?: { top?: number; bottom?: number; left?: number; right?: number };
  contentSafeAreaInset?: { top?: number; bottom?: number; left?: number; right?: number };
  ready?: () => void;
  expand?: () => void;
  close?: () => void;
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  setBottomBarColor?: (color: string) => void;
  openLink?: (url: string) => void;
  openTelegramLink?: (url: string) => void;
  showPopup?: (params: unknown) => void;
  hideKeyboard?: () => void;
  BackButton?: BackButton;
  HapticFeedback?: HapticFeedback;
  onEvent?: (event: string, callback: (...args: unknown[]) => void) => void;
  offEvent?: (event: string, callback: (...args: unknown[]) => void) => void;
};

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
    __ROXY_INITIAL_LAUNCH__?: { hash?: string; search?: string };
  }
}

const INITIAL_HASH_KEY = "__roxy_initial_hash";
const INITIAL_SEARCH_KEY = "__roxy_initial_search";

export function telegram(): TelegramWebApp | null {
  if (typeof window === "undefined") return null;
  return window.Telegram?.WebApp ?? null;
}

function paramsFromRaw(raw: string): URLSearchParams {
  const value = String(raw || "").trim();
  if (!value) return new URLSearchParams();
  return new URLSearchParams(value.startsWith("#") || value.startsWith("?") ? value.slice(1) : value);
}

function launchParamFrom(raw: string, names: string[]): string {
  const params = paramsFromRaw(raw);
  for (const name of names) {
    const value = String(params.get(name) || "").trim();
    if (value) return value;
  }
  return "";
}

export function getStartParamFallback(): string {
  if (typeof window === "undefined") return "";

  // 1. Telegram's canonical parsed value.
  const direct = String(telegram()?.initDataUnsafe?.start_param || "").trim();
  if (direct) return direct;

  // 2. Snapshot captured before telegram-web-app.js can rewrite launch params.
  const snapshot = window.__ROXY_INITIAL_LAUNCH__;
  for (const raw of [snapshot?.hash || "", snapshot?.search || ""]) {
    const value = launchParamFrom(raw, ["tgWebAppStartParam", "startapp", "start_payload"]);
    if (value) return value;
  }

  // 3. Telegram SDK raw init params.
  const sdkValue = String(telegram()?.initParams?.tgWebAppStartParam || "").trim();
  if (sdkValue) return sdkValue;

  // 4. Persisted early snapshots survive client-side navigation/remounts.
  for (const key of [INITIAL_HASH_KEY, INITIAL_SEARCH_KEY]) {
    try {
      const raw = window.sessionStorage.getItem(key) || "";
      const value = launchParamFrom(raw, ["tgWebAppStartParam", "startapp", "start_payload"]);
      if (value) return value;
    } catch {
      // Storage can be unavailable in restrictive WebViews.
    }
  }

  // 5. Current URL fallback. Keep KSU's product-owned start_payload alias too.
  for (const raw of [window.location.hash, window.location.search]) {
    const value = launchParamFrom(raw, ["tgWebAppStartParam", "startapp", "start_payload"]);
    if (value) return value;
  }

  // 6. Signed initData itself may still contain start_param even when SDK parsing is late.
  const initDataStart = String(paramsFromRaw(telegram()?.initData || "").get("start_param") || "").trim();
  if (initDataStart) return initDataStart;

  // 7. Compatibility with WebAppInfo launcher URLs and manual QA links.
  const search = paramsFromRaw(window.location.search);
  const start = String(search.get("start") || "").trim();
  if (start.startsWith("ref_")) return start;
  const ref = String(search.get("ref") || "").trim().toUpperCase();
  return ref ? `ref_${ref}` : "";
}

export function telegramHeaders(json = false): HeadersInit {
  const headers: Record<string, string> = { Accept: "application/json" };
  const initData = telegram()?.initData;
  if (initData) headers["X-Telegram-Init-Data"] = initData;
  const startParam = getStartParamFallback();
  if (startParam) headers["X-Telegram-Start-Param"] = startParam;
  if (json) headers["Content-Type"] = "application/json";
  return headers;
}

export function initTelegram(): TelegramWebApp | null {
  const tg = telegram();
  if (!tg) return null;
  tg.ready?.();
  tg.expand?.();
  try {
    tg.setHeaderColor?.("#0B0B10");
    tg.setBackgroundColor?.("#0B0B10");
    tg.setBottomBarColor?.("#0B0B10");
  } catch {
    // Older Telegram clients may not support all chrome methods.
  }
  syncSafeArea(tg);
  return tg;
}

function safeAreaValue(value: number | undefined, envName: string): string {
  const numeric = Number(value ?? 0);
  const pixels = Number.isFinite(numeric) ? Math.max(0, numeric) : 0;
  return `max(${pixels}px, env(${envName}, 0px))`;
}

export function syncSafeArea(tg = telegram()): void {
  if (!tg || typeof document === "undefined") return;
  const content = tg.contentSafeAreaInset ?? tg.safeAreaInset ?? {};
  const root = document.documentElement;
  root.style.setProperty("--tg-safe-top", safeAreaValue(content.top, "safe-area-inset-top"));
  root.style.setProperty("--tg-safe-bottom", safeAreaValue(content.bottom, "safe-area-inset-bottom"));
  root.style.setProperty("--tg-safe-left", safeAreaValue(content.left, "safe-area-inset-left"));
  root.style.setProperty("--tg-safe-right", safeAreaValue(content.right, "safe-area-inset-right"));
  if (tg.viewportStableHeight && Number.isFinite(tg.viewportStableHeight)) {
    root.style.setProperty("--tg-stable-height", `${Math.max(1, tg.viewportStableHeight)}px`);
  }
}

export function haptic(style: "light" | "medium" | "heavy" = "light"): void {
  try { telegram()?.HapticFeedback?.impactOccurred?.(style); } catch { /* optional */ }
}

export function notify(type: "error" | "success" | "warning"): void {
  try { telegram()?.HapticFeedback?.notificationOccurred?.(type); } catch { /* optional */ }
}

export function openExternalLink(url: string): void {
  try {
    const tg = telegram();
    if (tg?.openLink) { tg.openLink(url); return; }
  } catch { /* optional */ }
  window.open(url, "_blank", "noopener,noreferrer");
}

export function openTelegramShare(url: string): void {
  try {
    const tg = telegram();
    if (tg?.openTelegramLink) { tg.openTelegramLink(url); return; }
  } catch { /* optional */ }
  openExternalLink(url);
}

export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* fall through to legacy path */ }
  try {
    const el = document.createElement("textarea");
    el.value = text;
    el.style.position = "fixed";
    el.style.opacity = "0";
    document.body.appendChild(el);
    el.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(el);
    return ok;
  } catch {
    return false;
  }
}
