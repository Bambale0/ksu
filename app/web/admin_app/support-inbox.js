(() => {
  "use strict";
  const STATUSES = [["open", "Открыто"], ["in_progress", "В работе"], ["resolved", "Решено"], ["closed", "Закрыто"]];
  const DELIVERY = {
    pending: "В очереди отправки", claimed: "В очереди отправки", sending: "Отправляется", retry: "Повторная попытка отправки",
    delivery_unknown: "Доставка в Telegram не подтверждена",
    sent: "Доставлено в Telegram", failed: "Не удалось отправить", undeliverable: "Telegram недоступен пользователю",
  };
  const element = (tag, className = "", text = "") => {
    const item = document.createElement(tag);
    item.className = className;
    if (text) item.textContent = text;
    return item;
  };
  const button = (label, action, className = "table-action") => {
    const item = element("button", className, label);
    item.type = "button";
    item.addEventListener("click", action);
    return item;
  };
  const label = (title, control) => {
    const item = element("label", "field");
    item.append(element("span", "", title), control);
    return item;
  };
  const select = (options, value) => {
    const item = document.createElement("select");
    for (const [key, title] of options) {
      const option = element("option", "", title);
      option.value = key;
      item.append(option);
    }
    item.value = value;
    return item;
  };
  const identity = (ticket) => {
    const user = ticket.user || {};
    return [user.username ? "@" + user.username : "", [user.first_name, user.last_name].filter(Boolean).join(" "),
      user.telegram_id ? "Telegram " + user.telegram_id : "", "user " + ticket.user_id].filter(Boolean).join(" · ");
  };
  const date = (value) => value ? new Date(value).toLocaleString("ru-RU") : "—";
  const statusLabel = (value) => STATUSES.find(([key]) => key === value)?.[1] || value;
  const key = () => crypto.randomUUID();

  window.createSupportInbox = (config) => {
    let filters = { q: "", status: "", offset: 0 };
    let currentId = null;
    let sequence = 0;
    let messages = [];
    let olderCursor = null;
    let moreMessages = false;
    let historyComplete = false;
    let ticket = null;
    const drafts = new Map();
    const active = () => config.isActive();
    const valid = (request) => request === sequence && active();
    const writable = () => config.canManage();
    const shell = (title) => {
      const result = element("section", "panel support-inbox");
      result.append(element("h2", "support-title", title));
      return result;
    };
    const errorPanel = (error, retry) => {
      const panel = shell("Не удалось загрузить обращения");
      panel.append(element("p", "support-error", error.message || "Ошибка загрузки"), button("Повторить загрузку", retry));
      config.container.replaceChildren(panel);
    };
    const draftFor = (id) => {
      if (!drafts.has(id)) drafts.set(id, { body: "", key: null, keyBody: null, sending: false });
      return drafts.get(id);
    };
    const write = (path, body, method = "POST", idempotencyKey = key(), confirm = false) =>
      config.api(path, { method, body: JSON.stringify(body), headers: {
        "Idempotency-Key": idempotencyKey, "X-Admin-Confirm": confirm ? "true" : "false",
      } });

    async function list(next = filters) {
      filters = { ...filters, ...next };
      currentId = null;
      config.onSelect(null);
      const request = ++sequence;
      const query = new URLSearchParams({ limit: "50", offset: String(filters.offset || 0) });
      if (filters.q) query.set("q", filters.q);
      if (filters.status) query.set("status", filters.status);
      try {
        const data = await config.api(config.base + "?" + query);
        if (!valid(request)) return;
        const panel = shell("Очередь поддержки");
        const searchForm = element("form", "support-filters");
        const search = element("input");
        search.type = "search";
        search.value = filters.q;
        search.placeholder = "Имя, Telegram ID, тема или ID обращения";
        const status = select([["", "Все статусы"], ...STATUSES], filters.status);
        const find = button("Найти", () => {});
        find.type = "submit";
        searchForm.append(label("Поиск обращений", search), label("Статус обращений", status), find);
        searchForm.addEventListener("submit", (event) => {
          event.preventDefault();
          void list({ q: search.value.trim(), status: status.value, offset: 0 });
        });
        panel.append(searchForm);
        const rows = element("div", "support-tickets");
        for (const row of data.items || []) {
          const item = element("article", "support-ticket");
          const meta = element("div", "support-ticket-summary");
          meta.append(element("strong", "", row.topic), element("small", "muted", identity(row)));
          if (row.last_message) meta.append(element("p", "", row.last_message.body));
          const state = element("small", row.needs_reply ? "support-needs-reply" : "muted",
            statusLabel(row.status) + (row.needs_reply ? " · Нужен ответ" : "") + " · " + date(row.updated_at));
          meta.append(state);
          item.append(meta, button("Открыть", () => void open(row.id)));
          rows.append(item);
        }
        if (!data.items?.length) rows.append(element("p", "muted", "Обращения по этим условиям не найдены."));
        const paging = element("div", "support-actions");
        const previous = button("Предыдущая страница", () => void list({ offset: Math.max(0, filters.offset - 50) }));
        previous.disabled = !filters.offset;
        const nextPage = button("Следующая страница", () => void list({ offset: filters.offset + 50 }));
        nextPage.disabled = !data.has_more;
        paging.append(previous, element("span", "muted", "Всего обращений: " + data.total), nextPage,
          button("Обновить обращения", () => void list()));
        panel.append(rows, paging);
        config.container.replaceChildren(panel);
      } catch (error) {
        if (valid(request)) errorPanel(error, () => void list());
      }
    }

    function mergeMessages(incoming) {
      const byId = new Map(messages.map((message) => [message.id, message]));
      for (const message of incoming || []) byId.set(message.id, message);
      messages = [...byId.values()].sort((a, b) =>
        (a.created_at || "").localeCompare(b.created_at || "") || String(a.id).localeCompare(String(b.id)));
    }

    async function open(id, options = {}) {
      const sameTicket = currentId === id && ticket?.id === id;
      if (!sameTicket) {
        messages = []; olderCursor = null; moreMessages = false; historyComplete = false; ticket = null;
      }
      currentId = id;
      config.onSelect(id);
      const request = ++sequence;
      const query = new URLSearchParams({ message_limit: "100" });
      if (options.before) query.set("before", options.before);
      try {
        const data = await config.api(config.base + "/" + id + "?" + query);
        if (!valid(request) || currentId !== id) return;
        const knownIds = new Set(messages.map((message) => message.id));
        const disconnectedLatest = !options.before
          && !(data.messages || []).some((message) => knownIds.has(message.id));
        mergeMessages(data.messages);
        if (!sameTicket || options.before || !ticket || ticket.id !== id) {
          olderCursor = data.messages_before;
          moreMessages = data.messages_has_more;
          historyComplete = !data.messages_has_more;
        } else if (data.messages_has_more && (disconnectedLatest || (!historyComplete && !moreMessages))) {
          olderCursor = data.messages_before; moreMessages = true; historyComplete = false;
        }
        if (Number.isInteger(data.messages_total) && messages.length === data.messages_total) {
          olderCursor = null; moreMessages = false; historyComplete = true;
        }
        ticket = data;
        drawTicket();
      } catch (error) {
        if (valid(request)) errorPanel(error, () => void open(id, options));
      }
    }

    function drawTicket() {
      const id = currentId;
      const panel = shell(ticket.topic + " · " + statusLabel(ticket.status));
      panel.append(element("p", "muted support-identity", identity(ticket)));
      const navigation = element("div", "support-actions");
      navigation.append(button("← К очереди", () => void list()),
        button("Обновить переписку", () => void open(id)));
      panel.append(navigation);
      const feedback = element("p", "support-feedback");
      feedback.setAttribute("role", "status");
      if (writable()) {
        const controls = element("form", "support-actions");
        const status = select(STATUSES, ticket.status);
        const save = button("Сохранить статус", () => {});
        save.type = "submit";
        const update = async (value) => {
          save.disabled = true;
          try {
            await write(config.base + "/" + id + config.statusSuffix, { status: value }, config.statusMethod);
            if (active() && currentId === id) await open(id);
          } catch (error) { feedback.textContent = error.message || "Статус не сохранён"; }
          finally { save.disabled = false; }
        };
        controls.append(label("Статус обращения", status), save);
        controls.addEventListener("submit", (event) => { event.preventDefault(); void update(status.value); });
        if (ticket.status === "closed" || ticket.status === "resolved") {
          controls.append(button("Открыть обращение заново", () => void update("open")));
        }
        if (config.assignSuffix) {
          const assignee = element("input");
          assignee.value = ticket.assigned_admin_id || "";
          assignee.placeholder = "ID администратора; пусто — снять назначение";
          controls.append(label("Ответственный", assignee), button("Назначить", async (event) => {
            event.currentTarget.disabled = true;
            try {
              await write(config.base + "/" + id + config.assignSuffix, { assigned_admin_id: assignee.value.trim() || null });
              if (active() && currentId === id) await open(id);
            } catch (error) { feedback.textContent = error.message || "Назначение не сохранено"; }
            finally { event.target.disabled = false; }
          }));
          const priority = select([["low", "Низкий"], ["normal", "Обычный"], ["high", "Высокий"], ["urgent", "Срочный"]], ticket.priority);
          controls.append(label("Приоритет", priority), button("Сохранить приоритет", async () => {
            try {
              await write(config.base + "/" + id + config.statusSuffix, { priority: priority.value }, config.statusMethod);
              if (active() && currentId === id) await open(id);
            } catch (error) { feedback.textContent = error.message || "Приоритет не сохранён"; }
          }));
        }
        panel.append(controls);
      }
      panel.append(feedback);
      if (moreMessages && olderCursor) panel.append(button("Загрузить предыдущие сообщения", (event) => {
        event.currentTarget.disabled = true;
        void open(id, { before: olderCursor });
      }));
      const thread = element("div", "thread support-thread");
      for (const message of messages) {
        const item = element("article", "message" + (message.is_admin ? " admin" : ""));
        const head = element("div", "message-head");
        head.append(element("strong", "", message.is_admin ? "Администратор" : "Пользователь"),
          element("small", "muted", date(message.created_at)));
        item.append(head, element("p", "", message.body));
        if (message.is_admin) {
          const delivery = element("small", ["failed", "undeliverable"].includes(message.delivery_status) ? "support-error" : "muted",
            DELIVERY[message.delivery_status] || "Статус доставки неизвестен");
          item.append(delivery);
          if (message.delivery_status === "delivery_unknown") {
            item.append(element("p", "muted", "Уточните получение перед повторной отправкой."));
          }
        }
        thread.append(item);
      }
      if (!messages.length) thread.append(element("p", "muted", "В обращении ещё нет сообщений."));
      panel.append(thread);
      if (writable()) {
        if (ticket.status === "closed" || ticket.status === "resolved") {
          panel.append(element("p", "muted", "Чтобы продолжить переписку, откройте обращение заново."));
        } else {
          const draft = draftFor(id);
          const form = element("form", "support-compose");
          const body = element("textarea");
          body.value = draft.body;
          body.maxLength = 4000;
          body.required = true;
          body.rows = 4;
          body.addEventListener("input", () => { draft.body = body.value; });
          const send = button("Отправить ответ", () => {}, "primary");
          send.type = "submit";
          send.dataset.supportSend = "true";
          send.disabled = draft.sending;
          const outcome = element("p", "support-feedback");
          outcome.setAttribute("role", "status");
          form.append(label("Ответ пользователю", body),
            element("small", "muted", "Ответ сохранится в обращении и будет отправлен пользователю в Telegram."), outcome, send);
          form.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (draft.sending) return;
            const text = body.value.trim();
            if (!text) { outcome.textContent = "Введите текст ответа."; return; }
            if (draft.keyBody !== text) { draft.key = key(); draft.keyBody = text; }
            draft.body = body.value;
            draft.sending = true;
            send.disabled = true;
            outcome.textContent = "Сохраняем ответ…";
            try {
              const result = await write(config.base + "/" + id + config.replySuffix, { body: text }, "POST", draft.key, true);
              if (draft.body.trim() === text) draft.body = "";
              draft.key = null;
              draft.keyBody = null;
              draft.sending = false;
              body.value = draft.body;
              outcome.textContent = DELIVERY[result.delivery_status] || "Ответ сохранён";
              if (active() && currentId === id) await open(id);
            } catch (error) {
              outcome.textContent = "Отправка не подтверждена. Текст сохранён; повторите попытку. " + (error.message || "");
            } finally {
              draft.sending = false;
              send.disabled = false;
              if (active() && currentId === id) {
                const visibleSend = config.container.querySelector("[data-support-send]");
                if (visibleSend) visibleSend.disabled = false;
              }
            }
          });
          panel.append(form);
        }
      }
      config.container.replaceChildren(panel);
    }

    const timer = window.setInterval(() => {
      if (!active() || document.hidden || !config.container.querySelector(".support-inbox")) return;
      if (document.activeElement?.matches("input,textarea,select") || config.container.querySelector("button:disabled.primary")) return;
      void (currentId ? open(currentId) : list());
    }, 30000);
    return {
      list, open,
      reset() { ++sequence; currentId = null; messages = []; ticket = null; olderCursor = null; moreMessages = false; historyComplete = false; drafts.clear(); filters = { q: "", status: "", offset: 0 }; },
      destroy() { window.clearInterval(timer); ++sequence; drafts.clear(); },
    };
  };
})();
