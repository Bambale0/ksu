"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "@/lib/api";
import type { TrendItem } from "@/lib/types";

type Host = { textarea: HTMLTextAreaElement; host: HTMLElement; kind: StructuredKind };
type StructuredKind = "multi_prompt" | "kling_elements" | "video_list" | "audio_ids" | "character_ids";

type Shot = { prompt: string; duration: number };
type KlingElement = {
  name: string;
  description?: string;
  element_input_urls: string[];
  element_input_audio_urls?: string[];
  start_time?: number;
  end_time?: number;
};
type VideoRef = { url: string; start?: number; ends?: number };

const STRUCTURED_LABELS: Record<string, StructuredKind> = {
  "Кадры по сценам": "multi_prompt",
  "Element references": "kling_elements",
  "Видео-референс": "video_list",
  "Gemini Omni audio IDs": "audio_ids",
  "Character IDs": "character_ids",
};

function setNativeTextareaValue(textarea: HTMLTextAreaElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
  setter?.call(textarea, value);
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
  textarea.dispatchEvent(new Event("change", { bubbles: true }));
}

function parseJson<T>(value: string, fallback: T): T {
  if (!value.trim()) return fallback;
  try {
    const parsed = JSON.parse(value);
    return parsed as T;
  } catch {
    return fallback;
  }
}

