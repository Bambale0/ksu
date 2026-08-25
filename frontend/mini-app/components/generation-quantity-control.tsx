"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "@/lib/api";

const DEFAULT_MAX_GENERATION_QUANTITY = 6;

declare global {
  interface Window {
    __roxyGenerationQuantity?: number;
    __roxyMaxGenerationQuantity?: number;
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

function targetGenerationRequest(input: RequestInfo | URL, init?: RequestInit): boolean {
  const url = typeof input === "string" || input instanceof URL ? String(input) : input.url;
  const method = String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
  if (method !== "POST") return false;
  return url.endsWith("/api/v1/generations") || url.endsWith("/api/v1/generations/quote");
}

function withQuantity(init: RequestInit | undefined, quantity: number, maxQuantity: number): RequestInit | undefined {
  if (!init?.body || typeof init.body !== "string") return init;
  try {
    const payload = JSON.parse(init.body) as Record<string, unknown>;
    return {
      ...init,
      body: JSON.stringify({ ...payload, quantity: coerceQuantity(payload.quantity || quantity, maxQuantity) }),
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
      .catch(() => setMaxQuantity(DEFAULT_MAX_GENERATION_QUANTITY));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    maxQuantityRef.current = maxQuantity;
    window.__roxyMaxGenerationQuantity = maxQuantity;
    setQuantity((current) => coerceQuantity(current, maxQuantity));
  }, [maxQuantity]);

  useEffect(() => {
    quantityRef.current = coerceQuantity(quantity, maxQuantity);
    window.__roxyGenerationQuantity = quantityRef.current;
  }, [maxQuantity, quantity]);

  useEffect(() => {
    const originalFetch = window.fetch.bind(window);
    window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const nextInit = targetGenerationRequest(input, init)
        ? withQuantity(init, quantityRef.current, maxQuantityRef.current)
        : init;
      return originalFetch(input, nextInit);
    }) as typeof window.fetch;
    return () => {
      window.fetch = originalFetch;
    };
  }, []);

  useEffect(() => {
    const syncHost = () => {
      const controls = document.querySelector<HTMLElement>(".create-screen .create-controls");
      if (!controls) {
        setHost(null);
        return;
      }
      let next = controls.querySelector<HTMLElement>(":scope > [data-generation-quantity-control]");
      if (!next) {
        next = document.createElement("div");
        next.dataset.generationQuantityControl = "true";
        controls.appendChild(next);
      }
      setHost(next);
    };
    syncHost();
    const observer = new MutationObserver(syncHost);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
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
              setQuantity(count);
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