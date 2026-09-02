"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import { privateRepeatApi } from "@/lib/private-repeat-api";
import { haptic, notify } from "@/lib/telegram";
import type { GenerationModel, RecreateGenerationPayload, UiField, UiScenarioItem } from "@/lib/types";
import { StandaloneShell } from "./standalone-shell";

type Draft = {
  prompt: string;
  values: Record<string, unknown>;
  scenario: string | null;
  billingSeconds: number | null;
};

function isEmpty(value: unknown): boolean {
  return value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0);
}

function fileFieldNames(model: GenerationModel): Set<string> {
  return new Set(
    (model.ui_schema?.fields || [])
      .filter((field) => field.control === "file" || field.control === "files")
      .map((field) => field.name),
  );
}

function scenarioScore(item: UiScenarioItem, values: Record<string, unknown>): number {
  const required = item.required_fields || [];
  const any = item.required_any || [];
  if (required.some((name) => isEmpty(values[name]))) return -1;
  if (any.length && !any.some((name) => !isEmpty(values[name]))) return -1;
  return required.length * 4 + (any.length ? 3 : 0) + (item.visible_fields || []).filter((name) => !isEmpty(values[name])).length;
}

function chooseScenario(model: GenerationModel, recipe: RecreateGenerationPayload, values: Record<string, unknown>): string | null {
  const items = model.ui_schema?.scenario?.items || [];
  if (!items.length) return null;
  if (recipe.references_required) {
    const files = fileFieldNames(model);
    const referenceScenario = items.find((item) => (item.visible_fields || []).some((name) => files.has(name)));
    if (referenceScenario) return referenceScenario.id;
  }
  let winner = items[0];
  let score = -1;
  for (const item of items) {
    const next = scenarioScore(item, values);
    if (next > score) {
      winner = item;
      score = next;
    }
  }
  return winner?.id || model.ui_schema?.scenario?.default || items[0]?.id || null;
}

function visibleFields(model: GenerationModel, scenarioId: string | null): UiField[] {
  const fields = model.ui_schema?.fields || [];
  const scenarios = model.ui_schema?.scenario?.items || [];
  const scenario = scenarios.find((item) => item.id === scenarioId);
  if (!scenario) return fields;
  const controlled = new Set<string>();
  for (const item of scenarios) {
    for (const name of item.visible_fields || []) controlled.add(name);
    for (const name of item.clear_fields || []) controlled.add(name);
  }
  return fields.filter((field) => !controlled.has(field.name) || scenario.visible_fields?.includes(field.name));
}

function buildPayload(model: GenerationModel, draft: Draft): Record<string, unknown> {
  const parameters: Record<string, unknown> = {};
  for (const field of visibleFields(model, draft.scenario)) {
    if (field.name === "prompt") continue;
    const value = draft.values[field.name];
    if (isEmpty(value)) continue;
    if (field.control === "json" && typeof value === "string") parameters[field.name] = JSON.parse(value);
    else parameters[field.name] = value;
  }
  const payload: Record<string, unknown> = {
    model_id: model.id,
    prompt: draft.prompt,
    parameters,
  };
  if (draft.billingSeconds) payload.billing_seconds = draft.billingSeconds;
  return payload;
}

function validate(model: GenerationModel, draft: Draft): string[] {
  const errors: string[] = [];
  const fields = visibleFields(model, draft.scenario);
  for (const field of fields) {
    const value = field.name === "prompt" ? draft.prompt : draft.values[field.name];
    if (field.required && isEmpty(value)) errors.push(`Заполните «${field.name === "prompt" ? "Описание" : field.label}»`);
    if (field.control === "json" && !isEmpty(value)) {
      try { JSON.parse(String(value)); } catch { errors.push(`Проверьте «${field.label}»`); }
    }
  }
  const scenario = model.ui_schema?.scenario?.items?.find((item) => item.id === draft.scenario);
  for (const name of scenario?.required_fields || []) {
    if (isEmpty(draft.values[name])) errors.push("Добавьте обязательный референс");
  }
  const any = scenario?.required_any || [];
  if (any.length && !any.some((name) => !isEmpty(draft.values[name]))) errors.push("Добавьте хотя бы один свой референс");
  const billing = model.ui_schema?.billing_seconds;
  if (billing?.required && !draft.billingSeconds) errors.push(`Заполните «${billing.label || "Длительность"}»`);
  return [...new Set(errors)];
}

