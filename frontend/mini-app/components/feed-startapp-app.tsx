"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { FeedCard } from "@/lib/types";
import { Icon } from "./icons";
import { StandaloneShell } from "./standalone-shell";

function asset(card: FeedCard): { url: string; type: "image" | "video" | "audio" } {
  const url = card.preview_url || card.result_url || card.result_urls?.[0] || card.media?.[0]?.url || "";
  const contentType = String(card.media?.[0]?.content_type || "").toLowerCase();
  if (contentType.startsWith("video/") || /\.(mp4|mov|webm)(\?|$)/i.test(url)) return { url, type: "video" };
  if (contentType.startsWith("audio/") || /\.(mp3|wav|m4a|aac|ogg)(\?|$)/i.test(url)) return { url, type: "audio" };
  return { url, type: "image" };
}

export function FeedStartApp({ generationId, referralCode }: { generationId: string; referralCode: string }) {
  const [card, setCard] = useState<FeedCard | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    void api.feedItem(generationId, "feed")
      .then((value) => active && setCard(value))
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "Не удалось открыть работу"));
    return () => { active = false; };
  }, [generationId]);

  const media = card ? asset(card) : { url: "", type: "image" as const };
  const authorCode = String(card?.author_referral_code || card?.author?.telegram_id || "");
  const validReferral = Boolean(card && authorCode === referralCode);
  const author = card?.author?.display_name || card?.author?.username || "Автор ROXY";
  const model = String(card?.model || "ROXY");

  const repeat = async () => {
    if (!card || !validReferral || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.remix(card.id, "feed");
      window.location.assign(`/mini-app/?route=history&generation=${encodeURIComponent(result.id)}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось повторить работу");
      setBusy(false);
    }
  };

  const copyLink = async () => {
    if (!card || !validReferral) return;
    try {
      const result = await api.share(card.id, "feed");
      if (!result.link) throw new Error("Ссылка недоступна");
      await navigator.clipboard.writeText(result.link);
      setNotice("Реферальная ссылка скопирована");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось скопировать ссылку");
    }
  };

  return (
    <StandaloneShell kicker="Лента ROXY" title={model} copy="Публичная работа автора ROXY">
      <div className="tool-grid">
        <div className="panel tool-panel">
          {media.url && media.type === "video" ? <video className="trend-preview" src={media.url} controls playsInline /> : null}
          {media.url && media.type === "audio" ? <audio src={media.url} controls /> : null}
          {media.url && media.type === "image" ? <img className="trend-preview" src={media.url} alt="Работа из ленты ROXY" /> : null}
          {card ? <p className="muted" data-feed-startapp-author>Автор: <strong>{author}</strong></p> : null}
          {card?.prompt && !card.prompt_hidden ? <p className="prompt-copy">{card.prompt}</p> : null}
          {card && !validReferral ? <div className="action-error" role="alert">Реферальная подпись не совпадает с автором работы.</div> : null}
          {error ? <div className="action-error" role="alert">{error}</div> : null}
          {notice ? <div role="status">{notice}</div> : null}
          {!card && !error ? <p className="muted">Открываю работу…</p> : null}
          <div className="tool-actions">
            {card?.prompt_actions_allowed !== false && card ? <button className="primary" type="button" disabled={!validReferral || busy} onClick={() => void repeat()}><Icon name="create" size={16} />{busy ? "Запускаю…" : "Повторить"}</button> : null}
            {card ? <button className="secondary" type="button" disabled={!validReferral} onClick={() => void copyLink()}><Icon name="share" size={16} />Скопировать ссылку</button> : null}
            <button className="secondary" type="button" onClick={() => window.location.assign("/mini-app/?route=feed")}>Открыть всю ленту</button>
          </div>
        </div>
      </div>
    </StandaloneShell>
  );
}
