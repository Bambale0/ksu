"use client";

import { createPortal } from "react-dom";
import { useEffect, useMemo, useState } from "react";

import { compactNumber, customerRequest } from "@/lib/customer-api";

type HostKind = "profile" | "partners" | "history" | "discovery";
type Host = { kind: HostKind; node: HTMLElement };
type Overview = {
  notifications?: { unread?: number };
  support?: { statuses?: Record<string, number> };
  social?: { following?: number; followers?: number };
  partner?: { available_rub?: string; pending_rub?: string };
  payments?: { total?: number };
};
type DiscoverySlide = {
  id: string;
  eyebrow: string;
  title: string;
  body: string;
  cta: string;
  action: { type: "route" | "trends"; target: string };
  image_url?: string | null;
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

function routePath(target: string): string {
  if (target === "wallet") return "/mini-app/?route=profile";
  if (["home", "catalog", "create", "history", "profile", "feed", "partners"].includes(target)) return `/mini-app/?route=${encodeURIComponent(target)}`;
  return "/mini-app/?route=catalog";
}

export function CustomerParityHub() {
  const [hosts, setHosts] = useState<Host[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [slides, setSlides] = useState<DiscoverySlide[]>([]);

  useEffect(() => {
    let active = true;
    void Promise.allSettled([
      customerRequest<Overview>("/api/v1/me/overview"),
      customerRequest<{ slides: DiscoverySlide[] }>("/api/v1/discovery/home"),
    ]).then(([overviewResult, discoveryResult]) => {
      if (!active) return;
      if (overviewResult.status === "fulfilled") setOverview(overviewResult.value);
      if (discoveryResult.status === "fulfilled") setSlides(discoveryResult.value.slides || []);
    });
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
        const promo = document.querySelector<HTMLElement>(".promo-carousel");
        if (promo && slides.length) {
          promo.dataset.cmsReplaced = "true";
          for (const child of Array.from(promo.children)) {
            if (child instanceof HTMLElement && child.dataset.customerParityHost !== "discovery") child.style.display = "none";
          }
          next.push({ kind: "discovery", node: ensureHost(promo, "discovery") });
        }
        setHosts((current) => current.length === next.length && current.every((item, index) => item.kind === next[index]?.kind && item.node === next[index]?.node) ? current : next);
      });
    };
    scan();
    const observer = new MutationObserver(scan);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, [slides.length]);

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
    ]} /> : host.kind === "history" ? <QuickPanel title="Управление работами" copy="Backend умеет больше обычного просмотра истории: действия с результатом, скачивание, скрытие и восстановление." actions={[
      ["Действия с работами", "/mini-app/actions/", "Edit · Animate · Repeat"],
      ["Скачать файлы", "/mini-app/downloads/", "Оригиналы"],
      ["Скрытые работы", "/mini-app/history-manager/", "Архив"],
    ]} /> : <DiscoveryCarousel slides={slides} />,
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

function DiscoveryCarousel({ slides }: { slides: DiscoverySlide[] }) {
  const items = useMemo(() => slides.slice(0, 8), [slides]);
  return <div data-cms-discovery style={{ display: "grid", gridAutoFlow: "column", gridAutoColumns: "minmax(260px, 82%)", gap: 12, overflowX: "auto", scrollSnapType: "x mandatory" }}>
    {items.map((slide) => {
      const backgroundImage = slide.image_url ? `linear-gradient(180deg, rgba(10,8,16,.28), rgba(10,8,16,.92)), url("${slide.image_url.replaceAll('"', "%22")}")` : undefined;
      return <button key={slide.id} type="button" onClick={() => slide.action.type === "trends" ? open("/mini-app/?route=catalog") : open(routePath(slide.action.target))} style={{ minHeight: 180, borderRadius: 24, padding: 20, textAlign: "left", scrollSnapAlign: "start", position: "relative", overflow: "hidden", border: "1px solid rgba(177,92,255,.28)", backgroundColor: "rgba(14,12,20,.92)", backgroundImage, backgroundPosition: "center", backgroundSize: "cover", color: "inherit" }}>
        <span className="kicker">{slide.eyebrow || "ROXY"}</span><h2 style={{ margin: "8px 0" }}>{slide.title}</h2><p className="muted">{slide.body}</p><strong>{slide.cta || "Открыть"} →</strong>
      </button>;
    })}
  </div>;
}
