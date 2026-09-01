"use client";

import { createPortal } from "react-dom";
import { useEffect, useState } from "react";
import { haptic } from "@/lib/telegram";

function ensureMount(): HTMLElement | null {
  const host = document.querySelector<HTMLElement>("#roxy-home-trend-folders");
  if (!host) return null;
  let mount = host.querySelector<HTMLElement>(":scope > [data-ai-reference-home-entry]");
  if (!mount) {
    mount = document.createElement("div");
    mount.dataset.aiReferenceHomeEntry = "true";
    host.prepend(mount);
  }
  return mount;
}

export function AiReferenceHomeEntry() {
  const [mount, setMount] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const sync = () => setMount(ensureMount());
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  if (!mount) return null;
  return createPortal(
    <button
      className="ai-reference-home-card"
      type="button"
      onClick={() => {
        haptic("light");
        window.location.assign("/mini-app/ai-reference/");
      }}
    >
      <span><small>Главный инструмент</small><strong>AI РЕФЕРЕНС</strong><em>Создать референс · HD · Редактор</em></span>
      <b>Открыть →</b>
      <style>{`
        .ai-reference-home-card{width:100%;min-height:126px;margin:0 0 13px;padding:18px;display:flex;align-items:center;justify-content:space-between;gap:14px;border:1px solid rgba(205,121,255,.42);border-radius:24px;background:radial-gradient(circle at 85% 18%,rgba(204,92,255,.34),transparent 34%),linear-gradient(135deg,#1a1027,#0b0810 68%);color:#fff;text-align:left;box-shadow:0 16px 46px rgba(135,45,224,.18)}.ai-reference-home-card span{display:grid;gap:5px}.ai-reference-home-card small{color:#d89aff;font-size:10px;font-weight:900;letter-spacing:.08em;text-transform:uppercase}.ai-reference-home-card strong{font-size:24px;letter-spacing:-.04em}.ai-reference-home-card em{color:#b8afc2;font-size:12px;font-style:normal}.ai-reference-home-card b{flex-shrink:0;padding:10px 12px;border-radius:999px;background:rgba(190,92,255,.16);color:#ead0ff;font-size:11px}
      `}</style>
    </button>,
    mount,
  );
}
