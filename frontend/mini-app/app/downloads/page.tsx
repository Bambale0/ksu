"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { customerRequest, dateTime } from "@/lib/customer-api";
import type { Generation } from "@/lib/types";
import { subscribeToGenerationUpdates } from "@/lib/generation-delivery";
import { requestTelegramDownload } from "@/lib/telegram";

type OwnedMedia = { id?: string; url?: string; download_url?: string; download_filename?: string; public_url?: string; content_type?: string | null; size_bytes?: number | null; ordinal?: number };
type GenerationWithMedia = Omit<Generation, "media"> & { media?: OwnedMedia[] };

function sizeLabel(bytes?: number | null): string {
  if (!bytes) return "";
  const mb = bytes / 1024 / 1024;
  return mb >= 1 ? `${mb.toFixed(mb >= 10 ? 0 : 1)} МБ` : `${Math.ceil(bytes / 1024)} КБ`;
}


type DownloadDescriptor = {
  id?: string;
  generation_id?: string;
  status?: string;
  download_url?: string | null;
  download_filename?: string | null;
};

function DownloadButton({ assetId, generationId, label }: {
  assetId: string;
  generationId: string;
  label: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<AbortController | null>(null);

  useEffect(() => () => {
    pending.current?.abort();
    pending.current = null;
  }, []);

  const download = async () => {
    // Guard the same event turn as well as the rendered disabled state.
    if (pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setError("");
    try {
      // Signed capabilities expire while a tab is open. Always request a fresh,
      // owner-authorized descriptor for this exact asset, never a cached href.
      const descriptor = await customerRequest<DownloadDescriptor>(
        "/api/v1/media/" + encodeURIComponent(assetId),
        { signal: controller.signal },
      );
      if (controller.signal.aborted || pending.current !== controller) return;
      if (descriptor?.id !== assetId || descriptor.generation_id !== generationId
          || descriptor.status !== "ready"
          || typeof descriptor.download_url !== "string" || !descriptor.download_url.trim()
          || typeof descriptor.download_filename !== "string" || !descriptor.download_filename.trim()) {
        throw new Error("Файл пока недоступен для скачивания.");
      }
      let target: URL;
      try {
        target = new URL(descriptor.download_url, window.location.href);
      } catch {
        throw new Error("Не удалось получить ссылку для скачивания.");
      }
      if (!["https:", "http:"].includes(target.protocol) || target.username || target.password) {
        throw new Error("Не удалось получить ссылку для скачивания.");
      }
      const filename = descriptor.download_filename.trim();
      if (requestTelegramDownload(target.href, filename)) return;

      // The attachment response downloads in the current browsing context.
      // Opening a new popup after the asynchronous refresh can be blocked.
      const link = document.createElement("a");
      link.href = target.href;
      link.download = filename;
      link.target = "_self";
      link.rel = "noreferrer";
      link.hidden = true;
      document.body.append(link);
      try {
        link.click();
      } finally {
        link.remove();
      }
    } catch (reason) {
      if (controller.signal.aborted || pending.current !== controller) return;
      const message = reason instanceof Error ? reason.message : "Не удалось подготовить скачивание.";
      setError(message.includes("Попробуйте") ? message : message + " Попробуйте ещё раз.");
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        setBusy(false);
      }
    }
  };

  return <span style={{ display: "grid", gap: 4 }}>
    <button type="button" disabled={busy} aria-busy={busy} onClick={() => void download()}>
      {label}{busy ? " · Подготовка…" : ""}
    </button>
    {error ? <small className="action-error" role="alert">{error}</small> : null}
  </span>;
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
              {owned.map((media, index) => <DownloadButton
                key={media.id}
                assetId={media.id!}
                generationId={item.id}
                label={`Скачать ${owned.length > 1 ? index + 1 : ""}${sizeLabel(media.size_bytes) ? ` · ${sizeLabel(media.size_bytes)}` : ""}`.trim()}
              />)}
              {!owned.length && fallback ? <a href={fallback} target="_blank" rel="noreferrer">Открыть результат</a> : null}
            </span>
          </div>;
        }) : <p className="muted">Готовых файлов пока нет.</p>}</div>
      </div>
    </StandaloneShell>
  );
}
