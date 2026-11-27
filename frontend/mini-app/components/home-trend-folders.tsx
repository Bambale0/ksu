"use client";

import { createPortal } from "react-dom";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { TrendCategoryAdmin } from "@/components/trend-category-admin";
import { TrendCollectionAdmin } from "@/components/trend-collection-admin";
import { TrendPreviewMedia } from "@/components/trend-preview-media";
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

function CollectionPreview({ folder }: { folder: TrendCollection }) {
  const track = useRef<HTMLDivElement>(null);
  const [items, setItems] = useState<TrendItem[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const node = track.current;
    if (!node) return;
    let active = true;
    let started = false;
    const load = () => {
      if (started || !active) return;
      started = true;
      void trendCollectionsApi.items(folder.id, undefined, 8).then(result => {
        if (active) setItems((result.items || []).slice(0, 8));
      }).catch(() => {
        if (active) { setFailed(true); setItems([]); }
      });
    };
    if (typeof IntersectionObserver === "undefined") {
      load();
      return () => { active = false; };
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry?.isIntersecting) return;
      observer.disconnect();
      load();
    });
    observer.observe(node);
    return () => { active = false; observer.disconnect(); };
  }, [folder.id]);

  return <div ref={track} className="trend-collection-preview-track" aria-label={`Шаблоны категории ${folder.title}`}>
    {failed ? <span className="trend-collection-preview-status">Превью недоступны. Откройте все шаблоны.</span>
      : items === null ? <span className="trend-collection-preview-status" role="status">Загружаю шаблоны…</span>
      : items.length === 0 ? <span className="trend-collection-preview-status">В категории пока нет шаблонов.</span>
      : items.map(trend => <a key={trend.id} className="trend-collection-preview-card" href={`/mini-app/trend/?id=${encodeURIComponent(trend.id)}`}>
        {trend.preview_url ? <TrendPreviewMedia className="trend-collection-preview-media" mediaType={trend.media_type} url={trend.preview_url} thumbnailUrl={trend.preview_thumbnail_url} /> : null}
        {trend.media_type === "video" ? <span className="trend-collection-preview-kind">Видео</span> : null}
        <strong>{trend.title}</strong>
      </a>)}
  </div>;
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
        {trend.preview_url ? <TrendPreviewMedia className="home-trend-folder-media" mediaType={trend.media_type} url={trend.preview_url} thumbnailUrl={trend.preview_thumbnail_url} /> : null}
        <span className="home-trend-folder-item-copy">
          <strong>{trend.title}</strong>
          {trend.description ? <small>{trend.description}</small> : null}
          <span className="home-trend-folder-item-meta">
            <span>{trendUsageLabel(trend.usage_count)}</span>
            <span>{trend.media_type === "video" ? "Видео" : "Фото"}</span>
            {trend.workflow_type === "sequential_photo_video" ? <span>2 шага: фото → видео</span> : null}
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
    <section className={`home-trend-folders${selected ? " is-open" : ""}`} aria-label="Категории шаблонов">
      <style>{`
        .home-trend-folders{display:grid;gap:13px;margin:2px 0 26px;min-width:0}.home-trend-folders.is-open{position:fixed;z-index:70;inset:0 0 calc(92px + var(--tg-safe-bottom)) 0;overflow-x:hidden;overflow-y:auto;overscroll-behavior:contain;margin:0;padding:calc(18px + var(--tg-safe-top)) max(14px,var(--tg-safe-right)) 28px max(14px,var(--tg-safe-left));background:#0b0b10;align-content:start;-webkit-overflow-scrolling:touch}.home-trend-folders-head{display:flex;align-items:end;justify-content:space-between;gap:12px}.home-trend-folders-copy{display:grid;gap:4px;min-width:0}.home-trend-folders-copy h2{margin:0;font-size:24px;line-height:1;letter-spacing:-.04em}.home-trend-folders-copy p{margin:2px 0 0;color:var(--muted);font-size:12px;line-height:1.4}.home-trend-folders-actions{display:flex;align-items:center;gap:8px;flex-shrink:0}.home-trend-folders-back{border:1px solid rgba(255,255,255,.11);background:#17131d;color:#fff;border-radius:999px;padding:8px 11px;font-weight:850}.home-trend-folders-admin{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap;min-height:0}.home-trend-folder-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:10px;min-width:0}.home-trend-folder{position:relative;min-height:158px;overflow:hidden;border:1px solid rgba(190,117,255,.24);border-radius:23px;background:radial-gradient(circle at 80% 12%,rgba(170,74,255,.2),transparent 42%),linear-gradient(145deg,#15101e,#09070d);color:#fff;padding:0;text-align:left;box-shadow:0 16px 38px rgba(0,0,0,.2)}.home-trend-folder-preview{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.52}.home-trend-folder::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(5,3,9,.06),rgba(5,3,9,.9))}.home-trend-folder-card-copy{position:absolute;z-index:2;inset:auto 13px 13px;display:grid;gap:5px}.home-trend-folder-card-copy strong{font-size:18px;line-height:1.05}.home-trend-folder-card-copy small{color:rgba(255,255,255,.72);font-size:11px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.home-trend-folder-meta,.home-trend-folder-item-meta{display:flex;gap:5px;flex-wrap:wrap}.home-trend-folder-meta span,.home-trend-folder-item-meta span{padding:5px 7px;border-radius:999px;border:1px solid rgba(225,192,255,.18);background:rgba(12,8,18,.62);color:#ead8f8;font-size:9px;font-weight:850}.home-trend-folder-tabs{display:grid;grid-template-columns:1fr 1fr;gap:7px;padding:4px;border:1px solid rgba(255,255,255,.08);border-radius:17px;background:#0c0a0f}.home-trend-folder-tabs button{min-height:42px;border:0;border-radius:13px;background:transparent;color:#9d95a7;font-weight:850}.home-trend-folder-tabs button.active{background:linear-gradient(135deg,rgba(159,72,255,.88),rgba(207,94,255,.82));color:#fff;box-shadow:0 8px 24px rgba(165,72,255,.18)}.home-trend-folder-items{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;overflow:visible;padding:2px 0 8px;min-width:0}.home-trend-folder-item{position:relative;aspect-ratio:3/4;min-height:0;min-width:0;overflow:hidden;border:1px solid rgba(185,105,255,.28);border-radius:22px;background:#0b0910;color:#fff;box-shadow:0 18px 42px rgba(0,0,0,.24)}.home-trend-folder-item-open{position:absolute;inset:0;width:100%;padding:0;border:0;background:transparent;color:inherit;text-align:left}.home-trend-folder-media{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;background:#0b0910}.home-trend-folder-item-open::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.04) 28%,rgba(4,3,7,.88) 100%);pointer-events:none}.home-trend-folder-item-copy{position:absolute;z-index:2;left:14px;right:14px;bottom:14px;display:grid;gap:6px}.home-trend-folder-item-copy strong{font-size:18px;line-height:1.05}.home-trend-folder-item-copy small{color:rgba(255,255,255,.72);font-size:11px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.home-trend-folders-empty{padding:17px;border:1px dashed rgba(190,130,255,.26);border-radius:20px;color:var(--muted);background:rgba(16,12,22,.72)}.home-trend-folders-error{padding:11px 13px;border-radius:14px;background:rgba(255,80,120,.1);color:#ffc6d3}

        .home-trend-folder-row{display:grid;grid-template-columns:minmax(0,1fr);gap:8px;min-width:0}
        .home-trend-folders .home-trend-folder-grid{gap:20px}
        .home-trend-folders .home-trend-folder-row>.home-trend-folder{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;width:100%;min-height:100px;padding:13px}
        .home-trend-folder-row .home-trend-folder-card-copy{position:relative;inset:auto;min-width:0;flex:1}
        .home-trend-folder-row .home-trend-folder-card-copy strong{overflow-wrap:anywhere}
        .home-trend-folder-view-all{position:relative;z-index:2;align-self:center;flex-shrink:0;padding:8px 11px;border:1px solid rgba(255,255,255,.2);border-radius:999px;background:#17131d;font-size:12px;font-weight:850}
        .trend-collection-preview-track{display:grid;grid-auto-flow:column;grid-auto-columns:clamp(126px,44%,188px);gap:10px;overflow-x:auto;overscroll-behavior-x:contain;scroll-snap-type:x proximity;min-width:0;padding:2px 0 6px}
        .trend-collection-preview-card{position:relative;isolation:isolate;display:flex;align-items:flex-end;aspect-ratio:3/4;box-sizing:border-box;min-width:0;overflow:hidden;border:1px solid rgba(185,105,255,.28);border-radius:18px;background:#1a1222;color:#fff;text-decoration:none;padding:10px;scroll-snap-align:start}
        .trend-collection-preview-card::after{content:"";position:absolute;inset:0;z-index:-1;background:linear-gradient(transparent 35%,rgba(8,5,12,.94));pointer-events:none}
        .trend-collection-preview-media{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:-2}
        .trend-collection-preview-card strong{font-size:14px;overflow-wrap:anywhere}
        .trend-collection-preview-kind{position:absolute;top:8px;right:8px;background:#17131d;border-radius:8px;padding:4px 7px;font-size:11px}
        .trend-collection-preview-status{grid-column:1/-1;min-height:72px;display:flex;align-items:center;color:var(--muted);font-size:12px}
      `}</style>

      {selected ? <div className="home-trend-folders-head">
        <div className="home-trend-folders-copy">
          <h2>{selected.title}</h2>
          {selected.description ? <p>{selected.description}</p> : null}
        </div>
        <div className="home-trend-folders-actions">
          <button className="home-trend-folders-back" type="button" onClick={() => { setSelectedId(""); setItems([]); }}>← Назад</button>
          <TrendCollectionAdmin onChanged={refreshCollections} />
        </div>
      </div> : <div className="home-trend-folders-admin" aria-label="Управление шаблонами и категориями">
        <TrendCollectionAdmin onChanged={refreshCollections} />
        <TrendCategoryAdmin onChanged={refreshCollections} />
      </div>}

      {error ? <div className="home-trend-folders-error" role="alert">{error}</div> : null}

      {!selected ? loadingCollections ? <div className="home-trend-folders-empty">Загружаю категории…</div> : collections.length ? <div className="home-trend-folder-grid">
        {collections.map((folder) => <section key={folder.id} className="home-trend-folder-row" aria-label={folder.title}>
          <button className="home-trend-folder" type="button" onClick={() => openFolder(folder)}>
          {folder.preview_url ? <TrendPreviewMedia className="home-trend-folder-preview" mediaType={folder.preview_media_type} url={folder.preview_url} thumbnailUrl={folder.preview_thumbnail_url} /> : null}
          <span className="home-trend-folder-card-copy">
            <strong>{folder.title}</strong>
            {folder.description ? <small>{folder.description}</small> : null}
            <span className="home-trend-folder-meta">
              <span>{countLabel(Number(folder.item_count || 0))}</span>
              <span>Фото {folder.photo_count || 0}</span>
              <span>Видео {folder.video_count || 0}</span>
            </span>
          </span>
          <span className="home-trend-folder-view-all">Все →</span>
          </button>
          {Number(folder.item_count || 0) > 0 ? <CollectionPreview folder={folder} /> : null}
        </section>)}
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
