(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const profileView = document.getElementById("profileView");
  if (!profileView) return;

  const mount = document.createElement("section");
  mount.className = "shell-card account-overview-card";
  mount.dataset.accountOverview = "true";
  profileView.appendChild(mount);

  const style = document.createElement("style");
  style.textContent = `
    .account-overview-card{margin-top:12px;display:grid;gap:12px}
    .account-overview-head{display:flex;align-items:center;justify-content:space-between;gap:12px}
    .account-overview-head h3{margin:0;font-size:16px}
    .account-overview-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
    .account-overview-block{padding:12px;border:1px solid var(--shell-border,#e5e7eb);border-radius:14px;min-width:0}
    .account-overview-block strong{display:block;font-size:14px;margin-bottom:6px}
    .account-overview-block span,.account-overview-block small{display:block;word-break:break-word;line-height:1.45}
    .account-overview-list{display:grid;gap:3px}
    @media(max-width:520px){.account-overview-grid{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);

  function authHeaders() {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function api(path) {
    const response = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      headers: authHeaders(),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  function el(tag, text = "", className = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function formatDate(value) {
    const date = new Date(value || "");
    if (Number.isNaN(date.getTime())) return "—";
    return new Intl.DateTimeFormat("ru-RU", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function block(title, lines) {
    const root = el("div", "", "account-overview-block");
    root.appendChild(el("strong", title));
    const list = el("div", "", "account-overview-list");
    for (const line of lines) list.appendChild(el("span", line));
    root.appendChild(list);
    return root;
  }

  function paymentLines(payments) {
    const currencies = payments?.currencies || {};
    const rows = Object.entries(currencies).map(([currency, item]) => (
      `${currency}: ${item.successful_count || 0} успешных · ${item.successful_amount || 0} ${currency} · ${item.credited || 0} кр.`
    ));
    return rows.length ? rows : ["Платежей пока нет"];
  }

  function render(data) {
    mount.replaceChildren();
    const head = el("div", "", "account-overview-head");
    head.append(el("h3", "Подробно об аккаунте"), el("small", "Данные сервера"));
    const grid = el("div", "", "account-overview-grid");
    const account = data.account || {};
    const balance = data.balance || {};
    const generations = data.generations || {};
    const generationStatuses = generations.statuses || {};
    const support = data.support || {};
    const supportStatuses = support.statuses || {};
    const partner = data.partner || {};
    const social = data.social || {};
    const notifications = data.notifications || {};
    const onboarding = data.onboarding || {};
    const preferences = data.preferences || {};

    grid.append(
      block("Аккаунт", [
        `ID: ${account.id || "—"}`,
        `Telegram ID: ${account.telegram_id || "—"}`,
        `Username: ${account.username ? `@${account.username}` : "—"}`,
        `Регистрация: ${formatDate(account.created_at)}`,
        `Статус: ${account.is_active ? "активен" : "ограничен"}`,
      ]),
      block("Баланс", [
        `${balance.credits || 0} кредитов`,
        `Учётный эквивалент: ${balance.rub_accounting_equivalent || 0} ₽`,
        `Учётная ставка: ${balance.rub_per_credit || 0} ₽ / кредит`,
      ]),
      block("Генерации", [
        `Всего: ${generations.total || 0}`,
        `Готово: ${generationStatuses.succeeded || 0}`,
        `В работе: ${(generationStatuses.queued || 0) + (generationStatuses.submitting || 0) + (generationStatuses.generating || 0) + (generationStatuses.retry || 0)}`,
        `Ошибки: ${generationStatuses.failed || 0}`,
      ]),
      block("Платежи", paymentLines(data.payments)),
      block("Поддержка", [
        `Обращений: ${support.total || 0}`,
        `Открыто: ${supportStatuses.open || 0}`,
        `В работе: ${supportStatuses.in_progress || 0}`,
        `Решено: ${supportStatuses.resolved || 0}`,
      ]),
      block("Партнёрская программа", [
        `1 линия: ${partner.first_line || 0}`,
        `2 линия: ${partner.second_line || 0}`,
        `Доступно: ${partner.available_rub || 0} ₽`,
        `В ожидании: ${partner.pending_rub || 0} ₽`,
      ]),
      block("Социальное", [
        `Подписки: ${social.following || 0}`,
        `Подписчики: ${social.followers || 0}`,
        `Непрочитанных: ${notifications.unread || 0}`,
      ]),
      block("Настройки", [
        `Язык: ${preferences.ui_language || "auto"}`,
        `Уведомления: ${preferences.notifications_enabled ? "включены" : "выключены"}`,
        `Маркетинг: ${preferences.marketing_notifications ? "включён" : "выключен"}`,
        `Публичный профиль: ${preferences.profile_discoverable ? "да" : "нет"}`,
        `Onboarding: ${onboarding.is_current ? "актуален" : "нужно пройти"}`,
      ]),
    );
    mount.append(head, grid);
  }

  function renderError() {
    mount.replaceChildren(
      el("strong", "Подробно об аккаунте"),
      el("p", "Не удалось загрузить подробную статистику. Данные обновятся при следующем открытии профиля."),
    );
  }

  async function load() {
    if (profileView.hidden || !tg?.initData) return;
    mount.replaceChildren(el("p", "Загружаем подробную информацию…"));
    try {
      render(await api("/api/v1/me/overview"));
    } catch (_error) {
      renderError();
    }
  }

  const observer = new MutationObserver(() => {
    if (!profileView.hidden) void load();
  });
  observer.observe(profileView, { attributes: true, attributeFilter: ["hidden"] });
  tg?.onEvent?.("activated", () => { if (!profileView.hidden) void load(); });
  window.addEventListener("online", () => { if (!profileView.hidden) void load(); });
  if (!profileView.hidden) void load();
})();
