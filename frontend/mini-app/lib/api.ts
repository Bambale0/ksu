import { telegramHeaders } from "./telegram";
import type { FeedCard, Generation, GenerationModel, Me, Quote } from "./types";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      ...telegramHeaders(Boolean(init.body) && !isForm),
      ...(init.headers || {}),
    },
  });
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail ?? payload?.message ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload as T;
}

export const api = {
  me: () => request<Me>("/api/v1/me"),
  overview: () => request<Record<string, any>>("/api/v1/me/overview"),
  models: () => request<{ models: GenerationModel[] }>("/api/v1/generations/models"),
  generations: (params = "limit=24") => request<{ items: Generation[]; has_more: boolean; next_before?: string | null }>(`/api/v1/generations?${params}`),
  generation: (id: string) => request<Generation>(`/api/v1/generations/${encodeURIComponent(id)}`),
  quote: (body: Record<string, unknown>) => request<Quote>("/api/v1/generations/quote", { method: "POST", body: JSON.stringify(body) }),
  create: (body: Record<string, unknown>) => request<{ id: string; status?: string }>("/api/v1/generations", { method: "POST", body: JSON.stringify(body) }),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file, file.name);
    return request<{ url: string; name?: string; mime_type?: string; size?: number }>("/api/v1/uploads/kie", { method: "POST", body: form });
  },
  feed: (sort = "recent", offset = 0) => request<{ items: FeedCard[] }>(`/api/v1/feed?sort=${encodeURIComponent(sort)}&limit=24&offset=${offset}`),
  profileFeed: (referralCode: string, offset = 0) => request<{ items: FeedCard[] }>(`/api/v1/profiles/${encodeURIComponent(referralCode)}/feed?limit=24&offset=${offset}`),
  publish: (id: string, scope: "profile" | "feed") => request(`/api/v1/feed/${encodeURIComponent(id)}/publish`, {
    method: "POST",
    body: JSON.stringify({ publication_scope: scope, prompt_visible: false, references_visible: false }),
  }),
  transactions: () => request<Array<{ id: string; kind: string; amount: string; balance_after: string; status: string; created_at: string }>>("/api/v1/me/transactions"),
};
