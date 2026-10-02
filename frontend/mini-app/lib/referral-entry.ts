import { getStartParamFallback } from "./telegram";

const PLAIN_REFERRAL = /^ref_\d+$/i;
const PRODUCT_LAUNCH_PARAMS = ["startapp", "start_payload"];

export function isReferralDiscoveryLaunch(): boolean {
  if (typeof window === "undefined") return false;
  const url = new URL(window.location.href);
  // This is only a discovery shortcut. A server-required onboarding redirect
  // always keeps its existing gate, and never completes onboarding implicitly.
  if (url.searchParams.get("onboarding") === "1") return false;
  for (const raw of [url.search, url.hash]) {
    const internal = new URLSearchParams(raw.replace(/^[?#]/, "")).get("start_payload");
    if (internal && !PLAIN_REFERRAL.test(internal)) return false;
  }
  return PLAIN_REFERRAL.test(getStartParamFallback());
}

export function prepareReferralLanding(): void {
  if (!isReferralDiscoveryLaunch()) return;
  const url = new URL(window.location.href);
  const route = url.searchParams.get("route");
  if (route && route !== "home" && route !== "catalog") return;

  const state = window.history.state || {};
  const hash = new URLSearchParams(url.hash.replace(/^#/, ""));
  const explicit = [url.searchParams, hash].some((params) =>
    PRODUCT_LAUNCH_PARAMS.some((name) => PLAIN_REFERRAL.test(params.get(name) || "")),
  );
  // Telegram retains start_param across navigation. Do not reinterpret a
  // deliberate in-app route as a fresh referral after a WebView reload.
  if (!explicit && route && state.roxyRoute === route && state.roxyRootEntry !== true) return;

  // Keep the original launch in memory for the existing authenticated headers.
  // Never strip signed tgWebAppData or store credentials in browser storage.
  window.__ROXY_INITIAL_LAUNCH__ ??= { search: url.search, hash: url.hash };
  url.searchParams.set("route", "home");
  for (const params of [url.searchParams, hash]) {
    for (const name of PRODUCT_LAUNCH_PARAMS) {
      if (PLAIN_REFERRAL.test(params.get(name) || "")) params.delete(name);
    }
  }
  url.hash = hash.toString();
  window.history.replaceState(
    { ...state, roxyRoute: "home", roxyRootEntry: true },
    "",
    `${url.pathname}${url.search}${url.hash}`,
  );
}
