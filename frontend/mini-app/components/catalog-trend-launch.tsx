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

    // Catalog already has a useful preview sheet for one-tap trends. Preserve it
    // when no references are required; only reference trends are promoted to the
    // dedicated upload flow. This keeps existing preview/cost UX while making
    // reference trends actually runnable instead of ending in the old toast.
    const preservePreview = (event: Event) => {
      const target = event.target instanceof Element
        ? event.target.closest<HTMLElement>("[data-trend-launch='true']")
        : null;
      if (!target) return;
      const screen = target.closest<HTMLElement>(".screen");
      if (screen?.querySelector<HTMLElement>(".screen-head .kicker")?.textContent?.trim() !== "Каталог") return;
      const title = target.querySelector("strong")?.textContent?.trim() || "";
      const trend = byTitle.get(title);
      if (!trend || Number(trend.reference_requirements?.min || 0) > 0) return;

      // GlobalUxEnhancers listens on document capture for reference launches.
      // Mark this click as preview-only while it propagates, then restore the
      // marker after the existing React card handler has opened its preview.
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
