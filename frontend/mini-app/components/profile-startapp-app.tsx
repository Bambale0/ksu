"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { customerRequest } from "@/lib/customer-api";
import type { FeedCard } from "@/lib/types";
import { Icon } from "./icons";
import { StandaloneShell } from "./standalone-shell";

type PublicAuthor = {
  id?: string;
  telegram_id?: number;
  username?: string | null;
  display_name?: string;
  referral_code?: string;
};
type SocialProfile = PublicAuthor & {
  profile_discoverable?: boolean;
  is_self?: boolean;
  subscribed_by_me?: boolean;
  follower_count?: number;
};

function media(card: FeedCard): { url: string; type: "image" | "video" | "audio" } {
  const url = card.preview_url || card.result_url || card.result_urls?.[0] || card.media?.[0]?.url || "";
  const contentType = String(card.media?.[0]?.content_type || "").toLowerCase();
  if (contentType.startsWith("video/") || /\.(mp4|mov|webm)(\?|$)/i.test(url)) return { url, type: "video" };
  if (contentType.startsWith("audio/") || /\.(mp3|wav|m4a|aac|ogg)(\?|$)/i.test(url)) return { url, type: "audio" };
  return { url, type: "image" };
}

export function ProfileStartApp({ referralCode }: { referralCode: string }) {
  const [author, setAuthor] = useState<PublicAuthor | null>(null);
  const [social, setSocial] = useState<SocialProfile | null>(null);
  const [items, setItems] = useState<FeedCard[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void api.profileFeed(referralCode, 0)
      .then(async (payload) => {
        if (!active) return;
        const nextAuthor = (payload.author || null) as PublicAuthor | null;
        setAuthor(nextAuthor);
        setItems(payload.items || []);
        if (nextAuthor?.id) {
          try {
            const profile = await customerRequest<SocialProfile>(`/api/v1/social/profiles/${encodeURIComponent(nextAuthor.id)}`);
            if (active) setSocial(profile);
          } catch {
            if (active) setSocial(null);
          }
        }
      })
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "Не удалось открыть профиль"));
    return () => { active = false; };
  }, [referralCode]);

  const toggleSubscription = async () => {
    if (!social?.id || social.is_self || busy) return;
    setBusy(true);
    setError("");
    try {
      const next = await customerRequest<SocialProfile>(`/api/v1/social/profiles/${encodeURIComponent(social.id)}/subscribe`, {
        method: social.subscribed_by_me ? "DELETE" : "POST",
      });
      setSocial(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось изменить подписку");
    } finally { setBusy(false); }
  };

  const name = social?.display_name || author?.display_name || author?.username || "Автор ROXY";

  return (
    <StandaloneShell kicker="Профиль ROXY" title={name} copy={author?.username ? `@${author.username}` : "Публичные работы автора"}>
      <div className="tool-grid">
        <div className="panel tool-panel">
          {error ? <div className="action-error" role="alert">{error}</div> : null}
          {!author && !error ? <p className="muted">Открываю профиль…</p> : null}
          {social ? <div className="profile-stats"><div><strong>{Number(social.follower_count || 0).toLocaleString("ru-RU")}</strong><span>подписчиков</span></div><div><strong>{items.length}</strong><span>работ</span></div></div> : null}
          {social && !social.is_self ? <button className={social.subscribed_by_me ? "secondary wide" : "primary wide"} type="button" disabled={busy} onClick={() => void toggleSubscription()}>{busy ? "Обновляю…" : social.subscribed_by_me ? "Отписаться" : "Подписаться"}</button> : null}
          {author && !items.length ? <p className="muted">В профиле пока нет публичных работ.</p> : null}
          {items.length ? <div className="media-grid" data-profile-startapp-posts>{items.map((item) => {
            const asset = media(item);
            return <button className="media-tile" type="button" key={item.id} onClick={() => window.location.assign(`/mini-app/?start_payload=${encodeURIComponent(`feed_${item.id}_ref_${referralCode}`)}`)}>
              {asset.url && asset.type === "video" ? <video src={asset.url} muted playsInline preload="metadata" /> : null}
              {asset.url && asset.type === "image" ? <img src={asset.url} alt="" loading="lazy" /> : null}
              {asset.type === "audio" || !asset.url ? <span className="media-placeholder"><Icon name={asset.type === "audio" ? "music" : "image"}/></span> : null}
            </button>;
          })}</div> : null}
          <div className="tool-actions">
            <button className="primary" type="button" onClick={() => window.location.assign("/mini-app/subscriptions/")}><Icon name="heart" size={16}/>Мои подписки</button>
            <button className="secondary" type="button" onClick={() => window.location.assign("/mini-app/?route=feed")}>Открыть ленту</button>
            <button className="secondary" type="button" onClick={() => window.location.assign("/mini-app/?route=home")}>Открыть ROXY</button>
          </div>
        </div>
      </div>
    </StandaloneShell>
  );
}
