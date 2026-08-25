"use client";

import { useEffect, useState } from "react";

import { Icon, type IconName } from "@/components/icons";
import { StandaloneShell } from "@/components/standalone-shell";
import { haptic, initTelegram, telegramHeaders } from "@/lib/telegram";
import type { TrendItem } from "@/lib/types";

type ServicesResponse = { items?: TrendItem[] };
type CreationMedia = "image" | "video" | "audio";
type ServiceShortcut = {
  title: string;
  description: string;
  icon: IconName;
  route?: "create" | "partners" | "profile";
  media?: CreationMedia;
  pinterest?: boolean;
  badge?: string;
};

const MEDIA_FILTER_KEY = "ksu-selected-media";

const SERVICE_SHORTCUTS: ServiceShortcut[] = [
  { title: "Оживить", description: "Image-to-video", icon: "video", route: "create", media: "video" },
  { title: "Изменить", description: "Редактирование фото", icon: "image", route: "create", media: "image" },
  { title: "Музыка", description: "Генерация музыки", icon: "music", route: "create", media: "audio" },
  { title: "Avatar", description: "Фото и видео-сценарии", icon: "profile", route: "create", media: "video" },
  { title: "Партнёры", description: "Партнёрская программа", icon: "share", route: "partners" },
  { title: "Помощь", description: "Профиль и поддержка", icon: "settings", route: "profile" },
  { title: "Pinterest", description: "Повторить Pinterest-сцену со своей внешностью", icon: "spark", pinterest: true, badge: "Новинка" },
];

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
    headers: telegramHeaders(),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload as T;
}

function openMainRoute(route: "create" | "partners" | "profile", media?: CreationMedia) {
  if (media) localStorage.setItem(MEDIA_FILTER_KEY, media);
  haptic(route === "create" ? "medium" : "light");
  window.location.assign(`/mini-app/?route=${encodeURIComponent(route)}`);
}

export default function ServicesPage() {
  const [items, setItems] = useState<TrendItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    initTelegram();
    let active = true;
    request<ServicesResponse>("/api/v1/services/pinterest")
      .then((payload) => {
        if (!active) return;
        setItems(Array.isArray(payload.items) ? payload.items : []);
        setError("");
      })
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "Не удалось загрузить Pinterest"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const pinterest = items[0] ?? null;

  const openShortcut = (shortcut: ServiceShortcut) => {
    if (shortcut.pinterest) {
      if (!pinterest) return;
      haptic("medium");
      window.location.assign(`/mini-app/pinterest-flow/?id=${encodeURIComponent(pinterest.id)}`);
      return;
    }
    if (shortcut.route) openMainRoute(shortcut.route, shortcut.media);
  };

  return (
    <StandaloneShell kicker="AI" title="Сервисы" copy="Что здесь есть">
      <div className="service-shortcut-grid" aria-label="Сервисы">
        {SERVICE_SHORTCUTS.map((shortcut) => {
          const unavailable = shortcut.pinterest && !pinterest;
          return (
            <button
              key={shortcut.title}
              type="button"
              className={`service-shortcut${shortcut.pinterest ? " service-shortcut-pinterest" : ""}`}
              title={unavailable && !loading ? "Pinterest Flow пока не опубликован" : shortcut.description}
              aria-label={shortcut.title}
              disabled={unavailable}
              onClick={() => openShortcut(shortcut)}
            >
              {shortcut.badge ? <span className="service-shortcut-badge">{shortcut.badge}</span> : null}
              <span className="service-shortcut-icon" aria-hidden="true"><Icon name={shortcut.icon} size={19} /></span>
              <span className="service-shortcut-title">{shortcut.title}</span>
            </button>
          );
        })}
      </div>

      {loading ? <div className="service-status" role="status">Проверяю Pinterest Flow…</div> : null}
      {error ? <div className="service-error" role="alert">Pinterest временно недоступен: {error}</div> : null}
    </StandaloneShell>
  );
}
