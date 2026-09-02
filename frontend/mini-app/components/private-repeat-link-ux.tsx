"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { privateRepeatApi } from "@/lib/private-repeat-api";
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
  const selectedGeneration = useRef<string | null>(null);

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

    const makeButton = (generationId: string, preview = false) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.privateRepeatLink = generationId;
      button.dataset.privateRepeatPlacement = preview ? "preview" : "history";
      button.className = preview ? "secondary private-repeat-link-preview" : "private-repeat-link-history";
      button.textContent = "Скопировать ссылку на повтор";
      button.title = "Работа останется приватной";
      button.setAttribute("aria-label", "Скопировать приватную ссылку на повтор");
      return button;
    };

    const decorate = async () => {
      const cards = Array.from(document.querySelectorAll<HTMLElement>(".history-card"));
      if (cards.length) await loadUntil(cards.length);
      if (!active) return;

      cards.forEach((card, index) => {
        const generation = generations.current[index];
        const existing = card.querySelector<HTMLElement>(`${LINK_SELECTOR}[data-private-repeat-placement='history']`);
        if (!generation || generation.status !== "succeeded" || generation.prompt_actions_allowed === false) {
          existing?.remove();
          return;
        }
        if (!existing) card.appendChild(makeButton(generation.id));
      });

      const previewActions = document.querySelector<HTMLElement>(".preview-card .preview-actions");
      const privatePreview = document.querySelector<HTMLElement>(".preview-card .kicker")?.textContent?.trim() === "Моя работа";
      const existingPreview = previewActions?.querySelector<HTMLElement>(`${LINK_SELECTOR}[data-private-repeat-placement='preview']`);
      if (!previewActions || !privatePreview) {
        existingPreview?.remove();
        return;
      }
      const fromUrl = new URL(window.location.href).searchParams.get("generation");
      const generationId = selectedGeneration.current || fromUrl;
      const generation = generationId ? generations.current.find((item) => item.id === generationId) : null;
      if (!generation || generation.status !== "succeeded" || generation.prompt_actions_allowed === false) {
        existingPreview?.remove();
        return;
      }
      if (!existingPreview) previewActions.appendChild(makeButton(generation.id, true));
      else existingPreview.dataset.privateRepeatLink = generation.id;
    };

    const cardFromTarget = (target: EventTarget | null): HTMLElement | null => {
      if (!(target instanceof Element)) return null;
      return target.closest<HTMLElement>(".history-card");
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
      if (event.target instanceof Element) {
        const button = event.target.closest<HTMLButtonElement>(LINK_SELECTOR);
        if (button) {
          event.preventDefault();
          event.stopPropagation();
          event.stopImmediatePropagation();
          void copyLink(button);
          return;
        }
      }
      const card = cardFromTarget(event.target);
      if (!card) return;
      const cards = Array.from(document.querySelectorAll<HTMLElement>(".history-card"));
      const index = cards.indexOf(card);
      if (index >= 0) {
        void loadUntil(index + 1).then(() => {
          selectedGeneration.current = generations.current[index]?.id || null;
        });
      }
    };

    let queued = false;
    const schedule = () => {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(() => {
        queued = false;
        void decorate();
      });
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
    <style>{`
      .history-card .private-repeat-link-history {
        grid-column: 1 / -1;
        min-height: 34px;
        margin-top: 5px;
        border: 1px solid rgba(190, 125, 255, .24);
        border-radius: 10px;
        background: rgba(155, 92, 255, .09);
        color: #e6d4ff;
        font-size: 10px;
        font-weight: 800;
      }
      .history-card .private-repeat-link-history:disabled,
      .preview-actions .private-repeat-link-preview:disabled { opacity: .55; }
    `}</style>
    {toast ? <div className="toast" role="status" data-private-repeat-toast>{toast}</div> : null}
  </>;
}
