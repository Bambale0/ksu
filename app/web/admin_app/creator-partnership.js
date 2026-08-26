(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = { token: null, me: null, applications: [], agreements: [] };
  const byId = (id) => document.getElementById(id);

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

  function msg(text = "", error = false) {
    const node = byId("authMessage");
    if (!node) return;
    node.textContent = text;
    node.classList.toggle("error", error);
  }

  function toast(text) {
    const node = byId("toast");
    node.textContent = text;
    node.hidden = false;
    window.setTimeout(() => { if (node.textContent === text) node.hidden = true; }, 3000);
  }

  async function api(path, options = {}) {
    const { telegram = false, ...rest } = options;
    const headers = { Accept: "application/json", ...(rest.headers || {}) };
    if (rest.body !== undefined) headers["Content-Type"] = "application/json";
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    if (telegram && tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    const response = await fetch(path, { ...rest, headers, credentials: "same-origin", cache: "no-store" });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const error = new Error(payload?.detail || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function format(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value ?? "—");
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(number);
  }

  function statusLabel(status) {
    const labels = {
      active: "Активно",
      paused: "На паузе",
      ended: "Завершено",
      pending: "На рассмотрении",
      approved: "Одобрено",
      rejected: "Отклонено",
    };
    const normalized = String(status ?? "").toLowerCase();
    return labels[normalized] || status || "—";
  }

  function badge(status) {
    return el("span", `badge ${status || "unknown"}`, statusLabel(status));
  }

  function field(label, input) {
    const wrapper = el("label", "field");
    wrapper.append(el("span", "", label), input);
    return wrapper;
  }

  function input(type = "text", value = "", placeholder = "") {
    const node = document.createElement(type === "textarea" ? "textarea" : "input");
    if (type !== "textarea") node.type = type;
    node.value = value ?? "";
    node.placeholder = placeholder;
    return node;
  }

  async function login(event) {
    event.preventDefault();
    if (!tg?.initData) {
      msg("Нужен свежий Telegram initData. Открой эту страницу внутри Telegram.", true);
      return;
    }
    msg("Проверяю доступ…");
    try {
      const otp = byId("loginOtp").value.trim();
      const result = await api("/api/v1/admin/auth/login", {
        method: "POST",
        telegram: true,
        body: JSON.stringify({ otp: otp || null, recovery_code: null }),
      });
      state.token = result.token;
      if (result.mfa_setup_required) {
        state.token = null;
        throw new Error("Сначала настройте второй фактор в основной админке.");
      }
      state.me = await api("/api/v1/admin/auth/me");
      if (!state.me.permissions?.includes("partners.read") && !state.me.permissions?.includes("*")) {
        throw new Error("Нет права partners.read");
      }
      byId("authPanel").hidden = true;
      byId("consolePanel").hidden = false;
      byId("adminIdentity").textContent = `${state.me.username ? `@${state.me.username}` : state.me.telegram_id} · ${state.me.role}`;
      await refresh();
    } catch (error) {
      msg(error.message || "Не удалось войти", true);
    }
  }

  async function refresh() {
    const status = byId("statusFilter")?.value || "";
    try {
      const [applications, agreements] = await Promise.all([
        api(`/api/v1/admin/creator-partnership/applications?limit=100${status ? `&status=${encodeURIComponent(status)}` : ""}`),
        api("/api/v1/admin/creator-partnership/agreements?limit=100"),
      ]);
      state.applications = applications.items || [];
      state.agreements = agreements.items || [];
      render();
    } catch (error) {
      toast(error.message || "Не удалось обновить данные");
    }
  }

  function render() {
    const pending = state.applications.filter((item) => item.status === "pending").length;
    const active = state.agreements.filter((item) => item.status === "active").length;
    byId("summary").replaceChildren(
      metric("Заявок", state.applications.length),
      metric("На рассмотрении", pending),
      metric("Активных соглашений", active),
      metric("Месячный ROX", `${format(state.agreements.filter((item) => item.status === "active").reduce((sum, item) => sum + Number(item.monthly_rox || 0), 0))} ROX`),
    );
    renderApplications();
    renderAgreements();
  }

  function metric(label, value) {
    const node = el("article", "metric");
    node.append(el("span", "", label), el("strong", "", value));
    return node;
  }

  function renderApplications() {
    const root = byId("applications");
    root.replaceChildren();
    if (!state.applications.length) {
      root.appendChild(el("div", "empty", "Нет заявок."));
      return;
    }
    state.applications.forEach((item) => root.appendChild(applicationCard(item)));
  }

  function applicationCard(item) {
    const card = el("article", "card");
    const head = el("div", "card-head");
    const who = el("div");
    who.append(el("strong", "", item.channel_name), el("small", "", item.user?.username ? `@${item.user.username}` : `TG ${item.user?.telegram_id || "—"}`));
    head.append(who, badge(item.status));
    const facts = el("div", "facts");
    facts.append(
      fact("Аудитория", format(item.audience_size)),
      fact("Просмотры", item.average_views == null ? "—" : format(item.average_views)),
      fact("Формат", item.cooperation_format),
    );
    const link = document.createElement("a");
    link.href = item.channel_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = item.channel_url;
    card.append(head, facts, link);
    if (item.message) card.appendChild(el("p", "note", item.message));
    if (item.status === "pending" && canManage()) card.appendChild(decisionForm(item));
    if (item.decision_note) card.appendChild(el("p", "note decision", item.decision_note));
    return card;
  }

  function fact(label, value) {
    const node = el("div", "fact");
    node.append(el("span", "", label), el("strong", "", value));
    return node;
  }

  function canManage() {
    return state.me?.permissions?.includes("partners.manage") || state.me?.permissions?.includes("*");
  }

  function decisionForm(item) {
    const form = el("form", "decision-form");
    const monthly = input("number", "", "ROX / месяц");
    monthly.min = "1";
    monthly.step = "0.01";
    const terms = input("textarea", "", "Персональные условия");
    const note = input("textarea", "", "Комментарий решения");
    const start = input("date", new Date().toISOString().slice(0, 7) + "-01");
    const actions = el("div", "actions");
    actions.append(
      button("Одобрить", () => void decide(item, "approved", { monthly, terms, note, start }), "approve"),
      button("Отклонить", () => void decide(item, "rejected", { monthly, terms, note, start }), "danger"),
    );
    form.append(
      field("ROX в месяц", monthly),
      field("Условия", terms),
      field("Дата начала", start),
      field("Комментарий", note),
      actions,
    );
    return form;
  }

  async function decide(item, decision, fields) {
    const monthly = Number(fields.monthly.value);
    if (decision === "approved" && (!Number.isFinite(monthly) || monthly <= 0 || !fields.terms.value.trim())) {
      toast("Для одобрения нужны ROX/месяц и условия");
      return;
    }
    if (!window.confirm(decision === "approved" ? "Одобрить персональное соглашение?" : "Отклонить заявку?")) return;
    try {
      await api(`/api/v1/admin/creator-partnership/applications/${encodeURIComponent(item.id)}/decision`, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID(), "X-Confirm-Action": "confirmed" },
        body: JSON.stringify({
          decision,
          decision_note: fields.note.value.trim(),
          terms_summary: decision === "approved" ? fields.terms.value.trim() : null,
          monthly_rox: decision === "approved" ? monthly : null,
          terms: {},
          starts_on: decision === "approved" ? fields.start.value || null : null,
          ends_on: null,
        }),
      });
      toast("Решение сохранено");
      await refresh();
    } catch (error) {
      toast(error.message || "Не удалось сохранить решение");
    }
  }

  function renderAgreements() {
    const root = byId("agreements");
    root.replaceChildren();
    if (!state.agreements.length) {
      root.appendChild(el("div", "empty", "Соглашений пока нет."));
      return;
    }
    state.agreements.forEach((item) => root.appendChild(agreementCard(item)));
  }

  function agreementCard(item) {
    const card = el("article", "card agreement");
    const head = el("div", "card-head");
    const who = el("div");
    who.append(el("strong", "", item.user?.username ? `@${item.user.username}` : item.user?.first_name || "Партнёр"), el("small", "", item.terms_summary));
    head.append(who, badge(item.status));
    const facts = el("div", "facts");
    facts.append(fact("ROX / месяц", format(item.monthly_rox)), fact("Начало", item.starts_on), fact("Конец", item.ends_on || "—"));
    card.append(head, facts);
    if (item.grants?.length) {
      const list = el("div", "grant-list");
      item.grants.slice(0, 6).forEach((grant) => list.appendChild(fact(grant.period, `+${format(grant.amount_rox)} ROX`)));
      card.appendChild(list);
    }
    if (canManage()) card.appendChild(agreementActions(item));
    return card;
  }

  function agreementActions(item) {
    const actions = el("div", "actions");
    actions.append(
      button("Изменить условия", () => editAgreement(item), "secondary"),
      button("Начислить период", () => void manualGrant(item), "approve"),
    );
    return actions;
  }

  async function editAgreement(item) {
    const monthly = window.prompt("ROX в месяц", item.monthly_rox);
    if (monthly == null) return;
    const terms = window.prompt("Условия", item.terms_summary);
    if (terms == null) return;
    const status = window.prompt("Статус: активно / пауза / завершено", item.status);
    if (!status) return;
    const reason = window.prompt("Причина изменения", "Изменение условий") || "Изменение условий";
    if (!window.confirm("Подтвердить изменение соглашения?")) return;
    try {
      await api(`/api/v1/admin/creator-partnership/agreements/${encodeURIComponent(item.id)}`, {
        method: "PATCH",
        headers: { "Idempotency-Key": crypto.randomUUID(), "X-Confirm-Action": "confirmed" },
        body: JSON.stringify({ status, terms_summary: terms, monthly_rox: Number(monthly), terms: item.terms || {}, ends_on: item.ends_on, reason }),
      });
      toast("Соглашение обновлено");
      await refresh();
    } catch (error) {
      toast(error.message || "Не удалось обновить соглашение");
    }
  }

  async function stepUp() {
    const otp = window.prompt("Свежий код подтверждения");
    if (!otp) return false;
    try {
      await api("/api/v1/admin/auth/step-up", {
        method: "POST",
        telegram: true,
        body: JSON.stringify({ otp, recovery_code: null }),
      });
      return true;
    } catch (error) {
      toast(error.message || "Подтверждение не пройдено");
      return false;
    }
  }

  async function manualGrant(item) {
    const period = window.prompt("Период YYYY-MM", new Date().toISOString().slice(0, 7));
    if (!period) return;
    const note = window.prompt("Комментарий", "Ручное начисление") || "";
    if (!window.confirm(`Начислить ${item.monthly_rox} ROX за ${period}?`)) return;
    if (!(await stepUp())) return;
    try {
      await api(`/api/v1/admin/creator-partnership/agreements/${encodeURIComponent(item.id)}/grants`, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID(), "X-Confirm-Action": "confirmed" },
        body: JSON.stringify({ period, note }),
      });
      toast("Начисление выполнено");
      await refresh();
    } catch (error) {
      toast(error.message || "Не удалось начислить ROX");
    }
  }

  function init() {
    tg?.ready?.();
    tg?.expand?.();
    byId("loginForm")?.addEventListener("submit", login);
    byId("refreshButton")?.addEventListener("click", () => void refresh());
    byId("statusFilter")?.addEventListener("change", () => void refresh());
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
