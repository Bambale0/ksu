"use client";

import { telegramHeaders } from "./telegram";
import type { GenerationModel } from "./types";

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

export const trendAdminApi = {
  list: () => request<TrendAdminList>("/api/v1/trends/manage"),
  create: (body: TrendWriteBody) => request<TrendAdminItem>("/api/v1/trends/manage", {
    method: "POST",
    headers: writeHeaders("trend-create"),
    body: JSON.stringify(body),
  }),
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
