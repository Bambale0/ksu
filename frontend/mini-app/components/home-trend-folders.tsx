"use client";

import { createPortal } from "react-dom";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { TrendCategoryAdmin } from "@/components/trend-category-admin";
import { TrendCollectionAdmin } from "@/components/trend-collection-admin";
import { haptic } from "@/lib/telegram";
import {
  trendCollectionsApi,
  type TrendCollection,
} from "@/lib/trend-collections-api";
import { trendUsageLabel } from "@/lib/trend-usage";
import type { TrendItem } from "@/lib/types";

function ensureHost(): HTMLElement | null {
  const home = document.querySelector<HTMLElement>(".home-screen");
  if (!home) return null;
  const existing = home.querySelector<HTMLElement>(":scope > #roxy-home-trend-folders");
  if (existing) return existing;
  const liveTrends = home.querySelector<HTMLElement>(":scope > #roxy-home-live-trends");
  if (!liveTrends) return null;
  const host = document.createElement("div");
  host.id = "roxy-home-trend-folders";
  host.dataset.trendFolders = "home";
  liveTrends.insertAdjacentElement("afterend", host);
  return host;
}

function countLabel(count: number): string {
  if (count === 1) return "1 шаблон";
  if (count > 1 && count < 5) return `${count} шаблона`;
  return `${count} шаблонов`;
}

function price(trend: TrendItem): string {
  if (trend.admin_free || trend.cost_rox === "0.00" || trend.cost_rox === "0") return "Бесплатно";
  if (!trend.cost_rox) return "—";
  const value = Number(trend.cost_rox);
  return Number.isFinite(value)
    ? `${value.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ROX`
    : `${trend.cost_rox} ROX`;
}

function TrendCards({ trends }: { trends: TrendItem[] }) {
  return <div className="home-trend-folder-items">
    {trends.map((trend) => <article className="home-trend-folder-item" key={trend.id}>
      <button
        type="button"
        className="home-trend-folder-item-open"
        onClick={() => {
          haptic("light");
          window.location.assign(`/mini-app/trend/?id=${encodeURIComponent(trend.id)}`);
        }}
      >
        {trend.preview_url ? trend.media_type === "video"
          ? <video className="home-trend-folder-media" src={trend.preview_url} muted autoPlay loop playsInline preload="metadata" />
          : <img className="home-trend-folder-media" src={trend.preview_url} alt="" loading="lazy" />
          : null}
        <span className="home-trend-folder-item-copy">
          <strong>{trend.title}</strong>
          {trend.description ? <small>{trend.description}</small> : null}
          <span className="home-trend-folder-item-meta">
            <span>{trendUsageLabel(trend.usage_count)}</span>
            <span>{trend.media_type === "video" ? "Видео" : "Фото"}</span>
            <span>{price(trend)}</span>
          </span>
        </span>
      </button>
    </article>)}
  </div>;
}

