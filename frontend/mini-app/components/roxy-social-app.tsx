"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
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
  Quote,
  Route,
  UiField,
} from "@/lib/types";
import { Icon, type IconName } from "./icons";

const ROUTES: Route[] = ["home", "catalog", "create", "history", "profile"];
const DRAFTS_KEY = "roxy.next.generation-drafts.v2";
const MODEL_KEY = "ksu-selected-model";
const MEDIA_FILTER_KEY = "ksu-selected-media";
const ACTIVE_STATUSES = new Set(["queued", "retry", "submitting", "generating"]);

type PreviewSurface = "private" | FeedSurface;

function isRoute(value: string | null): value is Route {
  return ROUTES.includes(value as Route);
}

function compact(value: unknown): string {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  return new Intl.NumberFormat("ru-RU", {
    notation: Math.abs(number) >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(number);
}

function mediaUrl(item: Generation | FeedCard): string {
  return (item as FeedCard).preview_url || item.result_url || item.result_urls?.[0] || item.media?.[0]?.url || "";
}

function modelOf(item: Generation | FeedCard): GenerationModel | null {
  return item.model && typeof item.model === "object" ? item.model : null;
}

function mediaType(item: Generation | FeedCard): string {
  const model = modelOf(item);
  if (model?.media_type) return model.media_type;
  const url = mediaUrl(item);
  if (/\.(mp4|webm|mov)(\?|$)/i.test(url)) return "video";
  if (/\.(mp3|wav|m4a|aac|ogg)(\?|$)/i.test(url)) return "audio";
  return "image";
}

function modelIcon(media?: string): IconName {
  return media === "video" ? "video" : media === "audio" ? "music" : "image";
}

function priceLabel(value?: string | null): string {
  if (value === "0.00" || value === "0") return "Бесплатно";
  return value ? `${compact(value)} ROX` : "—";
}

function dateLabel(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(date);
}

function displayName(me: Me | null): string {
  if (!me) return "ROXY Creator";
  return [me.first_name, me.last_name].filter(Boolean).join(" ") || me.username || "ROXY Creator";
}

function initialRoute(): Route {
  if (typeof window === "undefined") return "home";
  const route = new URL(window.location.href).searchParams.get("route");
  return isRoute(route) ? route : "home";
}

function normalizeMediaFilter(value: string | null): "all" | "image" | "video" | "audio" {
  return value === "image" || value === "video" || value === "audio" ? value : "all";
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
  };
}

function isEmpty(value: unknown): boolean {
  return value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0);
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
  if (draft.billing_seconds) payload.billing_seconds = Number(draft.billing_seconds);
  return payload;
}

