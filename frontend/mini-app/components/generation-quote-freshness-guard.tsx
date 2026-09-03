"use client";

import { useLayoutEffect, useRef } from "react";

const STALE_ATTR = "data-roxy-quote-stale";
const STALE_TIMEOUT_MS = 12_000;

function requestUrl(input: RequestInfo | URL): string {
  return typeof input === "string" || input instanceof URL ? String(input) : input.url;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function isQuoteRequest(input: RequestInfo | URL, init?: RequestInit): boolean {
  if (requestMethod(input, init) !== "POST") return false;
  try {
    const url = new URL(requestUrl(input), window.location.href);
    return url.pathname === "/api/v1/generations/quote";
  } catch {
    return false;
  }
}

function quoteBox(): HTMLElement | null {
  return document.querySelector<HTMLElement>(".create-screen .quote-box");
}

function createButton(): HTMLButtonElement | null {
  return document.querySelector<HTMLButtonElement>(".create-screen .create-summary button.primary");
}

function compact(value: unknown): string {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) return "0";
  return new Intl.NumberFormat("ru-RU", {
    notation: Math.abs(numeric) >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(numeric);
}

function relevantDraftMutation(event: Event): boolean {
  const target = event.target;
  if (!(target instanceof Element)) return false;
  const screen = target.closest(".create-screen");
  if (!screen) return false;

  if (event.type === "input") {
    // React updates continuous numeric controls from `input`. Their native
    // `change` fires again on blur, after the fresh quote may already be shown;
    // treating both events as mutations would re-stale a valid quote with no
    // subsequent React draft change/request.
    if (target instanceof HTMLInputElement) {
      const type = String(target.type || "text").toLowerCase();
      return type === "number" || type === "range";
    }
    // Free-form prompt / negative-prompt copy changes the generation payload,
    // but does not affect billing and intentionally does not need a price lock.
    return false;
  }

  if (event.type === "change") {
    if (target instanceof HTMLSelectElement) return true;
    if (target instanceof HTMLInputElement) {
      const type = String(target.type || "text").toLowerCase();
      // Discrete controls do not have the number-input blur duplication above.
      return type === "checkbox" || type === "radio" || type === "file";
    }
    return false;
  }

  if (event.type !== "click") return false;

  const button = target.closest<HTMLButtonElement>("button");
  if (!button || button.closest(".create-summary")) return false;
  if (button.disabled) return false;

  if (button.closest(".generation-quantity-panel")) return true;
  if (button.matches(".variant-row") || button.matches(".saved-reference-pick")) return true;
  if (button.closest(".upload-list")) return true;

  const panel = button.closest<HTMLElement>(".panel");
  const label = panel?.querySelector<HTMLElement>(":scope > .label")?.textContent?.trim();
  // Scenario changes always mutate the payload. Media filtering can also switch
  // the selected model automatically, so mark it stale and let the short
  // no-request fallback release the guard when selection did not actually move.
  return label === "Режим" || label === "Модель";
}

export function GenerationQuoteFreshnessGuard() {
  const staleRef = useRef(false);
  const draftVersionRef = useRef(0);
  const quoteSerialRef = useRef(0);
  const latestQuoteSerialRef = useRef(0);
  const timeoutRef = useRef<number | null>(null);
  const noRequestTimeoutRef = useRef<number | null>(null);

  useLayoutEffect(() => {
    const clearTimers = () => {
      if (timeoutRef.current !== null) window.clearTimeout(timeoutRef.current);
      if (noRequestTimeoutRef.current !== null) window.clearTimeout(noRequestTimeoutRef.current);
      timeoutRef.current = null;
      noRequestTimeoutRef.current = null;
    };

    const syncMarker = () => {
      const box = quoteBox();
      const button = createButton();
      if (staleRef.current) {
        box?.setAttribute(STALE_ATTR, "true");
        if (button) {
          button.setAttribute(STALE_ATTR, "true");
          button.setAttribute("aria-disabled", "true");
        }
      } else {
        box?.removeAttribute(STALE_ATTR);
        if (button?.getAttribute(STALE_ATTR) === "true") {
          button.removeAttribute(STALE_ATTR);
          button.removeAttribute("aria-disabled");
        }
      }
    };

    const release = () => {
      staleRef.current = false;
      clearTimers();
      syncMarker();
    };

    const markStale = () => {
      staleRef.current = true;
      draftVersionRef.current += 1;
      const version = draftVersionRef.current;
      const quoteSerialAtMutation = latestQuoteSerialRef.current;
      clearTimers();
      syncMarker();
      timeoutRef.current = window.setTimeout(release, STALE_TIMEOUT_MS);
      // Some UI clicks only open/filter a model picker and do not change the
      // actual generation payload. If no new quote request starts, release after
      // the normal 300ms quote debounce plus a generous render margin.
      noRequestTimeoutRef.current = window.setTimeout(() => {
        if (
          staleRef.current
          && draftVersionRef.current === version
          && latestQuoteSerialRef.current === quoteSerialAtMutation
        ) release();
      }, 900);
    };

    const invalidate = (event: Event) => {
      if (relevantDraftMutation(event)) markStale();
    };

    const blockStaleCreate = (event: MouseEvent) => {
      if (!staleRef.current) return;
      const target = event.target;
      if (!(target instanceof Element)) return;
      const button = target.closest<HTMLButtonElement>(".create-screen .create-summary button.primary");
      if (!button) return;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      syncMarker();
    };

    const originalFetch = window.fetch.bind(window);
    const patchedFetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      if (!isQuoteRequest(input, init)) return originalFetch(input, init);

      const requestDraftVersion = draftVersionRef.current;
      const requestSerial = ++quoteSerialRef.current;
      latestQuoteSerialRef.current = requestSerial;
      if (noRequestTimeoutRef.current !== null) {
        window.clearTimeout(noRequestTimeoutRef.current);
        noRequestTimeoutRef.current = null;
      }

      const response = await originalFetch(input, init);
      if (!response.ok || !staleRef.current) return response;
      if (
        requestDraftVersion !== draftVersionRef.current
        || requestSerial !== latestQuoteSerialRef.current
      ) return response;

      let expected = "";
      try {
        const payload = await response.clone().json();
        // The Create UI deliberately displays retail `cost_rox`; admin-free and
        // other billing entitlements are explained separately. Match the same
        // field here so freshness follows what the customer can actually see.
        expected = `${compact(payload?.cost_rox ?? payload?.effective_cost_rox)} ROX`;
      } catch {
        expected = "";
      }

      const releaseWhenRendered = () => {
        if (!staleRef.current) return;
        if (
          requestDraftVersion !== draftVersionRef.current
          || requestSerial !== latestQuoteSerialRef.current
        ) return;
        const button = createButton();
        const text = (button?.textContent || "").replace(/\s+/g, " ").trim();
        if (expected && !text.includes(expected)) {
          window.requestAnimationFrame(releaseWhenRendered);
          return;
        }
        release();
      };
      window.requestAnimationFrame(releaseWhenRendered);
      return response;
    }) as typeof window.fetch;

    document.addEventListener("input", invalidate, true);
    document.addEventListener("change", invalidate, true);
    document.addEventListener("click", invalidate, true);
    document.addEventListener("click", blockStaleCreate, true);
    const observer = new MutationObserver(syncMarker);
    observer.observe(document.body, { childList: true, subtree: true });
    window.fetch = patchedFetch;

    return () => {
      document.removeEventListener("input", invalidate, true);
      document.removeEventListener("change", invalidate, true);
      document.removeEventListener("click", invalidate, true);
      document.removeEventListener("click", blockStaleCreate, true);
      observer.disconnect();
      if (window.fetch === patchedFetch) window.fetch = originalFetch;
      staleRef.current = false;
      clearTimers();
      syncMarker();
    };
  }, []);

  return <style jsx global>{`
    .create-screen .create-summary button.primary[${STALE_ATTR}="true"]{opacity:.56;cursor:wait;pointer-events:none}
    .create-screen .quote-box[${STALE_ATTR}="true"]{opacity:.72}
  `}</style>;
}
