"use client";

import { useEffect } from "react";

function sectionByKicker(home: HTMLElement, kicker: string): HTMLElement | null {
  for (const section of Array.from(home.querySelectorAll<HTMLElement>(":scope > .section-title"))) {
    if (section.querySelector<HTMLElement>(".kicker")?.textContent?.trim() === kicker) return section;
  }
  return null;
}

function promoteHomeTrends(): void {
  const home = document.querySelector<HTMLElement>(".home-screen");
  if (!home) return;

  const promo = home.querySelector<HTMLElement>(":scope > .promo-slider");
  const trendTitle = sectionByKicker(home, "Тренды");
  const trendRail = trendTitle?.nextElementSibling as HTMLElement | null;
  if (!promo || !trendTitle || !trendRail) return;
  if (!trendRail.matches(".model-grid, .empty")) return;

  if (promo.nextElementSibling === trendTitle && trendTitle.nextElementSibling === trendRail) return;

  promo.insertAdjacentElement("afterend", trendTitle);
  trendTitle.insertAdjacentElement("afterend", trendRail);
}

function promoteCatalogTrends(): void {
  for (const screen of Array.from(document.querySelectorAll<HTMLElement>(".main-shell > .screen"))) {
    const kicker = screen.querySelector<HTMLElement>(".screen-head .kicker")?.textContent?.trim();
    if (kicker !== "Каталог" && !screen.classList.contains("roxy-catalog-feature-mode")) continue;

    const promo = screen.querySelector<HTMLElement>(":scope > .promo-carousel");
    const trends = screen.querySelector<HTMLElement>(":scope > #roxy-live-trends");
    if (!promo || !trends || promo.nextElementSibling === trends) continue;

    promo.insertAdjacentElement("afterend", trends);
  }
}

function promoteTrends(): void {
  promoteHomeTrends();
  promoteCatalogTrends();
}

export function HomeTrendOrder() {
  useEffect(() => {
    let frame = 0;
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(promoteTrends);
    };

    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

  return null;
}
