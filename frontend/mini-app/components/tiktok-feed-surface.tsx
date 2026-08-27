"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { copyToClipboard, haptic, notify, openExternalLink, openTelegramShare, telegramHeaders } from "@/lib/telegram";
import type { FeedCard, FeedComment, FeedSurface } from "@/lib/types";
import { Icon } from "./icons";

const PAGE_SIZE = 24;
const STYLE = `
  .tiktok-feed-surface {
    position: fixed;
    z-index: 70;
    inset: 0;
    overflow: hidden;
    background: #000;
    color: #fff;
    isolation: isolate;
  }
  .tiktok-feed-scroll {
    width: 100%;
    height: var(--tg-stable-height, 100dvh);
    overflow-y: auto;
    overflow-x: hidden;
    scroll-snap-type: y mandatory;
    overscroll-behavior-y: contain;
    scrollbar-width: none;
    background: #000;
  }
  .tiktok-feed-scroll::-webkit-scrollbar { display: none; }
  .tiktok-feed-card {
    position: relative;
    width: 100%;
    height: var(--tg-stable-height, 100dvh);
    min-height: 100dvh;
    overflow: hidden;
    scroll-snap-align: start;
    scroll-snap-stop: always;
    background: #050507;
  }
  .tiktok-feed-media,
  .tiktok-feed-media > img,
  .tiktok-feed-media > video {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }
  .tiktok-feed-media { background: #050507; }
  .tiktok-feed-media > img,
  .tiktok-feed-media > video {
    display: block;
    object-fit: contain;
    object-position: center;
    background: #050507;
  }
  .tiktok-feed-media > img.tiktok-feed-cover {
    object-fit: cover;
    filter: blur(36px) saturate(.8) brightness(.48);
    transform: scale(1.12);
    opacity: .66;
  }
  .tiktok-feed-media > img.tiktok-feed-main-image {
    z-index: 1;
    object-fit: contain;
    background: transparent;
  }
  .tiktok-feed-media.blurred > img,
  .tiktok-feed-media.blurred > video { filter: blur(24px) brightness(.58); transform: scale(1.04); }
  .tiktok-feed-audio {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    align-content: center;
    gap: 18px;
    padding: 28px;
    background:
      radial-gradient(circle at 50% 36%, rgba(155,92,255,.33), transparent 30%),
      radial-gradient(circle at 40% 62%, rgba(255,95,183,.17), transparent 34%),
      #08070d;
  }
  .tiktok-feed-audio > span {
    width: 108px;
    height: 108px;
    display: grid;
    place-items: center;
    border: 1px solid rgba(210,170,255,.35);
    border-radius: 34px;
    background: rgba(155,92,255,.13);
    box-shadow: 0 0 70px rgba(155,92,255,.22);
  }
  .tiktok-feed-audio audio { width: min(86vw, 420px); }
  .tiktok-feed-gradient {
    position: absolute;
    z-index: 2;
    inset: 0;
    pointer-events: none;
    background:
      linear-gradient(180deg, rgba(0,0,0,.48) 0%, transparent 20%, transparent 56%, rgba(0,0,0,.28) 70%, rgba(0,0,0,.88) 100%),
      linear-gradient(90deg, transparent 58%, rgba(0,0,0,.12) 100%);
  }
  .tiktok-feed-top {
    position: absolute;
    z-index: 8;
    top: calc(var(--tg-safe-top, 0px) + 12px);
    left: max(12px, var(--tg-safe-left, 0px));
    right: max(12px, var(--tg-safe-right, 0px));
    display: grid;
    justify-items: center;
    gap: 9px;
    pointer-events: none;
  }
  .tiktok-feed-tabs,
  .tiktok-feed-sort {
    pointer-events: auto;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px;
    border: 1px solid rgba(255,255,255,.13);
    border-radius: 999px;
    background: rgba(8,8,12,.54);
    backdrop-filter: blur(18px) saturate(140%);
    box-shadow: 0 8px 28px rgba(0,0,0,.22);
  }
  .tiktok-feed-tabs button,
  .tiktok-feed-sort button,
  .tiktok-feed-refresh,
  .tiktok-feed-sound {
    border: 0;
    color: rgba(255,255,255,.68);
    background: transparent;
    font-weight: 850;
  }
  .tiktok-feed-tabs button { min-height: 34px; padding: 7px 13px; border-radius: 999px; font-size: 12px; }
  .tiktok-feed-tabs button.active { color: #fff; background: rgba(255,255,255,.13); }
  .tiktok-feed-sort { padding: 3px; }
  .tiktok-feed-sort button { min-height: 27px; padding: 5px 9px; border-radius: 999px; font-size: 9px; }
  .tiktok-feed-sort button.active { color: #fff; background: linear-gradient(110deg, rgba(155,92,255,.54), rgba(255,95,183,.35)); }
  .tiktok-feed-refresh,
  .tiktok-feed-sound {
    position: absolute;
    z-index: 9;
    top: calc(var(--tg-safe-top, 0px) + 16px);
    width: 40px;
    height: 40px;
    border: 1px solid rgba(255,255,255,.13);
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: rgba(8,8,12,.52);
    color: #fff;
    backdrop-filter: blur(18px);
  }
  .tiktok-feed-refresh { left: max(12px, var(--tg-safe-left, 0px)); font-size: 20px; }
  .tiktok-feed-sound { right: max(12px, var(--tg-safe-right, 0px)); font-size: 15px; }
  .tiktok-feed-meta {
    position: absolute;
    z-index: 5;
    left: max(14px, var(--tg-safe-left, 0px));
    right: 82px;
    bottom: calc(94px + var(--tg-safe-bottom, 0px));
    display: grid;
    gap: 7px;
    text-shadow: 0 1px 8px rgba(0,0,0,.72);
  }
  .tiktok-feed-author-line {
    width: fit-content;
    max-width: 100%;
    padding: 0;
    border: 0;
    display: flex;
    align-items: center;
    gap: 8px;
    background: transparent;
    color: #fff;
    text-align: left;
  }
  .tiktok-feed-author-line strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; font-weight: 900; }
  .tiktok-feed-author-line small { color: rgba(255,255,255,.66); font-size: 10px; }
  .tiktok-feed-model { width: fit-content; max-width: 100%; padding: 5px 8px; border: 1px solid rgba(205,165,255,.24); border-radius: 999px; background: rgba(118,67,181,.24); color: #ead8ff; font-size: 9px; font-weight: 800; }
  .tiktok-feed-prompt {
    margin: 0;
    max-width: min(620px, 100%);
    color: rgba(255,255,255,.92);
    font-size: 12px;
    line-height: 1.42;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    overflow: hidden;
  }
  .tiktok-feed-prompt.expanded { display: block; max-height: 19dvh; overflow-y: auto; }
  .tiktok-feed-prompt-more { width: fit-content; padding: 0; border: 0; background: transparent; color: #d7a4ff; font-size: 10px; font-weight: 850; }
  .tiktok-feed-rail {
    position: absolute;
    z-index: 6;
    right: max(10px, var(--tg-safe-right, 0px));
    bottom: calc(95px + var(--tg-safe-bottom, 0px));
    width: 60px;
    display: grid;
    justify-items: center;
    gap: 12px;
  }
  .tiktok-feed-rail-action,
  .tiktok-feed-avatar {
    width: 52px;
    min-height: 52px;
    padding: 0;
    border: 0;
    background: transparent;
    color: #fff;
    display: grid;
    place-items: center;
    align-content: center;
    gap: 2px;
    text-shadow: 0 1px 8px rgba(0,0,0,.8);
  }
  .tiktok-feed-rail-action > span:first-child {
    width: 43px;
    height: 43px;
    display: grid;
    place-items: center;
    border: 1px solid rgba(255,255,255,.14);
    border-radius: 50%;
    background: rgba(8,8,12,.52);
    backdrop-filter: blur(12px);
  }
  .tiktok-feed-rail-action small { color: #fff; font-size: 9px; font-weight: 800; }
  .tiktok-feed-rail-action.liked > span:first-child { color: #ff78bb; background: rgba(255,95,183,.18); border-color: rgba(255,95,183,.4); }
  .tiktok-feed-avatar { position: relative; width: 54px; height: 64px; }
  .tiktok-feed-avatar > span:first-child {
    width: 46px;
    height: 46px;
    display: grid;
    place-items: center;
    border: 2px solid rgba(255,255,255,.9);
    border-radius: 50%;
    background: linear-gradient(145deg, #6f3cc4, #25172f);
    font-size: 12px;
    font-weight: 950;
  }
  .tiktok-feed-follow {
    position: absolute;
    left: 50%;
    bottom: 1px;
    transform: translateX(-50%);
    min-width: 27px;
    height: 22px;
    padding: 0 7px;
    border: 2px solid #08080c;
    border-radius: 999px;
    display: grid;
    place-items: center;
    background: linear-gradient(110deg, #9b5cff, #ff5fb7);
    color: #fff;
    font-size: 13px;
    line-height: 1;
    font-weight: 950;
  }
  .tiktok-feed-follow.subscribed { background: rgba(30,29,37,.94); color: #d8c8ec; font-size: 10px; }
  .tiktok-feed-reveal {
    position: absolute;
    z-index: 7;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    min-height: 44px;
    padding: 10px 16px;
    border: 1px solid rgba(255,255,255,.23);
    border-radius: 999px;
    background: rgba(10,10,15,.76);
    color: #fff;
    font-weight: 850;
    backdrop-filter: blur(14px);
  }
  .tiktok-feed-heart-burst {
    position: absolute;
    z-index: 10;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    pointer-events: none;
    color: #ff71b7;
    filter: drop-shadow(0 8px 30px rgba(255,95,183,.48));
    animation: tiktok-heart-burst .62s ease-out both;
  }
  @keyframes tiktok-heart-burst {
    0% { opacity: 0; transform: translate(-50%, -50%) scale(.4) rotate(-8deg); }
    35% { opacity: 1; transform: translate(-50%, -50%) scale(1.35) rotate(4deg); }
    100% { opacity: 0; transform: translate(-50%, -50%) scale(1) rotate(0); }
  }
  .tiktok-feed-state {
    position: absolute;
    z-index: 7;
    inset: 0;
    display: grid;
    place-items: center;
    align-content: center;
    gap: 12px;
    padding: 28px;
    text-align: center;
    background: radial-gradient(circle at 50% 40%, rgba(155,92,255,.16), transparent 30%), #07070b;
  }
  .tiktok-feed-state strong { font-size: 20px; }
  .tiktok-feed-state p { max-width: 360px; margin: 0; color: #aaa5b5; font-size: 12px; line-height: 1.5; }
  .tiktok-feed-state button { min-height: 42px; padding: 9px 15px; border: 1px solid rgba(190,145,255,.35); border-radius: 999px; background: rgba(155,92,255,.2); color: #fff; font-weight: 850; }
  .tiktok-feed-loader { position: absolute; z-index: 7; left: 50%; bottom: calc(88px + var(--tg-safe-bottom, 0px)); transform: translateX(-50%); padding: 6px 10px; border-radius: 999px; background: rgba(8,8,12,.62); color: rgba(255,255,255,.75); font-size: 9px; backdrop-filter: blur(12px); }
  .tiktok-sheet-layer {
    position: fixed;
    z-index: 150;
    inset: 0;
    display: flex;
    align-items: flex-end;
    justify-content: center;
  }
  .tiktok-sheet-backdrop { position: absolute; inset: 0; border: 0; background: rgba(0,0,0,.62); backdrop-filter: blur(8px); }
  .tiktok-sheet {
    position: relative;
    z-index: 1;
    width: min(100%, 720px);
    max-height: min(78dvh, 760px);
    overflow-y: auto;
    padding: 16px max(14px, var(--tg-safe-right, 0px)) calc(18px + var(--tg-safe-bottom, 0px)) max(14px, var(--tg-safe-left, 0px));
    border: 1px solid rgba(180,130,255,.22);
    border-bottom: 0;
    border-radius: 28px 28px 0 0;
    background: rgba(13,12,19,.98);
    box-shadow: 0 -30px 90px rgba(0,0,0,.58);
  }
  .tiktok-sheet-handle { width: 42px; height: 4px; margin: 0 auto 14px; border-radius: 999px; background: rgba(255,255,255,.22); }
  .tiktok-sheet-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }
  .tiktok-sheet-head h2 { margin: 0; font-size: 20px; }
  .tiktok-sheet-close { width: 38px; height: 38px; border: 1px solid rgba(255,255,255,.12); border-radius: 50%; background: rgba(255,255,255,.04); color: #fff; display: grid; place-items: center; }
  .tiktok-comments-list { display: grid; gap: 8px; margin: 14px 0; }
  .tiktok-comment { padding: 10px 12px; border: 1px solid rgba(255,255,255,.07); border-radius: 14px; background: rgba(255,255,255,.025); }
  .tiktok-comment strong { display: block; font-size: 11px; }
  .tiktok-comment p { margin: 5px 0 0; color: #ded9e6; font-size: 12px; line-height: 1.4; }
  .tiktok-comment small { color: #777381; font-size: 9px; }
  .tiktok-comment-form { position: sticky; bottom: 0; display: grid; grid-template-columns: minmax(0,1fr) auto; gap: 8px; padding-top: 10px; background: linear-gradient(transparent, rgba(13,12,19,1) 22%); }
  .tiktok-comment-form textarea { min-height: 44px; max-height: 96px; resize: vertical; padding: 11px 12px; border: 1px solid rgba(180,130,255,.2); border-radius: 14px; background: rgba(255,255,255,.04); color: #fff; }
  .tiktok-comment-form button { min-width: 48px; border: 0; border-radius: 14px; background: linear-gradient(110deg, #9b5cff, #ff5fb7); color: #fff; font-weight: 900; }
  .tiktok-detail-actions { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 8px; margin: 12px 0; }
  .tiktok-detail-actions button, .tiktok-detail-actions a { min-height: 44px; padding: 9px 11px; border: 1px solid rgba(180,130,255,.19); border-radius: 14px; display: flex; align-items: center; justify-content: center; gap: 7px; background: rgba(255,255,255,.035); color: #fff; text-decoration: none; font-size: 11px; font-weight: 850; }
  .tiktok-detail-actions .danger { color: #ff9aad; border-color: rgba(255,120,150,.2); }
  .tiktok-detail-copy { margin: 10px 0; padding: 12px; border: 1px solid rgba(255,255,255,.07); border-radius: 16px; background: rgba(255,255,255,.025); }
  .tiktok-detail-copy small { color: #a9a4b4; font-size: 9px; text-transform: uppercase; letter-spacing: .08em; font-weight: 800; }
  .tiktok-detail-copy p { margin: 7px 0 0; color: #e6e1eb; font-size: 12px; line-height: 1.5; white-space: pre-wrap; }
  .tiktok-reference-row { display: flex; gap: 8px; overflow-x: auto; padding: 4px 0 10px; }
  .tiktok-reference-row a { flex: 0 0 76px; width: 76px; height: 76px; overflow: hidden; border: 1px solid rgba(255,255,255,.08); border-radius: 14px; background: #08080c; }
  .tiktok-reference-row img, .tiktok-reference-row video { width: 100%; height: 100%; object-fit: cover; }
  .tiktok-profile-summary { display: flex; align-items: center; gap: 12px; padding: 5px 0 13px; }
  .tiktok-profile-avatar { width: 58px; height: 58px; flex: 0 0 58px; border-radius: 50%; display: grid; place-items: center; background: linear-gradient(145deg,#7142c8,#25182f); font-weight: 950; }
  .tiktok-profile-copy { min-width: 0; flex: 1; display: grid; gap: 3px; }
  .tiktok-profile-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 16px; }
  .tiktok-profile-copy small { color: #9994a3; font-size: 10px; }
  .tiktok-profile-follow { min-height: 38px; padding: 8px 12px; border: 1px solid rgba(190,145,255,.32); border-radius: 999px; background: linear-gradient(110deg, rgba(155,92,255,.65), rgba(255,95,183,.45)); color: #fff; font-size: 10px; font-weight: 900; }
  .tiktok-profile-follow.subscribed { background: rgba(255,255,255,.045); color: #d3ccda; }
  .tiktok-profile-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 5px; }
  .tiktok-profile-work { aspect-ratio: 1/1.22; padding: 0; overflow: hidden; border: 0; border-radius: 12px; background: #07070b; }
  .tiktok-profile-work img, .tiktok-profile-work video { width: 100%; height: 100%; object-fit: cover; }
  .tiktok-toast { position: fixed; z-index: 180; left: 50%; bottom: calc(88px + var(--tg-safe-bottom,0px)); transform: translateX(-50%); width: max-content; max-width: calc(100vw - 28px); padding: 9px 13px; border: 1px solid rgba(190,145,255,.25); border-radius: 999px; background: rgba(14,12,20,.93); color: #fff; font-size: 10px; font-weight: 800; box-shadow: 0 12px 36px rgba(0,0,0,.35); backdrop-filter: blur(16px); }
  @media (min-width: 760px) {
    .tiktok-feed-surface { left: 50%; right: auto; width: min(100vw, 620px); transform: translateX(-50%); box-shadow: 0 0 90px rgba(0,0,0,.6); }
  }
  @media (prefers-reduced-motion: reduce) {
    .tiktok-feed-scroll { scroll-behavior: auto; }
    .tiktok-feed-heart-burst { animation: none; opacity: .9; }
  }
`;

