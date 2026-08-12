(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const profileView = document.getElementById("profileView");
  if (!profileView) return;

  const state = {
    mounted: false,
    loaded: false,
    preferences: null,
    notifications: [],
    unreadCount: 0,
    tickets: [],
    activeTicket: null,
  };

  const dom = {};

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function authHeaders(json = false) {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    if (json) headers["Content-Type"] = "application/json";
    return headers;
  }

  async function api(path, options = {}) {
    const hasBody = options.body !== undefined;
    const response = await fetch(path, {
      ...options,
      headers: { ...authHeaders(hasBody), ...(options.headers || {}) },
      credentials: "same-origin",
      cache: "no-store",
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }
    if (!response.ok) {
      const error = new Error(payload?.detail || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function haptic(kind = "light") {
    try {
      tg?.HapticFeedback?.impactOccurred?.(kind);
    } catch (_error) {
      // Optional Telegram client capability.
    }
  }

  function notify(kind = "success") {
    try {
      tg?.HapticFeedback?.notificationOccurred?.(kind);
    } catch (_error) {
      // Optional Telegram client capability.
    }
  }

  function formatDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function ticketStatusLabel(status) {
    return {
      open: "Открыто",
      in_progress: "В работе",
      resolved: "Решено",
      closed: "Закрыто",
    }[status] || status || "—";
  }

  function setMessage(node, message = "", tone = "") {
    node.textContent = message;
    node.className = `profile-message${tone ? ` ${tone}` : ""}`;
  }

  function makeSection(kicker, title) {
    const section = el("section", "profile-tools-section");
    const head = el("div", "profile-tools-head");
    const copy = el("div");
    copy.append(el("span", "section-kicker", kicker), el("h2", "", title));
    head.appendChild(copy);
    section.appendChild(head);
    return { section, head };
  }

  function settingRow(title, description, control) {
    const row = el("div", "profile-setting-row");
    const copy = el("div", "profile-setting-copy");
    copy.append(el("strong", "", title), el("small", "", description));
    row.append(copy, control);
    return row;
  }

  function switchControl(id, label) {
    const wrap = el("label", "profile-switch");
    wrap.setAttribute("aria-label", label);
    const input = document.createElement("input");
    input.type = "checkbox";
    input.id = id;
    const track = document.createElement("span");
    track.setAttribute("aria-hidden", "true");
    wrap.append(input, track);
    return { wrap, input };
  }

  function mount() {
    if (state.mounted) return;
    state.mounted = true;

    const root = el("div", "profile-tools");
    root.id = "profileTools";

    const settings = makeSection("Настройки", "Профиль и уведомления");
    const settingsPanel = el("div", "shell-panel profile-settings");
    const identityNote = el(
      "div",
      "profile-identity-note",
      "Имя и username берутся из Telegram и обновляются автоматически. Здесь сохраняются только настройки приложения.",
    );

    const language = document.createElement("select");
    language.id = "profileUiLanguage";
    language.setAttribute("aria-label", "Предпочитаемый язык интерфейса");
    [
      ["auto", "Как в Telegram"],
      ["ru", "Русский"],
      ["en", "English"],
    ].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      language.appendChild(option);
    });

    const notifications = switchControl("profileNotificationsEnabled", "Получать уведомления");
    const marketing = switchControl("profileMarketingNotifications", "Получать новости и предложения");
    const discoverable = switchControl("profileDiscoverable", "Публичный профиль");

    settingsPanel.append(
      identityNote,
      settingRow("Предпочитаемый язык", "Серверная настройка интерфейса", language),
      settingRow("Уведомления", "Системные уведомления о важных событиях", notifications.wrap),
      settingRow("Новости и предложения", "Отдельное согласие на маркетинговые сообщения", marketing.wrap),
      settingRow("Публичный профиль", "Разрешение на отображение профиля в публичных разделах", discoverable.wrap),
    );
    const settingsActions = el("div", "profile-toolbar");
    const saveSettings = el("button", "profile-save-button", "Сохранить настройки");
    saveSettings.type = "button";
    const settingsMessage = el("div", "profile-message");
    settingsActions.appendChild(saveSettings);
    settingsPanel.append(settingsActions, settingsMessage);
    settings.section.appendChild(settingsPanel);

    const notificationSection = makeSection("События", "Уведомления");
    const notificationMeta = el("div", "profile-toolbar");
    const unreadBadge = el("span", "notification-badge", "0");
    unreadBadge.id = "profileUnreadBadge";
    unreadBadge.setAttribute("aria-label", "Непрочитанных уведомлений: 0");
    const readAll = el("button", "profile-action-button secondary", "Прочитать все");
    readAll.type = "button";
    notificationMeta.append(unreadBadge, readAll);
    notificationSection.head.appendChild(notificationMeta);
    const notificationList = el("div", "shell-panel notification-list");
    notificationList.id = "profileNotificationList";
    notificationList.setAttribute("aria-live", "polite");
    notificationSection.section.appendChild(notificationList);

    const support = makeSection("Помощь", "Поддержка");
    const supportPanel = el("div", "shell-panel");
    const compose = el("form", "support-compose");
    compose.id = "supportComposeForm";
    const topic = document.createElement("input");
    topic.type = "text";
    topic.maxLength = 64;
    topic.placeholder = "Тема обращения";
    topic.setAttribute("aria-label", "Тема обращения");
    const message = document.createElement("textarea");
    message.maxLength = 8000;
    message.placeholder = "Опишите вопрос или проблему";
    message.setAttribute("aria-label", "Сообщение в поддержку");
    const createTicket = el("button", "profile-action-button", "Создать обращение");
    createTicket.type = "submit";
    const supportMessage = el("div", "profile-message");
    compose.append(topic, message, createTicket, supportMessage);

    const ticketsWrap = el("div");
    const ticketsHead = el("div", "support-thread-head");
    ticketsHead.appendChild(el("h3", "", "Мои обращения"));
    const refreshTickets = el("button", "profile-action-button secondary", "Обновить");
    refreshTickets.type = "button";
    ticketsHead.appendChild(refreshTickets);
    const ticketList = el("div", "support-ticket-list");
    ticketList.id = "profileSupportTickets";
    ticketList.setAttribute("aria-live", "polite");
    ticketsWrap.append(ticketsHead, ticketList);

    const ticketDetail = el("div");
    ticketDetail.id = "profileSupportDetail";
    ticketDetail.hidden = true;

    supportPanel.append(compose, ticketsWrap, ticketDetail);
    support.section.appendChild(supportPanel);

    root.append(settings.section, notificationSection.section, support.section);
    profileView.appendChild(root);

    Object.assign(dom, {
      root,
      language,
      notifications: notifications.input,
      marketing: marketing.input,
      discoverable: discoverable.input,
      saveSettings,
      settingsMessage,
      unreadBadge,
      readAll,
      notificationList,
      compose,
      topic,
      message,
      createTicket,
      supportMessage,
      ticketsWrap,
      ticketList,
      refreshTickets,
      ticketDetail,
    });

    dom.notifications.addEventListener("change", () => {
      if (!dom.notifications.checked) {
        dom.marketing.checked = false;
        dom.marketing.disabled = true;
      } else {
        dom.marketing.disabled = false;
      }
    });
    dom.saveSettings.addEventListener("click", savePreferences);
    dom.readAll.addEventListener("click", markAllRead);
    dom.compose.addEventListener("submit", createSupportTicket);
    dom.refreshTickets.addEventListener("click", () => loadTickets(true));
  }

  function renderLoading(container, count = 2) {
    container.replaceChildren();
    for (let index = 0; index < count; index += 1) {
      container.appendChild(el("div", "shell-skeleton"));
    }
  }

  function renderUnavailable(container, message) {
    container.replaceChildren(el("div", "profile-empty", message));
  }

  async function loadPreferences() {
    const payload = await api("/api/v1/me/preferences");
    state.preferences = payload;
    dom.language.value = payload.ui_language || "auto";
    dom.notifications.checked = Boolean(payload.notifications_enabled);
    dom.marketing.checked = Boolean(payload.marketing_notifications);
    dom.discoverable.checked = Boolean(payload.profile_discoverable);
    dom.marketing.disabled = !dom.notifications.checked;
    setMessage(dom.settingsMessage);
  }

  async function savePreferences() {
    if (!tg?.initData) return;
    haptic();
    dom.saveSettings.disabled = true;
    setMessage(dom.settingsMessage, "Сохраняю…");
    const payload = {
      ui_language: dom.language.value,
      notifications_enabled: dom.notifications.checked,
      marketing_notifications: dom.notifications.checked && dom.marketing.checked,
      profile_discoverable: dom.discoverable.checked,
    };
    try {
      state.preferences = await api("/api/v1/me/preferences", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      dom.marketing.checked = Boolean(state.preferences.marketing_notifications);
      setMessage(dom.settingsMessage, "Настройки сохранены", "ok");
      notify("success");
    } catch (error) {
      setMessage(dom.settingsMessage, error.message || "Не удалось сохранить настройки", "error");
      notify("error");
    } finally {
      dom.saveSettings.disabled = false;
    }
  }

  async function loadNotifications(showLoading = false) {
    if (showLoading) renderLoading(dom.notificationList);
    try {
      const payload = await api("/api/v1/notifications?limit=50");
      state.notifications = Array.isArray(payload?.items) ? payload.items : [];
      state.unreadCount = Number(payload?.unread_count || 0);
      renderNotifications();
    } catch (error) {
      renderUnavailable(dom.notificationList, error.message || "Не удалось загрузить уведомления");
    }
  }

  function syncUnreadBadge() {
    const value = Math.max(0, Number(state.unreadCount || 0));
    dom.unreadBadge.textContent = value > 99 ? "99+" : String(value);
    dom.unreadBadge.hidden = value === 0;
    dom.unreadBadge.setAttribute("aria-label", `Непрочитанных уведомлений: ${value}`);
    dom.readAll.disabled = value === 0;

    const profileNav = document.querySelector('.bottom-nav-item[data-shell-nav="profile"]');
    if (!profileNav) return;
    let badge = profileNav.querySelector(".profile-nav-badge");
    if (value === 0) {
      badge?.remove();
      return;
    }
    if (!badge) {
      badge = el("span", "profile-nav-badge");
      badge.setAttribute("aria-hidden", "true");
      profileNav.appendChild(badge);
    }
    badge.textContent = value > 9 ? "9+" : String(value);
  }

  function renderNotifications() {
    dom.notificationList.replaceChildren();
    syncUnreadBadge();
    if (!state.notifications.length) {
      renderUnavailable(dom.notificationList, "Пока нет уведомлений.");
      return;
    }
    for (const item of state.notifications) {
      const card = el("button", `notification-item${item.is_read ? "" : " is-unread"}`);
      card.type = "button";
      card.dataset.notificationId = item.id;
      card.style.border = "0";
      card.style.color = "inherit";
      card.style.textAlign = "left";
      card.style.width = "100%";
      const head = el("div", "notification-item-head");
      head.append(el("h3", "", item.title || "Уведомление"), el("small", "", formatDate(item.created_at)));
      const body = el("p", "", item.body || "");
      card.append(head, body);
      if (!item.is_read) {
        card.addEventListener("click", () => markOneRead(item.id, card));
      }
      dom.notificationList.appendChild(card);
    }
  }

  async function markOneRead(id, card) {
    haptic();
    try {
      await api(`/api/v1/notifications/${encodeURIComponent(id)}/read`, { method: "POST" });
      const item = state.notifications.find((entry) => entry.id === id);
      if (item && !item.is_read) {
        item.is_read = true;
        state.unreadCount = Math.max(0, state.unreadCount - 1);
      }
      card.classList.remove("is-unread");
      syncUnreadBadge();
    } catch (_error) {
      notify("error");
    }
  }

  async function markAllRead() {
    if (!state.unreadCount) return;
    haptic();
    dom.readAll.disabled = true;
    try {
      await api("/api/v1/notifications/read-all", { method: "POST" });
      state.notifications.forEach((item) => {
        item.is_read = true;
      });
      state.unreadCount = 0;
      renderNotifications();
      notify("success");
    } catch (_error) {
      dom.readAll.disabled = false;
      notify("error");
    }
  }

  async function loadTickets(showLoading = false) {
    if (showLoading) renderLoading(dom.ticketList);
    try {
      const payload = await api("/api/v1/support/tickets?limit=50");
      state.tickets = Array.isArray(payload?.items) ? payload.items : [];
      renderTickets();
    } catch (error) {
      renderUnavailable(dom.ticketList, error.message || "Не удалось загрузить обращения");
    }
  }

  function renderTickets() {
    dom.ticketList.replaceChildren();
    if (!state.tickets.length) {
      renderUnavailable(dom.ticketList, "Обращений пока нет. Создайте первое выше.");
      return;
    }
    for (const ticket of state.tickets) {
      const card = el("button", "support-ticket");
      card.type = "button";
      card.style.border = "0";
      card.style.color = "inherit";
      card.style.textAlign = "left";
      card.style.width = "100%";
      const head = el("div", "support-ticket-head");
      head.append(el("h3", "", ticket.topic || "Без темы"), el("small", "", ticketStatusLabel(ticket.status)));
      card.append(head, el("small", "", `Обновлено ${formatDate(ticket.updated_at || ticket.created_at)}`));
      card.addEventListener("click", () => openTicket(ticket.id));
      dom.ticketList.appendChild(card);
    }
  }

  async function createSupportTicket(event) {
    event.preventDefault();
    if (!tg?.initData) return;
    const topic = dom.topic.value.trim();
    const message = dom.message.value.trim();
    if (!topic || !message) {
      setMessage(dom.supportMessage, "Заполните тему и сообщение", "error");
      return;
    }
    haptic();
    dom.createTicket.disabled = true;
    setMessage(dom.supportMessage, "Создаю обращение…");
    try {
      const ticket = await api("/api/v1/support/tickets", {
        method: "POST",
        body: JSON.stringify({ topic, message }),
      });
      dom.topic.value = "";
      dom.message.value = "";
      setMessage(dom.supportMessage, "Обращение создано", "ok");
      notify("success");
      await loadTickets();
      await openTicket(ticket.id);
    } catch (error) {
      setMessage(dom.supportMessage, error.message || "Не удалось создать обращение", "error");
      notify("error");
    } finally {
      dom.createTicket.disabled = false;
    }
  }

  async function openTicket(id) {
    haptic();
    dom.ticketDetail.hidden = false;
    dom.ticketsWrap.hidden = true;
    dom.ticketDetail.replaceChildren(el("div", "shell-skeleton tall"));
    try {
      state.activeTicket = await api(`/api/v1/support/tickets/${encodeURIComponent(id)}`);
      renderTicketDetail();
    } catch (error) {
      dom.ticketDetail.replaceChildren();
      const errorBlock = el("div", "profile-empty", error.message || "Не удалось открыть обращение");
      const back = el("button", "profile-action-button secondary", "К обращениям");
      back.type = "button";
      back.addEventListener("click", closeTicketDetail);
      dom.ticketDetail.append(errorBlock, back);
    }
  }

  function closeTicketDetail() {
    state.activeTicket = null;
    dom.ticketDetail.hidden = true;
    dom.ticketsWrap.hidden = false;
  }

  function renderTicketDetail() {
    const ticket = state.activeTicket;
    dom.ticketDetail.replaceChildren();
    if (!ticket) return;

    const head = el("div", "support-thread-head");
    const titleWrap = el("div");
    titleWrap.append(el("h3", "", ticket.topic || "Обращение"), el("small", "", ticketStatusLabel(ticket.status)));
    const back = el("button", "profile-action-button secondary", "Назад");
    back.type = "button";
    back.addEventListener("click", closeTicketDetail);
    head.append(titleWrap, back);

    const thread = el("div", "support-thread");
    const messages = Array.isArray(ticket.messages) ? ticket.messages : [];
    if (!messages.length) {
      thread.appendChild(el("div", "profile-empty", "Сообщений пока нет."));
    } else {
      for (const message of messages) {
        const item = el("div", `support-message ${message.author === "support" ? "support" : "user"}`);
        item.append(
          el("small", "", message.author === "support" ? "Поддержка" : "Вы"),
          el("p", "", message.body || ""),
          el("small", "", formatDate(message.created_at)),
        );
        thread.appendChild(item);
      }
    }

    const actions = el("div", "profile-toolbar");
    if (ticket.can_close) {
      const close = el("button", "profile-action-button secondary", "Закрыть обращение");
      close.type = "button";
      close.addEventListener("click", () => changeTicketState("close"));
      actions.appendChild(close);
    }
    if (ticket.can_reopen) {
      const reopen = el("button", "profile-action-button", "Переоткрыть");
      reopen.type = "button";
      reopen.addEventListener("click", () => changeTicketState("reopen"));
      actions.appendChild(reopen);
    }

    dom.ticketDetail.append(head, thread, actions);

    if (ticket.can_reply) {
      const reply = el("form", "support-reply");
      const textarea = document.createElement("textarea");
      textarea.maxLength = 8000;
      textarea.placeholder = "Ответить в поддержку";
      textarea.setAttribute("aria-label", "Ответ в поддержку");
      const send = el("button", "profile-action-button", "Отправить");
      send.type = "submit";
      const message = el("div", "profile-message");
      reply.append(textarea, send, message);
      reply.addEventListener("submit", (event) => replyToTicket(event, textarea, send, message));
      dom.ticketDetail.appendChild(reply);
    }
  }

  async function replyToTicket(event, textarea, button, messageNode) {
    event.preventDefault();
    const message = textarea.value.trim();
    if (!message) {
      setMessage(messageNode, "Введите сообщение", "error");
      return;
    }
    button.disabled = true;
    setMessage(messageNode, "Отправляю…");
    try {
      await api(`/api/v1/support/tickets/${encodeURIComponent(state.activeTicket.id)}/messages`, {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      notify("success");
      await openTicket(state.activeTicket.id);
      await loadTickets();
    } catch (error) {
      setMessage(messageNode, error.message || "Не удалось отправить сообщение", "error");
      notify("error");
      button.disabled = false;
    }
  }

  async function changeTicketState(action) {
    if (!state.activeTicket) return;
    haptic();
    const id = state.activeTicket.id;
    try {
      await api(`/api/v1/support/tickets/${encodeURIComponent(id)}/${action}`, { method: "POST" });
      notify("success");
      await openTicket(id);
      await loadTickets();
    } catch (_error) {
      notify("error");
    }
  }

  async function loadAll({ force = false } = {}) {
    mount();
    if (!tg?.initData) {
      renderUnavailable(dom.notificationList, "Откройте Mini App через Telegram, чтобы увидеть уведомления.");
      renderUnavailable(dom.ticketList, "Поддержка доступна после входа через Telegram.");
      dom.saveSettings.disabled = true;
      dom.createTicket.disabled = true;
      return;
    }
    if (state.loaded && !force) return;
    state.loaded = true;
    renderLoading(dom.notificationList);
    renderLoading(dom.ticketList);
    await Promise.allSettled([loadPreferences(), loadNotifications(), loadTickets()]);
  }

  function profileVisible() {
    return !profileView.hidden;
  }

  mount();
  document.addEventListener(
    "click",
    (event) => {
      const nav = event.target.closest('[data-shell-nav="profile"]');
      if (!nav) return;
      queueMicrotask(() => loadAll({ force: state.loaded }));
    },
    true,
  );
  tg?.onEvent?.("activated", () => {
    if (profileVisible()) loadAll({ force: true });
  });
  window.addEventListener("online", () => {
    if (profileVisible()) loadAll({ force: true });
  });

  if (profileVisible()) loadAll();
})();
