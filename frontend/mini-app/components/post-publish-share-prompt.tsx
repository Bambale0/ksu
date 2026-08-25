"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { FeedSurface } from "@/lib/types";

type PublishedPrompt = {
  id: string;
  surface: FeedSurface;
  copied?: boolean;
};

function publishedSurface(payload: any): FeedSurface {
  return payload?.publication_scope === "profile" || payload?.item?.publication_scope === "profile" ? "profile" : "feed";
}

function generationIdFromPublishUrl(url: string): string | null {
  const match = /\/api\/v1\/feed\/([^/]+)\/publish(?:\?|$)/.exec(url);
  return match ? decodeURIComponent(match[1]) : null;
}

async function copyText(value: string | null | undefined): Promise<boolean> {
  if (!value || typeof navigator === "undefined" || !navigator.clipboard) return false;
  await navigator.clipboard.writeText(value);
  return true;
}

export function PostPublishSharePrompt() {
  const [published, setPublished] = useState<PublishedPrompt | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const originalFetch = window.fetch.bind(window);
    window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" || input instanceof URL ? String(input) : input.url;
      const method = String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
      const generationId = method === "POST" ? generationIdFromPublishUrl(url) : null;
      const response = await originalFetch(input, init);
      if (!generationId || !response.ok) return response;
      void response.clone().json()
        .then((payload) => setPublished({ id: payload?.item?.id || generationId, surface: publishedSurface(payload) }))
        .catch(() => setPublished({ id: generationId, surface: "feed" }));
      return response;
    }) as typeof window.fetch;
    return () => {
      window.fetch = originalFetch;
    };
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
