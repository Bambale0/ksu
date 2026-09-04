"use client";

import { useLayoutEffect } from "react";

function routeHref(url: URL): string {
  return `${url.pathname}${url.search}${url.hash}`;
}

function canonicalizeLegacyCatalogRoute(): void {
  const url = new URL(window.location.href);
  if (url.searchParams.get("route") !== "catalog") return;
  url.searchParams.set("route", "home");
  const state = window.history.state && typeof window.history.state === "object"
    ? { ...window.history.state, roxyRoute: "home", roxyRootEntry: true }
    : { roxyRoute: "home", roxyRootEntry: true };
  window.history.replaceState(state, "", routeHref(url));
  window.dispatchEvent(new Event("popstate"));
}

function homeScreen(): HTMLElement | null {
  return document.querySelector<HTMLElement>(".main-shell > .home-screen");
}

function ensureCatalogMarker(home: HTMLElement): void {
  if (home.querySelector(":scope > [data-home-catalog-marker]")) return;
  const marker = document.createElement("div");
  marker.className = "screen-head";
  marker.dataset.homeCatalogMarker = "true";
  marker.hidden = true;
  marker.setAttribute("aria-hidden", "true");
  const kicker = document.createElement("span");
  kicker.className = "kicker";
  kicker.textContent = "Каталог";
  marker.appendChild(kicker);
  home.prepend(marker);
}

function setHidden(node: HTMLElement | null, hidden: boolean): void {
  if (!node || node.hidden === hidden) return;
  node.hidden = hidden;
}

function hideLegacyHomeSections(home: HTMLElement): void {
  for (const title of Array.from(home.querySelectorAll<HTMLElement>(":scope > .section-title"))) {
    const kicker = title.querySelector<HTMLElement>(".kicker")?.textContent?.trim() || "";
    if (kicker !== "Студия" && kicker !== "Тренды") continue;
    setHidden(title, true);
    const body = title.nextElementSibling as HTMLElement | null;
    if (body?.matches(".format-grid, .model-grid, .empty")) setHidden(body, true);
  }
}

function syncNavigation(): void {
  const homeButton = document.querySelector<HTMLButtonElement>(".bottom-nav button[data-roxy-customer-route='home']");
  const catalogButton = document.querySelector<HTMLButtonElement>(".bottom-nav button[data-roxy-customer-route='catalog']");
  const homeLabel = homeButton?.querySelector<HTMLElement>("small");
  if (homeLabel && homeLabel.textContent !== "Каталог") homeLabel.textContent = "Каталог";
  if (homeButton) {
    homeButton.hidden = false;
    homeButton.removeAttribute("aria-hidden");
    if (homeButton.tabIndex < 0) homeButton.tabIndex = 0;
    homeButton.setAttribute("aria-label", "Каталог");
    homeButton.dataset.homeCatalog = "true";
  }
  if (catalogButton) {
    catalogButton.hidden = true;
    catalogButton.tabIndex = -1;
    catalogButton.setAttribute("aria-hidden", "true");
  }

  const brand = document.querySelector<HTMLButtonElement>(".topbar .brand[data-roxy-customer-route='home']");
  if (brand) brand.setAttribute("aria-label", "ROXY — каталог");
}

function placeAfter(anchor: HTMLElement | null, node: HTMLElement | null): HTMLElement | null {
  if (!anchor || !node || anchor === node) return anchor;
  if (anchor.nextElementSibling !== node) anchor.insertAdjacentElement("afterend", node);
  return node;
}

function orderCatalogSurface(home: HTMLElement): void {
  setHidden(home.querySelector<HTMLElement>(":scope > #roxy-live-trends"), true);

  const promo = home.querySelector<HTMLElement>(":scope > .promo-slider");
  const trends = home.querySelector<HTMLElement>(":scope > #roxy-home-live-trends");
  const folders = home.querySelector<HTMLElement>(":scope > #roxy-home-trend-folders");
  const features = home.querySelector<HTMLElement>(":scope > #roxy-catalog-feature-hub");
  const services = home.querySelector<HTMLElement>(":scope > #roxy-backend-parity-features");

  let anchor = promo;
  anchor = placeAfter(anchor, trends);
  anchor = placeAfter(anchor, folders);
  anchor = placeAfter(anchor, features);
  placeAfter(anchor, services);
}

function nativeBackHide(): (() => void) | null {
  const button = window.Telegram?.WebApp?.BackButton as ({ hide?: () => void } & object) | undefined;
  if (!button) return null;
  const prototype = Object.getPrototypeOf(button) as { hide?: () => void } | null;
  // telegram.ts wraps the SDK BackButton with Object.create(raw). Calling the
  // prototype's hide bypasses the managed adapter that intentionally keeps Back
  // visible on non-root routes. Fall back to the current object before wrapping.
  const nativeButton = prototype?.hide ? prototype : button;
  return nativeButton.hide ? nativeButton.hide.bind(nativeButton) : null;
}

function hideNativeBackAtRoot(rawHide: (() => void) | null): void {
  if (!rawHide) return;
  const url = new URL(window.location.href);
  if (url.pathname.replace(/\/+$/, "") !== "/mini-app") return;
  if ((url.searchParams.get("route") || "home") !== "home") return;
  rawHide();
}

function syncHomeCatalog(rawHide: (() => void) | null): void {
  canonicalizeLegacyCatalogRoute();
  syncNavigation();
  const home = homeScreen();
  if (home) {
    ensureCatalogMarker(home);
    hideLegacyHomeSections(home);
    orderCatalogSurface(home);
  }
  hideNativeBackAtRoot(rawHide);
}

export function HomeCatalogContract() {
  useLayoutEffect(() => {
    const rawHide = nativeBackHide();
    let frame = 0;
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => syncHomeCatalog(rawHide));
    };

    schedule();
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    window.addEventListener("popstate", schedule);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("popstate", schedule);
    };
  }, []);

  return <style jsx global>{`
    .bottom-nav button[data-home-catalog="true"] { display: grid !important; }
    .bottom-nav button[data-roxy-customer-route="catalog"] { display: none !important; }
  `}</style>;
}