function FieldControl({ field, value, disabled, onChange, onUpload }: {
  field: UiField;
  value: unknown;
  disabled: boolean;
  onChange: (value: unknown) => void;
  onUpload: (files: File[]) => void;
}) {
  const label = field.name === "prompt" ? "Описание" : field.label;
  if (field.control === "file" || field.control === "files") {
    const items = Array.isArray(value) ? value : value ? [value] : [];
    return <label className="field"><span className="label">{label}{field.required ? " · обязательно" : ""}</span><span className="upload-control"><span>{disabled ? "Загружаю…" : items.length ? `Добавлено: ${items.length} · выбрать ещё` : "Добавить свой файл"}</span><input type="file" accept={field.accept} multiple={field.control === "files"} disabled={disabled} onChange={(event) => { const files = Array.from(event.currentTarget.files || []); event.currentTarget.value = ""; onUpload(files); }} /></span>{items.length ? <small className="muted">Файлы автора сюда не передаются — используются только ваши загрузки.</small> : null}</label>;
  }
  if (field.control === "toggle") {
    return <label className="toggle-row"><span><strong>{label}</strong></span><input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} /><i /></label>;
  }
  if (field.suggestions?.length) {
    return <label className="field"><span className="label">{label}</span><select className="control" value={String(value ?? "")} onChange={(event) => onChange(event.target.value)}><option value="">Выберите</option>{field.suggestions.map((item) => <option key={String(item)} value={String(item)}>{String(item)}</option>)}</select></label>;
  }
  if (field.control === "number") {
    return <label className="field"><span className="label">{label}</span><input className="control" type="number" min={field.min} max={field.max} step={field.step} value={String(value ?? "")} onChange={(event) => onChange(event.target.value === "" ? "" : Number(event.target.value))} /></label>;
  }
  if (field.control === "textarea" || field.control === "json") {
    return <label className="field"><span className="label">{label}</span><textarea className="control textarea" rows={field.control === "json" ? 5 : 3} value={typeof value === "string" ? value : field.control === "json" && value ? JSON.stringify(value, null, 2) : String(value ?? "")} placeholder={field.placeholder} onChange={(event) => onChange(event.target.value)} /></label>;
  }
  return <label className="field"><span className="label">{label}</span><input className="control" value={String(value ?? "")} placeholder={field.placeholder} onChange={(event) => onChange(event.target.value)} /></label>;
}

