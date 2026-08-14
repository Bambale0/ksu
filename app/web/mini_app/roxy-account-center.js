(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    mounted: false,
    loading: false,
    notifications: [],
    unreadCount: 0,
    unreadOnly: false,
    tickets: [],
    activeTicket: null,
    subscriptions: [],
    socialProfile: null,
    preferences: null,
  };

  function authHeaders(json = false) {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    if (json) headers["Content-Type"] = "application/json";
    return headers;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      headers: { ...authHeaders(options.body !== undefined), ...(options.headers || {}) },
    });
    const payload = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload?.detail;
      const message = typeof detail === "string"
        ? detail
        : detail?.message || payload?.message || `HTTP ${response.status}`;
      throw new Error(message);
    }
    return payload;
  }

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function button(text, handler, className = "") {
    const node = el("button", className, text);
    node.type = "button";
    node.addEventListener("click", handler);
    return node;
  }

  function dateTime(value) {
    const date = new Date(value || "");
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function notify(kind = "success") {
    try { tg?.HapticFeedback?.notificationOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function showMessage(text, kind = "") {
    const target = document.getElementById("roxyAccountMessage");
    if (!target) return;
    target.textContent = text || "";
    target.className = `roxy-account-message ${kind}`.trim();
  }

  function section(title, subtitle, id) {
    const root = el("section", "roxy-account-section");
    root.id = id;
    const head = el("div", "roxy-account-section-head");
    const copy = el("div");
    copy.append(el("span", "section-kicker", subtitle), el("h3", "", title));
    head.appendChild(copy);
    root.appendChild(head);
    return { root, head };
  }

  function mount() {
    if (state.mounted) return true;
    const profileView = document.getElementById("profileView");
    const cabinet = document.getElementById("roxyProfileCabinet");
    if (!profileView || !cabinet) return false;

    const root = el("section", "roxy-account-center");
    root.id = "roxyAccountCenter";

    const quick = el("div", "roxy-account-quick-grid");
    const notificationButton = button("", () => scrollToSection("roxyNotifications"), "roxy-account-quick-card");
    notificationButton.id = "roxyNotificationsQuick";
    notificationButton.append(el("span", "roxy-account-quick-icon", "🔔"), el("strong", "", "Уведомления"), el("small", "", "Нет новых"));
    const promoButton = button("", () => scrollToSection("roxyPromo"), "roxy-account-quick-card");
    promoButton.append(el("span", "roxy-account-quick-icon", "🎟"), el("strong", "", "Промокод"), el("small", "", "Активировать бонус"));
    const supportButton = button("", () => scrollToSection("roxySupport"), "roxy-account-quick-card");
    supportButton.append(el("span", "roxy-account-quick-icon", "💬"), el("strong", "", "Поддержка"), el("small", "", "Обращения и ответы"));
    const socialButton = button("", () => scrollToSection("roxySocial"), "roxy-account-quick-card");
    socialButton.append(el("span", "roxy-account-quick-icon", "👤"), el("strong", "", "Подписки"), el("small", "", "Авторы ROXY"));
    const batchButton = button("", () => {
      const url = new URL("/mini-app/batch.html", window.location.origin).toString();
      if (tg?.openLink) tg.openLink(url);
      else window.location.href = url;
    }, "roxy-account-quick-card");
    batchButton.append(el("span", "roxy-account-quick-icon", "▦"), el("strong", "", "Batch"), el("small", "", "Пакетная генерация"));
    quick.append(notificationButton, promoButton, supportButton, socialButton, batchButton);

    const notifications = buildNotifications();
    const promo = buildPromo();
    const support = buildSupport();
    const social = buildSocial();
    const preferences = buildPreferences();
    const message = el("div", "roxy-account-message");
    message.id = "roxyAccountMessage";
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");

    root.append(quick, notifications, promo, support, social, preferences, message);
    cabinet.insertAdjacentElement("afterend", root);
    state.mounted = true;
    document.body?.classList.add("roxy-account-center-ready");
    return true;
  }

  function scrollToSection(id) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function buildNotifications() {
    const { root, head } = section("Уведомления", "События аккаунта", "roxyNotifications");
    const actions = el("div", "roxy-account-inline-actions");
    const unreadToggle = button("Только новые", async () => {
      state.unreadOnly = !state.unreadOnly;
      unreadToggle.classList.toggle("is-active", state.unreadOnly);
      await loadNotifications();
    }, "roxy-account-secondary");
    const markAll = button("Прочитать всё", async () => {
      await api("/api/v1/notifications/read-all", { method: "POST" });
      await loadNotifications();
      notify("success");
    }, "roxy-account-secondary");
    actions.append(unreadToggle, markAll);
    head.appendChild(actions);
    const list = el("div", "roxy-account-list");
    list.id = "roxyNotificationsList";
    root.appendChild(list);
    return root;
  }

  function renderNotifications() {
    const list = document.getElementById("roxyNotificationsList");
    if (!list) return;
    list.replaceChildren();
    if (!state.notifications.length) {
      list.appendChild(el("div", "roxy-account-empty", state.unreadOnly ? "Новых уведомлений нет." : "Уведомлений пока нет."));
    } else {
      state.notifications.forEach((item) => {
        const row = el("article", `roxy-notification-row${item.is_read ? "" : " is-unread"}`);
        const copy = el("div", "roxy-notification-copy");
        copy.append(el("strong", "", item.title), el("p", "", item.body), el("small", "", dateTime(item.created_at)));
        row.appendChild(copy);
        if (!item.is_read) {
          row.appendChild(button("Прочитано", async () => {
            await api(`/api/v1/notifications/${encodeURIComponent(item.id)}/read`, { method: "POST" });
            await loadNotifications();
          }, "roxy-account-secondary compact"));
        }
        list.appendChild(row);
      });
    }
    const quick = document.getElementById("roxyNotificationsQuick");
    const note = quick?.querySelector("small");
    if (note) note.textContent = state.unreadCount > 0 ? `${state.unreadCount} новых` : "Нет новых";
  }

  async function loadNotifications() {
    const query = state.unreadOnly ? "?unread_only=true&limit=50" : "?limit=50";
    const payload = await api(`/api/v1/notifications${query}`);
    state.notifications = payload?.items || [];
    state.unreadCount = Number(payload?.unread_count || 0);
    renderNotifications();
  }

  function buildPromo() {
    const { root } = section("Промокод", "Бонусы ROXY", "roxyPromo");
    const form = el("form", "roxy-promo-form");
    const input = document.createElement("input");
    input.type = "text";
    input.maxLength = 64;
    input.autocomplete = "off";
    input.placeholder = "Введите код";
    input.className = "input";
    const submit = el("button", "primary-button", "Активировать");
    submit.type = "submit";
    form.append(input, submit);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const code = input.value.trim();
      if (!code) return;
      submit.disabled = true;
      try {
        const result = await api("/api/v1/promocodes/redeem", {
          method: "POST",
          body: JSON.stringify({ code }),
        });
        input.value = "";
        notify("success");
        showMessage(`Промокод применён: +${result.reward_rox} ROX. Баланс ${result.balance_rox} ROX.`, "ok");
        window.dispatchEvent(new CustomEvent("roxy:wallet-changed"));
      } catch (error) {
        notify("error");
        showMessage(error.message || "Не удалось применить промокод.", "error");
      } finally {
        submit.disabled = false;
      }
    });
    root.appendChild(form);
    return root;
  }

  function buildSupport() {
    const { root, head } = section("Поддержка", "Диалоги с командой", "roxySupport");
    head.appendChild(button("Новое обращение", () => toggleSupportComposer(true), "roxy-account-secondary"));

    const composer = el("form", "roxy-support-composer");
    composer.id = "roxySupportComposer";
    composer.hidden = true;
    const topic = document.createElement("input");
    topic.className = "input";
    topic.maxLength = 64;
    topic.placeholder = "Тема";
    const message = document.createElement("textarea");
    message.className = "textarea";
    message.maxLength = 8000;
    message.placeholder = "Опишите вопрос";
    const submit = el("button", "primary-button", "Отправить");
    submit.type = "submit";
    composer.append(topic, message, submit);
    composer.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!topic.value.trim() || !message.value.trim()) return;
      submit.disabled = true;
      try {
        await api("/api/v1/support/tickets", {
          method: "POST",
          body: JSON.stringify({ topic: topic.value.trim(), message: message.value.trim() }),
        });
        topic.value = "";
        message.value = "";
        composer.hidden = true;
        await loadTickets();
        notify("success");
      } catch (error) {
        showMessage(error.message || "Не удалось создать обращение.", "error");
      } finally {
        submit.disabled = false;
      }
    });

    const tickets = el("div", "roxy-support-layout");
    const list = el("div", "roxy-support-ticket-list");
    list.id = "roxySupportTickets";
    const detail = el("div", "roxy-support-ticket-detail");
    detail.id = "roxySupportDetail";
    tickets.append(list, detail);
    root.append(composer, tickets);
    return root;
  }

  function toggleSupportComposer(force) {
    const node = document.getElementById("roxySupportComposer");
    if (!node) return;
    node.hidden = typeof force === "boolean" ? !force : !node.hidden;
    if (!node.hidden) node.querySelector("input")?.focus();
  }

  function renderTickets() {
    const list = document.getElementById("roxySupportTickets");
    if (!list) return;
    list.replaceChildren();
    if (!state.tickets.length) list.appendChild(el("div", "roxy-account-empty", "Обращений пока нет."));
    state.tickets.forEach((ticket) => {
      const row = button("", () => void openTicket(ticket.id), `roxy-ticket-row${state.activeTicket?.id === ticket.id ? " is-active" : ""}`);
      const copy = el("div");
      copy.append(el("strong", "", ticket.topic), el("small", "", `${ticket.status} · ${dateTime(ticket.updated_at)}`));
      row.append(copy, el("span", "roxy-ticket-arrow", "›"));
      list.appendChild(row);
    });
    renderTicketDetail();
  }

  function renderTicketDetail() {
    const detail = document.getElementById("roxySupportDetail");
    if (!detail) return;
    detail.replaceChildren();
    const ticket = state.activeTicket;
    if (!ticket) {
      detail.appendChild(el("div", "roxy-account-empty", "Выберите обращение, чтобы открыть переписку."));
      return;
    }
    const head = el("div", "roxy-ticket-detail-head");
    const copy = el("div");
    copy.append(el("strong", "", ticket.topic), el("small", "", ticket.status));
    const actions = el("div", "roxy-account-inline-actions");
    if (ticket.can_close) actions.appendChild(button("Закрыть", async () => {
      await api(`/api/v1/support/tickets/${encodeURIComponent(ticket.id)}/close`, { method: "POST" });
      await openTicket(ticket.id, true);
      await loadTickets(false);
    }, "roxy-account-secondary"));
    if (ticket.can_reopen) actions.appendChild(button("Переоткрыть", async () => {
      await api(`/api/v1/support/tickets/${encodeURIComponent(ticket.id)}/reopen`, { method: "POST" });
      await openTicket(ticket.id, true);
      await loadTickets(false);
    }, "roxy-account-secondary"));
    head.append(copy, actions);

    const messages = el("div", "roxy-ticket-messages");
    (ticket.messages || []).forEach((message) => {
      const bubble = el("div", `roxy-ticket-message ${message.author}`);
      bubble.append(el("p", "", message.body), el("small", "", dateTime(message.created_at)));
      messages.appendChild(bubble);
    });
    detail.append(head, messages);

    if (ticket.can_reply) {
      const form = el("form", "roxy-ticket-reply");
      const input = document.createElement("textarea");
      input.className = "textarea";
      input.maxLength = 8000;
      input.placeholder = "Ответить…";
      const submit = el("button", "primary-button", "Отправить");
      submit.type = "submit";
      form.append(input, submit);
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const message = input.value.trim();
        if (!message) return;
        submit.disabled = true;
        try {
          await api(`/api/v1/support/tickets/${encodeURIComponent(ticket.id)}/messages`, {
            method: "POST",
            body: JSON.stringify({ message }),
          });
          input.value = "";
          await openTicket(ticket.id, true);
        } finally {
          submit.disabled = false;
        }
      });
      detail.appendChild(form);
    }
  }

  async function loadTickets(keepActive = true) {
    const payload = await api("/api/v1/support/tickets?limit=50");
    state.tickets = payload?.items || [];
    if (!keepActive) state.activeTicket = null;
    renderTickets();
  }

  async function openTicket(ticketId, force = false) {
    if (!force && state.activeTicket?.id === ticketId) return;
    state.activeTicket = await api(`/api/v1/support/tickets/${encodeURIComponent(ticketId)}`);
    renderTickets();
  }

  function buildSocial() {
    const { root } = section("Сообщество", "Публичные профили", "roxySocial");
    const search = el("form", "roxy-social-search");
    const input = document.createElement("input");
    input.className = "input";
    input.placeholder = "@username";
    input.maxLength = 64;
    const submit = el("button", "primary-button", "Найти");
    submit.type = "submit";
    search.append(input, submit);
    search.addEventListener("submit", async (event) => {
      event.preventDefault();
      const username = input.value.trim();
      if (!username) return;
      submit.disabled = true;
      try {
        state.socialProfile = await api(`/api/v1/social/profiles?username=${encodeURIComponent(username)}`);
        renderSocial();
      } catch (error) {
        state.socialProfile = null;
        renderSocial();
        showMessage(error.message || "Профиль не найден.", "error");
      } finally {
        submit.disabled = false;
      }
    });
    const result = el("div", "roxy-social-result");
    result.id = "roxySocialResult";
    const subscriptions = el("div", "roxy-social-subscriptions");
    subscriptions.id = "roxySocialSubscriptions";
    root.append(search, result, subscriptions);
    return root;
  }

  function profileCard(profile) {
    const card = el("article", "roxy-social-profile-card");
    const copy = el("div");
    copy.append(el("strong", "", profile.display_name || "Пользователь ROXY"));
    if (profile.username) copy.appendChild(el("small", "", `@${profile.username}`));
    copy.appendChild(el("span", "", `${Number(profile.follower_count || 0)} подписчиков`));
    card.appendChild(copy);
    if (!profile.is_self) {
      card.appendChild(button(profile.subscribed_by_me ? "Отписаться" : "Подписаться", async () => {
        const method = profile.subscribed_by_me ? "DELETE" : "POST";
        state.socialProfile = await api(`/api/v1/social/profiles/${encodeURIComponent(profile.id)}/subscribe`, { method });
        await loadSubscriptions();
        renderSocial();
      }, profile.subscribed_by_me ? "roxy-account-secondary" : "primary-button"));
    }
    return card;
  }

  function renderSocial() {
    const result = document.getElementById("roxySocialResult");
    const subscriptions = document.getElementById("roxySocialSubscriptions");
    if (result) {
      result.replaceChildren();
      if (state.socialProfile) result.appendChild(profileCard(state.socialProfile));
    }
    if (subscriptions) {
      subscriptions.replaceChildren(el("h4", "", "Мои подписки"));
      if (!state.subscriptions.length) subscriptions.appendChild(el("div", "roxy-account-empty", "Вы пока ни на кого не подписаны."));
      state.subscriptions.forEach((profile) => subscriptions.appendChild(profileCard({ ...profile, follower_count: profile.follower_count || 0 })));
    }
  }

  async function loadSubscriptions() {
    const payload = await api("/api/v1/social/subscriptions?limit=50");
    state.subscriptions = payload?.items || [];
    renderSocial();
  }

  function buildPreferences() {
    const { root } = section("Настройки", "Профиль и уведомления", "roxyPreferences");
    const form = el("form", "roxy-preferences-form");
    form.id = "roxyPreferencesForm";
    root.appendChild(form);
    return root;
  }

  function checkbox(name, label, value) {
    const wrapper = el("label", "roxy-preference-check");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.name = name;
    input.checked = Boolean(value);
    wrapper.append(input, el("span", "", label));
    return wrapper;
  }

  function renderPreferences() {
    const form = document.getElementById("roxyPreferencesForm");
    if (!form || !state.preferences) return;
    form.replaceChildren();
    const language = document.createElement("select");
    language.className = "input";
    language.name = "ui_language";
    [["auto", "Авто"], ["ru", "Русский"], ["en", "English"]].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      if (state.preferences.ui_language === value) option.selected = true;
      language.appendChild(option);
    });
    const languageLabel = el("label", "roxy-preference-language");
    languageLabel.append(el("span", "", "Язык интерфейса"), language);
    const notifications = checkbox("notifications_enabled", "Системные уведомления", state.preferences.notifications_enabled);
    const marketing = checkbox("marketing_notifications", "Новости и маркетинг", state.preferences.marketing_notifications);
    const discoverable = checkbox("profile_discoverable", "Публичный профиль и подписки", state.preferences.profile_discoverable);
    const submit = el("button", "primary-button", "Сохранить настройки");
    submit.type = "submit";
    form.append(languageLabel, notifications, marketing, discoverable, submit);
    form.onsubmit = async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        state.preferences = await api("/api/v1/me/preferences", {
          method: "PUT",
          body: JSON.stringify({
            ui_language: language.value,
            notifications_enabled: form.elements.notifications_enabled.checked,
            marketing_notifications: form.elements.marketing_notifications.checked,
            profile_discoverable: form.elements.profile_discoverable.checked,
          }),
        });
        notify("success");
        showMessage("Настройки сохранены.", "ok");
      } catch (error) {
        showMessage(error.message || "Не удалось сохранить настройки.", "error");
      } finally {
        submit.disabled = false;
      }
    };
  }

  async function load(force = false) {
    if (!tg?.initData || state.loading) return;
    if (!mount()) return;
    if (!force && state.notifications.length && state.preferences) return;
    state.loading = true;
    try {
      const [notifications, tickets, subscriptions, preferences] = await Promise.all([
        api("/api/v1/notifications?limit=50"),
        api("/api/v1/support/tickets?limit=50"),
        api("/api/v1/social/subscriptions?limit=50"),
        api("/api/v1/me/preferences"),
      ]);
      state.notifications = notifications?.items || [];
      state.unreadCount = Number(notifications?.unread_count || 0);
      state.tickets = tickets?.items || [];
      state.subscriptions = subscriptions?.items || [];
      state.preferences = preferences;
      renderNotifications();
      renderTickets();
      renderSocial();
      renderPreferences();
    } catch (error) {
      showMessage(error.message || "Не удалось загрузить кабинет.", "error");
    } finally {
      state.loading = false;
    }
  }

  function init() {
    const tryMount = () => {
      if (!mount()) return false;
      const profile = document.getElementById("profileView");
      if (profile && !profile.hidden) void load();
      return true;
    };
    if (!tryMount()) {
      let attempts = 0;
      const timer = window.setInterval(() => {
        attempts += 1;
        if (tryMount() || attempts > 30) window.clearInterval(timer);
      }, 100);
    }
    document.addEventListener("click", (event) => {
      if (event.target.closest?.('[data-roxy-customer-route="profile"], [data-shell-nav="profile"]')) {
        window.setTimeout(() => void load(true), 40);
      }
    }, true);
    tg?.onEvent?.("activated", () => {
      const profile = document.getElementById("profileView");
      if (profile && !profile.hidden) void load(true);
    });
  }

  window.RoxyAccountCenter = Object.freeze({ load: () => load(true) });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
