(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    mounted: false,
    open: false,
    loading: false,
    activeTab: "visible",
    visible: [],
    hidden: [],
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
      el("small", "", "Скрытые работы сохраняются и доступны для восстановления после перезапуска."),
    );
    const toggle = button("Управлять", () => {
      state.open = !state.open;
      panel.classList.toggle("is-open", state.open);
      body.hidden = !state.open;
      toggle.textContent = state.open ? "Свернуть" : "Управлять";
      if (state.open) void load();
    }, "roxy-history-secondary");
    head.append(copy, toggle);

    const body = el("div", "roxy-history-management-body");
    body.hidden = true;
    const tabs = el("div", "roxy-history-management-actions");
    tabs.id = "roxyHistoryManagementTabs";
    const visibleTab = button("В истории", () => switchTab("visible"), "roxy-history-secondary");
    visibleTab.dataset.historyManagementTab = "visible";
    const hiddenTab = button("Скрытые", () => switchTab("hidden"), "roxy-history-secondary");
    hiddenTab.dataset.historyManagementTab = "hidden";
    tabs.append(visibleTab, hiddenTab);

    const list = el("div", "roxy-history-management-list");
    list.id = "roxyHistoryManagementList";
    list.setAttribute("aria-live", "polite");
    body.append(tabs, list);
    panel.append(head, body);
    historyMount.insertAdjacentElement("beforebegin", panel);
    state.mounted = true;
    syncTabs();
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

  function syncTabs() {
    document.querySelectorAll("[data-history-management-tab]").forEach((node) => {
      const active = node.dataset.historyManagementTab === state.activeTab;
      node.classList.toggle("is-active", active);
      node.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function switchTab(tab) {
    if (tab !== "visible" && tab !== "hidden") return;
    state.activeTab = tab;
    syncTabs();
    render();
  }

  function currentItems() {
    return state.activeTab === "hidden" ? state.hidden : state.visible;
  }

  function render() {
    const list = document.getElementById("roxyHistoryManagementList");
    if (!list) return;
    list.replaceChildren();
    syncTabs();
    const items = currentItems();
    if (!items.length) {
      list.appendChild(el(
        "div",
        "roxy-history-empty",
        state.activeTab === "hidden" ? "Скрытых работ нет." : "В истории пока нет работ.",
      ));
      return;
    }

    for (const item of items) {
      const hidden = state.activeTab === "hidden" || Boolean(item.hidden_from_history);
      const row = el("article", `roxy-history-management-row${hidden ? " is-hidden" : ""}`);
      const copy = el("div", "roxy-history-management-copy");
      copy.append(
        el("strong", "", item.model?.title || item.model_id || "Генерация"),
        el("small", "", `${statusLabel(item.status)} · ${date(item.created_at)}`),
      );
      if (item.prompt) copy.appendChild(el("p", "", item.prompt.slice(0, 110)));
      const actions = el("div", "roxy-history-management-actions");
      if (hidden) {
        actions.appendChild(button("Вернуть", () => restore(item), "primary-button compact"));
      } else {
        actions.appendChild(button("Скрыть", () => hide(item), "roxy-history-secondary danger"));
      }
      row.append(copy, actions);
      list.appendChild(row);
    }
  }

  function removeById(items, id) {
    return items.filter((entry) => entry.id !== id);
  }

  async function hide(item) {
    if (!item?.id) return;
    try {
      await api(`/api/v1/generations/${encodeURIComponent(item.id)}/history`, { method: "DELETE" });
      state.visible = removeById(state.visible, item.id);
      state.hidden = [{ ...item, hidden_from_history: true }, ...removeById(state.hidden, item.id)];
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
      state.hidden = removeById(state.hidden, item.id);
      state.visible = [{ ...item, hidden_from_history: false }, ...removeById(state.visible, item.id)];
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
      const [visiblePayload, hiddenPayload] = await Promise.all([
        api("/api/v1/generations?limit=50"),
        api("/api/v1/generation-history/hidden?limit=50"),
      ]);
      state.visible = Array.isArray(visiblePayload?.items) ? visiblePayload.items : [];
      state.hidden = Array.isArray(hiddenPayload?.items) ? hiddenPayload.items : [];
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
