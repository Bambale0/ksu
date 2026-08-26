"use client";

import { createPortal } from "react-dom";
import { useEffect, useState } from "react";

import { compactNumber, customerRequest } from "@/lib/customer-api";

type HostKind = "profile" | "partners" | "history";
type Host = { kind: HostKind; node: HTMLElement };
type Overview = {
  notifications?: { unread?: number };
  support?: { statuses?: Record<string, number> };
  social?: { following?: number; followers?: number };
  partner?: { available_rub?: string; pending_rub?: string };
  payments?: { total?: number };
};

function ensureHost(parent: HTMLElement, kind: HostKind): HTMLElement {
  const existing = parent.querySelector<HTMLElement>(`:scope > [data-customer-parity-host='${kind}']`);
  if (existing) return existing;
  const node = document.createElement("div");
  node.dataset.customerParityHost = kind;
  parent.appendChild(node);
  return node;
}

function open(path: string) {
  window.location.assign(path);
}

export function CustomerParityHub() {
  const [hosts, setHosts] = useState<Host[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);

  useEffect(() => {
    let active = true;
    void customerRequest<Overview>("/api/v1/me/overview")
      .then((value) => {
        if (active) setOverview(value);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let frame = 0;
    const scan = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const next: Host[] = [];
        for (const screen of Array.from(document.querySelectorAll<HTMLElement>(".main-shell > .screen"))) {
          const kicker = screen.querySelector<HTMLElement>(".screen-head .kicker")?.textContent?.trim() || "";
          if (kicker === "Профиль") next.push({ kind: "profile", node: ensureHost(screen, "profile") });
          if (kicker === "Партнёрам") next.push({ kind: "partners", node: ensureHost(screen, "partners") });
          if (kicker === "История") next.push({ kind: "history", node: ensureHost(screen, "history") });
        }
        setHosts((current) => current.length === next.length && current.every((item, index) => item.kind === next[index]?.kind && item.node === next[index]?.node) ? current : next);
      });
    };
    scan();
    const observer = new MutationObserver(scan);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, []);

  const unread = Number(overview?.notifications?.unread || 0);
  const openSupport = Number(overview?.support?.statuses?.open || 0);
  const following = Number(overview?.social?.following || 0);
  const partnerAvailable = Number(overview?.partner?.available_rub || 0);
  const paymentCount = Number(overview?.payments?.total || 0);

  return <>{hosts.map((host) => createPortal(
    host.kind === "profile" ? <QuickPanel title="Аккаунт и сервисы" copy="Баланс, настройки, уведомления, поддержка, файлы, пресеты и социальные функции." actions={[
      ["Аккаунт", "/mini-app/account/", "Все функции"],
      ["Пополнения", "/mini-app/payments/", paymentCount ? `${paymentCount}` : ""],
      ["Уведомления", "/mini-app/notifications/", unread ? `${unread} новых` : ""],
      ["Поддержка", "/mini-app/support/", openSupport ? `${openSupport} открыто` : ""],
      ["Настройки", "/mini-app/settings/", ""],
      ["Подписки", "/mini-app/subscriptions/", following ? `${following}` : ""],
      ["Пресеты", "/mini-app/presets/", ""],
      ["Скачать", "/mini-app/downloads/", ""],
      ["Промокод", "/mini-app/promocodes/", ""],
    ]} /> : host.kind === "partners" ? <QuickPanel title="Управление доходом" copy="Доступный партнёрский баланс можно вывести или перевести в ROX. Creator-программа живёт отдельно от реферальных начислений." actions={[
      ["Выплаты и ROX", "/mini-app/partner-wallet/", partnerAvailable ? `${compactNumber(partnerAvailable)} ₽` : ""],
      ["Creator-партнёрство", "/mini-app/creator-partnership/", "Заявка"],
    ]} /> : <QuickPanel title="Управление работами" copy="Backend умеет больше обычного просмотра истории: действия с результатом, скачивание, скрытие и восстановление." actions={[
      ["Действия с работами", "/mini-app/actions/", "Edit · Animate · Repeat"],
      ["Скачать файлы", "/mini-app/downloads/", "Оригиналы"],
      ["Скрытые работы", "/mini-app/history-manager/", "Архив"],
    ]} />,
    host.node,
    `${host.kind}:${host.node.dataset.customerParityHost}`,
  ))}</>;
}

function QuickPanel({ title, copy, actions }: { title: string; copy: string; actions: Array<[string, string, string]> }) {
  return <section className="panel" data-customer-parity-panel style={{ marginTop: 18 }}>
    <span className="kicker">ROXY</span><h2>{title}</h2><p className="muted">{copy}</p>
    <div className="tool-actions" style={{ flexWrap: "wrap" }}>{actions.map(([label, href, badge]) => <button className="secondary" type="button" key={href} onClick={() => open(href)}>{label}{badge ? ` · ${badge}` : ""}</button>)}</div>
  </section>;
}