type FeedTab = "for-you" | "following";
type FeedSort = "recent" | "top_day" | "top";
type SocialProfile = {
  id: string;
  display_name?: string;
  username?: string | null;
  referral_code?: string;
  is_self?: boolean;
  subscribed_by_me?: boolean;
  follower_count?: number;
};

function currentRouteIsFeed(): boolean {
  if (typeof window === "undefined") return false;
  try {
    if (new URL(window.location.href).searchParams.get("route") === "feed") return true;
  } catch { /* ignore */ }
  return Array.from(document.querySelectorAll<HTMLButtonElement>(".bottom-nav button.active")).some((button) => {
    const label = button.querySelector("small")?.textContent?.trim() || button.textContent?.trim() || "";
    return label === "Лента";
  });
}

async function socialRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    cache: "no-store",
    headers: { ...telegramHeaders(Boolean(init.body)), ...(init.headers || {}) },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail ?? payload?.message ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload as T;
}

function mediaUrl(card: FeedCard): string {
  return card.result_url || card.result_urls?.[0] || card.media?.[0]?.url || card.preview_url || "";
}

function mediaType(card: FeedCard): "image" | "video" | "audio" {
  const url = mediaUrl(card);
  const declared = card.media?.[0]?.kind || card.media?.[0]?.content_type || "";
  if (String(declared).includes("video") || /\.(mp4|mov|webm)(\?|$)/i.test(url)) return "video";
  if (String(declared).includes("audio") || /\.(mp3|wav|m4a|aac|ogg)(\?|$)/i.test(url)) return "audio";
  return "image";
}

