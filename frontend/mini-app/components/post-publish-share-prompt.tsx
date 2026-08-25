"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { FeedSurface } from "@/lib/types";

type PublishedPrompt = {
  id: string;
  surface: FeedSurface;
  copied?: boolean;
};

async function copyText(value: string | null | undefined): Promise<boolean> {
  if (!value || typeof navigator === "undefined" || !navigator.clipboard) return false;
  await navigator.clipboard.writeText(value);
  return true;
}

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
    try {
      const result = await api.share(published.id, published.surface);
      const copied = await copyText(result.link);
      setPublished((current) => current ? { ...current, copied } : current);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="toast post-publish-share-prompt" role="status">
      <span>{published.copied ? "Ссылка скопирована" : "Работа опубликована"}</span>
      <button type="button" disabled={busy} onClick={() => void share()}>
        {busy ? "Готовлю…" : "Поделиться"}
      </button>
      <button type="button" aria-label="Закрыть" onClick={() => setPublished(null)}>×</button>
    </div>
  );
}
