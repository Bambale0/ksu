"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { telegramHeaders } from "./telegram";
import type { Draft, UiField } from "./types";

export type SavedReference = {
  id: string;
  kind: "image" | "video" | "audio";
  label?: string | null;
  url: string;
  filename?: string | null;
  content_type?: string | null;
  source?: string | null;
  size_bytes?: number | null;
  duration_ms?: number | null;
  duration_seconds?: number | null;
  width?: number | null;
  height?: number | null;
  container?: string | null;
  video_codec?: string | null;
  audio_codec?: string | null;
  probe_status?: string | null;
  created_at: string;
  updated_at?: string | null;
  last_used_at?: string | null;
};

type UploadResult = {
  url: string;
  name?: string;
  mime_type?: string;
  size?: number;
  replayed?: boolean;
  probe_status?: string;
  duration_ms?: number | null;
  duration_seconds?: number | null;
  width?: number | null;
  height?: number | null;
  reference?: SavedReference;
};

type ReferenceMemoryContextValue = {
  references: SavedReference[];
  upload: (file: File) => Promise<UploadResult>;
  refresh: () => Promise<void>;
  touchUrls: (urls: string[]) => Promise<void>;
  touchDraft: (draft: Draft) => Promise<void>;
  remove: (id: string) => Promise<void>;
};

const ReferenceMemoryContext = createContext<ReferenceMemoryContextValue | null>(null);

async function referenceRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      ...telegramHeaders(Boolean(init.body) && !isForm),
      ...(init.headers || {}),
    },
  });
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail ?? payload?.message ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload as T;
}

function mergeReference(items: SavedReference[], reference: SavedReference): SavedReference[] {
  return [reference, ...items.filter((item) => item.id !== reference.id && item.url !== reference.url)];
}

function collectUrls(value: unknown, target: Set<string>): void {
  if (typeof value === "string") {
    if (/^https:\/\//i.test(value.trim())) target.add(value.trim());
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) collectUrls(item, target);
    return;
  }
  if (value && typeof value === "object") {
    for (const item of Object.values(value as Record<string, unknown>)) collectUrls(item, target);
  }
}

function acceptedKinds(field: UiField): Set<SavedReference["kind"]> {
  const raw = String(field.accept || "image/*,video/*,audio/*").toLowerCase();
  const kinds = new Set<SavedReference["kind"]>();
  if (raw.includes("image/") || raw.includes(".png") || raw.includes(".jpg") || raw.includes(".jpeg") || raw.includes(".webp")) kinds.add("image");
  if (raw.includes("video/") || raw.includes(".mp4") || raw.includes(".mov") || raw.includes(".webm")) kinds.add("video");
  if (raw.includes("audio/") || raw.includes(".mp3") || raw.includes(".wav") || raw.includes(".m4a") || raw.includes(".aac") || raw.includes(".ogg")) kinds.add("audio");
  if (!kinds.size) kinds.add("image");
  return kinds;
}

function referenceFitsField(reference: SavedReference, field: UiField): boolean {
  if (!field.max_size_mb || !reference.size_bytes) return true;
  return reference.size_bytes <= field.max_size_mb * 1024 * 1024;
}

