(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const state = {
    token: null,
    me: null,
    permissions: new Set(),
    view: "dashboard",
    pendingSensitive: null,
    currentUserId: null,
    currentTicketId: null,
  };

  const dom = Object.fromEntries(
    [
      "authView", "loginForm", "loginOtp", "loginRecovery", "loginButton", "loginMessage",
      "bootstrapButton", "bootstrapPanel", "bootstrapConfirm", "adminShell", "sidebar", "adminNav",
      "adminIdentity", "logoutButton", "sidebarToggle", "viewKicker", "viewTitle", "sessionStatus",
      "refreshButton", "adminView", "mfaSetupDialog", "mfaSecret", "mfaUri", "mfaConfirmOtp",
      "mfaConfirmButton", "mfaSetupMessage", "recoveryDialog", "recoveryCodes", "recoveryDone",
      "stepUpDialog", "stepUpTitle", "stepUpDescription", "stepUpOtp", "stepUpRecovery",
      "stepUpMessage", "stepConfirm", "stepUpCancel", "stepUpVerify", "stepUpExecute",
      "formDialog", "genericForm", "formKicker", "formTitle", "formFields", "formMessage",
      "formCancel", "formSubmit", "adminToast",
    ].map((id) => [id, document.getElementById(id)]),
  );

  const NAV = [
    ["dashboard", "Обзор", "◫", "dashboard.read"],
    ["users", "Пользователи", "◎", "users.read"],
    ["generations", "Генерации", "✦", "generations.read"],
    ["payments", "Платежи", "₽", "payments.read"],
    ["support", "Поддержка", "◌", "support.read"],
    ["withdrawals", "Выводы", "↗", "withdrawals.read"],
    ["promos", "Промокоды", "%", "promocodes.read"],
    ["referrals", "Рефералы", "⌘", "referrals.read"],
    ["security", "Security / Audit", "⌁", ["security.read", "audit.read"]],
    ["admins", "Администраторы", "♙", "admins.read"],
    ["sessions", "Мои сессии", "◷", null],
  ];

  const TITLES = {
    dashboard: ["OPERATIONS", "Обзор"],
    users: ["USERS", "Пользователи"],
    generations: ["AI JOBS", "Генерации"],
    payments: ["FINANCE", "Платежи"],
    support: ["SUPPORT", "Обращения"],
    withdrawals: ["PARTNERS", "Выводы партнёров"],
    promos: ["GROWTH", "Промокоды"],
    referrals: ["PARTNERS", "Реферальные начисления"],
    security: ["SECURITY", "Audit и безопасность"],
    admins: ["ACCESS", "Администраторы"],
    sessions: ["SECURITY", "Мои сессии"],
  };

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null && text !== "") node.textContent = String(text);
    return node;
  }

  function button(label, className = "table-action", handler = null) {
    const node = el("button", className, label);
    node.type = "button";
    if (handler) node.addEventListener("click", handler);
    return node;
  }

  function setMessage(node, text = "", tone = "") {
    if (!node) return;
    node.textContent = text;
    node.className = `form-message${tone ? ` ${tone}` : ""}`;
  }

  function toast(message) {
    dom.adminToast.textContent = message;
    dom.adminToast.hidden = false;
    window.setTimeout(() => {
      if (dom.adminToast.textContent === message) dom.adminToast.hidden = true;
    }, 3200);
  }

  function haptic(kind = "light") {
    try { tg?.HapticFeedback?.impactOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function notify(kind = "success") {
    try { tg?.HapticFeedback?.notificationOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function telegramHeaders() {
    return tg?.initData ? { "X-Telegram-Init-Data": tg.initData } : {};
  }

  function detailMessage(payload, fallback) {
    const detail = payload?.detail;
    if (typeof detail === "string") return detail;
    if (detail?.message) return detail.message;
    return fallback;
  }

  async function api(path, options = {}) {
    const { telegram = false, auth = true, ...fetchOptions } = options;
    const headers = { Accept: "application/json", ...(fetchOptions.headers || {}) };
    if (fetchOptions.body !== undefined && !(fetchOptions.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }
    if (auth && state.token) headers.Authorization = `Bearer ${state.token}`;
    if (telegram) Object.assign(headers, telegramHeaders());

    const response = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...fetchOptions,
      headers,
    });
    let payload = null;
    try { payload = await response.json(); } catch (_error) { payload = null; }
    if (!response.ok) {
      const error = new Error(detailMessage(payload, `HTTP ${response.status}`));
      error.status = response.status;
      error.payload = payload;
      error.requestId = response.headers.get("X-Request-ID");
      if (response.status === 401 && auth && !path.endsWith("/login")) {
        clearSession("Сессия истекла. Войдите снова.");
      }
      throw error;
    }
    return payload;
  }

  function hasPermission(permission) {
    if (!permission) return true;
    if (state.permissions.has("*")) return true;
    if (Array.isArray(permission)) return permission.some((item) => state.permissions.has(item));
    return state.permissions.has(permission);
  }

  function statusBadge(value) {
    const normalized = String(value ?? "unknown").toLowerCase();
    let tone = "info";
    if (["success", "succeeded", "paid", "resolved", "active", "completed", "available"].includes(normalized)) tone = "ok";
    if (["pending", "processing", "queued", "generating", "in_progress", "retry", "creating"].includes(normalized)) tone = "warn";
    if (["failed", "fail", "rejected", "canceled", "cancelled", "blocked", "inactive", "reversed"].includes(normalized)) tone = "danger";
    return el("span", `badge ${tone}`, value ?? "—");
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("ru-RU", {
      year: "2-digit", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    }).format(date);
  }

  function formatNumber(value, maximumFractionDigits = 2) {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value ?? "—");
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits }).format(number);
  }

  function loading(container = dom.adminView, count = 6) {
    container.replaceChildren();
    const list = el("div", "loading-list panel");
    for (let i = 0; i < count; i += 1) list.appendChild(el("div", "skeleton"));
    container.appendChild(list);
  }

  function empty(message) {
    return el("div", "empty", message);
  }

  function panel(title, body, actions = null) {
    const root = el("section", "panel");
    const head = el("div", "panel-head");
    head.appendChild(el("h2", "", title));
    if (actions) head.appendChild(actions);
    root.append(head, body);
    return root;
  }

  function table(columns, rows) {
    const wrap = el("div", "table-wrap");
    if (!rows.length) {
      wrap.appendChild(empty("Нет данных для текущего фильтра."));
      return wrap;
    }
    const tableNode = el("table", "data-table");
    const thead = document.createElement("thead");
    const hrow = document.createElement("tr");
    columns.forEach(([label]) => hrow.appendChild(el("th", "", label)));
    thead.appendChild(hrow);
    const tbody = document.createElement("tbody");
    for (const row of rows) {
      const tr = document.createElement("tr");
      for (const [, render] of columns) {
        const td = document.createElement("td");
        const value = render(row);
        if (value instanceof Node) td.appendChild(value);
        else td.textContent = value == null ? "—" : String(value);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    tableNode.append(thead, tbody);
    wrap.appendChild(tableNode);
    return wrap;
  }

  function actionsCell(...items) {
    const node = el("div", "actions");
    items.filter(Boolean).forEach((item) => node.appendChild(item));
    return node;
  }

  function metric(label, value, note = "") {
    const node = el("div", "metric");
    node.append(el("small", "", label), el("strong", "", value));
    if (note) node.appendChild(el("span", "metric-note", note));
    return node;
  }

  function kvRows(entries) {
    const dl = el("dl", "kv");
    entries.forEach(([key, value]) => {
      dl.append(el("dt", "", key), value instanceof Node ? (() => { const dd = document.createElement("dd"); dd.appendChild(value); return dd; })() : el("dd", "", value ?? "—"));
    });
    return dl;
  }

  function jsonText(value) {
    try { return JSON.stringify(value ?? {}, null, 2); } catch (_error) { return String(value ?? ""); }
  }

  function makeFilter(fields, onSubmit) {
    const form = el("form", "filter-bar");
    for (const field of fields) {
      let input;
      if (field.options) {
        input = document.createElement("select");
        for (const [value, label] of field.options) {
          const option = document.createElement("option");
          option.value = value;
          option.textContent = label;
          input.appendChild(option);
        }
      } else {
        input = document.createElement("input");
        input.type = field.type || "text";
        input.placeholder = field.placeholder || field.name;
      }
      input.name = field.name;
      if (field.value != null) input.value = field.value;
      if (field.grow) input.classList.add("grow");
      form.appendChild(input);
    }
    const submit = button("Применить", "primary");
    submit.type = "submit";
    form.appendChild(submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(form).entries());
      onSubmit(data);
    });
    return form;
  }

  function fieldNode(field) {
    const label = el("label", "field");
    label.appendChild(el("span", "", field.label));
    let control;
    if (field.type === "select") {
      control = document.createElement("select");
      for (const [value, text] of field.options || []) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = text;
        control.appendChild(option);
      }
    } else if (field.type === "textarea") {
      control = document.createElement("textarea");
    } else if (field.type === "checkbox") {
      control = document.createElement("input");
      control.type = "checkbox";
      control.checked = Boolean(field.value);
    } else {
      control = document.createElement("input");
      control.type = field.type || "text";
      if (field.value != null) control.value = field.value;
    }
    control.name = field.name;
    if (field.placeholder) control.placeholder = field.placeholder;
    if (field.required !== false && field.type !== "checkbox") control.required = true;
    if (field.min != null) control.min = field.min;
    if (field.max != null) control.max = field.max;
    if (field.step != null) control.step = field.step;
    if (field.maxLength != null) control.maxLength = field.maxLength;
    if (field.type === "select" && field.value != null) control.value = field.value;
    label.appendChild(control);
    if (field.help) label.appendChild(el("small", "", field.help));
    return label;
  }

  function openForm(config) {
    dom.formKicker.textContent = config.kicker || "ACTION";
    dom.formTitle.textContent = config.title;
    dom.formFields.replaceChildren();
    config.fields.forEach((field) => dom.formFields.appendChild(fieldNode(field)));
    dom.formSubmit.textContent = config.submitLabel || "Сохранить";
    setMessage(dom.formMessage);
    dom.genericForm.onsubmit = async (event) => {
      event.preventDefault();
      dom.formSubmit.disabled = true;
      const data = {};
      for (const [name, value] of new FormData(dom.genericForm).entries()) data[name] = value;
      for (const checkbox of dom.genericForm.querySelectorAll('input[type="checkbox"][name]')) data[checkbox.name] = checkbox.checked;
      try {
        const result = await config.onSubmit(data);
        if (result !== false) dom.formDialog.close();
      } catch (error) {
        setMessage(dom.formMessage, error.message || "Ошибка", "error");
      } finally {
        dom.formSubmit.disabled = false;
      }
    };
    dom.formDialog.showModal();
    requestAnimationFrame(() => dom.formFields.querySelector("input,select,textarea")?.focus());
  }

  async function executeOrStepUp(label, action) {
    try {
      return await action();
    } catch (error) {
      if (error.status === 403 && /step-up/i.test(error.message || "")) {
        openStepUp(label, action);
        return null;
      }
      throw error;
    }
  }

  function openStepUp(label, action) {
    state.pendingSensitive = { label, action };
    dom.stepUpTitle.textContent = "Подтвердите чувствительное действие";
    dom.stepUpDescription.textContent = label;
    dom.stepUpOtp.value = "";
    dom.stepUpRecovery.value = "";
    setMessage(dom.stepUpMessage);
    dom.stepConfirm.hidden = true;
    dom.stepUpVerify.hidden = false;
    dom.stepUpExecute.hidden = true;
    dom.stepUpDialog.showModal();
    requestAnimationFrame(() => dom.stepUpOtp.focus());
  }

  async function verifyStepUp() {
    const otp = dom.stepUpOtp.value.trim();
    const recovery = dom.stepUpRecovery.value.trim();
    if (!otp && !recovery) {
      setMessage(dom.stepUpMessage, "Введите OTP или recovery code", "error");
      return;
    }
    dom.stepUpVerify.disabled = true;
    setMessage(dom.stepUpMessage, "Проверяем MFA…");
    try {
      const payload = {};
      if (otp) payload.otp = otp;
      if (recovery) payload.recovery_code = recovery;
      const result = await api("/api/v1/admin/auth/step-up", {
        method: "POST", telegram: true, body: JSON.stringify(payload),
      });
      if (state.me) state.me.step_up_until = result.step_up_until;
      dom.stepUpOtp.value = "";
      dom.stepUpRecovery.value = "";
      setMessage(dom.stepUpMessage, "MFA подтверждена", "ok");
      dom.stepConfirm.hidden = false;
      dom.stepUpVerify.hidden = true;
      dom.stepUpExecute.hidden = false;
      dom.stepUpExecute.focus();
    } catch (error) {
      setMessage(dom.stepUpMessage, error.message || "MFA не подтверждена", "error");
      notify("error");
    } finally {
      dom.stepUpVerify.disabled = false;
    }
  }

  async function executePendingSensitive() {
    const pending = state.pendingSensitive;
    if (!pending) return;
    dom.stepUpExecute.disabled = true;
    setMessage(dom.stepUpMessage, "Выполняем подтверждённое действие…");
    try {
      await pending.action();
      state.pendingSensitive = null;
      dom.stepUpDialog.close();
      notify("success");
      toast("Действие выполнено");
      await loadView(state.view);
    } catch (error) {
      setMessage(dom.stepUpMessage, error.message || "Не удалось выполнить действие", "error");
      notify("error");
    } finally {
      dom.stepUpExecute.disabled = false;
    }
  }

  function buildNav() {
    dom.adminNav.replaceChildren();
    for (const [key, label, icon, permission] of NAV) {
      if (!hasPermission(permission)) continue;
      const node = button("", `nav-button${state.view === key ? " active" : ""}`);
      node.dataset.view = key;
      node.append(el("span", "nav-icon", icon), el("span", "", label));
      node.addEventListener("click", () => {
        state.currentUserId = null;
        state.currentTicketId = null;
        setView(key);
        dom.sidebar.classList.remove("open");
      });
      dom.adminNav.appendChild(node);
    }
  }

  function setView(key) {
    if (!NAV.some(([item]) => item === key)) key = "dashboard";
    const config = NAV.find(([item]) => item === key);
    if (config && !hasPermission(config[3])) key = NAV.find(([, , , permission]) => hasPermission(permission))?.[0] || "sessions";
    state.view = key;
    const [kicker, title] = TITLES[key] || ["ADMIN", key];
    dom.viewKicker.textContent = kicker;
    dom.viewTitle.textContent = title;
    buildNav();
    void loadView(key);
  }

  async function loadView(key) {
    loading();
    try {
      if (key === "dashboard") return await renderDashboard();
      if (key === "users") return state.currentUserId ? await renderUserDetail(state.currentUserId) : await renderUsers();
      if (key === "generations") return await renderGenerations();
      if (key === "payments") return await renderPayments();
      if (key === "support") return state.currentTicketId ? await renderSupportDetail(state.currentTicketId) : await renderSupport();
      if (key === "withdrawals") return await renderWithdrawals();
      if (key === "promos") return await renderPromos();
      if (key === "referrals") return await renderReferrals();
      if (key === "security") return await renderSecurity();
      if (key === "admins") return await renderAdmins();
      if (key === "sessions") return await renderSessions();
      dom.adminView.replaceChildren(empty("Раздел не найден."));
    } catch (error) {
      const message = el("div", "empty");
      message.append(el("strong", "", "Не удалось загрузить раздел"), el("p", "", error.message || "Ошибка API"));
      if (error.requestId) message.appendChild(el("small", "mono", `request: ${error.requestId}`));
      dom.adminView.replaceChildren(panel("Ошибка", message));
    }
  }

  async function renderDashboard() {
    const data = await api("/api/v1/admin/dashboard");
    const grid = el("div", "metric-grid");
    grid.append(
      metric("Пользователи", formatNumber(data.users?.total, 0), `${formatNumber(data.users?.active, 0)} активных`),
      metric("Активные генерации", formatNumber(data.generations?.active, 0), `${formatNumber(data.generations?.failed, 0)} failed`),
      metric("Support", formatNumber(data.support?.open, 0), "открытых тикетов"),
      metric("Выводы", formatNumber(data.withdrawals?.pending_or_processing, 0), "pending / processing"),
      metric("Успешные платежи", formatNumber(data.payments?.succeeded, 0), `${formatNumber(data.payments?.rub)} ₽`),
      metric("Продано кредитов", formatNumber(data.payments?.credits), "успешные платежи"),
    );
    dom.adminView.replaceChildren(grid);

    const links = el("div", "card-list");
    [
      ["Пользователи", "Поиск, история, статусы, wallet", "users", "users.read"],
      ["Поддержка", "Очередь обращений и ответы", "support", "support.read"],
      ["Платежи", "Provider status, reconcile, refunds", "payments", "payments.read"],
      ["Security", "Audit, сессии, auth anomalies", "security", ["security.read", "audit.read"]],
    ].forEach(([title, copy, view, permission]) => {
      if (!hasPermission(permission)) return;
      const card = el("div", "list-card");
      card.append(el("div", "list-card-head", ""), el("p", "muted", copy));
      card.querySelector(".list-card-head").append(el("strong", "", title), button("Открыть", "table-action", () => setView(view)));
      links.appendChild(card);
    });
    dom.adminView.appendChild(panel("Быстрые действия", links));
  }

  async function renderUsers(filters = {}) {
    const params = new URLSearchParams({ limit: "50" });
    if (filters.q) params.set("q", filters.q);
    if (filters.is_active !== undefined && filters.is_active !== "") params.set("is_active", filters.is_active);
    const data = await api(`/api/v1/admin/users?${params}`);
    const filter = makeFilter([
      { name: "q", placeholder: "username / имя / Telegram ID", grow: true, value: filters.q || "" },
      { name: "is_active", value: filters.is_active || "", options: [["", "Все"], ["true", "Активные"], ["false", "Отключённые"]] },
    ], renderUsers);
    const cols = [
      ["Пользователь", (row) => { const cell = el("div", "cell-main"); cell.append(el("strong", "", row.first_name || row.username || "Пользователь"), el("small", "", row.username ? `@${row.username}` : String(row.telegram_id))); return cell; }],
      ["Баланс", (row) => `${formatNumber(row.balance_credits)} кр. · ${formatNumber(row.balance_rub)} ₽`],
      ["Статус", (row) => statusBadge(row.is_active ? "active" : "inactive")],
      ["Создан", (row) => formatDate(row.created_at)],
      ["", (row) => actionsCell(button("Открыть", "table-action", () => { state.currentUserId = row.id; void renderUserDetail(row.id); }))],
    ];
    dom.adminView.replaceChildren(panel(`Пользователи · ${formatNumber(data.total, 0)}`, table(cols, data.items || []), filter));
  }

  async function renderUserDetail(userId) {
    loading();
    const [user, history] = await Promise.all([
      api(`/api/v1/admin/users/${encodeURIComponent(userId)}`),
      api(`/api/v1/admin/users/${encodeURIComponent(userId)}/history?limit=100`),
    ]);
    state.currentUserId = userId;
    const back = button("← К списку", "ghost", () => { state.currentUserId = null; void renderUsers(); });
    const controls = el("div", "actions");
    controls.appendChild(back);
    if (hasPermission("users.manage")) {
      controls.appendChild(button(user.is_active ? "Отключить" : "Активировать", "table-action dangerous", () => {
        openForm({
          title: user.is_active ? "Отключить пользователя" : "Активировать пользователя",
          fields: [{ name: "reason", label: "Причина", type: "textarea", maxLength: 500 }],
          submitLabel: "Подтвердить",
          onSubmit: async ({ reason }) => {
            const action = () => api(`/api/v1/admin/users/${userId}/status`, { method: "PATCH", body: JSON.stringify({ is_active: !user.is_active, reason }) });
            await executeOrStepUp("Изменение статуса пользователя", action);
            await renderUserDetail(userId);
          },
        });
      }));
    }
    if (hasPermission("users.wallet.adjust")) {
      controls.appendChild(button("Корректировка баланса", "table-action", () => openForm({
        title: "Корректировка кредитов",
        fields: [
          { name: "amount", label: "Сумма кредитов (+ / -)", type: "number", step: "0.01" },
          { name: "reason", label: "Причина", type: "textarea", maxLength: 500 },
        ],
        submitLabel: "К step-up",
        onSubmit: async ({ amount, reason }) => {
          dom.formDialog.close();
          openStepUp(`Изменить баланс пользователя на ${amount} кредитов`, async () => {
            await api(`/api/v1/admin/users/${userId}/wallet-adjustments`, { method: "POST", body: JSON.stringify({ amount, reason }) });
          });
          return false;
        },
      })));
    }
    if (hasPermission("users.notes")) {
      controls.appendChild(button("Добавить заметку", "table-action", () => openForm({
        title: "Внутренняя заметка",
        fields: [{ name: "body", label: "Заметка", type: "textarea", maxLength: 4000 }],
        onSubmit: async ({ body }) => { await api(`/api/v1/admin/users/${userId}/notes`, { method: "POST", body: JSON.stringify({ body }) }); await renderUserDetail(userId); },
      })));
    }

    const info = el("div", "panel-body");
    info.appendChild(kvRows([
      ["ID", user.id], ["Telegram", user.telegram_id], ["Username", user.username ? `@${user.username}` : "—"],
      ["Имя", [user.first_name, user.last_name].filter(Boolean).join(" ")], ["Статус", user.is_active ? "active" : "inactive"],
      ["Баланс", `${formatNumber(user.balance_credits)} кр. · ${formatNumber(user.balance_rub)} ₽`],
      ["Генерации", user.stats?.generations], ["Платежи", user.stats?.payments], ["Support", user.stats?.support_tickets], ["Admin", user.is_admin ? "да" : "нет"],
    ]));
    const eventList = el("div", "event-list panel-body");
    for (const event of history.items || []) {
      const card = el("div", "event");
      const head = el("div", "event-head");
      head.append(el("strong", "", event.type), el("small", "muted", formatDate(event.at)));
      card.append(head, el("pre", "audit-meta", jsonText(Object.fromEntries(Object.entries(event).filter(([key]) => !["type", "at"].includes(key))))));
      eventList.appendChild(card);
    }
    if (!(history.items || []).length) eventList.appendChild(empty("История пуста."));
    dom.adminView.replaceChildren(controls, panel("Карточка пользователя", info), panel("История действий", eventList));
  }

  async function renderGenerations(filters = {}) {
    const params = new URLSearchParams({ limit: "50" });
    if (filters.status) params.set("status", filters.status);
    if (filters.user_id) params.set("user_id", filters.user_id);
    const data = await api(`/api/v1/admin/generations?${params}`);
    const filter = makeFilter([
      { name: "status", value: filters.status || "", options: [["", "Все статусы"], ["queued", "queued"], ["submitting", "submitting"], ["generating", "generating"], ["succeeded", "succeeded"], ["failed", "failed"], ["retry", "retry"]] },
      { name: "user_id", placeholder: "User UUID", grow: true, value: filters.user_id || "" },
    ], renderGenerations);
    const cols = [
      ["Задача", (row) => { const c = el("div", "cell-main"); c.append(el("strong", "", row.model_id || row.kind), el("small", "mono", row.id), el("small", "", String(row.prompt || "").slice(0, 110))); return c; }],
      ["Статус", (row) => statusBadge(row.status)],
      ["Стоимость", (row) => `${formatNumber(row.cost_credits)} кр.`],
      ["Provider", (row) => { const c = el("div", "cell-main"); c.append(el("span", "", row.provider || "—"), el("small", "mono", row.external_id || "")); return c; }],
      ["Создан", (row) => formatDate(row.created_at)],
      ["", (row) => hasPermission("generations.manage") && row.provider === "kie" && row.external_id ? actionsCell(button("Reconcile", "table-action", async () => { try { await api(`/api/v1/admin/generations/${row.id}/reconcile`, { method: "POST" }); toast("Generation reconciled"); await renderGenerations(filters); } catch (error) { toast(error.message); } })) : ""],
    ];
    dom.adminView.replaceChildren(panel("Генерации", table(cols, data.items || []), filter));
  }

  async function renderPayments(filters = {}) {
    const params = new URLSearchParams({ limit: "50" });
    if (filters.status) params.set("status", filters.status);
    if (filters.provider) params.set("provider", filters.provider);
    if (filters.user_id) params.set("user_id", filters.user_id);
    const data = await api(`/api/v1/admin/payments?${params}`);
    const filter = makeFilter([
      { name: "status", value: filters.status || "", options: [["", "Все статусы"], ["creating", "creating"], ["pending", "pending"], ["succeeded", "succeeded"], ["failed", "failed"], ["canceled", "canceled"], ["refunded", "refunded"]] },
      { name: "provider", value: filters.provider || "", options: [["", "Все провайдеры"], ["cryptobot", "Crypto Pay"], ["tbank", "T-Bank"], ["yookassa", "YooKassa"]] },
      { name: "user_id", placeholder: "User UUID", grow: true, value: filters.user_id || "" },
    ], renderPayments);
    const cols = [
      ["Платёж", (row) => { const c = el("div", "cell-main"); c.append(el("strong", "", `${formatNumber(row.amount)} ${row.currency}`), el("small", "mono", row.id), el("small", "", `${row.provider} · ${formatNumber(row.credits)} кр.`)); return c; }],
      ["Статус", (row) => statusBadge(row.status)],
      ["User", (row) => el("span", "mono", row.user_id)],
      ["Создан", (row) => formatDate(row.created_at)],
      ["", (row) => {
        const cell = actionsCell();
        if (hasPermission("users.wallet.adjust")) {
          cell.appendChild(button("Reconcile", "table-action", () => openStepUp("Reconcile платёж у провайдера", async () => { await api(`/api/v1/admin/payments/${row.id}/reconcile`, { method: "POST" }); })));
          if (row.status === "succeeded") cell.appendChild(button("Refund", "table-action dangerous", () => openForm({
            title: "Запрос возврата",
            fields: [{ name: "amount", label: `Сумма (${row.currency})`, type: "number", step: "0.01" }, { name: "reason", label: "Причина", type: "textarea", maxLength: 250 }],
            submitLabel: "К step-up",
            onSubmit: async ({ amount, reason }) => {
              dom.formDialog.close();
              openStepUp(`Refund ${amount} ${row.currency} по платежу ${row.id}`, async () => {
                await api(`/api/v1/admin/payments/${row.id}/refund`, { method: "POST", body: JSON.stringify({ amount, reason, request_id: crypto.randomUUID() }) });
              });
              return false;
            },
          })));
        }
        return cell;
      }],
    ];
    dom.adminView.replaceChildren(panel("Платежи", table(cols, data.items || []), filter));
  }

  async function renderSupport(filters = {}) {
    const params = new URLSearchParams({ limit: "50" });
    if (filters.status) params.set("status", filters.status);
    const data = await api(`/api/v1/admin/support/tickets?${params}`);
    const filter = makeFilter([{ name: "status", value: filters.status || "", options: [["", "Все"], ["open", "open"], ["in_progress", "in_progress"], ["resolved", "resolved"], ["closed", "closed"]] }], renderSupport);
    const cols = [
      ["Тикет", (row) => { const c = el("div", "cell-main"); c.append(el("strong", "", row.topic), el("small", "mono", row.id), el("small", "", `user ${row.user_id}`)); return c; }],
      ["Статус", (row) => statusBadge(row.status)],
      ["Обновлён", (row) => formatDate(row.updated_at)],
      ["", (row) => actionsCell(button("Открыть", "table-action", () => { state.currentTicketId = row.id; void renderSupportDetail(row.id); }))],
    ];
    dom.adminView.replaceChildren(panel("Очередь поддержки", table(cols, data.items || []), filter));
  }

  async function renderSupportDetail(ticketId) {
    loading();
    const ticket = await api(`/api/v1/admin/support/tickets/${ticketId}`);
    state.currentTicketId = ticketId;
    const controls = actionsCell(button("← К очереди", "ghost", () => { state.currentTicketId = null; void renderSupport(); }));
    if (hasPermission("support.manage") && ticket.status !== "closed") {
      controls.appendChild(button("Ответить", "table-action", () => openForm({
        title: "Ответ пользователю", fields: [{ name: "body", label: "Сообщение", type: "textarea", maxLength: 4000 }],
        onSubmit: async ({ body }) => { await api(`/api/v1/admin/support/tickets/${ticketId}/messages`, { method: "POST", body: JSON.stringify({ body }) }); await renderSupportDetail(ticketId); },
      })));
      controls.appendChild(button("Изменить статус", "table-action", () => openForm({
        title: "Статус обращения",
        fields: [{ name: "status", label: "Статус", type: "select", options: [["open", "open"], ["in_progress", "in_progress"], ["resolved", "resolved"], ["closed", "closed"]], value: ticket.status }],
        onSubmit: async ({ status }) => { await api(`/api/v1/admin/support/tickets/${ticketId}/status`, { method: "PATCH", body: JSON.stringify({ status }) }); await renderSupportDetail(ticketId); },
      })));
    }
    const thread = el("div", "thread panel-body");
    for (const message of ticket.messages || []) {
      const card = el("div", `message${message.is_admin ? " admin" : ""}`);
      const head = el("div", "message-head");
      head.append(el("strong", "", message.is_admin ? "Администратор" : "Пользователь"), el("small", "muted", formatDate(message.created_at)));
      card.append(head, el("p", "", message.body));
      thread.appendChild(card);
    }
    dom.adminView.replaceChildren(controls, panel(`${ticket.topic} · ${ticket.status}`, thread));
  }

  async function renderWithdrawals(filters = {}) {
    const params = new URLSearchParams({ limit: "50" });
    if (filters.status) params.set("status", filters.status);
    const data = await api(`/api/v1/admin/withdrawals?${params}`);
    const filter = makeFilter([{ name: "status", value: filters.status || "", options: [["", "Все"], ["pending", "pending"], ["processing", "processing"], ["paid", "paid"], ["rejected", "rejected"], ["canceled", "canceled"]] }], renderWithdrawals);
    const cols = [
      ["Заявка", (row) => { const c = el("div", "cell-main"); c.append(el("strong", "", `${formatNumber(row.amount)} ₽`), el("small", "mono", row.id), el("small", "", `user ${row.user_id}`)); return c; }],
      ["Статус", (row) => statusBadge(row.status)],
      ["Реквизиты", (row) => typeof row.requisites === "string" ? row.requisites : jsonText(row.requisites)],
      ["Создана", (row) => formatDate(row.created_at)],
      ["", (row) => {
        if (!hasPermission("withdrawals.manage") || ["paid", "rejected", "canceled"].includes(row.status)) return "";
        return actionsCell(button("Сменить статус", "table-action", () => openForm({
          title: "Обработать вывод",
          fields: [
            { name: "status", label: "Новый статус", type: "select", options: row.status === "pending" ? [["processing", "processing"], ["rejected", "rejected"], ["canceled", "canceled"]] : [["paid", "paid"], ["rejected", "rejected"], ["canceled", "canceled"]] },
            { name: "reason", label: "Причина / комментарий", type: "textarea", maxLength: 500 },
          ],
          submitLabel: "К step-up",
          onSubmit: async ({ status, reason }) => {
            dom.formDialog.close();
            openStepUp(`Withdrawal ${row.id}: ${row.status} → ${status}`, async () => {
              await api(`/api/v1/admin/withdrawals/${row.id}/status`, { method: "PATCH", body: JSON.stringify({ status, reason }) });
            });
            return false;
          },
        })));
      }],
    ];
    dom.adminView.replaceChildren(panel("Партнёрские выводы", table(cols, data.items || []), filter));
  }

  async function renderPromos() {
    const data = await api("/api/v1/admin/promocodes?limit=100");
    const actions = hasPermission("promocodes.manage") ? button("Создать", "primary", () => openForm({
      title: "Новый промокод",
      fields: [
        { name: "code", label: "Код", maxLength: 64 },
        { name: "reward_credits", label: "Кредиты", type: "number", step: "0.01" },
        { name: "max_uses", label: "Макс. активаций", type: "number", required: false },
        { name: "expires_at", label: "Истекает (ISO, optional)", required: false, placeholder: "2026-12-31T23:59:00Z" },
      ],
      onSubmit: async (values) => {
        const payload = { code: values.code, reward_credits: values.reward_credits };
        if (values.max_uses) payload.max_uses = Number(values.max_uses);
        if (values.expires_at) payload.expires_at = values.expires_at;
        await api("/api/v1/admin/promocodes", { method: "POST", body: JSON.stringify(payload) });
        await renderPromos();
      },
    })) : null;
    const cols = [
      ["Код", (row) => el("strong", "mono", row.code)],
      ["Награда", (row) => `${formatNumber(row.reward_credits)} кр.`],
      ["Использовано", (row) => `${formatNumber(row.uses_count, 0)} / ${row.max_uses ?? "∞"}`],
      ["Статус", (row) => statusBadge(row.is_active ? "active" : "inactive")],
      ["Истекает", (row) => formatDate(row.expires_at)],
      ["", (row) => hasPermission("promocodes.manage") ? actionsCell(button(row.is_active ? "Отключить" : "Включить", "table-action", async () => { try { await api(`/api/v1/admin/promocodes/${row.id}`, { method: "PATCH", body: JSON.stringify({ is_active: !row.is_active }) }); await renderPromos(); } catch (error) { toast(error.message); } })) : ""],
    ];
    dom.adminView.replaceChildren(panel("Промокоды", table(cols, data.items || []), actions));
  }

  async function renderReferrals(filters = {}) {
    const params = new URLSearchParams({ limit: "100" });
    if (filters.partner_user_id) params.set("partner_user_id", filters.partner_user_id);
    if (filters.status) params.set("status", filters.status);
    const data = await api(`/api/v1/admin/referrals/rewards?${params}`);
    const filter = makeFilter([
      { name: "partner_user_id", placeholder: "Partner user UUID", grow: true, value: filters.partner_user_id || "" },
      { name: "status", value: filters.status || "", options: [["", "Все"], ["available", "available"], ["pending", "pending"], ["reversed", "reversed"]] },
    ], renderReferrals);
    const cols = [
      ["Партнёр", (row) => el("span", "mono", row.partner_user_id)],
      ["Источник", (row) => el("span", "mono", row.source_user_id)],
      ["Линия", (row) => String(row.level)],
      ["Начисление", (row) => `${formatNumber(row.amount)} · ${formatNumber(row.percent)}%`],
      ["Статус", (row) => statusBadge(row.status)],
      ["Создано", (row) => formatDate(row.created_at)],
    ];
    dom.adminView.replaceChildren(panel("Реферальные начисления", table(cols, data.items || []), filter));
  }

  async function renderSecurity() {
    const requests = [];
    if (hasPermission("security.read")) requests.push(api("/api/v1/admin/security/overview")); else requests.push(Promise.resolve(null));
    if (hasPermission("audit.read")) requests.push(api("/api/v1/admin/audit?limit=100")); else requests.push(Promise.resolve(null));
    if (hasPermission("security.read")) requests.push(api("/api/v1/admin/security/sessions?active_only=true&limit=100")); else requests.push(Promise.resolve(null));
    const [overview, audit, sessions] = await Promise.all(requests);
    dom.adminView.replaceChildren();
    if (overview) {
      const grid = el("div", "security-grid");
      grid.append(
        metric("Активные admin sessions", overview.active_sessions),
        metric("Failed auth · 24h", overview.failed_or_denied_auth_events_24h),
        metric("Locked admins", overview.locked_admins),
        metric("Без MFA", overview.active_admins_without_mfa),
      );
      dom.adminView.appendChild(grid);
    }
    if (sessions) {
      const cols = [
        ["Session", (row) => el("span", "mono", row.id)], ["Admin", (row) => el("span", "mono", row.admin_id)],
        ["Последняя активность", (row) => formatDate(row.last_seen_at)], ["MFA", (row) => statusBadge(row.mfa_verified ? "active" : "inactive")],
        ["Step-up", (row) => formatDate(row.step_up_until)],
        ["", (row) => hasPermission("sessions.manage") ? actionsCell(button("Revoke", "table-action dangerous", async () => { try { await api(`/api/v1/admin/security/sessions/${row.id}`, { method: "DELETE" }); await renderSecurity(); } catch (error) { toast(error.message); } })) : ""],
      ];
      dom.adminView.appendChild(panel("Активные сессии", table(cols, sessions.items || [])));
    }
    if (audit) {
      const cols = [
        ["Событие", (row) => { const c = el("div", "cell-main"); c.append(el("strong", "", row.action), el("small", "mono", row.id)); return c; }],
        ["Outcome", (row) => statusBadge(row.outcome)], ["Resource", (row) => `${row.resource_type || "—"} ${row.resource_id || ""}`],
        ["Admin", (row) => el("span", "mono", row.admin_id || "system")], ["Integrity", (row) => statusBadge(row.integrity_valid ? "success" : "failed")],
        ["Время", (row) => formatDate(row.created_at)], ["Metadata", (row) => el("pre", "audit-meta", jsonText(row.metadata))],
      ];
      dom.adminView.appendChild(panel("Audit log", table(cols, audit.items || [])));
    }
  }

  async function renderAdmins() {
    const [admins, roles] = await Promise.all([api("/api/v1/admin/admins"), api("/api/v1/admin/roles")]);
    const actions = hasPermission("admins.manage") && state.me?.role === "owner" ? button("Добавить администратора", "primary", () => openForm({
      title: "Новый администратор",
      fields: [
        { name: "telegram_id", label: "Telegram ID", type: "number" },
        { name: "role", label: "Роль", type: "select", options: Object.keys(roles.roles || {}).map((role) => [role, role]) },
      ],
      submitLabel: "К step-up",
      onSubmit: async ({ telegram_id, role }) => {
        dom.formDialog.close();
        openStepUp(`Создать администратора ${telegram_id} с ролью ${role}`, async () => {
          await api("/api/v1/admin/admins", { method: "POST", body: JSON.stringify({ telegram_id: Number(telegram_id), role, permission_overrides: {} }) });
        });
        return false;
      },
    })) : null;
    const cols = [
      ["Администратор", (row) => { const c = el("div", "cell-main"); c.append(el("strong", "", row.username ? `@${row.username}` : String(row.telegram_id)), el("small", "mono", row.id)); return c; }],
      ["Роль", (row) => statusBadge(row.role)], ["MFA", (row) => statusBadge(row.mfa_enabled ? "active" : "inactive")],
      ["Статус", (row) => statusBadge(row.is_active ? "active" : "inactive")], ["Последний вход", (row) => formatDate(row.last_login_at)],
      ["", (row) => hasPermission("admins.manage") && state.me?.role === "owner" ? actionsCell(button("Изменить", "table-action", () => openForm({
        title: "Изменить администратора",
        fields: [
          { name: "role", label: "Роль", type: "select", options: Object.keys(roles.roles || {}).map((role) => [role, role]), value: row.role },
          { name: "is_active", label: "Активен", type: "checkbox", value: row.is_active },
          { name: "reason", label: "Причина", type: "textarea", maxLength: 500 },
        ],
        submitLabel: "К step-up",
        onSubmit: async ({ role, is_active, reason }) => {
          dom.formDialog.close();
          openStepUp(`Изменить admin ${row.id}: role=${role}, active=${is_active}`, async () => {
            await api(`/api/v1/admin/admins/${row.id}`, { method: "PATCH", body: JSON.stringify({ role, is_active, reason, permission_overrides: row.permission_overrides || {} }) });
          });
          return false;
        },
      }))) : ""],
    ];
    dom.adminView.replaceChildren(panel("Администраторы", table(cols, admins.items || []), actions));
  }

  async function renderSessions() {
    const data = await api("/api/v1/admin/auth/sessions");
    const cols = [
      ["Session", (row) => { const c = el("div", "cell-main"); c.append(el("span", "mono", row.id), row.current ? statusBadge("current") : el("span")); return c; }],
      ["Создана", (row) => formatDate(row.created_at)], ["Последняя активность", (row) => formatDate(row.last_seen_at)],
      ["Истекает", (row) => formatDate(row.expires_at)], ["MFA", (row) => statusBadge(row.mfa_verified ? "active" : "inactive")],
      ["Step-up", (row) => formatDate(row.step_up_until)],
      ["", (row) => !row.revoked ? actionsCell(button(row.current ? "Завершить текущую" : "Отозвать", "table-action dangerous", async () => { try { await api(`/api/v1/admin/auth/sessions/${row.id}`, { method: "DELETE" }); if (row.current) clearSession("Сессия завершена"); else await renderSessions(); } catch (error) { toast(error.message); } })) : ""],
    ];
    dom.adminView.replaceChildren(panel("Мои admin-сессии", table(cols, data.sessions || [])));
  }

  async function login(event = null) {
    event?.preventDefault?.();
    if (!tg?.initData) {
      setMessage(dom.loginMessage, "Откройте админ-панель из Telegram. Signed initData отсутствует.", "error");
      return;
    }
    dom.loginButton.disabled = true;
    setMessage(dom.loginMessage, "Проверяем доступ…");
    const body = {};
    const otp = dom.loginOtp.value.trim();
    const recovery = dom.loginRecovery.value.trim();
    if (otp) body.otp = otp;
    if (recovery) body.recovery_code = recovery;
    try {
      const result = await api("/api/v1/admin/auth/login", { method: "POST", telegram: true, auth: false, body: JSON.stringify(body) });
      state.token = result.token;
      dom.loginOtp.value = "";
      dom.loginRecovery.value = "";
      if (result.mfa_setup_required) {
        await beginMfaSetup();
        return;
      }
      if (!result.mfa_verified) throw new Error("MFA verification required");
      await enterConsole();
    } catch (error) {
      setMessage(dom.loginMessage, error.status === 401 ? "Неверный OTP / recovery code" : (error.message || "Вход не выполнен"), "error");
      state.token = null;
      notify("error");
    } finally {
      dom.loginButton.disabled = false;
    }
  }

  async function beginMfaSetup() {
    const setup = await api("/api/v1/admin/auth/mfa/setup", { method: "POST", telegram: true });
    dom.mfaSecret.textContent = setup.secret;
    dom.mfaUri.textContent = setup.otpauth_uri;
    dom.mfaConfirmOtp.value = "";
    setMessage(dom.mfaSetupMessage);
    dom.mfaSetupDialog.showModal();
    requestAnimationFrame(() => dom.mfaConfirmOtp.focus());
  }

  async function confirmMfa() {
    const code = dom.mfaConfirmOtp.value.trim();
    if (!code) return setMessage(dom.mfaSetupMessage, "Введите код", "error");
    dom.mfaConfirmButton.disabled = true;
    try {
      const result = await api("/api/v1/admin/auth/mfa/confirm", { method: "POST", body: JSON.stringify({ code }) });
      dom.mfaSetupDialog.close();
      dom.recoveryCodes.replaceChildren();
      for (const recovery of result.recovery_codes || []) dom.recoveryCodes.appendChild(el("code", "", recovery));
      dom.recoveryDialog.showModal();
      await loadMe();
    } catch (error) {
      setMessage(dom.mfaSetupMessage, error.message || "Не удалось подтвердить MFA", "error");
    } finally {
      dom.mfaConfirmButton.disabled = false;
    }
  }

  async function loadMe() {
    state.me = await api("/api/v1/admin/auth/me");
    state.permissions = new Set(state.me.permissions || []);
    dom.adminIdentity.replaceChildren(
      el("strong", "", state.me.username ? `@${state.me.username}` : String(state.me.telegram_id)),
      el("small", "", state.me.role),
    );
  }

  async function enterConsole() {
    await loadMe();
    dom.authView.hidden = true;
    dom.adminShell.hidden = false;
    const preferred = hasPermission("dashboard.read") ? "dashboard" : NAV.find(([, , , permission]) => hasPermission(permission))?.[0] || "sessions";
    setView(preferred);
  }

  async function logout() {
    try { if (state.token) await api("/api/v1/admin/auth/logout", { method: "POST" }); } catch (_error) { /* local clear still wins */ }
    clearSession("Вы вышли из админ-панели.");
  }

  function clearSession(message = "") {
    state.token = null;
    state.me = null;
    state.permissions = new Set();
    state.pendingSensitive = null;
    state.currentUserId = null;
    state.currentTicketId = null;
    dom.adminShell.hidden = true;
    dom.authView.hidden = false;
    dom.sidebar.classList.remove("open");
    if (dom.stepUpDialog.open) dom.stepUpDialog.close();
    if (dom.formDialog.open) dom.formDialog.close();
    setMessage(dom.loginMessage, message, message ? "ok" : "");
  }

  dom.loginForm.addEventListener("submit", login);
  dom.bootstrapButton.addEventListener("click", () => { dom.bootstrapPanel.hidden = !dom.bootstrapPanel.hidden; });
  dom.bootstrapConfirm.addEventListener("click", () => { setMessage(dom.loginMessage, "Bootstrap owner выполняется через обычный login для разрешённого Telegram ID."); void login(); });
  dom.logoutButton.addEventListener("click", logout);
  dom.refreshButton.addEventListener("click", () => loadView(state.view));
  dom.sidebarToggle.addEventListener("click", () => dom.sidebar.classList.toggle("open"));
  dom.mfaConfirmButton.addEventListener("click", confirmMfa);
  dom.recoveryDone.addEventListener("click", async () => { dom.recoveryCodes.replaceChildren(); dom.recoveryDialog.close(); await enterConsole(); });
  dom.stepUpVerify.addEventListener("click", verifyStepUp);
  dom.stepUpExecute.addEventListener("click", executePendingSensitive);
  dom.stepUpCancel.addEventListener("click", () => { state.pendingSensitive = null; dom.stepUpDialog.close(); });
  dom.formCancel.addEventListener("click", () => dom.formDialog.close());

  tg?.ready?.();
  tg?.expand?.();
  if (!tg?.initData) {
    setMessage(dom.loginMessage, "Для админ-доступа нужен запуск из Telegram Mini App.", "error");
  }
})();
