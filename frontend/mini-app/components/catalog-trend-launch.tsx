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
          const needsReferences = Number(trend.reference_requirements?.min || 0) > 0;
          if (needsReferences) {
            card.dataset.trendLaunch = "true";
            card.dataset.trendId = trend.id;
          } else {
            delete card.dataset.trendLaunch;
            delete card.dataset.trendId;
          }
        }
      }
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [byTitle]);

  return null;
}
