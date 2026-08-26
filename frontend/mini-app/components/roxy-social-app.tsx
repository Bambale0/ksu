"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { SavedReferencePicker } from "@/lib/reference-memory";
import { haptic, initTelegram, notify, syncSafeArea, telegram } from "@/lib/telegram";
import type {
  Draft,
  FeedCard,
  FeedComment,
  FeedSurface,
  Generation,
  GenerationModel,
  GenerationModelFamily,
  Me,
  PartnerStats,
  Quote,
  RecreateGenerationPayload,
  ReferralInvitation,
  ReferralReward,
  Route,
  TrendItem,
  UiField,
  UiScenarioItem,
} from "@/lib/types";
import { Icon, type IconName } from "./icons";

const ROUTES: Route[] = ["home", "feed", "catalog", "create", "history", "profile", "partners"];
const MODEL_KEY = "ksu-selected-model";
const MEDIA_FILTER_KEY = "ksu-selected-media";
const PROMO_SLIDES = [
  { src: "promo/roxy-promo-1.webp", title: "Промо для авторов" },
  { src: "promo/roxy-promo-2.webp", title: "Партнёрские выплаты" },
];

type PreviewSurface = "private" | FeedSurface;
type MediaFilter = "all" | "image" | "video" | "audio";
type CreationMedia = Exclude<MediaFilter, "all">;
type ProfilePublication = FeedCard | Generation;
type CreateLaunch =
  | { nonce: number; kind: "new"; modelId?: string; media?: CreationMedia }
  | { nonce: number; kind: "reuse"; payload: RecreateGenerationPayload };

function isRoute(value: string | null): value is Route {
  return ROUTES.includes(value as Route);
}

