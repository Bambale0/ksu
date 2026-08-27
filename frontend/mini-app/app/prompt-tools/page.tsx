"use client";

import { useEffect, useMemo, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { api } from "@/lib/api";
import type { PromptToolCatalogItem, PromptToolTask } from "@/lib/types";

type Mode = "image" | "video" | "seedance";
type PromptResult = Record<string, unknown>;

const SEEDANCE_PRICES: Record<5 | 10 | 15, number> = {
  5: 30,
  10: 60,
  15: 90,
};

function initialMode(): Mode {
  if (typeof window === "undefined") return "image";
  const value = new URL(window.location.href).searchParams.get("mode");
  return value === "video" || value === "seedance" ? value : "image";
}

function formatRox(value: number): string {
  return `${value.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ROX`;
}

function price(tool?: PromptToolCatalogItem): string {
  if (!tool) return "—";
  const retail = Number(tool.retail_cost_credits ?? tool.cost_credits ?? 0);
  const effective = Number(tool.cost_credits ?? retail);
  if (tool.admin_free && retail > 0) return `Для вас бесплатно · пользователям ${formatRox(retail)}`;
  if (effective <= 0) return "Бесплатно";
  return formatRox(effective);
}

function promptToolError(reason: unknown, fallback: string): string {
  const raw = reason instanceof Error ? reason.message : typeof reason === "string" ? reason : "";
  if (!raw) return fallback;
  if (/stored provider input|provider media upload|kie_api_key|\/uploads\/refs\/|https?:\/\//i.test(raw)) {
    return "Не удалось обработать файл. Загрузите его ещё раз и повторите.";
  }
  return raw;
}

function resultText(result: PromptResult, ...keys: string[]): string {
  for (const key of keys) {
    const value = result[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function resultList(result: PromptResult, key: string): string[] {
  const value = result[key];
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item || "").trim()).filter(Boolean);
}

async function waitForTask(id: string): Promise<PromptToolTask> {
  for (let attempt = 0; attempt < 90; attempt += 1) {
    const task = await api.promptToolTask(id);
    if (task.status === "succeeded") return task;
    if (task.status === "failed") throw new Error(promptToolError(task.error, "Не удалось подготовить промпт"));
    await new Promise((resolve) => window.setTimeout(resolve, 2000));
  }
  throw new Error("Промпт ещё готовится. Откройте этот инструмент чуть позже.");
}

export default function PromptToolsPage() {
  const [mode, setMode] = useState<Mode>("image");
  const [text, setText] = useState("");
  const [duration, setDuration] = useState<5 | 10 | 15>(5);
  const [imageUrl, setImageUrl] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<PromptResult | null>(null);
  const [tools, setTools] = useState<PromptToolCatalogItem[]>([]);

  useEffect(() => {
    setMode(initialMode());
    void api.promptTools().then((payload) => setTools(payload.items || [])).catch(() => setTools([]));
  }, []);

  const toolById = useMemo(() => new Map(tools.map((item) => [item.id, item])), [tools]);
  const modePrice = mode === "seedance"
    ? formatRox(SEEDANCE_PRICES[duration])
    : mode === "video"
      ? price(toolById.get("video_prompt"))
      : price(
          imageUrl
            ? toolById.get("image_analysis")
            : toolById.get("prompt_builder") || toolById.get("image_analysis"),
        );

  const selectMode = (next: Mode) => {
    setMode(next);
    setError("");
    setResult(null);
    const url = new URL(window.location.href);
    url.searchParams.set("mode", next);
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  };

  const upload = async (file: File, kind: "image" | "video") => {
    if (kind === "video" && file.size > 30 * 1024 * 1024) {
      setError("Видео должно быть до 30 МБ");
      return;
    }
    setUploading(true);
    setError("");
    try {
      const uploaded = await api.upload(file);
      if (kind === "image") setImageUrl(uploaded.url);
      else setVideoUrl(uploaded.url);
    } catch (reason) {
      setError(promptToolError(reason, "Не удалось загрузить файл"));
    } finally {
      setUploading(false);
    }
  };

  const submit = async () => {
    if (busy || uploading) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      let task: PromptToolTask;
      if (mode === "video") {
        if (!videoUrl) throw new Error("Загрузите видео");
        task = await api.buildVideoPrompt({ video_url: videoUrl, instruction: text.trim() });
      } else if (mode === "image" && imageUrl) {
        task = await api.analyzeImagePrompt(imageUrl, text.trim());
      } else {
        if (!text.trim()) throw new Error(mode === "seedance" ? "Опишите сцену" : "Добавьте фото или описание");
        task = await api.buildPrompt({
          text: text.trim(),
          image_url: null,
          purpose: mode === "seedance" ? "seedance" : "image",
          duration_seconds: mode === "seedance" ? duration : null,
        });
      }
      const done = await waitForTask(task.id);
      setResult((done.result || {}) as PromptResult);
    } catch (reason) {
      setError(promptToolError(reason, "Не удалось подготовить промпт"));
    } finally {
      setBusy(false);
    }
  };

  const timeline = result ? resultList(result, "timeline_ru") : [];
  const details = result ? resultList(result, "key_details") : [];
  const resultEntries: Array<[string, string]> = result ? [
    ["Промпт RU", resultText(result, "prompt_ru")],
    ["Промпт EN", resultText(result, "prompt_en")],
    ["Камера", resultText(result, "camera_movement_ru", "camera")],
    ["Динамика", timeline.length ? timeline.map((item) => `• ${item}`).join("\n") : resultText(result, "motion")],
    ["Стиль", resultText(result, "visual_style_ru")],
    ["Звук", resultText(result, "audio_notes_ru")],
    ["Ключевые детали", details.length ? details.map((item) => `• ${item}`).join("\n") : ""],
    ["Рекомендация", resultText(result, "model_hint")],
    ["Что исключить", resultText(result, "negative_prompt")],
    ["Анализ", resultText(result, "summary", "generation_notes")],
  ].filter((item): item is [string, string] => Boolean(item[1])) : [];

  return (
    <StandaloneShell
      kicker="Промпты"
      title="Промпт по фото / видео"
      copy="Загрузите референс, при желании уточните задачу — ROXY разберёт визуал, движение и камеру и соберёт готовый промпт."
    >
      <div className="panel tool-panel">
        <div className="segmented scrollable" aria-label="Режим промпта">
          <button type="button" className={mode === "image" ? "active" : ""} onClick={() => selectMode("image")}>Фото</button>
          <button type="button" className={mode === "video" ? "active" : ""} onClick={() => selectMode("video")}>Видео</button>
          <button type="button" className={mode === "seedance" ? "active" : ""} onClick={() => selectMode("seedance")}>Сценарий</button>
        </div>
        <div className="section-title"><div><span className="kicker">Стоимость</span><h2>{modePrice}</h2></div></div>

        <label className="field">
          <span className="label">{mode === "video" ? "Что важно сохранить" : "Уточнение"}</span>
          <textarea
            className="control textarea"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={mode === "video" ? "Например: особенно точно передай движение камеры и финальный кадр" : "Необязательно: что особенно важно сохранить из фото"}
          />
        </label>

        {mode === "image" ? (
          <label className="upload-control">
            <span>{uploading ? "Загружаю…" : imageUrl ? "Фото загружено · заменить" : "Добавить фото"}</span>
            <input type="file" accept="image/*" onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void upload(file, "image"); }} />
          </label>
        ) : null}

        {mode === "video" ? (
          <label className="upload-control">
            <span>{uploading ? "Загружаю…" : videoUrl ? "Видео загружено · заменить" : "Добавить видео до 30 МБ"}</span>
            <input type="file" accept="video/*" onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void upload(file, "video"); }} />
          </label>
        ) : null}

        {mode === "seedance" ? (
          <div className="field">
            <span className="label">Длительность целевой сцены</span>
            <div className="segmented scrollable">
              {([5, 10, 15] as const).map((seconds) => (
                <button key={seconds} type="button" className={duration === seconds ? "active" : ""} onClick={() => setDuration(seconds)}>{seconds} сек</button>
              ))}
            </div>
          </div>
        ) : null}

        {error ? <div className="action-error" role="alert">{error}</div> : null}
        <button className="primary wide" type="button" disabled={busy || uploading} onClick={() => void submit()}>{busy ? "Анализирую…" : "Создать промпт"}</button>
      </div>

      {resultEntries.length ? (
        <div className="tool-result" aria-live="polite">
          {resultEntries.map(([label, value]) => <div className="tool-result-card" key={label}><strong>{label}</strong><pre>{value}</pre></div>)}
        </div>
      ) : null}
    </StandaloneShell>
  );
}
