"use client";

import { useEffect, useMemo, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { api } from "@/lib/api";
import { customerRequest, dateTime } from "@/lib/customer-api";
import type { GenerationModel, UiField } from "@/lib/types";

type Preset = { id: string; name: string; model_id: string; prompt: string; parameters: Record<string, unknown>; billing_seconds?: number | null; reference_ids: string[]; created_at: string; updated_at: string };
type ReferenceItem = { id: string; kind: string; label?: string | null; original_filename?: string | null; url?: string };

function EditableField({ field, value, onChange }: { field: UiField; value: unknown; onChange: (value: unknown) => void }) {
  if (field.control === "file" || field.control === "files") return null;
  if (field.control === "toggle") return <label className="toggle-row"><span><strong>{field.label}</strong><small>{field.placeholder || ""}</small></span><input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} /><i /></label>;
  if (field.suggestions?.length) return <label className="field"><span className="label">{field.label}</span><select className="control" value={value == null ? "" : String(value)} onChange={(event) => onChange(event.target.value)}><option value="">Не выбрано</option>{field.suggestions.map((item) => <option key={String(item)} value={String(item)}>{String(item)}</option>)}</select></label>;
  if (field.control === "textarea" || field.control === "json") return <label className="field"><span className="label">{field.label}</span><textarea className="control textarea" value={value == null ? "" : typeof value === "string" ? value : JSON.stringify(value)} onChange={(event) => onChange(event.target.value)} /></label>;
  return <label className="field"><span className="label">{field.label}</span><input className="control" type={field.control === "number" ? "number" : "text"} min={field.min} max={field.max} step={field.step} value={value == null ? "" : String(value)} onChange={(event) => onChange(field.control === "number" ? (event.target.value === "" ? null : Number(event.target.value)) : event.target.value)} /></label>;
}

