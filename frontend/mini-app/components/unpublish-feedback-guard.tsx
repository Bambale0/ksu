"use client";

import { useLayoutEffect } from "react";

const WRONG_UNPUBLISH_TOAST = "Работа опубликована в профиле";
const UNPUBLISH_SUCCESS_TOAST = "Публикация убрана";
const UNPUBLISH_FEEDBACK_WINDOW_MS = 10_000;

function requestUrl(input: RequestInfo | URL): string {
  return typeof input === "string" || input instanceof URL ? String(input) : input.url;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function isRemovePublicationRequest(input: RequestInfo | URL, init?: RequestInit): boolean {
  if (requestMethod(input, init) !== "POST") return false;
  try {
    const url = new URL(requestUrl(input), window.location.href);
    return /^\/api\/v1\/feed\/[^/]+\/remove$/.test(url.pathname);
  } catch {
    return false;
  }
}

function toastNode(): HTMLElement | null {
  return document.querySelector<HTMLElement>('.toast[role="status"]');
}

export function UnpublishFeedbackGuard() {
  useLayoutEffect(() => {
    let removeSucceededAt = 0;
    let correctionPending = false;
    const originalFetch = window.fetch.bind(window);

    const correctFeedback = () => {
      if (!correctionPending) return;
      if (!removeSucceededAt || Date.now() - removeSucceededAt > UNPUBLISH_FEEDBACK_WINDOW_MS) {
        correctionPending = false;
        return;
      }
      const toast = toastNode();
      if (!toast || (toast.textContent || "").trim() !== WRONG_UNPUBLISH_TOAST) return;
      toast.textContent = UNPUBLISH_SUCCESS_TOAST;
      toast.dataset.roxyUnpublishFeedback = "true";
      correctionPending = false;
    };

    const patchedFetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const removingPublication = isRemovePublicationRequest(input, init);
      const response = await originalFetch(input, init);
      if (removingPublication && response.ok) {
        removeSucceededAt = Date.now();
        correctionPending = true;
        window.queueMicrotask(correctFeedback);
      }
      return response;
    }) as typeof window.fetch;

    window.fetch = patchedFetch;
    const observer = new MutationObserver(correctFeedback);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });

    return () => {
      observer.disconnect();
      if (window.fetch === patchedFetch) window.fetch = originalFetch;
    };
  }, []);

  return null;
}
