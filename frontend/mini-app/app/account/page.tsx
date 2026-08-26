"use client";

import { useEffect, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { compactNumber, customerRequest } from "@/lib/customer-api";

type Overview = {
  account: { username?: string | null; first_name?: string | null; last_name?: string | null; created_at: string };
  balance: { bonus_rox: string; withdrawable_rox: string; rub_accounting_equivalent: string };
  generations: { total: number; statuses: Record<string, number> };
  payments: { total: number; currencies: Record<string, { count: number; successful_count: number; successful_amount: string; credited_rox: string }> };
  support: { total: number; statuses: Record<string, number> };
  partner: { first_line: number; second_line: number; available_rub: string; pending_rub: string; withdrawable_rox: string; withdrawals: Record<string, number> };
  social: { following: number; followers: number };
  notifications: { unread: number };
  preferences: { ui_language: string; notifications_enabled: boolean; marketing_notifications: boolean; profile_discoverable: boolean };
};

type HubItem = { title: string; copy: string; href: string; badge?: string };

export default function AccountPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  const load = async () => {
    setError("");
    try { setOverview(await customerRequest<Overview>("/api/v1/me/overview")); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось загрузить профиль"); }
  };

  useEffect(() => { void load(); }, []);

  const items: HubItem[] = [
    { title: "Пополнения и статусы", copy: "Пакеты, бонусные ROX и проверка незавершённых оплат", href: "/mini-app/payments/", badge: overview?.payments.total ? `${overview.payments.total}` : undefined },
    { title: "Уведомления", copy: "Результаты, платежи, промокоды и важные события", href: "/mini-app/notifications/", badge: overview?.notifications.unread ? `${overview.notifications.unread} новых` : undefined },
    { title: "Поддержка", copy: "Создать обращение или продолжить диалог", href: "/mini-app/support/", badge: overview?.support.statuses?.open ? `${overview.support.statuses.open} открыто` : undefined },
    { title: "Настройки", copy: "Язык, уведомления и видимость профиля", href: "/mini-app/settings/" },
    { title: "Промокод", copy: "Активировать код и получить ROX", href: "/mini-app/promocodes/" },
    { title: "Мои пресеты", copy: "Сохранённые модели, параметры и референсы", href: "/mini-app/presets/" },
    { title: "Подписки", copy: "Авторы и отдельная лента их работ", href: "/mini-app/subscriptions/", badge: overview?.social.following ? `${overview.social.following}` : undefined },
    { title: "Управление историей", copy: "Скрыть работу или восстановить её", href: "/mini-app/history-manager/" },
    { title: "Действия с работами", copy: "Повторить, изменить, оживить или сменить параметры", href: "/mini-app/actions/" },
    { title: "Скачать результаты", copy: "Оригинальные файлы из собственного хранилища ROXY", href: "/mini-app/downloads/" },
    { title: "Партнёрский доход", copy: "Вывод денег и перевод партнёрского баланса в ROX", href: "/mini-app/partner-wallet/", badge: Number(overview?.partner.available_rub || 0) > 0 ? `${compactNumber(overview?.partner.available_rub)} ₽` : undefined },
    { title: "Creator-партнёрство", copy: "Заявка на индивидуальные условия для авторов", href: "/mini-app/creator-partnership/" },
  ];

  const statuses = overview?.generations.statuses || {};
  const active = ["queued", "retry", "submitting", "generating"].reduce((sum, key) => sum + Number(statuses[key] || 0), 0);

  return (
    <StandaloneShell kicker="Аккаунт" title={overview?.account.first_name || overview?.account.username || "Мой ROXY"} copy="Баланс, активность и все пользовательские возможности backend в одном месте.">
      {error ? <div className="action-error" role="alert">{error}</div> : null}
      {overview ? <>
        <div className="profile-stats panel"><div><strong>{compactNumber(overview.balance.bonus_rox)} ROX</strong><span>баланс</span></div><div><strong>{overview.generations.total}</strong><span>генераций</span></div><div><strong>{overview.social.followers}</strong><span>подписчиков</span></div></div>
        <div className="profile-stats panel"><div><strong>{statuses.succeeded || 0}</strong><span>готово</span></div><div><strong>{active}</strong><span>в работе</span></div><div><strong>{statuses.failed || 0}</strong><span>ошибок</span></div></div>
      </> : <div className="panel"><p className="muted">Загружаю профиль…</p></div>}

      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">Возможности</span><h2>Аккаунт и сервисы</h2></div><button type="button" onClick={() => void load()}>Обновить</button></div>
        <div className="tool-grid">
          {items.map((item) => <button className="tool-result-card" type="button" key={item.href} onClick={() => window.location.assign(item.href)} style={{ textAlign: "left", width: "100%" }}>
            <div className="section-title"><div><span className="kicker">ROXY</span><h2>{item.title}</h2></div>{item.badge ? <span className="status succeeded">{item.badge}</span> : null}</div>
            <p className="muted">{item.copy}</p>
          </button>)}
        </div>
      </div>
    </StandaloneShell>
  );
}
