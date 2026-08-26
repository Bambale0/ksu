"use client";

import { createPortal } from "react-dom";
import { useEffect, useState } from "react";

const FEATURES = [
  ["Аккаунт и сервисы", "Баланс, уведомления, настройки и полный обзор", "/mini-app/account/"],
  ["Пополнения ROX", "Пакеты с бонусами и проверка статуса оплаты", "/mini-app/payments/"],
  ["Действия с работами", "Повтор, новый prompt, параметры, edit и animate", "/mini-app/actions/"],
  ["Мои пресеты", "Сохраняйте модель, параметры и референсы", "/mini-app/presets/"],
  ["Подписки", "Авторы и отдельная лента их публикаций", "/mini-app/subscriptions/"],
  ["Поддержка", "Обращения, ответы, закрытие и переоткрытие", "/mini-app/support/"],
  ["Уведомления", "Важные события аккаунта в одном месте", "/mini-app/notifications/"],
  ["Скачать результаты", "Оригинальные файлы из хранилища ROXY", "/mini-app/downloads/"],
  ["Управление историей", "Скрытые работы и восстановление", "/mini-app/history-manager/"],
  ["Партнёрские выплаты", "Вывод дохода и перевод RUB в ROX", "/mini-app/partner-wallet/"],
  ["Creator-партнёрство", "Заявка для авторов и каналов", "/mini-app/creator-partnership/"],
  ["Промокод", "Активировать код и получить ROX", "/mini-app/promocodes/"],
] as const;

function catalogScreen(): HTMLElement | null {
  for (const node of Array.from(document.querySelectorAll<HTMLElement>(".main-shell > .screen"))) {
    const kicker = node.querySelector<HTMLElement>(".screen-head .kicker")?.textContent?.trim();
    if (kicker === "Каталог" || node.classList.contains("roxy-catalog-feature-mode")) return node;
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
      <span className="kicker">Ещё возможности</span>
      <h2>Сервисы ROXY</h2>
      <p className="muted">Функции аккаунта, сообщества, платежей и готовых работ, которые уже поддерживаются backend.</p>
      <div className="tool-grid">
        {FEATURES.map(([title, copy, href]) => <button className="tool-result-card" type="button" key={href} onClick={() => window.location.assign(href)} style={{ width: "100%", textAlign: "left" }}>
          <strong>{title}</strong><small>{copy}</small>
        </button>)}
      </div>
    </section>,
    host,
  );
}
