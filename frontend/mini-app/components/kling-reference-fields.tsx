"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { assertUploadFileType } from "@/lib/upload-file-types";
import type { UiField } from "@/lib/types";

type Reference = { name?: string; image_urls?: string[]; video_url?: string; audio_url?: string; voice_url?: string; tag?: string; description?: string };
type Props = { field: UiField; value: unknown; onChange: (value: unknown) => void; onBusyChange?: (busy: boolean) => void };
const IMAGE_ACCEPT = ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp";
const VIDEO_ACCEPT = ".mp4,.mov,.qt,.mkv,.avi,.webm,video/mp4,video/quicktime,video/x-matroska,video/x-msvideo,video/webm";
const AUDIO_ACCEPT = ".mp3,.wav,.aac,.m4a,.ogg,audio/*";

export function KlingReferenceFields({ field, value, onChange, onBusyChange }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = useRef(true);
  const uploading = useRef(false);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  let rows: Reference[] = [];
  let parseError = false;
  try {
    const parsed = typeof value === "string" ? JSON.parse(value || "[]") : value || [];
    if (!Array.isArray(parsed) || parsed.some(item => !item || typeof item !== "object")) parseError = true;
    else rows = parsed;
  } catch { parseError = true; }
  const voices = field.editor === "kling_voices";
  const limit = field.max_items || (voices ? 3 : 7);
  function save(next: Reference[]) { onChange(JSON.stringify(next)); }
  function change(index: number, patch: Partial<Reference>) { save(rows.map((row, i) => i === index ? { ...row, ...patch } : row)); }

  async function upload(index: number, key: "image_urls" | "video_url" | "audio_url" | "voice_url", files: File[]) {
    if (!files.length || uploading.current) return;
    const accept = key === "image_urls" ? IMAGE_ACCEPT : key === "video_url" ? VIDEO_ACCEPT : AUDIO_ACCEPT;
    const existing = key === "image_urls" ? rows[index].image_urls || [] : [];
    const max = key === "image_urls" ? 4 : 1;
    try {
      if (existing.length + files.length > max) throw new Error(`Можно выбрать не более ${max} файлов`);
      files.forEach(file => {
        assertUploadFileType(file, accept);
        if ((key === "image_urls" || key === "video_url") && file.size > 10 * 1024 * 1024) throw new Error("Максимум 10 МБ на изображение или видео");
      });
      uploading.current = true;
      setBusy(true);
      setError("");
      onBusyChange?.(true);
      const urls = [...existing];
      for (const file of files) urls.push((await api.upload(file)).url);
      if (active.current) change(index, { [key]: key === "image_urls" ? urls : urls[0] });
    } catch (reason) {
      if (active.current) setError(reason instanceof Error ? reason.message : "Ошибка загрузки");
    } finally {
      if (uploading.current) {
        uploading.current = false;
        onBusyChange?.(false);
      }
      if (active.current) setBusy(false);
    }
  }

  function picker(index: number, key: "image_urls" | "video_url" | "audio_url" | "voice_url", label: string) {
    const row = rows[index];
    const urls = key === "image_urls" ? row.image_urls || [] : row[key] ? [String(row[key])] : [];
    return <div className="field"><label className="upload-control"><span>{label}</span><input aria-label={label} type="file" multiple={key === "image_urls"} disabled={busy} accept={key === "image_urls" ? IMAGE_ACCEPT : key === "video_url" ? VIDEO_ACCEPT : AUDIO_ACCEPT} onChange={event => { const files = Array.from(event.currentTarget.files || []); event.currentTarget.value = ""; void upload(index, key, files); }}/></label>
      <div className="upload-list">{urls.map((url, i) => <button type="button" disabled={busy} key={`${url}-${i}`} aria-label={`Убрать ${label} ${i + 1}`} onClick={() => {
        const next = { ...row };
        if (key === "image_urls") next.image_urls = urls.filter((_, j) => i !== j);
        else delete next[key];
        save(rows.map((item, j) => j === index ? next : item));
      }}>{label} {i + 1} ×</button>)}</div></div>;
  }

  if (parseError) return <label className="field"><span>{field.label}: проверьте сохранённые данные</span><textarea className="control" value={String(value || "")} onChange={event => onChange(event.target.value)}/></label>;
  return <div className="field" data-kling-editor={field.editor} aria-busy={busy}>
    <strong>{field.label}</strong><p className="muted">{voices ? "До 3 голосов. Упоминайте голос в промпте через @имя." : "До 7 персонажей и объектов. Добавьте 2–4 изображения или видео персонажа 3–8 с. Упоминайте через @имя."}</p>
    <fieldset disabled={busy} style={{ border: 0, padding: 0, minWidth: 0 }}>
      {rows.map((row, index) => <div className="panel form-stack" key={index}>
        <label className="field"><span>Имя {voices ? "голоса" : "персонажа"} {index + 1}</span><input className="control" aria-label={`Имя ${voices ? "голоса" : "персонажа"} ${index + 1}`} maxLength={20} pattern="[一-龥A-Za-z0-9_]{1,20}" value={row.name || ""} onChange={event => change(index, { name: event.target.value })}/></label>
        <small>Латинские буквы, цифры, китайские иероглифы и _. Например: @{row.name || "Hero"}</small>
        {voices ? picker(index, "audio_url", `Аудио голоса ${index + 1}`) : <>
          <label className="field"><span>Источник персонажа {index + 1}</span><select className="control" aria-label={`Источник персонажа ${index + 1}`} value={row.video_url !== undefined ? "video" : "images"} onChange={event => {
            const next = { ...row };
            delete next.image_urls; delete next.video_url;
            if (event.target.value === "video") { next.video_url = ""; next.tag = "character"; } else next.image_urls = [];
            save(rows.map((item, i) => i === index ? next : item));
          }}><option value="images">Изображения (2–4)</option><option value="video">Видео (3–8 с)</option></select></label>
          {row.video_url !== undefined ? picker(index, "video_url", `Видео персонажа ${index + 1}`) : picker(index, "image_urls", `Изображения персонажа ${index + 1}`)}
          <label className="field"><span>Категория {index + 1}</span><select className="control" aria-label={`Категория ${index + 1}`} disabled={row.video_url !== undefined} value={row.tag || ""} onChange={event => { const next = { ...row }; if (event.target.value) next.tag = event.target.value; else delete next.tag; if (next.tag && next.tag !== "character") delete next.voice_url; save(rows.map((item, i) => i === index ? next : item)); }}>
            <option value="">Определить автоматически</option><option value="character">Персонаж</option><option value="animal">Животное</option><option value="prop">Предмет</option><option value="costume">Костюм</option><option value="scene">Сцена</option><option value="effect">Эффект</option><option value="others">Другое</option>
          </select></label>
          <label className="field"><span>Описание {index + 1}</span><input className="control" maxLength={100} aria-label={`Описание ${index + 1}`} value={row.description || ""} onChange={event => change(index, { description: event.target.value })}/></label>
          {(!row.tag || row.tag === "character") && picker(index, "voice_url", `Голос персонажа ${index + 1} (необязательно)`)}
        </>}
        <button className="secondary" type="button" onClick={() => save(rows.filter((_, i) => i !== index))}>Удалить {voices ? "голос" : "персонажа"} {index + 1}</button>
      </div>)}
      <button className="secondary" type="button" disabled={rows.length >= limit} onClick={() => save([...rows, voices ? { name: "", audio_url: "" } : { name: "", image_urls: [], tag: "character" }])}>Добавить {voices ? "голос" : "персонажа"}</button>
    </fieldset>
    {busy && <p role="status">Загружаю референс…</p>}{error && <p role="alert">{error}</p>}
  </div>;
}
