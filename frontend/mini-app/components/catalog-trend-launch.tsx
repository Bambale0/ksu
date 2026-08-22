"use client";

import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { TrendItem } from "@/lib/types";

export function CatalogTrendLaunch() {
  const [trends, setTrends] = useState<TrendItem[]>([]);
  const byTitle = useMemo(() => new Map(trends.map((item) => [item.title.trim(), item])), [trends]);

  useEffect(() => {
    void api.trends().then((payload) => setTrends(payload.items || [])).catch(() => setTrends([]));
  }, []);

  useEffect(() => {
    if (!byTitle.size) return;
    const sync = () => {
      for (const screen of Array.from(document.querySelectorAll<HTMLElement>(".main-shell > .screen"))) {
        if (screen.querySelector<HTMLElement>(".screen-head .kicker")?.textContent?.trim() !== "Каталог") continue;
        for (const card of Array.from(screen.querySelectorAll<HTMLElement>(".model-card"))) {
          const title = card.querySelector("strong")?.textContent?.trim() || "";
          const trend = byTitle.get(title);
          if (!trend) continue;
          card.dataset.trendLaunch = "true";
          card.dataset.trendId = trend.id;
        }
      }
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });

    const preservePreview = (event: Event) => {
      if (event instanceof KeyboardEvent && event.key !== "Enter" && event.key !== " ") return;
      const target = event.target instanceof Element
        ? event.target.closest<HTMLElement>("[data-trend-launch='true']")
        : null;
      if (!target) return;
      const screen = target.closest<HTMLElement>(".screen");
      if (screen?.querySelector<HTMLElement>(".screen-head .kicker")?.textContent?.trim() !== "Каталог") return;
      const title = target.querySelector("strong")?.textContent?.trim() || "";
      const trend = byTitle.get(title);
      if (!trend || Number(trend.reference_requirements?.min || 0) > 0) return;
      target.dataset.trendLaunch = "preview";
      queueMicrotask(() => {
        if (target.isConnected) target.dataset.trendLaunch = "true";
      });
    };

    window.addEventListener("click", preservePreview, true);
    window.addEventListener("keydown", preservePreview, true);
    return () => {
      observer.disconnect();
      window.removeEventListener("click", preservePreview, true);
      window.removeEventListener("keydown", preservePreview, true);
    };
  }, [byTitle]);

  return null;
}
