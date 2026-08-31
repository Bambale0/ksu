"use client";

import { createPortal } from "react-dom";
import { useCallback, useEffect, useMemo, useState } from "react";

import { TrendCollectionAdmin } from "@/components/trend-collection-admin";
import { api } from "@/lib/api";
import { haptic } from "@/lib/telegram";
import {
  trendCollectionsApi,
  type TrendCollection,
} from "@/lib/trend-collections-api";
import { trendUsageLabel } from "@/lib/trend-usage";
import type { TrendItem } from "@/lib/types";

function catalogScreen(): HTMLElement | null {
  for (const node of Array.from(document.querySelectorAll<HTMLElement>(".main-shell > .screen"))) {
    const kicker = node.querySelector<HTMLElement>(".screen-head .kicker")?.textContent?.trim();
    if (kicker === "Каталог" || node.classList.contains("roxy-catalog-feature-mode")) return node;
  }
  return null;
}

function ensureHost(screen: HTMLElement): HTMLElement {
  const existing = screen.querySelector<HTMLElement>("#roxy-live-trends");
  if (existing) return existing;
  const host = document.createElement("div");
  host.id = "roxy-live-trends";
  host.dataset.liveTrends = "true";
  const featureHub = screen.querySelector("#roxy-catalog-feature-hub");
  if (featureHub?.nextSibling) screen.insertBefore(host, featureHub.nextSibling);
  else screen.appendChild(host);
  return host;
}

function price(trend: TrendItem): string {
  if (trend.admin_free || trend.cost_rox === "0.00" || trend.cost_rox === "0") return "Бесплатно";
  if (!trend.cost_rox) return "—";
  const value = Number(trend.cost_rox);
  return Number.isFinite(value)
    ? `${value.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ROX`
    : `${trend.cost_rox} ROX`;
}

function mediaLabel(trend: TrendItem): string {
  return trend.media_type === "video" ? "Видео" : "Фото";
}

function folderCount(folder: TrendCollection): string {
  if (folder.system_key === "ai_reference") return "3 инструмента";
  const count = Number(folder.item_count || 0);
  if (count === 1) return "1 шаблон";
  if (count > 1 && count < 5) return `${count} шаблона`;
  return `${count} шаблонов`;
}

function TrendCards({ trends }: { trends: TrendItem[] }) {
  return <div className="template-trend-rail">
    {trends.map((trend) => <article className="template-trend-card" key={trend.id}>
      <button
        className="template-trend-open"
        type="button"
        data-trend-launch="true"
        onClick={() => {
          haptic("light");
          window.location.assign(`/mini-app/trend/?id=${encodeURIComponent(trend.id)}`);
        }}
      >
        {trend.preview_url ? trend.media_type === "video"
          ? <video className="template-trend-media" src={trend.preview_url} muted autoPlay loop playsInline preload="metadata" />
          : <img className="template-trend-media" src={trend.preview_url} alt="" loading="lazy" />
          : null}
        <span className="template-trend-copy">
          <strong>{trend.title}</strong>
          {trend.description ? <small>{trend.description}</small> : null}
          <span className="template-trend-meta">
            <span>{trendUsageLabel(trend.usage_count)}</span>
            <span>{mediaLabel(trend)}</span>
            <span>{price(trend)}</span>
            {trend.billing_seconds ? <span>{trend.billing_seconds} сек</span> : null}
          </span>
        </span>
      </button>
    </article>)}
  </div>;
}

