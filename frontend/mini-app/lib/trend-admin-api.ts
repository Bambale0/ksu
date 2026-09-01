"use client";

import { telegramHeaders } from "./telegram";
import type { GenerationModel } from "./types";

const TREND_COLLECTION_TARGET_ATTRIBUTE = "data-roxy-trend-collection-target";
const INLINE_HASHTAG_RE = /#([\p{L}\p{N}_-]{1,40})/gu;

export function setTrendCollectionTarget(collectionId: string): void {
  if (typeof document === "undefined") return;
  const value = String(collectionId || "").trim();
  if (value) document.documentElement.setAttribute(TREND_COLLECTION_TARGET_ATTRIBUTE, value);
  else document.documentElement.removeAttribute(TREND_COLLECTION_TARGET_ATTRIBUTE);
}

export function clearTrendCollectionTarget(): void {
  if (typeof document === "undefined") return;
  document.documentElement.removeAttribute(TREND_COLLECTION_TARGET_ATTRIBUTE);
}

function targetCollection(): string {
  if (typeof document === "undefined") return "";
  return String(document.documentElement.getAttribute(TREND_COLLECTION_TARGET_ATTRIBUTE) || "").trim();
}

export type TrendAdminPayload = {
  schema_version?: number;
  description?: string;
  media_type: "image" | "video" | string;
  preview_url: string;
  model_id: string;
  prompt: string;
  parameters?: Record<string, unknown>;
  billing_seconds?: number | null;
  input_mode?: "none" | "image" | string;
  min_references?: number;
  max_references?: number;
  tags?: string[];
  sort_order?: number;
  usage_count?: number;
};

export type TrendAdminItem = {
  id: string;
  title: string;
  payload: TrendAdminPayload;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
  collection_id?: string;
};

export type TrendAdminList = {
  items: TrendAdminItem[];
  models?: GenerationModel[];
  limits?: { max_references?: number; max_tags?: number };
};

type TrendWriteBody = {
  title: string;
  payload: TrendAdminPayload;
  is_active?: boolean;
};

function hashtagsFromText(value: unknown): string[] {
  const text = String(value ?? "");
  return Array.from(text.matchAll(INLINE_HASHTAG_RE), (match) => match[1]);
}

export function normalizeTrendTags(tags: unknown): string[] {
  const source = Array.isArray(tags) ? tags : [tags];
  const normalized: string[] = [];
  const seen = new Set<string>();

  for (const raw of source) {
    for (const token of String(raw ?? "").split(/[\s,;]+/u)) {
      const tag = token.trim().replace(/^#+/, "").toLocaleLowerCase();
      if (!tag || tag.length > 40 || !/^[\p{L}\p{N}_-]+$/u.test(tag) || seen.has(tag)) continue;
      seen.add(tag);
      normalized.push(tag);
      if (normalized.length >= 20) return normalized;
    }
  }
  return normalized;
}

function normalizeWriteBody(body: TrendWriteBody): TrendWriteBody {
  const inlineHashtags = [
    ...hashtagsFromText(body.title),
    ...hashtagsFromText(body.payload.description),
  ];
  return {
    ...body,
    payload: {
      ...body.payload,
      tags: normalizeTrendTags([...(body.payload.tags || []), ...inlineHashtags]),
    },
  };
}

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
    "X-Request-Id": idempotencyKey("trend-ui"),
  };
}

export const trendAdminApi = {
  list: () => request<TrendAdminList>("/api/v1/trends/manage"),
  create: async (body: TrendWriteBody) => {
    const collectionId = targetCollection();
    const path = collectionId
      ? `/api/v1/trend-collections/manage/${encodeURIComponent(collectionId)}/items`
      : "/api/v1/trends/manage";
    const item = await request<TrendAdminItem>(path, {
      method: "POST",
      headers: writeHeaders(collectionId ? "folder-trend-create" : "trend-create"),
      body: JSON.stringify(normalizeWriteBody(body)),
    });
    clearTrendCollectionTarget();
    return item;
  },
  update: (id: string, body: TrendWriteBody) => request<TrendAdminItem>(`/api/v1/trends/manage/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: writeHeaders("trend-update"),
    body: JSON.stringify(normalizeWriteBody(body)),
  }),
  hide: (id: string) => request<TrendAdminItem>(`/api/v1/trends/manage/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: writeHeaders("trend-hide"),
  }),
  activate: (id: string) => request<TrendAdminItem>(`/api/v1/trends/manage/${encodeURIComponent(id)}/activate`, {
    method: "POST",
    headers: writeHeaders("trend-activate"),
  }),
};