export default function PresetsPage() {
  const [models, setModels] = useState<GenerationModel[]>([]);
  const [references, setReferences] = useState<ReferenceItem[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [modelId, setModelId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [parameters, setParameters] = useState<Record<string, unknown>>({});
  const [billingSeconds, setBillingSeconds] = useState<number | null>(null);
  const [referenceIds, setReferenceIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selected = useMemo(() => models.find((item) => item.id === modelId) || null, [models, modelId]);
  const fields = useMemo(() => (selected?.ui_schema?.fields || []).filter((field) => field.name !== "prompt"), [selected]);

  const load = async () => {
    setError("");
    try {
      const [catalog, presetResult, referenceResult] = await Promise.all([
        api.models(),
        customerRequest<{ items: Preset[] }>("/api/v1/presets"),
        customerRequest<{ items: ReferenceItem[] }>("/api/v1/references?limit=100"),
      ]);
      setModels(catalog.models || []);
      setPresets(presetResult.items || []);
      setReferences(referenceResult.items || []);
      if (!modelId && catalog.models?.[0]) {
        setModelId(catalog.models[0].id);
        setParameters({ ...(catalog.models[0].ui_schema?.defaults || {}) });
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить пресеты");
    }
  };

  useEffect(() => { void load(); }, []);

  const reset = (nextModelId?: string) => {
    const model = models.find((item) => item.id === (nextModelId || modelId)) || models[0];
    setEditingId(null); setName(""); setPrompt(""); setReferenceIds([]); setBillingSeconds(null);
    if (model) { setModelId(model.id); setParameters({ ...(model.ui_schema?.defaults || {}) }); }
  };

  const edit = (preset: Preset) => {
    setEditingId(preset.id); setName(preset.name); setModelId(preset.model_id); setPrompt(preset.prompt); setParameters({ ...(preset.parameters || {}) }); setBillingSeconds(preset.billing_seconds ?? null); setReferenceIds(preset.reference_ids || []);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const serializeParameters = () => {
    const next: Record<string, unknown> = {};
    for (const field of fields) {
      let value = parameters[field.name];
      if (value === "" || value === null || value === undefined) continue;
      if (field.control === "json" && typeof value === "string") value = JSON.parse(value);
      next[field.name] = value;
    }
    return next;
  };

  const save = async () => {
    if (!name.trim() || !modelId || busy) return;
    setBusy(true); setError("");
    try {
      const body = JSON.stringify({ name: name.trim(), model_id: modelId, prompt, parameters: serializeParameters(), reference_ids: referenceIds, billing_seconds: billingSeconds });
      if (editingId) await customerRequest(`/api/v1/presets/${encodeURIComponent(editingId)}`, { method: "PUT", body });
      else await customerRequest("/api/v1/presets", { method: "POST", body });
      reset(); await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить пресет");
    } finally { setBusy(false); }
  };

  const remove = async (id: string) => {
    if (busy) return;
    setBusy(true); setError("");
    try { await customerRequest(`/api/v1/presets/${encodeURIComponent(id)}`, { method: "DELETE" }); if (editingId === id) reset(); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось удалить пресет"); }
    finally { setBusy(false); }
  };

  const chooseModel = (id: string) => {
    const model = models.find((item) => item.id === id);
    if (!model) return;
    setModelId(id); setParameters({ ...(model.ui_schema?.defaults || {}) }); setBillingSeconds(null);
  };

  return (
    <StandaloneShell kicker="Пресеты" title="Мои настройки" copy="Сохраняйте модель, промпт, параметры, длительность и библиотеку референсов как повторно используемые наборы.">
      {error ? <div className="action-error" role="alert">{error}</div> : null}
      <div className="tool-grid">
        <div className="panel tool-panel">
          <div className="section-title"><div><span className="kicker">{editingId ? "Редактирование" : "Новый пресет"}</span><h2>{editingId ? "Изменить набор" : "Сохранить набор"}</h2></div>{editingId ? <button type="button" onClick={() => reset()}>Отмена</button> : null}</div>
          <div className="form-stack">
            <label className="field"><span className="label">Название</span><input className="control" maxLength={80} value={name} onChange={(event) => setName(event.target.value)} placeholder="Например: Kling cinematic" /></label>
            <label className="field"><span className="label">Модель</span><select className="control" value={modelId} onChange={(event) => chooseModel(event.target.value)}>{models.map((model) => <option key={model.id} value={model.id}>{model.title}</option>)}</select></label>
            <label className="field"><span className="label">Промпт</span><textarea className="control textarea" maxLength={8000} value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Базовый промпт пресета" /></label>
            {fields.map((field) => <EditableField key={field.name} field={field} value={parameters[field.name]} onChange={(value) => setParameters((current) => ({ ...current, [field.name]: value }))} />)}
            {selected?.ui_schema?.billing_seconds ? <label className="field"><span className="label">{selected.ui_schema.billing_seconds.label || "Длительность"}</span><input className="control" type="number" min={selected.ui_schema.billing_seconds.min || 1} max={selected.ui_schema.billing_seconds.max || 600} value={billingSeconds ?? ""} onChange={(event) => setBillingSeconds(event.target.value ? Number(event.target.value) : null)} /></label> : null}
            {references.length ? <div className="field"><span className="label">Сохранённые референсы</span><div className="transaction-list">{references.map((reference) => <label className="transaction" key={reference.id}><div><strong>{reference.label || reference.original_filename || (reference.kind === "image" ? "Фото" : reference.kind === "video" ? "Видео" : "Аудио")}</strong><small>{reference.kind}</small></div><input type="checkbox" checked={referenceIds.includes(reference.id)} onChange={(event) => setReferenceIds((current) => event.target.checked ? [...new Set([...current, reference.id])].slice(0, 16) : current.filter((id) => id !== reference.id))} /></label>)}</div></div> : null}
            <button className="primary wide" type="button" disabled={busy || !name.trim() || !modelId} onClick={() => void save()}>{busy ? "Сохраняю…" : editingId ? "Сохранить изменения" : "Создать пресет"}</button>
          </div>
        </div>

        <div className="panel tool-panel">
          <div className="section-title"><div><span className="kicker">Библиотека</span><h2>Сохранённые пресеты</h2></div><button type="button" onClick={() => void load()}>Обновить</button></div>
          <div className="transaction-list">{presets.length ? presets.map((preset) => <div className="transaction" key={preset.id}><div><strong>{preset.name}</strong><small>{models.find((item) => item.id === preset.model_id)?.title || preset.model_id} · {dateTime(preset.updated_at)}</small><small>{preset.prompt ? preset.prompt.slice(0, 100) : "Без фиксированного промпта"}</small></div><span style={{ display: "flex", gap: 8 }}><button type="button" onClick={() => edit(preset)}>Изменить</button><button type="button" disabled={busy} onClick={() => void remove(preset.id)}>Удалить</button></span></div>) : <p className="muted">Пресетов пока нет.</p>}</div>
        </div>
      </div>
    </StandaloneShell>
  );
}