export function PrivateRepeatStartApp({ token }: { token: string }) {
  const [recipe, setRecipe] = useState<RecreateGenerationPayload | null>(null);
  const [model, setModel] = useState<GenerationModel | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [quote, setQuote] = useState<{ cost_rox?: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const quoteSeq = useRef(0);

  useEffect(() => {
    let active = true;
    Promise.all([privateRepeatApi.resolve(token), api.models()])
      .then(([nextRecipe, catalog]) => {
        if (!active) return;
        const nextModel = catalog.models.find((item) => item.id === nextRecipe.model_id);
        if (!nextModel) throw new Error("Эта модель больше недоступна");
        const values = { ...(nextModel.ui_schema?.defaults || {}), ...(nextRecipe.parameters || {}) };
        const scenario = chooseScenario(nextModel, nextRecipe, values);
        setRecipe(nextRecipe);
        setModel(nextModel);
        setDraft({ prompt: nextRecipe.prompt || "", values, scenario, billingSeconds: nextRecipe.billing_seconds ?? null });
      })
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "Не удалось открыть ссылку повтора"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [token]);

  const errors = useMemo(() => model && draft ? validate(model, draft) : [], [draft, model]);
  const fields = useMemo(() => model && draft ? visibleFields(model, draft.scenario).filter((field) => field.name !== "prompt") : [], [draft, model]);

  useEffect(() => {
    if (!model || !draft || errors.length || uploading || submitting) { setQuote(null); return; }
    const seq = ++quoteSeq.current;
    const timer = window.setTimeout(() => {
      let body: Record<string, unknown>;
      try { body = buildPayload(model, draft); } catch { setQuote(null); return; }
      void api.quote(body)
        .then((next) => { if (quoteSeq.current === seq) { setQuote(next); setError(""); } })
        .catch((reason) => { if (quoteSeq.current === seq) { setQuote(null); setError(reason instanceof Error ? reason.message : "Не удалось рассчитать стоимость"); } });
    }, 260);
    return () => window.clearTimeout(timer);
  }, [draft, errors.length, model, submitting, uploading]);

  const update = (name: string, value: unknown) => setDraft((current) => current ? { ...current, values: { ...current.values, [name]: value } } : current);

  const upload = async (field: UiField, files: File[]) => {
    if (!files.length || uploading) return;
    setUploading(true); setError("");
    try {
      const urls: string[] = [];
      for (const file of files.slice(0, field.control === "file" ? 1 : field.max_items || 12)) {
        if (field.max_size_mb && file.size > field.max_size_mb * 1024 * 1024) throw new Error(`${file.name}: максимум ${field.max_size_mb} МБ`);
        const result = await api.upload(file);
        urls.push(result.url);
      }
      update(field.name, field.control === "file" ? urls[0] || "" : urls);
      notify("success"); haptic("light");
    } catch (reason) {
      notify("error"); setError(reason instanceof Error ? reason.message : "Не удалось загрузить файл");
    } finally { setUploading(false); }
  };

  const launch = async () => {
    if (!model || !draft || errors.length || !quote || submitting) return;
    setSubmitting(true); setError("");
    try {
      const created = await api.create(buildPayload(model, draft));
      notify("success"); haptic("medium");
      window.location.assign(`/mini-app/?route=history&generation=${encodeURIComponent(created.id)}`);
    } catch (reason) {
      notify("error"); setError(reason instanceof Error ? reason.message : "Не удалось запустить повтор"); setSubmitting(false);
    }
  };

  return <StandaloneShell kicker="Приватный повтор" title={model?.title || "Повторить в ROXY"} copy="Исходная работа остаётся приватной. Ссылка переносит только идею и безопасные настройки — фото, видео и другие файлы автора не передаются.">
    {loading ? <div className="panel tool-panel"><p className="muted">Открываю настройки повтора…</p></div> : null}
    {error ? <div className="action-error" role="alert">{error}</div> : null}
    {recipe && model && draft ? <div className="tool-grid">
      <div className="panel tool-panel">
        <span className="kicker">1 · Идея</span>
        <label className="field"><span className="label">Описание</span><textarea className="control textarea" rows={4} maxLength={8000} value={draft.prompt} onChange={(event) => setDraft((current) => current ? { ...current, prompt: event.target.value } : current)} /></label>
        {recipe.references_required ? <div className="panel" style={{ padding: 12 }}><strong>Добавьте свои референсы</strong><p className="muted">У автора в этой генерации были свои файлы. Из соображений приватности ROXY их не показывает и не копирует.</p></div> : null}
        {fields.map((field) => <FieldControl key={field.name} field={field} value={draft.values[field.name]} disabled={uploading} onChange={(value) => update(field.name, value)} onUpload={(files) => void upload(field, files)} />)}
        {model.ui_schema?.billing_seconds ? <label className="field"><span className="label">{model.ui_schema.billing_seconds.label || "Длительность"}</span><input className="control" type="number" min={model.ui_schema.billing_seconds.min} max={model.ui_schema.billing_seconds.max} value={draft.billingSeconds ?? ""} onChange={(event) => setDraft((current) => current ? { ...current, billingSeconds: event.target.value ? Number(event.target.value) : null } : current)} /></label> : null}
      </div>
      <aside className="panel tool-panel">
        <span className="kicker">2 · Запуск</span><h2>{model.title}</h2>
        <p className="muted">Никакой публикации не происходит. Новая работа тоже будет приватной, пока вы сами не решите её опубликовать.</p>
        <div className="quote-box"><span>Стоимость</span><strong>{quote?.cost_rox ? `${quote.cost_rox} ROX` : "—"}</strong><small>{errors[0] || (quote ? "Можно запускать" : "Считаю…")}</small></div>
        <button className="primary wide" type="button" disabled={!quote || Boolean(errors.length) || uploading || submitting} onClick={() => void launch()}>{submitting ? "Запускаю…" : quote?.cost_rox ? `Повторить · ${quote.cost_rox} ROX` : "Повторить"}</button>
        <button className="secondary wide" type="button" disabled={submitting} onClick={() => window.location.assign("/mini-app/?route=home")}>На главную</button>
      </aside>
    </div> : null}
  </StandaloneShell>;
}
