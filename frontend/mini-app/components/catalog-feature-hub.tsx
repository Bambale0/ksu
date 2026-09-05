"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "@/lib/api";
import { haptic } from "@/lib/telegram";
import type { PromptToolCatalogItem } from "@/lib/types";
import { Icon, type IconName } from "./icons";

type MediaKind = "image" | "video" | "audio";
type CatalogRoute = "create" | "feed" | "history" | "partners" | "profile";

type CatalogFeature = {
  id: string;
  title: string;
  copy: string;
  icon: IconName;
  badge?: string;
  price?: string | null;
  href?: string;
  route?: CatalogRoute;
  media?: MediaKind;
};

const MEDIA_FILTER_KEY = "ksu-selected-media";
const SEEDANCE_MIN_PRICE_ROX = 30;

function catalogScreen(): HTMLElement | null {
  for (const node of Array.from(document.querySelectorAll<HTMLElement>(".main-shell > .screen"))) {
    if (node.classList.contains("roxy-catalog-feature-mode")) return node;
    const kicker = node.querySelector<HTMLElement>(".screen-head .kicker")?.textContent?.trim();
    if (kicker === "Каталог") return node;
  }
  return null;
}

function ensureHost(): HTMLElement | null {
  const screen = catalogScreen();
  if (!screen) return null;
  screen.classList.add("roxy-catalog-feature-mode");

  const existing = screen.querySelector<HTMLElement>("#roxy-catalog-feature-hub");
  if (existing) return existing;

  const host = document.createElement("div");
  host.id = "roxy-catalog-feature-hub";
  host.dataset.catalogFeatureHub = "true";

  const promo = screen.querySelector(".promo-carousel");
  if (promo?.nextSibling) screen.insertBefore(host, promo.nextSibling);
  else screen.insertBefore(host, screen.firstChild);
  return host;
}

function price(tool?: PromptToolCatalogItem): string | null {
  if (!tool?.enabled) return null;
  if (tool.admin_free || tool.cost_credits === "0.00" || tool.cost_credits === "0") return "Бесплатно";
  return tool.cost_credits
    ? `${Number(tool.cost_credits).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ROX`
    : null;
}

function navigateToRoute(route: CatalogRoute, media?: MediaKind) {
  if (media) localStorage.setItem(MEDIA_FILTER_KEY, media);
  const url = new URL(window.location.href);
  url.searchParams.set("route", route);
  url.searchParams.delete("generation");
  url.searchParams.delete("action");
  url.searchParams.delete("action_context_id");
  window.history.pushState({ roxyRoute: route }, "", `${url.pathname}${url.search}${url.hash}`);
  window.dispatchEvent(new Event("popstate"));
  window.scrollTo({ top: 0, behavior: "auto" });
}

function openFeature(feature: CatalogFeature) {
  haptic(feature.route === "create" ? "medium" : "light");
  if (feature.href) {
    window.location.assign(feature.href);
    return;
  }
  if (feature.route) navigateToRoute(feature.route, feature.media);
}

