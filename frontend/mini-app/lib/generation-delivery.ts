import type { Generation } from "./types";

import { telegram } from "./telegram";

export const GENERATION_TRACK_EVENT = "roxy:generation-track";
const KEY = "roxy.generation-delivery.v1.";
const UUID_RE = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/i;
const MAX_AGE = 7 * 24 * 60 * 60 * 1000;

export function isGenerationId(value: unknown): value is string {
  return typeof value === "string" && UUID_RE.test(value);
}

export function isTerminalGeneration(status: string): boolean {
  return ["succeeded", "completed", "failed", "canceled", "cancelled"].includes(status);
}

export function hasOwnedGenerationMedia(item: Generation): boolean {
  return Boolean(item.media?.some((media) => media.url));
}

export function isGenerationMediaReady(item: Generation): boolean {
  if (item.status !== "succeeded" || !hasOwnedGenerationMedia(item)) return false;
  if (item.media_delivery) return item.media_delivery.state === "ready";
  // Older API releases do not expose ingestion progress; fall back to
  // checking known result count, without trusting a provider URL as delivery.
  return (item.media?.filter((asset) => asset.url).length || 0) >=
    Math.max(1, item.result_urls?.length || 0);
}

export function isGenerationMediaFailed(item: Generation): boolean {
  return item.status === "succeeded" && item.media_delivery?.state === "failed";
}

export function signedUserHint(): number | null {
  const value = Number(telegram()?.initDataUnsafe?.user?.id);
  return Number.isSafeInteger(value) && value > 0 ? value : null;
}

export function readPendingGenerationIds(telegramId: number): string[] {
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(KEY + telegramId) || "[]");
    if (!Array.isArray(value)) return [];
    const now = Date.now();
    return [...new Set(value
      .filter((item): item is { id: string; at: number } =>
        isGenerationId(item?.id) && typeof item.at === "number" &&
        item.at <= now && now - item.at < MAX_AGE)
      .map((item) => item.id))].slice(-32);
  } catch {
    return [];
  }
}

export const GENERATION_UPDATE_EVENT = "roxy:generation-update";
export type GenerationDeliveryUpdate = {
  generation: Generation;
  ready: boolean;
  terminal: boolean;
  mediaFailed?: boolean;
  mediaTimedOut?: boolean;
  trackingExpired?: boolean;
};


export function savePendingGenerationIds(telegramId: number, ids: string[]): void {
  try {
    const now = Date.now();
    const value: unknown = JSON.parse(window.localStorage.getItem(KEY + telegramId) || "[]");
    const previous = new Map<string, number>();
    if (Array.isArray(value)) {
      for (const entry of value) {
        if (isGenerationId(entry?.id) && typeof entry.at === "number") {
          previous.set(entry.id, entry.at);
        }
      }
    }
    const unique = [...new Set(ids.filter(isGenerationId))].slice(-32);
    const tasks = unique.map((id) => ({ id, at: previous.get(id) || now }));
    window.localStorage.setItem(KEY + telegramId, JSON.stringify(tasks));
  } catch {
    // Storage restrictions must not interrupt generation or live polling.
  }
}

export function rememberGenerationIds(ids: string[]): void {
  if (typeof window === "undefined") return;
  const unique = [...new Set(ids.filter(isGenerationId))];
  if (!unique.length) return;
  const telegramId = signedUserHint();
  if (telegramId) {
    savePendingGenerationIds(telegramId, [...readPendingGenerationIds(telegramId), ...unique]);
  }
  window.dispatchEvent(new CustomEvent(GENERATION_TRACK_EVENT, {
    detail: { ids: unique, telegramId },
  }));
}

export function announceGenerationUpdate(detail: GenerationDeliveryUpdate): void {
  window.dispatchEvent(new CustomEvent(GENERATION_UPDATE_EVENT, { detail }));
}

export function subscribeToGenerationUpdates(handler: (update: GenerationDeliveryUpdate) => void): () => void {
  const listener = (event: Event) => handler((event as CustomEvent<GenerationDeliveryUpdate>).detail);
  window.addEventListener(GENERATION_UPDATE_EVENT, listener);
  return () => window.removeEventListener(GENERATION_UPDATE_EVENT, listener);
}
