"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { haptic, telegramHeaders } from "@/lib/telegram";

type ModerationAction = "visible" | "blurred" | "hidden" | "removed";

function key(prefix: string): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return `${prefix}:${crypto.randomUUID()}`;
  return `${prefix}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
}

function currentFeedCard(): string {
  const viewportCenter = window.innerHeight / 2;
  let winner: { id: string; distance: number } | null = null;
  for (const card of Array.from(document.querySelectorAll<HTMLElement>(".tiktok-feed-card[data-feed-id]"))) {
    const rect = card.getBoundingClientRect();
    if (rect.bottom <= 0 || rect.top >= window.innerHeight) continue;
    const center = rect.top + rect.height / 2;
    const distance = Math.abs(center - viewportCenter);
    const id = card.dataset.feedId || "";
    if (id && (!winner || distance < winner.distance)) winner = { id, distance };
  }
  return winner?.id || "";
}

async function moderate(id: string, action: ModerationAction): Promise<void> {
  const labels: Record<ModerationAction, string> = {
    visible: "Вернуть публикацию в обычный вид",
    blurred: "18+ / скрыть превью до нажатия",
    hidden: "Скрыть публикацию из публичных поверхностей",
    removed: "Удалить публикацию из ленты и профиля",
  };
  const response = await fetch(`/api/v1/inline-admin/feed/${encodeURIComponent(id)}/moderation`, {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      ...telegramHeaders(true),
      "Idempotency-Key": key(`feed-${action}`),
      "X-Request-Id": key("feed-admin-ui"),
    },
    body: JSON.stringify({ action, reason: labels[action] }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail ?? payload?.message ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
}

export function FeedAdminModeration() {
  const [isAdmin, setIsAdmin] = useState(false);
  const [feedVisible, setFeedVisible] = useState(false);
  const [generationId, setGenerationId] = useState("");
  const [busy, setBusy] = useState<ModerationAction | "">("");
  const [message, setMessage] = useState("");
  const layoutActive = isAdmin && feedVisible && Boolean(generationId);

  useEffect(() => {
    let active = true;
    void api.me()
      .then((me) => { if (active) setIsAdmin(Boolean(me.is_admin)); })
      .catch(() => { if (active) setIsAdmin(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    let frame = 0;
    const scan = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const visible = Boolean(document.querySelector(".tiktok-feed-surface"));
        setFeedVisible(visible);
        setGenerationId(visible ? currentFeedCard() : "");
      });
    };
    scan();
    const observer = new MutationObserver(scan);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "data-feed-id"] });
    window.addEventListener("scroll", scan, true);
    window.addEventListener("resize", scan);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("scroll", scan, true);
      window.removeEventListener("resize", scan);
    };
  }, [isAdmin]);

  useEffect(() => {
    if (!layoutActive) return;
    const root = document.documentElement;
    const previous = root.style.getPropertyValue("--feed-admin-clearance");
    root.style.setProperty("--feed-admin-clearance", "58px");
    return () => {
      if (previous) root.style.setProperty("--feed-admin-clearance", previous);
      else root.style.removeProperty("--feed-admin-clearance");
    };
  }, [layoutActive]);

  const apply = useCallback(async (action: ModerationAction) => {
    if (!generationId || busy) return;
    if (action === "removed" && !window.confirm("Удалить эту публикацию из ленты и профиля?")) return;
    setBusy(action);
    setMessage("");
    try {
      await moderate(generationId, action);
      haptic(action === "removed" ? "medium" : "light");
      setMessage(action === "blurred" ? "Публикация размыта" : action === "hidden" ? "Публикация скрыта" : action === "removed" ? "Публикация удалена" : "Публикация возвращена");
      document.querySelector<HTMLButtonElement>(".tiktok-feed-refresh")?.click();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Не удалось применить модерацию");
    } finally {
      setBusy("");
    }
  }, [busy, generationId]);

  if (!layoutActive) return null;

  return <div className="feed-admin-moderation" role="group" aria-label="Модерация публикации">
    <style>{`
      .feed-admin-moderation { position:fixed; z-index:145; left:50%; bottom:calc(88px + var(--tg-safe-bottom, 0px)); transform:translateX(-50%); width:min(calc(100vw - 22px), 620px); display:flex; align-items:center; gap:5px; padding:6px; border:1px solid rgba(218,176,255,.24); border-radius:18px; background:rgba(8,7,12,.82); box-shadow:0 14px 42px rgba(0,0,0,.42); backdrop-filter:blur(18px) saturate(135%); }
      .feed-admin-moderation button { flex:1 1 auto; min-width:0; min-height:34px; padding:6px 8px; border:0; border-radius:12px; background:rgba(155,92,255,.16); color:#f2e8ff; font-size:9px; font-weight:850; white-space:nowrap; }
      .feed-admin-moderation button.danger { background:rgba(255,77,118,.16); color:#ffd4df; }
      .feed-admin-moderation button:disabled { opacity:.45; }
      .feed-admin-moderation-status { position:absolute; left:50%; bottom:calc(100% + 7px); transform:translateX(-50%); max-width:90vw; padding:6px 9px; border-radius:999px; background:rgba(8,7,12,.9); color:#fff; font-size:9px; white-space:nowrap; }
      @media (max-width:390px) { .feed-admin-moderation { gap:3px; padding:4px; } .feed-admin-moderation button { padding:5px 4px; font-size:8px; } }
    `}</style>
    {message ? <span className="feed-admin-moderation-status" role="status">{message}</span> : null}
    <button type="button" disabled={Boolean(busy)} onClick={() => void apply("blurred")}>{busy === "blurred" ? "…" : "18+ / Blur"}</button>
    <button type="button" disabled={Boolean(busy)} onClick={() => void apply("hidden")}>{busy === "hidden" ? "…" : "Скрыть"}</button>
    <button className="danger" type="button" disabled={Boolean(busy)} onClick={() => void apply("removed")}>{busy === "removed" ? "…" : "Удалить"}</button>
    <button type="button" disabled={Boolean(busy)} onClick={() => void apply("visible")}>{busy === "visible" ? "…" : "Вернуть"}</button>
  </div>;
}
