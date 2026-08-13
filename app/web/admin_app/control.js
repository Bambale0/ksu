(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const state = {
    token: null,
    me: null,
    view: "overview",
    stepResolve: null,
    stepReject: null,
  };

  const VIEWS = [
    ["overview", "Обзор", "CONTROL"],
    ["users", "Пользователи", "USERS"],
    ["payments", "Платежи", "FINANCE"],
    ["operations", "Операции", "OPERATIONS"],
    ["support", "Поддержка", "SUPPORT"],
    ["pricing", "Тарифы", "PRICING"],
    ["cms", "CMS", "CONTENT"],
    ["campaigns", "Рассылки", "NOTIFICATIONS"],
    ["promos", "Промо", "PROMOS"],
    ["content", "Модерация", "MODERATION"],
    ["runtime", "Runtime", "RUNTIME"],
    ["partners", "Партнёры", "PARTNERS"],
    ["exports", "Экспорт", "EXPORT"],
  ];

  const dom = {};
  for (const id of [
    "controlAuth", "controlLogin", "controlOtp", "controlRecovery", "controlLoginMessage",
    "controlShell", "controlIdentity", "controlNav", "controlLogout", "controlKicker",
    "controlTitle", "controlSessionStatus", "controlRefresh", "controlView", "controlStepDialog",
    "controlStepDescription", "controlStepOtp", "controlStepRecovery", "controlStepMessage",
    "controlStepCancel", "controlStepVerify", "controlFormDialog", "controlForm", "controlFormKicker",
    "controlFormTitle", "controlFormFields", "controlFormMessage", "controlFormCancel",
    "controlFormSubmit", "controlToast",
  ]) dom[id] = document.getElementById(id);

  function node(tag, className = "", text = "") {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== "") item.textContent = String(text);
    return item;
  }

  function button(text, className = "table-action", handler = null) {
    const item = node("button", className, text);
    item.type = "button";
    if (handler) item.addEventListener("click", handler);
    return item;
  }

  function setMessage(target, text = "", kind = "") {
    target.textContent = text;
    target.className = `form-message${kind ? ` ${kind}` : ""}`;
  }

  function toast(text, kind = "") {
    dom.controlToast.textContent = text;
    dom.controlToast.className = `toast${kind ? ` ${kind}` : ""}`;
    dom.controlToast.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { dom.controlToast.hidden = true; }, 3600);
  }

  function json(value) {
    return JSON.stringify(value, null, 2);
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("ru-RU");
  }

  function randomId(prefix = "web") {
    const value = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    return `${prefix}:${value}`;
  }

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Accept", options.accept || "application/json");
    headers.set("X-Request-Id", options.requestId || randomId("control-request"));
    if (options.auth !== false) {
      if (!state.token) throw new Error("Admin session is not authenticated");
      headers.set("Authorization", `Bearer ${state.token}`);
    }
    if (options.telegram && tg?.initData) headers.set("X-Telegram-Init-Data", tg.initData);
    if (options.body != null && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(path, {
      method: options.method || "GET",
      headers,
      body: options.body,
      cache: "no-store",
      credentials: "same-origin",
    });
    const requestId = response.headers.get("X-Request-Id") || headers.get("X-Request-Id");
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json().catch(() => ({}))
      : await response.text().catch(() => "");
    if (!response.ok) {
      const error = new Error(
        (payload && typeof payload === "object" && (payload.detail || payload.message))
          || (typeof payload === "string" && payload)
          || `HTTP ${response.status}`,
      );
      error.status = response.status;
      error.requestId = requestId;
      throw error;
    }
    return payload;
  }

  async function download(path, filenameFallback) {
    const headers = new Headers({
      Accept: "*/*",
      Authorization: `Bearer ${state.token}`,
      "X-Request-Id": randomId("control-export"),
    });
    const response = await fetch(path, { headers, cache: "no-store", credentials: "same-origin" });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/i);
    const filename = match?.[1] || filenameFallback;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function stepUp(label) {
    if (!tg?.initData) throw new Error("Fresh Telegram initData is required for MFA step-up");
    if (state.stepReject) state.stepReject(new Error("Previous step-up was replaced"));
    dom.controlStepDescription.textContent = label;
    dom.controlStepOtp.value = "";
    dom.controlStepRecovery.value = "";
    setMessage(dom.controlStepMessage);
    dom.controlStepDialog.showModal();
    requestAnimationFrame(() => dom.controlStepOtp.focus());
    return new Promise((resolve, reject) => {
      state.stepResolve = resolve;
      state.stepReject = reject;
    });
  }

  async function verifyStepUp() {
    const otp = dom.controlStepOtp.value.trim();
    const recovery = dom.controlStepRecovery.value.trim();
    if (!otp && !recovery) {
      setMessage(dom.controlStepMessage, "Введите OTP или recovery code", "error");
      return;
    }
    dom.controlStepVerify.disabled = true;
    try {
      const payload = {};
      if (otp) payload.otp = otp;
      if (recovery) payload.recovery_code = recovery;
      const result = await api("/api/v1/admin/auth/step-up", {
        method: "POST",
        telegram: true,
        body: JSON.stringify(payload),
      });
      if (state.me) state.me.step_up_until = result.step_up_until;
      dom.controlStepDialog.close();
      const resolve = state.stepResolve;
      state.stepResolve = null;
      state.stepReject = null;
      resolve?.(result);
    } catch (error) {
      setMessage(dom.controlStepMessage, error.message || "MFA step-up failed", "error");
    } finally {
      dom.controlStepVerify.disabled = false;
    }
  }

  function cancelStepUp() {
    dom.controlStepDialog.close();
    const reject = state.stepReject;
    state.stepResolve = null;
    state.stepReject = null;
    reject?.(new Error("Step-up cancelled"));
  }

  async function mutate(path, options = {}) {
    const label = options.label || "Подтвердить административное действие?";
    if (options.confirm !== false && !window.confirm(label)) return null;
    const requestId = randomId("control-command");
    const idempotencyKey = randomId("control-idem");
    const execute = () => api(path, {
      method: options.method || "POST",
      body: options.body == null ? undefined : JSON.stringify(options.body),
      requestId,
      headers: {
        "Idempotency-Key": idempotencyKey,
        "X-Admin-Confirm": options.confirm === false ? "false" : "confirmed",
      },
    });
    if (options.sensitive) {
      await stepUp(label);
    }
    try {
      return await execute();
    } catch (error) {
      if (error.status === 403 && /step-up/i.test(error.message || "")) {
        await stepUp(label);
        return await execute();
      }
      throw error;
    }
  }

  function card(title, content = null, actions = null, className = "") {
    const wrapper = node("section", `control-card${className ? ` ${className}` : ""}`);
    wrapper.appendChild(node("h2", "", title));
    if (content) wrapper.appendChild(content);
    if (actions) wrapper.appendChild(actions);
    return wrapper;
  }

  function pre(value) {
    return node("pre", "control-json", typeof value === "string" ? value : json(value));
  }

  function actions(...items) {
    const row = node("div", "control-actions");
    for (const item of items.filter(Boolean)) row.appendChild(item);
    return row;
  }

  function field(labelText, input) {
    const label = node("label", "field");
    label.append(node("span", "", labelText), input);
    return label;
  }

  function input(type = "text", value = "", placeholder = "") {
    const item = document.createElement("input");
    item.type = type;
    item.value = value;
    if (placeholder) item.placeholder = placeholder;
    return item;
  }

  function textarea(value = "", placeholder = "") {
    const item = document.createElement("textarea");
    item.value = value;
    if (placeholder) item.placeholder = placeholder;
    return item;
  }

  function select(options, value = "") {
    const item = document.createElement("select");
    for (const [key, label] of options) {
      const option = document.createElement("option");
      option.value = key;
      option.textContent = label;
      item.appendChild(option);
    }
    item.value = value;
    return item;
  }

  function table(headers, rows, renderRow) {
    const wrap = node("div", "control-table-wrap");
    const tableNode = node("table", "control-table");
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    for (const header of headers) headRow.appendChild(node("th", "", header));
    head.appendChild(headRow);
    tableNode.appendChild(head);
    const body = document.createElement("tbody");
    for (const row of rows) {
      const tr = document.createElement("tr");
      const cells = renderRow(row);
      for (const value of cells) {
        const td = document.createElement("td");
        if (value instanceof Node) td.appendChild(value); else td.textContent = value == null ? "—" : String(value);
        tr.appendChild(td);
      }
      body.appendChild(tr);
    }
    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = headers.length;
      td.textContent = "Нет данных";
      tr.appendChild(td);
      body.appendChild(tr);
    }
    tableNode.appendChild(body);
    wrap.appendChild(tableNode);
    return wrap;
  }

  function openForm(config) {
    dom.controlFormKicker.textContent = config.kicker || "ACTION";
    dom.controlFormTitle.textContent = config.title;
    dom.controlFormFields.replaceChildren();
    const controls = {};
    for (const spec of config.fields || []) {
      let control;
      if (spec.type === "textarea") control = textarea(spec.value || "", spec.placeholder || "");
      else if (spec.type === "select") control = select(spec.options || [], spec.value || "");
      else control = input(spec.type || "text", spec.value ?? "", spec.placeholder || "");
      control.name = spec.name;
      if (spec.required !== false) control.required = true;
      if (spec.maxLength) control.maxLength = spec.maxLength;
      if (spec.step) control.step = spec.step;
      controls[spec.name] = control;
      dom.controlFormFields.appendChild(field(spec.label, control));
    }
    setMessage(dom.controlFormMessage);
    dom.controlFormSubmit.textContent = config.submitLabel || "Выполнить";
    dom.controlForm.onsubmit = async (event) => {
      event.preventDefault();
      dom.controlFormSubmit.disabled = true;
      const values = {};
      for (const [key, control] of Object.entries(controls)) values[key] = control.value;
      try {
        const result = await config.onSubmit(values);
        if (result !== false) dom.controlFormDialog.close();
      } catch (error) {
        setMessage(dom.controlFormMessage, error.message || "Ошибка", "error");
      } finally {
        dom.controlFormSubmit.disabled = false;
      }
    };
    dom.controlFormDialog.showModal();
    requestAnimationFrame(() => Object.values(controls)[0]?.focus());
  }

  function loading() {
    dom.controlView.replaceChildren(card("Загрузка", node("p", "muted", "Получаем актуальные данные…")));
  }

  function errorView(error) {
    const content = node("div");
    content.appendChild(node("p", "", error.message || "Не удалось загрузить данные"));
    if (error.requestId) content.appendChild(node("small", "mono", `request: ${error.requestId}`));
    dom.controlView.replaceChildren(card("Ошибка", content, null, "control-danger"));
  }

  function buildNav() {
    dom.controlNav.replaceChildren();
    for (const [key, title] of VIEWS) {
      const item = button(title, `nav-button${state.view === key ? " active" : ""}`, () => setView(key));
      dom.controlNav.appendChild(item);
    }
  }

  function setView(key) {
    const config = VIEWS.find(([value]) => value === key) || VIEWS[0];
    state.view = config[0];
    dom.controlKicker.textContent = config[2];
    dom.controlTitle.textContent = config[1];
    buildNav();
    void loadView();
  }

  async function loadView() {
    loading();
    try {
      if (state.view === "overview") return await renderOverview();
      if (state.view === "users") return await renderUsers();
      if (state.view === "payments") return await renderPayments();
      if (state.view === "operations") return await renderOperations();
      if (state.view === "support") return await renderSupport();
      if (state.view === "pricing") return await renderPricing();
      if (state.view === "cms") return await renderCms();
      if (state.view === "campaigns") return await renderCampaigns();
      if (state.view === "promos") return await renderPromos();
      if (state.view === "content") return await renderContent();
      if (state.view === "runtime") return await renderRuntime();
      if (state.view === "partners") return await renderPartners();
      if (state.view === "exports") return await renderExports();
    } catch (error) {
      errorView(error);
    }
  }

  async function renderOverview() {
    const data = await api("/api/v1/admin/dashboard");
    const grid = node("div", "control-grid");
    const metrics = [
      ["Пользователи", `${data.users?.active ?? 0} / ${data.users?.total ?? 0}`],
      ["Генерации", `${data.generations?.active ?? 0} active · ${data.generations?.failed ?? 0} failed`],
      ["Support", `${data.support?.open ?? 0} open`],
      ["Withdrawals", `${data.withdrawals?.pending_or_processing ?? 0} pending/processing`],
      ["Payments", `${data.payments?.succeeded ?? 0} succeeded`],
      ["Credits sold", String(data.payments?.credits ?? 0)],
    ];
    for (const [title, value] of metrics) grid.appendChild(card(title, node("strong", "metric-value", value)));
    dom.controlView.replaceChildren(grid);
    dom.controlView.appendChild(card(
      "Архитектура",
      node("p", "muted", "UI не содержит privileged business logic: все команды идут через shared services, policy, audit/idempotency и durable workers."),
    ));
  }

  async function renderUsers(query = "") {
    const params = new URLSearchParams({ limit: "50" });
    if (query) params.set("q", query);
    const data = await api(`/api/v1/admin/control/users?${params}`);
    const search = input("search", query, "Telegram ID / UUID / username / name");
    const searchButton = button("Найти", "primary", () => void renderUsers(search.value.trim()));
    const filter = node("div", "control-form-inline");
    filter.append(field("Поиск", search), searchButton);
    const userTable = table(
      ["User", "Telegram", "Balance", "Status", "Actions"],
      data.items || [],
      (row) => {
        const actionRow = actions(
          button(row.is_active ? "Block" : "Unblock", "table-action dangerous", () => {
            openForm({
              title: row.is_active ? "Block user" : "Unblock user",
              fields: [{ name: "reason", label: "Причина", type: "textarea", maxLength: 500 }],
              onSubmit: async ({ reason }) => {
                await mutate(`/api/v1/admin/control/users/${row.id}/${row.is_active ? "block" : "unblock"}`, {
                  body: { reason },
                  label: `${row.is_active ? "Заблокировать" : "Разблокировать"} пользователя ${row.id}?`,
                });
                toast("Статус пользователя обновлён", "ok");
                await renderUsers(query);
              },
            });
          }),
          button("Balance", "table-action", () => {
            openForm({
              title: "Balance adjustment",
              fields: [
                { name: "amount", label: "Credits (+/-)", type: "number", step: "0.01" },
                { name: "reason", label: "Причина", type: "textarea", maxLength: 500 },
              ],
              onSubmit: async ({ amount, reason }) => {
                await mutate(`/api/v1/admin/control/users/${row.id}/balance`, {
                  body: { amount, reason },
                  sensitive: true,
                  label: `Изменить баланс ${row.id} на ${amount} credits?`,
                });
                toast("Баланс обновлён", "ok");
                await renderUsers(query);
              },
            });
          }),
        );
        return [row.username ? `@${row.username}\n${row.id}` : row.id, row.telegram_id, row.balance_credits, row.is_active ? "active" : "blocked", actionRow];
      },
    );
    dom.controlView.replaceChildren(card(`Пользователи · ${data.total ?? 0}`, userTable, filter));
  }

  async function renderPayments() {
    const data = await api("/api/v1/admin/control/payments?limit=100");
    const paymentTable = table(
      ["Payment", "Provider", "Amount", "Credits", "Status", "Actions"],
      data.items || [],
      (row) => [
        row.id,
        row.provider,
        `${row.amount} ${row.currency}`,
        row.credits,
        row.status,
        actions(
          button("Recheck", "table-action", async () => {
            try {
              await mutate(`/api/v1/admin/control/payments/${row.id}/recheck`, { confirm: false });
              toast("Recheck completed", "ok");
              await renderPayments();
            } catch (error) { toast(error.message, "error"); }
          }),
          button("Reprocess", "table-action dangerous", async () => {
            try {
              await mutate(`/api/v1/admin/control/payments/${row.id}/reprocess`, {
                sensitive: true,
                label: `Reprocess payment ${row.id}?`,
              });
              toast("Reprocess completed", "ok");
              await renderPayments();
            } catch (error) { toast(error.message, "error"); }
          }),
        ),
      ],
    );
    dom.controlView.replaceChildren(card(`Платежи · ${data.total ?? 0}`, paymentTable));
  }

  async function renderOperations() {
    const data = await api("/api/v1/admin/control/operations?limit=100");
    const operationTable = table(
      ["Operation", "Model", "Status", "Cost", "Created", "Actions"],
      data.items || [],
      (row) => [
        row.id,
        row.parameters?._model_id || row.provider || "—",
        row.status,
        row.cost_credits,
        formatDate(row.created_at),
        actions(
          button("Preview", "table-action", async () => {
            try {
              const detail = await api(`/api/v1/admin/control/operations/${row.id}`);
              openForm({
                title: `Operation ${row.id}`,
                fields: [{ name: "preview", label: "Redacted detail", type: "textarea", value: json(detail), required: false }],
                submitLabel: "Закрыть",
                onSubmit: async () => true,
              });
            } catch (error) { toast(error.message, "error"); }
          }),
          button("Replay", "table-action", async () => {
            try {
              await mutate(`/api/v1/admin/control/operations/${row.id}/replay`, {
                sensitive: true,
                label: `Replay operation ${row.id} without double charge?`,
              });
              toast("Child operation queued", "ok");
              await renderOperations();
            } catch (error) { toast(error.message, "error"); }
          }),
          button("Refund", "table-action dangerous", () => openForm({
            title: `Refund ${row.id}`,
            fields: [{ name: "reason", label: "Причина", type: "textarea", maxLength: 500 }],
            onSubmit: async ({ reason }) => {
              await mutate(`/api/v1/admin/control/operations/${row.id}/refund`, {
                body: { reason },
                sensitive: true,
                label: `Refund operation ${row.id}?`,
              });
              toast("Refund command completed", "ok");
              await renderOperations();
            },
          })),
        ),
      ],
    );
    dom.controlView.replaceChildren(card("Generation operations", operationTable));
  }

  async function renderSupport() {
    const data = await api("/api/v1/admin/control/tickets?limit=100");
    const ticketTable = table(
      ["Ticket", "Topic", "Status", "Priority", "Assigned", "Actions"],
      data.items || [],
      (row) => [
        row.id,
        row.topic,
        row.status,
        row.priority,
        row.assigned_admin_id || "—",
        actions(button("Open", "table-action", () => void renderTicket(row.id))),
      ],
    );
    dom.controlView.replaceChildren(card("Support tickets", ticketTable));
  }

  async function renderTicket(ticketId) {
    loading();
    try {
      const ticket = await api(`/api/v1/admin/control/tickets/${ticketId}`);
      const messageList = node("div", "card-list");
      for (const message of ticket.messages || []) {
        const item = node("article", "list-card");
        item.append(
          node("strong", "", message.is_admin ? "Admin" : "User"),
          node("p", "", message.body),
          node("small", "muted", formatDate(message.created_at)),
        );
        messageList.appendChild(item);
      }
      const controls = actions(
        button("Assign", "table-action", () => openForm({
          title: "Assign ticket",
          fields: [{ name: "assigned_admin_id", label: "Admin UUID (empty = unassign)", required: false }],
          onSubmit: async ({ assigned_admin_id }) => {
            await mutate(`/api/v1/admin/control/tickets/${ticketId}/assign`, {
              body: { assigned_admin_id: assigned_admin_id || null },
              confirm: false,
            });
            await renderTicket(ticketId);
          },
        })),
        button("Update", "table-action", () => openForm({
          title: "Update ticket",
          fields: [
            { name: "status", label: "Status", type: "select", value: ticket.status, options: [["open", "open"], ["in_progress", "in_progress"], ["resolved", "resolved"], ["closed", "closed"]] },
            { name: "priority", label: "Priority", type: "select", value: ticket.priority, options: [["low", "low"], ["normal", "normal"], ["high", "high"], ["urgent", "urgent"]] },
          ],
          onSubmit: async ({ status, priority }) => {
            await mutate(`/api/v1/admin/control/tickets/${ticketId}/update`, {
              body: { status, priority },
              confirm: false,
            });
            await renderTicket(ticketId);
          },
        })),
        button("Reply", "table-action", () => openForm({
          title: "Queue support reply",
          fields: [{ name: "body", label: "Ответ", type: "textarea", maxLength: 4000 }],
          onSubmit: async ({ body }) => {
            await mutate(`/api/v1/admin/control/tickets/${ticketId}/reply`, {
              body: { body },
              label: `Поставить ответ по ticket ${ticketId} в durable outbox?`,
            });
            toast("Ответ поставлен в durable outbox", "ok");
            await renderTicket(ticketId);
          },
        })),
        button("← Tickets", "ghost", () => void renderSupport()),
      );
      dom.controlView.replaceChildren(
        card(`Ticket ${ticketId}`, pre({
          user_id: ticket.user_id,
          topic: ticket.topic,
          status: ticket.status,
          priority: ticket.priority,
          assigned_admin_id: ticket.assigned_admin_id,
        }), controls),
        card("Messages", messageList),
      );
    } catch (error) { errorView(error); }
  }

  async function renderPricing() {
    const data = await api("/api/v1/admin/tariffs");
    const editor = textarea(data.current?.payload ? json(data.current.payload) : "{\n  \"packages\": {}\n}");
    editor.className = "control-json";
    editor.rows = 18;
    const publish = button("Publish new version", "primary", async () => {
      try {
        const payload = JSON.parse(editor.value);
        await mutate("/api/v1/admin/tariffs/publish", {
          body: { payload },
          sensitive: true,
          label: "Опубликовать новую versioned tariff конфигурацию?",
        });
        toast("Tariff published", "ok");
        await renderPricing();
      } catch (error) { toast(error.message, "error"); }
    });
    const content = node("div", "stack");
    content.append(
      node("p", "muted", data.current ? `Published v${data.current.version}` : "Published version отсутствует"),
      editor,
    );
    dom.controlView.replaceChildren(card("Versioned tariffs", content, actions(publish)));
  }

  async function renderCms() {
    const data = await api("/api/v1/admin/cms/documents");
    const createButton = button("New version", "primary", () => openForm({
      title: "Save CMS document version",
      fields: [
        { name: "slug", label: "Slug" },
        { name: "title", label: "Title" },
        { name: "body", label: "Body", type: "textarea", maxLength: 500000 },
      ],
      onSubmit: async ({ slug, title, body }) => {
        await mutate("/api/v1/admin/cms/documents", {
          body: { slug, title, body },
          confirm: false,
        });
        toast("Draft version saved", "ok");
        await renderCms();
      },
    }));
    const list = table(
      ["Document", "Slug", "Status", "Updated", "Actions"],
      data.items || [],
      (row) => [
        row.title,
        row.slug,
        row.status,
        formatDate(row.updated_at),
        actions(
          button("View", "table-action", async () => {
            try {
              const detail = await api(`/api/v1/admin/cms/documents/${row.id}`);
              const latest = detail.versions?.[0];
              openForm({
                title: `CMS ${row.slug}`,
                fields: [{ name: "body", label: "Latest content", type: "textarea", value: latest?.body || "", required: false }],
                submitLabel: "Закрыть",
                onSubmit: async () => true,
              });
            } catch (error) { toast(error.message, "error"); }
          }),
          button("Publish latest", "table-action", async () => {
            try {
              await mutate(`/api/v1/admin/cms/documents/${row.id}/publish`, {
                body: { version_id: null },
                label: `Publish latest CMS version for ${row.slug}?`,
              });
              toast("CMS published", "ok");
              await renderCms();
            } catch (error) { toast(error.message, "error"); }
          }),
        ),
      ],
    );
    dom.controlView.replaceChildren(card("CMS documents", list, actions(createButton)));
  }

  async function renderCampaigns() {
    const data = await api("/api/v1/admin/notifications/campaigns");
    const createButton = button("Create campaign", "primary", () => openForm({
      title: "Notification campaign",
      fields: [
        { name: "name", label: "Name" },
        { name: "title", label: "Message title" },
        { name: "body", label: "Message body", type: "textarea", maxLength: 4000 },
      ],
      onSubmit: async ({ name, title, body }) => {
        const preview = await api("/api/v1/admin/notifications/preview", {
          method: "POST",
          body: JSON.stringify({ segment: { active_only: true }, message: { title, body } }),
        });
        if (!window.confirm(`Получателей: ${preview.recipient_count}. Создать campaign draft?`)) return false;
        await mutate("/api/v1/admin/notifications/campaigns", {
          body: { name, segment: { active_only: true }, message: { title, body } },
          confirm: false,
        });
        toast("Campaign created", "ok");
        await renderCampaigns();
      },
    }));
    const campaignTable = table(
      ["Campaign", "Status", "Created", "Actions"],
      data.items || [],
      (row) => [
        `${row.name}\n${row.id}`,
        row.status,
        formatDate(row.created_at),
        actions(
          button("Test", "table-action", () => openForm({
            title: "Test campaign",
            fields: [{ name: "test_user_id", label: "Test user UUID" }],
            onSubmit: async ({ test_user_id }) => {
              await mutate(`/api/v1/admin/notifications/campaigns/${row.id}/test`, {
                body: { test_user_id },
                label: `Queue test delivery for ${row.name}?`,
              });
              toast("Test delivery queued", "ok");
            },
          })),
          button("Start", "table-action", async () => {
            try {
              await mutate(`/api/v1/admin/notifications/campaigns/${row.id}/start`, {
                sensitive: true,
                label: `Materialize and start campaign ${row.name}?`,
              });
              toast("Campaign started", "ok");
              await renderCampaigns();
            } catch (error) { toast(error.message, "error"); }
          }),
          button("Cancel", "table-action dangerous", async () => {
            try {
              await mutate(`/api/v1/admin/notifications/campaigns/${row.id}/cancel`, {
                label: `Cancel campaign ${row.name}?`,
              });
              toast("Campaign cancelled", "ok");
              await renderCampaigns();
            } catch (error) { toast(error.message, "error"); }
          }),
        ),
      ],
    );
    dom.controlView.replaceChildren(card("Durable campaigns", campaignTable, actions(createButton)));
  }

  async function renderPromos() {
    const data = await api("/api/v1/admin/control/promocodes");
    const createButton = button("Create promo", "primary", () => openForm({
      title: "Create promo code",
      fields: [
        { name: "code", label: "Code" },
        { name: "reward_credits", label: "Reward credits", type: "number", step: "0.01" },
        { name: "max_uses", label: "Max uses (optional)", type: "number", required: false },
      ],
      onSubmit: async ({ code, reward_credits, max_uses }) => {
        await mutate("/api/v1/admin/control/promocodes", {
          body: { code, reward_credits, max_uses: max_uses ? Number(max_uses) : null },
          label: `Create promo ${code}?`,
        });
        toast("Promo created", "ok");
        await renderPromos();
      },
    }));
    const promoTable = table(
      ["Code", "Reward", "Usage", "Status", "Actions"],
      data.items || [],
      (row) => [
        row.code,
        row.reward_credits,
        `${row.uses_count}/${row.max_uses || "∞"}`,
        row.is_active ? "active" : "inactive",
        actions(button(row.is_active ? "Deactivate" : "Activate", "table-action", async () => {
          try {
            await mutate(`/api/v1/admin/promocodes/${row.id}/state`, {
              body: { is_active: !row.is_active },
              label: `${row.is_active ? "Deactivate" : "Activate"} promo ${row.code}?`,
            });
            await renderPromos();
          } catch (error) { toast(error.message, "error"); }
        })),
      ],
    );
    dom.controlView.replaceChildren(card("Promo management", promoTable, actions(createButton)));
  }

  async function renderContent() {
    const [prompts, trends] = await Promise.all([
      api("/api/v1/admin/prompts?status=pending"),
      api("/api/v1/admin/trends"),
    ]);
    const promptTable = table(
      ["Prompt", "Status", "Actions"],
      prompts.items || [],
      (row) => [
        `${row.title}\n${row.prompt.slice(0, 300)}`,
        row.status,
        actions(
          ...["approve", "reject", "deactivate"].map((action) => button(action, action === "reject" ? "table-action dangerous" : "table-action", () => openForm({
            title: `${action} prompt`,
            fields: [{ name: "reason", label: "Reason", type: "textarea", maxLength: 1000 }],
            onSubmit: async ({ reason }) => {
              await mutate(`/api/v1/admin/prompts/${row.id}/moderate`, {
                body: { action, reason },
                label: `${action} prompt ${row.id}?`,
              });
              await renderContent();
            },
          }))),
        ),
      ],
    );
    const trendCreate = button("Create trend", "primary", () => openForm({
      title: "Create trend",
      fields: [
        { name: "title", label: "Title" },
        { name: "payload", label: "Payload JSON", type: "textarea", value: "{}" },
      ],
      onSubmit: async ({ title, payload }) => {
        await mutate("/api/v1/admin/trends", {
          body: { title, payload: JSON.parse(payload || "{}") },
          label: `Create trend ${title}?`,
        });
        await renderContent();
      },
    }));
    const trendTable = table(
      ["Trend", "Status", "Actions"],
      trends.items || [],
      (row) => [row.title, row.is_active ? "active" : "inactive", actions(button("Remove", "table-action dangerous", async () => {
        try {
          await mutate(`/api/v1/admin/trends/${row.id}`, { method: "DELETE", label: `Remove trend ${row.title}?` });
          await renderContent();
        } catch (error) { toast(error.message, "error"); }
      }))],
    );
    const feedForm = node("div", "stack");
    const generation = input("text", "", "Generation UUID");
    const stateSelect = select([["visible", "visible"], ["blurred", "blurred"], ["removed", "removed"]], "blurred");
    const reason = textarea("", "Moderation reason");
    feedForm.append(field("Generation UUID", generation), field("State", stateSelect), field("Reason", reason));
    feedForm.appendChild(button("Apply feed moderation", "primary", async () => {
      try {
        await mutate(`/api/v1/admin/feed/${generation.value.trim()}/moderation`, {
          body: { state: stateSelect.value, reason: reason.value },
          label: `Set generation ${generation.value.trim()} to ${stateSelect.value}?`,
        });
        toast("Feed moderation saved", "ok");
      } catch (error) { toast(error.message, "error"); }
    }));
    dom.controlView.replaceChildren(
      card("Prompt moderation", promptTable),
      card("Trends", trendTable, actions(trendCreate)),
      card("Feed moderation", feedForm),
    );
  }

  async function renderRuntime() {
    const data = await api("/api/v1/admin/runtime");
    const subscription = Boolean(data.subscription_required?.enabled);
    const body = pre(data);
    const controls = actions(
      button(`Subscription required: ${subscription ? "ON" : "OFF"}`, "table-action", async () => {
        try {
          await mutate("/api/v1/admin/runtime/subscription-required", {
            body: { enabled: !subscription },
            label: `Set subscription_required=${!subscription}?`,
          });
          await renderRuntime();
        } catch (error) { toast(error.message, "error"); }
      }),
      button("Reload pricing", "table-action", async () => {
        try {
          await mutate("/api/v1/admin/runtime/reload", {
            label: "Reload runtime pricing from latest published TariffVersion?",
          });
          toast("Runtime reloaded", "ok");
          await renderRuntime();
        } catch (error) { toast(error.message, "error"); }
      }),
    );
    dom.controlView.replaceChildren(card("Runtime settings", body, controls));
  }

  async function renderPartners() {
    const [analytics, withdrawals] = await Promise.all([
      api("/api/v1/admin/partners/analytics"),
      api("/api/v1/admin/partners/withdrawals?limit=100"),
    ]);
    const summary = pre(analytics);
    const withdrawalTable = table(
      ["Withdrawal", "User", "Amount", "Status", "Actions"],
      withdrawals.items || [],
      (row) => [
        row.id,
        row.user_id,
        row.amount,
        row.status,
        actions(button("Change state", "table-action", () => openForm({
          title: `Withdrawal ${row.id}`,
          fields: [
            { name: "status", label: "Target status", type: "select", options: [["processing", "processing"], ["paid", "paid"], ["rejected", "rejected"], ["canceled", "canceled"]] },
            { name: "reason", label: "Reason", type: "textarea", maxLength: 500 },
          ],
          onSubmit: async ({ status, reason }) => {
            await mutate(`/api/v1/admin/partners/withdrawals/${row.id}/state`, {
              body: { status, reason },
              sensitive: true,
              label: `Move withdrawal ${row.id} to ${status}?`,
            });
            await renderPartners();
          },
        }))),
      ],
    );
    dom.controlView.replaceChildren(card("Partner analytics", summary), card("Withdrawals", withdrawalTable));
  }

  async function renderExports() {
    const content = node("div", "control-grid");
    for (const kind of ["payments", "withdrawals"]) {
      content.appendChild(card(
        kind === "payments" ? "Payments" : "Withdrawals",
        node("p", "muted", "До 10 000 последних записей, без секретных provider payload/requisites."),
        actions(
          button("CSV", "table-action", async () => {
            try { await download(`/api/v1/admin/control/exports/${kind}.csv`, `${kind}.csv`); }
            catch (error) { toast(error.message, "error"); }
          }),
          button("XLSX", "table-action", async () => {
            try { await download(`/api/v1/admin/control/exports/${kind}.xlsx`, `${kind}.xlsx`); }
            catch (error) { toast(error.message, "error"); }
          }),
        ),
      ));
    }
    dom.controlView.replaceChildren(content);
  }

  async function login(event) {
    event.preventDefault();
    if (!tg?.initData) {
      setMessage(dom.controlLoginMessage, "Откройте control page из Telegram Mini App: signed initData отсутствует.", "error");
      return;
    }
    const payload = {};
    const otp = dom.controlOtp.value.trim();
    const recovery = dom.controlRecovery.value.trim();
    if (otp) payload.otp = otp;
    if (recovery) payload.recovery_code = recovery;
    setMessage(dom.controlLoginMessage, "Проверяем admin identity…");
    try {
      const result = await api("/api/v1/admin/auth/login", {
        method: "POST",
        telegram: true,
        auth: false,
        body: JSON.stringify(payload),
      });
      state.token = result.token;
      if (result.mfa_setup_required) {
        state.token = null;
        setMessage(
          dom.controlLoginMessage,
          "Первичная настройка MFA выполняется в основной admin console. После настройки вернитесь сюда.",
          "error",
        );
        return;
      }
      if (!result.mfa_verified) throw new Error("MFA verification required");
      state.me = await api("/api/v1/admin/auth/me");
      if (!state.me.is_active || !state.me.role) throw new Error("Server did not confirm active admin role");
      dom.controlIdentity.replaceChildren(
        node("strong", "", state.me.username ? `@${state.me.username}` : String(state.me.telegram_id)),
        node("small", "", `${state.me.role} · server confirmed`),
      );
      dom.controlAuth.hidden = true;
      dom.controlShell.hidden = false;
      dom.controlOtp.value = "";
      dom.controlRecovery.value = "";
      setView("overview");
    } catch (error) {
      state.token = null;
      state.me = null;
      setMessage(dom.controlLoginMessage, error.message || "Login failed", "error");
    }
  }

  async function logout() {
    try {
      if (state.token) await api("/api/v1/admin/auth/logout", { method: "POST" });
    } catch (_error) {
      // Local memory-only credential removal is still mandatory.
    }
    state.token = null;
    state.me = null;
    dom.controlShell.hidden = true;
    dom.controlAuth.hidden = false;
    dom.controlView.replaceChildren();
    setMessage(dom.controlLoginMessage, "Сессия завершена.", "ok");
  }

  dom.controlLogin.addEventListener("submit", login);
  dom.controlLogout.addEventListener("click", logout);
  dom.controlRefresh.addEventListener("click", () => loadView());
  dom.controlStepVerify.addEventListener("click", verifyStepUp);
  dom.controlStepCancel.addEventListener("click", cancelStepUp);
  dom.controlFormCancel.addEventListener("click", () => dom.controlFormDialog.close());
  tg?.ready?.();
  tg?.expand?.();
  if (!tg?.initData) {
    setMessage(dom.controlLoginMessage, "Для admin control нужен запуск из Telegram Mini App.", "error");
  }
})();
