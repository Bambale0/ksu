"use client";

import { useEffect } from "react";

export function LegacyTrendCatalogGuard() {
  useEffect(() => {
    const hidden = new Set<HTMLElement>();

    const hideLegacy = () => {
      for (const heading of Array.from(document.querySelectorAll<HTMLElement>(".section-title h2"))) {
        if (heading.textContent?.trim() !== "Готовые сценарии") continue;
        const title = heading.closest<HTMLElement>(".section-title");
        const grid = title?.nextElementSibling;
        if (title && !hidden.has(title)) {
          title.style.display = "none";
          hidden.add(title);
        }
        if (grid instanceof HTMLElement && grid.classList.contains("model-grid") && !hidden.has(grid)) {
          grid.style.display = "none";
          hidden.add(grid);
        }
      }
    };

    hideLegacy();
    const observer = new MutationObserver(hideLegacy);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      for (const node of hidden) node.style.removeProperty("display");
    };
  }, []);

  return null;
}
