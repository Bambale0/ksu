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

function removeDuplicateFeedNav() {
  const nav = document.querySelector(".bottom-nav");
  if (!nav) return;
  const buttons = Array.from(nav.querySelectorAll<HTMLButtonElement>("button"));
  const hasCatalog = buttons.some((button) => buttonLabel(button) === "Каталог");
  if (!hasCatalog) return;

  for (const button of buttons) {
    if (buttonLabel(button) !== "Лента") continue;
    button.setAttribute("aria-hidden", "true");
    button.setAttribute("tabindex", "-1");
    button.style.display = "none";
  }
}

export function SingleFeedSurfaceGuard() {
  useEffect(() => {
    if (currentRoute() === "feed") replaceRoute("catalog");
    removeDuplicateFeedNav();

    const observer = new MutationObserver(removeDuplicateFeedNav);
    observer.observe(document.documentElement, { childList: true, subtree: true });

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
