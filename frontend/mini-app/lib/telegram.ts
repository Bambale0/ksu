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
const URL_START_PARAM_NAMES = ["tgWebAppStartParam", "start_payload", "startapp"];
const MINI_APP_RETURN_KEY = "__roxy_standalone_return_v1";
const MAIN_ROUTES = new Set(["home", "feed", "catalog", "create", "history", "profile", "partners"]);
const managedTelegramApps = new WeakSet<object>();
let returnTrackerInstalled = false;

type RoxyHistoryState = Record<string, unknown> & {
  roxyRoute?: string;
  roxyRootEntry?: boolean;
};

function isMainMiniAppPath(): boolean {
  if (typeof window === "undefined") return false;
  return window.location.pathname.replace(/\/+$/, "") === "/mini-app";
}

function currentMainRoute(): string {
  if (typeof window === "undefined") return "home";
  const route = String(new URL(window.location.href).searchParams.get("route") || "home");
  return MAIN_ROUTES.has(route) ? route : "home";
}

function historyState(): RoxyHistoryState {
  if (typeof window === "undefined") return {};
  const value = window.history.state;
  return value && typeof value === "object" ? { ...(value as Record<string, unknown>) } : {};
}

function stampMiniAppRootEntry(): void {
  if (!isMainMiniAppPath()) return;
  const state = historyState();
  if (state.roxyRootEntry === true || typeof state.roxyRoute === "string") return;
  const next: RoxyHistoryState = { ...state, roxyRoute: currentMainRoute(), roxyRootEntry: true };
  window.history.replaceState(next, "", window.location.href);
}

function rememberMiniAppReturnLocation(): void {
  if (!isMainMiniAppPath()) return;
  try {
    window.sessionStorage.setItem(
      MINI_APP_RETURN_KEY,
      `${window.location.pathname}${window.location.search}${window.location.hash}`,
    );
  } catch {
    // sessionStorage can be unavailable in restrictive WebViews.
  }
}

function installMiniAppReturnTracker(): void {
  if (typeof window === "undefined" || returnTrackerInstalled) return;
  returnTrackerInstalled = true;
  const remember = () => rememberMiniAppReturnLocation();
  window.addEventListener("pagehide", remember);
  window.addEventListener("popstate", remember);
  remember();
}

