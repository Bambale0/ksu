import { telegramHeaders } from "./telegram";

export type PinterestRepeatRequest = {
  scene_reference_url: string;
  identity_reference_urls: string[];
  height_cm: number;
  weight_kg: number;
  expression?: string;
};

export type PinterestRepeatQuote = {
  mode: "pinterest_repeat";
  model_id: string;
  unit_price_rox: string;
  cost_rox: string;
  effective_cost_rox: string;
  cost_rub: string;
  retail_cost_rox: string;
  billing_seconds: number | null;
  admin_free: boolean;
};

export type PinterestRepeatRun = {
  id: string;
  status: string;
  mode: "pinterest_repeat";
  cost_rox: string;
  admin_free: boolean;
  idempotency_replayed: boolean;
};

export type PinterestResolvedReference = {
  source_url: string;
  reference_url: string;
};

async function post<T>(path: string, body: unknown, headers?: Record<string, string>): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: { ...telegramHeaders(true), ...(headers || {}) },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null) as { detail?: string } | null;
  if (!response.ok) {
    throw new Error(payload?.detail || "Не удалось выполнить запрос");
  }
  return payload as T;
}

export const pinterestRepeatApi = {
  resolve: (url: string) => post<PinterestResolvedReference>("/api/v1/pinterest-repeat/resolve", { url }),
  quote: (body: PinterestRepeatRequest) => post<PinterestRepeatQuote>("/api/v1/pinterest-repeat/quote", body),
  run: (body: PinterestRepeatRequest, idempotencyKey: string) => post<PinterestRepeatRun>(
    "/api/v1/pinterest-repeat/run",
    body,
    { "Idempotency-Key": idempotencyKey },
  ),
};