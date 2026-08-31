"use client";

import { createPortal } from "react-dom";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { haptic, telegramHeaders } from "@/lib/telegram";
import { trendUsageLabel } from "@/lib/trend-usage";
import type { TrendItem } from "@/lib/types";

function catalogScreen(): HTMLElement | null {
  for (const node of Array.from(document.querySelectorAll<HTMLElement>(".main-shell > .screen"))) {
    const kicker = node.querySelector<HTMLElement>(".screen-head .kicker")?.textContent?.trim();
    if (kicker === "Каталог" || node.classList.contains("roxy-catalog-feature-mode")) return node;
  }
  return null;
}

function homeScreen(): HTMLElement | null {
  return document.querySelector<HTMLElement>(".home-screen");
}

function ensureCatalogHost(screen: HTMLElement): HTMLElement {
  const existing = screen.querySelector<HTMLElement>("#roxy-live-trends");
  if (existing) return existing;
  const host = document.createElement("div");
  host.id = "roxy-live-trends";
  host.dataset.liveTrends = "catalog";
  const promo = screen.querySelector<HTMLElement>(":scope > .promo-carousel");
  if (promo) promo.insertAdjacentElement("afterend", host);
  else {
    const featureHub = screen.querySelector("#roxy-catalog-feature-hub");
    if (featureHub?.nextSibling) screen.insertBefore(host, featureHub.nextSibling);
    else screen.appendChild(host);
  }
  return host;
}

function ensureHomeHost(screen: HTMLElement): HTMLElement | null {
  const existing = screen.querySelector<HTMLElement>("#roxy-home-live-trends");
  if (existing) return existing;
  const promo = screen.querySelector<HTMLElement>(":scope > .promo-slider");
  if (!promo) return null;
  const host = document.createElement("div");
  host.id = "roxy-home-live-trends";
  host.dataset.liveTrends = "home";
  promo.insertAdjacentElement("afterend", host);
  return host;
}

