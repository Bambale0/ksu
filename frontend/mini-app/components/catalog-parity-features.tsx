"use client";

import { createPortal } from "react-dom";
import { useEffect, useState } from "react";

const FEATURES = [
  ["Аккаунт и сервисы", "Баланс, уведомления, настройки и полный обзор", "/mini-app/account/", "overview"],
  ["Пополнения ROX", "Пакеты с бонусами и проверка статуса оплаты", "/mini-app/payments/", "account"],
  ["Действия с работами", "Повтор, редактирование и оживление работ", "/mini-app/actions/", "works"],
  ["Мои пресеты", "Сохраняйте модель, параметры и референсы", "/mini-app/presets/", "works"],
  ["Подписки", "Авторы и отдельная лента их публикаций", "/mini-app/subscriptions/", "works"],
  ["Поддержка", "Обращения, ответы, закрытие и переоткрытие", "/mini-app/support/", "account"],
  ["Уведомления", "Важные события аккаунта в одном месте", "/mini-app/notifications/", "account"],
  ["Скачать результаты", "Оригинальные файлы из хранилища ROXY", "/mini-app/downloads/", "works"],
  ["Управление историей", "Скрытые работы и восстановление", "/mini-app/history-manager/", "works"],
  ["Партнёрские выплаты", "Вывод дохода и перевод рублей в ROX", "/mini-app/partner-wallet/", "partners"],
  ["Creator-партнёрство", "Заявка для авторов и каналов", "/mini-app/creator-partnership/", "partners"],
  ["Промокод", "Активировать код и получить ROX", "/mini-app/promocodes/", "account"],
] as const;

const GROUPS = [
  ["account", "Аккаунт и помощь"],
  ["works", "Работы и публикации"],
  ["partners", "Партнёрство и доход"],
] as const;

function ServiceCard({ feature: [title, copy, href] }: { feature: typeof FEATURES[number] }) {
  return <button className="tool-result-card roxy-service-card" type="button" onClick={() => window.location.assign(href)} style={{ width: "100%", textAlign: "left" }}>
    <strong>{title}</strong><small>{copy}</small>
  </button>;
}

function catalogScreen(): HTMLElement | null {
  const home = document.querySelector<HTMLElement>(".main-shell > .home-screen");
  if (home) return home;
  for (const node of Array.from(document.querySelectorAll<HTMLElement>(".main-shell > .screen"))) {
    const kicker = node.querySelector<HTMLElement>(".screen-head .kicker")?.textContent?.trim();
    if (kicker === "Каталог") return node;
  }
  return null;
}

function ensureHost(screen: HTMLElement): HTMLElement {
  const existing = screen.querySelector<HTMLElement>("#roxy-backend-parity-features");
  if (existing) return existing;
  const host = document.createElement("div");
  host.id = "roxy-backend-parity-features";
  host.dataset.backendParityFeatures = "true";
  screen.appendChild(host);
  return host;
}

export function CatalogParityFeatures() {
  const [host, setHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    let frame = 0;
    const scan = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const screen = catalogScreen();
        setHost(screen ? ensureHost(screen) : null);
      });
    };
    scan();
    const observer = new MutationObserver(scan);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, []);

  if (!host) return null;
  return createPortal(
    <section className="panel" style={{ marginTop: 20 }} aria-label="Сервисы аккаунта ROXY">
      <span className="kicker">Аккаунт</span>
      <h2>Сервисы ROXY</h2>
      <div className="catalog-services-overview">
        {FEATURES.filter((feature) => feature[3] === "overview").map((feature) => <ServiceCard key={feature[2]} feature={feature} />)}
      </div>
      <div className="catalog-service-groups">
        {GROUPS.map(([id, title]) => <details className="catalog-disclosure" key={id}>
          <summary>{title}</summary>
          <div className="tool-grid">
            {FEATURES.filter((feature) => feature[3] === id).map((feature) => <ServiceCard key={feature[2]} feature={feature} />)}
          </div>
        </details>)}
      </div>
    </section>,
    host,
  );
}
