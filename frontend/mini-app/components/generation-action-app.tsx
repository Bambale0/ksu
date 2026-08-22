"use client";

import { useEffect, useMemo, useState } from "react";
import { SavedReferencePicker } from "@/lib/reference-memory";
import { haptic, initTelegram, notify, telegram, telegramHeaders } from "@/lib/telegram";
import type { UiField, UiSchema } from "@/lib/types";
import { Icon } from "./icons";
import { RoxySocialApp } from "./roxy-social-app";

type ActionRoute = { generationId: string; action: string };
type ActionModel = {
  id: string;
  title: string;
  family?: string;
  media_type?: string;
  operation?: string;
  ui_schema?: UiSchema;
};
type ActionContext = {
  generation: {
    id: string;
    status: string;
    media_type: string;
    result_url?: string | null;
    model_id?: string;
    model_title?: string;
    prompt?: string;
    prompt_hidden?: boolean;
    publication_scope?: string;
  };
  action: { id: string; label: string; derivative: boolean };
  candidate_models: ActionModel[];
  defaults: {
    model_id?: string | null;
    prompt?: string;
    parameters?: Record<string, unknown>;
    billing_seconds?: number | null;
    input_url?: string | null;
  };
  source_url?: string | null;
  source_references?: { images?: string[]; videos?: string[] };
  edit_presets?: Array<{ id: string; label: string }>;
};
type Quote = { cost_rox?: string; cost_rub?: string; effective_cost_rox?: string };

const SOURCE_ACTIONS = new Set(["remix", "edit", "animate"]);
const REFERENCE_FIELDS = new Set([
  "image_urls", "input_urls", "image_input", "image_url", "first_frame_url", "last_frame_url",
  "first_frame", "reference_image", "reference_image_urls", "video_urls", "video_url",
  "first_clip_url", "reference_video", "reference_video_urls",
]);

function parseActionRoute(): ActionRoute | null {
  if (typeof window === "undefined") return null;
  const url = new URL(window.location.href);
  if (url.searchParams.get("route") !== "generation-action") return null;
  const generationId = url.searchParams.get("generation") || "";
  const action = url.searchParams.get("action") || "";
  return generationId && action ? { generationId, action } : null;
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
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail ?? payload?.message ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload as T;
}

function resultMediaType(context: ActionContext): string {
  const type = context.generation.media_type;
  if (type) return type;
  const url = context.source_url || "";
  if (/\.(mp4|mov|webm)(\?|$)/i.test(url)) return "video";
  if (/\.(mp3|wav|m4a|aac|ogg)(\?|$)/i.test(url)) return "audio";
  return "image";
}

function sourceScenario(schema: UiSchema | undefined, action: string, values: Record<string, unknown>): string | null {
  const items = schema?.scenario?.items || [];
  if (!items.length) return null;
  if (SOURCE_ACTIONS.has(action)) {
    const withReference = items.find((item) => (item.visible_fields || []).some((name) => REFERENCE_FIELDS.has(name)));
    if (withReference) return withReference.id;
  }
  const withExisting = items.find((item) => (item.visible_fields || []).some((name) => {
    const value = values[name];
    return Array.isArray(value) ? value.length > 0 : value !== undefined && value !== null && value !== "";
  }));
  return withExisting?.id || schema?.scenario?.default || items[0]?.id || null;
}

function visibleFields(model: ActionModel | null, action: string, values: Record<string, unknown>): UiField[] {
  const fields = model?.ui_schema?.fields || [];
  const items = model?.ui_schema?.scenario?.items || [];
  const scenarioId = sourceScenario(model?.ui_schema, action, values);
  const scenario = items.find((item) => item.id === scenarioId);
  const controlled = new Set<string>();
  for (const item of items) {
    for (const name of item.visible_fields || []) controlled.add(name);
    for (const name of item.clear_fields || []) controlled.add(name);
  }
  return fields.filter((field) => {
    if (field.name === "prompt") return false;
    if (SOURCE_ACTIONS.has(action) && REFERENCE_FIELDS.has(field.name)) return false;
    if (!scenario || !controlled.has(field.name)) return true;
    return Boolean(scenario.visible_fields?.includes(field.name));
  });
}

