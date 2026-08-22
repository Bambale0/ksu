"use client";

import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { TrendItem } from "@/lib/types";

export function CatalogTrendLaunch() {
  const [trends, setTrends] = useState<TrendItem[]>([]);
  const byTitle = useMemo(() => new Map(trends.map((item) => [item.title.trim(), item.id])), [trends]);

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
          const id = byTitle.get(title);
          if (!id) continue;
          card.dataset.trendLaunch = "true";
          card.dataset.trendId = id;
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
