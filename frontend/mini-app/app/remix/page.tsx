"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { api, type FeedRemixDraft, type FeedRemixQuote } from "@/lib/api";
import { haptic, notify } from "@/lib/telegram";
import type { FeedSurface } from "@/lib/types";

type OwnedReference = {
  id: string;
  kind: "image" | "video" | "audio";
  name: string;
  url: string;
};

const EMPTY_REFERENCE_REQUIREMENTS = {
  image_count: 0,
  video_count: 0,
  audio_count: 0,
  required: false,
};

function queryContext(): { source: string; surface: FeedSurface } {
  if (typeof window === "undefined") return { source: "", surface: "feed" };
  const params = new URL(window.location.href).searchParams;
  return {
    source: params.get("source") || "",
    surface: params.get("surface") === "profile" ? "profile" : "feed",
  };
}

function mediaKind(url: string): "image" | "video" | "audio" {
  if (/\.(mp4|mov|webm|m4v)(\?|$)/i.test(url)) return "video";
  if (/\.(mp3|wav|m4a|aac|ogg|flac)(\?|$)/i.test(url)) return "audio";
  return "image";
}

function requirementLabel(kind: OwnedReference["kind"], count: number): string {
  if (kind === "image") return `${count} ${count === 1 ? "своё фото" : "своих фото"}`;
  if (kind === "video") return `${count} ${count === 1 ? "своё видео" : "своих видео"}`;
  return `${count} ${count === 1 ? "свой аудиофайл" : "своих аудиофайла"}`;
}

function returnToFeed(): void {
  if (window.history.length > 1) {
    window.history.back();
    return;
  }
  window.location.assign("/mini-app/");
}