function StructuredEditor({ textarea, kind }: { textarea: HTMLTextAreaElement; kind: StructuredKind }) {
  const [value, setValue] = useState(() => textarea.value || "[]");
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    const sync = () => setValue(textarea.value || "[]");
    textarea.addEventListener("input", sync);
    return () => textarea.removeEventListener("input", sync);
  }, [textarea]);

  const commit = (next: unknown) => {
    const serialized = JSON.stringify(next);
    setValue(serialized);
    setNativeTextareaValue(textarea, serialized);
  };

  if (kind === "audio_ids" || kind === "character_ids") {
    const items = parseJson<string[]>(value, []).filter((item) => typeof item === "string");
    return <div className="structured-editor" data-structured-kind={kind}>
      <p className="muted">Добавляйте ID по одному. ROXY соберёт массив автоматически.</p>
      {items.map((item, index) => <div className="structured-row-grid" key={`${item}-${index}`}>
        <input className="control" value={item} placeholder={kind === "audio_ids" ? "audio_id" : "character_id"} onChange={(event) => commit(items.map((current, i) => i === index ? event.target.value : current))}/>
        <button className="secondary" type="button" onClick={() => commit(items.filter((_, i) => i !== index))}>Удалить</button>
      </div>)}
      <button className="secondary wide" type="button" onClick={() => commit([...items, ""])}>+ Добавить ID</button>
    </div>;
  }

  if (kind === "multi_prompt") {
    const shots = parseJson<Shot[]>(value, []).filter((item) => item && typeof item === "object");
    return <div className="structured-editor" data-structured-kind={kind}>
      <p className="muted">Опишите каждый кадр и задайте длительность. Общая сумма должна совпадать с длиной видео.</p>
      {shots.map((shot, index) => <div className="structured-row" key={index}>
        <textarea className="control textarea" value={shot.prompt || ""} placeholder={`Сцена ${index + 1}`} onChange={(event) => commit(shots.map((current, i) => i === index ? { ...current, prompt: event.target.value } : current))}/>
        <div className="structured-row-grid">
          <input className="control" type="number" min={1} max={12} value={shot.duration || 1} onChange={(event) => commit(shots.map((current, i) => i === index ? { ...current, duration: Number(event.target.value) || 1 } : current))}/>
          <button className="secondary" type="button" onClick={() => commit(shots.filter((_, i) => i !== index))}>Удалить</button>
        </div>
      </div>)}
      <button className="secondary wide" type="button" onClick={() => commit([...shots, { prompt: "", duration: 3 }])}>+ Добавить сцену</button>
    </div>;
  }

  if (kind === "video_list") {
    const videos = parseJson<VideoRef[]>(value, []).filter((item) => item && typeof item === "object");
    const uploadVideo = async (file: File, index: number) => {
      setUploading(true);
      try {
        const uploaded = await api.upload(file);
        commit(videos.map((current, i) => i === index ? { ...current, url: uploaded.url } : current));
      } finally { setUploading(false); }
    };
    return <div className="structured-editor" data-structured-kind={kind}>
      <p className="muted">Загрузите одно видео и укажите нужный фрагмент.</p>
      {videos.map((video, index) => <div className="structured-row" key={index}>
        <input className="control" value={video.url || ""} placeholder="https://..." onChange={(event) => commit(videos.map((current, i) => i === index ? { ...current, url: event.target.value } : current))}/>
        <label className="upload-control"><span>{uploading ? "Загружаю…" : "Загрузить видео"}</span><input type="file" accept="video/*" disabled={uploading} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void uploadVideo(file, index); }}/></label>
        <div className="structured-row-grid">
          <input className="control" type="number" min={0} step="0.1" placeholder="Начало, сек" value={video.start ?? ""} onChange={(event) => commit(videos.map((current, i) => i === index ? { ...current, start: event.target.value === "" ? undefined : Number(event.target.value) } : current))}/>
          <input className="control" type="number" min={0} step="0.1" placeholder="Конец, сек" value={video.ends ?? ""} onChange={(event) => commit(videos.map((current, i) => i === index ? { ...current, ends: event.target.value === "" ? undefined : Number(event.target.value) } : current))}/>
        </div>
        <button className="secondary wide" type="button" onClick={() => commit(videos.filter((_, i) => i !== index))}>Удалить видео</button>
      </div>)}
      {!videos.length ? <button className="secondary wide" type="button" onClick={() => commit([{ url: "" }])}>+ Добавить видео</button> : null}
    </div>;
  }

  const elements = parseJson<KlingElement[]>(value, []).filter((item) => item && typeof item === "object");
  const updateElement = (index: number, patch: Partial<KlingElement>) => commit(elements.map((item, i) => i === index ? { ...item, ...patch } : item));
  const uploadElement = async (file: File, index: number, audio = false) => {
    setUploading(true);
    try {
      const uploaded = await api.upload(file);
      const current = elements[index];
      if (audio) updateElement(index, { element_input_audio_urls: [uploaded.url] });
      else updateElement(index, { element_input_urls: [...(current.element_input_urls || []), uploaded.url].slice(0, 4) });
    } finally { setUploading(false); }
  };
  return <div className="structured-editor" data-structured-kind={kind}>
    <p className="muted">До 3 элементов. Для каждого: одно видео или 2–4 изображения; дополнительно можно прикрепить одно аудио.</p>
    {elements.map((element, index) => <div className="structured-row" key={index}>
      <input className="control" value={element.name || ""} placeholder="Имя элемента" onChange={(event) => updateElement(index, { name: event.target.value })}/>
      <textarea className="control textarea" value={element.description || ""} placeholder="Описание элемента" onChange={(event) => updateElement(index, { description: event.target.value })}/>
      <div className="tool-file-list">{(element.element_input_urls || []).map((url, refIndex) => <div className="tool-file-chip" key={`${url}-${refIndex}`}><span>Референс {refIndex + 1}</span><button type="button" onClick={() => updateElement(index, { element_input_urls: element.element_input_urls.filter((_, i) => i !== refIndex) })}>×</button></div>)}</div>
      <label className="upload-control"><span>{uploading ? "Загружаю…" : "Добавить фото / видео"}</span><input type="file" accept="image/*,video/*" disabled={uploading || (element.element_input_urls || []).length >= 4} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void uploadElement(file, index); }}/></label>
      <label className="upload-control"><span>{element.element_input_audio_urls?.length ? "Заменить аудио" : "Добавить аудио"}</span><input type="file" accept="audio/*" disabled={uploading} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void uploadElement(file, index, true); }}/></label>
      {(element.element_input_audio_urls || []).length ? <div className="tool-file-chip"><span>Аудио добавлено</span><button type="button" onClick={() => updateElement(index, { element_input_audio_urls: [] })}>×</button></div> : null}
      {(element.element_input_urls || []).length === 1 ? <div className="structured-row-grid">
        <input className="control" type="number" min={0} step={100} placeholder="Начало, мс" value={element.start_time ?? ""} onChange={(event) => updateElement(index, { start_time: event.target.value === "" ? undefined : Number(event.target.value) })}/>
        <input className="control" type="number" min={0} step={100} placeholder="Конец, мс" value={element.end_time ?? ""} onChange={(event) => updateElement(index, { end_time: event.target.value === "" ? undefined : Number(event.target.value) })}/>
      </div> : null}
      <button className="secondary wide" type="button" onClick={() => commit(elements.filter((_, i) => i !== index))}>Удалить элемент</button>
    </div>)}
    {elements.length < 3 ? <button className="secondary wide" type="button" onClick={() => commit([...elements, { name: "", description: "", element_input_urls: [] }])}>+ Добавить элемент</button> : null}
  </div>;
}

