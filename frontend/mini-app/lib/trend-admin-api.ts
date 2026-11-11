"use client";

import { telegramHeaders } from "./telegram";
import type { GenerationModel, TrendUserField, UiSchema } from "./types";

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

export type TrendAdminModel = GenerationModel & {
  known_fields?: string[];
  required_fields?: string[];
  reference_capacity?: number;
  min_seconds?: number | null;
  max_seconds?: number | null;
  duration_field?: string | null;
  notes?: string[];
  capabilities?: string[] | Record<string, boolean>;
  ui_schema?: UiSchema;
};

type TrendAdminPayloadBase = {
  description?: string;
  preview_url: string;
  // Kept optional on the shared view type because the collection metadata
  // editor reads these fields before it can discriminate the recipe branch.
  // V2 writes never add them to the root recipe.
  media_type?: string;
  prompt?: string;
  user_fields?: TrendUserField[];
  tags?: string[];
  sort_order?: number;
  usage_count?: number;
};

export type TrendAdminV1Payload = TrendAdminPayloadBase & {
  schema_version?: 1;
  media_type: "image" | "video" | string;
  model_id: string;
  prompt: string;
  user_fields?: TrendUserField[];
  parameters?: Record<string, unknown>;
  billing_seconds?: number | null;
  input_mode?: "none" | "image" | string;
  min_references?: number;
  max_references?: number;
  template_video_url?: string | null;
};

export type TrendAdminInput = {
  id: string;
  label: string;
  help: string;
  type: "image" | "text" | "number" | "date" | "select";
  required: boolean;
  order: number;
  options?: string[];
};

export type TrendAdminBinding = {
  from: string;
  to: string;
};

type TrendAdminStepBase = {
  id: string;
  kind: "image" | "video";
  title: string;
  instructions: string;
  preview_url?: string | null;
  model_id: string;
  model_title?: string;
  prompt: string;
  parameters: Record<string, unknown>;
  inputs: TrendAdminInput[];
  pricing_source?: string;
  image_input_mode?: "ordered" | "semantic";
};

export type TrendAdminImageStep = TrendAdminStepBase & {
  kind: "image";
};

export type TrendAdminVideoStep = TrendAdminStepBase & {
  kind: "video";
  inputs: TrendAdminInput[];
  bindings: [TrendAdminBinding];
};

export type TrendAdminV2Payload = TrendAdminPayloadBase & {
  schema_version: 2;
  workflow_type: "sequential_photo_video";
  pricing_source?: string;
  steps: [TrendAdminImageStep, TrendAdminVideoStep];
};

export type TrendAdminPayload = TrendAdminV1Payload | TrendAdminV2Payload;

/*
 * The v1 shape is deliberately kept separate from the workflow recipe. This
 * prevents an old template from being reconstructed as a one-step recipe
 * merely because an editor opened it.
 */
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
  models?: TrendAdminModel[];
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

class TrendAdminHttpError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "TrendAdminHttpError";
  }
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
    throw new TrendAdminHttpError(typeof detail === "string" ? detail : JSON.stringify(detail), response.status);
  }
  return payload as T;
}

function writeHeaders(prefix: string): Record<string, string> {
  return {
    "Idempotency-Key": idempotencyKey(prefix),
    "X-Request-Id": idempotencyKey("trend-ui"),
  };
}

// Only trend admin create/update are retried: those writes use the same
// idempotency token even when a gateway has lost a successful response.
// Bounded recovery handles short API rotations without repeating a mutation.
async function sendAdminWrite<T>(path: string, method: "POST" | "PATCH",
  save: ReturnType<typeof retryableWrite>): Promise<T> {
  const delaysMs = [0, 800, 2300];
  for (const [attempt, delay] of delaysMs.entries()) {
    if (delay) await new Promise<void>((resolve) => setTimeout(resolve, delay));
    try {
      return await request<T>(path, {
        method, headers: save.headers, body: JSON.stringify(save.normalized),
      });
    } catch (error) {
      if (!(error instanceof TrendAdminHttpError)
        || ![502, 503, 504].includes(error.status)
        || attempt === delaysMs.length - 1) throw error;
    }
  }
  throw new Error("Не удалось сохранить тренд");
}

// A gateway timeout can happen *after* a write commits. Reuse the same
// idempotency key when exactly the same admin save is retried, so a 502
// never creates duplicate trends. Only a confirmed success releases the key.
const pendingTrendWrites = new Map<string, string>();

function retryableWrite(prefix: string, path: string, body: TrendWriteBody) {
  const normalized = normalizeWriteBody(body);
  const fingerprint = JSON.stringify([prefix, path, normalized]);
  let key = pendingTrendWrites.get(fingerprint);
  if (!key) {
    key = idempotencyKey(prefix);
    pendingTrendWrites.set(fingerprint, key);
  }
  return {
    normalized,
    fingerprint,
    headers: { "Idempotency-Key": key, "X-Request-Id": idempotencyKey("trend-ui") },
  };
}

export const trendAdminApi = {
  list: async (): Promise<TrendAdminList> => {
    const [managed, publicCatalog] = await Promise.all([
      request<TrendAdminList>("/api/v1/trends/manage"),
      request<{ models?: TrendAdminModel[] }>("/api/v1/generations/models"),
    ]);
    const publicModels = new Map((publicCatalog.models || []).map((model) => [model.id, model]));
    return {
      ...managed,
      models: (managed.models || []).map((model) => ({
        ...publicModels.get(model.id),
        ...model,
        ui_schema: model.ui_schema || publicModels.get(model.id)?.ui_schema,
      })),
    };
  },
  create: async (body: TrendWriteBody) => {
    const collectionId = targetCollection();
    const path = collectionId
      ? `/api/v1/trend-collections/manage/${encodeURIComponent(collectionId)}/items`
      : "/api/v1/trends/manage";
    const save = retryableWrite(collectionId ? "folder-trend-create" : "trend-create", path, body);
    const item = await sendAdminWrite<TrendAdminItem>(path, "POST", save);
    pendingTrendWrites.delete(save.fingerprint);
    clearTrendCollectionTarget();
    return item;
  },
  update: async (id: string, body: TrendWriteBody) => {
    const path = `/api/v1/trends/manage/${encodeURIComponent(id)}`;
    const save = retryableWrite("trend-update", path, body);
    const result = await sendAdminWrite<TrendAdminItem>(path, "PATCH", save);
    pendingTrendWrites.delete(save.fingerprint);
    return result;
  },
  hide: (id: string) => request<TrendAdminItem>(`/api/v1/trends/manage/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: writeHeaders("trend-hide"),
  }),
  activate: (id: string) => request<TrendAdminItem>(`/api/v1/trends/manage/${encodeURIComponent(id)}/activate`, {
    method: "POST",
    headers: writeHeaders("trend-activate"),
  }),
};
