import { telegramHeaders } from "./telegram";

export type AiReferenceScenario = "create" | "hd" | "edit";
export type AiReferenceSubject = "adult" | "child" | "pet";

export type AiReferenceRequest = {
  scenario: AiReferenceScenario;
  subject?: AiReferenceSubject;
  reference_urls: string[];
  instruction?: string;
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

async function request<T>(path: string, body: AiReferenceRequest): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      ...telegramHeaders(true),
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
  quote: (body: AiReferenceRequest) => request<AiReferenceQuote>("/api/v1/ai-reference/quote", body),
  run: (body: AiReferenceRequest) => request<{ id: string; status: string; scenario: AiReferenceScenario; cost_rox: string; admin_free: boolean }>("/api/v1/ai-reference/run", body),
};
