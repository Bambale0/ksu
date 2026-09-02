"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import { privateRepeatApi, type PrivateRepeatDescriptor } from "@/lib/private-repeat-api";
import { haptic, notify } from "@/lib/telegram";
import type { GenerationModel, UiField, UiScenarioItem } from "@/lib/types";
import { StandaloneShell } from "./standalone-shell";

type Draft = {
  values: Record<string, unknown>;
  scenario: string | null;
};

function isEmpty(value: unknown): boolean {
  return value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0);
}

function modelFileFields(model: GenerationModel): UiField[] {
  return (model.ui_schema?.fields || []).filter((field) => field.control === "file" || field.control === "files");
}

function repeatReferenceFields(model: GenerationModel, descriptor: PrivateRepeatDescriptor): UiField[] {
  const modelFields = modelFileFields(model);
  const explicit = descriptor.reference_fields || [];
  if (!explicit.length) return descriptor.references_required ? modelFields : [];

  const byName = new Map(modelFields.map((field) => [field.name, field]));
  const result: UiField[] = [];
  for (const name of explicit) {
    const field = byName.get(name);
    if (field) {
      result.push(field);
      continue;
    }
    if (name === "input_url") {
      // Older generations stored the primary source outside model parameters.
      // It is still recipient media, but has no corresponding public UI field.
      result.push({
        name: "input_url",
        label: "Референс",
        control: "file",
        accept: "image/*,video/*,audio/*",
        required: true,
      });
    }
  }
  return result;
}

function allowedReferenceNames(model: GenerationModel, descriptor: PrivateRepeatDescriptor): Set<string> {
  return new Set(repeatReferenceFields(model, descriptor).map((field) => field.name));
}

function chooseScenario(model: GenerationModel, descriptor: PrivateRepeatDescriptor): string | null {
  const items = model.ui_schema?.scenario?.items || [];
  if (!items.length) return null;
  const modelNames = new Set(modelFileFields(model).map((field) => field.name));
  const allowed = new Set([...allowedReferenceNames(model, descriptor)].filter((name) => modelNames.has(name)));
  if (allowed.size) {
    const match = items.find((item) => (item.visible_fields || []).some((name) => allowed.has(name)));
    if (match) return match.id;
  }
  return model.ui_schema?.scenario?.default || items[0]?.id || null;
}

function scenarioReferenceFields(
  model: GenerationModel,
  scenarioId: string | null,
  descriptor: PrivateRepeatDescriptor,
): UiField[] {
  const fields = repeatReferenceFields(model, descriptor);
  if (!fields.length) return [];
  const scenarios = model.ui_schema?.scenario?.items || [];
  const scenario = scenarios.find((item) => item.id === scenarioId);
  const visible = new Set(scenario?.visible_fields || []);
  const modelNames = new Set(modelFileFields(model).map((field) => field.name));
  return fields.filter((field) => !modelNames.has(field.name) || !scenario || visible.has(field.name));
}

function requiredReferenceNames(
  model: GenerationModel,
  scenarioId: string | null,
  descriptor: PrivateRepeatDescriptor,
): Set<string> {
  const explicit = new Set(descriptor.reference_fields || []);
  if (explicit.size) return explicit;
  const scenario = model.ui_schema?.scenario?.items?.find((item: UiScenarioItem) => item.id === scenarioId);
  const fileNames = new Set(modelFileFields(model).map((field) => field.name));
  const required = new Set<string>();
  for (const name of scenario?.required_fields || []) if (fileNames.has(name)) required.add(name);
  return required;
}

function validateReferences(
  model: GenerationModel,
  draft: Draft,
  descriptor: PrivateRepeatDescriptor,
): string[] {
  if (!descriptor.references_required) return [];
  const available = allowedReferenceNames(model, descriptor);
  const explicit = descriptor.reference_fields || [];
  if (explicit.some((name) => !available.has(name))) {
    return ["Для этой работы нужен референс, который текущая версия модели больше не принимает"];
  }

  const visible = scenarioReferenceFields(model, draft.scenario, descriptor);
  if (!visible.length) return ["Для повтора нужен свой референс"];

  const required = requiredReferenceNames(model, draft.scenario, descriptor);
  if (required.size) {
    for (const name of required) {
      if (isEmpty(draft.values[name])) return ["Добавьте обязательный референс"];
    }
    return [];
  }
  if (!visible.some((field) => !isEmpty(draft.values[field.name]))) return ["Добавьте хотя бы один свой референс"];
  return [];
}

function referenceParameters(fields: UiField[], values: Record<string, unknown>): Record<string, unknown> {
  const parameters: Record<string, unknown> = {};
  for (const field of fields) {
    const value = values[field.name];
    if (!isEmpty(value)) parameters[field.name] = value;
  }
  return parameters;
}

function ReferenceFieldControl({ field, value, disabled, onUpload }: {
  field: UiField;
  value: unknown;
  disabled: boolean;
  onUpload: (files: File[]) => void;
}) {
  const items = Array.isArray(value) ? value : value ? [value] : [];
  return <label className="field">
    <span className="label">{field.label}</span>
    <span className="upload-control">
      <span>{disabled ? "Загружаю…" : items.length ? `Добавлено: ${items.length} · выбрать ещё` : "Добавить свой файл"}</span>
      <input
        type="file"
        accept={field.accept}
        multiple={field.control === "files"}
        disabled={disabled}
        onChange={(event) => {
          const files = Array.from(event.currentTarget.files || []);
          event.currentTarget.value = "";
          onUpload(files);
        }}
      />
    </span>
    {items.length ? <small className="muted">Используются только ваши загрузки.</small> : null}
  </label>;
}

