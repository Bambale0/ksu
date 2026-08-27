"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { openTelegramShare } from "@/lib/telegram";
import type { FeedSurface } from "@/lib/types";

type PublishedPrompt = {
  id: string;
  surface: FeedSurface;
  shared?: boolean;
  error?: string;
};

export function PostPublishSharePrompt() {
  const [published, setPublished] = useState<PublishedPrompt | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onPublished = (event: WindowEventMap["roxy:published"]) => {
      setPublished({ id: event.detail.id, surface: event.detail.surface });
    };
    window.addEventListener("roxy:published", onPublished);
    return () => window.removeEventListener("roxy:published", onPublished);
  }, []);

  if (!published) return null;

  const share = async () => {
    setBusy(true);
    setPublished((current) => current ? { ...current, error: undefined } : current);
    try {
      const result = await api.share(published.id, published.surface);
      if (!result.link) throw new Error("Не удалось получить ссылку на публикацию");
      const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(result.link)}&text=${encodeURIComponent("Смотри, что сделали в ROXY ✨")}`;
      openTelegramShare(shareUrl);
      setPublished((current) => current ? { ...current, shared: true } : current);
    } catch (reason) {
      setPublished((current) => current ? {
        ...current,
        error: reason instanceof Error ? reason.message : "Не удалось поделиться публикацией",
      } : current);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="toast post-publish-share-prompt" role="status">
      <span>{published.error || (published.shared ? "Открываю отправку в Telegram" : "Работа опубликована")}</span>
      <button type="button" disabled={busy} onClick={() => void share()}>
        {busy ? "Готовлю…" : "Поделиться"}
      </button>
      <button type="button" aria-label="Закрыть" onClick={() => setPublished(null)}>×</button>
    </div>
  );
}
