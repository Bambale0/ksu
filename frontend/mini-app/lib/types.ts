export type MediaType = "image" | "video" | "audio" | string;
export type FeedSurface = "feed" | "profile";
export type PublicationScope = "private" | "profile" | "feed";

export type TelegramUser = {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  photo_url?: string;
};

export type Me = {
  id: string;
  telegram_id: number;
  username?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  language_code?: string | null;
  balance_rox: string;
  created_at: string;
  is_active: boolean;
  preferences?: {
    ui_language: string;
    notifications_enabled: boolean;
    marketing_notifications: boolean;
    profile_discoverable: boolean;
  };
};

export type UiField = {
  name: string;
  label: string;
  group?: string;
  control?: "text" | "textarea" | "number" | "toggle" | "combobox" | "file" | "files" | "json" | string;
  required?: boolean;
  placeholder?: string;
  suggestions?: Array<string | number>;
  accept?: string;
  max_items?: number;
  max_size_mb?: number;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
};

export type UiScenarioItem = {
  id: string;
  title: string;
  visible_fields?: string[];
  clear_fields?: string[];
};

export type UiSchema = {
  defaults?: Record<string, unknown>;
  groups?: Array<{ id: string; title: string }>;
  fields?: UiField[];
  scenario?: { default?: string | null; items?: UiScenarioItem[] };
  billing_seconds?: { label?: string; required?: boolean; min?: number; max?: number };
};

export type GenerationModel = {
  id: string;
  title: string;
  family: string;
  operation: string;
  media_type: MediaType;
  price_mode?: string;
  price_rox?: string;
  price_credits?: string;
  price_rub?: string;
  ui_schema?: UiSchema;
  presentation?: {
    title?: string;
    product_key?: string;
    product_title?: string;
    family_group?: string | null;
    family_title?: string;
    version_label?: string;
  };
  admin_free?: boolean;
  retail_price_rox?: string;
};

export type GenerationModelVariant = Pick<GenerationModel, "id" | "title" | "operation" | "media_type" | "price_rox" | "price_credits" | "price_rub" | "retail_price_rox" | "ui_schema"> & {
  version?: string;
  badge?: string | null;
  recommended?: boolean;
  description?: string;
};

export type GenerationModelFamily = {
  family: string;
  id: string;
  title: string;
  icon?: string;
  media_types?: string[];
  variant_count: number;
  price_from_rox?: string | null;
  variants: GenerationModelVariant[];
};

export type Generation = {
  id: string;
  status: string;
  prompt?: string;
  prompt_hidden?: boolean;
  prompt_actions_allowed?: boolean;
  model?: GenerationModel | string;
  settings?: Record<string, unknown>;
  cost_rox?: string;
  cost_rub?: string;
  billing_seconds?: number | null;
  result_url?: string | null;
  result_urls?: string[];
  media?: Array<{ url?: string; kind?: string; content_type?: string | null; ordinal?: number }>;
  error?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type FeedAuthor = {
  id?: string;
  telegram_id?: number;
  username?: string | null;
  display_name?: string;
  referral_code?: string;
};

export type FeedCard = Generation & {
  task_id?: string;
  preview_url?: string | null;
  gen_type?: string;
  reference_images?: string[];
  reference_videos?: string[];
  references_hidden?: boolean;
  likes_count?: number;
  comments_count?: number;
  shares_count?: number;
  remixes?: number;
  liked_by_me?: boolean;
  author?: FeedAuthor;
  author_referral_code?: string;
  is_mine?: boolean;
  feed_blurred?: boolean;
  feed_prompt_visible?: boolean;
  feed_references_visible?: boolean;
  publication_scope?: PublicationScope;
  is_profile_visible?: boolean;
  is_public_feed?: boolean;
  feed_interactions_enabled?: boolean;
  surface?: FeedSurface;
  source_feed_gen_id?: string | null;
  feed_published_at?: string | null;
};

export type FeedComment = {
  id: string;
  generation_id: string;
  surface: FeedSurface;
  text: string;
  created_at: string;
  author?: FeedAuthor;
};

export type Quote = {
  model_id: string;
  cost_rox: string;
  cost_rub: string;
  billing_seconds?: number | null;
};

export type Draft = {
  values: Record<string, unknown>;
  scenario?: string | null;
  billing_seconds?: number | null;
};

export type Route = "home" | "catalog" | "create" | "history" | "profile";