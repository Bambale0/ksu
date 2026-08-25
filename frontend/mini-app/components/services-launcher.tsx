"use client";

import { useEffect, useState } from "react";

import { haptic } from "@/lib/telegram";

export function ServicesLauncher() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const url = new URL(window.location.href);
    const hasDeepTarget = Boolean(
      url.searchParams.get("start_payload")
      || url.searchParams.get("tgWebAppStartParam")
      || url.searchParams.get("generation")
      || url.searchParams.get("action_context_id")
      || url.searchParams.get("route") === "generation-action",
    );
    setVisible(!hasDeepTarget);
  }, []);

  if (!visible) return null;

  return (
    <button
      type="button"
      className="services-launcher"
      aria-label="Открыть сервисы"
      onClick={() => {
        haptic("light");
        window.location.assign("/mini-app/services/");
      }}
    >
      <span className="services-launcher-icon" aria-hidden="true">✦</span>
      <span>
        <strong>Сервисы</strong>
        <small>Pinterest AI · новинка</small>
      </span>
    </button>
  );
}
