"use client";

import { useLayoutEffect, useRef } from "react";

const SUBMIT_LOCK_ATTR = "data-roxy-submit-locked";
const LOCK_TIMEOUT_MS = 15_000;

function requestUrl(input: RequestInfo | URL): string {
  return typeof input === "string" || input instanceof URL ? String(input) : input.url;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function isGenerationCreate(input: RequestInfo | URL, init?: RequestInit): boolean {
  if (requestMethod(input, init) !== "POST") return false;
  try {
    const url = new URL(requestUrl(input), window.location.href);
    return url.pathname === "/api/v1/generations";
  } catch {
    return false;
  }
}

function createButtonFromEvent(event: MouseEvent): HTMLButtonElement | null {
  const target = event.target;
  if (!(target instanceof Element)) return null;
  return target.closest<HTMLButtonElement>(".create-screen .create-summary button.primary");
}

export function GenerationSubmitGuard() {
  const lockedRef = useRef(false);
  const timeoutRef = useRef<number | null>(null);

  useLayoutEffect(() => {
    const unlock = () => {
      lockedRef.current = false;
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      document.querySelector<HTMLButtonElement>(`.create-summary button[${SUBMIT_LOCK_ATTR}="true"]`)?.removeAttribute(SUBMIT_LOCK_ATTR);
    };

    const lock = (button: HTMLButtonElement) => {
      lockedRef.current = true;
      button.setAttribute(SUBMIT_LOCK_ATTR, "true");
      if (timeoutRef.current !== null) window.clearTimeout(timeoutRef.current);
      timeoutRef.current = window.setTimeout(unlock, LOCK_TIMEOUT_MS);
    };

    const guardClick = (event: MouseEvent) => {
      const button = createButtonFromEvent(event);
      if (!button) return;
      if (lockedRef.current) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        return;
      }
      if (button.disabled || button.getAttribute("aria-disabled") === "true") return;
      lock(button);
    };

    const originalFetch = window.fetch.bind(window);
    const patchedFetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const generationCreate = isGenerationCreate(input, init);
      try {
        return await originalFetch(input, init);
      } finally {
        if (generationCreate) unlock();
      }
    }) as typeof window.fetch;

    document.addEventListener("click", guardClick, true);
    window.fetch = patchedFetch;
    return () => {
      document.removeEventListener("click", guardClick, true);
      if (window.fetch === patchedFetch) window.fetch = originalFetch;
      unlock();
    };
  }, []);

  return null;
}
