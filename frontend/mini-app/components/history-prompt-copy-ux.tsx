"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { haptic } from "@/lib/telegram";
import type { Generation } from "@/lib/types";

const HISTORY_PROMPT_SELECTOR = "[data-history-prompt-copy]";
const PREVIEW_PROMPT_SELECTOR = ".preview-card .prompt-copy";

async function copyText(value: string): Promise<boolean> {
  const text = value.trim();
  if (!text) return false;

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // iOS Telegram WebView may expose Clipboard API but reject the write.
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.setAttribute("aria-hidden", "true");
  textarea.style.position = "fixed";
  textarea.style.inset = "0 auto auto -9999px";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus({ preventScroll: true });
  textarea.select();
  textarea.setSelectionRange(0, text.length);
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    textarea.remove();
  }
}

function promptFor(item: Generation | undefined): string {
  if (!item?.prompt || item.prompt_hidden) return "";
  return item.prompt.trim();
}

export function HistoryPromptCopyUx() {
  const [toast, setToast] = useState("");
  const toastTimer = useRef<number | null>(null);
  const generations = useRef<Generation[]>([]);
  const nextBefore = useRef<string | null>(null);
  const hasMore = useRef(true);
  const loading = useRef<Promise<void> | null>(null);

  const showToast = useCallback((message: string) => {
    setToast(message);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 2200);
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
          const query = `limit=24${before ? `&before=${encodeURIComponent(before)}` : ""}`;
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

    const decoratePreview = () => {
      for (const node of Array.from(document.querySelectorAll<HTMLElement>(PREVIEW_PROMPT_SELECTOR))) {
        node.dataset.copyablePrompt = "true";
        node.setAttribute("role", "button");
        node.tabIndex = 0;
        node.setAttribute("aria-label", "Скопировать промпт");
        node.title = "Нажмите, чтобы скопировать промпт";
      }
    };

    const decorateHistory = async () => {
      const cards = Array.from(document.querySelectorAll<HTMLElement>(".history-card"));
      decoratePreview();
      if (!cards.length) return;
      await loadUntil(cards.length);
      if (!active) return;

      cards.forEach((card, index) => {
        const prompt = promptFor(generations.current[index]);
        let target = card.querySelector<HTMLElement>(HISTORY_PROMPT_SELECTOR);
        if (!prompt) {
          target?.remove();
          return;
        }
        if (!target) {
          target = document.createElement("span");
          target.dataset.historyPromptCopy = "true";
          target.setAttribute("role", "button");
          target.tabIndex = 0;
          target.setAttribute("aria-label", "Скопировать промпт");
          target.title = "Нажмите, чтобы скопировать промпт";
          card.appendChild(target);
        }
        target.dataset.prompt = prompt;
        if (target.textContent !== prompt) target.textContent = prompt;
      });
    };

    const copyFromTarget = async (target: HTMLElement) => {
      const value = target.matches(HISTORY_PROMPT_SELECTOR)
        ? target.dataset.prompt || target.textContent || ""
        : target.textContent || "";
      const copied = await copyText(value);
      if (copied) {
        haptic("light");
        showToast("Промпт скопирован");
      } else {
        showToast("Не удалось скопировать промпт");
      }
    };

    const findTarget = (eventTarget: EventTarget | null): HTMLElement | null => {
      if (!(eventTarget instanceof Element)) return null;
      return eventTarget.closest<HTMLElement>(`${HISTORY_PROMPT_SELECTOR}, ${PREVIEW_PROMPT_SELECTOR}`);
    };

    const onClick = (event: MouseEvent) => {
      const target = findTarget(event.target);
      if (!target) return;
      event.preventDefault();
      event.stopPropagation();
      if (target.matches(HISTORY_PROMPT_SELECTOR)) event.stopImmediatePropagation();
      void copyFromTarget(target);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const target = findTarget(event.target);
      if (!target) return;
      event.preventDefault();
      event.stopPropagation();
      if (target.matches(HISTORY_PROMPT_SELECTOR)) event.stopImmediatePropagation();
      void copyFromTarget(target);
    };

    let queued = false;
    const scheduleDecorate = () => {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(() => {
        queued = false;
        void decorateHistory();
      });
    };

    scheduleDecorate();
    const observer = new MutationObserver(scheduleDecorate);
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("click", onClick, true);
    document.addEventListener("keydown", onKeyDown, true);

    return () => {
      active = false;
      observer.disconnect();
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, [showToast]);

  return <>
    <style>{`
      .history-card [data-history-prompt-copy] {
        grid-column: 2 / -1;
        min-width: 0;
        margin-top: 1px;
        padding: 6px 8px;
        overflow: hidden;
        border: 1px solid rgba(155, 92, 255, .12);
        border-radius: 9px;
        background: rgba(155, 92, 255, .055);
        color: #d8d3df;
        cursor: copy;
        font-size: 9px;
        font-weight: 500;
        line-height: 1.35;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .history-card [data-history-prompt-copy]:focus-visible,
      .preview-card .prompt-copy[data-copyable-prompt="true"]:focus-visible {
        outline: 2px solid var(--violet-soft);
        outline-offset: 2px;
      }
      .preview-card .prompt-copy[data-copyable-prompt="true"] {
        cursor: copy;
        border: 1px solid rgba(155, 92, 255, .16);
      }
    `}</style>
    {toast ? <div className="toast" role="status" data-history-copy-toast>{toast}</div> : null}
  </>;
}
