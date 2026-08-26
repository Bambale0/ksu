"use client";

import { useEffect, useState } from "react";
import {
  copyToClipboard,
  haptic,
  initTelegram,
  notify,
  openTelegramShare,
  telegramHeaders,
} from "@/lib/telegram";
import { GenerationActionGate } from "./generation-action-app";

type PublishRoute = { generationId: string };
type PublishContext = {
  generation: {
    id: string;
    status: string;
    media_type: string;
    result_url?: string | null;
    model_title?: string;
  };
  source_url?: string | null;
};
type SharePayload = {
  link?: string | null;
  share_url?: string | null;
  share_text?: string;
  copy_link?: string | null;
};

function parsePublishRoute(): PublishRoute | null {
  if (typeof window === "undefined") return null;
  const url = new URL(window.location.href);
  if (url.searchParams.get("route") !== "generation-action") return null;
  if (url.searchParams.get("action") !== "publish") return null;
  const generationId = url.searchParams.get("generation") || "";
  return generationId ? { generationId } : null;
}

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
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail ?? payload?.message ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload as T;
}

function goToGeneration(generationId: string) {
  const url = new URL(window.location.href);
  url.searchParams.set("route", "history");
  url.searchParams.set("generation", generationId);
  url.searchParams.delete("action");
  url.searchParams.delete("action_context_id");
  window.location.assign(`${url.pathname}${url.search}${url.hash}`);
}

function mediaType(context: PublishContext): string {
  if (context.generation.media_type) return context.generation.media_type;
  const url = context.source_url || context.generation.result_url || "";
  if (/\.(mp4|mov|webm)(\?|$)/i.test(url)) return "video";
  if (/\.(mp3|wav|m4a|aac|ogg)(\?|$)/i.test(url)) return "audio";
  return "image";
}

