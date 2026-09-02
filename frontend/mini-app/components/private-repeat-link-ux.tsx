"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { privateRepeatApi } from "@/lib/private-repeat-api";
import { resolveRenderedGeneration } from "@/lib/rendered-generation-identity";
import { copyToClipboard, haptic } from "@/lib/telegram";
import type { Generation } from "@/lib/types";

const LINK_SELECTOR = "[data-private-repeat-link]";

export function PrivateRepeatLinkUx() {
  const [toast, setToast] = useState("");
  const toastTimer = useRef<number | null>(null);
  const generations = useRef<Generation[]>([]);
  const nextBefore = useRef<string | null>(null);
  const hasMore = useRef(true);
  const loading = useRef<Promise<void> | null>(null);
  const previewLoads = useRef(new Set<string>());

  const showToast = useCallback((message: string) => {
    setToast(message);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 2400);
  }, []);

  useEffect(() => () => {
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
  }, []);

  useEffect(() => {
    let active = true;
    let queued = false;

    const loadUntil = async (count: number) => {
      if (generations.current.length >= count || !hasMore.current) return;
      if (loading.current) {
        await loading.current;
        if (generations.current.length < count && hasMore.current) await loadUntil(count);
        return;
      }
      const task = (async () => {
        while (active && generations.current.length < count && hasMore.current) {
          const before = nextBefore.current;
          const query = `limit=50${before ? `&before=${encodeURIComponent(before)}` : ""}`;
          const payload = await api.generations(query);
          generations.current = [...generations.current, ...(payload.items || [])];
          nextBefore.current = payload.next_before || null;
          hasMore.current = Boolean(payload.has_more && payload.next_before);
          if (!payload.items?.length) hasMore.current = false;
        }
      })().catch(() => undefined).finally(() => { loading.current = null; });
      loading.current = task;
      await task;
    };

    const loadExactGeneration = async (generationId: string): Promise<Generation | null> => {
      const known = generations.current.find((item) => item.id === generationId);
      if (known) return known;
      if (previewLoads.current.has(generationId)) return null;
      previewLoads.current.add(generationId);
      try {
        const generation = await api.generation(generationId);
        if (active && !generations.current.some((item) => item.id === generation.id)) {
          generations.current = [...generations.current, generation];
        }
        return generation;
      } catch {
        return null;
      }
    };

    const makeButton = (generationId: string) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.privateRepeatLink = generationId;
      button.className = "secondary private-repeat-link-preview";
      button.textContent = "Скопировать ссылку на повтор";
      button.title = "Работа останется приватной";
      button.setAttribute("aria-label", "Скопировать приватную ссылку на повтор");
      return button;
    };

    const decorate = async () => {
      const previewCard = document.querySelector<HTMLElement>(".preview-card");
      const previewActions = previewCard?.querySelector<HTMLElement>(".preview-actions");
      const privatePreview = previewCard?.querySelector<HTMLElement>(".kicker")?.textContent?.trim() === "Моя работа";
      const existingPreview = previewActions?.querySelector<HTMLButtonElement>(LINK_SELECTOR);
      if (!previewCard || !previewActions || !privatePreview) {
        existingPreview?.remove();
        return;
      }

      const cards = Array.from(document.querySelectorAll<HTMLElement>(".history-card"));
      await loadUntil(Math.max(cards.length, 1));
      if (!active) return;

      const fromUrl = new URL(window.location.href).searchParams.get("generation");
      let generation = fromUrl ? generations.current.find((item) => item.id === fromUrl) || null : null;
      if (fromUrl && !generation) generation = await loadExactGeneration(fromUrl);
      if (!generation) generation = resolveRenderedGeneration(previewCard, generations.current);
      if (!active) return;

      // A newer generation can appear between History's request and this enhancer's
      // request. Never fall back to card/list position: an unresolved preview is
      // safer than creating a repeat link for somebody else's work.
      if (!generation || generation.status !== "succeeded" || generation.prompt_actions_allowed === false) {
        existingPreview?.remove();
        return;
      }
      if (!existingPreview) previewActions.appendChild(makeButton(generation.id));
      else existingPreview.dataset.privateRepeatLink = generation.id;
    };

    const schedule = () => {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(() => {
        queued = false;
        void decorate();
      });
    };

    const copyLink = async (button: HTMLButtonElement) => {
      const generationId = String(button.dataset.privateRepeatLink || "");
      if (!generationId || button.disabled) return;
      const original = button.textContent || "Скопировать ссылку на повтор";
      button.disabled = true;
      button.textContent = "Копирую…";
      try {
        const result = await privateRepeatApi.createLink(generationId);
        const copied = await copyToClipboard(result.link);
        if (!copied) throw new Error("Не удалось скопировать ссылку");
        haptic("light");
        button.textContent = "Скопировано ✓";
        showToast("Ссылка на повтор скопирована · работа осталась приватной");
        window.setTimeout(() => {
          if (button.isConnected) button.textContent = original;
        }, 1700);
      } catch (reason) {
        button.textContent = original;
        showToast(reason instanceof Error ? reason.message : "Не удалось создать ссылку повтора");
      } finally {
        button.disabled = false;
      }
    };

    const onClick = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return;
      const button = event.target.closest<HTMLButtonElement>(LINK_SELECTOR);
      if (!button) return;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      void copyLink(button);
    };

    schedule();
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("click", onClick, true);
    return () => {
      active = false;
      observer.disconnect();
      document.removeEventListener("click", onClick, true);
    };
  }, [showToast]);

  return <>
    <style>{`.preview-actions .private-repeat-link-preview:disabled { opacity: .55; }`}</style>
    {toast ? <div className="toast" role="status" data-private-repeat-toast>{toast}</div> : null}
  </>;
}