export function CatalogFeatureHub() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [tools, setTools] = useState<PromptToolCatalogItem[]>([]);

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

  useEffect(() => {
    if (!host) return;
    let active = true;
    void api.promptTools()
      .then((payload) => {
        if (active) setTools((payload.items || []).filter((item) => item.enabled));
      })
      .catch(() => {
        if (active) setTools([]);
      });
    return () => { active = false; };
  }, [host]);

  const features = useMemo<CatalogFeature[]>(() => {
    const byId = new Map(tools.map((tool) => [tool.id, tool]));
    const imageTool = byId.get("prompt_builder") || byId.get("image_analysis");
    const videoTool = byId.get("video_prompt");

    return [
      {
        id: "create-image",
        title: "Создать фото",
        copy: "Генерация и редактирование изображений",
        icon: "image",
        badge: "Создать",
        route: "create",
        media: "image",
      },
      {
        id: "create-video",
        title: "Создать видео",
        copy: "Ролики из описания, фото или готового кадра",
        icon: "video",
        badge: "Создать",
        route: "create",
        media: "video",
      },
      {
        id: "create-audio",
        title: "Создать музыку",
        copy: "Песни и аудио для ваших идей",
        icon: "music",
        badge: "Создать",
        route: "create",
        media: "audio",
      },
      {
        id: "pinterest-repeat",
        title: "Повтори фото",
        copy: "Сцена, свет и поза из Pinterest — с вашей внешностью",
        icon: "image",
        badge: "Новое",
        href: "/mini-app/pinterest-repeat/",
      },
      {
        id: "prompt-image",
        title: "Описание по фото",
        copy: "Разобрать фото или усилить идею перед генерацией",
        icon: "spark",
        href: "/mini-app/prompt-tools/?mode=image",
        price: price(imageTool),
      },
      {
        id: "prompt-video",
        title: "Описание по видео",
        copy: "Камера, движение, сцена и динамика ролика",
        icon: "video",
        href: "/mini-app/prompt-tools/?mode=video",
        price: price(videoTool),
      },
      {
        id: "prompt-seedance",
        title: "Сценарий для видео",
        copy: "Сцена, камера, движение и детали в готовой структуре",
        icon: "spark",
        href: "/mini-app/prompt-tools/?mode=seedance",
        price: imageTool?.enabled ? `от ${SEEDANCE_MIN_PRICE_ROX} ROX` : null,
      },
      {
        id: "batch",
        title: "Пакетная обработка",
        copy: "Несколько генераций одной задачей",
        icon: "catalog",
        href: "/mini-app/batch/",
      },
      {
        id: "feed",
        title: "Лента",
        copy: "Публичные работы, реакции и повторы",
        icon: "heart",
        route: "feed",
      },
      {
        id: "partners",
        title: "Партнёры",
        copy: "Реферальная ссылка, выплаты и статистика",
        icon: "share",
        route: "partners",
      },
      {
        id: "history",
        title: "История",
        copy: "Все готовые работы и активные задачи",
        icon: "history",
        route: "history",
      },
      {
        id: "profile",
        title: "Профиль",
        copy: "Публикации, работы и баланс аккаунта",
        icon: "profile",
        route: "profile",
      },
    ];
  }, [tools]);

  if (!host) return null;

  return createPortal(
    <section className="catalog-feature-hub" aria-label="Фичи ROXY">
      <style>{`
        .catalog-feature-hub {
          display: grid;
          gap: 18px;
          margin: 18px 0 26px;
          max-width: 100%;
          min-width: 0;
        }
        .catalog-feature-hero {
          min-width: 0;
          padding: 22px;
          border-radius: 28px;
          border: 1px solid rgba(177, 92, 255, 0.28);
          background: radial-gradient(circle at 0% 0%, rgba(188, 99, 255, 0.18), transparent 34%), rgba(15, 12, 22, 0.82);
          box-shadow: 0 18px 46px rgba(0, 0, 0, 0.26);
        }
        .catalog-feature-hero h1 {
          margin: 7px 0 8px;
          font-size: clamp(32px, 8vw, 52px);
          line-height: 0.92;
          letter-spacing: -0.06em;
        }
        .catalog-feature-hero p {
          margin: 0;
          max-width: 520px;
          color: var(--muted);
          font-size: 15px;
          line-height: 1.45;
        }
        .catalog-feature-section {
          display: grid;
          gap: 12px;
          min-width: 0;
        }
        .catalog-feature-section-title {
          display: flex;
          align-items: end;
          justify-content: space-between;
          gap: 12px;
        }
        .catalog-feature-section-title h2 {
          margin: 4px 0 0;
          font-size: 25px;
          line-height: 1;
          letter-spacing: -0.04em;
        }
        .catalog-feature-grid {
          display: grid;
          grid-template-columns: minmax(0, 1fr);
          gap: 12px;
          min-width: 0;
        }
        .catalog-feature-card {
          width: 100%;
          min-width: 0;
          display: grid;
          grid-template-columns: auto minmax(0, 1fr) auto;
          align-items: center;
          gap: 14px;
          padding: 18px;
          min-height: 92px;
          border-radius: 24px;
          border: 1px solid rgba(177, 92, 255, 0.28);
          background: rgba(14, 12, 20, 0.92);
          color: inherit;
          text-align: left;
          text-decoration: none;
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
        }
        .catalog-feature-card:active {
          transform: translateY(1px) scale(0.995);
        }
        .catalog-feature-card strong {
          display: block;
          overflow-wrap: anywhere;
          font-size: 19px;
          line-height: 1.05;
        }
        .catalog-feature-card small {
          display: block;
          overflow-wrap: anywhere;
          margin-top: 7px;
          color: var(--muted);
          font-size: 13px;
          line-height: 1.35;
        }
        .catalog-feature-icon {
          width: 58px;
          height: 58px;
          border-radius: 18px;
          display: grid;
          place-items: center;
          color: white;
          border: 1px solid rgba(214, 134, 255, 0.36);
          background: linear-gradient(145deg, rgba(178, 75, 255, 0.45), rgba(68, 35, 104, 0.78));
          box-shadow: 0 12px 30px rgba(159, 73, 255, 0.18);
        }
        .catalog-feature-pill {
          align-self: center;
          padding: 7px 11px;
          border-radius: 999px;
          color: #f3d9ff;
          background: rgba(149, 75, 232, 0.20);
          font-weight: 800;
          font-size: 12px;
          white-space: nowrap;
        }
        @media (max-width: 360px) {
          .catalog-feature-hero {
            padding: 18px;
            border-radius: 22px;
          }
          .catalog-feature-card {
            grid-template-columns: 46px minmax(0, 1fr);
            gap: 10px;
            padding: 14px;
            border-radius: 20px;
          }
          .catalog-feature-icon {
            width: 46px;
            height: 46px;
            border-radius: 15px;
          }
          .catalog-feature-pill {
            grid-column: 2;
            justify-self: start;
            white-space: normal;
          }
        }
      `}</style>

      <div className="catalog-feature-hero">
        <span className="kicker">Каталог</span>
        <h1>Все фичи ROXY</h1>
        <p>Каталог — это навигация по возможностям бота. Выбор конкретной модели остаётся в разделе «Создать».</p>
      </div>

      <div className="catalog-feature-section">
        <div className="catalog-feature-section-title">
          <div><span className="kicker">Быстрый старт</span><h2>Создание</h2></div>
        </div>
        <div className="catalog-feature-grid">
          {features.slice(0, 3).map((feature) => <FeatureCard key={feature.id} feature={feature} />)}
        </div>
      </div>

      <div className="catalog-feature-section">
        <div className="catalog-feature-section-title">
          <div><span className="kicker">Инструменты</span><h2>Помощники и режимы</h2></div>
        </div>
        <div className="catalog-feature-grid">
          {features.slice(3).map((feature) => <FeatureCard key={feature.id} feature={feature} />)}
        </div>
      </div>
    </section>,
    host,
  );
}

function FeatureCard({ feature }: { feature: CatalogFeature }) {
  return (
    <button className="catalog-feature-card" type="button" onClick={() => openFeature(feature)} data-catalog-feature={feature.id}>
      <span className="catalog-feature-icon"><Icon name={feature.icon} /></span>
      <span><strong>{feature.title}</strong><small>{feature.copy}</small></span>
      <span className="catalog-feature-pill">{feature.price || feature.badge || "Открыть"}</span>
    </button>
  );
}