"use client";

import { telegramHeaders } from "./telegram";

export type PrivateRepeatDescriptor = {
  model_id: string;
  references_required: boolean;
  reference_fields?: string[];
};

type PrivateRepeatInputs = {
  parameters: Record<string, unknown>;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
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

function inputs(parameters: Record<string, unknown>): PrivateRepeatInputs {
  return { parameters };
}

export const privateRepeatApi = {
  createLink: (generationId: string) => request<{ link: string; payload: string; private: true }>(
    `/api/v1/generations/${encodeURIComponent(generationId)}/repeat-link`,
    { method: "POST" },
  ),
  resolve: (token: string) => request<PrivateRepeatDescriptor>(
    `/api/v1/generation-repeat-links/${encodeURIComponent(token)}`,
  ),
  quote: (token: string, parameters: Record<string, unknown>) => request<{ cost_rox?: string; enough_balance?: boolean }>(
    `/api/v1/generation-repeat-links/${encodeURIComponent(token)}/quote`,
    { method: "POST", body: JSON.stringify(inputs(parameters)) },
  ),
  launch: (token: string, parameters: Record<string, unknown>) => request<{ id: string; ids?: string[]; quantity?: number; status?: string; cost_rox?: string }>(
    `/api/v1/generation-repeat-links/${encodeURIComponent(token)}/launch`,
    { method: "POST", body: JSON.stringify(inputs(parameters)) },
  ),
};
