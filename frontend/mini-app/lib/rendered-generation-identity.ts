import type { Generation } from "./types";

function normalizeUrl(value?: string | null): string {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    return new URL(raw, window.location.href).href;
  } catch {
    return raw;
  }
}

function generationMediaUrls(item: Generation): string[] {
  const urls = [
    item.result_url,
    ...(item.result_urls || []),
    ...(item.media || []).map((media) => media.url || ""),
  ]
    .map(normalizeUrl)
    .filter(Boolean);
  return [...new Set(urls)];
}

function renderedMediaUrl(root: Element): string {
  const media = root.querySelector<HTMLImageElement | HTMLVideoElement | HTMLAudioElement>("img[src], video[src], audio[src]");
  if (!media) return "";
  return normalizeUrl(media.currentSrc || media.getAttribute("src") || "");
}

function dateLabel(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function statusLabel(value?: string | null): string {
  const labels: Record<string, string> = {
    queued: "В очереди",
    submitting: "Запускается",
    generating: "Создаётся",
    retry: "Повторяем",
    succeeded: "Готово",
    failed: "Не получилось",
    canceled: "Отменено",
  };
  return value ? labels[value] || "В работе" : "В работе";
}

function modelTitle(item: Generation): string {
  return item.model && typeof item.model === "object" ? String(item.model.title || "").trim() : "";
}

/**
 * Resolve a rendered History/Preview work back to its Generation without relying
 * on list position. Independent enhancer requests can see a newer list snapshot,
 * so index-based identity can silently target the wrong work.
 *
 * Media URL is the strongest identity. For media-less failed/pending cards we use
 * the exact visible model/date/status fingerprint only when it identifies one
 * generation. Ambiguous matches intentionally return null rather than exposing or
 * acting on another generation's data.
 */
export function resolveRenderedGeneration(root: Element, items: Generation[]): Generation | null {
  const mediaUrl = renderedMediaUrl(root);
  if (mediaUrl) {
    const mediaMatches = items.filter((item) => generationMediaUrls(item).includes(mediaUrl));
    if (mediaMatches.length === 1) return mediaMatches[0];
    if (mediaMatches.length > 1) return null;
  }

  const text = String(root.textContent || "").replace(/\s+/g, " ").trim();
  if (!text) return null;

  const knownStatusLabels = [...new Set(items.map((item) => statusLabel(item.status)))];
  const renderedStatuses = knownStatusLabels.filter((label) => text.includes(label));

  const matches = items.filter((item) => {
    const title = modelTitle(item);
    const date = dateLabel(item.created_at);
    const status = statusLabel(item.status);
    if (title && !text.includes(title)) return false;
    if (date && !text.includes(date)) return false;
    if (renderedStatuses.length && !renderedStatuses.includes(status)) return false;
    return Boolean(title || date || renderedStatuses.length);
  });

  return matches.length === 1 ? matches[0] : null;
}
