"use client";

import { createPortal } from "react-dom";
import { useCallback, useEffect, useMemo, useState } from "react";

import { haptic } from "@/lib/telegram";
import { trendCollectionsApi, type TrendCollection } from "@/lib/trend-collections-api";
import { trendUsageLabel } from "@/lib/trend-usage";
import type { TrendItem } from "@/lib/types";

function catalogScreen(): HTMLElement | null {
  for (const node of Array.from(document.querySelectorAll<HTMLElement>(".main-shell > .screen"))) {
    const kicker = node.querySelector<HTMLElement>(".screen-head .kicker")?.textContent?.trim();
    if (kicker === "Каталог" || node.classList.contains("roxy-catalog-feature-mode")) return node;
  }
  return null;
}

function ensureHost(): HTMLElement | null {
  const catalog = catalogScreen();
  if (!catalog) return null;
  const existing = catalog.querySelector<HTMLElement>(":scope > #roxy-catalog-trend-folders");
  if (existing) return existing;
  const liveTrends = catalog.querySelector<HTMLElement>(":scope > #roxy-live-trends");
  if (!liveTrends) return null;
  const host = document.createElement("div");
  host.id = "roxy-catalog-trend-folders";
  host.dataset.trendFolders = "catalog";
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
  const value = Number(trend.cost_rox || 0);
  return Number.isFinite(value) ? `${value.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ROX` : "—";
}

