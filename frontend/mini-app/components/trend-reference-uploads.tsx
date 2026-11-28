"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { referenceTitle } from "@/lib/trend-references";
import type { TrendReferenceSchema, TrendReferenceSlot } from "@/lib/types";

export function TrendReferenceUploads({ schema, values, onChange, disabled, onBusy }: {
  schema: TrendReferenceSchema; values: Record<string, string>; disabled: boolean;
  onChange: (values: Record<string, string>) => void; onBusy: (busy: boolean) => void;
}) {
  const [busy, setBusy] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [names, setNames] = useState<Record<string, string>>({});
  const customer = schema.slots.filter(slot => slot.source === "user");
  const upload = async (slot: TrendReferenceSlot, file: File) => {
    if (busy || disabled) return;
    if (!file.type.startsWith(`${slot.kind}/`)) {
      setErrors(current => ({ ...current, [slot.id]: slot.kind === "image" ? "Выберите фотографию" : "Выберите видео" }));
      return;
    }
    setBusy(slot.id); onBusy(true);
    setErrors(current => ({ ...current, [slot.id]: "" }));
    try {
      const result = await api.upload(file);
      if (result.reference?.kind !== slot.kind || result.probe_status !== "ready") throw new Error("Не удалось проверить файл. Загрузите его заново.");
      onChange({ ...values, [slot.id]: result.url });
      setNames(current => ({ ...current, [slot.id]: file.name }));
    } catch (reason) {
      setErrors(current => ({ ...current, [slot.id]: reason instanceof Error ? reason.message : "Не удалось загрузить файл. Повторите попытку." }));
    } finally { setBusy(""); onBusy(false); }
  };
  return <section className="trend-named-references" aria-label="Именные референсы">
    <strong>Загрузите референсы</strong>
    <p role="status">{customer.filter(slot => values[slot.id]).length} из {customer.length}</p>
    {schema.mode === "range" ? <p className="muted">Обязательные поля отмечены *. Остальные можно добавлять по порядку.</p> : null}
    {schema.slots.map(slot => <fieldset key={slot.id} disabled={disabled || Boolean(busy)} style={{ minWidth: 0, margin: "12px 0", borderRadius: 12, border: "1px solid #55465f", padding: 12 }}>
      <legend>{referenceTitle(slot)}{slot.required && slot.source === "user" ? " *" : ""}</legend>
      {slot.description ? <p>{slot.description}</p> : null}
      {slot.source === "admin" ? <p className="muted">Уже добавлено администратором</p> : <>
        {values[slot.id] ? <p style={{ overflowWrap: "anywhere" }}>{names[slot.id] || "Файл загружен"}</p> : null}
        <label className="upload-control"><span>{busy === slot.id ? "Загружаю…" : values[slot.id] ? "Заменить" : slot.kind === "image" ? "Выбрать фото" : "Выбрать видео"}</span>
          <input type="file" accept={slot.kind === "image" ? "image/*" : "video/mp4,video/quicktime"} aria-label={`Загрузить ${slot.label}`}
            onChange={event => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; if (file) void upload(slot, file); }} />
        </label>
        {values[slot.id] ? <button className="secondary" type="button" aria-label={`Удалить ${slot.label}`} onClick={() => {
          const next = { ...values }; delete next[slot.id]; onChange(next);
        }}>Удалить</button> : null}
        {errors[slot.id] ? <p role="alert" className="action-error">{errors[slot.id]}</p> : null}
      </>}
    </fieldset>)}
  </section>;
}