function validateDraft(model: GenerationModel, draft: Draft): string[] {
  const errors: string[] = [];
  for (const field of visibleFields(model, draft)) {
    const value = draft.values[field.name];
    if (field.required && isEmpty(value)) errors.push(`Заполните «${field.label}»`);
    if (field.control === "json" && !isEmpty(value)) {
      try { JSON.parse(String(value)); } catch { errors.push(`Исправьте JSON в «${field.label}»`); }
    }
  }
  const scenario = model.ui_schema?.scenario?.items?.find((item) => item.id === draft.scenario) as any;
  for (const name of scenario?.required_fields || []) {
    if (isEmpty(draft.values[name])) errors.push("Заполните обязательное поле");
  }
  const any = scenario?.required_any || [];
  if (any.length && !any.some((name: string) => !isEmpty(draft.values[name]))) errors.push("Добавьте хотя бы один референс");
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

export function RoxySocialApp() {
  const [booting, setBooting] = useState(true);
  const [route, setRoute] = useState<Route>("home");
  const [me, setMe] = useState<Me | null>(null);
  const [models, setModels] = useState<GenerationModel[]>([]);
  const [families, setFamilies] = useState<GenerationModelFamily[]>([]);
  const [recent, setRecent] = useState<Generation[]>([]);
  const [feed, setFeed] = useState<FeedCard[]>([]);
  const [history, setHistory] = useState<Generation[]>([]);
  const [historyBefore, setHistoryBefore] = useState<string | null>(null);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [profileWorks, setProfileWorks] = useState<Generation[]>([]);
  const [profilePublications, setProfilePublications] = useState<FeedCard[]>([]);
  const [profileTab, setProfileTab] = useState<"works" | "publications">("works");
  const [walletOpen, setWalletOpen] = useState(false);
  const [preview, setPreview] = useState<Generation | FeedCard | null>(null);
  const [previewSurface, setPreviewSurface] = useState<PreviewSurface>("private");
  const [toast, setToast] = useState("");
  const [onboarding, setOnboarding] = useState<Record<string, any> | null>(null);
  const toastTimer = useRef<number | null>(null);

  const showToast = useCallback((message: string) => {
    setToast(message);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 2600);
  }, []);

  const refreshMe = useCallback(async () => {
    const next = await api.me();
    setMe(next);
    return next;
  }, []);

  const loadFeed = useCallback(async () => {
    const payload = await api.feed("recent", 0);
    setFeed(payload.items || []);
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
      api.generations("limit=24&status=succeeded"),
      me ? api.profileFeed(String(me.telegram_id), 0) : Promise.resolve({ items: [] as FeedCard[] }),
    ]);
    setProfileWorks(works.items);
    setProfilePublications(publications.items);
  }, [me]);

  useEffect(() => {
    let active = true;
    const tg = initTelegram();
    const safe = () => syncSafeArea(tg);
    tg?.onEvent?.("safeAreaChanged", safe);
    tg?.onEvent?.("contentSafeAreaChanged", safe);
    tg?.onEvent?.("viewportChanged", safe);
    setRoute(initialRoute());

    (async () => {
      try {
        const [modelResult, meResult, recentResult, feedResult, onboardingResult] = await Promise.allSettled([
          api.models(),
          tg?.initData ? api.me() : Promise.resolve(null),
          tg?.initData ? api.generations("limit=12") : Promise.resolve({ items: [] }),
          tg?.initData ? api.feed("recent", 0) : Promise.resolve({ items: [] }),
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
  }, [route, history.length, loadHistory, loadProfile]);

  useEffect(() => {
    if (route !== "catalog") return;
    void loadFeed();
    const timer = window.setInterval(() => void loadFeed(), 15000);
    return () => window.clearInterval(timer);
  }, [loadFeed, route]);

  const navigate = useCallback((next: Route) => {
    setWalletOpen(false);
    setPreview(null);
    setRoute(next);
    const url = new URL(window.location.href);
    url.searchParams.set("route", next);
    window.history.pushState({ roxyRoute: next }, "", `${url.pathname}${url.search}${url.hash}`);
    haptic(next === "create" ? "medium" : "light");
    window.scrollTo({ top: 0, behavior: "auto" });
  }, []);

  const openCreate = useCallback((media?: "image" | "video" | "audio") => {
    if (media) localStorage.setItem(MEDIA_FILTER_KEY, media);
    navigate("create");
  }, [navigate]);

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
        <button className="brand" type="button" onClick={() => navigate("home")} aria-label="ROXY — главная">
          <RoxyMark />
          <span className="brand-copy"><strong>ROXY</strong><small>AI CREATIVE STUDIO</small></span>
        </button>
        <button className="balance-button" type="button" onClick={() => setWalletOpen(true)}>
          <span>Баланс</span><strong>{me ? `${compact(me.balance_rox)} ROX` : "—"}</strong>
        </button>
      </header>

      <main className="main-shell">
        {route === "home" && <HomeScreen models={models} recent={recent} onNavigate={navigate} onCreate={openCreate} onPreview={(item) => { setPreviewSurface("private"); setPreview(item); }} />}
        {route === "catalog" && <CatalogScreen models={models} families={families} feed={feed} onCreate={(model) => { localStorage.setItem(MODEL_KEY, model.id); navigate("create"); }} onPreview={(item) => { setPreviewSurface("feed"); setPreview(item); }} />}
        {route === "create" && <CreateScreen models={models} families={families} me={me} onBalance={refreshMe} onCreated={(item) => { setRecent((current) => [item, ...current.filter((x) => x.id !== item.id)].slice(0, 12)); setPreviewSurface("private"); setPreview(item); }} showToast={showToast} />}
        {route === "history" && <HistoryScreen items={history} hasMore={historyHasMore} onMore={() => historyBefore && void loadHistory(true, historyBefore)} onPreview={(item) => { setPreviewSurface("private"); setPreview(item); }} />}
        {route === "profile" && <ProfileScreen me={me} avatar={avatar} tab={profileTab} setTab={setProfileTab} works={profileWorks} publications={profilePublications} onPreview={(item, surface) => { setPreviewSurface(surface); setPreview(item); }} onWallet={() => setWalletOpen(true)} />}
      </main>

      <BottomNav route={route} onNavigate={navigate} />

      {walletOpen && <WalletSheet me={me} onClose={() => setWalletOpen(false)} onRefresh={refreshMe} showToast={showToast} />}
      {preview && <Preview item={preview} surface={previewSurface} onClose={() => setPreview(null)} onPublished={async (scope) => { await Promise.allSettled([loadProfile(), loadFeed(), loadHistory()]); showToast(scope === "feed" ? "Работа опубликована в ленте и профиле" : "Работа опубликована в профиле"); }} showToast={showToast} />}
      {onboarding?.enabled && !onboarding?.completed && <Onboarding data={onboarding} onDone={async () => { const next = await api.completeOnboarding(); setOnboarding(next); }} />}
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}

function Splash() {
  return <div className="splash" role="status" aria-label="ROXY загружается"><div className="splash-orbit"><span/><RoxyMark large /></div><strong>ROXY</strong><small>AI CREATIVE STUDIO</small><div className="splash-progress"><i /></div></div>;
}

function RoxyMark({ large = false }: { large?: boolean }) {
  return <span className={`roxy-mark${large ? " large" : ""}`} aria-hidden="true"><span>RX</span></span>;
}

function HomeScreen({ models, recent, onNavigate, onCreate, onPreview }: { models: GenerationModel[]; recent: Generation[]; onNavigate: (route: Route) => void; onCreate: (media: "image" | "video" | "audio") => void; onPreview: (item: Generation) => void }) {
  const counts = useMemo(() => ({ image: models.filter((m) => m.media_type === "image").length, video: models.filter((m) => m.media_type === "video").length, audio: models.filter((m) => m.media_type === "audio").length }), [models]);
  return <section className="screen home-screen"><SectionTitle kicker="Создание" title="Что создаём?" /><div className="format-grid"><FormatCard icon="image" title="Фото" count={counts.image} onClick={() => onCreate("image")} /><FormatCard icon="video" title="Видео" count={counts.video} onClick={() => onCreate("video")} /><FormatCard icon="music" title="Музыка" count={counts.audio} onClick={() => onCreate("audio")} /></div><SectionTitle kicker="Недавнее" title="Последние работы" action="Все" onAction={() => onNavigate("history")} /><MediaGrid items={recent.filter((item) => item.status === "succeeded").slice(0, 9)} empty="Готовые работы появятся здесь." onClick={onPreview} /></section>;
}

function FormatCard({ icon, title, count, onClick }: { icon: IconName; title: string; count: number; onClick: () => void }) {
  return <button className="format-card" type="button" onClick={onClick}><span className="format-icon"><Icon name={icon}/></span><strong>{title}</strong><small>{count ? `${count} моделей` : "Скоро"}</small><Icon name="chevron" className="format-chevron"/></button>;
}

function CatalogScreen({ models, families, feed, onCreate, onPreview }: { models: GenerationModel[]; families: GenerationModelFamily[]; feed: FeedCard[]; onCreate: (model: GenerationModel) => void; onPreview: (item: FeedCard) => void }) {
  const [media, setMedia] = useState<"all" | "image" | "video" | "audio">("all");
  const [familySheet, setFamilySheet] = useState<GenerationModelFamily | null>(null);
  const byId = useMemo(() => new Map(models.map((model) => [model.id, model])), [models]);
  const filtered = media === "all" ? families : families.filter((family) => family.media_types?.includes(media));
  return <section className="screen"><ScreenHead kicker="Каталог" title="Модели и лента" copy="Модели строятся из backend schema; лента обновляется автоматически." /><div className="segmented scrollable">{(["all", "image", "video", "audio"] as const).map((key) => <button key={key} type="button" className={media === key ? "active" : ""} onClick={() => setMedia(key)}>{key === "all" ? "Все" : key === "image" ? "Фото" : key === "video" ? "Видео" : "Музыка"}</button>)}</div><div className="model-grid">{filtered.map((family) => <button key={family.id} className="model-card" type="button" onClick={() => setFamilySheet(family)}><span className="model-icon"><Icon name={modelIcon(family.media_types?.[0])}/></span><div><strong>{family.title}</strong><small>{family.variant_count} вариантов</small></div><span className="price-pill">от {priceLabel(family.price_from_rox)}</span></button>)}</div><SectionTitle kicker="Сообщество" title="Свежие работы" /><MediaGrid items={feed} empty="Публикаций пока нет." onClick={onPreview} reactions />{familySheet && <FamilyVariantSheet family={familySheet} models={byId} selectedId="" onClose={() => setFamilySheet(null)} onChoose={(id) => { const model = byId.get(id); if (model) onCreate(model); setFamilySheet(null); }} />}</section>;
}

function CreateScreen({ models, families, me, onBalance, onCreated, showToast }: { models: GenerationModel[]; families: GenerationModelFamily[]; me: Me | null; onBalance: () => Promise<Me>; onCreated: (item: Generation) => void; showToast: (message: string) => void }) {
  const initialModelId = typeof window !== "undefined" ? localStorage.getItem(MODEL_KEY) : null;
  const initialMedia = typeof window !== "undefined" ? normalizeMediaFilter(localStorage.getItem(MEDIA_FILTER_KEY)) : "all";
  const [selectedId, setSelectedId] = useState(initialModelId || models[0]?.id || "");
  const [media, setMedia] = useState<"all" | "image" | "video" | "audio">(initialMedia);
  const selected = models.find((model) => model.id === selectedId) || models[0] || null;
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoteError, setQuoteError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [familySheet, setFamilySheet] = useState<GenerationModelFamily | null>(null);
  const quoteSeq = useRef(0);
  const byId = useMemo(() => new Map(models.map((model) => [model.id, model])), [models]);
  const visibleFamilies = useMemo(() => media === "all" ? families : families.filter((family) => family.media_types?.includes(media)), [families, media]);

  useEffect(() => { try { setDrafts(JSON.parse(localStorage.getItem(DRAFTS_KEY) || "{}")); } catch { setDrafts({}); } }, []);
  useEffect(() => { if (!selectedId && models[0]) setSelectedId(models[0].id); }, [models, selectedId]);
  useEffect(() => {
    if (!visibleFamilies.length || !models.length) return;
    const selectedIsVisible = visibleFamilies.some((family) => family.variants.some((variant) => variant.id === selectedId));
    if (selectedIsVisible) return;
    const next = visibleFamilies.flatMap((family) => family.variants).map((variant) => byId.get(variant.id)).find(Boolean);
    if (next) chooseModel(next.id);
  }, [byId, models.length, selectedId, visibleFamilies]);

  const draft = useMemo(() => {
    if (!selected) return null;
    const existing = drafts[selected.id];
    return existing ? { ...createDefaultDraft(selected), ...existing, values: { ...createDefaultDraft(selected).values, ...(existing.values || {}) } } : createDefaultDraft(selected);
  }, [drafts, selected]);

  const persist = useCallback((modelId: string, next: Draft) => {
    setDrafts((current) => { const all = { ...current, [modelId]: next }; localStorage.setItem(DRAFTS_KEY, JSON.stringify(all)); return all; });
  }, []);

  const updateValue = (name: string, value: unknown) => { if (selected && draft) persist(selected.id, { ...draft, values: { ...draft.values, [name]: value } }); };
  const errors = selected && draft ? validateDraft(selected, draft) : ["Выберите модель"];

  useEffect(() => {
    if (!selected || !draft || errors.length || uploading) { setQuote(null); return; }
    const seq = ++quoteSeq.current;
    const timer = window.setTimeout(async () => {
      try { const next = await api.quote(buildPayload(selected, draft)); if (quoteSeq.current === seq) { setQuote(next); setQuoteError(""); } }
      catch (error) { if (quoteSeq.current === seq) { setQuote(null); setQuoteError(error instanceof Error ? error.message : "Не удалось рассчитать цену"); } }
    }, 320);
    return () => window.clearTimeout(timer);
  }, [draft, selected, uploading, errors.join("|")]);

  const chooseModel = (id: string) => { setSelectedId(id); localStorage.setItem(MODEL_KEY, id); setQuote(null); haptic("light"); };
  const chooseMedia = (next: "all" | "image" | "video" | "audio") => { setMedia(next); localStorage.setItem(MEDIA_FILTER_KEY, next); };
  const setScenario = (id: string) => { if (!selected || !draft) return; const scenario = selected.ui_schema?.scenario?.items?.find((item) => item.id === id); const values = { ...draft.values }; for (const key of scenario?.clear_fields || []) delete values[key]; persist(selected.id, { ...draft, scenario: id, values }); };

  const submit = async () => {
    if (!selected || !draft || errors.length || !quote || submitting) return;
    if (!telegram()?.initData) { showToast("Откройте Mini App через Telegram-бота"); return; }
    setSubmitting(true);
    try {
      const created = await api.create(buildPayload(selected, draft));
      notify("success");
      showToast("Генерация запущена");
      await onBalance();
      let current: Generation = { id: created.id, status: created.status || "queued", model: selected, prompt: String(draft.values.prompt || "") };
      const started = Date.now();
      while (Date.now() - started < 10 * 60 * 1000) {
        current = await api.generation(created.id);
        if (!ACTIVE_STATUSES.has(current.status)) break;
        await new Promise((resolve) => window.setTimeout(resolve, 1800));
      }
      onCreated(current);
    } catch (error) { notify("error"); showToast(error instanceof Error ? error.message : "Не удалось запустить генерацию"); }
    finally { setSubmitting(false); }
  };

  if (!selected || !draft) return <section className="screen"><ScreenHead kicker="Создание" title="Каталог моделей загружается" /></section>;
  const fields = visibleFields(selected, draft);
  const groups = selected.ui_schema?.groups || [{ id: "main", title: "Настройки" }];

  return <section className="screen create-screen"><ScreenHead kicker="Создание" title="Настрой генерацию" copy="Один продукт сам выбирает text/reference режим по вашим файлам." /><div className="create-layout"><div className="create-controls"><div className="panel"><label className="label">Модель</label><div className="segmented scrollable family-tabs">{(["all", "image", "video", "audio"] as const).map((key) => <button key={key} type="button" className={media === key ? "active" : ""} onClick={() => chooseMedia(key)}>{key === "all" ? "Все" : key === "image" ? "Фото" : key === "video" ? "Видео" : "Музыка"}</button>)}</div><div className="family-grid">{visibleFamilies.map((family) => { const active = family.variants.some((variant) => variant.id === selected.id); return <button className={`family-card${active ? " active" : ""}`} type="button" key={family.id} onClick={() => setFamilySheet(family)}><span className="model-icon"><Icon name={modelIcon(family.media_types?.[0])}/></span><div><strong>{family.title}</strong><small>{family.variant_count} вариантов</small></div><span className="price-pill">от {priceLabel(family.price_from_rox)}</span></button>; })}</div><div className="chips"><span>{selected.media_type}</span><span>{selected.family}</span><span>{variantLabel(selected)}</span><span>{selected.operation.replaceAll("_", " ")}</span></div></div>{selected.ui_schema?.scenario?.items?.length ? <div className="panel"><label className="label">Режим</label><div className="segmented scrollable">{selected.ui_schema.scenario.items.map((item) => <button key={item.id} type="button" className={draft.scenario === item.id ? "active" : ""} onClick={() => setScenario(item.id)}>{item.title}</button>)}</div></div> : null}{groups.map((group) => { const grouped = fields.filter((field) => (field.group || "main") === group.id || (groups.length === 1 && !field.group)); if (!grouped.length) return null; return <div className="panel" key={group.id}><h2>{group.title}</h2><div className="form-stack">{grouped.map((field) => <DynamicField key={field.name} field={field} value={draft.values[field.name]} onChange={(value) => updateValue(field.name, value)} onUpload={async (files) => { setUploading(true); try { const max = field.control === "file" ? 1 : field.max_items || 20; const urls: string[] = field.control === "files" && Array.isArray(draft.values[field.name]) ? [...draft.values[field.name] as string[]] : []; for (const file of files.slice(0, Math.max(0, max - urls.length))) { if (field.max_size_mb && file.size > field.max_size_mb * 1024 * 1024) { showToast(`${file.name}: максимум ${field.max_size_mb} МБ`); continue; } const uploaded = await api.upload(file); if (field.control === "file") { updateValue(field.name, uploaded.url); break; } urls.push(uploaded.url); } if (field.control === "files") updateValue(field.name, urls); notify("success"); } catch (error) { notify("error"); showToast(error instanceof Error ? error.message : "Ошибка загрузки"); } finally { setUploading(false); } }} />)}</div></div>; })}{selected.ui_schema?.billing_seconds && <div className="panel"><label className="label">{selected.ui_schema.billing_seconds.label || "Длительность"}</label><input className="control" type="number" min={selected.ui_schema.billing_seconds.min || 1} max={selected.ui_schema.billing_seconds.max || 600} value={draft.billing_seconds ?? ""} onChange={(e) => persist(selected.id, { ...draft, billing_seconds: e.target.value ? Number(e.target.value) : null })}/></div>}</div><aside className="create-summary panel"><span className="kicker">Итог</span><h2>{selected.title}</h2><p className="muted">{me ? `Баланс: ${compact(me.balance_rox)} ROX` : "Откройте через Telegram для запуска"}</p><div className="quote-box"><span>Стоимость</span><strong>{quote ? `${compact(quote.cost_rox)} ROX` : "—"}</strong><small>{quote ? `≈ ${compact(quote.cost_rub)} ₽` : quoteError || errors[0] || "Считаю…"}</small></div><button className="primary wide" disabled={!quote || errors.length > 0 || uploading || submitting} type="button" onClick={() => void submit()}><Icon name="spark"/>{submitting ? "Генерирую…" : quote ? `Создать · ${compact(quote.cost_rox)} ROX` : "Создать"}</button></aside></div>{familySheet && <FamilyVariantSheet family={familySheet} models={byId} selectedId={selected.id} onClose={() => setFamilySheet(null)} onChoose={(id) => { chooseModel(id); setFamilySheet(null); }} />}</section>;
}

function FamilyVariantSheet({ family, models, selectedId, onClose, onChoose }: { family: GenerationModelFamily; models: Map<string, GenerationModel>; selectedId: string; onClose: () => void; onChoose: (id: string) => void }) {
  return <div className="sheet-backdrop" role="presentation" onClick={onClose}><section className="bottom-sheet" role="dialog" aria-modal="true" aria-label={family.title} onClick={(event) => event.stopPropagation()}><div className="sheet-head"><div><span className="kicker">Модель</span><h2>{family.title}</h2></div><button className="icon-button" type="button" onClick={onClose} aria-label="Закрыть"><Icon name="close"/></button></div><div className="variant-list">{family.variants.map((variant) => { const model = models.get(variant.id); const active = variant.id === selectedId; return <button key={variant.id} className={`variant-row${active ? " active" : ""}`} type="button" onClick={() => model && onChoose(model.id)} disabled={!model}><span className="variant-badge">{variant.badge || (variant.recommended ? "TOP" : variant.version || "AI")}</span><span><strong>{variant.version || variant.title}</strong><small>{variant.description || variant.title}</small></span><span className="price-pill">{priceLabel(variant.price_rox)}</span></button>; })}</div></section></div>;
}

function DynamicField({ field, value, onChange, onUpload }: { field: UiField; value: unknown; onChange: (value: unknown) => void; onUpload: (files: File[]) => Promise<void> }) {
  if (field.control === "toggle") return <label className="toggle-row"><span><strong>{field.label}</strong></span><input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)}/><i/></label>;
  if (field.control === "file" || field.control === "files") { const urls = field.control === "files" ? (Array.isArray(value) ? value as string[] : []) : value ? [String(value)] : []; return <div className="field"><label className="label">{field.label}{field.required ? " *" : ""}</label><label className="upload-control"><Icon name="upload"/><span>{urls.length ? `${urls.length} загружено` : "Выбрать файл"}</span><input type="file" multiple={field.control === "files"} accept={field.accept || "image/*,video/*,audio/*"} onChange={(e) => void onUpload(Array.from(e.target.files || []))}/></label>{urls.length > 0 && <div className="upload-list">{urls.map((url, i) => <button type="button" key={`${url}-${i}`} onClick={() => onChange(field.control === "files" ? urls.filter((_, index) => index !== i) : "")}>{new URL(url, window.location.href).pathname.split("/").pop() || `Файл ${i + 1}`} ×</button>)}</div>}</div>; }
  if (field.control === "textarea" || field.control === "json") return <label className="field"><span className="label">{field.label}{field.required ? " *" : ""}</span><textarea className="control textarea" placeholder={field.placeholder || ""} value={value == null ? "" : typeof value === "string" ? value : JSON.stringify(value, null, 2)} onChange={(e) => onChange(e.target.value)}/></label>;
  if (field.suggestions?.length) return <label className="field"><span className="label">{field.label}{field.required ? " *" : ""}</span><select className="control" value={value == null ? "" : String(value)} onChange={(e) => onChange(e.target.value)}><option value="">Выберите</option>{field.suggestions.map((item) => <option key={String(item)} value={String(item)}>{String(item)}</option>)}</select></label>;
  return <label className="field"><span className="label">{field.label}{field.required ? " *" : ""}</span><div className="input-with-suffix"><input className="control" type={field.control === "number" ? "number" : "text"} min={field.min} max={field.max} step={field.step} placeholder={field.placeholder || ""} value={value == null ? "" : String(value)} onChange={(e) => onChange(field.control === "number" ? (e.target.value ? Number(e.target.value) : null) : e.target.value)}/>{field.suffix && <span>{field.suffix}</span>}</div></label>;
}

function HistoryScreen({ items, hasMore, onMore, onPreview }: { items: Generation[]; hasMore: boolean; onMore: () => void; onPreview: (item: Generation) => void }) {
  return <section className="screen"><ScreenHead kicker="История" title="Все генерации" copy="Готовые результаты, активные задачи и ошибки — в одном месте."/><div className="history-list">{items.length ? items.map((item) => <button className="history-card" type="button" key={item.id} onClick={() => onPreview(item)}><MediaThumb item={item}/><div><strong>{modelOf(item)?.title || "AI генерация"}</strong><small>{dateLabel(item.created_at)} · {item.status}</small>{item.error && <p>{item.error}</p>}</div><span className={`status ${item.status}`}>{item.status}</span></button>) : <Empty text="История пока пуста."/>}</div>{hasMore && <button className="secondary wide" type="button" onClick={onMore}>Показать ещё</button>}</section>;
}

function ProfileScreen({ me, avatar, tab, setTab, works, publications, onPreview, onWallet }: { me: Me | null; avatar: string; tab: "works" | "publications"; setTab: (tab: "works" | "publications") => void; works: Generation[]; publications: FeedCard[]; onPreview: (item: Generation | FeedCard, surface: PreviewSurface) => void; onWallet: () => void }) {
  const likes = publications.reduce((sum, item) => sum + Number(item.likes_count || 0), 0);
  return <section className="screen profile-screen"><div className="profile-hero panel"><div className="avatar">{avatar ? <img src={avatar} alt=""/> : <span>{(me?.first_name?.[0] || me?.username?.[0] || "R").toUpperCase()}</span>}</div><div className="profile-copy"><span className="kicker">Профиль</span><h1>{displayName(me)}</h1><p>{me?.username ? `@${me.username}` : "ROXY creator"}</p></div><button className="icon-button" type="button" onClick={onWallet} aria-label="Баланс"><Icon name="wallet"/></button><div className="profile-stats"><div><strong>{works.length}</strong><span>работ</span></div><div><strong>{publications.length}</strong><span>публикаций</span></div><div><strong>{compact(likes)}</strong><span>лайков</span></div></div></div><div className="profile-tabs"><button type="button" className={tab === "works" ? "active" : ""} onClick={() => setTab("works")}>Работы</button><button type="button" className={tab === "publications" ? "active" : ""} onClick={() => setTab("publications")}>Публикации</button></div>{tab === "works" ? <MediaGrid items={works} empty="Готовых работ пока нет." onClick={(item) => onPreview(item, "private")}/> : <MediaGrid items={publications} empty="Публикаций пока нет." onClick={(item) => onPreview(item, "profile")} reactions/>}</section>;
}

function MediaGrid<T extends Generation | FeedCard>({ items, empty, onClick, reactions = false }: { items: T[]; empty: string; onClick: (item: T) => void; reactions?: boolean }) {
  if (!items.length) return <Empty text={empty}/>;
  return <div className="media-grid">{items.map((item) => <button className="media-tile" type="button" key={item.id} onClick={() => onClick(item)}><MediaThumb item={item}/>{reactions && <span className="tile-reactions"><Icon name="heart" size={13}/>{compact((item as FeedCard).likes_count)} <Icon name="comment" size={13}/>{compact((item as FeedCard).comments_count)}</span>}</button>)}</div>;
}

function MediaThumb({ item }: { item: Generation | FeedCard }) {
  const url = mediaUrl(item);
  const type = mediaType(item);
  if (!url) return <span className="media-placeholder"><Icon name={type === "video" ? "video" : type === "audio" ? "music" : "image"}/><small>{item.status || "Нет превью"}</small></span>;
  if (type === "video") return <video src={url} muted playsInline preload="metadata"/>;
  if (type === "audio") return <span className="media-placeholder audio"><Icon name="music"/><small>Аудио</small></span>;
  return <img src={url} alt="" loading="lazy"/>;
}

function Preview({ item, surface, onClose, onPublished, showToast }: { item: Generation | FeedCard; surface: PreviewSurface; onClose: () => void; onPublished: (scope: "profile" | "feed", item: FeedCard) => Promise<void>; showToast: (message: string) => void }) {
  const [current, setCurrent] = useState<Generation | FeedCard>(item);
  const [publishing, setPublishing] = useState<"profile" | "feed" | null>(null);
  const [busy, setBusy] = useState<"like" | "share" | "comments" | "comment" | "remix" | "remove" | null>(null);
  const [promptVisible, setPromptVisible] = useState(false);
  const [referencesVisible, setReferencesVisible] = useState(false);
  const [commentsOpen, setCommentsOpen] = useState(false);
  const [comments, setComments] = useState<FeedComment[]>([]);
  const [commentText, setCommentText] = useState("");

  useEffect(() => setCurrent(item), [item]);

  const card = current as FeedCard;
  const url = mediaUrl(current);
  const type = mediaType(current);
  const feedSurface: FeedSurface = surface === "profile" ? "profile" : "feed";
  const canPublish = surface === "private" && current.status === "succeeded";
  const canSocial = surface !== "private";
  const isMine = Boolean(card.is_mine);
  const publicReferences = [
    ...(card.reference_images || []).map((value) => ({ type: "image" as const, value })),
    ...(card.reference_videos || []).map((value) => ({ type: "video" as const, value })),
  ];

  const patchCard = (patch: Partial<FeedCard>) => setCurrent((prev) => ({ ...(prev as FeedCard), ...patch }));

  const publish = async (scope: "profile" | "feed") => {
    setPublishing(scope);
    try {
      const result = await api.publish(current.id, { scope, promptVisible, referencesVisible });
      patchCard(result.item);
      notify("success");
      await onPublished(result.publication_scope === "feed" ? "feed" : "profile", result.item);
      if (result.downgraded_to_profile) showToast("18+ работа опубликована только в профиле");
    } catch (error) { notify("error"); showToast(error instanceof Error ? error.message : "Не удалось опубликовать"); }
    finally { setPublishing(null); }
  };

  const toggleLike = async () => {
    if (!canSocial || busy) return;
    setBusy("like");
    try {
      const result = card.liked_by_me ? await api.unlike(current.id, feedSurface) : await api.like(current.id, feedSurface);
      patchCard({ liked_by_me: result.liked_by_me, likes_count: result.likes_count });
      haptic("light");
    } catch (error) { showToast(error instanceof Error ? error.message : "Не удалось обновить лайк"); }
    finally { setBusy(null); }
  };

  const share = async () => {
    if (!canSocial || busy) return;
    setBusy("share");
    try {
      const result = await api.share(current.id, feedSurface);
      patchCard({ shares_count: result.shares_count });
      if (await copyText(result.link)) showToast("Ссылка скопирована");
      else showToast("Ссылка создана");
    } catch (error) { showToast(error instanceof Error ? error.message : "Не удалось создать ссылку"); }
    finally { setBusy(null); }
  };

  const loadComments = async () => {
    if (!canSocial) return;
    setCommentsOpen(true);
    setBusy("comments");
    try {
      const payload = await api.comments(current.id, feedSurface);
      setComments(payload.items || []);
    } catch (error) { showToast(error instanceof Error ? error.message : "Не удалось загрузить комментарии"); }
    finally { setBusy(null); }
  };

  const addComment = async () => {
    const text = commentText.trim();
    if (!text || busy) return;
    setBusy("comment");
    try {
      const comment = await api.addComment(current.id, feedSurface, text);
      setComments((items) => [comment, ...items]);
      setCommentText("");
      patchCard({ comments_count: Number(card.comments_count || 0) + 1 });
    } catch (error) { showToast(error instanceof Error ? error.message : "Не удалось отправить комментарий"); }
    finally { setBusy(null); }
  };

  const remix = async () => {
    if (!canSocial || busy) return;
    setBusy("remix");
    try {
      await api.remix(current.id, feedSurface);
      notify("success");
      showToast("Повтор запущен. Результат появится в истории.");
    } catch (error) { notify("error"); showToast(error instanceof Error ? error.message : "Не удалось повторить"); }
    finally { setBusy(null); }
  };

  const removePublication = async () => {
    if (!isMine || busy) return;
    setBusy("remove");
    try {
      const target = card.publication_scope === "feed" ? "profile" : "private";
      await api.removePublication(current.id, target);
      notify("success");
      showToast(target === "profile" ? "Убрано из ленты, осталось в профиле" : "Публикация скрыта");
      onClose();
    } catch (error) { notify("error"); showToast(error instanceof Error ? error.message : "Не удалось убрать публикацию"); }
    finally { setBusy(null); }
  };

  return <div className="overlay" role="dialog" aria-modal="true"><button className="overlay-backdrop" type="button" onClick={onClose} aria-label="Закрыть"/><div className="preview-card"><button className="preview-close" type="button" onClick={onClose} aria-label="Закрыть"><Icon name="close"/></button><div className="preview-media">{url && type === "video" ? <video src={url} controls playsInline autoPlay={false}/> : url && type === "audio" ? <audio src={url} controls/> : url ? <img src={url} alt="Результат"/> : <span className="media-placeholder"><Icon name="image"/></span>}</div><div className="preview-copy"><span className="kicker">{surface === "private" ? "Моя работа" : surface === "profile" ? "Профиль" : "Лента"}</span><h2>{modelOf(current)?.title || card.model || "ROXY generation"}</h2><p className="muted">{dateLabel(current.created_at || card.feed_published_at)}</p>{current.prompt && !current.prompt_hidden && <p className="prompt-copy">{current.prompt}</p>}{publicReferences.length > 0 && <div className="upload-list">{publicReferences.map((ref, index) => <a key={`${ref.value}-${index}`} href={ref.value} target="_blank" rel="noreferrer">{ref.type === "video" ? "Видео" : "Фото"} ref {index + 1}</a>)}</div>}{canPublish && <div className="panel" style={{ padding: 12 }}><label className="toggle-row"><span><strong>Показать промпт</strong><small>Только если это не remix/trend</small></span><input type="checkbox" checked={promptVisible} onChange={(e) => setPromptVisible(e.target.checked)}/><i/></label><label className="toggle-row"><span><strong>Показать референсы</strong><small>Откроет исходники в карточке</small></span><input type="checkbox" checked={referencesVisible} onChange={(e) => setReferencesVisible(e.target.checked)}/><i/></label></div>}<div className="preview-actions">{url && <a className="primary" href={url} target="_blank" rel="noreferrer">Открыть результат</a>}{canPublish && <button className="secondary" type="button" disabled={Boolean(publishing)} onClick={() => void publish("profile")}>{publishing === "profile" ? "Публикую…" : "В профиль"}</button>}{canPublish && <button className="primary" type="button" disabled={Boolean(publishing)} onClick={() => void publish("feed")}>{publishing === "feed" ? "Публикую…" : "В ленту + профиль"}</button>}{canSocial && <button className="secondary" type="button" disabled={busy === "like"} onClick={() => void toggleLike()}><Icon name="heart" size={16}/>{card.liked_by_me ? "Лайк есть" : "Лайк"} · {compact(card.likes_count)}</button>}{canSocial && <button className="secondary" type="button" disabled={busy === "share"} onClick={() => void share()}><Icon name="share" size={16}/>Поделиться · {compact(card.shares_count)}</button>}{canSocial && <button className="secondary" type="button" disabled={busy === "comments"} onClick={() => void loadComments()}><Icon name="comment" size={16}/>Комментарии · {compact(card.comments_count)}</button>}{canSocial && card.prompt_actions_allowed !== false && <button className="secondary" type="button" disabled={busy === "remix"} onClick={() => void remix()}><Icon name="create" size={16}/>Повторить</button>}{canSocial && isMine && <button className="secondary" type="button" disabled={busy === "remove"} onClick={() => void removePublication()}>Убрать</button>}</div>{commentsOpen && <div className="panel" style={{ padding: 12 }}><div className="section-title"><div><span className="kicker">Social</span><h2>Комментарии</h2></div><button type="button" onClick={() => setCommentsOpen(false)}>Закрыть</button></div><div className="form-stack"><textarea className="control textarea" maxLength={300} placeholder="Ваш комментарий" value={commentText} onChange={(event) => setCommentText(event.target.value)}/><button className="primary wide" type="button" disabled={!commentText.trim() || busy === "comment"} onClick={() => void addComment()}>{busy === "comment" ? "Отправляю…" : "Отправить"}</button></div><div className="transaction-list">{comments.length ? comments.map((comment) => <div className="transaction" key={comment.id}><div><strong>{comment.author?.display_name || comment.author?.username || "Пользователь"}</strong><small>{dateLabel(comment.created_at)}</small></div><span>{comment.text}</span></div>) : <Empty text="Пока пусто."/>}</div></div>}</div></div></div>;
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
  return <div className="overlay sheet-overlay" role="dialog" aria-modal="true"><button className="overlay-backdrop" type="button" onClick={onClose}/><section className="sheet"><div className="sheet-handle"/><header><div><span className="kicker">Wallet</span><h2>{me ? `${compact(me.balance_rox)} ROX` : "Баланс"}</h2></div><button className="icon-button" type="button" onClick={onClose}><Icon name="close"/></button></header><SectionTitle kicker="Пополнение" title="Выберите пакет"/><div className="package-grid">{Object.entries(packages).map(([id, pack]) => <button type="button" key={id} className={selected === id ? "package active" : "package"} onClick={() => setSelected(id)}><strong>{compact(pack.credits)} ROX</strong><small>{compact(pack.prices[currency] || 0)} {currency}</small></button>)}</div><div className="segmented scrollable">{(["RUB", "USD", "EUR"] as const).filter((item) => Object.values(packages).some((pack) => pack.prices[item])).map((item) => <button type="button" key={item} className={currency === item ? "active" : ""} onClick={() => setCurrency(item)}>{item}</button>)}</div><input className="wallet-input" type="email" inputMode="email" autoComplete="email" placeholder="Email для чека" value={email} onChange={(event) => setEmail(event.target.value)} /><button className="primary wide" type="button" disabled={!selected || !email.trim() || paying} onClick={() => void pay()}>{paying ? "Создаю платёж…" : "Перейти к оплате"}</button><SectionTitle kicker="Операции" title="Последние движения"/><div className="transaction-list">{transactions.slice(0, 12).map((tx) => <div className="transaction" key={tx.id}><div><strong>{tx.kind}</strong><small>{dateLabel(tx.created_at)}</small></div><span className={Number(tx.amount) >= 0 ? "positive" : "negative"}>{Number(tx.amount) >= 0 ? "+" : ""}{compact(tx.amount)} ROX</span></div>)}</div></section></div>;
}

function Onboarding({ data, onDone }: { data: Record<string, any>; onDone: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  return <div className="overlay onboarding-overlay" role="dialog" aria-modal="true"><div className="onboarding-card"><RoxyMark large/><span className="kicker">Добро пожаловать</span><h1>{data.title || "ROXY"}</h1><p>{data.body || "AI Creative Studio для генерации фото, видео и музыки."}</p><div className="onboarding-links">{data.rules_url && <a href={data.rules_url} target="_blank" rel="noreferrer">Правила</a>}{data.privacy_url && <a href={data.privacy_url} target="_blank" rel="noreferrer">Конфиденциальность</a>}</div><button className="primary wide" type="button" disabled={busy} onClick={async () => { setBusy(true); try { await onDone(); } finally { setBusy(false); } }}>{busy ? "Открываю…" : "Открыть ROXY"}</button></div></div>;
}

function BottomNav({ route, onNavigate }: { route: Route; onNavigate: (route: Route) => void }) {
  const menu: Array<[Route, IconName, string]> = [["home", "home", "Главная"], ["catalog", "catalog", "Каталог"], ["create", "create", "Создать"], ["history", "history", "История"], ["profile", "profile", "Профиль"]];
  return <nav className="bottom-nav" aria-label="Основная навигация">{menu.map(([key, icon, label]) => <button type="button" key={key} className={`${route === key ? "active " : ""}${key === "create" ? "central" : ""}`} onClick={() => onNavigate(key)} aria-current={route === key ? "page" : undefined}><span><Icon name={icon}/></span><small>{label}</small></button>)}</nav>;
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
