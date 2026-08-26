"use client";

import { useEffect, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { customerRequest, dateTime } from "@/lib/customer-api";
import type { FeedCard } from "@/lib/types";

type Subscription = {
  id: string;
  display_name: string;
  username?: string | null;
  referral_code?: string | null;
  profile_discoverable: boolean;
  subscribed_by_me: boolean;
  subscribed_at?: string;
};

function mediaUrl(item: FeedCard): string {
  return item.preview_url || item.result_url || item.result_urls?.[0] || item.media?.[0]?.url || "";
}

function mediaType(item: FeedCard): "image" | "video" | "audio" {
  const url = mediaUrl(item);
  if (/\.(mp4|mov|webm)(\?|$)/i.test(url)) return "video";
  if (/\.(mp3|wav|m4a|aac|ogg)(\?|$)/i.test(url)) return "audio";
  return "image";
}

export default function SubscriptionsPage() {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [feed, setFeed] = useState<FeedCard[]>([]);
  const [tab, setTab] = useState<"feed" | "authors">("feed");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = async () => {
    setError("");
    try {
      const [authors, cards] = await Promise.all([
        customerRequest<{ items: Subscription[] }>("/api/v1/social/subscriptions?limit=100"),
        customerRequest<{ items: FeedCard[] }>("/api/v1/social/subscriptions/feed?limit=50&offset=0"),
      ]);
      setSubscriptions(authors.items || []);
      setFeed(cards.items || []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить подписки");
    }
  };

  useEffect(() => { void load(); }, []);

  const unsubscribe = async (author: Subscription) => {
    setBusy(author.id); setError("");
    try {
      await customerRequest(`/api/v1/social/profiles/${encodeURIComponent(author.id)}/subscribe`, { method: "DELETE" });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отписаться");
    } finally { setBusy(null); }
  };

  return (
    <StandaloneShell kicker="Сообщество" title="Мои подписки" copy="Работы авторов, на которых вы подписаны, собраны в отдельную ленту.">
      <div className="segmented scrollable">
        <button type="button" className={tab === "feed" ? "active" : ""} onClick={() => setTab("feed")}>Лента</button>
        <button type="button" className={tab === "authors" ? "active" : ""} onClick={() => setTab("authors")}>Авторы · {subscriptions.length}</button>
      </div>
      {error ? <div className="action-error" role="alert">{error}</div> : null}

      {tab === "feed" ? <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">Подписки</span><h2>Новые работы</h2></div><button type="button" onClick={() => void load()}>Обновить</button></div>
        {feed.length ? <div className="media-grid">{feed.map((item) => {
          const url = mediaUrl(item); const type = mediaType(item);
          return <button className="media-tile" type="button" key={item.id} onClick={() => window.location.assign(`/mini-app/?start_payload=${encodeURIComponent(`feed_${item.id}_ref_${item.author?.telegram_id || item.author?.referral_code || "0"}`)}`)}>
            {url && type === "video" ? <video src={url} muted playsInline preload="metadata" /> : null}
            {url && type === "image" ? <img src={url} alt="" loading="lazy" /> : null}
            {type === "audio" || !url ? <span className="media-placeholder">{type === "audio" ? "♫" : "ROXY"}</span> : null}
          </button>;
        })}</div> : <p className="muted">Здесь появятся публикации авторов, на которых вы подпишетесь.</p>}
      </div> : null}

      {tab === "authors" ? <div className="panel tool-panel">
        <div className="transaction-list">{subscriptions.length ? subscriptions.map((author) => <div className="transaction" key={author.id}>
          <div><strong>{author.display_name}</strong><small>{author.username ? `@${author.username}` : "Профиль скрыт"}{author.subscribed_at ? ` · ${dateTime(author.subscribed_at)}` : ""}</small></div>
          <span style={{ display: "flex", gap: 8 }}>
            {author.referral_code ? <button type="button" onClick={() => window.location.assign(`/mini-app/?start_payload=${encodeURIComponent(`profile_${author.referral_code}`)}`)}>Профиль</button> : null}
            <button type="button" disabled={busy === author.id} onClick={() => void unsubscribe(author)}>{busy === author.id ? "…" : "Отписаться"}</button>
          </span>
        </div>) : <p className="muted">Вы пока ни на кого не подписаны.</p>}</div>
      </div> : null}
    </StandaloneShell>
  );
}
