(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const baseFetch = window.fetch.bind(window);
  const state = {
    recovery: null,
    promoMounted: false,
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
    if (json) headers["Content-Type"] = "application/json";
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function api(path, options = {}) {
    const hasBody = options.body !== undefined;
    const response = await baseFetch(path, {
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
      const message = typeof detail === "string"
        ? detail
        : detail?.message || payload?.message || `HTTP ${response.status}`;
      const error = new Error(message);
      error.status = response.status;
      error.code = detail?.code || null;
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  function requestInfo(input, init) {
    const raw = typeof input === "string" ? input : input?.url;
    if (!raw) return null;
    let url;
    try {
      url = new URL(raw, window.location.origin);
    } catch (_error) {
      return null;
    }
    const method = String(
      init?.method || (typeof input !== "string" ? input?.method : "GET") || "GET",
    ).toUpperCase();
    return { url, method };
  }

  window.fetch = async (input, init) => {
    const response = await baseFetch(input, init);
    const info = requestInfo(input, init);
    if (!info) return response;

    if (
      info.method === "POST"
      && info.url.pathname === "/api/v1/generations"
      && response.status === 409
    ) {
      response.clone().json().then((payload) => {
        if (payload?.detail !== "Insufficient credits") return;
        let generationPayload = null;
        try {
          generationPayload = typeof init?.body === "string" ? JSON.parse(init.body) : null;
        } catch (_error) {
          generationPayload = null;
        }
        if (generationPayload) void showInsufficientRecovery(generationPayload);
      }).catch(() => {});
    }

    if (info.method === "GET" && info.url.pathname === "/api/v1/me" && response.ok) {
      response.clone().json().then((me) => {
        refreshRecoveryBalance(me?.balance_rox);
      }).catch(() => {});
    }
    return response;
  };

  function formatCredits(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(number);
  }

  function setBalanceDom(value) {
    const formatted = `${formatCredits(value)} кр.`;
    for (const id of ["balanceValue", "walletBalance"]) {
      const node = document.getElementById(id);
      if (node) node.textContent = formatted;
    }
  }

  function haptic(kind = "light") {
    try {
      tg?.HapticFeedback?.impactOccurred?.(kind);
    } catch (_error) {
      // Optional Telegram capability.
    }
  }

  function notify(kind = "success") {
    try {
      tg?.HapticFeedback?.notificationOccurred?.(kind);
    } catch (_error) {
      // Optional Telegram capability.
    }
  }

  function ensureRecoveryDialog() {
    let dialog = document.getElementById("insufficientCreditsDialog");
    if (dialog) return dialog;

    dialog = el("dialog", "insufficient-dialog");
    dialog.id = "insufficientCreditsDialog";
    const panel = el("div", "insufficient-panel");
    panel.appendChild(el("span", "section-kicker", "Недостаточно кредитов"));
    panel.appendChild(el("h3", "", "Пополнить баланс?"));

    const summary = el("dl", "insufficient-summary");
    const rows = [
      ["Текущий баланс", "insufficientCurrent"],
      ["Стоимость действия", "insufficientRequired"],
      ["Не хватает", "insufficientShortage"],
    ];
    for (const [label, id] of rows) {
      const dt = el("dt", "", label);
      const dd = el("dd", "", "—");
      dd.id = id;
      summary.append(dt, dd);
    }

    const message = el("div", "profile-message");
    message.id = "insufficientMessage";
    const actions = el("div", "insufficient-actions");
    const cancel = el("button", "profile-action-button secondary", "Отмена");
    cancel.type = "button";
    cancel.addEventListener("click", () => dialog.close("cancel"));
    const topup = el("button", "profile-action-button", "Пополнить");
    topup.type = "button";
    topup.addEventListener("click", () => {
      haptic();
      dialog.close("topup");
      openWalletRecovery();
    });
    actions.append(cancel, topup);
    panel.append(summary, message, actions);
    dialog.appendChild(panel);
    document.body.appendChild(dialog);
    return dialog;
  }

  async function showInsufficientRecovery(generationPayload) {
    if (!tg?.initData) return;
    const wasBuilderOpen = !document.getElementById("builderView")?.hidden;
    try {
      const [me, quote] = await Promise.all([
        api("/api/v1/me"),
        api("/api/v1/generations/quote", {
          method: "POST",
          body: JSON.stringify(generationPayload),
        }),
      ]);
      const current = Number(me?.balance_rox || 0);
      const required = Number(quote?.cost_credits || quote?.cost_rox || 0);
      const shortage = Math.max(0, required - current);
      state.recovery = {
        current,
        required,
        shortage,
        wasBuilderOpen,
      };
      setBalanceDom(me?.balance_rox || 0);
      renderRecoveryDialog();
      const dialog = ensureRecoveryDialog();
      if (typeof dialog.showModal === "function" && !dialog.open) dialog.showModal();
      notify("error");
    } catch (_error) {
      // Core generator still shows its own API error. Recovery UI is best-effort enhancement.
    }
  }

  function renderRecoveryDialog() {
    if (!state.recovery) return;
    document.getElementById("insufficientCurrent").textContent = `${formatCredits(state.recovery.current)} кр.`;
    document.getElementById("insufficientRequired").textContent = `${formatCredits(state.recovery.required)} кр.`;
    document.getElementById("insufficientShortage").textContent = `${formatCredits(state.recovery.shortage)} кр.`;
    const message = document.getElementById("insufficientMessage");
    if (message) {
      message.textContent = state.recovery.shortage > 0
        ? "Настройки генерации сохранены. После пополнения вернитесь и нажмите «Создать» снова."
        : "Баланс уже достаточен. Закройте окно и повторите создание.";
    }
  }

  function ensureWalletRecoveryBanner() {
    const wallet = document.getElementById("walletView");
    if (!wallet) return null;
    let banner = document.getElementById("walletRecoveryBanner");
    if (banner) return banner;
    banner = el("section", "shell-panel wallet-recovery-banner");
    banner.id = "walletRecoveryBanner";
    banner.hidden = true;
    const copy = el("div", "wallet-recovery-copy");
    copy.append(el("strong", "", "Пополнение для генерации"), el("small", "", ""));
    const button = el("button", "profile-action-button", "Проверить баланс");
    button.type = "button";
    button.disabled = true;
    button.addEventListener("click", returnToBuilder);
    banner.append(copy, button);
    const firstPanel = wallet.querySelector(".wallet-hero, .shell-panel");
    if (firstPanel?.parentNode) firstPanel.parentNode.insertBefore(banner, firstPanel.nextSibling);
    else wallet.prepend(banner);
    return banner;
  }

  function openWalletRecovery() {
    if (!state.recovery) return;
    const banner = ensureWalletRecoveryBanner();
    if (banner) {
      banner.hidden = false;
      renderWalletRecovery();
    }
    document.querySelector('[data-shell-nav="wallet"]')?.click();
  }

  function renderWalletRecovery() {
    const banner = ensureWalletRecoveryBanner();
    if (!banner || !state.recovery) return;
    banner.hidden = false;
    const small = banner.querySelector("small");
    const button = banner.querySelector("button");
    const enough = state.recovery.current >= state.recovery.required;
    if (small) {
      small.textContent = enough
        ? `Баланс ${formatCredits(state.recovery.current)} кр. — достаточно для генерации.`
        : `Нужно ещё ${formatCredits(state.recovery.shortage)} кр. Текущий баланс: ${formatCredits(state.recovery.current)} кр.`;
    }
    if (button) {
      button.disabled = !enough;
      button.textContent = enough ? "Вернуться к генерации" : "Ожидаем пополнение";
    }
  }

  function refreshRecoveryBalance(value) {
    if (!state.recovery) return;
    const current = Number(value);
    if (!Number.isFinite(current)) return;
    state.recovery.current = current;
    state.recovery.shortage = Math.max(0, state.recovery.required - current);
    setBalanceDom(current);
    renderRecoveryDialog();
    renderWalletRecovery();
  }

  function returnToBuilder() {
    if (!state.recovery || state.recovery.current < state.recovery.required) return;
    haptic();
    document.querySelector('[data-shell-nav="create"]')?.click();
    if (state.recovery.wasBuilderOpen) {
      const createHome = document.getElementById("createHome");
      const builder = document.getElementById("builderView");
      const detail = document.getElementById("generationDetailView");
      if (createHome && builder) {
        createHome.hidden = true;
        builder.hidden = false;
        if (detail) detail.hidden = true;
        try {
          tg?.BackButton?.show?.();
        } catch (_error) {
          // Optional Telegram client chrome.
        }
      }
    }
    document.getElementById("walletRecoveryBanner")?.setAttribute("hidden", "");
    state.recovery = null;
  }

  function mountPromo() {
    if (state.promoMounted) return;
    const profile = document.getElementById("profileView");
    if (!profile) return;
    state.promoMounted = true;

    const section = el("section", "home-section promo-section");
    const head = el("div", "home-section-head");
    const copy = el("div");
    copy.append(el("span", "section-kicker", "Бонус"), el("h2", "", "Промокод"));
    head.appendChild(copy);

    const panel = el("div", "shell-panel promo-panel");
    const form = el("form", "promo-form");
    const input = document.createElement("input");
    input.type = "text";
    input.maxLength = 64;
    input.autocomplete = "off";
    input.placeholder = "Введите промокод";
    input.setAttribute("aria-label", "Промокод");
    const button = el("button", "profile-action-button", "Применить");
    button.type = "submit";
    const message = el("div", "profile-message");
    message.setAttribute("aria-live", "polite");
    form.append(input, button);
    panel.append(form, message);
    section.append(head, panel);
    profile.appendChild(section);
    Object.assign(dom, { promoForm: form, promoInput: input, promoButton: button, promoMessage: message });
    form.addEventListener("submit", redeemPromo);
  }

  function setPromoMessage(text = "", tone = "") {
    if (!dom.promoMessage) return;
    dom.promoMessage.textContent = text;
    dom.promoMessage.className = `profile-message${tone ? ` ${tone}` : ""}`;
  }

  async function redeemPromo(event) {
    event.preventDefault();
    if (!tg?.initData || dom.promoButton.disabled) return;
    const code = dom.promoInput.value.trim();
    if (!code) {
      setPromoMessage("Введите промокод", "error");
      return;
    }
    haptic();
    dom.promoButton.disabled = true;
    setPromoMessage("Проверяем промокод…");
    try {
      const result = await api("/api/v1/promocodes/redeem", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      dom.promoInput.value = "";
      setBalanceDom(result.balance_rox);
      setPromoMessage(
        `Готово: начислено ${formatCredits(result.reward_rox)} кр. Баланс ${formatCredits(result.balance_rox)} кр.`,
        "ok",
      );
      notify("success");
      refreshRecoveryBalance(result.balance_rox);
      // Reopening Profile asks the notifications module for the authoritative new inbox item.
    } catch (error) {
      const messages = {
        invalid: "Промокод не существует или недоступен для аккаунта",
        expired: "Срок действия промокода истёк",
        already_used: "Этот промокод уже был использован",
        usage_limit_reached: "Лимит активаций промокода исчерпан",
      };
      setPromoMessage(messages[error.code] || error.message || "Не удалось применить промокод", "error");
      notify("error");
    } finally {
      dom.promoButton.disabled = false;
    }
  }

  function enforceTransactionEmptyCopy() {
    const list = document.getElementById("transactionList");
    if (!list) return;
    const empty = list.querySelector(".shell-empty");
    if (empty && empty.textContent.trim() === "Операций пока нет.") {
      empty.textContent = "Операций пока нет. Пополните баланс или создайте первый контент.";
    }
  }

  function observeTransactionEmptyState() {
    const list = document.getElementById("transactionList");
    if (!list) return;
    new MutationObserver(enforceTransactionEmptyCopy).observe(list, { childList: true, subtree: true });
    enforceTransactionEmptyCopy();
  }

  mountPromo();
  ensureRecoveryDialog();
  ensureWalletRecoveryBanner();
  observeTransactionEmptyState();
})();
