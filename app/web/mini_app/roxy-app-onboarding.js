(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  let overlay = null;

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
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
    return payload;
  }

  function node(tag, className = "", text = "") {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  }

  function safeLink(label, href) {
    if (!href || !String(href).startsWith("https://")) return null;
    const link = node("a", "roxy-onboarding-link", label);
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    return link;
  }

  async function complete(button, status) {
    button.disabled = true;
    status.textContent = "Сохраняю…";
    try {
      await api("/api/v1/onboarding/complete", { method: "POST" });
      overlay?.remove();
      overlay = null;
      document.body?.classList.remove("roxy-app-onboarding-open");
      try { tg?.HapticFeedback?.notificationOccurred?.("success"); } catch (_error) { /* optional */ }
      window.dispatchEvent(new CustomEvent("roxy:onboarding-complete"));
    } catch (error) {
      button.disabled = false;
      status.textContent = error?.message || "Не удалось сохранить. Попробуй ещё раз.";
      status.classList.add("is-error");
    }
  }

  function render(data) {
    if (overlay || data.completed || !data.enabled) return;
    overlay = node("section", "roxy-app-onboarding");
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-labelledby", "roxyOnboardingTitle");

    const card = node("div", "roxy-app-onboarding-card");
    const mark = node("div", "roxy-app-onboarding-mark", "RX");
    const kicker = node("div", "roxy-app-onboarding-kicker", "ROXY");
    const title = node("h1", "roxy-app-onboarding-title", data.title || "Добро пожаловать в ROXY");
    title.id = "roxyOnboardingTitle";
    const body = node(
      "p",
      "roxy-app-onboarding-body",
      data.body || "Все инструменты ROXY находятся внутри приложения: генерации, баланс, история, профиль и поддержка."
    );

    const links = node("div", "roxy-app-onboarding-links");
    const rules = safeLink("Правила", data.rules_url);
    const privacy = safeLink("Конфиденциальность", data.privacy_url);
    if (rules) links.appendChild(rules);
    if (privacy) links.appendChild(privacy);

    const button = node("button", "roxy-app-onboarding-button", "Открыть ROXY");
    button.type = "button";
    const status = node("div", "roxy-app-onboarding-status");
    button.addEventListener("click", () => void complete(button, status));

    card.append(mark, kicker, title, body);
    if (links.childElementCount) card.appendChild(links);
    card.append(button, status);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    document.body.classList.add("roxy-app-onboarding-open");
    window.setTimeout(() => button.focus(), 0);
  }

  async function init() {
    // Browser fallback sessions can use other auth flows. Do not lock the UI when
    // Telegram initData is unavailable; the protected API remains authoritative.
    if (!tg?.initData) return;
    try {
      const status = await api("/api/v1/onboarding");
      render(status || {});
    } catch (_error) {
      // Fail open: onboarding must never make a healthy Mini App unusable.
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => void init(), { once: true });
  } else {
    void init();
  }
})();