function trendCardContext(card: HTMLElement): boolean {
  if (card.closest(".home-screen")) return true;
  const screen = card.closest<HTMLElement>(".screen");
  if (!screen) return false;
  const kicker = screen.querySelector<HTMLElement>(".screen-head .kicker")?.textContent?.trim();
  if (kicker !== "Каталог") return false;
  const grids = Array.from(screen.querySelectorAll<HTMLElement>(".model-grid"));
  const index = grids.findIndex((grid) => grid.contains(card));
  return index === 0;
}

export function GlobalUxEnhancers() {
  const [trends, setTrends] = useState<TrendItem[]>([]);
  const [hosts, setHosts] = useState<Host[]>([]);
  const trendByTitle = useMemo(() => new Map(trends.map((trend) => [trend.title.trim(), trend])), [trends]);

  useEffect(() => {
    void api.trends().then((payload) => setTrends(payload.items || [])).catch(() => setTrends([]));
  }, []);

  useEffect(() => {
    const scan = () => {
      const next: Host[] = [];
      for (const field of Array.from(document.querySelectorAll<HTMLElement>(".field"))) {
        const label = field.querySelector<HTMLElement>(".label")?.textContent?.replace(/\s+\*$/, "").trim() || "";
        const kind = STRUCTURED_LABELS[label];
        if (!kind) continue;
        const textarea = field.querySelector<HTMLTextAreaElement>("textarea.control");
        if (!textarea) continue;
        textarea.classList.add("structured-json-source");
        let host = field.querySelector<HTMLElement>(":scope > [data-structured-editor-host]");
        if (!host) {
          host = document.createElement("div");
          host.dataset.structuredEditorHost = kind;
          textarea.insertAdjacentElement("afterend", host);
        }
        next.push({ textarea, host, kind });
      }
      setHosts((current) => {
        if (current.length === next.length && current.every((item, index) => item.textarea === next[index]?.textarea && item.host === next[index]?.host && item.kind === next[index]?.kind)) return current;
        return next;
      });
    };
    scan();
    const observer = new MutationObserver(scan);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!trendByTitle.size) return;
    const decorate = () => {
      for (const card of Array.from(document.querySelectorAll<HTMLElement>(".model-card"))) {
        if (!trendCardContext(card)) continue;
        const title = card.querySelector("strong")?.textContent?.trim() || "";
        const trend = trendByTitle.get(title);
        if (!trend) continue;
        card.dataset.trendLaunch = "true";
        card.dataset.trendId = trend.id;
        if (card.tagName !== "BUTTON" && card.tagName !== "A") {
          card.setAttribute("role", "button");
          card.tabIndex = 0;
        }
      }
    };
    decorate();
    const observer = new MutationObserver(decorate);
    observer.observe(document.body, { childList: true, subtree: true });
    const open = (target: EventTarget | null) => {
      const element = target instanceof Element ? target.closest<HTMLElement>("[data-trend-launch='true']") : null;
      const id = element?.dataset.trendId;
      if (!id) return false;
      window.location.assign(`/mini-app/trend/?id=${encodeURIComponent(id)}`);
      return true;
    };
    const click = (event: MouseEvent) => {
      if (!open(event.target)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
    };
    const keydown = (event: KeyboardEvent) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      if (!open(event.target)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
    };
    document.addEventListener("click", click, true);
    document.addEventListener("keydown", keydown, true);
    return () => {
      observer.disconnect();
      document.removeEventListener("click", click, true);
      document.removeEventListener("keydown", keydown, true);
    };
  }, [trendByTitle]);

  return <>{hosts.map((item) => createPortal(<StructuredEditor textarea={item.textarea} kind={item.kind} />, item.host, `${item.kind}:${item.host.dataset.structuredEditorHost || "host"}`))}</>;
}
