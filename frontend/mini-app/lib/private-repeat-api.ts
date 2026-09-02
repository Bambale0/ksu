"use client";

import { telegramHeaders } from "./telegram";
import type { RecreateGenerationPayload } from "./types";

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

export const privateRepeatApi = {
  createLink: (generationId: string) => request<{ link: string; payload: string; private: true }>(
    `/api/v1/generations/${encodeURIComponent(generationId)}/repeat-link`,
    { method: "POST" },
  ),
  resolve: (token: string) => request<RecreateGenerationPayload>(
    `/api/v1/generation-repeat-links/${encodeURIComponent(token)}`,
  ),
};