export default function FeedRemixPage() {
  const [draft, setDraft] = useState<FeedRemixDraft | null>(null);
  const [sourceId, setSourceId] = useState("");
  const [surface, setSurface] = useState<FeedSurface>("feed");
  const [prompt, setPrompt] = useState("");
  const [references, setReferences] = useState<OwnedReference[]>([]);
  const [quote, setQuote] = useState<FeedRemixQuote | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState("");
  const quoteSeq = useRef(0);

  useEffect(() => {
    let active = true;
    const load = async () => {
      const query = queryContext();
      setSourceId(query.source);
      setSurface(query.surface);
      if (!query.source) {
        setError("Не удалось определить работу для повтора");
        setLoading(false);
        return;
      }
      try {
        const prepared = await api.prepareRemix(query.source, query.surface);
        if (!active) return;
        setDraft(prepared);
        setSurface(prepared.surface || query.surface);
        setPrompt(prepared.prompt || "");
        setError("");
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "Не удалось подготовить повтор");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, []);

  const counts = useMemo(() => ({
    image: references.filter((item) => item.kind === "image").length,
    video: references.filter((item) => item.kind === "video").length,
    audio: references.filter((item) => item.kind === "audio").length,
  }), [references]);

  const referenceRequirements = draft?.reference_requirements ?? EMPTY_REFERENCE_REQUIREMENTS;

  const requirementsMet = useMemo(() => (
    Boolean(draft)
      && counts.image >= Number(referenceRequirements.image_count || 0)
      && counts.video >= Number(referenceRequirements.video_count || 0)
      && counts.audio >= Number(referenceRequirements.audio_count || 0)
  ), [counts, draft, referenceRequirements]);

  useEffect(() => {
    if (!draft || !sourceId || !requirementsMet || uploading || launching) {
      setQuote(null);
      return;
    }
    const seq = ++quoteSeq.current;
    const timer = window.setTimeout(async () => {
      try {
        const next = await api.quoteRemix(sourceId, {
          surface,
          prompt: draft.prompt_editable ? prompt : null,
          reference_ids: references.map((item) => item.id),
          confirm_own_references: true,
        });
        if (quoteSeq.current === seq) {
          setQuote(next);
          setError("");
        }
      } catch (reason) {
        if (quoteSeq.current === seq) {
          setQuote(null);
          setError(reason instanceof Error ? reason.message : "Не удалось рассчитать стоимость");
        }
      }
    }, 260);
    return () => window.clearTimeout(timer);
  }, [draft, launching, prompt, references, requirementsMet, sourceId, surface, uploading]);

  const upload = async (files: File[], expectedKind?: OwnedReference["kind"]) => {
    if (!files.length || uploading) return;
    setUploading(true);
    setError("");
    try {
      const added: OwnedReference[] = [];
      for (const file of files.slice(0, 12)) {
        const result = await api.upload(file);
        const reference = result.reference;
        if (!reference?.id || !reference.kind) throw new Error("ROXY не сохранила референс. Попробуйте ещё раз.");
        if (expectedKind && reference.kind !== expectedKind) {
          throw new Error(expectedKind === "image" ? "Загрузите изображение" : expectedKind === "video" ? "Загрузите видео" : "Загрузите аудиофайл");
        }
        added.push({
          id: reference.id,
          kind: reference.kind,
          name: result.name || reference.filename || file.name,
          url: result.url,
        });
      }
      setReferences((current) => {
        const ids = new Set(current.map((item) => item.id));
        return [...current, ...added.filter((item) => !ids.has(item.id))];
      });
      notify("success");
      haptic("light");
    } catch (reason) {
      notify("error");
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить референс");
    } finally {
      setUploading(false);
    }
  };

  const launch = async () => {
    if (!draft || !sourceId || !requirementsMet || !quote || launching) return;
    setLaunching(true);
    setError("");
    try {
      const created = await api.launchRemix(sourceId, {
        surface,
        prompt: draft.prompt_editable ? prompt : null,
        reference_ids: references.map((item) => item.id),
        confirm_own_references: true,
      });
      notify("success");
      haptic("medium");
      window.location.assign(`/mini-app/?route=history&generation=${encodeURIComponent(created.id)}`);
    } catch (reason) {
      notify("error");
      setError(reason instanceof Error ? reason.message : "Не удалось запустить повтор");
      setLaunching(false);
    }
  };

  const requiredRows = ([
    ["image", Number(referenceRequirements.image_count || 0), "image/*"],
    ["video", Number(referenceRequirements.video_count || 0), "video/*"],
    ["audio", Number(referenceRequirements.audio_count || 0), "audio/*"],
  ] as const).filter(([, count]) => count > 0);

  const previewUrl = draft?.preview_url || "";
  const previewKind = mediaKind(previewUrl);

  return (
    <StandaloneShell
      kicker="Повтор из ленты"
      title={draft?.model_title || "Своя версия работы"}
      copy="Берём идею и настройки исходной работы, а референсы добавляете вы. Файлы автора в вашу генерацию не переносятся."
    >
      {loading ? <div className="panel tool-panel"><p className="muted">Подготавливаю повтор…</p></div> : null}
      {error ? <div className="action-error" role="alert">{error}</div> : null}

      {draft ? <>
        <div className="panel tool-panel">
          <p className="muted">Повтор запущен не будет автоматически — сначала добавьте свои референсы и подтвердите запуск.</p>
        </div>
        <div className="tool-grid">
          <div className="panel tool-panel">
            {previewUrl && previewKind === "video" ? <video className="trend-preview" src={previewUrl} controls playsInline /> : null}
            {previewUrl && previewKind === "audio" ? <audio src={previewUrl} controls /> : null}
            {previewUrl && previewKind === "image" ? <img className="trend-preview" src={previewUrl} alt="Исходная работа" /> : null}

            <div>
              <span className="kicker">1 · Идея</span>
              {draft.prompt_hidden
                ? <><h2>Промпт автора скрыт</h2><p className="muted">ROXY использует исходный промпт на сервере, но не раскрывает его. Вам остаётся заменить референсы своими.</p></>
                : <label className="field"><span className="label">Описание</span><textarea className="control textarea" value={prompt} onChange={(event) => setPrompt(event.target.value)} maxLength={8000} /></label>}
            </div>

            <div>
              <span className="kicker">2 · Ваши референсы</span>
              <h2>{requiredRows.length ? "Замените референсы автора" : "Добавьте свои референсы"}</h2>
              <p className="muted">В повтор попадут только файлы из вашего аккаунта ROXY. Референсы исходной публикации не копируются.</p>

              {requiredRows.length ? <div className="form-stack">
                {requiredRows.map(([kind, required, accept]) => {
                  const current = counts[kind];
                  return <div className="field" key={kind}>
                    <span className="label">Нужно: {requirementLabel(kind, required)} · добавлено {current}</span>
                    <label className="upload-control">
                      <span>{uploading ? "Загружаю…" : current >= required ? "Добавить ещё" : "Выбрать файлы"}</span>
                      <input type="file" multiple accept={accept} disabled={uploading} onChange={(event) => {
                        const files = Array.from(event.currentTarget.files || []);
                        event.currentTarget.value = "";
                        void upload(files, kind);
                      }} />
                    </label>
                  </div>;
                })}
              </div> : <label className="upload-control">
                <span>{uploading ? "Загружаю…" : "Добавить фото, видео или аудио"}</span>
                <input type="file" multiple accept="image/*,video/*,audio/*" disabled={uploading} onChange={(event) => {
                  const files = Array.from(event.currentTarget.files || []);
                  event.currentTarget.value = "";
                  void upload(files);
                }} />
              </label>}

              {references.length ? <div className="upload-list">
                {references.map((reference) => <button type="button" key={reference.id} onClick={() => setReferences((current) => current.filter((item) => item.id !== reference.id))}>{reference.name} ×</button>)}
              </div> : null}

              {!requirementsMet ? <p className="muted">Сначала добавьте все свои референсы, которые нужны для этой работы.</p> : null}
            </div>
          </div>

          <aside className="panel tool-panel">
            <span className="kicker">3 · Запуск</span>
            <h2>{draft.model_title || "Повтор работы"}</h2>
            <p className="muted">Настройки исходной работы сохранены. ROXY автоматически выберет text/reference режим модели по вашим файлам.</p>
            <div className="quote-box">
              <span>Стоимость</span>
              <strong>{quote?.cost_rox ? `${quote.cost_rox} ROX` : "—"}</strong>
              <small>{quote ? (quote.admin_free ? "Для администратора бесплатно" : "Расчёт готов") : requirementsMet ? "Считаю…" : "Добавьте референсы"}</small>
            </div>
            <button className="primary wide" type="button" disabled={!quote?.cost_rox || !requirementsMet || uploading || launching} onClick={() => void launch()}>{launching ? "Запускаю…" : quote?.cost_rox ? `Повторить · ${quote.cost_rox} ROX` : "Повторить"}</button>
            <button className="secondary wide" type="button" disabled={launching} onClick={returnToFeed}>Вернуться в ленту</button>
          </aside>
        </div>
      </> : null}
    </StandaloneShell>
  );
}