export function PrivateRepeatStartApp({ token }: { token: string }) {
  const [descriptor, setDescriptor] = useState<PrivateRepeatDescriptor | null>(null);
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
      .then(([nextDescriptor, catalog]) => {
        if (!active) return;
        const nextModel = catalog.models.find((item) => item.id === nextDescriptor.model_id);
        if (!nextModel) throw new Error("Эта модель больше недоступна");
        setDescriptor(nextDescriptor);
        setModel(nextModel);
        setDraft({ values: {}, scenario: chooseScenario(nextModel, nextDescriptor) });
      })
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "Не удалось открыть ссылку повтора"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [token]);

  const referenceFields = useMemo(() => model && draft && descriptor
    ? scenarioReferenceFields(model, draft.scenario, descriptor)
    : [], [descriptor, draft, model]);
  const errors = useMemo(() => model && draft && descriptor
    ? validateReferences(model, draft, descriptor)
    : [], [descriptor, draft, model]);
  const parameters = useMemo(() => draft ? referenceParameters(referenceFields, draft.values) : {}, [draft, referenceFields]);

  useEffect(() => {
    if (!descriptor || !model || !draft || errors.length || uploading || submitting) { setQuote(null); return; }
    const seq = ++quoteSeq.current;
    const timer = window.setTimeout(() => {
      void privateRepeatApi.quote(token, parameters)
        .then((next) => { if (quoteSeq.current === seq) { setQuote(next); setError(""); } })
        .catch((reason) => { if (quoteSeq.current === seq) { setQuote(null); setError(reason instanceof Error ? reason.message : "Не удалось рассчитать стоимость"); } });
    }, 260);
    return () => window.clearTimeout(timer);
  }, [descriptor, draft, errors.length, model, parameters, submitting, token, uploading]);

  const update = (name: string, value: unknown) => setDraft((current) => current ? { ...current, values: { ...current.values, [name]: value } } : current);

  const upload = async (field: UiField, files: File[]) => {
    if (!files.length || uploading) return;
    setUploading(true); setError("");
    try {
      const existing = field.control === "files" && Array.isArray(draft?.values[field.name])
        ? [...draft.values[field.name] as string[]]
        : [];
      const maxItems = field.control === "file" ? 1 : field.max_items || 12;
      const availableSlots = Math.max(0, maxItems - existing.length);
      if (field.control === "files" && availableSlots === 0) throw new Error(`Можно добавить максимум ${maxItems} файлов`);

      const urls: string[] = [];
      for (const file of files.slice(0, field.control === "file" ? 1 : availableSlots)) {
        if (field.max_size_mb && file.size > field.max_size_mb * 1024 * 1024) throw new Error(`${file.name}: максимум ${field.max_size_mb} МБ`);
        const result = await api.upload(file);
        urls.push(result.url);
      }
      update(field.name, field.control === "file" ? urls[0] || "" : [...existing, ...urls]);
      notify("success"); haptic("light");
    } catch (reason) {
      notify("error"); setError(reason instanceof Error ? reason.message : "Не удалось загрузить файл");
    } finally { setUploading(false); }
  };

  const launch = async () => {
    if (!model || !draft || !descriptor || errors.length || !quote || submitting) return;
    setSubmitting(true); setError("");
    try {
      const created = await privateRepeatApi.launch(token, parameters);
      notify("success"); haptic("medium");
      window.location.assign(`/mini-app/?route=history&generation=${encodeURIComponent(created.id)}`);
    } catch (reason) {
      notify("error"); setError(reason instanceof Error ? reason.message : "Не удалось запустить повтор"); setSubmitting(false);
    }
  };

  return <StandaloneShell
    kicker="Приватный повтор"
    title={model?.title || "Повторить в ROXY"}
    copy="Промпт и настройки исходной работы скрыты. Добавьте только свои референсы — остальное ROXY повторит автоматически."
  >
    {loading ? <div className="panel tool-panel"><p className="muted">Открываю повтор…</p></div> : null}
    {error ? <div className="action-error" role="alert">{error}</div> : null}
    {descriptor && model && draft ? <div className="tool-grid">
      <div className="panel tool-panel">
        <span className="kicker">1 · Референс</span>
        <div className="panel" style={{ padding: 12 }}>
          <strong>{descriptor.references_required ? "Добавьте свой референс" : "Всё готово к повтору"}</strong>
          <p className="muted">Промпт и исходные настройки не показываются, не загружаются в приложение и не редактируются. ROXY использует их только на сервере.</p>
        </div>
        {referenceFields.map((field) => <ReferenceFieldControl
          key={field.name}
          field={field}
          value={draft.values[field.name]}
          disabled={uploading}
          onUpload={(files) => void upload(field, files)}
        />)}
      </div>
      <aside className="panel tool-panel">
        <span className="kicker">2 · Запуск</span><h2>{model.title}</h2>
        <p className="muted">Новая работа останется приватной, пока вы сами не решите её опубликовать.</p>
        <div className="quote-box"><span>Стоимость</span><strong>{quote?.cost_rox ? `${quote.cost_rox} ROX` : "—"}</strong><small>{errors[0] || (quote ? "Можно запускать" : "Считаю…")}</small></div>
        <button className="primary wide" type="button" disabled={!quote || Boolean(errors.length) || uploading || submitting} onClick={() => void launch()}>{submitting ? "Запускаю…" : quote?.cost_rox ? `Повторить · ${quote.cost_rox} ROX` : "Повторить"}</button>
        <button className="secondary wide" type="button" disabled={submitting} onClick={() => window.location.assign("/mini-app/?route=home")}>На главную</button>
      </aside>
    </div> : null}
  </StandaloneShell>;
}
