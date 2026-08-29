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
  profile_link?: string | null;
  username?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  language_code?: string | null;
  balance_rox: string;
  created_at: string;
  is_active: boolean;
  is_admin?: boolean;
  billing_mode?: "admin_free" | "wallet" | string;
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
  required_fields?: string[];
  required_any?: string[];
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
  batch_id?: string | null;
  batch_index?: number | null;
  batch_size?: number | null;
  result_url?: string | null;
  result_urls?: string[];
  media?: Array<{ url?: string; kind?: string; content_type?: string | null; ordinal?: number }>;
  error?: string | null;
  created_at?: string;
  updated_at?: string;
  publication_scope?: PublicationScope;
  is_profile_visible?: boolean;
  is_public_feed?: boolean;
};

export type RecreateGenerationPayload = {
  model_id: string;
  prompt: string;
  input_url?: string | null;
  billing_seconds?: number | null;
  parameters: Record<string, unknown>;
  references_required?: boolean;
};

export type FeedAuthor = {
  id?: string;
  telegram_id?: number;
  username?: string | null;
  display_name?: string;
  referral_code?: string;
};

export type FeedCard = Omit<Generation, "model"> & {
  model?: string;
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

export type TrendItem = {
  id: string;
  title: string;
  description?: string;
  media_type: "image" | "video" | string;
  preview_url?: string | null;
  model?: { id: string; title?: string; family?: string };
  cost_rox?: string;
  retail_cost_rox?: string;
  cost_rub?: string;
  admin_free?: boolean;
  billing_seconds?: number | null;
  reference_requirements?: { kind?: string; min?: number; max?: number };
  tags?: string[];
  usage_count?: number;
  created_at?: string;
};

export type TrendShare = {
  id: string;
  link: string;
  copy_link: string;
  share_text: string;
  share_url: string;
};

export type PromptToolId = "image_analysis" | "prompt_builder" | "video_prompt";

export type PromptToolCatalogItem = {
  id: PromptToolId;
  title: string;
  model: string;
  enabled: boolean;
  admin_free?: boolean;
  cost_credits?: string | null;
  retail_cost_credits?: string | null;
  cost_rub?: string | null;
};

export type PromptToolTask = {
  id: string;
  tool: PromptToolId;
  status: "queued" | "processing" | "succeeded" | "failed" | string;
  model: string;
  cost_credits: string;
  cost_rub: string;
  retail_cost_credits?: string;
  admin_free?: boolean;
  result?: Record<string, string> | null;
  error?: string | null;
  has_image?: boolean;
  has_video?: boolean;
  duration_seconds?: number | null;
  created_at: string;
  completed_at?: string | null;
};

export type PartnerStats = {
  first_line?: number;
  second_line?: number;
  available?: string;
  partner_balance_rub?: string;
  pending?: string;
  total_earned?: string;
  transferred_to_rox?: string;
  pending_withdrawals?: string;
  minimum_withdrawal?: string;
  first_line_percent?: string;
  second_line_percent?: string;
  referral_payload?: string;
  referral_link?: string;
  profile_link?: string;
  author_profile_link?: string;
  partner_chat_url?: string | null;
  rox_balance?: string;
  welcome_bonus_rox?: string;
  invite_bonus_rox?: string;
  prompt_repeat_bonus_rox?: string;
  minimum_withdrawal_rox?: string;
  prompts_created?: number;
  prompt_repeats?: number;
  withdrawal_status?: string;
};

export type ReferralReward = {
  id: string;
  line: number;
  percent: string;
  amount: string;
  amount_rox?: string;
  net_amount?: string;
  net_amount_rox?: string;
  status: string;
  created_at: string;
  source_user?: { username?: string | null; first_name?: string | null };
};

export type ReferralInvitation = {
  user_id: string;
  username?: string | null;
  first_name?: string | null;
  line: number;
  joined_at: string;
};

export type Quote = {
  model_id: string;
  cost_rox: string;
  cost_rub: string;
  quantity?: number;
  unit_price_rox?: string;
  effective_cost_rox?: string;
  retail_cost_rox?: string;
  billing_seconds?: number | null;
};

export type Draft = {
  values: Record<string, unknown>;
  scenario?: string | null;
  billing_seconds?: number | null;
  input_url?: string | null;
  quantity?: number;
};

export type Route = "home" | "feed" | "catalog" | "create" | "history" | "profile" | "partners";
