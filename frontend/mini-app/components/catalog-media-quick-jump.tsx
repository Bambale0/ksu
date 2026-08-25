"use client";

import { useEffect } from "react";

const CATALOG_MEDIA_LABELS = new Set(["Все", "Фото", "Видео", "Музыка"]);
const CATALOG_TITLES = new Set(["Тренды и модели", "Модели и идеи"]);

function isCatalogScreen(screen: HTMLElement): boolean {
  const kicker = screen.querySelector<HTMLElement>(".screen-head .kicker")?.textContent?.trim();
  const title = screen.querySelector<HTMLElement>(".screen-head h1")?.textContent?.trim();
  return kicker === "Каталог" && (!title || CATALOG_TITLES.has(title));
}

function modelChoiceTarget(screen: HTMLElement): HTMLElement | null {
  const heading = Array.from(screen.querySelectorAll<HTMLElement>(".section-title h2"))
    .find((item) => item.textContent?.trim() === "Полный каталог");
  return heading?.closest<HTMLElement>(".section-title") || screen.querySelector<HTMLElement>(".model-grid");
}

export function CatalogMediaQuickJump() {
  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const button = event.target instanceof Element
        ? event.target.closest<HTMLButtonElement>(".segmented.scrollable button")
        : null;
      if (!button) return;

      const label = button.textContent?.trim() || "";
      if (!CATALOG_MEDIA_LABELS.has(label)) return;

      const screen = button.closest<HTMLElement>(".screen");
      if (!screen || !isCatalogScreen(screen)) return;

      const firstSegment = screen.querySelector<HTMLElement>(".segmented.scrollable");
      if (firstSegment !== button.closest<HTMLElement>(".segmented.scrollable")) return;

      window.setTimeout(() => {
        window.requestAnimationFrame(() => {
          const target = modelChoiceTarget(screen);
          target?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      }, 0);
    };

    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, []);

  return null;
}
