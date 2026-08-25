"use client";

import { useEffect, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { haptic, initTelegram, telegramHeaders } from "@/lib/telegram";
import type { TrendItem } from "@/lib/types";

type ServicesResponse = { items?: TrendItem[] };

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

function price(item: TrendItem): string {
  const raw = item.cost_rox ?? item.retail_cost_rox;
  const parsed = Number(raw ?? 0);
  if (!Number.isFinite(parsed)) return "—";
  return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(parsed)} ROX`;
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
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "Не удалось загрузить сервисы"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const pinterest = items[0] ?? null;

  return (
    <StandaloneShell
      kicker="ROXY SERVICES"
      title="Сервисы"
      copy="Готовые AI-сценарии, где сложная логика референсов и промптов уже настроена за тебя."
    >
      <div className="services-grid">
        <article className="service-card service-card-pinterest">
          <div className="service-card-media">
            {pinterest?.preview_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={pinterest.preview_url} alt="Pinterest AI" />
            ) : (
              <div className="service-card-placeholder" aria-hidden="true">P</div>
            )}
            <span className="service-new-badge">НОВИНКА</span>
          </div>
          <div className="service-card-body">
            <div>
              <span className="service-eyebrow">Pinterest Flow</span>
              <h2>Pinterest AI</h2>
            </div>
            <p>Повторяй трендовые сцены с твоим лицом, телом и дополнительными ракурсами.</p>
            <ul className="service-points">
              <li>Сцена из Pinterest — отдельный референс</li>
              <li>Лицо и тело — отдельный identity reference</li>
              <li>До 5 дополнительных ракурсов</li>
            </ul>
            {pinterest ? (
              <button
                type="button"
                className="service-primary-button"
                onClick={() => {
                  haptic("medium");
                  window.location.assign(`/mini-app/pinterest-flow/?id=${encodeURIComponent(pinterest.id)}`);
                }}
              >
                <span>Открыть Pinterest Flow</span>
                <strong>{price(pinterest)}</strong>
              </button>
            ) : (
              <button type="button" className="service-primary-button" disabled>
                {loading ? "Загружаю сервис…" : "Pinterest Flow пока не опубликован"}
              </button>
            )}
          </div>
        </article>
      </div>

      {error ? <div className="service-error" role="alert">{error}</div> : null}
    </StandaloneShell>
  );
}
