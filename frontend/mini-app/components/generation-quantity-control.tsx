"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "@/lib/api";

const DEFAULT_MAX_GENERATION_QUANTITY = 4;
const LEGACY_HIDDEN_ATTR = "data-roxy-legacy-quantity-hidden";

type PublishDetail = {
  id: string;
  surface: "feed" | "profile";
};

declare global {
  interface Window {
    __roxyGenerationQuantity?: number;
    __roxyMaxGenerationQuantity?: number;
  }

  interface WindowEventMap {
    "roxy:published": CustomEvent<PublishDetail>;
  }
}

function coerceMaxQuantity(value: unknown): number {
  const numeric = Number(value || DEFAULT_MAX_GENERATION_QUANTITY);
  if (!Number.isFinite(numeric)) return DEFAULT_MAX_GENERATION_QUANTITY;
  return Math.min(DEFAULT_MAX_GENERATION_QUANTITY, Math.max(1, Math.trunc(numeric)));
}

function coerceQuantity(value: unknown, maxQuantity = DEFAULT_MAX_GENERATION_QUANTITY): number {
  const numeric = Number(value || 1);
  if (!Number.isFinite(numeric)) return 1;
  return Math.min(maxQuantity, Math.max(1, Math.trunc(numeric)));
}

function requestUrl(input: RequestInfo | URL): string {
  return typeof input === "string" || input instanceof URL ? String(input) : input.url;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function targetGenerationRequest(input: RequestInfo | URL, init?: RequestInit): boolean {
  const url = requestUrl(input);
  if (requestMethod(input, init) !== "POST") return false;
  return url.endsWith("/api/v1/generations") || url.endsWith("/api/v1/generations/quote");
}

function publishedGenerationId(input: RequestInfo | URL, init?: RequestInit): string | null {
  if (requestMethod(input, init) !== "POST") return null;
  const match = /\/api\/v1\/feed\/([^/]+)\/publish(?:\?|$)/.exec(requestUrl(input));
  return match ? decodeURIComponent(match[1]) : null;
}

function publishedSurface(payload: any): "feed" | "profile" {
  return payload?.publication_scope === "profile" || payload?.item?.publication_scope === "profile" ? "profile" : "feed";
}

function emitPublished(response: Response, fallbackId: string) {
  void response.clone().json()
    .then((payload) => {
      window.dispatchEvent(new CustomEvent<PublishDetail>("roxy:published", {
        detail: { id: payload?.item?.id || fallbackId, surface: publishedSurface(payload) },
      }));
    })
    .catch(() => {
      window.dispatchEvent(new CustomEvent<PublishDetail>("roxy:published", {
        detail: { id: fallbackId, surface: "feed" },
      }));
    });
}

function withQuantity(init: RequestInit | undefined, quantity: number, maxQuantity: number): RequestInit | undefined {
  if (!init?.body || typeof init.body !== "string") return init;
  try {
    const payload = JSON.parse(init.body) as Record<string, unknown>;
    return {
      ...init,
      body: JSON.stringify({ ...payload, quantity: coerceQuantity(quantity, maxQuantity) }),
    };
  } catch {
    return init;
  }
}

function dispatchTextareaInput(textarea: HTMLTextAreaElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
  setter?.call(textarea, value);
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
  textarea.dispatchEvent(new Event("change", { bubbles: true }));
}

function triggerQuoteRefresh() {
  const prompt = document.querySelector<HTMLTextAreaElement>(".create-screen textarea.control");
  if (!prompt) return;
  const current = prompt.value;
  const temporary = current.endsWith(" ") ? current.slice(0, -1) : `${current} `;
  dispatchTextareaInput(prompt, temporary);
  window.setTimeout(() => dispatchTextareaInput(prompt, current), 0);
}

function legacyQuantityPanel(): HTMLElement | null {
  for (const label of document.querySelectorAll<HTMLElement>(".create-screen .create-controls .panel > .label")) {
    const panel = label.closest<HTMLElement>(".panel");
    if (
      (label.textContent || "").trim() === "Количество запусков"
      && panel
      && !panel.classList.contains("generation-quantity-panel")
    ) {
      return panel;
    }
  }
  return null;
}

function legacyQuantityButtons(panel: HTMLElement): Array<{ button: HTMLButtonElement; count: number }> {
  return Array.from(panel.querySelectorAll<HTMLButtonElement>("button"))
    .map((button) => ({ button, count: Number((button.textContent || "").trim()) }))
    .filter((item) => Number.isInteger(item.count) && item.count >= 1);
}

function selectLegacyQuantity(count: number): void {
  const panel = legacyQuantityPanel();
  if (!panel) return;
  legacyQuantityButtons(panel).find((item) => item.count === count)?.button.click();
}

export function GenerationQuantityControl() {
  const [quantity, setQuantity] = useState(1);
  const [maxQuantity, setMaxQuantity] = useState(DEFAULT_MAX_GENERATION_QUANTITY);
  const [host, setHost] = useState<HTMLElement | null>(null);
  const quantityRef = useRef(1);
  const maxQuantityRef = useRef(DEFAULT_MAX_GENERATION_QUANTITY);

  useEffect(() => {
    let active = true;
    void api.models()
      .then((payload) => {
        if (!active) return;
        setMaxQuantity(coerceMaxQuantity(payload.max_generation_quantity));
      })
      .catch(() => {
        if (active) setMaxQuantity(DEFAULT_MAX_GENERATION_QUANTITY);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    maxQuantityRef.current = maxQuantity;
    window.__roxyMaxGenerationQuantity = maxQuantity;
    const clamped = coerceQuantity(quantityRef.current, maxQuantity);
    quantityRef.current = clamped;
    window.__roxyGenerationQuantity = clamped;
    setQuantity((current) => current === clamped ? current : clamped);
  }, [maxQuantity]);

  useEffect(() => {
    quantityRef.current = coerceQuantity(quantity, maxQuantity);
    window.__roxyGenerationQuantity = quantityRef.current;
  }, [maxQuantity, quantity]);

  useEffect(() => {
    const originalFetch = window.fetch.bind(window);
    const patchedFetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const publishId = publishedGenerationId(input, init);
      const nextInit = targetGenerationRequest(input, init)
        ? withQuantity(init, quantityRef.current, maxQuantityRef.current)
        : init;
      const response = await originalFetch(input, nextInit);
      if (publishId && response.ok) emitPublished(response, publishId);
      return response;
    }) as typeof window.fetch;
    window.fetch = patchedFetch;
    return () => {
      if (window.fetch === patchedFetch) window.fetch = originalFetch;
    };
  }, []);

  useEffect(() => {
    const sync = () => {
      const controls = document.querySelector<HTMLElement>(".create-screen .create-controls");
      if (!controls) {
        setHost(null);
        return;
      }

      const legacy = legacyQuantityPanel();
      if (legacy) {
        const alreadySynced = legacy.getAttribute(LEGACY_HIDDEN_ATTR) === "true";
        const buttons = legacyQuantityButtons(legacy);
        const active = buttons.find(({ button }) => button.classList.contains("active"));
        const intended = coerceQuantity(quantityRef.current, maxQuantityRef.current);
        const next = alreadySynced
          ? intended
          : coerceQuantity(active?.count || intended, maxQuantityRef.current);

        if (!alreadySynced) {
          quantityRef.current = next;
          window.__roxyGenerationQuantity = next;
          setQuantity(next);
        }

        if (active?.count !== next) {
          buttons.find(({ count }) => count === next)?.button.click();
        }

        legacy.hidden = true;
        legacy.setAttribute("aria-hidden", "true");
        legacy.setAttribute(LEGACY_HIDDEN_ATTR, "true");
      }

      let next = controls.querySelector<HTMLElement>(":scope > [data-generation-quantity-control]");
      if (!next) {
        next = document.createElement("div");
        next.dataset.generationQuantityControl = "true";
        controls.appendChild(next);
      }
      setHost(next);
    };

    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      for (const panel of document.querySelectorAll<HTMLElement>(`[${LEGACY_HIDDEN_ATTR}="true"]`)) {
        panel.hidden = false;
        panel.removeAttribute("aria-hidden");
        panel.removeAttribute(LEGACY_HIDDEN_ATTR);
      }
    };
  }, []);

  if (!host) return null;

  return createPortal(
    <div className="panel generation-quantity-panel">
      <label className="label">Количество запусков</label>
      <div className="segmented scrollable" aria-label="Количество запусков">
        {Array.from({ length: maxQuantity }, (_, index) => index + 1).map((count) => (
          <button
            key={count}
            type="button"
            className={quantity === count ? "active" : ""}
            aria-pressed={quantity === count}
            onClick={() => {
              quantityRef.current = count;
              window.__roxyGenerationQuantity = count;
              setQuantity(count);
              selectLegacyQuantity(count);
              window.setTimeout(triggerQuoteRefresh, 0);
            }}
          >
            {count}
          </button>
        ))}
      </div>
      <p className="muted">{quantity > 1 ? `Стоимость за ${quantity}` : "Один запуск"}. Каждый запуск создаёт отдельную работу.</p>
    </div>,
    host,
  );
}
