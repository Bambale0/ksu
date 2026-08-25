"use client";

import { useEffect } from "react";

function currentRoute(): string {
  try {
    return new URL(window.location.href).searchParams.get("route") || "home";
  } catch {
    return "home";
  }
}

function replaceRoute(next: string) {
  const url = new URL(window.location.href);
  url.searchParams.set("route", next);
  window.history.replaceState({ roxyRoute: next }, "", `${url.pathname}${url.search}${url.hash}`);
  window.dispatchEvent(new PopStateEvent("popstate", { state: { roxyRoute: next } }));
}

function buttonLabel(button: HTMLButtonElement): string {
  return button.querySelector("small")?.textContent?.trim() || button.textContent?.trim() || "";
}

function setButtonLabel(button: HTMLButtonElement, label: string) {
  const small = button.querySelector("small");
  if (small) small.textContent = label;
  button.setAttribute("aria-label", label);
}

function removeDuplicateFeedNav() {
  const nav = document.querySelector(".bottom-nav");
  if (!nav) return;

  const buttons = Array.from(nav.querySelectorAll<HTMLButtonElement>("button"));
  const feedButtons = buttons.filter((button) => buttonLabel(button) === "Лента");

  // The app used to expose two different bottom-nav entries both named
  // "Лента": the real community feed and the catalog entry after a legacy
  // label patch. Keep exactly one visible Feed entry and restore the second
  // slot back to Catalog instead of hiding the user's catalog access.
  if (feedButtons.length > 1) {
    for (const duplicate of feedButtons.slice(1)) setButtonLabel(duplicate, "Каталог");
  }

  const catalogButtons = buttons.filter((button) => buttonLabel(button) === "Каталог");
  if (catalogButtons.length > 1) {
    for (const duplicate of catalogButtons.slice(1)) {
      duplicate.setAttribute("aria-hidden", "true");
      duplicate.setAttribute("tabindex", "-1");
      duplicate.style.display = "none";
    }
  }
}

export function SingleFeedSurfaceGuard() {
  useEffect(() => {
    if (currentRoute() === "feed") replaceRoute("catalog");
    removeDuplicateFeedNav();

    const observer = new MutationObserver(removeDuplicateFeedNav);
    observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });

    const onPopState = () => {
      if (currentRoute() === "feed") replaceRoute("catalog");
      window.requestAnimationFrame(removeDuplicateFeedNav);
    };
    window.addEventListener("popstate", onPopState);

    return () => {
      observer.disconnect();
      window.removeEventListener("popstate", onPopState);
    };
  }, []);

  return null;
}