export function CatalogTrendFolders() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [collections, setCollections] = useState<TrendCollection[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [mediaType, setMediaType] = useState<"image" | "video">("image");
  const [items, setItems] = useState<TrendItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let frame = 0;
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setHost(ensureHost()));
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, []);

  useEffect(() => {
    if (!host) return;
    let alive = true;
    setLoading(true);
    void trendCollectionsApi.list()
      .then((response) => {
        if (!alive) return;
        setCollections((response.items || []).filter((folder) => folder.system_key !== "trends"));
        setError("");
      })
      .catch((cause) => {
        if (!alive) return;
        setCollections([]);
        setError(cause instanceof Error ? cause.message : "Не удалось загрузить папки трендов");
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [host]);

  const selected = useMemo(() => collections.find((folder) => folder.id === selectedId) || null, [collections, selectedId]);

  const loadItems = useCallback(async (collectionId: string, kind: "image" | "video") => {
    setLoading(true);
    setError("");
    try {
      const response = await trendCollectionsApi.items(collectionId, kind);
      setItems(response.items || []);
    } catch (cause) {
      setItems([]);
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить шаблоны");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId) void loadItems(selectedId, mediaType);
    else setItems([]);
  }, [selectedId, mediaType, loadItems]);

  if (!host) return null;

  return createPortal(
    <section className="home-trend-folders catalog-trend-folders" aria-label="Папки трендов по категориям">
      <style>{`
        #roxy-catalog-trend-folders{margin:0 0 24px}.catalog-trend-folders{display:grid;gap:13px}.catalog-trend-folders .home-trend-folder-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.catalog-trend-folders .home-trend-folder{position:relative;min-height:158px;overflow:hidden;border:1px solid rgba(190,117,255,.24);border-radius:23px;background:radial-gradient(circle at 80% 12%,rgba(170,74,255,.2),transparent 42%),linear-gradient(145deg,#15101e,#09070d);color:#fff;padding:0;text-align:left}.catalog-trend-folders .home-trend-folder-preview{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.52}.catalog-trend-folders .home-trend-folder::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(5,3,9,.06),rgba(5,3,9,.9))}.catalog-trend-folders .home-trend-folder-card-copy{position:absolute;z-index:2;inset:auto 13px 13px;display:grid;gap:5px}.catalog-trend-folders .home-trend-folder-meta,.catalog-trend-folders .home-trend-folder-item-meta{display:flex;gap:5px;flex-wrap:wrap}.catalog-trend-folders .home-trend-folder-meta span,.catalog-trend-folders .home-trend-folder-item-meta span{padding:5px 7px;border-radius:999px;border:1px solid rgba(225,192,255,.18);background:rgba(12,8,18,.62);color:#ead8f8;font-size:9px;font-weight:850}.catalog-trend-folders .home-trend-folder-tabs{display:grid;grid-template-columns:1fr 1fr;gap:7px;padding:4px;border:1px solid rgba(255,255,255,.08);border-radius:17px;background:#0c0a0f}.catalog-trend-folders .home-trend-folder-tabs button{min-height:42px;border:0;border-radius:13px;background:transparent;color:#9d95a7;font-weight:850}.catalog-trend-folders .home-trend-folder-tabs button.active{background:linear-gradient(135deg,rgba(159,72,255,.88),rgba(207,94,255,.82));color:#fff}.catalog-trend-folders .home-trend-folder-items{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(210px,76vw);gap:12px;overflow-x:auto;padding:2px 2px 8px}.catalog-trend-folders .home-trend-folder-item{position:relative;min-height:268px;overflow:hidden;border:1px solid rgba(185,105,255,.28);border-radius:25px;background:#0b0910}.catalog-trend-folders .home-trend-folder-item-open{position:absolute;inset:0;width:100%;padding:0;border:0;background:transparent;color:#fff;text-align:left}.catalog-trend-folders .home-trend-folder-media{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.catalog-trend-folders .home-trend-folder-item-copy{position:absolute;z-index:2;left:14px;right:14px;bottom:14px;display:grid;gap:6px}.catalog-trend-folders .home-trend-folders-empty{padding:17px;border:1px dashed rgba(190,130,255,.26);border-radius:20px;color:var(--muted)}@media(min-width:720px){.catalog-trend-folders .home-trend-folder-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
      `}</style>
      <div className="home-trend-folders-head">
        <div className="home-trend-folders-copy"><span className="kicker">Категории</span><h2>{selected?.title || "Папки трендов"}</h2><p>{selected?.description || "Праздники и тематические подборки."}</p></div>
        {selected ? <button className="home-trend-folders-back" type="button" onClick={() => setSelectedId("")}>← Папки</button> : null}
      </div>
      {error ? <div className="home-trend-folders-error" role="alert">{error}</div> : null}
      {!selected ? loading ? <div className="home-trend-folders-empty">Загружаю категории…</div> : collections.length ? <div className="home-trend-folder-grid">
        {collections.map((folder) => <button className="home-trend-folder" type="button" key={folder.id} onClick={() => { haptic("light"); setSelectedId(folder.id); setMediaType(Number(folder.photo_count || 0) > 0 || Number(folder.video_count || 0) === 0 ? "image" : "video"); }}>
          {folder.preview_url ? <img className="home-trend-folder-preview" src={folder.preview_url} alt="" loading="lazy" /> : null}
          <span className="home-trend-folder-card-copy"><strong>{folder.title}</strong>{folder.description ? <small>{folder.description}</small> : null}<span className="home-trend-folder-meta"><span>{countLabel(Number(folder.item_count || 0))}</span><span>Фото {folder.photo_count || 0}</span><span>Видео {folder.video_count || 0}</span></span></span>
        </button>)}
      </div> : <div className="home-trend-folders-empty">Категории скоро появятся здесь.</div> : <>
        <div className="home-trend-folder-tabs" role="tablist" aria-label="Тип шаблона"><button className={mediaType === "image" ? "active" : ""} role="tab" aria-selected={mediaType === "image"} type="button" onClick={() => setMediaType("image")}>Фото · {selected.photo_count || 0}</button><button className={mediaType === "video" ? "active" : ""} role="tab" aria-selected={mediaType === "video"} type="button" onClick={() => setMediaType("video")}>Видео · {selected.video_count || 0}</button></div>
        {loading ? <div className="home-trend-folders-empty">Загружаю шаблоны…</div> : items.length ? <div className="home-trend-folder-items">{items.map((trend) => <article className="home-trend-folder-item" key={trend.id}><button type="button" className="home-trend-folder-item-open" onClick={() => window.location.assign(`/mini-app/trend/?id=${encodeURIComponent(trend.id)}`)}>{trend.preview_url ? trend.media_type === "video" ? <video className="home-trend-folder-media" src={trend.preview_url} muted autoPlay loop playsInline preload="metadata" /> : <img className="home-trend-folder-media" src={trend.preview_url} alt="" loading="lazy" /> : null}<span className="home-trend-folder-item-copy"><strong>{trend.title}</strong><span className="home-trend-folder-item-meta"><span>{trendUsageLabel(trend.usage_count)}</span><span>{trend.media_type === "video" ? "Видео" : "Фото"}</span><span>{price(trend)}</span></span></span></button></article>)}</div> : <div className="home-trend-folders-empty">В этой вкладке пока нет шаблонов.</div>}
      </>}
    </section>,
    host,
  );
}
