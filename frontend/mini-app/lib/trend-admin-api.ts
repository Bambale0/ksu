"use client";

import { telegramHeaders } from "./telegram";
import { trendCollectionsApi } from "./trend-collections-api";
import type { GenerationModel } from "./types";

export const TREND_COLLECTION_TARGET_KEY = "__roxy_trend_collection_target_v1";

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

async function targetCollection(): Promise<string> {
  if (typeof window === "undefined") return "";
  try {
    return String(window.sessionStorage.getItem(TREND_COLLECTION_TARGET_KEY) || "").trim();
  } catch {
    return "";
  }
}

function clearTargetCollection(): void {
  if (typeof window === "undefined") return;
  try { window.sessionStorage.removeItem(TREND_COLLECTION_TARGET_KEY); } catch { /* optional */ }
}

export const trendAdminApi = {
  list: () => request<TrendAdminList>("/api/v1/trends/manage"),
  create: async (body: TrendWriteBody) => {
    const item = await request<TrendAdminItem>("/api/v1/trends/manage", {
      method: "POST",
      headers: writeHeaders("trend-create"),
      body: JSON.stringify(body),
    });
    const collectionId = await targetCollection();
    if (collectionId) {
      await trendCollectionsApi.assign(item.id, collectionId);
      clearTargetCollection();
    }
    return item;
  },
  update: (id: string, body: TrendWriteBody) => request<TrendAdminItem>(`/api/v1/trends/manage/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: writeHeaders("trend-update"),
    body: JSON.stringify(body),
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
