(() => {
  "use strict";

  const LABEL = "Оплата картой · USD / EUR / RUB / СБП";
  const tg = window.Telegram?.WebApp;
  const walletView = document.getElementById("walletView");
  const legacyTopup = document.getElementById("topupHeading")?.closest(".home-section");
  if (!walletView || !legacyTopup) return;

  const state = {
    packages: [],
    currency: "RUB",
    packageId: null,
    email: "",
    intent: null,
    busy: false,
    current: null,
    pollTimer: null,
  };

  const section = document.createElement("section");
  section.className = "home-section primary-card-section";
  section.setAttribute("aria-labelledby", "primaryCardHeading");
  legacyTopup.before(section);

  const style = document.createElement("style");
  style.textContent = `
    .primary-card-section{display:grid;gap:12px}
    .primary-card-panel{display:grid;gap:14px;padding:16px}
    .primary-card-title{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
    .primary-card-title h2{margin:2px 0 0;font-size:18px}
    .primary-card-badge{padding:5px 9px;border-radius:999px;background:rgba(127,127,127,.12);font-size:11px;font-weight:700}
    .primary-card-controls{display:grid;grid-template-columns:130px minmax(0,1fr);gap:10px}
    .primary-card-controls label{display:grid;gap:6px;font-size:12px;font-weight:700}
    .primary-card-controls select,.primary-card-controls input{width:100%;min-height:44px;border:1px solid var(--shell-border,#d9dde5);border-radius:12px;background:transparent;color:inherit;padding:0 12px;font:inherit}
    .primary-card-packages{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
    .primary-card-package{display:grid;gap:4px;text-align:left;padding:12px;border-radius:14px;border:1px solid var(--shell-border,#d9dde5);background:transparent;color:inherit}
    .primary-card-package.is-selected{outline:2px solid currentColor;outline-offset:-2px}
    .primary-card-package strong{font-size:15px}.primary-card-package span{font-size:12px;opacity:.72}
    .primary-card-summary{display:flex;justify-content:space-between;gap:12px;align-items:center;padding-top:2px}
    .primary-card-message{min-height:20px;font-size:13px}.primary-card-message.error{color:#d14343}.primary-card-message.ok{color:#138a52}
    .primary-card-actions{display:flex;gap:8px;flex-wrap:wrap}.primary-card-actions button{flex:1;min-width:140px}
    @media(max-width:620px){.primary-card-controls{grid-template-columns:1fr}.primary-card-packages{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);

  const titleWrap = document.createElement("div");
  titleWrap.className = "primary-card-title";
  const titleCopy = document.createElement("div");
  const kicker = document.createElement("span");
  kicker.className = "section-kicker";
  kicker.textContent = "Основной способ оплаты";
  const heading = document.createElement("h2");
  heading.id = "primaryCardHeading";
  heading.textContent = LABEL;
  titleCopy.append(kicker, heading);
  const badge = document.createElement("span");
  badge.className = "primary-card-badge";
  badge.textContent = "Рекомендуется";
  titleWrap.append(titleCopy, badge);

  const panel = document.createElement("div");
  panel.className = "shell-panel primary-card-panel";
  const controls = document.createElement("div");
  controls.className = "primary-card-controls";
  const currencyLabel = document.createElement("label");
  currencyLabel.textContent = "Валюта";
  const currency = document.createElement("select");
  currency.setAttribute("aria-label", "Валюта оплаты");
  ["RUB", "USD", "EUR"].forEach((code) => {
    const option = document.createElement("option");
    option.value = code;
    option.textContent = code;
    currency.appendChild(option);
  });
  currencyLabel.appendChild(currency);
  const emailLabel = document.createElement("label");
  emailLabel.textContent = "Email для платёжной страницы и чека";
  const email = document.createElement("input");
  email.type = "email";
  email.inputMode = "email";
  email.autocomplete = "email";
  email.placeholder = "you@example.com";
  email.maxLength = 254;
  emailLabel.appendChild(email);
  controls.append(currencyLabel, emailLabel);

  const packages = document.createElement("div");
  packages.className = "primary-card-packages";
  packages.setAttribute("aria-live", "polite");
  const summary = document.createElement("div");
  summary.className = "primary-card-summary";
  const summaryText = document.createElement("strong");
  summaryText.textContent = "Выберите пакет";
  const note = document.createElement("small");
  note.textContent = "Без автоматического пересчёта валют";
  summary.append(summaryText, note);
  const message = document.createElement("div");
  message.className = "primary-card-message";
  message.setAttribute("role", "status");
  message.setAttribute("aria-live", "polite");
  const actions = document.createElement("div");
  actions.className = "primary-card-actions";
  const pay = document.createElement("button");
  pay.type = "button";
  pay.className = "primary-button";
  pay.textContent = "Перейти к оплате";
  pay.disabled = true;
  const refresh = document.createElement("button");
  refresh.type = "button";
  refresh.className = "quiet-button";
  refresh.textContent = "Обновить статус";
  refresh.hidden = true;
  actions.append(pay, refresh);
  panel.append(controls, packages, summary, message, actions);
  section.append(titleWrap, panel);

  const legacyHeading = document.getElementById("topupHeading");
  if (legacyHeading) legacyHeading.textContent = "Другие способы оплаты";

  function headers(extra = {}) {
    const result = { Accept: "application/json", ...extra };
    if (tg?.initData) result["X-Telegram-Init-Data"] = tg.initData;
    return result;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      headers: headers(options.headers || {}),
    });
    let payload = null;
    try { payload = await response.json(); } catch (_error) { payload = null; }
    if (!response.ok) {
      const detail = typeof payload?.detail === "string" ? payload.detail : `HTTP ${response.status}`;
      const error = new Error(detail);
      error.status = response.status;
      error.retryAfter = Number(response.headers.get("Retry-After") || payload?.retry_after || 0);
      throw error;
    }
    return payload;
  }

  function uuid() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    const bytes = new Uint8Array(16);
    globalThis.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map((item) => item.toString(16).padStart(2, "0"));
    return `${hex.slice(0,4).join("")}-${hex.slice(4,6).join("")}-${hex.slice(6,8).join("")}-${hex.slice(8,10).join("")}-${hex.slice(10).join("")}`;
  }

  function format(value) {
    const number = Number(value);
    return Number.isFinite(number)
      ? new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(number)
      : String(value ?? "—");
  }

  function selectedPackage() {
    return state.packages.find((item) => item.id === state.packageId) || null;
  }

  function priceFor(pkg) {
    return pkg?.prices?.[state.currency] ?? null;
  }

  function setMessage(text = "", tone = "") {
    message.textContent = text;
    message.classList.toggle("error", tone === "error");
    message.classList.toggle("ok", tone === "ok");
  }

  function validEmail() {
    const value = state.email.trim();
    return value.length >= 3 && value.length <= 254 && !value.includes(" ") && value.split("@").length === 2;
  }

  function sync() {
    const pkg = selectedPackage();
    const amount = priceFor(pkg);
    summaryText.textContent = pkg && amount != null
      ? `${format(pkg.credits)} кр. · ${format(amount)} ${state.currency === "RUB" ? "₽" : state.currency}`
      : `Нет выбранного пакета для ${state.currency}`;
    pay.disabled = state.busy || !tg?.initData || !pkg || amount == null || !validEmail();
    pay.textContent = state.busy ? "Создаём оплату…" : "Перейти к оплате";
    refresh.hidden = !state.current;
  }

  function renderPackages() {
    packages.replaceChildren();
    const available = state.packages.filter((pkg) => priceFor(pkg) != null);
    if (!available.length) {
      const empty = document.createElement("div");
      empty.className = "shell-empty";
      empty.textContent = `Пакеты в ${state.currency} пока не настроены.`;
      packages.appendChild(empty);
      state.packageId = null;
      sync();
      return;
    }
    if (!available.some((pkg) => pkg.id === state.packageId)) state.packageId = available[0].id;
    available.forEach((pkg) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `primary-card-package${pkg.id === state.packageId ? " is-selected" : ""}`;
      button.append(
        Object.assign(document.createElement("strong"), { textContent: `${format(pkg.credits)} кр.` }),
        Object.assign(document.createElement("span"), { textContent: `${format(priceFor(pkg))} ${state.currency === "RUB" ? "₽" : state.currency}` }),
      );
      button.addEventListener("click", () => {
        state.packageId = pkg.id;
        state.intent = null;
        renderPackages();
        tg?.HapticFeedback?.impactOccurred?.("light");
      });
      packages.appendChild(button);
    });
    sync();
  }

  async function loadPackages() {
    if (!tg?.initData) {
      setMessage("Оплата доступна при открытии Mini App через Telegram.", "error");
      return;
    }
    try {
      const payload = await api("/api/v1/payments/card/packages");
      state.packages = Object.entries(payload?.packages || {}).map(([id, item]) => ({ id, ...item }));
      renderPackages();
    } catch (_error) {
      packages.replaceChildren(Object.assign(document.createElement("div"), {
        className: "shell-error",
        textContent: "Не удалось загрузить основной способ оплаты.",
      }));
      sync();
    }
  }

  function intent() {
    const pkg = selectedPackage();
    if (!pkg) return null;
    const key = `${pkg.id}:${state.currency}:${state.email.trim().toLowerCase()}`;
    if (state.intent?.fingerprint === key) return state.intent;
    state.intent = { fingerprint: key, id: uuid() };
    return state.intent;
  }

  function openUrl(url) {
    if (!url) return;
    try {
      if (tg?.openLink) tg.openLink(url);
      else window.open(url, "_blank", "noopener,noreferrer");
    } catch (_error) {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  }

  async function refreshBalance() {
    try {
      const me = await api("/api/v1/me");
      const value = `${format(me.balance_rox)} кр.`;
      const walletBalance = document.getElementById("walletBalance");
      const headerBalance = document.getElementById("balanceValue");
      if (walletBalance) walletBalance.textContent = value;
      if (headerBalance) headerBalance.textContent = value;
    } catch (_error) { /* shell will recover on next refresh */ }
  }

  function renderStatus(payment) {
    state.current = payment;
    if (!payment) {
      setMessage();
      sync();
      return;
    }
    const labels = {
      creating: "создаём оплату",
      creation_unknown: "уточняем состояние",
      pending: "ожидает оплаты",
      succeeded: "оплачено",
      failed: "не оплачено",
      refunded: "возвращено",
      partially_refunded: "частичный возврат",
      refund_review: "проверяем возврат",
    };
    const text = `Статус: ${labels[payment.status] || payment.status}. ${format(payment.amount)} ${payment.currency}.`;
    setMessage(text, payment.status === "succeeded" ? "ok" : (["failed", "canceled", "expired"].includes(payment.status) ? "error" : ""));
    sync();
    rewriteNeutralHistoryLabels();
  }

  async function reconcile(userInitiated = false) {
    if (!state.current?.id) return null;
    try {
      const payment = await api(`/api/v1/payments/card/${encodeURIComponent(state.current.id)}/reconcile`, { method: "POST" });
      const previous = state.current?.status;
      renderStatus(payment);
      if (payment.status === "succeeded" && previous !== "succeeded") {
        tg?.HapticFeedback?.notificationOccurred?.("success");
        await refreshBalance();
      }
      return payment;
    } catch (_error) {
      if (userInitiated) setMessage("Не удалось обновить статус. Попробуйте ещё раз.", "error");
      return null;
    }
  }

  function startPolling() {
    clearTimeout(state.pollTimer);
    if (!state.current?.id) return;
    const tick = async () => {
      if (walletView.hidden || !state.current) return;
      const payment = await api(`/api/v1/payments/card/${encodeURIComponent(state.current.id)}`).catch(() => null);
      if (payment) renderStatus(payment);
      if (payment && ["creating", "creation_unknown", "pending"].includes(payment.status)) {
        state.pollTimer = setTimeout(tick, 5000);
      }
    };
    state.pollTimer = setTimeout(tick, 4000);
  }

  async function checkout() {
    if (state.busy || !validEmail()) return;
    const pkg = selectedPackage();
    const currentIntent = intent();
    if (!pkg || !currentIntent) return;
    state.busy = true;
    sync();
    setMessage("Создаём безопасный платёжный intent…");
    try {
      const payment = await api("/api/v1/payments/card/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": currentIntent.id },
        body: JSON.stringify({
          package_id: pkg.id,
          currency: state.currency,
          billing_email: state.email.trim(),
        }),
      });
      renderStatus(payment);
      if (payment.payment_url) openUrl(payment.payment_url);
      startPolling();
    } catch (error) {
      if (error.status === 409) state.intent = null;
      setMessage(error.message || "Не удалось открыть оплату.", "error");
    } finally {
      state.busy = false;
      sync();
    }
  }

  function rewriteNeutralHistoryLabels() {
    const nodes = walletView.querySelectorAll(".payment-history-copy strong,.payment-status-copy small,.payment-status-meta strong");
    nodes.forEach((node) => {
      const text = node.textContent || "";
      if (text === "card") node.textContent = LABEL;
      else if (text.startsWith("card ·")) node.textContent = `${LABEL}${text.slice(4)}`;
    });
  }

  currency.addEventListener("change", () => {
    state.currency = currency.value;
    state.intent = null;
    renderPackages();
  });
  email.addEventListener("input", () => {
    const next = email.value;
    if (state.email !== next) state.intent = null;
    state.email = next;
    sync();
  });
  pay.addEventListener("click", () => {
    tg?.HapticFeedback?.impactOccurred?.("medium");
    void checkout();
  });
  refresh.addEventListener("click", () => {
    tg?.HapticFeedback?.impactOccurred?.("light");
    void reconcile(true);
  });

  const walletObserver = new MutationObserver(() => {
    if (!walletView.hidden) {
      void loadPackages();
      rewriteNeutralHistoryLabels();
    } else {
      clearTimeout(state.pollTimer);
    }
  });
  walletObserver.observe(walletView, { attributes: true, subtree: true, childList: true, attributeFilter: ["hidden"] });
  tg?.onEvent?.("activated", () => { if (!walletView.hidden) void loadPackages(); });
  window.addEventListener("online", () => { if (!walletView.hidden) void loadPackages(); });

  void loadPackages();
  sync();
})();