function key(prefix: string): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return `${prefix}:${crypto.randomUUID()}`;
  return `${prefix}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
}

async function deleteTrend(id: string): Promise<void> {
  const response = await fetch(`/api/v1/inline-admin/trends/${encodeURIComponent(id)}`, {
    method: "DELETE",
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      ...telegramHeaders(false),
      "Idempotency-Key": key("trend-delete"),
      "X-Request-Id": key("trend-ui"),
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail ?? payload?.message ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
}

function price(trend: TrendItem): string {
  if (trend.admin_free || trend.cost_rox === "0.00" || trend.cost_rox === "0") return "Бесплатно";
  if (!trend.cost_rox) return "—";
  const value = Number(trend.cost_rox);
  return Number.isFinite(value) ? `${value.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ROX` : `${trend.cost_rox} ROX`;
}

function mediaLabel(trend: TrendItem): string {
  if (trend.media_type === "video") return "Видео";
  if (trend.media_type === "audio") return "Музыка";
  return "Фото";
}

type TrendHosts = {
  home: HTMLElement | null;
  catalog: HTMLElement | null;
};

export function LiveTrendRail() {
  const [hosts, setHosts] = useState<TrendHosts>({ home: null, catalog: null });
  const [trends, setTrends] = useState<TrendItem[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let frame = 0;
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const home = homeScreen();
        const catalog = catalogScreen();
        const next = {
          home: home ? ensureHomeHost(home) : null,
          catalog: catalog ? ensureCatalogHost(catalog) : null,
        };
        setHosts((current) => (
          current.home === next.home && current.catalog === next.catalog ? current : next
        ));
      });
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, []);

  const refresh = useCallback(async () => {
    try {
      const payload = await api.trends();
      setTrends(payload.items || []);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить сценарии");
    }
  }, []);

  useEffect(() => {
    if (!hosts.home && !hosts.catalog) return;
    void refresh();
    void api.me().then((me) => setIsAdmin(Boolean(me.is_admin))).catch(() => setIsAdmin(false));
  }, [hosts.home, hosts.catalog, refresh]);

  const remove = async (trend: TrendItem) => {
    if (!isAdmin || busyId) return;
    if (!window.confirm(`Удалить «${trend.title}» навсегда?`)) return;
    setBusyId(trend.id);
    setError("");
    try {
      await deleteTrend(trend.id);
      setTrends((current) => current.filter((item) => item.id !== trend.id));
      haptic("medium");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось удалить тренд");
    } finally {
      setBusyId("");
    }
  };

  const section = (scope: "home" | "catalog") => (
    <section className="live-trend-section" aria-label={scope === "home" ? "Актуальные тренды ROXY" : "Живые тренды ROXY"}>
      <style>{`
        .live-trend-section { display:grid; gap:12px; margin:20px 0 24px; min-width:0; }
        #roxy-home-live-trends .live-trend-section { margin:16px 0 18px; }
        .live-trend-section .section-title { display:flex; align-items:end; justify-content:space-between; gap:12px; }
        .live-trend-section .section-title h2 { margin:4px 0 0; font-size:25px; line-height:1; letter-spacing:-.04em; }
        .live-trend-rail { display:grid; grid-auto-flow:column; grid-auto-columns:minmax(210px, 76vw); gap:12px; overflow-x:auto; overscroll-behavior-x:contain; scroll-snap-type:x proximity; padding:2px 2px 8px; scrollbar-width:none; }
        .live-trend-rail::-webkit-scrollbar { display:none; }
        .live-trend-card { position:relative; min-height:280px; overflow:hidden; border:1px solid rgba(185,105,255,.28); border-radius:26px; background:#0b0910; color:#fff; scroll-snap-align:start; box-shadow:0 18px 42px rgba(0,0,0,.24); }
        .live-trend-open { position:absolute; inset:0; width:100%; padding:0; border:0; background:transparent; color:inherit; text-align:left; }
        .live-trend-media { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; background:#0b0910; }
        .live-trend-open::after { content:""; position:absolute; inset:0; background:linear-gradient(180deg,rgba(0,0,0,.04) 28%,rgba(4,3,7,.86) 100%); pointer-events:none; }
        .live-trend-copy { position:absolute; z-index:2; left:15px; right:15px; bottom:15px; display:grid; gap:6px; }
        .live-trend-copy strong { font-size:18px; line-height:1.05; }
        .live-trend-copy small { color:rgba(255,255,255,.72); font-size:11px; line-height:1.35; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
        .live-trend-meta { display:flex; flex-wrap:wrap; gap:6px; }
        .live-trend-meta span { padding:5px 8px; border-radius:999px; background:rgba(15,10,22,.66); border:1px solid rgba(220,180,255,.22); backdrop-filter:blur(10px); color:#efdfff; font-size:9px; font-weight:850; }
        .live-trend-delete { position:absolute; z-index:4; top:10px; right:10px; min-width:38px; height:38px; padding:0 10px; border:1px solid rgba(255,115,150,.35); border-radius:999px; background:rgba(22,8,14,.74); color:#ffd7df; backdrop-filter:blur(12px); font-weight:900; }
        .live-trend-empty { padding:18px; border:1px dashed rgba(190,130,255,.26); border-radius:22px; color:var(--muted); background:rgba(16,12,22,.72); }
        @media (min-width:720px) { .live-trend-rail { grid-auto-columns:minmax(230px, 310px); } }
      `}</style>
      <div className="section-title">
        <div><span className="kicker">Тренды</span><h2>Актуальные тренды</h2></div>
      </div>
      {error ? <div className="inline-trend-error" role="alert">{error}</div> : null}
      {trends.length ? <div className="live-trend-rail">
        {trends.map((trend) => (
          <article className="live-trend-card" key={trend.id}>
            <button className="live-trend-open" type="button" onClick={() => { haptic("light"); window.location.assign(`/mini-app/trend/?id=${encodeURIComponent(trend.id)}`); }}>
              {trend.preview_url ? trend.media_type === "video"
                ? <video className="live-trend-media" src={trend.preview_url} muted autoPlay loop playsInline preload="metadata" />
                : <img className="live-trend-media" src={trend.preview_url} alt="" loading="lazy" />
                : null}
              <span className="live-trend-copy">
                <strong>{trend.title}</strong>
                {trend.description ? <small>{trend.description}</small> : null}
                <span className="live-trend-meta"><span>{trendUsageLabel(trend.usage_count)}</span><span>{mediaLabel(trend)}</span><span>{price(trend)}</span>{trend.billing_seconds ? <span>{trend.billing_seconds} сек</span> : null}</span>
              </span>
            </button>
            {isAdmin ? <button className="live-trend-delete" type="button" aria-label={`Удалить ${trend.title}`} onClick={() => void remove(trend)}>{busyId === trend.id ? "…" : "Удалить"}</button> : null}
          </article>
        ))}
      </div> : <div className="live-trend-empty">Новые сценарии скоро появятся здесь.</div>}
    </section>
  );

  return (
    <>
      {hosts.home ? createPortal(section("home"), hosts.home, "roxy-home-live-trends") : null}
      {hosts.catalog ? createPortal(section("catalog"), hosts.catalog, "roxy-catalog-live-trends") : null}
    </>
  );
}
