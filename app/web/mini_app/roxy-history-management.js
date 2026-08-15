(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    mounted: false,
    open: false,
    loading: false,
    items: [],
  };

  function authHeaders() {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      headers: { ...authHeaders(), ...(options.headers || {}) },
    });
    const body = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) {
      const detail = body?.detail;
      throw new Error(typeof detail === "string" ? detail : `HTTP ${response.status}`);
    }
    return body;
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

  function date(value) {
    const parsed = new Date(value || "");
    if (Number.isNaN(parsed.getTime())) return "";
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(parsed);
  }

  function notify(kind) {
    try { tg?.HapticFeedback?.notificationOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function mount() {
    if (state.mounted) return true;
    const historyView = document.getElementById("historyView");
    const historyMount = document.getElementById("historyMount");
    if (!historyView || !historyMount) return false;

    const panel = el("section", "roxy-history-management");
    panel.id = "roxyHistoryManagement";
    const head = el("div", "roxy-history-management-head");
    const copy = el("div");
    copy.append(
      el("span", "section-kicker", "История"),
      el("strong", "", "Управление работами"),
      el("small", "", "Скрывайте лишнее и возвращайте одним нажатием."),
    );
    const toggle = button("Управлять", () => {
      state.open = !state.open;
      panel.classList.toggle("is-open", state.open);
      list.hidden = !state.open;
      toggle.textContent = state.open ? "Свернуть" : "Управлять";
      if (state.open) void load();
    }, "roxy-history-secondary");
    head.append(copy, toggle);

    const list = el("div", "roxy-history-management-list");
    list.id = "roxyHistoryManagementList";
    list.hidden = true;
    list.setAttribute("aria-live", "polite");
    panel.append(head, list);
    historyMount.insertAdjacentElement("beforebegin", panel);
    state.mounted = true;
    return true;
  }

  function statusLabel(status) {
    return {
      queued: "В очереди",
      retry: "Повтор",
      submitting: "Запускается",
      generating: "Генерируется",
      succeeded: "Готово",
      failed: "Ошибка",
    }[status] || status || "—";
  }

  function render() {
    const list = document.getElementById("roxyHistoryManagementList");
    if (!list) return;
    list.replaceChildren();
    if (!state.items.length) {
      list.appendChild(el("div", "roxy-history-empty", "В истории пока нет работ."));
      return;
    }

    for (const item of state.items) {
      const row = el("article", `roxy-history-management-row${item.__hiddenLocally ? " is-hidden" : ""}`);
      const copy = el("div", "roxy-history-management-copy");
      copy.append(
        el("strong", "", item.model?.title || item.model_id || "Генерация"),
        el("small", "", `${statusLabel(item.status)} · ${date(item.created_at)}`),
      );
      if (item.prompt) copy.appendChild(el("p", "", item.prompt.slice(0, 110)));
      const actions = el("div", "roxy-history-management-actions");
      if (item.__hiddenLocally) {
        actions.appendChild(button("Вернуть", () => restore(item), "primary-button compact"));
      } else {
        actions.appendChild(button("Скрыть", () => hide(item), "roxy-history-secondary danger"));
      }
      row.append(copy, actions);
      list.appendChild(row);
    }
  }

  async function hide(item) {
    if (!item?.id) return;
    try {
      await api(`/api/v1/generations/${encodeURIComponent(item.id)}/history`, { method: "DELETE" });
      item.__hiddenLocally = true;
      notify("success");
      render();
      window.dispatchEvent(new CustomEvent("roxy:history-changed"));
    } catch (error) {
      notify("error");
      window.alert(error.message || "Не удалось скрыть генерацию.");
    }
  }

  async function restore(item) {
    if (!item?.id) return;
    try {
      await api(`/api/v1/generations/${encodeURIComponent(item.id)}/history/restore`, { method: "POST" });
      item.__hiddenLocally = false;
      notify("success");
      render();
      window.dispatchEvent(new CustomEvent("roxy:history-changed"));
    } catch (error) {
      notify("error");
      window.alert(error.message || "Не удалось вернуть генерацию.");
    }
  }

  async function load() {
    if (!tg?.initData || state.loading) return;
    state.loading = true;
    const list = document.getElementById("roxyHistoryManagementList");
    if (list) list.replaceChildren(el("div", "roxy-history-empty", "Загружаю…"));
    try {
      const payload = await api("/api/v1/generations?limit=50");
      state.items = Array.isArray(payload?.items) ? payload.items : [];
      render();
    } catch (error) {
      if (list) list.replaceChildren(el("div", "roxy-history-empty error", error.message || "Не удалось загрузить историю."));
    } finally {
      state.loading = false;
    }
  }

  function init() {
    if (mount()) return;
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      if (mount() || attempts >= 30) window.clearInterval(timer);
    }, 100);
  }

  window.RoxyHistoryManagement = Object.freeze({ load });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
