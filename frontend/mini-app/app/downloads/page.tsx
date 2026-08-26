"use client";

import { useEffect, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { customerRequest, dateTime } from "@/lib/customer-api";
import type { Generation } from "@/lib/types";

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

  const load = async () => {
    setError("");
    try {
      const payload = await customerRequest<{ items: GenerationWithMedia[] }>("/api/v1/generations?limit=50&status=succeeded");
      setItems(payload.items || []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить файлы");
    }
  };

  useEffect(() => { void load(); }, []);

  return (
    <StandaloneShell kicker="Файлы" title="Скачать результаты" copy="Когда результат уже перенесён в собственное хранилище ROXY, скачивание идёт через защищённую ссылку с корректным именем файла.">
      {error ? <div className="action-error" role="alert">{error}</div> : null}
      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">Готовые работы</span><h2>Оригиналы</h2></div><button type="button" onClick={() => void load()}>Обновить</button></div>
        <div className="transaction-list">{items.length ? items.map((item) => {
          const model = typeof item.model === "object" ? item.model?.title : String(item.model || "ROXY");
          const owned = (item.media || []).filter((media) => media.id && media.download_url);
          const fallback = item.result_url || item.result_urls?.[0] || "";
          return <div className="transaction" key={item.id} style={{ alignItems: "flex-start" }}>
            <div><strong>{model || "ROXY"}</strong><small>{dateTime(item.created_at)}</small>{item.prompt && !item.prompt_hidden ? <small>{item.prompt.slice(0, 120)}</small> : null}</div>
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
