"use client";

import { useEffect } from "react";

const STYLE_ID = "roxy-hybrid-feed-style";

function currentRoute(): string {
  try {
    return new URL(window.location.href).searchParams.get("route") || "home";
  } catch {
    return "home";
  }
}

function buttonLabel(button: HTMLButtonElement): string {
  return button.querySelector("small")?.textContent?.trim() || button.textContent?.trim() || "";
}

function setButtonLabel(button: HTMLButtonElement, label: string) {
  const small = button.querySelector("small");
  if (small) small.textContent = label;
  button.setAttribute("aria-label", label);
}

function normalizeBottomNav() {
  const nav = document.querySelector(".bottom-nav");
  if (!nav) return;

  const buttons = Array.from(nav.querySelectorAll<HTMLButtonElement>("button"));
  const feedButtons = buttons.filter((button) => buttonLabel(button) === "Лента");

  // There must be one community feed entry. If a legacy patch labels the
  // catalog slot as Feed too, keep the first Feed button and restore the
  // duplicate grid/catalog slot back to Catalog. Do not redirect Feed away:
  // Feed is the single hybrid surface.
  if (feedButtons.length > 1) {
    for (const duplicate of feedButtons.slice(1)) setButtonLabel(duplicate, "Каталог");
  }
}

function activeScreen(): HTMLElement | null {
  return document.querySelector<HTMLElement>("main .screen");
}

function markPinterestFeed() {
  const screen = activeScreen();
  if (!screen) return;
  const isFeed = currentRoute() === "feed" || screen.textContent?.includes("Работы сообщества");
  screen.classList.toggle("roxy-hybrid-feed-screen", Boolean(isFeed));
}

function markTikTokPreview() {
  document.querySelectorAll<HTMLElement>(".preview-card").forEach((card) => {
    const kicker = card.querySelector(".preview-copy .kicker")?.textContent?.trim() || "";
    const isFeedPreview = kicker === "Лента" || currentRoute() === "feed";
    card.classList.toggle("roxy-feed-tiktok-preview", isFeedPreview);
  });
}

function applyHybridFeedState() {
  normalizeBottomNav();
  markPinterestFeed();
  markTikTokPreview();
}

function installStyle() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .roxy-hybrid-feed-screen .screen-head {
      margin-bottom: 12px;
    }

    .roxy-hybrid-feed-screen .segmented {
      margin-bottom: 12px;
    }

    .roxy-hybrid-feed-screen .media-grid {
      display: grid !important;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      align-items: start;
    }

    .roxy-hybrid-feed-screen .media-tile {
      min-height: 0;
      aspect-ratio: 3 / 4;
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 14px 34px rgba(0, 0, 0, .28);
    }

    .roxy-hybrid-feed-screen .media-tile:nth-child(4n + 2),
    .roxy-hybrid-feed-screen .media-tile:nth-child(4n + 3) {
      aspect-ratio: 1 / 1.35;
    }

    .roxy-hybrid-feed-screen .media-tile img,
    .roxy-hybrid-feed-screen .media-tile video {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .roxy-feed-tiktok-preview {
      position: fixed !important;
      inset: 0 !important;
      width: 100dvw !important;
      height: 100dvh !important;
      max-width: none !important;
      max-height: none !important;
      margin: 0 !important;
      padding: 0 !important;
      border-radius: 0 !important;
      border: 0 !important;
      background: #000 !important;
      overflow: hidden !important;
    }

    .roxy-feed-tiktok-preview .preview-close {
      z-index: 4;
      top: calc(env(safe-area-inset-top, 0px) + 14px);
      right: 14px;
      background: rgba(15, 15, 22, .64);
      backdrop-filter: blur(16px);
    }

    .roxy-feed-tiktok-preview .preview-media {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      background: #000;
    }

    .roxy-feed-tiktok-preview .preview-media img,
    .roxy-feed-tiktok-preview .preview-media video {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }

    .roxy-feed-tiktok-preview .preview-copy {
      position: absolute;
      left: 14px;
      right: 14px;
      bottom: calc(env(safe-area-inset-bottom, 0px) + 92px);
      z-index: 3;
      max-height: 42dvh;
      overflow: auto;
      padding: 16px;
      border-radius: 24px;
      background: linear-gradient(180deg, rgba(9, 9, 14, .18), rgba(9, 9, 14, .82));
      backdrop-filter: blur(18px);
    }

    .roxy-feed-tiktok-preview .preview-copy .prompt-copy {
      max-height: 96px;
      overflow: auto;
    }

    .roxy-feed-tiktok-preview .preview-actions {
      display: flex;
      gap: 8px;
      overflow-x: auto;
      padding-bottom: 2px;
      scroll-snap-type: x mandatory;
    }

    .roxy-feed-tiktok-preview .preview-actions > * {
      flex: 0 0 auto;
      scroll-snap-align: start;
      min-height: 42px;
    }
  `;
  document.head.appendChild(style);
}

export function SingleFeedSurfaceGuard() {
  useEffect(() => {
    installStyle();
    applyHybridFeedState();

    const observer = new MutationObserver(() => window.requestAnimationFrame(applyHybridFeedState));
    observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });

    const onPopState = () => window.requestAnimationFrame(applyHybridFeedState);
    window.addEventListener("popstate", onPopState);

    return () => {
      observer.disconnect();
      window.removeEventListener("popstate", onPopState);
    };
  }, []);

  return null;
}