function compact(value: unknown): string {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  return new Intl.NumberFormat("ru-RU", {
    notation: Math.abs(number) >= 10000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(number);
}

function dateLabel(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function statusLabel(value?: string | null): string {
  const labels: Record<string, string> = {
    queued: "В очереди",
    submitting: "Запускается",
    generating: "Создаётся",
    retry: "Повторяем",
    succeeded: "Готово",
    failed: "Не получилось",
    canceled: "Отменено",
    pending: "Ждёт",
    available: "Доступно",
    reversed: "Возвращено",
  };
  return value ? labels[value] || "В работе" : "В работе";
}

function transactionLabel(value?: string | null): string {
  const labels: Record<string, string> = {
    purchase: "Пополнение",
    payment: "Пополнение",
    generation: "Создание",
    refund: "Возврат",
    bonus: "Бонус",
    referral_bonus: "Бонус за приглашение",
    partner_transfer: "Перевод партнёра",
    adjustment: "Корректировка",
  };
  return value ? labels[value] || "Операция" : "Операция";
}

function displayName(me: Me | null): string {
  if (!me) return "ROXY Creator";
  return [me.first_name, me.last_name].filter(Boolean).join(" ") || me.username || "ROXY Creator";
}

function resultMediaUrl(item: Generation | FeedCard): string {
  return item.result_url || item.result_urls?.[0] || item.media?.[0]?.url || "";
}

function mediaUrl(item: Generation | FeedCard): string {
  return (item as FeedCard).preview_url || resultMediaUrl(item);
}

function modelOf(item: Generation | FeedCard): GenerationModel | null {
  return item.model && typeof item.model === "object" ? item.model : null;
}

function mediaType(item: Generation | FeedCard): string {
  const model = modelOf(item);
  if (model?.media_type) return model.media_type;
  const url = resultMediaUrl(item) || mediaUrl(item);
  if (/\.(mp4|webm|mov)(\?|$)/i.test(url)) return "video";
  if (/\.(mp3|wav|m4a|aac|ogg)(\?|$)/i.test(url)) return "audio";
  return "image";
}

function modelIcon(media?: string): IconName {
  return media === "video" ? "video" : media === "audio" ? "music" : "image";
}

function creationMedia(model?: GenerationModel | null): CreationMedia | undefined {
  if (model?.media_type === "video" || model?.media_type === "audio") return model.media_type;
  if (model?.media_type === "image") return "image";
  return undefined;
}

function priceLabel(value?: string | null): string {
  if (value === "0.00" || value === "0") return "Бесплатно";
  return value ? `${compact(value)} ROX` : "—";
}

function normalizeMediaFilter(value: string | null): MediaFilter {
  return value === "image" || value === "video" || value === "audio" ? value : "all";
}

function initialRoute(): Route {
  if (typeof window === "undefined") return "home";
  const route = new URL(window.location.href).searchParams.get("route");
  return isRoute(route) ? route : "home";
}

function variantLabel(model: GenerationModel): string {
  return model.presentation?.version_label || model.title;
}

function fallbackFamilies(models: GenerationModel[]): GenerationModelFamily[] {
  const grouped = new Map<string, GenerationModel[]>();
  for (const model of models) {
    const key = model.presentation?.family_group || model.family || model.id;
    grouped.set(key, [...(grouped.get(key) || []), model]);
  }
  return [...grouped.entries()].map(([id, variants]) => ({
    family: id.replaceAll("-", "_"),
    id: id.replaceAll("-", "_"),
    title: variants[0]?.presentation?.family_title || variants[0]?.family || variants[0]?.title || id,
    icon: modelIcon(variants[0]?.media_type),
    media_types: [...new Set(variants.map((item) => item.media_type))],
    variant_count: variants.length,
    price_from_rox: variants.map((item) => item.price_rox).filter(Boolean).sort()[0] || null,
    variants: variants.map((item) => ({
      id: item.id,
      title: item.title,
      version: variantLabel(item),
      operation: item.operation,
      media_type: item.media_type,
      price_rox: item.price_rox,
      price_credits: item.price_credits,
      price_rub: item.price_rub,
      retail_price_rox: item.retail_price_rox,
      recommended: false,
      description: item.presentation?.product_title || item.title,
      ui_schema: item.ui_schema,
    })),
  }));
}

function createDefaultDraft(model: GenerationModel): Draft {
  return {
    values: { ...(model.ui_schema?.defaults || {}) },
    scenario: model.ui_schema?.scenario?.default || model.ui_schema?.scenario?.items?.[0]?.id || null,
    billing_seconds: null,
    input_url: null,
  };
}

function isEmpty(value: unknown): boolean {
  return value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0);
}

function userFieldLabel(field: UiField): string {
  return field.name === "prompt" || field.label === "Промпт" ? "Описание" : field.label;
}

function scenarioScore(item: UiScenarioItem, values: Record<string, unknown>): number {
  const required = item.required_fields || [];
  const requiredAny = item.required_any || [];
  if (required.some((name) => isEmpty(values[name]))) return -1;
  if (requiredAny.length && !requiredAny.some((name) => !isEmpty(values[name]))) return -1;
  let score = required.length * 4 + (requiredAny.length ? 3 : 0);
  for (const name of item.visible_fields || []) if (!isEmpty(values[name])) score += 1;
  return score;
}

function inferReuseScenario(model: GenerationModel, values: Record<string, unknown>): string | null {
  const items = model.ui_schema?.scenario?.items || [];
  if (!items.length) return null;
  let winner: UiScenarioItem | null = null;
  let winnerScore = -1;
  for (const item of items) {
    const score = scenarioScore(item, values);
    if (score > winnerScore) {
      winner = item;
      winnerScore = score;
    }
  }
  return winner?.id || model.ui_schema?.scenario?.default || items[0]?.id || null;
}

function hydrateReuseDraft(model: GenerationModel, payload: RecreateGenerationPayload): Draft {
  const base = createDefaultDraft(model);
  const values = {
    ...base.values,
    ...(payload.parameters || {}),
    prompt: payload.prompt || "",
  };
  return {
    values,
    scenario: inferReuseScenario(model, values),
    billing_seconds: payload.billing_seconds ?? null,
    input_url: payload.input_url ?? null,
  };
}

function visibleFields(model: GenerationModel, draft: Draft): UiField[] {
  const fields = model.ui_schema?.fields || [];
  const scenario = model.ui_schema?.scenario?.items?.find((item) => item.id === draft.scenario);
  if (!scenario) return fields;
  const controlled = new Set<string>();
  for (const item of model.ui_schema?.scenario?.items || []) {
    for (const name of item.visible_fields || []) controlled.add(name);
    for (const name of item.clear_fields || []) controlled.add(name);
  }
  return fields.filter((field) => !controlled.has(field.name) || scenario.visible_fields?.includes(field.name));
}

function buildPayload(model: GenerationModel, draft: Draft): Record<string, unknown> {
  const parameters: Record<string, unknown> = {};
  for (const field of visibleFields(model, draft)) {
    if (field.name === "prompt") continue;
    const value = draft.values[field.name];
    if (isEmpty(value)) continue;
    if (field.control === "json" && typeof value === "string") parameters[field.name] = JSON.parse(value);
    else parameters[field.name] = value;
  }
  const payload: Record<string, unknown> = {
    model_id: model.id,
    prompt: String(draft.values.prompt || ""),
    parameters,
  };
  if (draft.input_url) payload.input_url = draft.input_url;
  if (draft.billing_seconds) payload.billing_seconds = Number(draft.billing_seconds);
  return payload;
}

function validateDraft(model: GenerationModel, draft: Draft): string[] {
  const errors: string[] = [];
  for (const field of visibleFields(model, draft)) {
    const value = draft.values[field.name];
    const label = userFieldLabel(field);
    if (field.required && isEmpty(value)) errors.push(`Заполните «${label}»`);
    if (field.control === "json" && !isEmpty(value)) {
      try { JSON.parse(String(value)); } catch { errors.push(`Проверьте поле «${label}»`); }
    }
  }
  const scenario = model.ui_schema?.scenario?.items?.find((item) => item.id === draft.scenario);
  for (const name of scenario?.required_fields || []) {
    if (isEmpty(draft.values[name])) errors.push("Заполните обязательное поле");
  }
  const any = scenario?.required_any || [];
  if (any.length && !any.some((name) => !isEmpty(draft.values[name]))) errors.push("Добавьте хотя бы один референс");
  const billing = model.ui_schema?.billing_seconds;
  if (billing?.required && !draft.billing_seconds) errors.push(`Заполните «${billing.label || "Длительность"}»`);
  if (draft.billing_seconds && billing?.min && draft.billing_seconds < billing.min) errors.push(`Минимум ${billing.min} сек.`);
  if (draft.billing_seconds && billing?.max && draft.billing_seconds > billing.max) errors.push(`Максимум ${billing.max} сек.`);
  return [...new Set(errors)];
}

async function copyText(value: string | null | undefined) {
  if (!value || typeof navigator === "undefined" || !navigator.clipboard) return false;
  await navigator.clipboard.writeText(value);
  return true;
}

function profileLink(stats: PartnerStats | null, me: Me | null): string | null {
  if (!stats?.referral_link || !me?.telegram_id) return null;
  return stats.referral_link.replace(`ref_${me.telegram_id}`, `profile_${me.telegram_id}`).replace("start=ref_", "start=profile_");
}

function isPublishedGeneration(item: Generation): boolean {
  return Boolean(item.is_profile_visible || item.is_public_feed || item.publication_scope === "profile" || item.publication_scope === "feed");
}

export function RoxySocialApp() {
  const [booting, setBooting] = useState(true);
  const [route, setRoute] = useState<Route>("home");
  const [me, setMe] = useState<Me | null>(null);
  const [models, setModels] = useState<GenerationModel[]>([]);
  const [families, setFamilies] = useState<GenerationModelFamily[]>([]);
  const [recent, setRecent] = useState<Generation[]>([]);
  const [feed, setFeed] = useState<FeedCard[]>([]);
  const [feedSort, setFeedSort] = useState<"recent" | "top_day" | "top">("recent");
  const [trends, setTrends] = useState<TrendItem[]>([]);
  const [history, setHistory] = useState<Generation[]>([]);
  const [historyBefore, setHistoryBefore] = useState<string | null>(null);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [profileWorks, setProfileWorks] = useState<Generation[]>([]);
  const [profilePublications, setProfilePublications] = useState<ProfilePublication[]>([]);
  const [profileTab, setProfileTab] = useState<"works" | "publications">("works");
  const [partnerStats, setPartnerStats] = useState<PartnerStats | null>(null);
  const [partnerRewards, setPartnerRewards] = useState<ReferralReward[]>([]);
  const [partnerInvites, setPartnerInvites] = useState<ReferralInvitation[]>([]);
  const [walletOpen, setWalletOpen] = useState(false);
  const [preview, setPreview] = useState<Generation | FeedCard | null>(null);
  const [previewSurface, setPreviewSurface] = useState<PreviewSurface>("private");
  const [toast, setToast] = useState("");
  const [onboarding, setOnboarding] = useState<Record<string, any> | null>(null);
  const [createLaunch, setCreateLaunch] = useState<CreateLaunch>({ nonce: 0, kind: "new" });
  const createLaunchSeq = useRef(0);
  const deepLinkedGeneration = useRef<string | null>(null);
  const toastTimer = useRef<number | null>(null);

  const showToast = useCallback((message: string) => {
    setToast(message);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 2800);
  }, []);

  const refreshMe = useCallback(async () => {
    const next = await api.me();
    setMe(next);
    return next;
  }, []);

  const loadFeed = useCallback(async (sort = feedSort) => {
    const payload = await api.feed(sort, 0);
    setFeed(payload.items || []);
    return payload.items || [];
  }, [feedSort]);

  const loadTrends = useCallback(async () => {
    const payload = await api.trends();
    setTrends(payload.items || []);
    return payload.items || [];
  }, []);

  const loadHistory = useCallback(async (append = false, before?: string | null) => {
    const query = `limit=24${before ? `&before=${encodeURIComponent(before)}` : ""}`;
    const payload = await api.generations(query);
    setHistory((current) => append ? [...current, ...payload.items] : payload.items);
    setHistoryBefore(payload.next_before || null);
    setHistoryHasMore(Boolean(payload.has_more));
    return payload.items;
  }, []);

  const loadProfile = useCallback(async () => {
    const [works, publications] = await Promise.all([
      api.generations("limit=36&status=succeeded"),
      me ? api.profileFeed(String(me.telegram_id), 0) : Promise.resolve({ items: [] as FeedCard[] }),
    ]);
    const ownPublished = works.items.filter(isPublishedGeneration);
    const publishedIds = new Set((publications.items || []).map((item) => item.id));
    setProfileWorks(works.items);
    setProfilePublications([
      ...(publications.items || []),
      ...ownPublished.filter((item) => !publishedIds.has(item.id)),
    ]);
  }, [me]);

  const loadPartners = useCallback(async () => {
    const [stats, rewards, invitations] = await Promise.allSettled([
      api.referralStats(),
      api.referralRewards(),
      api.referralInvitations(),
    ]);
    if (stats.status === "fulfilled") setPartnerStats(stats.value);
    if (rewards.status === "fulfilled") setPartnerRewards(rewards.value.items || []);
    if (invitations.status === "fulfilled") setPartnerInvites(invitations.value.items || []);
  }, []);

  useEffect(() => {
    let active = true;
    const tg = initTelegram();
    const safe = () => syncSafeArea(tg);
    tg?.ready?.();
    tg?.expand?.();
    tg?.onEvent?.("safeAreaChanged", safe);
    tg?.onEvent?.("contentSafeAreaChanged", safe);
    tg?.onEvent?.("viewportChanged", safe);
    setRoute(initialRoute());

    (async () => {
      try {
        const [modelResult, meResult, recentResult, feedResult, trendsResult, onboardingResult] = await Promise.allSettled([
          api.models(),
          tg?.initData ? api.me() : Promise.resolve(null),
          tg?.initData ? api.generations("limit=12") : Promise.resolve({ items: [] }),
          tg?.initData ? api.feed("recent", 0) : Promise.resolve({ items: [] }),
          tg?.initData ? api.trends() : Promise.resolve({ items: [] }),
          tg?.initData ? api.onboarding() : Promise.resolve(null),
        ]);
        if (!active) return;
        if (modelResult.status === "fulfilled") {
          const nextModels = modelResult.value.models || [];
          setModels(nextModels);
          setFamilies(modelResult.value.families?.length ? modelResult.value.families : fallbackFamilies(nextModels));
        }
        if (meResult.status === "fulfilled" && meResult.value) setMe(meResult.value);
        if (recentResult.status === "fulfilled") setRecent(recentResult.value.items || []);
        if (feedResult.status === "fulfilled") setFeed(feedResult.value.items || []);
        if (trendsResult.status === "fulfilled") setTrends(trendsResult.value.items || []);
        if (onboardingResult.status === "fulfilled" && onboardingResult.value) setOnboarding(onboardingResult.value);
      } finally {
        if (active) setBooting(false);
      }
    })();

    const onPop = () => setRoute(initialRoute());
    window.addEventListener("popstate", onPop);
    return () => {
      active = false;
      window.removeEventListener("popstate", onPop);
      tg?.offEvent?.("safeAreaChanged", safe);
      tg?.offEvent?.("contentSafeAreaChanged", safe);
      tg?.offEvent?.("viewportChanged", safe);
    };
  }, []);

  useEffect(() => {
    if (route === "history" && history.length === 0) void loadHistory();
    if (route === "profile") void loadProfile();
    if (route === "partners") void loadPartners();
    if (route === "catalog") void loadTrends();
  }, [route, history.length, loadHistory, loadProfile, loadPartners, loadTrends]);

  useEffect(() => {
    if (route !== "feed") return;
    const refreshVisible = () => {
      if (document.visibilityState === "visible") void loadFeed(feedSort);
    };
    void loadFeed(feedSort);
    const timer = window.setInterval(refreshVisible, 15000);
    window.addEventListener("focus", refreshVisible);
    document.addEventListener("visibilitychange", refreshVisible);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refreshVisible);
      document.removeEventListener("visibilitychange", refreshVisible);
    };
  }, [feedSort, loadFeed, route]);

  useEffect(() => {
    if (booting || !telegram()?.initData) return;
    const generationId = new URL(window.location.href).searchParams.get("generation");
    if (!generationId || deepLinkedGeneration.current === generationId) return;
    deepLinkedGeneration.current = generationId;
    void api.generation(generationId)
      .then((item) => {
        setPreviewSurface("private");
        setPreview(item);
        setRoute("history");
        void loadHistory();
      })
      .catch((error) => showToast(error instanceof Error ? error.message : "Не удалось открыть работу"));
  }, [booting, loadHistory, showToast]);

  const navigate = useCallback((next: Route) => {
    setWalletOpen(false);
    setPreview(null);
    setRoute(next);
    const url = new URL(window.location.href);
    url.searchParams.set("route", next);
    url.searchParams.delete("generation");
    window.history.pushState({ roxyRoute: next }, "", `${url.pathname}${url.search}${url.hash}`);
    haptic(next === "create" ? "medium" : "light");
    window.scrollTo({ top: 0, behavior: "auto" });
  }, []);

  const startNewGeneration = useCallback((media?: CreationMedia, modelId?: string) => {
    if (media) localStorage.setItem(MEDIA_FILTER_KEY, media);
    if (modelId) localStorage.setItem(MODEL_KEY, modelId);
    setCreateLaunch({ nonce: ++createLaunchSeq.current, kind: "new", media, modelId });
    navigate("create");
  }, [navigate]);

  const reuseGeneration = useCallback(async (generationId: string) => {
    const payload = await api.recreateGeneration(generationId);
    const model = models.find((item) => item.id === payload.model_id);
    if (!model) throw new Error("Эта модель больше недоступна");
    localStorage.setItem(MODEL_KEY, model.id);
    const media = creationMedia(model);
    if (media) localStorage.setItem(MEDIA_FILTER_KEY, media);
    setCreateLaunch({ nonce: ++createLaunchSeq.current, kind: "reuse", payload });
    navigate("create");
  }, [models, navigate]);

  useEffect(() => {
    const tg = telegram();
    if (!tg?.BackButton) return;
    const back = () => {
      if (preview) { setPreview(null); return; }
      if (walletOpen) { setWalletOpen(false); return; }
      if (window.history.length > 1 && route !== "home") window.history.back();
      else if (route !== "home") navigate("home");
    };
    if (preview || walletOpen || route !== "home") tg.BackButton.show?.();
    else tg.BackButton.hide?.();
    tg.BackButton.onClick?.(back);
    return () => tg.BackButton?.offClick?.(back);
  }, [navigate, preview, route, walletOpen]);

  if (booting) return <Splash />;

  const tgUser = telegram()?.initDataUnsafe?.user;
  const avatar = tgUser?.photo_url || "";

  return (
    <div className="roxy-app">
      <header className="topbar">
        <button className="brand" type="button" data-roxy-customer-route="home" onClick={() => navigate("home")} aria-label="ROXY — главная">
          <RoxyMark />
          <span className="brand-copy"><strong>ROXY</strong><small>Студия творчества</small></span>
        </button>
        <button id="balance" className="balance-button" type="button" onClick={() => setWalletOpen(true)}>
          <span>Баланс</span><strong>{me ? `${compact(me.balance_rox)} ROX` : "—"}</strong>
        </button>
      </header>

      <main className="main-shell">
        {route === "home" && <HomeScreen models={models} recent={recent} trends={trends} onNavigate={navigate} onCreate={(media) => startNewGeneration(media)} onPreview={(item) => { setPreviewSurface("private"); setPreview(item); }} />}
        {route === "feed" && <FeedScreen items={feed} sort={feedSort} setSort={setFeedSort} onRefresh={() => void loadFeed(feedSort)} onPreview={(item) => { setPreviewSurface("feed"); setPreview(item); }} />}
        {route === "catalog" && <CatalogScreen models={models} families={families} trends={trends} onCreate={(model) => startNewGeneration(creationMedia(model), model.id)} onOpenPartners={() => navigate("partners")} onRunTrend={async (trend) => {
          if ((trend.reference_requirements?.min || 0) > 0) { showToast("Для этого тренда нужен пример. Скоро откроем удобную форму."); return; }
          try { const run = await api.runTrend(trend.id); const item = await api.generation(run.id); setPreviewSurface("private"); setPreview(item); showToast("Тренд запущен"); }
          catch (error) { showToast(error instanceof Error ? error.message : "Не удалось запустить тренд"); }
        }} />}
        {route === "create" && <CreateScreen key={createLaunch.nonce} launch={createLaunch} models={models} families={families} me={me} onBalance={refreshMe} onCreated={(item) => { setRecent((current) => [item, ...current.filter((x) => x.id !== item.id)].slice(0, 12)); setPreviewSurface("private"); setPreview(item); }} showToast={showToast} />}
        {route === "history" && <HistoryScreen items={history} hasMore={historyHasMore} onMore={() => historyBefore && void loadHistory(true, historyBefore)} onPreview={(item) => { setPreviewSurface("private"); setPreview(item); }} />}
        {route === "profile" && <ProfileScreen me={me} avatar={avatar} stats={partnerStats} tab={profileTab} setTab={setProfileTab} works={profileWorks} publications={profilePublications} onPreview={(item, surface) => { setPreviewSurface(surface); setPreview(item); }} onWallet={() => setWalletOpen(true)} onCopy={async (value) => { if (await copyText(value)) showToast("Ссылка скопирована"); }} />}
        {route === "partners" && <PartnerScreen me={me} stats={partnerStats} rewards={partnerRewards} invitations={partnerInvites} onRefresh={() => void loadPartners()} showToast={showToast} />}
      </main>

      <BottomNav route={route} onNavigate={(next) => next === "create" ? startNewGeneration() : navigate(next)} />

      {walletOpen && <WalletSheet me={me} onClose={() => setWalletOpen(false)} onRefresh={refreshMe} showToast={showToast} />}
      {preview && <Preview item={preview} surface={previewSurface} onClose={() => setPreview(null)} onReuse={reuseGeneration} onPublished={async (scope) => { await Promise.allSettled([loadProfile(), loadFeed(), loadHistory()]); showToast(scope === "feed" ? "Работа опубликована в ленте и профиле" : "Работа опубликована в профиле"); }} showToast={showToast} />}
      {onboarding?.enabled && !onboarding?.completed && <Onboarding data={onboarding} onDone={async () => { const next = await api.completeOnboarding(); setOnboarding(next); }} />}
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}

