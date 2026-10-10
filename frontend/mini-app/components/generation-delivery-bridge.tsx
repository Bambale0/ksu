"use client";

import { useEffect } from "react";
import { api } from "@/lib/api";
import {
  announceGenerationUpdate,
  GENERATION_TRACK_EVENT,
  isGenerationMediaReady,
  isGenerationMediaFailed,
  isGenerationId,
  isTerminalGeneration,
  readPendingGenerationIds,
  savePendingGenerationIds,
} from "@/lib/generation-delivery";

type PollState = {
  nextAt: number;
  errors: number;
  signature: string;
  waitingSince: number | null;
  warnedAboutIngest: boolean;
};

const ACTIVE_POLL_MS = 2200;
const INGEST_POLL_MS = 4000;
const MAX_RETRY_MS = 30000;
const MAX_IN_FLIGHT = 4;
const MAX_MEDIA_WAIT_MS = 10 * 60 * 1000;
const SLOW_INGEST_POLL_MS = 60000;
const MAX_TRACK_AGE_MS = 7 * 24 * 60 * 60 * 1000;
const MAX_DISCOVERY_RETRIES = 5;

// One observer per authenticated Mini App WebView, shared by all routes.
// It never depends on whether a private Telegram chat exists.
export function GenerationDeliveryBridge() {
  useEffect(() => {
    const pending = new Map<string, PollState>();
    const beforeIdentity = new Set<string>();
    let identity: number | null = null;
    let disposed = false;
    let connecting = false;
    let polling = false;
    let timer: number | null = null;
    let lastDiscovery = 0;
    let discoveryAttempts = 0;
    let discoveryTimer: number | null = null;

    const visible = () => document.visibilityState !== "hidden" && navigator.onLine !== false;

    const cancelTimer = () => {
      if (timer !== null) window.clearTimeout(timer);
      timer = null;
    };

    const persist = () => {
      if (identity !== null) savePendingGenerationIds(identity, [...pending.keys()]);
    };

    const schedule = (delay: number) => {
      cancelTimer();
      if (!disposed && visible()) {
        timer = window.setTimeout(() => { void cycle(); }, delay);
      }
    };

    const addTasks = (ids: string[]) => {
      let added = false;
      for (const id of ids) {
        if (!isGenerationId(id) || pending.has(id)) continue;
        pending.set(id, { nextAt: 0, errors: 0, signature: "", waitingSince: null, warnedAboutIngest: false });
        added = true;
      }
      if (added) persist();
      if (pending.size) schedule(0);
    };

    async function pollOne(id: string): Promise<void> {
      const state = pending.get(id);
      if (!state) return;
      try {
        const item = await api.generation(id);
        if (disposed || !pending.has(id)) return;
        const terminal = isTerminalGeneration(item.status);
        const ready = isGenerationMediaReady(item);
        const mediaFailed = isGenerationMediaFailed(item);
        const createdAt = item.created_at ? new Date(item.created_at).getTime() : Date.now();
        const pastDeadline = Number.isFinite(createdAt) && Date.now() - createdAt > MAX_TRACK_AGE_MS;
        const mediaTimedOut = item.status === "succeeded" && !ready && !mediaFailed && pastDeadline;
        const trackingExpired = !terminal && pastDeadline;
        const signature = JSON.stringify([
          item.status, item.updated_at, item.error,
          // Signed media URLs rotate; only asset identities and delivery counts change state.
          item.media?.map((asset) => [asset.id, asset.ordinal, asset.kind, asset.content_type]),
          item.media_delivery, mediaTimedOut, trackingExpired,
        ]);
        if (signature !== state.signature) {
          state.signature = signature;
          announceGenerationUpdate({
            generation: item, terminal: terminal || trackingExpired, ready,
            mediaFailed, mediaTimedOut, trackingExpired,
          });
          if (terminal && (ready || mediaFailed || mediaTimedOut || item.status !== "succeeded")) {
            console.info("roxy_generation_delivery_complete", { generation_id: id, status: item.status, media_ready: ready });
          }
        }
        if (trackingExpired || terminal && (item.status !== "succeeded" || ready || mediaFailed || mediaTimedOut)) {
          pending.delete(id);
          persist();
          return;
        }
        if (terminal && state.waitingSince === null) state.waitingSince = Date.now();
        const mediaWaitMs = state.waitingSince === null ? 0 : Date.now() - state.waitingSince;
        if (terminal && mediaWaitMs > MAX_MEDIA_WAIT_MS && !state.warnedAboutIngest) {
          // Retain the pending UUID: never silently lose a result if ingest is late.
          state.warnedAboutIngest = true;
          console.warn("roxy_generation_media_delayed", { generation_id: id });
        }
        state.errors = 0;
        state.nextAt = Date.now() + (terminal
          ? (mediaWaitMs > MAX_MEDIA_WAIT_MS ? SLOW_INGEST_POLL_MS : INGEST_POLL_MS)
          : ACTIVE_POLL_MS);
      } catch (error) {
        if (disposed || !pending.has(id)) return;
        const message = error instanceof Error ? error.message : "";
        if (message.includes("Данные не найдены") || message.includes("Недостаточно прав")) {
          pending.delete(id);
          persist();
          return;
        }
        state.errors += 1;
        state.nextAt = Date.now() + Math.min(MAX_RETRY_MS, 2000 * 2 ** Math.min(state.errors, 4));
        if (state.errors === 1 || state.errors === 5) {
          console.warn("roxy_generation_delivery_retry", { generation_id: id, attempt: state.errors });
        }
      }
    }

    async function cycle(): Promise<void> {
      timer = null;
      if (disposed || !visible() || polling) return;
      if (identity === null) {
        void connect();
        return;
      }
      const now = Date.now();
      const due = [...pending.entries()]
        .filter(([, state]) => state.nextAt <= now)
        .slice(0, MAX_IN_FLIGHT)
        .map(([id]) => id);
      if (!due.length) {
        if (pending.size) {
          const nextAt = Math.min(...[...pending.values()].map((state) => state.nextAt));
          schedule(Math.max(250, nextAt - now));
        }
        return;
      }
      polling = true;
      try {
        await Promise.all(due.map(pollOne));
      } finally {
        polling = false;
        if (pending.size) schedule(150);
      }
    }

    async function discover(): Promise<void> {
      if (identity === null || disposed || !visible()) return;
      if (Date.now() - lastDiscovery < 10000) return;
      // One bounded retry timer also works if there are no known pending IDs.
      if (discoveryTimer !== null) {
        window.clearTimeout(discoveryTimer);
        discoveryTimer = null;
      }
      try {
        const page = await api.generations("limit=24");
        if (disposed) return;
        lastDiscovery = Date.now();
        discoveryAttempts = 0;
        addTasks(page.items.filter((item) => {
          const created = item.created_at ? new Date(item.created_at).getTime() : Date.now();
          const recent = Number.isFinite(created) && Date.now() - created < MAX_TRACK_AGE_MS;
          return recent && (!isTerminalGeneration(item.status) ||
            (item.status === "succeeded" && !isGenerationMediaReady(item) && !isGenerationMediaFailed(item)));
        }).map((item) => item.id));
      } catch {
        discoveryAttempts += 1;
        if (!disposed && discoveryAttempts <= MAX_DISCOVERY_RETRIES) {
          const delay = Math.min(MAX_RETRY_MS, 2000 * 2 ** Math.min(discoveryAttempts, 4));
          discoveryTimer = window.setTimeout(() => {
            discoveryTimer = null;
            void discover();
          }, delay);
        }
      }
    }

    async function connect(): Promise<void> {
      if (identity !== null || connecting || disposed || !visible()) return;
      connecting = true;
      try {
        const me = await api.me();
        if (disposed || !Number.isSafeInteger(me.telegram_id) || me.telegram_id <= 0) return;
        identity = me.telegram_id;
        const deepLinkId = new URLSearchParams(window.location.search).get("generation");
        addTasks([
          ...readPendingGenerationIds(identity),
          ...beforeIdentity,
          ...(deepLinkId ? [deepLinkId] : []),
        ]);
        beforeIdentity.clear();
        await discover();
      } catch {
        // Retry when the WebView regains auth/network access.
      } finally {
        connecting = false;
        if (identity === null && !disposed) schedule(5000);
      }
    }

    const onTracked = (event: Event) => {
      const detail = (event as CustomEvent<{ ids?: string[]; telegramId?: number | null }>).detail;
      if (!detail || !Array.isArray(detail.ids)) return;
      if (identity !== null && detail.telegramId && detail.telegramId !== identity) return;
      if (identity === null) {
        detail.ids.forEach((id) => beforeIdentity.add(id));
      } else {
        addTasks(detail.ids);
      }
    };

    const wake = () => {
      if (!visible()) {
        cancelTimer();
        return;
      }
      if (identity === null) void connect();
      else {
        addTasks(readPendingGenerationIds(identity));
        void discover();
        if (pending.size) schedule(0);
      }
    };

    window.addEventListener(GENERATION_TRACK_EVENT, onTracked);
    window.addEventListener("focus", wake);
    window.addEventListener("online", wake);
    window.addEventListener("storage", wake);
    document.addEventListener("visibilitychange", wake);
    void connect();

    return () => {
      disposed = true;
      cancelTimer();
      if (discoveryTimer !== null) window.clearTimeout(discoveryTimer);
      window.removeEventListener(GENERATION_TRACK_EVENT, onTracked);
      window.removeEventListener("focus", wake);
      window.removeEventListener("online", wake);
      window.removeEventListener("storage", wake);
      document.removeEventListener("visibilitychange", wake);
    };
  }, []);

  return null;
}
