"use client";

import { useEffect, useMemo, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { api } from "@/lib/api";
import { telegramHeaders } from "@/lib/telegram";
import type { GenerationModel, UiField } from "@/lib/types";

const INPUT_FIELDS = new Set(["image_url", "image_urls", "image_input", "input_urls"]);
const BATCH_UNSUPPORTED_FIELDS = new Set(["bbox_list"]);

type CatalogModel = GenerationModel & { known_fields?: string[]; notes?: string[] };
type BatchQuote = {
  input_count: number;
  per_item_cost_credits?: string | null;
  total_cost_credits: string;
  total_cost_rub?: string;
  admin_free?: boolean;
};
type BatchItem = { ordinal: number; generation: { id: string; status: string; result_url?: string | null; error?: string | null; cost_credits?: string } };
type BatchJob = {
  id: string;
  status: string;
  model_id: string;
  prompt: string;
  input_count: number;
  succeeded_count: number;
  failed_count: number;
  active_count: number;
  progress_percent: number;
  total_charged_credits: string;
  admin_free?: boolean;
  items?: BatchItem[];
};

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
  const payload = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail ?? payload?.message ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload as T;
}

function idem(prefix: string): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return `${prefix}:${crypto.randomUUID()}`;
  return `${prefix}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
}

function money(value?: string | number | null): string {
  if (value == null) return "—";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) : String(value);
}

function statusLabel(value?: string | null): string {
  const labels: Record<string, string> = {
    queued: "В очереди",
    running: "Создаётся",
    succeeded: "Готово",
    failed: "Не получилось",
    partial: "Частично готово",
    canceled: "Отменено",
  };
  return value ? labels[value] || "В работе" : "В работе";
}

function batchFields(model: CatalogModel | null): UiField[] {
  if (!model) return [];
  return (model.ui_schema?.fields || []).filter((field) => (
    field.name !== "prompt" && !INPUT_FIELDS.has(field.name) && !BATCH_UNSUPPORTED_FIELDS.has(field.name)
  ));
}

function DynamicBatchField({ field, value, onChange }: { field: UiField; value: unknown; onChange: (value: unknown) => void }) {
  if (field.control === "toggle") return <label className="toggle-row"><span><strong>{field.label}</strong></span><input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)}/><i/></label>;
  if (field.suggestions?.length) return <label className="field"><span className="label">{field.label}{field.required ? " *" : ""}</span><select className="control" value={value == null ? "" : String(value)} onChange={(event) => onChange(event.target.value)}><option value="">Выберите</option>{field.suggestions.map((item) => <option key={String(item)} value={String(item)}>{String(item)}</option>)}</select></label>;
  if (field.control === "textarea") return <label className="field"><span className="label">{field.label}{field.required ? " *" : ""}</span><textarea className="control textarea" value={value == null ? "" : String(value)} placeholder={field.placeholder || ""} onChange={(event) => onChange(event.target.value)}/></label>;
  if (field.control === "json") return null;
  return <label className="field"><span className="label">{field.label}{field.required ? " *" : ""}</span><div className="input-with-suffix"><input className="control" type={field.control === "number" ? "number" : "text"} min={field.min} max={field.max} step={field.step} value={value == null ? "" : String(value)} placeholder={field.placeholder || ""} onChange={(event) => onChange(field.control === "number" ? (event.target.value === "" ? null : Number(event.target.value)) : event.target.value)}/>{field.suffix ? <span>{field.suffix}</span> : null}</div></label>;
}

export default function BatchPage() {
  const [models, setModels] = useState<CatalogModel[]>([]);
  const [modelId, setModelId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [parameters, setParameters] = useState<Record<string, unknown>>({});
  const [billingSeconds, setBillingSeconds] = useState<number | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [urls, setUrls] = useState<string[]>([]);
  const [quote, setQuote] = useState<BatchQuote | null>(null);
  const [jobs, setJobs] = useState<BatchJob[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selected = useMemo(() => models.find((model) => model.id === modelId) || null, [modelId, models]);
  const fields = useMemo(() => batchFields(selected), [selected]);

  const loadJobs = async () => {
    try {
      const payload = await request<{ items: BatchJob[] }>("/api/v1/batch-generations?limit=10");
      setJobs(payload.items || []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить пакеты");
    }
  };

  useEffect(() => {
    void Promise.all([
      api.models().then((catalog) => {
        const compatible = (catalog.models as CatalogModel[]).filter((model) => (
          model.media_type === "image" && (model.known_fields || []).some((field) => INPUT_FIELDS.has(field))
        ));
        setModels(compatible);
        const first = compatible[0];
        if (first) {
          setModelId(first.id);
          setParameters({ ...(first.ui_schema?.defaults || {}) });
        }
      }),
      loadJobs(),
    ]).catch((reason) => setError(reason instanceof Error ? reason.message : "Не удалось открыть Batch"));
  }, []);

  const chooseModel = (id: string) => {
    const model = models.find((item) => item.id === id);
    if (!model) return;
    setModelId(id);
    setParameters({ ...(model.ui_schema?.defaults || {}) });
    setBillingSeconds(null);
    setQuote(null);
    setError("");
  };

  const addFiles = (nextFiles: File[]) => {
    const seen = new Set(files.map((file) => `${file.name}:${file.size}:${file.lastModified}`));
    const next = [...files];
    for (const file of nextFiles.filter((item) => item.type.startsWith("image/"))) {
      const key = `${file.name}:${file.size}:${file.lastModified}`;
      if (!seen.has(key) && next.length < 20) {
        seen.add(key);
        next.push(file);
      }
    }
    setFiles(next);
    setUrls([]);
    setQuote(null);
  };

  const validate = (): string => {
    if (!selected) return "Выберите модель";
    if (files.length < 2 || files.length > 20) return "Добавьте от 2 до 20 изображений";
    const promptField = selected.ui_schema?.fields?.find((field) => field.name === "prompt");
    if (promptField?.required && !prompt.trim()) return "Добавьте описание";
    for (const field of fields) {
      const value = parameters[field.name];
      const empty = value === undefined || value === null || value === "" || (Array.isArray(value) && !value.length);
      if (field.required && empty) return `Заполните «${field.label}»`;
    }
    const billing = selected.ui_schema?.billing_seconds;
    if (billing?.required && !billingSeconds) return `Заполните «${billing.label || "Длительность"}»`;
    return "";
  };

  const uploadAll = async (): Promise<string[]> => {
    if (urls.length === files.length) return urls;
    const uploaded: string[] = [];
    for (const file of files) {
      const result = await api.upload(file);
      uploaded.push(result.url);
    }
    setUrls(uploaded);
    return uploaded;
  };

  const payload = async () => ({
    model_id: modelId,
    prompt: prompt.trim(),
    parameters: Object.fromEntries(Object.entries(parameters).filter(([name, value]) => (
      name !== "prompt" && !INPUT_FIELDS.has(name) && !BATCH_UNSUPPORTED_FIELDS.has(name) && value !== "" && value !== null && value !== undefined
    ))),
    billing_seconds: billingSeconds,
    input_urls: await uploadAll(),
    reference_ids: [],
  });

  const calculate = async () => {
    const issue = validate();
    if (issue) { setError(issue); return; }
    setBusy(true);
    setError("");
    try {
      const result = await request<BatchQuote>("/api/v1/batch-generations/quote", { method: "POST", body: JSON.stringify(await payload()) });
      setQuote(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось рассчитать пакет");
    } finally { setBusy(false); }
  };

  const start = async () => {
    const issue = validate();
    if (issue) { setError(issue); return; }
    setBusy(true);
    setError("");
    try {
      const result = await request<BatchJob>("/api/v1/batch-generations", {
        method: "POST",
        headers: { "Idempotency-Key": idem("batch") },
        body: JSON.stringify(await payload()),
      });
      setFiles([]);
      setUrls([]);
      setQuote(null);
      setJobs((current) => [result, ...current.filter((item) => item.id !== result.id)]);
      window.setTimeout(() => void loadJobs(), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось запустить пакет");
    } finally { setBusy(false); }
  };

  const retry = async (job: BatchJob) => {
    setBusy(true);
    setError("");
    try {
      const retryQuote = await request<{ failed_count: number; total_cost_credits: string; admin_free?: boolean }>(`/api/v1/batch-generations/${encodeURIComponent(job.id)}/retry-quote`);
      if (!retryQuote.failed_count) return;
      const result = await request<BatchJob & { retried_count?: number }>(`/api/v1/batch-generations/${encodeURIComponent(job.id)}/retry`, {
        method: "POST",
        headers: { "Idempotency-Key": idem("batch-retry") },
      });
      setJobs((current) => current.map((item) => item.id === result.id ? result : item));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось повторить ошибки");
    } finally { setBusy(false); }
  };

  return (
    <StandaloneShell kicker="Пакет" title="Пакетная обработка" copy="Загрузите 2–20 изображений, добавьте одно описание и запустите их одной задачей.">
      <div className="panel tool-panel">
        <label className="field"><span className="label">Модель</span><select className="control" value={modelId} onChange={(event) => chooseModel(event.target.value)}>{models.map((model) => <option key={model.id} value={model.id}>{model.title} · {money(model.price_rox)} ROX</option>)}</select></label>
        <label className="field"><span className="label">Описание</span><textarea className="control textarea" value={prompt} onChange={(event) => { setPrompt(event.target.value); setQuote(null); }} placeholder="Что изменить в каждом изображении?"/></label>

        {fields.length ? <div className="form-stack">{fields.map((field) => <DynamicBatchField key={field.name} field={field} value={parameters[field.name]} onChange={(value) => { setParameters((current) => ({ ...current, [field.name]: value })); setQuote(null); }}/>)}</div> : null}

        {selected?.ui_schema?.billing_seconds ? <label className="field"><span className="label">{selected.ui_schema.billing_seconds.label || "Длительность"}</span><input className="control" type="number" min={selected.ui_schema.billing_seconds.min || 1} max={selected.ui_schema.billing_seconds.max || 600} value={billingSeconds ?? ""} onChange={(event) => { setBillingSeconds(event.target.value ? Number(event.target.value) : null); setQuote(null); }}/></label> : null}

        <label className="upload-control"><span>{files.length ? `${files.length} изображений выбрано` : "Добавить 2–20 изображений"}</span><input type="file" accept="image/*" multiple disabled={busy} onChange={(event) => { addFiles(Array.from(event.target.files || [])); event.target.value = ""; }}/></label>
        <div className="tool-file-list">{files.map((file, index) => <div className="tool-file-chip" key={`${file.name}-${file.lastModified}-${index}`}><span>{index + 1}. {file.name}</span><button type="button" aria-label={`Удалить ${file.name}`} onClick={() => { setFiles((current) => current.filter((_, i) => i !== index)); setUrls([]); setQuote(null); }}>×</button></div>)}</div>

        {quote ? <div className="profile-stats"><div><strong>{quote.input_count}</strong><span>изображений</span></div><div><strong>{quote.admin_free ? "0" : money(quote.per_item_cost_credits)}</strong><span>ROX / файл</span></div><div><strong>{quote.admin_free ? "0" : money(quote.total_cost_credits)}</strong><span>ROX всего</span></div></div> : null}
        {error ? <div className="action-error" role="alert">{error}</div> : null}
        <div className="tool-actions"><button className="secondary" type="button" disabled={busy} onClick={() => void calculate()}>{busy ? "Работаю…" : "Рассчитать стоимость"}</button><button className="primary" type="button" disabled={busy} onClick={() => void start()}>{busy ? "Работаю…" : "Запустить пакет"}</button></div>
      </div>

      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">История</span><h2>Последние пакеты</h2></div><button type="button" onClick={() => void loadJobs()}>Обновить</button></div>
        <div className="tool-grid">{jobs.length ? jobs.map((job) => <article className="tool-result-card" key={job.id}>
          <div className="section-title"><div><span className="kicker">{job.model_id}</span><h2>{job.succeeded_count}/{job.input_count} готово</h2></div><span className={`status ${job.status}`}>{statusLabel(job.status)}</span></div>
          <div className="tool-progress"><i style={{ width: `${Math.max(0, Math.min(100, Number(job.progress_percent) || 0))}%` }}/></div>
          <div className="profile-stats"><div><strong>{job.succeeded_count}</strong><span>успешно</span></div><div><strong>{job.failed_count}</strong><span>ошибок</span></div><div><strong>{job.admin_free ? "0" : money(job.total_charged_credits)}</strong><span>ROX</span></div></div>
          {job.items?.length ? <div className="media-grid">{job.items.map((item) => <div className="media-tile" key={item.ordinal}>{item.generation.result_url ? <img src={item.generation.result_url} alt={`Результат ${item.ordinal + 1}`}/> : <span className="media-placeholder"><small>{item.generation.error ? "Не получилось" : statusLabel(item.generation.status)}</small></span>}</div>)}</div> : null}
          {job.failed_count > 0 && !["running", "queued"].includes(job.status) ? <button className="secondary wide" type="button" disabled={busy} onClick={() => void retry(job)}>Повторить ошибки</button> : null}
        </article>) : <p className="muted">Пакетов пока нет.</p>}</div>
      </div>
    </StandaloneShell>
  );
}
