import { telegramHeaders } from "./telegram";
import type { AspectRatioOptions } from "./aspect-ratio";

export type AiReferenceScenario = "create" | "hd" | "edit";
export type AiReferenceSubject = "adult" | "child" | "pet";

export type AiReferenceRequest = {
  scenario: AiReferenceScenario;
  subject?: AiReferenceSubject;
  reference_urls: string[];
  instruction?: string;
  aspect_ratio?: string | null;
};

export type AiReferenceQuote = {
  scenario: AiReferenceScenario;
  model_id: string;
  unit_price_rox: string;
  cost_rox: string;
  effective_cost_rox: string;
  cost_rub: string;
  retail_cost_rox: string;
  billing_seconds?: number | null;
  admin_free: boolean;
};

async function request<T>(path: string, body?: AiReferenceRequest): Promise<T> {
  const response = await fetch(path, {
    method: body ? "POST" : "GET",
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      ...telegramHeaders(Boolean(body)),
    },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail ?? payload?.message ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload as T;
}

export const aiReferenceApi = {
  options: (scenario: AiReferenceScenario, subject: AiReferenceSubject) => request<AspectRatioOptions & { model_id: string }>(`/api/v1/ai-reference/options?scenario=${scenario}&subject=${subject}`),
  quote: (body: AiReferenceRequest) => request<AiReferenceQuote>("/api/v1/ai-reference/quote", body),
  run: (body: AiReferenceRequest) => request<{ id: string; status: string; scenario: AiReferenceScenario; cost_rox: string; admin_free: boolean }>("/api/v1/ai-reference/run", body),
};