function formatDuration(reference: SavedReference): string | null {
  const seconds = reference.duration_seconds;
  if (!seconds || seconds <= 0) return null;
  if (seconds < 60) return `${seconds}с`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function formatSize(reference: SavedReference): string | null {
  if (!reference.size_bytes || reference.size_bytes <= 0) return null;
  const mb = reference.size_bytes / 1024 / 1024;
  return mb >= 1 ? `${mb.toFixed(mb >= 10 ? 0 : 1)} МБ` : `${Math.ceil(reference.size_bytes / 1024)} КБ`;
}

export function ReferenceMemoryProvider({ children }: { children: ReactNode }) {
  const [references, setReferences] = useState<SavedReference[]>([]);

  const refresh = useCallback(async () => {
    try {
      const payload = await referenceRequest<{ items: SavedReference[] }>("/api/v1/references?limit=50");
      setReferences(payload.items || []);
    } catch {
      // Telegram auth can still be initializing during the first paint. Reference
      // memory is an enhancement; generation itself remains available.
    }
  }, []);

  useEffect(() => {
    void refresh();
    const retry = window.setTimeout(() => void refresh(), 800);
    return () => window.clearTimeout(retry);
  }, [refresh]);

  const upload = useCallback(async (file: File): Promise<UploadResult> => {
    const form = new FormData();
    form.append("file", file, file.name);
    const result = await referenceRequest<UploadResult>("/api/v1/uploads/kie", {
      method: "POST",
      body: form,
    });
    if (result.reference) {
      setReferences((current) => mergeReference(current, result.reference!));
    }
    return result;
  }, []);

  const touchUrls = useCallback(async (rawUrls: string[]) => {
    const urls = [...new Set(rawUrls.map((value) => String(value || "").trim()).filter(Boolean))].slice(0, 64);
    if (!urls.length) return;
    try {
      await referenceRequest<{ touched: number }>("/api/v1/references/touch", {
        method: "POST",
        body: JSON.stringify({ urls }),
      });
      const used = new Set(urls);
      setReferences((current) => [
        ...current.filter((item) => used.has(item.url)),
        ...current.filter((item) => !used.has(item.url)),
      ]);
    } catch {
      // A failed LRU touch must never block choosing a saved reference.
    }
  }, []);

  const touchDraft = useCallback(async (draft: Draft) => {
    const urls = new Set<string>();
    collectUrls(draft.input_url, urls);
    collectUrls(draft.values, urls);
    await touchUrls([...urls]);
  }, [touchUrls]);

  const remove = useCallback(async (id: string) => {
    await referenceRequest<void>(`/api/v1/references/${encodeURIComponent(id)}`, { method: "DELETE" });
    setReferences((current) => current.filter((item) => item.id !== id));
  }, []);

  const value = useMemo<ReferenceMemoryContextValue>(
    () => ({ references, upload, refresh, touchUrls, touchDraft, remove }),
    [references, upload, refresh, touchUrls, touchDraft, remove],
  );

  return <ReferenceMemoryContext.Provider value={value}>{children}</ReferenceMemoryContext.Provider>;
}

export function useReferenceMemory(): ReferenceMemoryContextValue {
  const value = useContext(ReferenceMemoryContext);
  if (!value) throw new Error("ReferenceMemoryProvider is missing");
  return value;
}

export function SavedReferencePicker({
  field,
  value,
  onChange,
}: {
  field: UiField;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const memory = useReferenceMemory();
  const selected = field.control === "files"
    ? (Array.isArray(value) ? value.map(String) : [])
    : value ? [String(value)] : [];
  const selectedKey = selected.join("\n");

  useEffect(() => {
    void memory.refresh();
  }, [memory.refresh, selectedKey]);

  const selectedSet = new Set(selected);
  const kinds = acceptedKinds(field);
  const available = memory.references
    .filter((item) => kinds.has(item.kind) && !selectedSet.has(item.url) && referenceFitsField(item, field))
    .slice(0, 12);

  if (!available.length) return null;

  const choose = (reference: SavedReference) => {
    void memory.touchUrls([reference.url]);
    if (field.control === "file") {
      onChange(reference.url);
      return;
    }
    const maxItems = Math.max(1, field.max_items || 20);
    if (selected.length >= maxItems) return;
    onChange([...selected, reference.url]);
  };

  return (
    <div className="saved-reference-library">
      <div className="saved-reference-head">
        <span>
          <strong>Сохранённые референсы</strong>
          <small>Добавляются только по нажатию</small>
        </span>
        <small>{available.length} доступно</small>
      </div>
      <div className="saved-reference-row">
        {available.map((reference) => {
          const duration = formatDuration(reference);
          const size = formatSize(reference);
          return (
            <div className="saved-reference-card" key={reference.id}>
              <button
                className="saved-reference-pick"
                type="button"
                onClick={() => choose(reference)}
                title={reference.filename || reference.label || "Сохранённый референс"}
              >
                <span className="saved-reference-preview">
                  {reference.kind === "image" ? (
                    <img src={reference.url} alt="" loading="lazy" />
                  ) : (
                    <span aria-hidden="true">{reference.kind === "video" ? "🎬" : "🎵"}</span>
                  )}
                </span>
                <span className="saved-reference-name">
                  {reference.label || reference.filename || (reference.kind === "image" ? "Фото" : reference.kind === "video" ? "Видео" : "Аудио")}
                  {(duration || size) && <small>{[duration, size].filter(Boolean).join(" · ")}</small>}
                  {reference.kind !== "image" && reference.probe_status && reference.probe_status !== "ready" && (
                    <small>Длительность не проверена</small>
                  )}
                </span>
                <span className="saved-reference-plus" aria-hidden="true">＋</span>
              </button>
              <button
                className="saved-reference-delete"
                type="button"
                aria-label="Удалить из сохранённых референсов"
                onClick={() => void memory.remove(reference.id)}
              >
                ×
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
