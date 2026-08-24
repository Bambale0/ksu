import { telegramHeaders } from "./telegram";
import type {
  FeedCard,
  FeedComment,
  FeedSurface,
  Generation,
  GenerationModel,
  GenerationModelFamily,
  Me,
  PartnerStats,
  PromptToolCatalogItem,
  PromptToolTask,
  PublicationScope,
  Quote,
  RecreateGenerationPayload,
  ReferralInvitation,
  ReferralReward,
  TrendItem,
} from "./types";

declare global {
  interface Window {
    __roxyPublishPrivacy?: { hidePrompt?: boolean };
  }
}

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

type PublishOptions = {
  scope: Exclude<PublicationScope, "private">;
  promptVisible?: boolean;
  referencesVisible?: boolean;
};

type PromptBuilderBody = {
  text?: string;
  image_url?: string | null;
  purpose?: "general" | "image" | "video" | "seedance";
  duration_seconds?: 5 | 10 | 15 | null;
};

type VideoPromptBody = {
  video_url: string;
  instruction?: string;
  duration_seconds?: 5 | 10 | 15 | null;
};

const publicPrivacyDefaults = { prompt_visible: false, references_visible: false };

function normalizePublishOptions(options: Exclude<PublicationScope, "private"> | PublishOptions): PublishOptions {
  return typeof options === "string" ? { scope: options } : options;
}

function promptVisibleForPublish(normalized: PublishOptions): boolean {
  if (typeof window !== "undefined" && window.__roxyPublishPrivacy) {
    return !Boolean(window.__roxyPublishPrivacy.hidePrompt);
  }
  return Boolean(normalized.promptVisible);
}