export function consumeMiniAppReturnLocation(): string | null {
  if (typeof window === "undefined") return null;
  let raw = "";
  try {
    raw = String(window.sessionStorage.getItem(MINI_APP_RETURN_KEY) || "").trim();
    window.sessionStorage.removeItem(MINI_APP_RETURN_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  try {
    const target = new URL(raw, window.location.origin);
    if (target.origin !== window.location.origin) return null;
    if (target.pathname.replace(/\/+$/, "") !== "/mini-app") return null;
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return null;
  }
}

function hasTransientCustomerLayer(): boolean {
  if (typeof document === "undefined") return false;
  return Boolean(document.querySelector([
    '[role="dialog"]',
    ".overlay",
    ".sheet-overlay",
    ".sheet-backdrop",
    ".bottom-sheet",
    ".preview-card",
    ".tiktok-sheet-layer",
  ].join(",")));
}

function isCustomerMainSurface(): boolean {
  return isMainMiniAppPath()
    && typeof document !== "undefined"
    && Boolean(document.querySelector(".roxy-app .bottom-nav"));
}

function replaceRootRouteWithHome(): void {
  const url = new URL(window.location.href);
  url.searchParams.set("route", "home");
  const next: RoxyHistoryState = { ...historyState(), roxyRoute: "home", roxyRootEntry: true };
  window.history.replaceState(next, "", url);
  try {
    window.dispatchEvent(new PopStateEvent("popstate", { state: next }));
  } catch {
    window.dispatchEvent(new Event("popstate"));
  }
}

function handleCustomerBack(tg: TelegramWebApp): boolean {
  if (!isCustomerMainSurface() || hasTransientCustomerLayer()) return false;

  rememberMiniAppReturnLocation();
  const route = currentMainRoute();
  const state = historyState();

  if (state.roxyRootEntry === true) {
    if (route === "home") {
      tg.close?.();
      return true;
    }
    replaceRootRouteWithHome();
    return true;
  }

  if (typeof state.roxyRoute === "string") {
    window.history.back();
    return true;
  }

  if (route === "home") {
    tg.close?.();
    return true;
  }

  replaceRootRouteWithHome();
  return true;
}

function installManagedBackButton(tg: TelegramWebApp): void {
  const raw = tg.BackButton;
  if (!raw || managedTelegramApps.has(tg as object)) return;

  const rawShow = raw.show?.bind(raw);
  const rawHide = raw.hide?.bind(raw);
  const rawOnClick = raw.onClick?.bind(raw);
  const rawOffClick = raw.offClick?.bind(raw);
  const adapters = new Map<() => void, () => void>();
  const managed = Object.create(raw) as BackButton;

  managed.show = () => {
    rememberMiniAppReturnLocation();
    rawShow?.();
  };
  managed.hide = () => {
    rememberMiniAppReturnLocation();
    if (isMainMiniAppPath()) rawShow?.();
    else rawHide?.();
  };
  managed.onClick = (callback) => {
    const previous = adapters.get(callback);
    if (previous) rawOffClick?.(previous);
    const adapter = () => {
      if (!handleCustomerBack(tg)) callback();
    };
    adapters.set(callback, adapter);
    rawOnClick?.(adapter);
  };
  managed.offClick = (callback) => {
    const adapter = adapters.get(callback);
    if (!adapter) return;
    rawOffClick?.(adapter);
    adapters.delete(callback);
  };

  try {
    tg.BackButton = managed;
    managedTelegramApps.add(tg as object);
  } catch {
    // Fall back to the SDK object unchanged on clients with immutable properties.
  }
}

export function telegram(): TelegramWebApp | null {
  if (typeof window === "undefined") return null;
  const tg = window.Telegram?.WebApp ?? null;
  if (tg) installManagedBackButton(tg);
  return tg;
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

export function getInitDataFallback(): string {
  if (typeof window === "undefined") return "";

  // Prefer Telegram SDK's canonical initData whenever it is ready.
  const sdkValue = String(telegram()?.initData || "").trim();
  if (sdkValue) return sdkValue;

  // On a cold WebView start tgWebAppData can exist in the original launch URL
  // before telegram-web-app.js has populated WebApp.initData. Keep this fallback
  // in page memory only; auth payloads are intentionally not persisted to storage.
  const snapshot = window.__ROXY_INITIAL_LAUNCH__;
  for (const raw of [snapshot?.hash || "", snapshot?.search || ""]) {
    const value = launchParamFrom(raw, ["tgWebAppData"]);
    if (value) return value;
  }

  for (const raw of [window.location.hash, window.location.search]) {
    const value = launchParamFrom(raw, ["tgWebAppData"]);
    if (value) return value;
  }

  return "";
}

export function getStartParamFallback(): string {
  if (typeof window === "undefined") return "";

  // 1. Telegram's canonical parsed value.
  const direct = String(telegram()?.initDataUnsafe?.start_param || "").trim();
  if (direct) return direct;

  // 2. Telegram SDK raw launch param when available.
  const sdkValue = String(telegram()?.initParams?.tgWebAppStartParam || "").trim();
  if (sdkValue) return sdkValue;

  // 3. Signed tgWebAppData is authoritative before product-owned URL aliases.
  const signedStart = String(paramsFromRaw(getInitDataFallback()).get("start_param") || "").trim();
  if (signedStart) return signedStart;

  // 4. Snapshot captured before telegram-web-app.js can rewrite launch params.
  // KSU's explicit start_payload alias has priority over the generic startapp
  // compatibility query when both are present in a product-owned launcher URL.
  const snapshot = window.__ROXY_INITIAL_LAUNCH__;
  for (const raw of [snapshot?.hash || "", snapshot?.search || ""]) {
    const value = launchParamFrom(raw, URL_START_PARAM_NAMES);
    if (value) return value;
  }

  // 5. Persisted launch-param snapshots survive client-side navigation/remounts.
  // They contain only the routing payload, never Telegram auth initData.
  for (const key of [INITIAL_HASH_KEY, INITIAL_SEARCH_KEY]) {
    try {
      const raw = window.sessionStorage.getItem(key) || "";
      const value = launchParamFrom(raw, URL_START_PARAM_NAMES);
      if (value) return value;
    } catch {
      // Storage can be unavailable in restrictive WebViews.
    }
  }

  // 6. Current URL fallback. Keep KSU's product-owned start_payload alias too.
  for (const raw of [window.location.hash, window.location.search]) {
    const value = launchParamFrom(raw, URL_START_PARAM_NAMES);
    if (value) return value;
  }

  // 7. Compatibility with WebAppInfo launcher URLs and manual QA links.
  const search = paramsFromRaw(window.location.search);
  const start = String(search.get("start") || "").trim();
  if (start.startsWith("ref_")) return start;
  const ref = String(search.get("ref") || "").trim().toUpperCase();
  return ref ? `ref_${ref}` : "";
}

export function telegramHeaders(json = false): HeadersInit {
  const headers: Record<string, string> = { Accept: "application/json" };
  const initData = getInitDataFallback();
  if (initData) headers["X-Telegram-Init-Data"] = initData;
  const startParam = getStartParamFallback();
  if (startParam) headers["X-Telegram-Start-Param"] = startParam;
  if (json) headers["Content-Type"] = "application/json";
  return headers;
}

export function initTelegram(): TelegramWebApp | null {
  const tg = telegram();
  if (!tg) return null;

  stampMiniAppRootEntry();
  installMiniAppReturnTracker();

  // Reset native navigation to the current screen baseline. On the customer
  // Mini App path the managed BackButton remains visible so the user can always
  // walk back through ROXY and close the WebView at the root screen.
  try {
    tg.BackButton?.hide?.();
  } catch {
    // Older clients may not expose the native BackButton API consistently.
  }

  // Telegram can expose tgWebAppData in the initial WebView URL before its SDK
  // populates WebApp.initData. Hydrate that already-present, still-untrusted value
  // into the in-memory SDK object so existing authenticated bootstrap gates do not
  // skip the first API request. The backend remains the signature authority.
  const recoveredInitData = getInitDataFallback();
  if (!String(tg.initData || "").trim() && recoveredInitData) tg.initData = recoveredInitData;

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

export function openPaymentLink(rawUrl: string): boolean {
  try {
    const parsed = new URL(rawUrl);
    if (parsed.protocol !== "https:") return false;
    const tg = telegram();
    const host = parsed.hostname.toLowerCase();
    if ((host === "t.me" || host === "telegram.me") && tg?.openTelegramLink) {
      tg.openTelegramLink(parsed.toString());
      return true;
    }
    if (tg?.openLink) {
      tg.openLink(parsed.toString());
      return true;
    }
    window.open(parsed.toString(), "_blank", "noopener,noreferrer");
    return true;
  } catch {
    return false;
  }
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
