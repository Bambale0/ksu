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
  }
}

export function telegram(): TelegramWebApp | null {
  if (typeof window === "undefined") return null;
  return window.Telegram?.WebApp ?? null;
}

export function telegramHeaders(json = false): HeadersInit {
  const headers: Record<string, string> = { Accept: "application/json" };
  const initData = telegram()?.initData;
  if (initData) headers["X-Telegram-Init-Data"] = initData;
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
  // Telegram and WebKit do not always report identical insets. Keep whichever
  // one is larger so a notch/home indicator can never be covered.
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