function Splash() {
  return <div className="splash" role="status" aria-label="ROXY загружается"><div className="splash-orbit"><span/><RoxyMark large /></div><strong>ROXY</strong><small>Студия творчества</small><div className="splash-progress"><i /></div></div>;
}

function RoxyMark({ large = false }: { large?: boolean }) {
  return <span className={`roxy-mark${large ? " large" : ""}`} aria-hidden="true"><span>RX</span></span>;
}

function HomeScreen({ models, recent, trends, onNavigate, onCreate, onPreview }: { models: GenerationModel[]; recent: Generation[]; trends: TrendItem[]; onNavigate: (route: Route) => void; onCreate: (media: CreationMedia) => void; onPreview: (item: Generation) => void }) {
  const counts = useMemo(() => ({ image: models.filter((m) => m.media_type === "image").length, video: models.filter((m) => m.media_type === "video").length, audio: models.filter((m) => m.media_type === "audio").length }), [models]);
  return <section className="screen home-screen">
    <div className="promo-slider" aria-label="Промо ROXY">{PROMO_SLIDES.map((slide) => <button className="promo-slide" type="button" key={slide.src} onClick={() => onNavigate("partners")}><img src={slide.src} alt={slide.title} /></button>)}</div>
    <SectionTitle kicker="Студия" title="Что создаём?" />
    <div className="format-grid"><FormatCard icon="image" title="Фото" count={counts.image} onClick={() => onCreate("image")} /><FormatCard icon="video" title="Видео" count={counts.video} onClick={() => onCreate("video")} /><FormatCard icon="music" title="Музыка" count={counts.audio} onClick={() => onCreate("audio")} /></div>
    <SectionTitle kicker="Тренды" title="Быстрый старт" action="Каталог" onAction={() => onNavigate("catalog")} />
    <TrendStrip items={trends.slice(0, 6)} />
    <SectionTitle kicker="Недавнее" title="Последние работы" action="Все" onAction={() => onNavigate("history")} />
    <MediaGrid items={recent.filter((item) => item.status === "succeeded").slice(0, 9)} empty="Готовые работы появятся здесь." onClick={onPreview} />
  </section>;
}