function defaultPromptLabel(action: string): { title: string; placeholder: string; copy: string } {
  if (action === "remix") return { title: "Что изменить?", placeholder: "Например: сделай вечерний свет и красное платье", copy: "Исходное изображение уже закреплено как референс." };
  if (action === "edit") return { title: "Как изменить образ?", placeholder: "Опиши только нужное изменение", copy: "ROXY сохранит лицо, позу, композицию и остальные детали максимально неизменными." };
  if (action === "animate") return { title: "Как оживить кадр?", placeholder: "Например: плавный поворот головы, лёгкое движение камеры", copy: "Картинка автоматически станет первым кадром video I2V." };
  if (action === "new_prompt") return { title: "Новый промпт", placeholder: "Опиши новый результат", copy: "Модель и совместимые параметры сохранены, текст начинается с чистого поля." };
  if (action === "parameters") return { title: "Промпт", placeholder: "Промпт", copy: "Промпт сохранён. Измени нужные параметры ниже и запусти новый вариант." };
  return { title: "Промпт", placeholder: "Промпт", copy: "Промпт и совместимые настройки перенесены из выбранной работы." };
}

function money(value?: string | null): string {
  if (!value) return "—";
  const parsed = Number(value);
  return Number.isFinite(parsed) ? new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(parsed) : value;
}

function buildQuoteBody(
  context: ActionContext,
  action: string,
  model: ActionModel,
  prompt: string,
  parameters: Record<string, unknown>,
  billingSeconds: number | null,
): Record<string, unknown> {
  const body: Record<string, unknown> = { model_id: model.id, prompt, parameters };
  const inputUrl = SOURCE_ACTIONS.has(action) ? context.source_url : context.defaults.input_url;
  if (inputUrl) body.input_url = inputUrl;
  if (billingSeconds) body.billing_seconds = billingSeconds;
  return body;
}

