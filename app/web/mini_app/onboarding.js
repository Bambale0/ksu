(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const appShell = document.getElementById("appShell");
  const previousFetch = window.fetch.bind(window);
  const state = {
    status: null,
    loading: false,
  };
  const dom = {};

  function authHeaders(json = false) {
    const headers = { Accept: "application/json" };
    if (json) headers["Content-Type"] = "application/json";
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function api(path, options = {}) {
    const hasBody = options.body !== undefined;
    const response = await previousFetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      headers: { ...authHeaders(hasBody), ...(options.headers || {}) },
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }
    if (!response.ok) {
      const detail = payload?.detail;
      const message = typeof detail === "string" ? detail : detail?.message || `HTTP ${response.status}`;
      const error = new Error(message);
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function setLocked(locked) {
    if (!appShell) return;
    appShell.inert = Boolean(locked);
    appShell.setAttribute("aria-hidden", locked ? "true" : "false");
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

  function ensureOverlay() {
    if (dom.overlay) return dom.overlay;
    const overlay = el("div", "onboarding-overlay");
    overlay.id = "onboardingOverlay";
    overlay.hidden = true;
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-labelledby", "onboardingTitle");

    const card = el("section", "onboarding-card");
    const mark = el("div", "onboarding-mark", "RX");
    mark.setAttribute("aria-hidden", "true");
    const kicker = el("span", "section-kicker", "ROXY · AI CREATIVE STUDIO");
    const title = el("h1", "", "Загрузка…");
    title.id = "onboardingTitle";
    const body = el("p", "onboarding-body", "Проверяем состояние профиля.");
    const links = el("div", "onboarding-links");
    const message = el("div", "onboarding-message");
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");
    const start = el("button", "onboarding-start", "Начать");
    start.type = "button";
    start.disabled = true;
    const retry = el("button", "onboarding-retry", "Повторить");
    retry.type = "button";
    retry.hidden = true;

    card.append(mark, kicker, title, body, links, message, start, retry);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    Object.assign(dom, { overlay, card, title, body, links, message, start, retry });

    start.addEventListener("click", complete);
    retry.addEventListener("click", loadStatus);
    return overlay;
  }

  function safeHttps(value) {
    if (!value) return null;
    try {
      const url = new URL(value);
      return url.protocol === "https:" ? url.href : null;
    } catch (_error) {
      return null;
    }
  }

  function openExternal(url) {
    const safe = safeHttps(url);
    if (!safe) return;
    haptic();
    try {
      if (tg?.openLink) {
        tg.openLink(safe);
        return;
      }
    } catch (_error) {
      // Fall through to normal browser navigation.
    }
    window.open(safe, "_blank", "noopener,noreferrer");
  }

  function renderLinks(status) {
    dom.links.replaceChildren();
    const items = [
      ["Правила", status.rules_url],
      ["Конфиденциальность", status.privacy_url],
    ];
    for (const [label, value] of items) {
      const safe = safeHttps(value);
      if (!safe) continue;
      const button = el("button", "onboarding-link", label);
      button.type = "button";
      button.addEventListener("click", () => openExternal(safe));
      dom.links.appendChild(button);
    }
    dom.links.hidden = dom.links.children.length === 0;
  }

  function showLoading() {
    ensureOverlay();
    setLocked(true);
    dom.overlay.hidden = false;
    dom.title.textContent = "Загрузка…";
    dom.body.textContent = "Проверяем состояние профиля.";
    dom.links.hidden = true;
    dom.message.textContent = "";
    dom.start.disabled = true;
    dom.retry.hidden = true;
  }

  function showError(message) {
    ensureOverlay();
    setLocked(true);
    dom.overlay.hidden = false;
    dom.title.textContent = "Не удалось открыть ROXY";
    dom.body.textContent = "Состояние onboarding не подтверждено сервером.";
    dom.links.hidden = true;
    dom.message.textContent = message || "Проверьте соединение и повторите попытку.";
    dom.start.disabled = true;
    dom.retry.hidden = false;
    dom.retry.focus({ preventScroll: true });
  }

  function showStatus(status) {
    ensureOverlay();
    state.status = status;
    if (!status?.enabled || status?.completed) {
      dom.overlay.hidden = true;
      setLocked(false);
      return;
    }
    setLocked(true);
    dom.overlay.hidden = false;
    dom.title.textContent = status.title || "Добро пожаловать в ROXY";
    dom.body.textContent = status.body || "Завершите вводный экран, чтобы продолжить.";
    renderLinks(status);
    dom.message.textContent = "";
    dom.start.disabled = false;
    dom.retry.hidden = true;
    requestAnimationFrame(() => dom.start.focus({ preventScroll: true }));
  }

  async function loadStatus() {
    if (!tg?.initData || state.loading) {
      if (!tg?.initData) setLocked(false);
      return;
    }
    state.loading = true;
    showLoading();
    try {
      const status = await api("/api/v1/onboarding");
      showStatus(status);
    } catch (error) {
      showError(error.message);
    } finally {
      state.loading = false;
    }
  }

  async function complete() {
    if (!tg?.initData || dom.start.disabled) return;
    haptic("medium");
    dom.start.disabled = true;
    dom.message.textContent = "Сохраняем…";
    try {
      const status = await api("/api/v1/onboarding/complete", { method: "POST" });
      state.status = status;
      if (!status?.completed) throw new Error("Onboarding state was not confirmed");
      notify("success");
      dom.overlay.hidden = true;
      setLocked(false);
      window.dispatchEvent(new CustomEvent("ksu:onboarding-complete", { detail: status }));
    } catch (error) {
      notify("error");
      dom.message.textContent = error.message || "Не удалось сохранить. Повторите попытку.";
      dom.start.disabled = false;
    }
  }

  window.fetch = async (input, init) => {
    const response = await previousFetch(input, init);
    if (response.status === 428 && tg?.initData) {
      response.clone().json().then((payload) => {
        if (payload?.detail?.code === "onboarding_required") void loadStatus();
      }).catch(() => {});
    }
    return response;
  };

  ensureOverlay();
  if (tg?.initData) {
    setLocked(true);
    void loadStatus();
  } else {
    setLocked(false);
  }
})();