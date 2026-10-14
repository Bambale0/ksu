"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { customerRequest, dateTime } from "@/lib/customer-api";
import type { Generation } from "@/lib/types";
import { subscribeToGenerationUpdates } from "@/lib/generation-delivery";

type OwnedMedia = { id?: string; url?: string; download_url?: string; public_url?: string; content_type?: string | null; size_bytes?: number | null; ordinal?: number };
type GenerationWithMedia = Omit<Generation, "media"> & { media?: OwnedMedia[] };

function sizeLabel(bytes?: number | null): string {
  if (!bytes) return "";
  const mb = bytes / 1024 / 1024;
  return mb >= 1 ? `${mb.toFixed(mb >= 10 ? 0 : 1)} МБ` : `${Math.ceil(bytes / 1024)} КБ`;
}

export default function DownloadsPage() {
  const [items, setItems] = useState<GenerationWithMedia[]>([]);
  const [error, setError] = useState("");
  const requestVersion = useRef(0);
  const refreshTimer = useRef<number | null>(null);

  const load = useCallback(async () => {
    const version = ++requestVersion.current;
    setError("");
    try {
      const payload = await customerRequest<{ items: GenerationWithMedia[] }>("/api/v1/generations?limit=50&status=succeeded");
      // Multiple results can finish together; a stale response must never
      // overwrite a more recent owned-media view.
      if (version === requestVersion.current) setItems(payload.items || []);
    } catch (reason) {
      if (version === requestVersion.current) {
        setError(reason instanceof Error ? reason.message : "Не удалось загрузить файлы");
      }
    }
  }, []);

  useEffect(() => {
    void load();
    return () => { requestVersion.current += 1; };
  }, [load]);
  useEffect(() => {
    const unsubscribe = subscribeToGenerationUpdates(({ terminal, ready, generation, mediaFailed }) => {
      if (generation.status === "succeeded" && (generation.media?.length || 0) > 0 ||
          ready || mediaFailed || terminal && generation.status !== "succeeded") {
        if (refreshTimer.current !== null) window.clearTimeout(refreshTimer.current);
        refreshTimer.current = window.setTimeout(() => {
          refreshTimer.current = null;
          void load();
        }, 90);
      }
    });
    return () => {
      unsubscribe();
      if (refreshTimer.current !== null) window.clearTimeout(refreshTimer.current);
    };
  }, [load]);

  return (
    <StandaloneShell kicker="Файлы" title="Скачать результаты" copy="Когда результат уже перенесён в собственное хранилище ROXY, скачивание идёт через защищённую ссылку с корректным именем файла.">
      {error ? <div className="action-error" role="alert">{error}</div> : null}
      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">Готовые работы</span><h2>Оригиналы</h2></div><button type="button" onClick={() => void load()}>Обновить</button></div>
        <div className="transaction-list">{items.length ? items.map((item) => {
          const model = typeof item.model === "object" ? item.model?.title : String(item.model || "ROXY");
          const owned = (item.media || []).filter((media) => media.id && media.download_url);
          const fallback = item.media_delivery ? "" : item.result_url || item.result_urls?.[0] || "";
          const delivery = item.media_delivery;
          return <div className="transaction" key={item.id} style={{ alignItems: "flex-start" }}>
            <div><strong>{model || "ROXY"}</strong><small>{dateTime(item.created_at)}</small>{delivery?.state === "pending" ? <small>Сохраняем файлы: {delivery.ready}/{delivery.expected}</small> : null}{delivery?.state === "failed" ? <small>Не все файлы сохранены: {delivery.ready}/{delivery.expected}</small> : null}{item.prompt && !item.prompt_hidden ? <small>{item.prompt.slice(0, 120)}</small> : null}</div>
            <span style={{ display: "grid", gap: 8 }}>
              {owned.map((media, index) => <a key={media.id} href={media.download_url} target="_blank" rel="noreferrer">Скачать {owned.length > 1 ? index + 1 : ""}{sizeLabel(media.size_bytes) ? ` · ${sizeLabel(media.size_bytes)}` : ""}</a>)}
              {!owned.length && fallback ? <a href={fallback} target="_blank" rel="noreferrer">Открыть результат</a> : null}
            </span>
          </div>;
        }) : <p className="muted">Готовых файлов пока нет.</p>}</div>
      </div>
    </StandaloneShell>
  );
}