export function GenerationActionGate() {
  const [ready, setReady] = useState(false);
  const [route, setRoute] = useState<ActionRoute | null>(null);

  useEffect(() => {
    const sync = () => { setRoute(parseActionRoute()); setReady(true); };
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  if (!ready) return <div className="splash" role="status"><strong>ROXY</strong><small>Загружаю действие…</small></div>;
  if (!route) return <RoxySocialApp />;
  return <GenerationActionApp generationId={route.generationId} action={route.action} />;
}

function GenerationActionApp({ generationId, action }: { generationId: string; action: string }) {
  const [context, setContext] = useState<ActionContext | null>(null);
  const [modelId, setModelId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [parameters, setParameters] = useState<Record<string, unknown>>({});
  const [billingSeconds, setBillingSeconds] = useState<number | null>(null);
  const [editKind, setEditKind] = useState("clothes");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoteError, setQuoteError] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [promptVisible, setPromptVisible] = useState(false);
  const [scope, setScope] = useState<"profile" | "feed">("feed");

  useEffect(() => {
    const tg = initTelegram();
    tg?.ready?.();
    tg?.expand?.();
    const goBack = () => goToGeneration(generationId);
    tg?.BackButton?.show?.();
    tg?.BackButton?.onClick?.(goBack);
    return () => tg?.BackButton?.offClick?.(goBack);
  }, [generationId]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    request<ActionContext>(`/api/v1/generations/${encodeURIComponent(generationId)}/action-context?action=${encodeURIComponent(action)}`)
      .then((next) => {
        if (!active) return;
        setContext(next);
        setModelId(String(next.defaults.model_id || next.candidate_models[0]?.id || ""));
        setPrompt(String(next.defaults.prompt || ""));
        setParameters({ ...(next.defaults.parameters || {}) });
        setBillingSeconds(next.defaults.billing_seconds ?? null);
        if (next.edit_presets?.length) setEditKind(next.edit_presets[0].id);
        setError("");
      })
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "Не удалось открыть действие"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [action, generationId]);

  const model = useMemo(() => context?.candidate_models.find((item) => item.id === modelId) || null, [context, modelId]);
  const fields = useMemo(() => visibleFields(model, action, parameters), [action, model, parameters]);
  const promptMeta = defaultPromptLabel(action);

  const formError = useMemo(() => {
    if (!context || action === "publish") return "";
    if (!model) return "Выберите модель";
    if ((SOURCE_ACTIONS.has(action) || action === "new_prompt") && !prompt.trim()) return "Добавьте промпт";
    for (const field of fields) {
      const value = parameters[field.name];
      const empty = value === undefined || value === null || value === "" || (Array.isArray(value) && !value.length);
      if (field.required && empty) return `Заполните «${field.label}»`;
    }
    return "";
  }, [action, context, fields, model, parameters, prompt]);

  useEffect(() => {
    if (!context || !model || action === "publish" || formError || uploading) {
      setQuote(null);
      return;
    }
    const timer = window.setTimeout(() => {
      let serialized: Record<string, unknown>;
      try { serialized = serializeParameters(fields, parameters); }
      catch (reason) { setQuote(null); setQuoteError(reason instanceof Error ? reason.message : "Проверьте параметры"); return; }
      void request<Quote>("/api/v1/generations/quote", {
        method: "POST",
        body: JSON.stringify(buildQuoteBody(context, action, model, prompt, serialized, billingSeconds)),
      }).then((next) => { setQuote(next); setQuoteError(""); })
        .catch((reason) => { setQuote(null); setQuoteError(reason instanceof Error ? reason.message : "Не удалось рассчитать цену"); });
    }, 280);
    return () => window.clearTimeout(timer);
  }, [action, billingSeconds, context, fields, formError, model, parameters, prompt, uploading]);

  const chooseModel = (nextId: string) => {
    if (!context) return;
    const next = context.candidate_models.find((item) => item.id === nextId);
    if (!next) return;
    const allowed = new Set((next.ui_schema?.fields || []).map((field) => field.name));
    const retained = Object.fromEntries(Object.entries(parameters).filter(([key]) => allowed.has(key)));
    setParameters({ ...(next.ui_schema?.defaults || {}), ...retained });
    setModelId(nextId);
    setBillingSeconds(null);
    setQuote(null);
    haptic("light");
  };

  const changeParameter = (name: string, value: unknown) => setParameters((current) => ({ ...current, [name]: value }));

  const uploadFiles = async (field: UiField, files: File[]) => {
    setUploading(true);
    try {
      const current = field.control === "files" && Array.isArray(parameters[field.name]) ? [...parameters[field.name] as string[]] : [];
      const max = field.control === "file" ? 1 : field.max_items || 20;
      for (const file of files.slice(0, Math.max(0, max - current.length))) {
        if (field.max_size_mb && file.size > field.max_size_mb * 1024 * 1024) throw new Error(`${file.name}: максимум ${field.max_size_mb} МБ`);
        const form = new FormData();
        form.append("file", file, file.name);
        const uploaded = await request<{ url: string }>("/api/v1/uploads/kie", { method: "POST", body: form });
        if (field.control === "file") { changeParameter(field.name, uploaded.url); break; }
        current.push(uploaded.url);
      }
      if (field.control === "files") changeParameter(field.name, current);
      notify("success");
    } catch (reason) {
      notify("error");
      setError(reason instanceof Error ? reason.message : "Ошибка загрузки");
    } finally { setUploading(false); }
  };

  const submitDerivative = async () => {
    if (!context || !model || formError || !quote || submitting) return;
    if (!telegram()?.initData) { setError("Откройте ROXY через Telegram-бота"); return; }
    setSubmitting(true);
    setError("");
    try {
      const serialized = serializeParameters(fields, parameters);
      const result = await request<{ id: string; status: string }>(`/api/v1/generations/${encodeURIComponent(generationId)}/actions/${encodeURIComponent(action)}`, {
        method: "POST",
        body: JSON.stringify({
          model_id: model.id,
          prompt,
          parameters: serialized,
          billing_seconds: billingSeconds,
          edit_kind: action === "edit" ? editKind : null,
        }),
      });
      notify("success");
      haptic("medium");
      goToGeneration(result.id);
    } catch (reason) {
      notify("error");
      setError(reason instanceof Error ? reason.message : "Не удалось запустить генерацию");
    } finally { setSubmitting(false); }
  };

  const publish = async () => {
    if (!context || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      await request(`/api/v1/feed/${encodeURIComponent(generationId)}/publish`, {
        method: "POST",
        body: JSON.stringify({ publication_scope: scope, prompt_visible: promptVisible, references_visible: false }),
      });
      notify("success");
      goToGeneration(generationId);
    } catch (reason) {
      notify("error");
      setError(reason instanceof Error ? reason.message : "Не удалось опубликовать");
    } finally { setSubmitting(false); }
  };

  if (loading) return <div className="splash" role="status"><strong>ROXY</strong><small>Готовлю действие…</small></div>;
  if (!context) return <ActionError error={error || "Действие недоступно"} generationId={generationId} />;

  const mediaType = resultMediaType(context);
  const source = context.source_url;

  return <div className="roxy-app generation-action-app">
    <header className="topbar action-topbar">
      <button className="brand" type="button" onClick={() => goToGeneration(generationId)} aria-label="Вернуться к работе"><span className="action-back">‹</span><span className="brand-copy"><strong>ROXY</strong><small>{context.action.label}</small></span></button>
      <button className="balance-button" type="button" onClick={() => goToGeneration(generationId)}><span>Исходник</span><strong>Открыть</strong></button>
    </header>
    <main className="main-shell"><section className="screen generation-action-screen">
      <div className="action-source panel">
        <div className="action-source-media">{source && mediaType === "video" ? <video src={source} controls playsInline /> : source && mediaType === "audio" ? <audio src={source} controls /> : source ? <img src={source} alt="Исходная генерация" /> : <span><Icon name="image"/></span>}</div>
        <div><span className="kicker">Исходная работа</span><h1>{context.generation.model_title || "ROXY generation"}</h1><p className="muted">{context.action.label} · связь с исходником сохранится в истории</p></div>
      </div>

      {action === "publish" ? <div className="action-grid">
        <div className="panel"><span className="kicker">Публикация</span><h2>Куда опубликовать?</h2><div className="segmented"><button type="button" className={scope === "profile" ? "active" : ""} onClick={() => setScope("profile")}>В профиль</button><button type="button" className={scope === "feed" ? "active" : ""} onClick={() => setScope("feed")}>Лента + профиль</button></div><label className="toggle-row"><span><strong>Показать промпт</strong><small>По умолчанию промпт скрыт</small></span><input type="checkbox" checked={promptVisible} onChange={(event) => setPromptVisible(event.target.checked)}/><i/></label><p className="muted">Референсы остаются скрытыми.</p></div>
        <aside className="panel create-summary"><span className="kicker">Готово</span><h2>{scope === "feed" ? "Публичная лента" : "Профиль"}</h2><button className="primary wide" type="button" disabled={submitting} onClick={() => void publish()}>{submitting ? "Публикую…" : "Опубликовать"}</button></aside>
      </div> : <div className="action-grid">
        <div className="action-form">
          {context.candidate_models.length > 1 && <div className="panel"><label className="label">Модель</label><select className="control" value={modelId} onChange={(event) => chooseModel(event.target.value)}>{context.candidate_models.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></div>}
          <div className="panel"><span className="kicker">{context.action.label}</span><h2>{promptMeta.title}</h2><p className="muted">{promptMeta.copy}</p>{action === "edit" && Boolean(context.edit_presets?.length) && <div className="segmented scrollable action-presets">{context.edit_presets?.map((preset) => <button type="button" key={preset.id} className={editKind === preset.id ? "active" : ""} onClick={() => setEditKind(preset.id)}>{preset.label}</button>)}</div>}<textarea className="control textarea action-prompt" value={prompt} placeholder={promptMeta.placeholder} onChange={(event) => setPrompt(event.target.value)} /></div>

          {fields.length > 0 && <div className="panel"><span className="kicker">Настройки</span><h2>{action === "parameters" ? "Изменить параметры" : "Параметры модели"}</h2><div className="form-stack">{fields.map((field) => <ActionField key={field.name} field={field} value={parameters[field.name]} onChange={(value) => changeParameter(field.name, value)} onUpload={(files) => uploadFiles(field, files)} />)}</div></div>}
          {model?.ui_schema?.billing_seconds && <div className="panel"><label className="label">{model.ui_schema.billing_seconds.label || "Длительность"}</label><input className="control" type="number" min={model.ui_schema.billing_seconds.min || 1} max={model.ui_schema.billing_seconds.max || 600} value={billingSeconds ?? ""} onChange={(event) => setBillingSeconds(event.target.value ? Number(event.target.value) : null)} /></div>}
        </div>
        <aside className="panel create-summary action-summary"><span className="kicker">Новая версия</span><h2>{model?.title || "Выберите модель"}</h2><div className="quote-box"><span>Стоимость</span><strong>{quote ? `${money(quote.effective_cost_rox || quote.cost_rox)} ROX` : "—"}</strong><small>{quote ? `≈ ${money(quote.cost_rub)} ₽` : quoteError || formError || "Считаю…"}</small></div><button className="primary wide" type="button" disabled={!quote || Boolean(formError) || uploading || submitting} onClick={() => void submitDerivative()}><Icon name="spark"/>{submitting ? "Запускаю…" : context.action.label}</button><button className="secondary wide" type="button" onClick={() => goToGeneration(generationId)}>Отмена</button></aside>
      </div>}
      {error && <div className="action-error" role="alert">{error}</div>}
    </section></main>
  </div>;
}

function ActionField({ field, value, onChange, onUpload }: { field: UiField; value: unknown; onChange: (value: unknown) => void; onUpload: (files: File[]) => Promise<void> }) {
  if (field.control === "toggle") return <label className="toggle-row"><span><strong>{field.label}</strong></span><input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)}/><i/></label>;
  if (field.control === "file" || field.control === "files") {
    const urls = field.control === "files" ? (Array.isArray(value) ? value as string[] : []) : value ? [String(value)] : [];
    return <div className="field"><label className="label">{field.label}{field.required ? " *" : ""}</label><SavedReferencePicker field={field} value={value} onChange={onChange}/><label className="upload-control"><Icon name="upload"/><span>{urls.length ? `${urls.length} выбрано` : "Добавить файл"}</span><input type="file" multiple={field.control === "files"} accept={field.accept || "image/*,video/*,audio/*"} onChange={(event) => void onUpload(Array.from(event.target.files || []))}/></label>{urls.length > 0 && <div className="upload-list">{urls.map((url, index) => <button type="button" key={`${url}-${index}`} onClick={() => onChange(field.control === "files" ? urls.filter((_, i) => i !== index) : "")}>Референс {index + 1} ×</button>)}</div>}</div>;
  }
  if (field.control === "textarea" || field.control === "json") return <label className="field"><span className="label">{field.label}{field.required ? " *" : ""}</span><textarea className="control textarea" value={value == null ? "" : typeof value === "string" ? value : JSON.stringify(value, null, 2)} placeholder={field.placeholder || ""} onChange={(event) => onChange(event.target.value)}/></label>;
  if (field.suggestions?.length) return <label className="field"><span className="label">{field.label}{field.required ? " *" : ""}</span><select className="control" value={value == null ? "" : String(value)} onChange={(event) => onChange(event.target.value)}><option value="">Выберите</option>{field.suggestions.map((item) => <option key={String(item)} value={String(item)}>{String(item)}</option>)}</select></label>;
  return <label className="field"><span className="label">{field.label}{field.required ? " *" : ""}</span><div className="input-with-suffix"><input className="control" type={field.control === "number" ? "number" : "text"} min={field.min} max={field.max} step={field.step} value={value == null ? "" : String(value)} placeholder={field.placeholder || ""} onChange={(event) => onChange(field.control === "number" ? (event.target.value ? Number(event.target.value) : null) : event.target.value)}/>{field.suffix && <span>{field.suffix}</span>}</div></label>;
}

function serializeParameters(fields: UiField[], values: Record<string, unknown>): Record<string, unknown> {
  const result = { ...values };
  for (const field of fields) {
    if (field.control !== "json") continue;
    const value = result[field.name];
    if (typeof value === "string" && value.trim()) {
      try { result[field.name] = JSON.parse(value); }
      catch { throw new Error(`Исправьте JSON в «${field.label}»`); }
    }
  }
  return result;
}

function goToGeneration(generationId: string) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  url.searchParams.set("route", "history");
  url.searchParams.set("generation", generationId);
  url.searchParams.delete("action");
  window.location.assign(`${url.pathname}${url.search}${url.hash}`);
}

function ActionError({ error, generationId }: { error: string; generationId: string }) {
  return <div className="roxy-app"><main className="main-shell"><section className="screen"><div className="panel action-error-card"><Icon name="settings"/><h1>Действие недоступно</h1><p className="muted">{error}</p><button className="primary wide" type="button" onClick={() => goToGeneration(generationId)}>Вернуться к работе</button></div></section></main></div>;
}
