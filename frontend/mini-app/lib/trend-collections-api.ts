"use client";

import { telegramHeaders } from "./telegram";
import type { TrendItem } from "./types";

export type TrendCollection = {
  id: string;
  system_key?: string | null;
  title: string;
  description?: string;
  aliases?: string[];
  sort_order: number;
  is_active: boolean;
  item_count?: number;
  photo_count?: number;
  video_count?: number;
  preview_url?: string | null;
  preview_media_type?: "image" | "video" | null;
};

export type TrendCollectionState = {
  schema_version?: number;
  initialized?: boolean;
  collections: TrendCollection[];
  assignments: Record<string, string>;
};

export type TrendCollectionWrite = {
  title: string;
  description?: string;
  hashtags?: string[];
  sort_order?: number;
  is_active?: boolean;
};

function idempotencyKey(prefix: string): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return `${prefix}:${crypto.randomUUID()}`;
  return `${prefix}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...telegramHeaders(Boolean(init.body)),
      ...(init.headers || {}),
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail ?? payload?.message ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload as T;
}

function writeHeaders(prefix: string): Record<string, string> {
  return {
    "Idempotency-Key": idempotencyKey(prefix),
    "X-Request-Id": idempotencyKey("folder-ui"),
  };
}

export const trendCollectionsApi = {
  list: () => request<{ items: TrendCollection[] }>("/api/v1/trend-collections"),
  items: (collectionId: string, mediaType?: "image" | "video") => request<{ collection: TrendCollection; items: TrendItem[] }>(
    `/api/v1/trend-collections/${encodeURIComponent(collectionId)}/items?limit=60${mediaType ? `&media_type=${mediaType}` : ""}`,
  ),
  manage: () => request<TrendCollectionState>("/api/v1/trend-collections/manage"),
  create: (body: TrendCollectionWrite) => request<TrendCollection>("/api/v1/trend-collections/manage", {
    method: "POST",
    headers: writeHeaders("folder-create"),
    body: JSON.stringify(body),
  }),
  update: (id: string, body: TrendCollectionWrite) => request<TrendCollection>(`/api/v1/trend-collections/manage/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: writeHeaders("folder-update"),
    body: JSON.stringify(body),
  }),
  remove: (id: string) => request<{ id: string; deleted: boolean; released_items: number; auto_reassigned: number }>(`/api/v1/trend-collections/manage/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: writeHeaders("folder-delete"),
  }),
  activate: (id: string) => request<TrendCollection>(`/api/v1/trend-collections/manage/${encodeURIComponent(id)}/activate`, {
    method: "POST",
    headers: writeHeaders("folder-activate"),
  }),
  assign: (trendId: string, collectionId: string) => request<{ trend_id: string; collection_id: string }>(`/api/v1/trend-collections/manage/items/${encodeURIComponent(trendId)}`, {
    method: "PUT",
    headers: writeHeaders("folder-assign"),
    body: JSON.stringify({ collection_id: collectionId }),
  }),
};