function FormatCard({ icon, title, count, onClick }: { icon: IconName; title: string; count: number; onClick: () => void }) {
  return <button className="format-card" type="button" onClick={onClick}><span className="format-icon"><Icon name={icon}/></span><strong>{title}</strong><small>{count ? `${count} моделей` : "Скоро"}</small><Icon name="chevron" className="format-chevron"/></button>;
}

function FeedScreen({ items, sort, setSort, onRefresh, onPreview }: { items: FeedCard[]; sort: "recent" | "top_day" | "top"; setSort: (sort: "recent" | "top_day" | "top") => void; onRefresh: () => void; onPreview: (item: FeedCard) => void }) {
  return <section className="screen"><ScreenHead kicker="Лента" title="Работы сообщества" copy="Смотрите свежие идеи, сохраняйте понравившееся и повторяйте работы в своём стиле." />
    <div className="segmented scrollable"><button className={sort === "recent" ? "active" : ""} type="button" onClick={() => setSort("recent")}>Новые</button><button className={sort === "top_day" ? "active" : ""} type="button" onClick={() => setSort("top_day")}>Топ дня</button><button className={sort === "top" ? "active" : ""} type="button" onClick={() => setSort("top")}>Топ</button><button type="button" onClick={onRefresh}>Обновить</button></div>
    <MediaGrid items={items} empty="Лента пока пуста. Опубликуйте работу в предпросмотре." onClick={onPreview} reactions />
  </section>;
}

function CatalogScreen({ models, families, trends, onCreate, onOpenPartners, onRunTrend }: { models: GenerationModel[]; families: GenerationModelFamily[]; trends: TrendItem[]; onCreate: (model: GenerationModel) => void; onOpenPartners: () => void; onRunTrend: (trend: TrendItem) => void | Promise<void> }) {
  const [media, setMedia] = useState<MediaFilter>("all");
  const [familySheet, setFamilySheet] = useState<GenerationModelFamily | null>(null);
  const byId = useMemo(() => new Map(models.map((model) => [model.id, model])), [models]);
  const filteredFamilies = media === "all" ? families : families.filter((family) => family.media_types?.includes(media));
  const filteredTrends = media === "all" || media === "audio" ? trends : trends.filter((trend) => trend.media_type === media);
  return <section className="screen"><PromoCarousel onOpenPartners={onOpenPartners} /><ScreenHead kicker="Каталог" title="Тренды и модели" copy="Начните с готового сценария или выберите модель под свою идею." />
    <div className="segmented scrollable">{(["all", "image", "video", "audio"] as const).map((key) => <button key={key} type="button" className={media === key ? "active" : ""} onClick={() => setMedia(key)}>{key === "all" ? "Все" : key === "image" ? "Фото" : key === "video" ? "Видео" : "Музыка"}</button>)}</div>
    <SectionTitle kicker="Тренды" title="Готовые сценарии" />
    <div className="model-grid">{filteredTrends.slice(0, 12).map((trend) => <button className="model-card" type="button" key={trend.id} onClick={() => void onRunTrend(trend)}><span className="model-icon"><Icon name={modelIcon(trend.media_type)}/></span><div><strong>{trend.title}</strong><small>{trend.description || trend.model?.title || "Тренд"}</small></div><span className="price-pill">{priceLabel(trend.cost_rox)}</span></button>)}</div>
    <SectionTitle kicker="Модели" title="Полный каталог" />
    <div className="model-grid">{filteredFamilies.map((family) => <button key={family.id} className="model-card" type="button" onClick={() => setFamilySheet(family)}><span className="model-icon"><Icon name={modelIcon(family.media_types?.[0])}/></span><div><strong>{family.title}</strong><small>{family.variant_count} вариантов</small></div><span className="price-pill">от {priceLabel(family.price_from_rox)}</span></button>)}</div>
    {familySheet && <FamilyVariantSheet family={familySheet} models={byId} selectedId="" onClose={() => setFamilySheet(null)} onChoose={(id) => { const model = byId.get(id); if (model) onCreate(model); setFamilySheet(null); }} />}
  </section>;
}

function PromoCarousel({ onOpenPartners }: { onOpenPartners: () => void }) {
  const [active, setActive] = useState(0);
  const paused = useRef(false);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!paused.current) setActive((current) => (current + 1) % PROMO_SLIDES.length);
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  const select = (index: number) => setActive((index + PROMO_SLIDES.length) % PROMO_SLIDES.length);
  const slide = PROMO_SLIDES[active];

  return <div className="promo-carousel" aria-label="Промо ROXY" onMouseEnter={() => { paused.current = true; }} onMouseLeave={() => { paused.current = false; }} onFocus={() => { paused.current = true; }} onBlur={() => { paused.current = false; }}>
    <button className="promo-carousel-slide" type="button" onClick={onOpenPartners} aria-label={slide.title}>
      <img src={slide.src} alt={slide.title} />
    </button>
    <button className="promo-carousel-arrow promo-carousel-prev" type="button" onClick={() => select(active - 1)} aria-label="Предыдущий слайд"><Icon name="chevron" size={18} /></button>
    <button className="promo-carousel-arrow promo-carousel-next" type="button" onClick={() => select(active + 1)} aria-label="Следующий слайд"><Icon name="chevron" size={18} /></button>
    <div className="promo-carousel-dots" role="tablist" aria-label="Слайды промо">
      {PROMO_SLIDES.map((item, index) => <button key={item.src} className={index === active ? "active" : ""} type="button" role="tab" aria-selected={index === active} aria-label={`Слайд ${index + 1}`} onClick={() => select(index)} />)}
    </div>
  </div>;
}

function TrendStrip({ items }: { items: TrendItem[] }) {
  if (!items.length) return <Empty text="Тренды скоро появятся здесь." />;
  return <div className="model-grid">{items.map((trend) => <div className="model-card" key={trend.id}><span className="model-icon"><Icon name={modelIcon(trend.media_type)}/></span><div><strong>{trend.title}</strong><small>{trend.description || trend.model?.title || "Готовый сценарий"}</small></div><span className="price-pill">{priceLabel(trend.cost_rox)}</span></div>)}</div>;
}