export function HomeTrendFolders() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [collections, setCollections] = useState<TrendCollection[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [mediaType, setMediaType] = useState<"image" | "video">("image");
  const [items, setItems] = useState<TrendItem[]>([]);
  const [loadingCollections, setLoadingCollections] = useState(false);
  const [loadingItems, setLoadingItems] = useState(false);
  const [error, setError] = useState("");
  const itemRequestVersion = useRef(0);

  useEffect(() => {
    let frame = 0;
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setHost(ensureHost()));
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

  const refreshCollections = useCallback(async () => {
    setLoadingCollections(true);
    try {
      const response = await trendCollectionsApi.list();
      const next = (response.items || []).filter((folder) => folder.system_key !== "trends");
      setCollections(next);
      setSelectedId((current) => current && next.some((folder) => folder.id === current) ? current : "");
      setError("");
    } catch (cause) {
      setCollections([]);
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить категории");
    } finally {
      setLoadingCollections(false);
    }
  }, []);

  useEffect(() => {
    if (host) void refreshCollections();
  }, [host, refreshCollections]);

  const selected = useMemo(
    () => collections.find((folder) => folder.id === selectedId) || null,
    [collections, selectedId],
  );

  const loadItems = useCallback(async (collectionId: string, kind: "image" | "video") => {
    const version = ++itemRequestVersion.current;
    setLoadingItems(true);
    setError("");
    try {
      const response = await trendCollectionsApi.items(collectionId, kind);
      if (version !== itemRequestVersion.current) return;
      setItems(response.items || []);
    } catch (cause) {
      if (version !== itemRequestVersion.current) return;
      setItems([]);
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить шаблоны");
    } finally {
      if (version === itemRequestVersion.current) setLoadingItems(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId) {
      void loadItems(selectedId, mediaType);
      return;
    }
    itemRequestVersion.current += 1;
    setItems([]);
    setLoadingItems(false);
    setError("");
  }, [selectedId, mediaType, loadItems]);

  const openFolder = (folder: TrendCollection) => {
    haptic("light");
    setSelectedId(folder.id);
    const photos = Number(folder.photo_count || 0);
    const videos = Number(folder.video_count || 0);
    setMediaType(photos > 0 || videos === 0 ? "image" : "video");
  };

  if (!host) return null;

  return createPortal(
    <section className="home-trend-folders" aria-label="Категории шаблонов">
      <style>{`
        .home-trend-folders{display:grid;gap:13px;margin:2px 0 26px;min-width:0}.home-trend-folders-head{display:flex;align-items:end;justify-content:space-between;gap:12px}.home-trend-folders-copy{display:grid;gap:4px;min-width:0}.home-trend-folders-copy h2{margin:0;font-size:24px;line-height:1;letter-spacing:-.04em}.home-trend-folders-copy p{margin:2px 0 0;color:var(--muted);font-size:12px;line-height:1.4}.home-trend-folders-actions{display:flex;align-items:center;gap:8px;flex-shrink:0}.home-trend-folders-back{border:1px solid rgba(255,255,255,.11);background:#17131d;color:#fff;border-radius:999px;padding:8px 11px;font-weight:850}.home-trend-folders-admin{display:flex;justify-content:flex-end;min-height:0}.home-trend-folder-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.home-trend-folder{position:relative;min-height:158px;overflow:hidden;border:1px solid rgba(190,117,255,.24);border-radius:23px;background:radial-gradient(circle at 80% 12%,rgba(170,74,255,.2),transparent 42%),linear-gradient(145deg,#15101e,#09070d);color:#fff;padding:0;text-align:left;box-shadow:0 16px 38px rgba(0,0,0,.2)}.home-trend-folder-preview{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.52}.home-trend-folder::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(5,3,9,.06),rgba(5,3,9,.9))}.home-trend-folder-card-copy{position:absolute;z-index:2;inset:auto 13px 13px;display:grid;gap:5px}.home-trend-folder-card-copy strong{font-size:18px;line-height:1.05}.home-trend-folder-card-copy small{color:rgba(255,255,255,.72);font-size:11px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.home-trend-folder-meta,.home-trend-folder-item-meta{display:flex;gap:5px;flex-wrap:wrap}.home-trend-folder-meta span,.home-trend-folder-item-meta span{padding:5px 7px;border-radius:999px;border:1px solid rgba(225,192,255,.18);background:rgba(12,8,18,.62);color:#ead8f8;font-size:9px;font-weight:850}.home-trend-folder-tabs{display:grid;grid-template-columns:1fr 1fr;gap:7px;padding:4px;border:1px solid rgba(255,255,255,.08);border-radius:17px;background:#0c0a0f}.home-trend-folder-tabs button{min-height:42px;border:0;border-radius:13px;background:transparent;color:#9d95a7;font-weight:850}.home-trend-folder-tabs button.active{background:linear-gradient(135deg,rgba(159,72,255,.88),rgba(207,94,255,.82));color:#fff;box-shadow:0 8px 24px rgba(165,72,255,.18)}.home-trend-folder-items{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(210px,76vw);gap:12px;overflow-x:auto;overscroll-behavior-x:contain;scroll-snap-type:x proximity;padding:2px 2px 8px;scrollbar-width:none}.home-trend-folder-items::-webkit-scrollbar{display:none}.home-trend-folder-item{position:relative;min-height:268px;overflow:hidden;border:1px solid rgba(185,105,255,.28);border-radius:25px;background:#0b0910;color:#fff;scroll-snap-align:start;box-shadow:0 18px 42px rgba(0,0,0,.24)}.home-trend-folder-item-open{position:absolute;inset:0;width:100%;padding:0;border:0;background:transparent;color:inherit;text-align:left}.home-trend-folder-media{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;background:#0b0910}.home-trend-folder-item-open::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.04) 28%,rgba(4,3,7,.88) 100%);pointer-events:none}.home-trend-folder-item-copy{position:absolute;z-index:2;left:14px;right:14px;bottom:14px;display:grid;gap:6px}.home-trend-folder-item-copy strong{font-size:18px;line-height:1.05}.home-trend-folder-item-copy small{color:rgba(255,255,255,.72);font-size:11px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.home-trend-folders-empty{padding:17px;border:1px dashed rgba(190,130,255,.26);border-radius:20px;color:var(--muted);background:rgba(16,12,22,.72)}.home-trend-folders-error{padding:11px 13px;border-radius:14px;background:rgba(255,80,120,.1);color:#ffc6d3}@media(min-width:720px){.home-trend-folder-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.home-trend-folder-items{grid-auto-columns:minmax(230px,310px)}}
      `}</style>

      {selected ? <div className="home-trend-folders-head">
        <div className="home-trend-folders-copy">
          <h2>{selected.title}</h2>
          {selected.description ? <p>{selected.description}</p> : null}
        </div>
        <div className="home-trend-folders-actions">
          <button className="home-trend-folders-back" type="button" onClick={() => { setSelectedId(""); setItems([]); }}>← Категории</button>
          <TrendCollectionAdmin onChanged={refreshCollections} />
        </div>
      </div> : <div className="home-trend-folders-admin" aria-label="Управление категориями">
        <TrendCategoryAdmin onChanged={refreshCollections} />
      </div>}

      {error ? <div className="home-trend-folders-error" role="alert">{error}</div> : null}

      {!selected ? loadingCollections ? <div className="home-trend-folders-empty">Загружаю категории…</div> : collections.length ? <div className="home-trend-folder-grid">
        {collections.map((folder) => <button className="home-trend-folder" type="button" key={folder.id} onClick={() => openFolder(folder)}>
          {folder.preview_url ? folder.preview_media_type === "video"
            ? <video
                className="home-trend-folder-preview"
                src={folder.preview_url}
                muted
                autoPlay
                loop
                playsInline
                preload="metadata"
                onError={(event) => { event.currentTarget.style.display = "none"; }}
              />
            : <img className="home-trend-folder-preview" src={folder.preview_url} alt="" loading="lazy" onError={(event) => { event.currentTarget.style.display = "none"; }} />
          : null}
          <span className="home-trend-folder-card-copy">
            <strong>{folder.title}</strong>
            {folder.description ? <small>{folder.description}</small> : null}
            <span className="home-trend-folder-meta">
              <span>{countLabel(Number(folder.item_count || 0))}</span>
              <span>Фото {folder.photo_count || 0}</span>
              <span>Видео {folder.video_count || 0}</span>
            </span>
          </span>
        </button>)}
      </div> : <div className="home-trend-folders-empty">Категории скоро появятся здесь.</div> : <>
        <div className="home-trend-folder-tabs" role="tablist" aria-label="Тип шаблона">
          <button className={mediaType === "image" ? "active" : ""} role="tab" aria-selected={mediaType === "image"} type="button" onClick={() => setMediaType("image")}>Фото · {selected.photo_count || 0}</button>
          <button className={mediaType === "video" ? "active" : ""} role="tab" aria-selected={mediaType === "video"} type="button" onClick={() => setMediaType("video")}>Видео · {selected.video_count || 0}</button>
        </div>
        {loadingItems ? <div className="home-trend-folders-empty">Загружаю шаблоны…</div> : items.length ? <TrendCards trends={items} /> : <div className="home-trend-folders-empty">В этой вкладке пока нет шаблонов.</div>}
      </>}
    </section>,
    host,
  );
}