function idempotencyKey(prefix: string): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return `${prefix}:${crypto.randomUUID()}`;
  return `${prefix}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
}

export const api = {
  me: () => request<Me>("/api/v1/me"),
  overview: () => request<Record<string, any>>("/api/v1/me/overview"),
  onboarding: () => request<Record<string, any>>("/api/v1/onboarding"),
  completeOnboarding: () => request<Record<string, any>>("/api/v1/onboarding/complete", { method: "POST" }),
  models: () => request<{ models: GenerationModel[]; families?: GenerationModelFamily[]; max_generation_quantity?: number }>("/api/v1/generations/models"),
  generations: (params = "limit=24") => request<{ items: Generation[]; has_more: boolean; next_before?: string | null }>(`/api/v1/generations?${params}`),
  generation: (id: string) => request<Generation>(`/api/v1/generations/${encodeURIComponent(id)}`),
  recreateGeneration: (id: string) => request<RecreateGenerationPayload>(`/api/v1/generations/${encodeURIComponent(id)}/recreate`),
  quote: (body: Record<string, unknown>) => request<Quote>("/api/v1/generations/quote", { method: "POST", body: JSON.stringify(body) }),
  create: (body: Record<string, unknown>) => request<{ id: string; ids?: string[]; quantity?: number; status?: string; cost_rox?: string }>("/api/v1/generations", { method: "POST", body: JSON.stringify(body) }),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file, file.name);
    return request<{ url: string; name?: string; mime_type?: string; size?: number }>("/api/v1/uploads/kie", { method: "POST", body: form });
  },
  feed: (sort = "recent", offset = 0) => request<{ items: FeedCard[] }>(`/api/v1/feed?sort=${encodeURIComponent(sort)}&limit=24&offset=${offset}`),
  feedItem: (id: string, surface: FeedSurface = "feed") => request<FeedCard>(`/api/v1/feed/${encodeURIComponent(id)}?surface=${encodeURIComponent(surface)}`),
  profileFeed: (referralCode: string, offset = 0) => request<{ author?: Record<string, unknown>; items: FeedCard[] }>(`/api/v1/profiles/${encodeURIComponent(referralCode)}/feed?limit=24&offset=${offset}`),
  publish: (
    id: string,
    options: Exclude<PublicationScope, "private"> | PublishOptions,
  ) => {
    const normalized = normalizePublishOptions(options);
    return request<{ publication_scope: PublicationScope; downgraded_to_profile: boolean; item: FeedCard }>(`/api/v1/feed/${encodeURIComponent(id)}/publish`, {
      method: "POST",
      body: JSON.stringify({
        ...publicPrivacyDefaults,
        publication_scope: normalized.scope,
        prompt_visible: promptVisibleForPublish(normalized),
        references_visible: Boolean(normalized.referencesVisible),
      }),
    });
  },
  removePublication: (id: string, targetScope: "private" | "profile" = "private") => request<{ id: string; publication_scope: PublicationScope; is_public_feed: boolean; is_profile_visible: boolean }>(`/api/v1/feed/${encodeURIComponent(id)}/remove`, {
    method: "POST",
    body: JSON.stringify({ target_scope: targetScope }),
  }),
  like: (id: string, surface: FeedSurface = "feed") => request<{ id: string; surface: FeedSurface; liked_by_me: boolean; likes_count: number }>(`/api/v1/feed/${encodeURIComponent(id)}/like`, {
    method: "POST",
    body: JSON.stringify({ surface }),
  }),
  unlike: (id: string, surface: FeedSurface = "feed") => request<{ id: string; surface: FeedSurface; liked_by_me: boolean; likes_count: number }>(`/api/v1/feed/${encodeURIComponent(id)}/like?surface=${encodeURIComponent(surface)}`, { method: "DELETE" }),
  share: (id: string, surface: FeedSurface = "feed") => request<{ id: string; shares_count: number; link: string | null }>(`/api/v1/feed/${encodeURIComponent(id)}/share`, {
    method: "POST",
    body: JSON.stringify({ surface }),
  }),
  comments: (id: string, surface: FeedSurface = "feed") => request<{ items: FeedComment[] }>(`/api/v1/feed/${encodeURIComponent(id)}/comments?surface=${encodeURIComponent(surface)}&limit=50`),
  addComment: (id: string, surface: FeedSurface, text: string) => request<FeedComment>(`/api/v1/feed/${encodeURIComponent(id)}/comments`, {
    method: "POST",
    body: JSON.stringify({ surface, text }),
  }),
  remix: (id: string, surface: FeedSurface = "feed") => request<{ id: string; status: string; source_feed_gen_id?: string; action_type?: string }>(`/api/v1/feed/${encodeURIComponent(id)}/remix`, {
    method: "POST",
    body: JSON.stringify({ surface }),
  }),
  trends: (mediaType?: "image" | "video") => request<{ items: TrendItem[] }>(`/api/v1/trends?limit=60${mediaType ? `&media_type=${mediaType}` : ""}`),
  trend: (id: string) => request<TrendItem>(`/api/v1/trends/${encodeURIComponent(id)}`),
  runTrend: (id: string, referenceUrls: string[] = []) => request<{ id: string; task_id?: string; status: string; cost_rox?: string; result_url?: string | null }>(`/api/v1/trends/${encodeURIComponent(id)}/run`, {
    method: "POST",
    body: JSON.stringify({ reference_urls: referenceUrls }),
  }),
  promptTools: () => request<{ admin_free: boolean; items: PromptToolCatalogItem[] }>("/api/v1/prompt-tools"),
  promptToolTask: (id: string) => request<PromptToolTask>(`/api/v1/prompt-tools/${encodeURIComponent(id)}`),
  buildPrompt: (body: PromptBuilderBody) => request<PromptToolTask>("/api/v1/prompt-tools/prompt-builder", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey("prompt-builder") },
    body: JSON.stringify(body),
  }),
  analyzeImagePrompt: (imageUrl: string, instruction = "") => request<PromptToolTask>("/api/v1/prompt-tools/image-analysis", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey("image-analysis") },
    body: JSON.stringify({ image_url: imageUrl, instruction }),
  }),
  buildVideoPrompt: (body: VideoPromptBody) => request<PromptToolTask>("/api/v1/prompt-tools/video-prompt", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey("video-prompt") },
    body: JSON.stringify(body),
  }),
  referralStats: () => request<PartnerStats>("/api/v1/referrals/stats"),
  referralInvitations: () => request<{ items: ReferralInvitation[] }>("/api/v1/referrals/invitations?limit=20"),
  referralRewards: () => request<{ items: ReferralReward[] }>("/api/v1/referrals/rewards?limit=20"),
  referralTransfers: () => request<{ items: Array<{ id: string; amount_rub: string; rox_amount: string; created_at: string }> }>("/api/v1/referrals/wallet-transfers?limit=20"),
  creatorPartnership: () => request<Record<string, any>>("/api/v1/creator-partnership"),
  applyCreatorPartnership: (body: Record<string, unknown>) => request<Record<string, any>>("/api/v1/creator-partnership/applications", {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(body),
  }),
  transactions: () => request<Array<{ id: string; kind: string; amount: string; balance_after: string; status: string; created_at: string }>>("/api/v1/me/transactions"),
  paymentPackages: () => request<{
    provider: string;
    label: string;
    currencies: string[];
    packages: Record<string, { credits: string; prices: Record<string, string> }>;
  }>("/api/v1/payments/card/packages"),
  payments: () => request<{ items: Array<{ id: string; status: string; provider: string; amount: string; currency: string; rox: string; payment_url: string; created_at: string }> }>("/api/v1/payments?limit=20"),
  createPayment: (packageId: string, currency: "RUB" | "USD" | "EUR", billingEmail: string) => request<{ id: string; status: string; payment_url: string }>("/api/v1/payments/card/checkout", {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ package_id: packageId, currency, billing_email: billingEmail }),
  }),
};