export function PublishModerationGate() {
  const [ready, setReady] = useState(false);
  const [route, setRoute] = useState<PublishRoute | null>(null);

  useEffect(() => {
    const sync = () => {
      setRoute(parsePublishRoute());
      setReady(true);
    };
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  if (!ready) return <div className="splash" role="status"><strong>ROXY</strong><small>Открываю публикацию…</small></div>;
  if (!route) return <GenerationActionGate />;
  return <PublishModerationScreen generationId={route.generationId} />;
}

function PublishModerationScreen({ generationId }: { generationId: string }) {
  const [context, setContext] = useState<PublishContext | null>(null);
  const [scope, setScope] = useState<"profile" | "feed">("feed");
  const [promptVisible, setPromptVisible] = useState(false);
  const [adultContent, setAdultContent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [share, setShare] = useState<SharePayload | null>(null);
  const [pending, setPending] = useState(false);
  const [removed, setRemoved] = useState(false);

  useEffect(() => {
    const tg = initTelegram();
    tg?.ready?.();
    tg?.expand?.();
    const back = () => goToGeneration(generationId);
    tg?.BackButton?.show?.();
    tg?.BackButton?.onClick?.(back);
    return () => tg?.BackButton?.offClick?.(back);
  }, [generationId]);

  useEffect(() => {
    let active = true;
    request<PublishContext>(`/api/v1/generations/${encodeURIComponent(generationId)}/action-context?action=publish`)
      .then((value) => active && setContext(value))
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "Не удалось открыть публикацию"));
    return () => { active = false; };
  }, [generationId]);

  const publish = async () => {
    if (!context || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      if (scope === "feed" && adultContent) {
        const result = await request<{ moderation_state?: string; pending_moderation?: boolean }>(`/api/v1/feed/${encodeURIComponent(generationId)}/publish-adult`, {
          method: "POST",
          body: JSON.stringify({ prompt_visible: promptVisible, references_visible: false }),
        });
        notify("success");
        haptic("medium");
        if (result.moderation_state === "removed") {
          setRemoved(true);
          return;
        }
        setPending(result.pending_moderation !== false);
        return;
      }

      const result = await request<{ share?: SharePayload }>(`/api/v1/feed/${encodeURIComponent(generationId)}/publish`, {
        method: "POST",
        body: JSON.stringify({ publication_scope: scope, prompt_visible: promptVisible, references_visible: false }),
      });
      notify("success");
      haptic("medium");
      setShare(result.share || {});
    } catch (reason) {
      notify("error");
      setError(reason instanceof Error ? reason.message : "Не удалось опубликовать");
    } finally {
      setSubmitting(false);
    }
  };

  if (pending) {
    return <StatusCard title="На модерации" copy="После проверки работа появится в ленте. Мы сохранили исходник на стороне ROXY." generationId={generationId} />;
  }
  if (removed) {
    return <StatusCard title="Работа скрыта" copy="Эта публикация уже была снята с публичной ленты модератором." generationId={generationId} />;
  }
  if (share) return <PublishSuccess share={share} generationId={generationId} scope={scope} />;
  if (!context && !error) return <div className="splash" role="status"><strong>ROXY</strong><small>Готовлю публикацию…</small></div>;
  if (!context) return <StatusCard title="Публикация недоступна" copy={error || "Не удалось открыть работу"} generationId={generationId} />;

  const source = context.source_url || context.generation.result_url || "";
  const type = mediaType(context);

  return <div className="roxy-app generation-action-app moderation-publish-app">
    <header className="topbar action-topbar">
      <button className="brand" type="button" onClick={() => goToGeneration(generationId)} aria-label="Вернуться к работе"><span className="action-back">‹</span><span className="brand-copy"><strong>ROXY</strong><small>Опубликовать</small></span></button>
    </header>
    <main className="main-shell"><section className="screen generation-action-screen">
      <div className="action-source panel">
        <div className="action-source-media">{source && type === "video" ? <video src={source} controls playsInline /> : source && type === "audio" ? <audio src={source} controls /> : source ? <img src={source} alt="Исходная генерация" /> : null}</div>
        <div><span className="kicker">Готовая работа</span><h1>{context.generation.model_title || "ROXY generation"}</h1><p className="muted">Перед публикацией выберите, где работа будет видна.</p></div>
      </div>
      <div className="action-grid">
        <div className="panel">
          <span className="kicker">Публикация</span><h2>Куда опубликовать?</h2>
          <div className="segmented"><button type="button" className={scope === "profile" ? "active" : ""} onClick={() => setScope("profile")}>В профиль</button><button type="button" className={scope === "feed" ? "active" : ""} onClick={() => setScope("feed")}>Лента + профиль</button></div>
          <label className="toggle-row"><span><strong>Показать промпт</strong><small>По умолчанию промпт скрыт</small></span><input type="checkbox" checked={promptVisible} onChange={(event) => setPromptVisible(event.target.checked)}/><i/></label>
          {scope === "feed" && <label className="toggle-row adult-publish-toggle"><span><strong>Пометить как 18+</strong><small>Такая работа сначала пройдёт модерацию</small></span><input type="checkbox" checked={adultContent} onChange={(event) => setAdultContent(event.target.checked)}/><i/></label>}
          <p className="muted">Референсы остаются скрытыми.</p>
        </div>
        <aside className="panel create-summary"><span className="kicker">Готово</span><h2>{scope === "feed" ? adultContent ? "Сначала модерация" : "Публичная лента" : "Профиль"}</h2><button className="primary wide" type="button" disabled={submitting} onClick={() => void publish()}>{submitting ? "Публикую…" : adultContent && scope === "feed" ? "Отправить на модерацию" : "Опубликовать"}</button></aside>
      </div>
      {error && <div className="action-error" role="alert">{error}</div>}
    </section></main>
  </div>;
}

function StatusCard({ title, copy, generationId }: { title: string; copy: string; generationId: string }) {
  return <div className="roxy-app publish-success"><main className="main-shell"><section className="screen"><div className="panel publish-success-card" role="status"><span className="publish-success-badge">18+</span><h1>{title}</h1><p className="muted">{copy}</p><button className="primary wide" type="button" onClick={() => goToGeneration(generationId)}>Вернуться к работе</button></div></section></main></div>;
}

function PublishSuccess({ share, generationId, scope }: { share: SharePayload; generationId: string; scope: "profile" | "feed" }) {
  const [copied, setCopied] = useState(false);
  const link = share.link || share.copy_link || "";
  const copy = async () => {
    if (!link) return;
    const ok = await copyToClipboard(link);
    notify(ok ? "success" : "error");
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2200);
    }
  };
  const sharePost = () => {
    if (share.share_url) return openTelegramShare(share.share_url);
    if (link) openTelegramShare(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(share.share_text || "Посмотри мою работу в ROXY ✨")}`);
  };
  return <div className="roxy-app publish-success"><main className="main-shell"><section className="screen"><div className="panel publish-success-card" role="status"><span className="publish-success-badge">🎉</span><h1>Работа опубликована!</h1><p className="muted">{scope === "feed" ? "Теперь она доступна в ленте и профиле." : "Теперь она доступна в вашем профиле."}</p><div className="publish-success-actions">{scope === "feed" && <button className="primary wide" type="button" disabled={!share.share_url && !link} onClick={sharePost}>Поделиться ссылкой</button>}<button className="secondary wide" type="button" disabled={!link} onClick={() => void copy()}>{copied ? "Ссылка скопирована ✓" : "Скопировать ссылку"}</button></div><button className="publish-success-back" type="button" onClick={() => goToGeneration(generationId)}>Вернуться к работе</button></div></section></main></div>;
}