function cardSurface(card: FeedCard, tab: FeedTab): FeedSurface {
  return card.surface === "profile" || tab === "following" ? "profile" : "feed";
}

function authorName(card: FeedCard): string {
  return card.author?.display_name || card.author?.username || "Автор ROXY";
}

function authorInitials(card: FeedCard): string {
  return authorName(card).split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "RX";
}

function compact(value: unknown): string {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  return new Intl.NumberFormat("ru-RU", { notation: Math.abs(number) >= 10000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(number);
}

function dateLabel(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" }).format(date);
}

function sortLabel(sort: FeedSort): string {
  return sort === "top_day" ? "Топ дня" : sort === "top" ? "Топ" : "Новые";
}

function uniqueCards(cards: FeedCard[]): FeedCard[] {
  const seen = new Set<string>();
  return cards.filter((card) => card?.id && !seen.has(card.id) && seen.add(card.id));
}

export function TikTokFeedSurface() {
  const [visible, setVisible] = useState(false);
  const [tab, setTab] = useState<FeedTab>("for-you");
  const [sort, setSort] = useState<FeedSort>("recent");
  const [items, setItems] = useState<FeedCard[]>([]);
  const [modelTitles, setModelTitles] = useState<Record<string, string>>({});
  const [profiles, setProfiles] = useState<Record<string, SocialProfile>>({});
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [muted, setMuted] = useState(true);
  const [paused, setPaused] = useState(false);
  const [busyAction, setBusyAction] = useState("");
  const [expandedPrompt, setExpandedPrompt] = useState<string | null>(null);
  const [revealed, setRevealed] = useState<Set<string>>(() => new Set());
  const [heartBurst, setHeartBurst] = useState<string | null>(null);
  const [commentsId, setCommentsId] = useState<string | null>(null);
  const [comments, setComments] = useState<FeedComment[]>([]);
  const [commentText, setCommentText] = useState("");
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [detailsId, setDetailsId] = useState<string | null>(null);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [profileWorks, setProfileWorks] = useState<FeedCard[]>([]);
  const [profileLoading, setProfileLoading] = useState(false);
  const [toast, setToast] = useState("");
  const videoRefs = useRef(new Map<string, HTMLVideoElement>());
  const slideRefs = useRef(new Map<string, HTMLElement>());
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const toastTimer = useRef<number | null>(null);
  const loadingRef = useRef(false);

  const showToast = useCallback((message: string) => {
    setToast(message);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 2800);
  }, []);

  const patchCard = useCallback((id: string, patch: Partial<FeedCard>) => {
    setItems((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item));
    setProfileWorks((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item));
  }, []);

  useEffect(() => {
    const sync = () => setVisible(currentRouteIsFeed());
    sync();
    const observer = new MutationObserver(() => window.requestAnimationFrame(sync));
    observer.observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] });
    window.addEventListener("popstate", sync);
    return () => {
      observer.disconnect();
      window.removeEventListener("popstate", sync);
    };
  }, []);

  useEffect(() => {
    if (!visible) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, [visible]);

  const loadPage = useCallback(async (reset: boolean) => {
    if (!visible || loadingRef.current) return;
    loadingRef.current = true;
    reset ? setLoading(true) : setLoadingMore(true);
    try {
      const offset = reset ? 0 : items.length;
      const result = tab === "following"
        ? await socialRequest<{ items: FeedCard[]; has_more?: boolean }>(`/api/v1/social/subscriptions/feed?limit=${PAGE_SIZE}&offset=${offset}`)
        : await api.feed(sort, offset);
      const next = result.items || [];
      setItems((current) => reset ? uniqueCards(next) : uniqueCards([...current, ...next]));
      setHasMore(typeof result.has_more === "boolean" ? result.has_more : next.length >= PAGE_SIZE);
      setError("");
      if (reset) {
        setActiveIndex(0);
        scrollRef.current?.scrollTo({ top: 0 });
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить ленту");
      if (reset) setItems([]);
    } finally {
      setLoading(false);
      setLoadingMore(false);
      loadingRef.current = false;
    }
  }, [items.length, sort, tab, visible]);

  useEffect(() => {
    if (!visible) return;
    void loadPage(true);
    void api.models().then((result) => {
      setModelTitles(Object.fromEntries((result.models || []).map((model) => [model.id, model.title])));
    }).catch(() => undefined);
  }, [visible, tab, sort]); // loadPage intentionally omitted: items.length changes during pagination.

  useEffect(() => {
    if (!visible || !items.length) return;
    const observer = new IntersectionObserver((entries) => {
      let winner: { ratio: number; id: string } | null = null;
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const id = (entry.target as HTMLElement).dataset.feedId || "";
        if (!winner || entry.intersectionRatio > winner.ratio) winner = { ratio: entry.intersectionRatio, id };
      }
      if (!winner || winner.ratio < .55) return;
      const index = items.findIndex((item) => item.id === winner!.id);
      if (index >= 0) {
        setActiveIndex(index);
        setPaused(false);
      }
    }, { root: scrollRef.current, threshold: [.55, .72, .9] });
    for (const node of slideRefs.current.values()) observer.observe(node);
    return () => observer.disconnect();
  }, [items, visible]);

  useEffect(() => {
    const active = items[activeIndex];
    for (const [id, video] of videoRefs.current.entries()) {
      video.muted = muted;
      if (!visible || !active || id !== active.id || paused) video.pause();
      else void video.play().catch(() => undefined);
    }
    if (visible && activeIndex >= items.length - 3 && hasMore && !loadingMore) void loadPage(false);
  }, [activeIndex, hasMore, items, loadPage, loadingMore, muted, paused, visible]);

  const activeCard = items[activeIndex] || null;

  useEffect(() => {
    if (!visible || !activeCard?.author?.id || activeCard.is_mine || profiles[activeCard.author.id]) return;
    const authorId = activeCard.author.id;
    void socialRequest<SocialProfile>(`/api/v1/social/profiles/${encodeURIComponent(authorId)}`)
      .then((profile) => setProfiles((current) => ({ ...current, [authorId]: profile })))
      .catch(() => undefined);
  }, [activeCard, profiles, visible]);

  const toggleLike = useCallback(async (card: FeedCard, burst = false) => {
    const key = `${card.id}:like`;
    if (busyAction === key) return;
    if (burst) {
      setHeartBurst(card.id);
      window.setTimeout(() => setHeartBurst((current) => current === card.id ? null : current), 650);
    }
    if (card.liked_by_me && burst) return;
    setBusyAction(key);
    try {
      const surface = cardSurface(card, tab);
      const result = card.liked_by_me ? await api.unlike(card.id, surface) : await api.like(card.id, surface);
      patchCard(card.id, { liked_by_me: result.liked_by_me, likes_count: result.likes_count });
      haptic(card.liked_by_me ? "light" : "medium");
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "Не удалось поставить лайк");
    } finally { setBusyAction(""); }
  }, [busyAction, patchCard, showToast, tab]);

  const toggleFollow = useCallback(async (card: FeedCard) => {
    const authorId = card.author?.id;
    if (!authorId || card.is_mine) return;
    const profile = profiles[authorId];
    const key = `${authorId}:follow`;
    if (busyAction === key) return;
    setBusyAction(key);
    try {
      const method = profile?.subscribed_by_me ? "DELETE" : "POST";
      const next = await socialRequest<SocialProfile>(`/api/v1/social/profiles/${encodeURIComponent(authorId)}/subscribe`, { method });
      setProfiles((current) => ({ ...current, [authorId]: next }));
      haptic("medium");
      showToast(next.subscribed_by_me ? "Вы подписались" : "Подписка отменена");
      if (tab === "following" && !next.subscribed_by_me) {
        setItems((current) => current.filter((item) => item.author?.id !== authorId));
      }
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "Не удалось изменить подписку");
    } finally { setBusyAction(""); }
  }, [busyAction, profiles, showToast, tab]);

  const shareCard = useCallback(async (card: FeedCard) => {
    const key = `${card.id}:share`;
    if (busyAction === key) return;
    setBusyAction(key);
    try {
      const result = await api.share(card.id, cardSurface(card, tab));
      patchCard(card.id, { shares_count: result.shares_count });
      if (result.link) {
        const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(result.link)}&text=${encodeURIComponent("Смотри, что сделали в ROXY ✨")}`;
        openTelegramShare(shareUrl);
      } else {
        showToast("Ссылка пока недоступна");
      }
      haptic("light");
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "Не удалось поделиться");
    } finally { setBusyAction(""); }
  }, [busyAction, patchCard, showToast, tab]);

  const remixCard = useCallback(async (card: FeedCard) => {
    const key = `${card.id}:remix`;
    if (busyAction === key) return;
    setBusyAction(key);
    try {
      await api.remix(card.id, cardSurface(card, tab));
      patchCard(card.id, { remixes: Number(card.remixes || 0) + 1 });
      notify("success");
      showToast("Повтор запущен — результат появится в истории");
    } catch (reason) {
      notify("error");
      showToast(reason instanceof Error ? reason.message : "Не удалось повторить работу");
    } finally { setBusyAction(""); }
  }, [busyAction, patchCard, showToast, tab]);

  const openComments = useCallback(async (card: FeedCard) => {
    setCommentsId(card.id);
    setComments([]);
    setCommentText("");
    setCommentsLoading(true);
    try {
      const result = await api.comments(card.id, cardSurface(card, tab));
      setComments(result.items || []);
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "Не удалось открыть комментарии");
    } finally { setCommentsLoading(false); }
  }, [showToast, tab]);

  const commentsCard = commentsId ? items.find((item) => item.id === commentsId) || profileWorks.find((item) => item.id === commentsId) || null : null;

  const addComment = useCallback(async () => {
    if (!commentsCard || !commentText.trim()) return;
    const key = `${commentsCard.id}:comment`;
    if (busyAction === key) return;
    setBusyAction(key);
    try {
      const comment = await api.addComment(commentsCard.id, cardSurface(commentsCard, tab), commentText.trim());
      setComments((current) => [comment, ...current]);
      patchCard(commentsCard.id, { comments_count: Number(commentsCard.comments_count || 0) + 1 });
      setCommentText("");
      notify("success");
    } catch (reason) {
      notify("error");
      showToast(reason instanceof Error ? reason.message : "Не удалось отправить комментарий");
    } finally { setBusyAction(""); }
  }, [busyAction, commentText, commentsCard, patchCard, showToast, tab]);

  const openProfile = useCallback(async (card: FeedCard) => {
    const authorId = card.author?.id;
    if (!authorId) return;
    setProfileId(authorId);
    setProfileWorks([]);
    setProfileLoading(true);
    try {
      const profilePromise = profiles[authorId]
        ? Promise.resolve(profiles[authorId])
        : socialRequest<SocialProfile>(`/api/v1/social/profiles/${encodeURIComponent(authorId)}`);
      const referral = card.author_referral_code || card.author?.referral_code || String(card.author?.telegram_id || "");
      const [profile, works] = await Promise.all([
        profilePromise,
        referral ? api.profileFeed(referral, 0) : Promise.resolve({ items: [] as FeedCard[] }),
      ]);
      setProfiles((current) => ({ ...current, [authorId]: profile }));
      setProfileWorks(works.items || []);
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "Не удалось открыть профиль");
    } finally { setProfileLoading(false); }
  }, [profiles, showToast]);

  const removeOwnPublication = useCallback(async (card: FeedCard) => {
    if (!card.is_mine) return;
    const key = `${card.id}:remove`;
    if (busyAction === key) return;
    setBusyAction(key);
    try {
      await api.removePublication(card.id, "private");
      setItems((current) => current.filter((item) => item.id !== card.id));
      setDetailsId(null);
      notify("success");
      showToast("Публикация убрана");
    } catch (reason) {
      notify("error");
      showToast(reason instanceof Error ? reason.message : "Не удалось убрать публикацию");
    } finally { setBusyAction(""); }
  }, [busyAction, showToast]);

  const detailsCard = detailsId ? items.find((item) => item.id === detailsId) || null : null;
  const profileCard = profileId ? items.find((item) => item.author?.id === profileId) || profileWorks.find((item) => item.author?.id === profileId) || null : null;
  const currentProfile = profileId ? profiles[profileId] : undefined;

  const togglePlayback = (card: FeedCard) => {
    if (mediaType(card) !== "video") return;
    const video = videoRefs.current.get(card.id);
    if (!video) return;
    if (video.paused) { setPaused(false); void video.play().catch(() => undefined); }
    else { video.pause(); setPaused(true); }
    haptic("light");
  };

  const toggleReveal = (id: string) => {
    setRevealed((current) => new Set([...current, id]));
    haptic("light");
  };

  const copyShareLink = useCallback(async (card: FeedCard) => {
    try {
      const result = await api.share(card.id, cardSurface(card, tab));
      patchCard(card.id, { shares_count: result.shares_count });
      if (!result.link) throw new Error("Ссылка пока недоступна");
      const copied = await copyToClipboard(result.link);
      showToast(copied ? "Ссылка скопирована" : "Не удалось скопировать ссылку");
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "Не удалось скопировать ссылку");
    }
  }, [patchCard, showToast, tab]);

  const switchTab = (next: FeedTab) => {
    if (next === tab) return;
    setTab(next);
    setItems([]);
    setHasMore(true);
    setError("");
    haptic("light");
  };

  const switchSort = (next: FeedSort) => {
    if (next === sort) return;
    setSort(next);
    setItems([]);
    setHasMore(true);
    setError("");
    haptic("light");
  };

  const visibleItems = useMemo(() => items.filter((item) => Boolean(mediaUrl(item))), [items]);

  if (!visible) return null;

  return <>
    <style>{STYLE}</style>
    <section className="tiktok-feed-surface" aria-label="Лента ROXY">
      <div className="tiktok-feed-top">
        <div className="tiktok-feed-tabs" role="tablist" aria-label="Раздел ленты">
          <button type="button" role="tab" aria-selected={tab === "for-you"} className={tab === "for-you" ? "active" : ""} onClick={() => switchTab("for-you")}>Для вас</button>
          <button type="button" role="tab" aria-selected={tab === "following"} className={tab === "following" ? "active" : ""} onClick={() => switchTab("following")}>Подписки</button>
        </div>
        {tab === "for-you" && <div className="tiktok-feed-sort" aria-label="Сортировка">
          {(["recent", "top_day", "top"] as FeedSort[]).map((value) => <button key={value} type="button" className={sort === value ? "active" : ""} onClick={() => switchSort(value)}>{sortLabel(value)}</button>)}
        </div>}
      </div>
      <button className="tiktok-feed-refresh" type="button" aria-label="Обновить ленту" disabled={loading} onClick={() => void loadPage(true)}>↻</button>
      <button className="tiktok-feed-sound" type="button" aria-label={muted ? "Включить звук" : "Выключить звук"} onClick={() => { setMuted((current) => !current); haptic("light"); }}>{muted ? "🔇" : "🔊"}</button>

      {loading && !visibleItems.length ? <div className="tiktok-feed-state"><strong>ROXY</strong><p>Загружаю лучшие работы сообщества…</p></div>
      : error && !visibleItems.length ? <div className="tiktok-feed-state"><strong>Лента не загрузилась</strong><p>{error}</p><button type="button" onClick={() => void loadPage(true)}>Попробовать ещё раз</button></div>
      : !visibleItems.length ? <div className="tiktok-feed-state"><strong>{tab === "following" ? "Подписок пока нет" : "Лента пока пуста"}</strong><p>{tab === "following" ? "Подпишитесь на понравившихся авторов — их новые работы появятся здесь." : "Как только авторы опубликуют работы, они появятся здесь."}</p>{tab === "following" && <button type="button" onClick={() => switchTab("for-you")}>Найти авторов</button>}</div>
      : <div ref={scrollRef} className="tiktok-feed-scroll">
        {visibleItems.map((card) => {
          const type = mediaType(card);
          const url = mediaUrl(card);
          const authorId = card.author?.id || "";
          const profile = authorId ? profiles[authorId] : undefined;
          const blurred = Boolean(card.feed_blurred && !revealed.has(card.id));
          const promptExpanded = expandedPrompt === card.id;
          return <article
            key={card.id}
            ref={(node) => { if (node) slideRefs.current.set(card.id, node); else slideRefs.current.delete(card.id); }}
            data-feed-id={card.id}
            className="tiktok-feed-card"
            aria-label={`Работа ${authorName(card)}`}
          >
            <div className={`tiktok-feed-media${blurred ? " blurred" : ""}`} onDoubleClick={() => void toggleLike(card, true)} onClick={() => togglePlayback(card)}>
              {type === "video" ? <video
                ref={(node) => { if (node) videoRefs.current.set(card.id, node); else videoRefs.current.delete(card.id); }}
                src={url}
                muted={muted}
                playsInline
                loop
                preload={Math.abs(visibleItems.indexOf(card) - activeIndex) <= 1 ? "auto" : "metadata"}
              /> : type === "audio" ? <div className="tiktok-feed-audio"><span><Icon name="music" size={46}/></span><strong>Аудио ROXY</strong><audio src={url} controls preload="metadata" /></div> : <><img className="tiktok-feed-cover" src={url} alt="" aria-hidden="true"/><img className="tiktok-feed-main-image" src={url} alt={`Работа ${authorName(card)}`} loading={visibleItems.indexOf(card) <= activeIndex + 2 ? "eager" : "lazy"}/></>}
            </div>
            <div className="tiktok-feed-gradient" />
            {blurred && <button className="tiktok-feed-reveal" type="button" onClick={(event) => { event.stopPropagation(); toggleReveal(card.id); }}>Показать работу</button>}
            {heartBurst === card.id && <span className="tiktok-feed-heart-burst"><Icon name="heart" size={86}/></span>}

            <div className="tiktok-feed-meta">
              <button className="tiktok-feed-author-line" type="button" onClick={() => void openProfile(card)}>
                <strong>{authorName(card)}</strong>
                {card.author?.username && <small>@{card.author.username}</small>}
              </button>
              <span className="tiktok-feed-model">{modelTitles[String(card.model || "")] || String(card.model || "ROXY")}</span>
              {card.prompt && !card.prompt_hidden && <>
                <p className={`tiktok-feed-prompt${promptExpanded ? " expanded" : ""}`}>{card.prompt}</p>
                {card.prompt.length > 90 && <button className="tiktok-feed-prompt-more" type="button" onClick={() => setExpandedPrompt(promptExpanded ? null : card.id)}>{promptExpanded ? "свернуть" : "ещё"}</button>}
              </>}
              <small style={{ color: "rgba(255,255,255,.55)", fontSize: 9 }}>{dateLabel(card.feed_published_at || card.created_at)}</small>
            </div>

            <div className="tiktok-feed-rail">
              <button className="tiktok-feed-avatar" type="button" onClick={() => void openProfile(card)} aria-label={`Профиль ${authorName(card)}`}>
                <span>{authorInitials(card)}</span>
                {!card.is_mine && <span className={`tiktok-feed-follow${profile?.subscribed_by_me ? " subscribed" : ""}`} onClick={(event) => { event.stopPropagation(); void toggleFollow(card); }}>{profile?.subscribed_by_me ? "✓" : "+"}</span>}
              </button>
              <button className={`tiktok-feed-rail-action${card.liked_by_me ? " liked" : ""}`} type="button" disabled={busyAction === `${card.id}:like`} onClick={() => void toggleLike(card)} aria-label="Лайк"><span><Icon name="heart" size={23}/></span><small>{compact(card.likes_count)}</small></button>
              <button className="tiktok-feed-rail-action" type="button" onClick={() => void openComments(card)} aria-label="Комментарии"><span><Icon name="comment" size={22}/></span><small>{compact(card.comments_count)}</small></button>
              <button className="tiktok-feed-rail-action" type="button" disabled={busyAction === `${card.id}:share`} onClick={() => void shareCard(card)} aria-label="Поделиться"><span><Icon name="share" size={22}/></span><small>{compact(card.shares_count)}</small></button>
              {card.prompt_actions_allowed !== false && <button className="tiktok-feed-rail-action" type="button" disabled={busyAction === `${card.id}:remix`} onClick={() => void remixCard(card)} aria-label="Повторить"><span><Icon name="create" size={22}/></span><small>{compact(card.remixes)}</small></button>}
              <button className="tiktok-feed-rail-action" type="button" onClick={() => setDetailsId(card.id)} aria-label="Ещё"><span style={{ fontSize: 24, lineHeight: 1 }}>•••</span><small>Ещё</small></button>
            </div>
          </article>;
        })}
        {loadingMore && <div className="tiktok-feed-loader">Загружаю ещё…</div>}
      </div>}
    </section>

    {commentsCard && <div className="tiktok-sheet-layer" role="dialog" aria-modal="true" aria-label="Комментарии">
      <button className="tiktok-sheet-backdrop" type="button" onClick={() => setCommentsId(null)} aria-label="Закрыть комментарии"/>
      <section className="tiktok-sheet">
        <div className="tiktok-sheet-handle" />
        <div className="tiktok-sheet-head"><h2>Комментарии · {compact(commentsCard.comments_count)}</h2><button className="tiktok-sheet-close" type="button" onClick={() => setCommentsId(null)} aria-label="Закрыть"><Icon name="close"/></button></div>
        {commentsLoading ? <p style={{ color: "#9994a3", fontSize: 12 }}>Загружаю обсуждение…</p> : <div className="tiktok-comments-list">{comments.length ? comments.map((comment) => <div className="tiktok-comment" key={comment.id}><strong>{comment.author?.display_name || comment.author?.username || "Пользователь"}</strong><small>{dateLabel(comment.created_at)}</small><p>{comment.text}</p></div>) : <p style={{ color: "#9994a3", fontSize: 12 }}>Комментариев пока нет. Можно быть первым.</p>}</div>}
        <div className="tiktok-comment-form"><textarea maxLength={300} placeholder="Написать комментарий…" value={commentText} onChange={(event) => setCommentText(event.target.value)}/><button type="button" disabled={!commentText.trim() || busyAction === `${commentsCard.id}:comment`} onClick={() => void addComment()} aria-label="Отправить">↑</button></div>
      </section>
    </div>}

    {detailsCard && <div className="tiktok-sheet-layer" role="dialog" aria-modal="true" aria-label="Действия с работой">
      <button className="tiktok-sheet-backdrop" type="button" onClick={() => setDetailsId(null)} aria-label="Закрыть"/>
      <section className="tiktok-sheet">
        <div className="tiktok-sheet-handle" />
        <div className="tiktok-sheet-head"><h2>{modelTitles[String(detailsCard.model || "")] || "Работа ROXY"}</h2><button className="tiktok-sheet-close" type="button" onClick={() => setDetailsId(null)} aria-label="Закрыть"><Icon name="close"/></button></div>
        <button className="tiktok-feed-author-line" type="button" onClick={() => { setDetailsId(null); void openProfile(detailsCard); }}><strong>{authorName(detailsCard)}</strong>{detailsCard.author?.username && <small>@{detailsCard.author.username}</small>}</button>
        {detailsCard.prompt && !detailsCard.prompt_hidden && <div className="tiktok-detail-copy"><small>Описание</small><p>{detailsCard.prompt}</p></div>}
        {!detailsCard.references_hidden && Boolean((detailsCard.reference_images?.length || 0) + (detailsCard.reference_videos?.length || 0)) && <div className="tiktok-detail-copy"><small>Референсы автора</small><div className="tiktok-reference-row">{(detailsCard.reference_images || []).map((url, index) => <a href={url} target="_blank" rel="noreferrer" key={`${url}-${index}`}><img src={url} alt={`Референс ${index + 1}`}/></a>)}{(detailsCard.reference_videos || []).map((url, index) => <a href={url} target="_blank" rel="noreferrer" key={`${url}-${index}`}><video src={url} muted playsInline preload="metadata"/></a>)}</div></div>}
        <div className="tiktok-detail-actions">
          <button type="button" onClick={() => openExternalLink(mediaUrl(detailsCard))}>Открыть результат</button>
          <button type="button" onClick={() => void copyShareLink(detailsCard)}>Скопировать ссылку</button>
          <button type="button" onClick={() => { setDetailsId(null); void openComments(detailsCard); }}>Комментарии</button>
          {detailsCard.prompt_actions_allowed !== false && <button type="button" onClick={() => void remixCard(detailsCard)}>Повторить работу</button>}
          {detailsCard.is_mine && <button className="danger" type="button" onClick={() => void removeOwnPublication(detailsCard)}>Убрать публикацию</button>}
        </div>
      </section>
    </div>}

    {profileId && profileCard && <div className="tiktok-sheet-layer" role="dialog" aria-modal="true" aria-label="Профиль автора">
      <button className="tiktok-sheet-backdrop" type="button" onClick={() => setProfileId(null)} aria-label="Закрыть профиль"/>
      <section className="tiktok-sheet">
        <div className="tiktok-sheet-handle" />
        <div className="tiktok-sheet-head"><h2>Профиль автора</h2><button className="tiktok-sheet-close" type="button" onClick={() => setProfileId(null)} aria-label="Закрыть"><Icon name="close"/></button></div>
        <div className="tiktok-profile-summary">
          <span className="tiktok-profile-avatar">{authorInitials(profileCard)}</span>
          <div className="tiktok-profile-copy"><strong>{currentProfile?.display_name || authorName(profileCard)}</strong><small>{currentProfile?.username ? `@${currentProfile.username}` : profileCard.author?.username ? `@${profileCard.author.username}` : "Автор ROXY"}</small><small>{compact(currentProfile?.follower_count)} подписчиков</small></div>
          {!profileCard.is_mine && <button className={`tiktok-profile-follow${currentProfile?.subscribed_by_me ? " subscribed" : ""}`} type="button" onClick={() => void toggleFollow(profileCard)}>{currentProfile?.subscribed_by_me ? "Вы подписаны" : "Подписаться"}</button>}
        </div>
        {profileLoading ? <p style={{ color: "#9994a3", fontSize: 12 }}>Загружаю работы…</p> : profileWorks.length ? <div className="tiktok-profile-grid">{profileWorks.slice(0, 12).map((work) => <button className="tiktok-profile-work" type="button" key={work.id} onClick={() => openExternalLink(mediaUrl(work))}>{mediaType(work) === "video" ? <video src={mediaUrl(work)} muted playsInline preload="metadata"/> : <img src={mediaUrl(work)} alt="" loading="lazy"/>}</button>)}</div> : <p style={{ color: "#9994a3", fontSize: 12 }}>Публичных работ пока нет.</p>}
      </section>
    </div>}

    {toast && <div className="tiktok-toast" role="status">{toast}</div>}
  </>;
}