function CreateScreen({ launch, models, families, me, onBalance, onCreated, showToast }: { launch: CreateLaunch; models: GenerationModel[]; families: GenerationModelFamily[]; me: Me | null; onBalance: () => Promise<Me>; onCreated: (item: Generation) => void; showToast: (message: string) => void }) {
  const launchModelId = launch.kind === "reuse" ? launch.payload.model_id : launch.modelId;
  const storedModelId = typeof window !== "undefined" ? localStorage.getItem(MODEL_KEY) : null;
  const storedMedia = typeof window !== "undefined" ? normalizeMediaFilter(localStorage.getItem(MEDIA_FILTER_KEY)) : "all";
  const [selectedId, setSelectedId] = useState(launchModelId || storedModelId || models[0]?.id || "");
  const [media, setMedia] = useState<MediaFilter>(launch.kind === "new" && launch.media ? launch.media : storedMedia);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoteError, setQuoteError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [familySheet, setFamilySheet] = useState<GenerationModelFamily | null>(null);
  const quoteSeq = useRef(0);
  const byId = useMemo(() => new Map(models.map((model) => [model.id, model])), [models]);
  const selected = models.find((model) => model.id === selectedId) || models[0] || null;
  const visibleFamilies = useMemo(() => media === "all" ? families : families.filter((family) => family.media_types?.includes(media)), [families, media]);

  useEffect(() => {
    if (!models.length) return;
    const requestedId = launch.kind === "reuse" ? launch.payload.model_id : launch.modelId || storedModelId || models[0]?.id;
    const target = models.find((model) => model.id === requestedId) || models[0];
    if (!target) return;
    setSelectedId(target.id);
    localStorage.setItem(MODEL_KEY, target.id);
    const nextMedia = launch.kind === "new" && launch.media ? launch.media : creationMedia(target) || storedMedia;
    setMedia(nextMedia);
    if (nextMedia !== "all") localStorage.setItem(MEDIA_FILTER_KEY, nextMedia);
    setDrafts({ [target.id]: launch.kind === "reuse" ? hydrateReuseDraft(target, launch.payload) : createDefaultDraft(target) });
    setQuote(null);
    setQuoteError("");
  }, [launch, models]);

  useEffect(() => {
    if (!visibleFamilies.length || !models.length) return;
    const visible = visibleFamilies.some((family) => family.variants.some((variant) => variant.id === selectedId));
    if (visible) return;
    const next = visibleFamilies.flatMap((family) => family.variants).map((variant) => byId.get(variant.id)).find(Boolean);
    if (next) chooseModel(next.id);
  }, [byId, models.length, selectedId, visibleFamilies]);

  const draft = useMemo(() => {
    if (!selected) return null;
    return drafts[selected.id] || createDefaultDraft(selected);
  }, [drafts, selected]);

  const persist = useCallback((modelId: string, next: Draft) => {
    setDrafts((current) => ({ ...current, [modelId]: next }));
  }, []);

  const updateValue = (name: string, value: unknown) => { if (selected && draft) persist(selected.id, { ...draft, values: { ...draft.values, [name]: value } }); };
  const errors = selected && draft ? validateDraft(selected, draft) : ["Выберите модель"];

  useEffect(() => {
    if (!selected || !draft || errors.length || uploading) { setQuote(null); return; }
    const seq = ++quoteSeq.current;
    const timer = window.setTimeout(async () => {
      try { const next = await api.quote(buildPayload(selected, draft)); if (quoteSeq.current === seq) { setQuote(next); setQuoteError(""); } }
      catch (error) { if (quoteSeq.current === seq) { setQuote(null); setQuoteError(error instanceof Error ? error.message : "Не удалось рассчитать цену"); } }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [draft, selected, uploading, errors.join("|")]);

  const chooseModel = (id: string) => {
    const target = byId.get(id);
    if (!target) return;
    setDrafts((current) => ({ ...current, [id]: createDefaultDraft(target) }));
    setSelectedId(id);
    localStorage.setItem(MODEL_KEY, id);
    const nextMedia = creationMedia(target);
    if (nextMedia) {
      setMedia(nextMedia);
      localStorage.setItem(MEDIA_FILTER_KEY, nextMedia);
    }
    setQuote(null);
    setQuoteError("");
    haptic("light");
  };
  const chooseMedia = (next: MediaFilter) => { setMedia(next); localStorage.setItem(MEDIA_FILTER_KEY, next); };
  const setScenario = (id: string) => { if (!selected || !draft) return; const scenario = selected.ui_schema?.scenario?.items?.find((item) => item.id === id); const values = { ...draft.values }; for (const key of scenario?.clear_fields || []) delete values[key]; persist(selected.id, { ...draft, scenario: id, values }); };

  const submit = async () => {
    if (!selected || !draft || errors.length || !quote || submitting) return;
    if (!telegram()?.initData) { showToast("Откройте ROXY через Telegram-бота"); return; }
    setSubmitting(true);
    try {
      const created = await api.create(buildPayload(selected, draft));
      await onBalance();
      let item: Generation = { id: created.id, status: created.status || "queued", model: selected, created_at: new Date().toISOString() };
      try { item = await api.generation(created.id); } catch {}
      notify("success");
      showToast("Генерация запущена. ROXY можно закрыть — результат придёт в Telegram.");
      onCreated(item);
    } catch (error) {
      notify("error");
      showToast(error instanceof Error ? error.message : "Не удалось запустить генерацию");
    } finally { setSubmitting(false); }
  };

  if (!selected || !draft) return <section className="screen"><ScreenHead kicker="Создание" title="Каталог моделей загружается" /></section>;
  const fields = visibleFields(selected, draft);
  const groups = selected.ui_schema?.groups || [{ id: "main", title: "Настройки" }];

  return <section className="screen create-screen"><ScreenHead kicker="Создание" title={launch.kind === "reuse" ? "Использовать настройки" : "Новая работа"} copy="Опишите идею, добавьте примеры и выберите подходящий формат." />
    {launch.kind === "reuse" && <div className="panel"><span className="kicker">На основе работы</span><p className="muted">Описание и подходящие настройки уже перенесены. Если выбрать другую модель, ROXY подготовит форму заново.</p></div>}
    <div className="create-layout"><div className="create-controls"><div className="panel"><label className="label">Модель</label><div className="segmented scrollable family-tabs">{(["all", "image", "video", "audio"] as const).map((key) => <button key={key} type="button" className={media === key ? "active" : ""} onClick={() => chooseMedia(key)}>{key === "all" ? "Все" : key === "image" ? "Фото" : key === "video" ? "Видео" : "Музыка"}</button>)}</div><div className="family-grid">{visibleFamilies.map((family) => { const active = family.variants.some((variant) => variant.id === selected.id); return <button className={`family-card${active ? " active" : ""}`} type="button" key={family.id} onClick={() => setFamilySheet(family)}><span className="model-icon"><Icon name={modelIcon(family.media_types?.[0])}/></span><div><strong>{family.title}</strong><small>{family.variant_count} вариантов</small></div><span className="price-pill">от {priceLabel(family.price_from_rox)}</span></button>; })}</div></div>
      {selected.ui_schema?.scenario?.items?.length ? <div className="panel"><label className="label">Режим</label><div className="segmented scrollable">{selected.ui_schema.scenario.items.map((item) => <button key={item.id} type="button" className={draft.scenario === item.id ? "active" : ""} onClick={() => setScenario(item.id)}>{item.title}</button>)}</div></div> : null}
      {groups.map((group) => { const grouped = fields.filter((field) => (field.group || "main") === group.id || (groups.length === 1 && !field.group)); if (!grouped.length) return null; return <div className="panel" key={group.id}><h2>{group.title}</h2><div className="form-stack">{grouped.map((field) => <DynamicField key={field.name} field={field} value={draft.values[field.name]} onChange={(value) => updateValue(field.name, value)} onUpload={async (files) => { setUploading(true); try { const max = field.control === "file" ? 1 : field.max_items || 20; const urls: string[] = field.control === "files" && Array.isArray(draft.values[field.name]) ? [...draft.values[field.name] as string[]] : []; for (const file of files.slice(0, Math.max(0, max - urls.length))) { if (field.max_size_mb && file.size > field.max_size_mb * 1024 * 1024) { showToast(`${file.name}: максимум ${field.max_size_mb} МБ`); continue; } const uploaded = await api.upload(file); if (field.control === "file") { updateValue(field.name, uploaded.url); break; } urls.push(uploaded.url); } if (field.control === "files") updateValue(field.name, urls); notify("success"); } catch (error) { notify("error"); showToast(error instanceof Error ? error.message : "Ошибка загрузки"); } finally { setUploading(false); } }} />)}</div></div>; })}
      {selected.ui_schema?.billing_seconds && <div className="panel"><label className="label">{selected.ui_schema.billing_seconds.label || "Длительность"}</label><input className="control" type="number" min={selected.ui_schema.billing_seconds.min || 1} max={selected.ui_schema.billing_seconds.max || 600} value={draft.billing_seconds ?? ""} onChange={(e) => persist(selected.id, { ...draft, billing_seconds: e.target.value ? Number(e.target.value) : null })}/></div>}
    </div><aside className="create-summary panel"><span className="kicker">Итог</span><h2>{selected.title}</h2><p className="muted">{me ? `Баланс: ${compact(me.balance_rox)} ROX` : "Откройте через Telegram для запуска"}</p><div className="quote-box"><span>Стоимость</span><strong>{quote ? `${compact(quote.cost_rox)} ROX` : "—"}</strong><small>{quoteError || errors[0] || (quote ? "Списание только в ROX" : "Считаю…")}</small></div><button className="primary wide" disabled={!quote || errors.length > 0 || uploading || submitting} type="button" onClick={() => void submit()}><Icon name="spark"/>{submitting ? "Запускаю…" : quote ? `Создать · ${compact(quote.cost_rox)} ROX` : "Создать"}</button></aside></div>
    {familySheet && <FamilyVariantSheet family={familySheet} models={byId} selectedId={selected.id} onClose={() => setFamilySheet(null)} onChoose={(id) => { chooseModel(id); setFamilySheet(null); }} />}
  </section>;
}

function FamilyVariantSheet({ family, models, selectedId, onClose, onChoose }: { family: GenerationModelFamily; models: Map<string, GenerationModel>; selectedId: string; onClose: () => void; onChoose: (id: string) => void }) {
  return <div className="sheet-backdrop" role="presentation" onClick={onClose}><section className="bottom-sheet" role="dialog" aria-modal="true" aria-label={family.title} onClick={(event) => event.stopPropagation()}><div className="sheet-head"><div><span className="kicker">Модель</span><h2>{family.title}</h2></div><button className="icon-button" type="button" onClick={onClose} aria-label="Закрыть"><Icon name="close"/></button></div><div className="variant-list">{family.variants.map((variant) => { const model = models.get(variant.id); const active = variant.id === selectedId; return <button key={variant.id} className={`variant-row${active ? " active" : ""}`} type="button" onClick={() => model && onChoose(model.id)} disabled={!model}><span className="variant-badge">{variant.badge || (variant.recommended ? "TOP" : variant.version || "AI")}</span><span><strong>{variant.version || variant.title}</strong><small>{variant.description || variant.title}</small></span><span className="price-pill">{priceLabel(variant.price_rox)}</span></button>; })}</div></section></div>;
}

function DynamicField({ field, value, onChange, onUpload }: { field: UiField; value: unknown; onChange: (value: unknown) => void; onUpload: (files: File[]) => Promise<void> }) {
  const label = userFieldLabel(field);
  if (field.control === "toggle") return <label className="toggle-row"><span><strong>{field.label}</strong></span><input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)}/><i/></label>;
  if (field.control === "file" || field.control === "files") {
    const urls = field.control === "files" ? (Array.isArray(value) ? value as string[] : []) : value ? [String(value)] : [];
    return <div className="field"><label className="label">{label}{field.required ? " *" : ""}</label><SavedReferencePicker field={field} value={value} onChange={onChange}/><label className="upload-control"><Icon name="upload"/><span>{urls.length ? `${urls.length} загружено` : "Выбрать файл"}</span><input type="file" multiple={field.control === "files"} accept={field.accept || "image/*,video/*,audio/*"} onChange={(e) => void onUpload(Array.from(e.target.files || []))}/></label>{urls.length > 0 && <div className="upload-list">{urls.map((url, i) => <button type="button" key={`${url}-${i}`} onClick={() => onChange(field.control === "files" ? urls.filter((_, index) => index !== i) : "")}>{safeFileName(url) || `Файл ${i + 1}`} ×</button>)}</div>}</div>;
  }
  if (field.control === "textarea" || field.control === "json") return <label className="field"><span className="label">{label}{field.required ? " *" : ""}</span><textarea className="control textarea" placeholder={field.placeholder || ""} value={value == null ? "" : typeof value === "string" ? value : JSON.stringify(value, null, 2)} onChange={(e) => onChange(e.target.value)}/></label>;
  if (field.suggestions?.length) return <label className="field"><span className="label">{label}{field.required ? " *" : ""}</span><select className="control" value={value == null ? "" : String(value)} onChange={(e) => onChange(e.target.value)}><option value="">Выберите</option>{field.suggestions.map((item) => <option key={String(item)} value={String(item)}>{String(item)}</option>)}</select></label>;
  return <label className="field"><span className="label">{label}{field.required ? " *" : ""}</span><div className="input-with-suffix"><input className="control" type={field.control === "number" ? "number" : "text"} min={field.min} max={field.max} step={field.step} placeholder={field.placeholder || ""} value={value == null ? "" : String(value)} onChange={(e) => onChange(field.control === "number" ? (e.target.value ? Number(e.target.value) : null) : e.target.value)}/>{field.suffix && <span>{field.suffix}</span>}</div></label>;
}

function safeFileName(url: string): string {
  try { return new URL(url, window.location.href).pathname.split("/").pop() || ""; } catch { return ""; }
}

function HistoryScreen({ items, hasMore, onMore, onPreview }: { items: Generation[]; hasMore: boolean; onMore: () => void; onPreview: (item: Generation) => void }) {
  return <section className="screen"><ScreenHead kicker="История" title="Все работы" copy="Здесь собраны готовые работы и то, что ещё создаётся."/><div className="history-list">{items.length ? items.map((item) => <button className="history-card" type="button" key={item.id} onClick={() => onPreview(item)}><MediaThumb item={item}/><div><strong>{modelOf(item)?.title || "Работа ROXY"}</strong><small>{dateLabel(item.created_at)} · {statusLabel(item.status)}</small>{item.error && <p>Не получилось создать работу. Попробуйте ещё раз или измените описание.</p>}</div><span className={`status ${item.status}`}>{statusLabel(item.status)}</span></button>) : <Empty text="История пока пуста."/>}</div>{hasMore && <button className="secondary wide" type="button" onClick={onMore}>Показать ещё</button>}</section>;
}

function ProfileScreen({ me, avatar, stats, tab, setTab, works, publications, onPreview, onWallet, onCopy }: { me: Me | null; avatar: string; stats: PartnerStats | null; tab: "works" | "publications"; setTab: (tab: "works" | "publications") => void; works: Generation[]; publications: ProfilePublication[]; onPreview: (item: Generation | FeedCard, surface: PreviewSurface) => void; onWallet: () => void; onCopy: (value: string | null | undefined) => Promise<void> }) {
  const likes = publications.reduce((sum, item) => sum + Number((item as FeedCard).likes_count || 0), 0);
  const link = profileLink(stats, me);
  return <section className="screen profile-screen"><div className="profile-hero panel"><div className="avatar">{avatar ? <img src={avatar} alt=""/> : <span>{(me?.first_name?.[0] || me?.username?.[0] || "R").toUpperCase()}</span>}</div><div className="profile-copy"><span className="kicker">Профиль</span><h1>{displayName(me)}</h1><p>{me?.username ? `@${me.username}` : "Автор ROXY"}</p></div><button className="icon-button" type="button" onClick={onWallet} aria-label="Баланс"><Icon name="wallet"/></button><div className="profile-stats"><div><strong>{works.length}</strong><span>работ</span></div><div><strong>{publications.length}</strong><span>публикаций</span></div><div><strong>{compact(likes)}</strong><span>лайков</span></div></div></div>{link && <div className="panel"><span className="kicker">Ссылка на профиль</span><p className="muted">{link}</p><button className="secondary wide" type="button" onClick={() => void onCopy(link)}>Скопировать профиль</button></div>}<div className="profile-tabs"><button type="button" className={tab === "works" ? "active" : ""} onClick={() => setTab("works")}>Работы</button><button type="button" className={tab === "publications" ? "active" : ""} onClick={() => setTab("publications")}>Публикации</button></div>{tab === "works" ? <MediaGrid items={works} empty="Готовых работ пока нет." onClick={(item) => onPreview(item, "private")}/> : <MediaGrid items={publications} empty="Публикаций пока нет. Открой работу и нажми “В профиль” или “В ленту + профиль”." onClick={(item) => onPreview(item, "surface" in item && item.surface ? item.surface as FeedSurface : "private")} reactions/>}</section>;
}

function PartnerScreen({ me, stats, rewards, invitations, onRefresh, showToast }: { me: Me | null; stats: PartnerStats | null; rewards: ReferralReward[]; invitations: ReferralInvitation[]; onRefresh: () => void; showToast: (message: string) => void }) {
  const pLink = profileLink(stats, me);
  const copy = async (value?: string | null) => { if (await copyText(value)) showToast("Ссылка скопирована"); };
  return <section className="screen"><ScreenHead kicker="Партнёрам" title="Кабинет автора" copy="Делитесь ссылкой, приглашайте друзей и отслеживайте бонусы в одном месте." />
    <div className="profile-stats panel"><div><strong>{compact(stats?.first_line)}</strong><span>1 линия</span></div><div><strong>{compact(stats?.second_line)}</strong><span>2 линия</span></div><div><strong>{compact(stats?.partner_balance_rub)} ₽</strong><span>доступно</span></div></div>
    <div className="panel"><span className="kicker">Реферальная ссылка</span><p className="muted">{stats?.referral_link || "Ссылка появится после входа в ROXY."}</p><button className="primary wide" type="button" onClick={() => void copy(stats?.referral_link)}>Скопировать ссылку</button>{pLink && <button className="secondary wide" type="button" onClick={() => void copy(pLink)}>Скопировать профиль</button>}{stats?.partner_chat_url && <a className="secondary wide" href={stats.partner_chat_url} target="_blank" rel="noreferrer">Чат партнёров</a>}</div>
    <SectionTitle kicker="Доход" title="Последние начисления" action="Обновить" onAction={onRefresh} />
    <div className="transaction-list">{rewards.length ? rewards.map((reward) => <div className="transaction" key={reward.id}><div><strong>{reward.source_user?.first_name || reward.source_user?.username || `Линия ${reward.line}`}</strong><small>{dateLabel(reward.created_at)} · {statusLabel(reward.status)}</small></div><span>+{compact(reward.net_amount_rox || reward.amount_rox || reward.amount)} ROX</span></div>) : <Empty text="Начислений пока нет." />}</div>
    <SectionTitle kicker="Рефералы" title="Новые приглашения" />
    <div className="transaction-list">{invitations.length ? invitations.map((item) => <div className="transaction" key={item.user_id}><div><strong>{item.first_name || item.username || "Пользователь"}</strong><small>{dateLabel(item.joined_at)} · линия {item.line}</small></div><span>{item.username ? `@${item.username}` : "—"}</span></div>) : <Empty text="Приглашений пока нет." />}</div>
  </section>;
}

function MediaGrid<T extends Generation | FeedCard>({ items, empty, onClick, reactions = false }: { items: T[]; empty: string; onClick: (item: T) => void; reactions?: boolean }) {
  if (!items.length) return <Empty text={empty}/>;
  return <div className="media-grid">{items.map((item) => <button className="media-tile" type="button" key={item.id} onClick={() => onClick(item)}><MediaThumb item={item}/>{reactions && <span className="tile-reactions"><Icon name="heart" size={13}/>{compact((item as FeedCard).likes_count)}</span>}</button>)}</div>;
}

function MediaThumb({ item }: { item: Generation | FeedCard }) {
  const url = mediaUrl(item);
  const type = mediaType(item);
  if (!url) return <span className="media-placeholder"><Icon name={type === "video" ? "video" : type === "audio" ? "music" : "image"}/><small>{statusLabel(item.status) || "Готовим"}</small></span>;
  if (type === "video") return <video src={url} muted playsInline preload="metadata"/>;
  if (type === "audio") return <span className="media-placeholder audio"><Icon name="music"/><small>Аудио</small></span>;
  return <img src={url} alt="" loading="lazy"/>;
}

function Preview({ item, surface, onClose, onReuse, onPublished, showToast }: { item: Generation | FeedCard; surface: PreviewSurface; onClose: () => void; onReuse: (generationId: string) => Promise<void>; onPublished: (scope: "profile" | "feed") => Promise<void>; showToast: (message: string) => void }) {
  const [current, setCurrent] = useState<Generation | FeedCard>(item);
  const [publishing, setPublishing] = useState<"profile" | "feed" | null>(null);
  const [promptVisible, setPromptVisible] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [commentsOpen, setCommentsOpen] = useState(false);
  const [comments, setComments] = useState<FeedComment[]>([]);
  const [commentText, setCommentText] = useState("");
  const url = resultMediaUrl(current);
  const type = mediaType(current);
  const card = current as FeedCard;
  const canPublish = surface === "private" && current.status === "succeeded";
  const canReuse = canPublish && current.prompt_actions_allowed !== false;
  const socialSurface: FeedSurface = surface === "profile" ? "profile" : "feed";
  const canSocial = surface !== "private";
  const isMine = Boolean(card.is_mine);
  const referenceImages = canSocial && !card.references_hidden ? card.reference_images || [] : [];
  const referenceVideos = canSocial && !card.references_hidden ? card.reference_videos || [] : [];

  const publish = async (scope: "profile" | "feed") => {
    setPublishing(scope);
    try { const result = await api.publish(current.id, { scope, promptVisible, referencesVisible: false }); setCurrent(result.item); notify("success"); await onPublished(scope); }
    catch (error) { notify("error"); showToast(error instanceof Error ? error.message : "Не удалось опубликовать"); }
    finally { setPublishing(null); }
  };
  const reuseSettings = async () => { setBusy("reuse"); try { await onReuse(current.id); } catch (error) { showToast(error instanceof Error ? error.message : "Не удалось перенести настройки"); } finally { setBusy(null); } };
  const toggleLike = async () => { setBusy("like"); try { const result = card.liked_by_me ? await api.unlike(current.id, socialSurface) : await api.like(current.id, socialSurface); setCurrent({ ...card, liked_by_me: result.liked_by_me, likes_count: result.likes_count }); } catch (error) { showToast(error instanceof Error ? error.message : "Не удалось поставить лайк"); } finally { setBusy(null); } };
  const share = async () => { setBusy("share"); try { const result = await api.share(current.id, socialSurface); setCurrent({ ...card, shares_count: result.shares_count }); if (result.link && await copyText(result.link)) showToast("Ссылка скопирована"); } catch (error) { showToast(error instanceof Error ? error.message : "Не удалось поделиться"); } finally { setBusy(null); } };
  const loadComments = async () => { setBusy("comments"); try { const result = await api.comments(current.id, socialSurface); setComments(result.items || []); setCommentsOpen(true); } catch (error) { showToast(error instanceof Error ? error.message : "Не удалось открыть комментарии"); } finally { setBusy(null); } };
  const addComment = async () => { const text = commentText.trim(); if (!text) return; setBusy("comment"); try { const next = await api.addComment(current.id, socialSurface, text); setComments((items) => [next, ...items]); setCommentText(""); setCurrent({ ...card, comments_count: Number(card.comments_count || 0) + 1 }); } catch (error) { showToast(error instanceof Error ? error.message : "Не удалось отправить комментарий"); } finally { setBusy(null); } };
  const remix = async () => { setBusy("remix"); try { await api.remix(current.id, socialSurface); showToast("Повтор запущен"); } catch (error) { showToast(error instanceof Error ? error.message : "Не удалось повторить"); } finally { setBusy(null); } };
  const removePublication = async () => { setBusy("remove"); try { await api.removePublication(current.id, "private"); notify("success"); onClose(); await onPublished("profile"); } catch (error) { notify("error"); showToast(error instanceof Error ? error.message : "Не удалось убрать публикацию"); } finally { setBusy(null); } };

  return <div className="overlay" role="dialog" aria-modal="true"><button className="overlay-backdrop" type="button" onClick={onClose} aria-label="Закрыть"/><div className="preview-card"><button className="preview-close" type="button" onClick={onClose} aria-label="Закрыть"><Icon name="close"/></button><div className="preview-media">{url && type === "video" ? <video src={url} controls playsInline autoPlay={false}/> : url && type === "audio" ? <audio src={url} controls/> : url ? <img src={url} alt="Результат"/> : <span className="media-placeholder"><Icon name="image"/></span>}</div><div className="preview-copy"><span className="kicker">{surface === "private" ? "Моя работа" : surface === "profile" ? "Профиль" : "Лента"}</span><h2>{modelOf(current)?.title || card.model || "Работа ROXY"}</h2><p className="muted">{dateLabel(current.created_at || card.feed_published_at)}</p>{current.prompt && !current.prompt_hidden && <p className="prompt-copy">{current.prompt}</p>}{(referenceImages.length > 0 || referenceVideos.length > 0) && <div className="panel" style={{ padding: 12 }}><span className="kicker">Примеры</span><div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>{referenceImages.map((reference, index) => { const durable = reference.includes("/uploads/refs/"); const suffix = `?surface=${encodeURIComponent(socialSurface)}`; const thumb = durable ? `/api/v1/feed/reference-image/${encodeURIComponent(current.id)}/${index}/thumbnail${suffix}` : reference; const full = durable ? `/api/v1/feed/reference-image/${encodeURIComponent(current.id)}/${index}/full${suffix}` : reference; return <a key={`${reference}-${index}`} href={full} target="_blank" rel="noreferrer" aria-label={`Открыть пример ${index + 1}`}><img src={thumb} alt="" loading="lazy" style={{ width: 72, height: 72, borderRadius: 10, objectFit: "cover" }} /></a>; })}{referenceVideos.map((reference, index) => <a key={`${reference}-${index}`} href={reference} target="_blank" rel="noreferrer" aria-label={`Открыть видео-пример ${index + 1}`}><video src={reference} muted playsInline preload="metadata" style={{ width: 72, height: 72, borderRadius: 10, objectFit: "cover" }} /></a>)}</div></div>}{canPublish && <div className="panel" style={{ padding: 12 }}><label className="toggle-row"><span><strong>Показать описание</strong><small>Будет видно в публикации только если включить</small></span><input type="checkbox" checked={promptVisible} onChange={(e) => setPromptVisible(e.target.checked)}/><i/></label></div>}<div className="preview-actions">{url && <a className="primary" href={url} target="_blank" rel="noreferrer">Открыть результат</a>}{canReuse && <button className="secondary" type="button" disabled={busy === "reuse"} onClick={() => void reuseSettings()}><Icon name="create" size={16}/>{busy === "reuse" ? "Переношу…" : "Использовать настройки"}</button>}{canPublish && <button className="secondary" type="button" disabled={Boolean(publishing)} onClick={() => void publish("profile")}>{publishing === "profile" ? "Публикую…" : "В профиль"}</button>}{canPublish && <button className="primary" type="button" disabled={Boolean(publishing)} onClick={() => void publish("feed")}>{publishing === "feed" ? "Публикую…" : "В ленту + профиль"}</button>}{canSocial && <button className="secondary" type="button" disabled={busy === "like"} onClick={() => void toggleLike()}><Icon name="heart" size={16}/>{card.liked_by_me ? "Лайк есть" : "Лайк"} · {compact(card.likes_count)}</button>}{canSocial && <button className="secondary" type="button" disabled={busy === "share"} onClick={() => void share()}><Icon name="share" size={16}/>Поделиться · {compact(card.shares_count)}</button>}{canSocial && <button className="secondary" type="button" disabled={busy === "comments"} onClick={() => void loadComments()}><Icon name="comment" size={16}/>Комментарии · {compact(card.comments_count)}</button>}{canSocial && card.prompt_actions_allowed !== false && <button className="secondary" type="button" disabled={busy === "remix"} onClick={() => void remix()}><Icon name="create" size={16}/>Повторить</button>}{canSocial && isMine && <button className="secondary" type="button" disabled={busy === "remove"} onClick={() => void removePublication()}>Убрать</button>}</div>{commentsOpen && <div className="panel" style={{ padding: 12 }}><div className="section-title"><div><span className="kicker">Обсуждение</span><h2>Комментарии</h2></div><button type="button" onClick={() => setCommentsOpen(false)}>Закрыть</button></div><div className="form-stack"><textarea className="control textarea" maxLength={300} placeholder="Ваш комментарий" value={commentText} onChange={(event) => setCommentText(event.target.value)}/><button className="primary wide" type="button" disabled={!commentText.trim() || busy === "comment"} onClick={() => void addComment()}>{busy === "comment" ? "Отправляю…" : "Отправить"}</button></div><div className="transaction-list">{comments.length ? comments.map((comment) => <div className="transaction" key={comment.id}><div><strong>{comment.author?.display_name || comment.author?.username || "Пользователь"}</strong><small>{dateLabel(comment.created_at)}</small></div><span>{comment.text}</span></div>) : <Empty text="Комментариев пока нет."/>}</div></div>}</div></div></div>;
}

function WalletSheet({ me, onClose, onRefresh, showToast }: { me: Me | null; onClose: () => void; onRefresh: () => Promise<Me>; showToast: (message: string) => void }) {
  const [packages, setPackages] = useState<Record<string, { credits: string; prices: Record<string, string> }>>({});
  const [transactions, setTransactions] = useState<Array<{ id: string; kind: string; amount: string; balance_after: string; status: string; created_at: string }>>([]);
  const [selected, setSelected] = useState("");
  const [currency, setCurrency] = useState<"RUB" | "USD" | "EUR">("RUB");
  const [email, setEmail] = useState("");
  const [paying, setPaying] = useState(false);
  useEffect(() => { void Promise.allSettled([api.paymentPackages().then((data) => { setPackages(data.packages || {}); setSelected((current) => current || Object.keys(data.packages || {})[0] || ""); }), api.transactions().then(setTransactions)]); }, []);
  const pay = async () => { if (!selected) return; setPaying(true); try { const payment = await api.createPayment(selected, currency, email); if (!payment.payment_url) throw new Error("Платёжная ссылка не получена"); const tg = telegram(); if (tg?.openLink) tg.openLink(payment.payment_url); else window.open(payment.payment_url, "_blank", "noopener,noreferrer"); showToast("Платёж создан"); window.setTimeout(() => void onRefresh(), 2000); } catch (error) { showToast(error instanceof Error ? error.message : "Не удалось создать платёж"); } finally { setPaying(false); } };
  return <div className="overlay sheet-overlay" role="dialog" aria-modal="true"><button className="overlay-backdrop" type="button" onClick={onClose}/><section className="sheet"><div className="sheet-handle"/><header><div><span className="kicker">Баланс</span><h2>{me ? `${compact(me.balance_rox)} ROX` : "Баланс"}</h2></div><button className="icon-button" type="button" onClick={onClose}><Icon name="close"/></button></header><SectionTitle kicker="Пополнение" title="Выберите пакет"/><div className="package-grid">{Object.entries(packages).map(([id, pack]) => <button type="button" key={id} className={selected === id ? "package active" : "package"} onClick={() => setSelected(id)}><strong>{compact(pack.credits)} ROX</strong><small>{compact(pack.prices[currency] || 0)} {currency}</small></button>)}</div><div className="segmented scrollable">{(["RUB", "USD", "EUR"] as const).filter((item) => Object.values(packages).some((pack) => pack.prices[item])).map((item) => <button type="button" key={item} className={currency === item ? "active" : ""} onClick={() => setCurrency(item)}>{item}</button>)}</div><input className="wallet-input" type="email" inputMode="email" autoComplete="email" placeholder="Email для чека" value={email} onChange={(event) => setEmail(event.target.value)} /><button className="primary wide" type="button" disabled={!selected || !email.trim() || paying} onClick={() => void pay()}>{paying ? "Готовлю оплату…" : "Перейти к оплате"}</button><SectionTitle kicker="История" title="Последние движения"/><div className="transaction-list">{transactions.slice(0, 12).map((tx) => <div className="transaction" key={tx.id}><div><strong>{transactionLabel(tx.kind)}</strong><small>{dateLabel(tx.created_at)}</small></div><span className={Number(tx.amount) >= 0 ? "positive" : "negative"}>{Number(tx.amount) >= 0 ? "+" : ""}{compact(tx.amount)} ROX</span></div>)}</div></section></div>;
}

function Onboarding({ data, onDone }: { data: Record<string, any>; onDone: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  return <div className="overlay onboarding-overlay" role="dialog" aria-modal="true"><div className="onboarding-card"><RoxyMark large/><span className="kicker">Добро пожаловать</span><h1>{data.title || "ROXY"}</h1><p>{data.body || "Студия для создания фото, видео и музыки."}</p><div className="onboarding-links">{data.rules_url && <a href={data.rules_url} target="_blank" rel="noreferrer">Правила</a>}{data.privacy_url && <a href={data.privacy_url} target="_blank" rel="noreferrer">Конфиденциальность</a>}</div><button className="primary wide" type="button" disabled={busy} onClick={async () => { setBusy(true); try { await onDone(); } finally { setBusy(false); } }}>{busy ? "Открываю…" : "Открыть ROXY"}</button></div></div>;
}

function BottomNav({ route, onNavigate }: { route: Route; onNavigate: (route: Route) => void }) {
  const menu: Array<[Route, IconName, string]> = [["home", "home", "Студия"], ["feed", "heart", "Лента"], ["catalog", "catalog", "Каталог"], ["create", "create", "Создать"], ["partners", "share", "Партнёры"], ["profile", "profile", "Профиль"]];
  return <nav className="bottom-nav" aria-label="Основная навигация">{menu.map(([key, icon, label]) => <button type="button" key={key} data-roxy-customer-route={key} className={`${route === key ? "active " : ""}${key === "create" ? "central" : ""}`} onClick={() => onNavigate(key)} aria-current={route === key ? "page" : undefined}><span><Icon name={icon}/></span><small>{label}</small></button>)}</nav>;
}

function SectionTitle({ kicker, title, action, onAction }: { kicker: string; title: string; action?: string; onAction?: () => void }) {
  return <div className="section-title"><div><span className="kicker">{kicker}</span><h2>{title}</h2></div>{action && <button type="button" onClick={onAction}>{action}<Icon name="chevron" size={16}/></button>}</div>;
}

function ScreenHead({ kicker, title, copy }: { kicker: string; title: string; copy?: string }) {
  return <header className="screen-head"><span className="kicker">{kicker}</span><h1>{title}</h1>{copy && <p>{copy}</p>}</header>;
}

function Empty({ text }: { text: string }) {
  return <div className="empty"><Icon name="spark"/><p>{text}</p></div>;
}