export function LiveTrendRail() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [collections, setCollections] = useState<TrendCollection[]>([]);
  const [fallbackTrends, setFallbackTrends] = useState<TrendItem[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [mediaType, setMediaType] = useState<"image" | "video">("image");
  const [trends, setTrends] = useState<TrendItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let frame = 0;
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const screen = catalogScreen();
        setHost(screen ? ensureHost(screen) : null);
      });
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, []);

  const loadLegacyFallback = useCallback(async () => {
    try {
      const legacy = await api.trends();
      setFallbackTrends(legacy.items || []);
      setError("");
    } catch (cause) {
      setFallbackTrends([]);
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить шаблоны");
    }
  }, []);

  const refreshCollections = useCallback(async () => {
    try {
      const result = await trendCollectionsApi.list();
      const items = result.items || [];
      setCollections(items);
      if (items.length) {
        setFallbackTrends([]);
        setError("");
      } else {
        await loadLegacyFallback();
      }
    } catch {
      setCollections([]);
      await loadLegacyFallback();
    }
  }, [loadLegacyFallback]);

  useEffect(() => {
    if (!host) return;
    void refreshCollections();
  }, [host, refreshCollections]);

  const selected = useMemo(
    () => collections.find((folder) => folder.id === selectedId) || null,
    [collections, selectedId],
  );

  const loadItems = useCallback(async (collectionId: string, kind: "image" | "video") => {
    setLoading(true);
    setError("");
    try {
      const result = await trendCollectionsApi.items(collectionId, kind);
      setTrends(result.items || []);
    } catch (cause) {
      setTrends([]);
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить шаблоны");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId) void loadItems(selectedId, mediaType);
    else setTrends([]);
  }, [selectedId, mediaType, loadItems]);

  const openFolder = (folder: TrendCollection) => {
    haptic("light");
    if (folder.system_key === "ai_reference") {
      window.location.assign("/mini-app/ai-reference/");
      return;
    }
    setSelectedId(folder.id);
    setMediaType(Number(folder.photo_count || 0) > 0 || Number(folder.video_count || 0) === 0 ? "image" : "video");
  };

  if (!host) return null;

  return createPortal(
    <section className="template-library" aria-label="Библиотека шаблонов ROXY">
      <style>{`
        .template-library{display:grid;gap:14px;margin:20px 0 26px;min-width:0}.template-library-head{display:flex;align-items:end;justify-content:space-between;gap:12px}.template-library-title{display:grid;gap:4px}.template-library-title h2{margin:0;font-size:25px;line-height:1;letter-spacing:-.04em}.template-library-title p{margin:3px 0 0;color:var(--muted);font-size:12px;line-height:1.4}.template-library-actions{display:flex;align-items:center;gap:8px}.template-library-back{border:1px solid rgba(255,255,255,.11);background:#17131d;color:#fff;border-radius:999px;padding:8px 12px;font-weight:800}.template-folder-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.template-folder{position:relative;min-height:156px;overflow:hidden;border:1px solid rgba(185,105,255,.23);border-radius:23px;background:linear-gradient(145deg,#15101e,#09070d);color:#fff;padding:0;text-align:left;box-shadow:0 16px 38px rgba(0,0,0,.2)}.template-folder.is-ai-reference{grid-column:1/-1;min-height:184px;border-color:rgba(211,132,255,.42);background:radial-gradient(circle at 75% 25%,rgba(203,91,255,.3),transparent 42%),linear-gradient(135deg,#171021,#09070d)}.template-folder-preview{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.48}.template-folder::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(5,3,9,.04),rgba(5,3,9,.88))}.template-folder-copy{position:absolute;z-index:2;inset:auto 14px 14px;display:grid;gap:5px}.template-folder-copy strong{font-size:18px;line-height:1.05}.template-folder.is-ai-reference .template-folder-copy strong{font-size:24px}.template-folder-copy small{color:rgba(255,255,255,.72);line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.template-folder-meta{display:flex;gap:6px;flex-wrap:wrap}.template-folder-meta span{padding:5px 8px;border-radius:999px;border:1px solid rgba(225,192,255,.18);background:rgba(12,8,18,.58);color:#ead8f8;font-size:9px;font-weight:850}.template-media-tabs{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:4px;border:1px solid rgba(255,255,255,.08);border-radius:17px;background:#0c0a0f}.template-media-tabs button{min-height:42px;border:0;border-radius:13px;background:transparent;color:#9d95a7;font-weight:850}.template-media-tabs button.active{background:linear-gradient(135deg,rgba(159,72,255,.88),rgba(207,94,255,.82));color:#fff;box-shadow:0 8px 24px rgba(165,72,255,.18)}.template-trend-rail{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(210px,76vw);gap:12px;overflow-x:auto;overscroll-behavior-x:contain;scroll-snap-type:x proximity;padding:2px 2px 8px;scrollbar-width:none}.template-trend-rail::-webkit-scrollbar{display:none}.template-trend-card{position:relative;min-height:280px;overflow:hidden;border:1px solid rgba(185,105,255,.28);border-radius:26px;background:#0b0910;color:#fff;scroll-snap-align:start;box-shadow:0 18px 42px rgba(0,0,0,.24)}.template-trend-open{position:absolute;inset:0;width:100%;padding:0;border:0;background:transparent;color:inherit;text-align:left}.template-trend-media{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;background:#0b0910}.template-trend-open::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.04) 28%,rgba(4,3,7,.86) 100%);pointer-events:none}.template-trend-copy{position:absolute;z-index:2;left:15px;right:15px;bottom:15px;display:grid;gap:6px}.template-trend-copy strong{font-size:18px;line-height:1.05}.template-trend-copy small{color:rgba(255,255,255,.72);font-size:11px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.template-trend-meta{display:flex;flex-wrap:wrap;gap:6px}.template-trend-meta span{padding:5px 8px;border-radius:999px;background:rgba(15,10,22,.66);border:1px solid rgba(220,180,255,.22);backdrop-filter:blur(10px);color:#efdfff;font-size:9px;font-weight:850}.template-library-empty{padding:18px;border:1px dashed rgba(190,130,255,.26);border-radius:22px;color:var(--muted);background:rgba(16,12,22,.72)}.template-library-error{padding:11px 13px;border-radius:14px;background:rgba(255,80,120,.1);color:#ffc6d3}@media(min-width:720px){.template-folder-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.template-folder.is-ai-reference{grid-column:span 2}.template-trend-rail{grid-auto-columns:minmax(230px,310px)}}
      `}</style>

      <div className="template-library-head">
        <div className="template-library-title">
          <span className="kicker">{selected ? "Папка" : "Шаблоны"}</span>
          <h2>{selected?.title || "Выберите, что хотите повторить"}</h2>
          <p>{selected?.description || "Праздники, тренды и готовые AI-сценарии — всё разложено по папкам."}</p>
        </div>
        <div className="template-library-actions">
          {selected ? <button className="template-library-back" type="button" onClick={() => { setSelectedId(""); setTrends([]); }}>← Все папки</button> : null}
          <TrendCollectionAdmin onChanged={refreshCollections} />
        </div>
      </div>

      {error ? <div className="template-library-error" role="alert">{error}</div> : null}

      {!selected ? collections.length ? <div className="template-folder-grid">
        {collections.map((folder) => <button className={`template-folder${folder.system_key === "ai_reference" ? " is-ai-reference" : ""}`} type="button" key={folder.id} onClick={() => openFolder(folder)}>
          {folder.preview_url ? <img className="template-folder-preview" src={folder.preview_url} alt="" loading="lazy" /> : null}
          <span className="template-folder-copy">
            <strong>{folder.title}</strong>
            {folder.description ? <small>{folder.description}</small> : null}
            {folder.system_key === "ai_reference"
              ? <span className="template-folder-meta"><span>{folderCount(folder)}</span><span>Старт работы</span></span>
              : <span className="template-folder-meta"><span>{folderCount(folder)}</span><span>Фото {folder.photo_count || 0}</span><span>Видео {folder.video_count || 0}</span></span>}
          </span>
        </button>)}
      </div> : fallbackTrends.length ? <TrendCards trends={fallbackTrends} /> : <div className="template-library-empty">Папки пока не созданы.</div> : <>
        <div className="template-media-tabs" role="tablist" aria-label="Тип шаблона">
          <button className={mediaType === "image" ? "active" : ""} role="tab" aria-selected={mediaType === "image"} type="button" onClick={() => setMediaType("image")}>Фото · {selected.photo_count || 0}</button>
          <button className={mediaType === "video" ? "active" : ""} role="tab" aria-selected={mediaType === "video"} type="button" onClick={() => setMediaType("video")}>Видео · {selected.video_count || 0}</button>
        </div>

        {loading ? <div className="template-library-empty">Загружаю шаблоны…</div> : trends.length ? <TrendCards trends={trends} /> : <div className="template-library-empty">В этой вкладке пока нет шаблонов.</div>}
      </>}
    </section>,
    host,
  );
}
