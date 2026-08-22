"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "@/lib/api";
import type { PromptToolCatalogItem } from "@/lib/types";
import { Icon, type IconName } from "./icons";

type MediaKind = "image" | "video" | "audio";

type Capability = {
  id: string;
  title: string;
  copy: string;
  icon: IconName;
  href?: string;
  media?: MediaKind;
  price?: string | null;
};

const MEDIA_KEY = "ksu-selected-media";

function price(tool?: PromptToolCatalogItem): string | null {
  if (!tool?.enabled) return null;
  if (tool.admin_free || tool.cost_credits === "0.00" || tool.cost_credits === "0") return "Бесплатно";
  return tool.cost_credits ? `${Number(tool.cost_credits).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ROX` : null;
}

function catalogScreen(): HTMLElement | null {
  for (const node of Array.from(document.querySelectorAll<HTMLElement>(".main-shell > .screen"))) {
    if (node.querySelector<HTMLElement>(".screen-head .kicker")?.textContent?.trim() === "Каталог") return node;
  }
  return null;
}

function ensureHost(): HTMLElement | null {
  const screen = catalogScreen();
  if (!screen) return null;
  const existing = screen.querySelector<HTMLElement>("#roxy-catalog-capabilities");
  if (existing) return existing;
  const host = document.createElement("div");
  host.id = "roxy-catalog-capabilities";
  host.dataset.catalogCapabilities = "true";
  const firstSection = screen.querySelector(".section-title");
  screen.insertBefore(host, firstSection || null);
  return host;
}

function openCreate(media: MediaKind) {
  localStorage.setItem(MEDIA_KEY, media);
  const url = new URL(window.location.href);
  url.searchParams.set("route", "create");
  url.searchParams.delete("generation");
  window.location.assign(`${url.pathname}${url.search}${url.hash}`);
}

function openCatalog() {
  const url = new URL(window.location.href);
  url.searchParams.set("route", "catalog");
  url.searchParams.delete("generation");
  window.location.assign(`${url.pathname}${url.search}${url.hash}`);
}

export function CatalogCapabilities() {
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

    const brand = document.querySelector<HTMLElement>(".topbar .brand");
    const brandHandler = (event: Event) => {
      event.preventDefault();
      event.stopPropagation();
      openCatalog();
    };
    brand?.addEventListener("click", brandHandler, true);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      brand?.removeEventListener("click", brandHandler, true);
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

  const capabilities = useMemo<Capability[]>(() => {
    const byId = new Map(tools.map((tool) => [tool.id, tool]));
    const imageTool = byId.get("prompt_builder") || byId.get("image_analysis");
    const videoTool = byId.get("video_prompt");
    return [
      { id: "create-image", title: "Создать фото", copy: "Все фото-модели и режимы", icon: "image", media: "image" },
      { id: "create-video", title: "Создать видео", copy: "Все видео-модели и режимы", icon: "video", media: "video" },
      { id: "create-audio", title: "Создать музыку", copy: "Аудио-модели ROXY", icon: "music", media: "audio" },
      { id: "prompt-image", title: "Prompt фото / описание", copy: "Разобрать фото или улучшить идею", icon: "spark", href: "/mini-app/prompt-tools.html?mode=image", price: price(imageTool) },
      { id: "prompt-video", title: "Prompt по видео", copy: "Разбор ролика, камера и динамика", icon: "video", href: "/mini-app/prompt-tools.html?mode=video", price: price(videoTool) },
      { id: "prompt-seedance", title: "Prompt для Seedance", copy: "Сцена, камера, движение и negative prompt", icon: "spark", href: "/mini-app/prompt-tools.html?mode=seedance", price: price(imageTool) },
      { id: "batch", title: "Пакетная обработка", copy: "Несколько генераций одной задачей", icon: "catalog", href: "/mini-app/batch.html" },
    ];
  }, [tools]);

  if (!host) return null;

  return createPortal(
    <section className="catalog-capabilities" aria-label="Возможности ROXY">
      <div className="section-title">
        <div><span className="kicker">Возможности</span><h2>Все инструменты ROXY</h2></div>
      </div>
      <div className="model-grid catalog-capability-grid">
        {capabilities.map((item) => {
          const content = <><span className="model-icon"><Icon name={item.icon}/></span><div><strong>{item.title}</strong><small>{item.copy}</small></div><span className="price-pill">{item.price || "Открыть"}</span></>;
          if (item.media) return <button data-catalog-feature={item.id} className="model-card" type="button" key={item.id} onClick={() => openCreate(item.media!)}>{content}</button>;
          return <a data-catalog-feature={item.id} className="model-card" key={item.id} href={item.href}>{content}</a>;
        })}
      </div>
    </section>,
    host,
  );
}
