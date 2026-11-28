"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { extractReferenceSlots, referenceTitle } from "@/lib/trend-references";
import type { TrendReferenceSchema, TrendReferenceSlot } from "@/lib/types";

function renumber(slots: TrendReferenceSlot[]): TrendReferenceSlot[] {
  const indexes = { image: 0, video: 0 };
  return slots.map((slot, order) => ({ ...slot, id: `${slot.kind}_${++indexes[slot.kind]}`, order }));
}

export function TrendReferenceEditor({ value, prompt, templateVideoUrl, onChange, onBusy, disabled }: {
  value?: TrendReferenceSchema; prompt: string; templateVideoUrl: string;
  onChange: (schema: TrendReferenceSchema | undefined) => void;
  onBusy: (busy: boolean) => void; disabled: boolean;
}) {
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  let suggestions: TrendReferenceSlot[] = [];
  let discoveryError = "";
  try { suggestions = extractReferenceSlots(prompt); } catch (reason) { discoveryError = (reason as Error).message; }
  const missing = suggestions.filter(s => !value?.slots.some(slot => slot.id === s.id));
  const update = (index: number, patch: Partial<TrendReferenceSlot>) => {
    if (value) onChange({ ...value, slots: renumber(value.slots.map((slot, i) => i === index ? { ...slot, ...patch } : slot)) });
  };
  const upload = async (index: number, file: File) => {
    if (!value || uploading || disabled) return;
    const slot = value.slots[index];
    setUploading(true); onBusy(true); setError("");
    try {
      const result = await api.upload(file, slot.kind === "image" ? "template-image" : "template-video");
      if (!active.current) return;
      if (result.reference?.kind !== slot.kind || result.probe_status !== "ready") throw new Error("Не удалось проверить референс. Повторите загрузку.");
      update(index, { url: result.url });
    } catch (reason) { if (active.current) setError(reason instanceof Error ? reason.message : "Не удалось загрузить референс"); }
    finally { if (active.current) { setUploading(false); onBusy(false); } }
  };
  return <section className="inline-trend-user-fields-admin" aria-label="Настройка именных референсов">
    <strong>Именные референсы</strong>
    <small>Для каждого фото или видео задайте роль. Ссылки Image1, @image_1 и @Video1 распознаются автоматически. Изменения применяются после подтверждения и сохранения.</small>
    {discoveryError ? <p role="alert">{discoveryError}</p> : null}
    {missing.length ? <div><strong>Найдены референсы в промпте</strong><p>{suggestions.map(referenceTitle).join(", ")}</p>
      <button className="inline-trend-secondary" type="button" disabled={disabled || uploading} onClick={() => {
        const slots = renumber([...value?.slots || [], ...missing].sort((a, b) => a.kind.localeCompare(b.kind) || Number(a.id.split("_")[1]) - Number(b.id.split("_")[1])));
        onChange({ mode: value?.mode || "strict", slots: slots.map(slot => slot.kind === "video" && templateVideoUrl ? { ...slot, source: "admin", url: templateVideoUrl } : slot) });
      }}>Подтвердить референсы из промпта</button>
    </div> : null}
    {!value ? <button className="inline-trend-secondary" type="button" disabled={disabled || uploading} onClick={() => onChange({ mode: "strict", slots: [{ id: "image_1", label: "Ваше фото", description: "", kind: "image", source: "user", order: 0, required: true }] })}>Настроить референсы вручную</button> : <>
      <label><span>Режим референсов</span><select value={value.mode} disabled={disabled || uploading} onChange={event => {
        const mode = event.target.value as "strict" | "range";
        onChange({ mode, slots: value.slots.map(slot => ({ ...slot, required: mode === "strict" || slot.source === "admin" ? true : slot.required })) });
      }}><option value="strict">Строго заданный набор</option><option value="range">Диапазон: обязательные и дополнительные</option></select></label>
      <small>Необязательными могут быть только последние референсы каждого типа без ссылок в промпте.</small>
      {value.slots.map((slot, index) => <fieldset className="inline-trend-workflow-input" key={`${index}:${slot.kind}`} disabled={disabled || uploading}>
        <legend>{referenceTitle(slot)}</legend>
        <label><span>Название референса {index + 1}</span><input value={slot.label} maxLength={64} onChange={e => update(index, { label: e.target.value })} required /></label>
        <label><span>Описание референса {index + 1}</span><textarea value={slot.description} maxLength={240} rows={2} onChange={e => update(index, { description: e.target.value })} /></label>
        <label><span>Тип референса {index + 1}</span><select value={slot.kind} onChange={e => update(index, { kind: e.target.value as "image" | "video", url: undefined })}><option value="image">Фото</option><option value="video">Видео</option></select></label>
        <label><span>Источник референса {index + 1}</span><select value={slot.source} onChange={e => update(index, { source: e.target.value as "user" | "admin", url: undefined, required: true })}><option value="user">Загружает пользователь</option><option value="admin">Заранее задан администратором</option></select></label>
        <label className="inline-trend-checkbox"><input type="checkbox" checked={slot.required} disabled={value.mode === "strict" || slot.source === "admin"} onChange={e => update(index, { required: e.target.checked })} /><span>Обязательный референс {index + 1}</span></label>
        {slot.source === "admin" ? <>
          <label><span>{slot.url ? "Заменить постоянный референс" : "Загрузить постоянный референс"} {index + 1}</span><input type="file" accept={slot.kind === "image" ? "image/*" : "video/mp4,video/quicktime"} onChange={e => { const file = e.currentTarget.files?.[0]; e.currentTarget.value = ""; if (file) void upload(index, file); }} /></label>
          {slot.url ? slot.kind === "image" ? <img src={slot.url} alt={slot.label} style={{ maxWidth: "100%", maxHeight: 160 }} /> : <video src={slot.url} controls preload="metadata" style={{ maxWidth: "100%", maxHeight: 160 }} /> : null}
        </> : null}
        <div className="inline-trend-field-presets">
          <button className="inline-trend-secondary" type="button" disabled={index === 0} onClick={() => { const slots = [...value.slots]; [slots[index - 1], slots[index]] = [slots[index], slots[index - 1]]; onChange({ ...value, slots: renumber(slots) }); }}>Выше</button>
          <button className="inline-trend-secondary" type="button" disabled={index === value.slots.length - 1} onClick={() => { const slots = [...value.slots]; [slots[index], slots[index + 1]] = [slots[index + 1], slots[index]]; onChange({ ...value, slots: renumber(slots) }); }}>Ниже</button>
          <button className="inline-trend-secondary" type="button" disabled={value.slots.length === 1} onClick={() => onChange({ ...value, slots: renumber(value.slots.filter((_, i) => i !== index)) })}>Удалить референс</button>
        </div>
      </fieldset>)}
      <button className="inline-trend-secondary" type="button" disabled={disabled || uploading || value.slots.length >= 16} onClick={() => onChange({ ...value, slots: renumber([...value.slots, { id: "", label: "Новое фото", description: "", kind: "image", source: "user", order: value.slots.length, required: value.mode === "strict" }]) })}>Добавить референс</button>
      <button className="inline-trend-secondary" type="button" disabled={disabled || uploading} onClick={() => onChange(undefined)}>Использовать общий список загрузок</button>
    </>}
    {uploading ? <p role="status">Сохраняю постоянный референс…</p> : null}
    {error ? <p role="alert">{error}</p> : null}
  </section>;
}
