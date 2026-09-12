"use client";

import { useEffect } from "react";

function routeHref(url: URL): string {
  return `${url.pathname}${url.search}${url.hash}`;
}

function canonicalizeLegacyCatalogRoute(): void {
  const url = new URL(window.location.href);
  if (url.searchParams.get("route") !== "catalog") return;
  url.searchParams.set("route", "home");
  const state = window.history.state && typeof window.history.state === "object"
    ? { ...window.history.state, roxyRoute: "home" }
    : { roxyRoute: "home" };
  window.history.replaceState(state, "", routeHref(url));
  // RoxySocialApp listens to popstate to synchronize its internal route.
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
  // LiveTrendRail still understands the historical Home host. Keep that one
  // visible because HomeTrendFolders (including its inline admin controls) is
  // intentionally the canonical category implementation.
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

function syncHomeCatalog(): void {
  canonicalizeLegacyCatalogRoute();
  syncNavigation();
  const home = homeScreen();
  if (!home) return;
  ensureCatalogMarker(home);
  hideLegacyHomeSections(home);
  orderCatalogSurface(home);
}

export function HomeCatalogContract() {
  useEffect(() => {
    let frame = 0;
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(syncHomeCatalog);
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

  return null;
}
