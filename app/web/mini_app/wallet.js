(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const NONTERMINAL = new Set(["creating", "creation_unknown", "pending"]);
  const SUCCESS = new Set(["succeeded"]);
  const FAILED = new Set(["failed", "canceled", "expired"]);
  const state = {
    packages: [],
    internalCreditRub: null,
    selectedPackageId: null,
    selectedProvider: "cryptobot",
    checkoutIntent: null,
    checkoutBusy: false,
    retryBlockedUntil: 0,
    payments: [],
    currentPayment: null,
    pollTimer: null,
    lastTerminalId: null,
  };

  const dom = {
    walletView: document.getElementById("walletView"),
    walletBalance: document.getElementById("walletBalance"),
    balanceValue: document.getElementById("balanceValue"),
    transactionList: document.getElementById("transactionList"),
    packageGrid: document.getElementById("paymentPackageGrid"),
    rateLabel: document.getElementById("paymentRateLabel"),
    providerGrid: document.getElementById("paymentProviderGrid"),
    selectionSummary: document.getElementById("paymentSelectionSummary"),
    checkoutMessage: document.getElementById("paymentCheckoutMessage"),
    checkoutButton: document.getElementById("paymentCheckoutButton"),
    statusSection: document.getElementById("paymentStatusSection"),
    statusCard: document.getElementById("paymentStatusCard"),
    historyList: document.getElementById("paymentHistoryList"),
  };

  if (!dom.walletView || !dom.packageGrid || !dom.checkoutButton) return;

  function ensureWalletStyles() {
    if (document.querySelector('link[href="/mini-app/wallet.css"]')) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/mini-app/wallet.css";
    document.head.appendChild(link);
  }

  function authHeaders(extra = {}) {
    const headers = { Accept: "application/json", ...extra };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function apiRequest(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      headers: authHeaders(options.headers || {}),
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }
    if (!response.ok) {
      const error = new Error(
        typeof payload?.detail === "string" ? payload.detail : `HTTP ${response.status}`,
      );
      error.status = response.status;
      error.retryAfter = Number(
        response.headers.get("Retry-After") || payload?.retry_after || 0,
      );
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  function formatNumber(value, digits = 2) {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value ?? "—");
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(number);
  }

  function formatDate(value) {
    const date = new Date(value || "");
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function providerLabel(provider) {
    return {
      cryptobot: "Crypto Pay",
      tbank: "Т-Банк",
      yookassa: "ЮKassa",
    }[provider] || provider || "Провайдер";
  }

  function paymentStatusLabel(status) {
    return {
      creating: "Создаём",
      creation_unknown: "Проверяем",
      pending: "Ожидает оплаты",
      succeeded: "Оплачено",
      partially_refunded: "Частичный возврат",
      refunded: "Возвращено",
      refund_review: "Проверка возврата",
      canceled: "Отменено",
      expired: "Истекло",
      failed: "Ошибка",
    }[status] || status || "—";
  }

  function paymentStatusClass(status) {
    if (NONTERMINAL.has(status)) return "pending";
    if (SUCCESS.has(status)) return "success";
    if (FAILED.has(status)) return "failed";
    return "";
  }

  function clear(node) {
    node?.replaceChildren();
  }

  function haptic(kind = "light") {
    tg?.HapticFeedback?.impactOccurred?.(kind);
  }

  function notify(kind) {
    tg?.HapticFeedback?.notificationOccurred?.(kind);
  }

  function uuid() {
    if (crypto?.randomUUID) return crypto.randomUUID();
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map((item) => item.toString(16).padStart(2, "0"));
    return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
  }

  function selectedPackage() {
    return state.packages.find((item) => item.id === state.selectedPackageId) || null;
  }

  function walletVisible() {
    return !dom.walletView.hidden;
  }

  function setMessage(message = "", type = "") {
    dom.checkoutMessage.textContent = message;
    dom.checkoutMessage.classList.toggle("error", type === "error");
    dom.checkoutMessage.classList.toggle("ok", type === "ok");
  }

  function syncCheckoutButton() {
    const blocked = Date.now() < state.retryBlockedUntil;
    const pkg = selectedPackage();
    dom.checkoutButton.disabled = !pkg || state.checkoutBusy || blocked || !tg?.initData;
    dom.checkoutButton.setAttribute("aria-busy", state.checkoutBusy ? "true" : "false");
    dom.checkoutButton.textContent = state.checkoutBusy
      ? "Создаём платёж…"
      : blocked
        ? "Повторите чуть позже"
        : "Перейти к оплате";
    dom.selectionSummary.textContent = pkg
      ? `${formatNumber(pkg.credits)} кр. · ${formatNumber(pkg.amount)} ${pkg.currency === "RUB" ? "₽" : pkg.currency}`
      : "Сначала выберите пакет";
  }

  function selectPackage(packageId) {
    if (state.selectedPackageId !== packageId) state.checkoutIntent = null;
    state.selectedPackageId = packageId;
    document.querySelectorAll(".payment-package").forEach((button) => {
      const selected = button.dataset.packageId === packageId;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-checked", selected ? "true" : "false");
    });
    setMessage();
    syncCheckoutButton();
  }

  function selectProvider(provider) {
    if (state.selectedProvider !== provider) state.checkoutIntent = null;
    state.selectedProvider = provider;
    document.querySelectorAll("[data-payment-provider]").forEach((button) => {
      const selected = button.dataset.paymentProvider === provider;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-checked", selected ? "true" : "false");
    });
    setMessage();
    syncCheckoutButton();
  }

  async function loadPackages() {
    try {
      const payload = await apiRequest("/api/v1/payments/packages");
      state.internalCreditRub = payload?.internal_credit_rub ?? null;
      state.packages = Object.entries(payload?.packages || {})
        .map(([id, item]) => ({ id, ...item }))
        .sort((a, b) => Number(a.amount) - Number(b.amount));
      renderPackages();
    } catch (_error) {
      clear(dom.packageGrid);
      const error = document.createElement("div");
      error.className = "shell-error";
      error.textContent = "Не удалось загрузить пакеты пополнения.";
      dom.packageGrid.appendChild(error);
      dom.rateLabel.textContent = "";
    }
  }

  function renderPackages() {
    clear(dom.packageGrid);
    dom.rateLabel.textContent = state.internalCreditRub
      ? `1 кр. = ${formatNumber(state.internalCreditRub)} ₽`
      : "";
    if (!state.packages.length) {
      const empty = document.createElement("div");
      empty.className = "shell-empty";
      empty.textContent = "Пакеты пополнения пока не настроены.";
      dom.packageGrid.appendChild(empty);
      state.selectedPackageId = null;
      syncCheckoutButton();
      return;
    }

    if (!state.packages.some((item) => item.id === state.selectedPackageId)) {
      state.selectedPackageId = state.packages[0].id;
    }
    state.packages.forEach((pkg) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "payment-package";
      button.dataset.packageId = pkg.id;
      button.setAttribute("role", "radio");
      button.setAttribute("aria-checked", pkg.id === state.selectedPackageId ? "true" : "false");
      if (pkg.id === state.selectedPackageId) button.classList.add("is-selected");

      const check = document.createElement("span");
      check.className = "payment-package-check";
      check.textContent = "✓";
      check.setAttribute("aria-hidden", "true");
      const credits = document.createElement("strong");
      credits.textContent = `${formatNumber(pkg.credits)} кр.`;
      const packageId = document.createElement("span");
      packageId.textContent = pkg.id;
      const amount = document.createElement("b");
      amount.textContent = `${formatNumber(pkg.amount)} ${pkg.currency === "RUB" ? "₽" : pkg.currency}`;
      button.append(check, credits, packageId, amount);
      button.addEventListener("click", () => {
        haptic();
        selectPackage(pkg.id);
      });
      dom.packageGrid.appendChild(button);
    });
    syncCheckoutButton();
  }

  function getOrCreateIntent() {
    const pkg = selectedPackage();
    if (!pkg) return null;
    if (
      state.checkoutIntent
      && state.checkoutIntent.packageId === pkg.id
      && state.checkoutIntent.provider === state.selectedProvider
    ) {
      return state.checkoutIntent;
    }
    state.checkoutIntent = {
      key: uuid(),
      packageId: pkg.id,
      provider: state.selectedProvider,
    };
    return state.checkoutIntent;
  }

  async function checkout() {
    if (state.checkoutBusy || Date.now() < state.retryBlockedUntil || !tg?.initData) return;
    const intent = getOrCreateIntent();
    if (!intent) return;
    state.checkoutBusy = true;
    syncCheckoutButton();
    setMessage("Создаём один платёжный intent. Повторный тап новый счёт не создаст.");

    try {
      const payment = await apiRequest("/api/v1/payments", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": intent.key,
        },
        body: JSON.stringify({
          provider: intent.provider,
          package_id: intent.packageId,
        }),
      });
      state.currentPayment = payment;
      upsertPayment(payment);
      renderPaymentStatus(payment);
      renderPaymentHistory();
      setMessage(
        payment.payment_url
          ? "Платёж создан. После оплаты вернитесь в Ксю — статус обновится автоматически."
          : "Платёж создан, провайдер ещё уточняет состояние. Новый счёт не создаём.",
        "ok",
      );
      if (payment.payment_url) openPaymentUrl(payment.payment_url);
      startPolling(payment.id);
    } catch (error) {
      if (error.status === 429 && error.retryAfter > 0) {
        state.retryBlockedUntil = Date.now() + error.retryAfter * 1000;
        setMessage(`Слишком много попыток. Повторите через ${error.retryAfter} сек.`, "error");
        setTimeout(syncCheckoutButton, error.retryAfter * 1000 + 100);
      } else if (error.status === 409) {
        state.checkoutIntent = null;
        setMessage("Этот платёжный intent уже использован иначе. Создадим новый при следующей попытке.", "error");
      } else if (error.status === 502) {
        setMessage("Ответ провайдера неопределён. Проверяем существующий платёж — новый не создаём.");
        await refreshPaymentsOnly();
      } else {
        setMessage("Не удалось подтвердить создание платежа. Повторите — будет использован тот же idempotency key.", "error");
      }
    } finally {
      state.checkoutBusy = false;
      syncCheckoutButton();
    }
  }

  function openPaymentUrl(url) {
    if (!url) return;
    try {
      const parsed = new URL(url, window.location.href);
      const telegramHost = ["t.me", "telegram.me", "www.t.me", "www.telegram.me"].includes(parsed.hostname);
      if (telegramHost && tg?.openTelegramLink) {
        tg.openTelegramLink(parsed.href);
        return;
      }
      if (tg?.openLink) {
        tg.openLink(parsed.href);
        return;
      }
      window.open(parsed.href, "_blank", "noopener,noreferrer");
    } catch (_error) {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  }

  async function refreshPaymentsOnly() {
    if (!tg?.initData) return;
    try {
      const payload = await apiRequest("/api/v1/payments?limit=12");
      state.payments = Array.isArray(payload?.items) ? payload.items : [];
      const active = state.payments.find((payment) => NONTERMINAL.has(payment.status));
      if (active) {
        state.currentPayment = active;
        renderPaymentStatus(active);
        startPolling(active.id);
      } else if (state.currentPayment && !NONTERMINAL.has(state.currentPayment.status)) {
        renderPaymentStatus(state.currentPayment);
      } else {
        state.currentPayment = null;
        dom.statusSection.hidden = true;
        stopPolling();
      }
      renderPaymentHistory();
    } catch (_error) {
      // Keep already rendered server state on transient refresh failures.
    }
  }

  function upsertPayment(payment) {
    const index = state.payments.findIndex((item) => item.id === payment.id);
    if (index === -1) state.payments.unshift(payment);
    else state.payments[index] = payment;
    state.payments = state.payments.slice(0, 12);
  }

  function renderPaymentStatus(payment) {
    if (!payment) {
      dom.statusSection.hidden = true;
      clear(dom.statusCard);
      return;
    }
    dom.statusSection.hidden = false;
    clear(dom.statusCard);

    const top = document.createElement("div");
    top.className = "payment-status-top";
    const copy = document.createElement("div");
    copy.className = "payment-status-copy";
    const title = document.createElement("strong");
    title.textContent = `${formatNumber(payment.credits)} кр. · ${formatNumber(payment.amount)} ${payment.currency === "RUB" ? "₽" : payment.currency}`;
    const provider = document.createElement("small");
    provider.textContent = `${providerLabel(payment.provider)} · ${formatDate(payment.created_at)}`;
    copy.append(title, provider);
    const badge = document.createElement("span");
    badge.className = `payment-status-badge ${paymentStatusClass(payment.status)}`.trim();
    badge.textContent = paymentStatusLabel(payment.status);
    top.append(copy, badge);

    const meta = document.createElement("div");
    meta.className = "payment-status-meta";
    meta.append(
      statusMeta("Пакет", payment.package_id || "—"),
      statusMeta("Провайдер", providerLabel(payment.provider)),
    );

    const actions = document.createElement("div");
    actions.className = "payment-status-actions";
    if (payment.payment_url && NONTERMINAL.has(payment.status)) {
      const reopen = document.createElement("button");
      reopen.type = "button";
      reopen.className = "primary";
      reopen.textContent = "Открыть оплату";
      reopen.addEventListener("click", () => {
        haptic();
        openPaymentUrl(payment.payment_url);
      });
      actions.appendChild(reopen);
    }
    const refresh = document.createElement("button");
    refresh.type = "button";
    refresh.textContent = "Обновить статус";
    refresh.addEventListener("click", async () => {
      haptic();
      await refreshPayment(payment.id, true);
    });
    actions.appendChild(refresh);

    dom.statusCard.append(top, meta, actions);
  }

  function statusMeta(labelText, valueText) {
    const item = document.createElement("div");
    const label = document.createElement("span");
    label.textContent = labelText;
    const value = document.createElement("strong");
    value.textContent = valueText;
    item.append(label, value);
    return item;
  }

  async function refreshPayment(paymentId, userInitiated = false) {
    try {
      const payment = await apiRequest(`/api/v1/payments/${encodeURIComponent(paymentId)}`);
      const previous = state.currentPayment?.status;
      state.currentPayment = payment;
      upsertPayment(payment);
      renderPaymentStatus(payment);
      renderPaymentHistory();

      if (!NONTERMINAL.has(payment.status)) {
        stopPolling();
        state.checkoutIntent = null;
        if (payment.id !== state.lastTerminalId) {
          state.lastTerminalId = payment.id;
          if (SUCCESS.has(payment.status)) {
            notify("success");
            setMessage("Оплата подтверждена. Баланс обновлён.", "ok");
            await refreshFinancialData();
          } else if (FAILED.has(payment.status)) {
            notify("error");
            setMessage(`Платёж: ${paymentStatusLabel(payment.status).toLowerCase()}. Можно создать новый intent.`, "error");
          }
        }
      } else if (userInitiated && previous === payment.status) {
        setMessage("Провайдер ещё не подтвердил новый статус. Продолжаем проверять.");
      }
      return payment;
    } catch (_error) {
      if (userInitiated) setMessage("Не удалось обновить статус. Попробуйте ещё раз.", "error");
      return null;
    }
  }

  function startPolling(paymentId) {
    stopPolling();
    if (!paymentId || !walletVisible()) return;
    const tick = async () => {
      if (!walletVisible() || state.currentPayment?.id !== paymentId) return;
      const payment = await refreshPayment(paymentId, false);
      if (payment && NONTERMINAL.has(payment.status)) {
        state.pollTimer = setTimeout(tick, 3000);
      }
    };
    state.pollTimer = setTimeout(tick, 2200);
  }

  function stopPolling() {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }

  function renderPaymentHistory() {
    clear(dom.historyList);
    if (!state.payments.length) {
      const empty = document.createElement("div");
      empty.className = "shell-empty";
      empty.textContent = "Пополнений пока нет.";
      dom.historyList.appendChild(empty);
      return;
    }
    state.payments.slice(0, 8).forEach((payment) => {
      const row = document.createElement("div");
      row.className = "payment-history-row";
      const copy = document.createElement("div");
      copy.className = "payment-history-copy";
      const title = document.createElement("strong");
      title.textContent = `${providerLabel(payment.provider)} · ${payment.package_id || "пакет"}`;
      const date = document.createElement("small");
      date.textContent = formatDate(payment.created_at);
      copy.append(title, date);
      const value = document.createElement("div");
      value.className = "payment-history-value";
      const amount = document.createElement("strong");
      amount.textContent = `${formatNumber(payment.amount)} ${payment.currency === "RUB" ? "₽" : payment.currency}`;
      const status = document.createElement("small");
      status.className = paymentStatusClass(payment.status);
      status.textContent = paymentStatusLabel(payment.status);
      value.append(amount, status);
      row.append(copy, value);
      dom.historyList.appendChild(row);
    });
  }

  async function refreshFinancialData() {
    if (!tg?.initData) return;
    try {
      const [me, transactions] = await Promise.all([
        apiRequest("/api/v1/me"),
        apiRequest("/api/v1/me/transactions"),
      ]);
      const balance = `${formatNumber(me.balance_rox)} кр.`;
      dom.walletBalance.textContent = balance;
      if (dom.balanceValue) dom.balanceValue.textContent = balance;
      renderTransactions(Array.isArray(transactions) ? transactions : []);
    } catch (_error) {
      // Shell's next activated/navigation refresh will recover authoritative values.
    }
  }

  function renderTransactions(rows) {
    if (!dom.transactionList) return;
    clear(dom.transactionList);
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "shell-empty";
      empty.textContent = "Операций пока нет.";
      dom.transactionList.appendChild(empty);
      return;
    }
    rows.slice(0, 20).forEach((tx) => {
      const row = document.createElement("div");
      row.className = "transaction-row";
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = transactionLabel(tx.kind);
      const date = document.createElement("small");
      date.textContent = formatDate(tx.created_at);
      copy.append(title, date);
      const amount = document.createElement("div");
      const numeric = Number(tx.amount);
      amount.className = `transaction-amount ${numeric >= 0 ? "positive" : "negative"}`;
      amount.textContent = `${numeric > 0 ? "+" : ""}${formatNumber(tx.amount)} кр.`;
      row.append(copy, amount);
      dom.transactionList.appendChild(row);
    });
  }

  function transactionLabel(kind) {
    return {
      generation: "Генерация",
      generation_debit: "Генерация",
      generation_refund: "Возврат за генерацию",
      payment: "Пополнение",
      payment_credit: "Пополнение",
      promo: "Промокод",
      referral: "Партнёрское начисление",
      adjustment: "Корректировка",
    }[kind] || String(kind || "Операция").replaceAll("_", " ");
  }

  async function loadWalletPayments() {
    if (!walletVisible()) return;
    if (!tg?.initData) {
      clear(dom.historyList);
      const empty = document.createElement("div");
      empty.className = "shell-empty";
      empty.textContent = "Оплата доступна при открытии Mini App через Telegram.";
      dom.historyList.appendChild(empty);
      syncCheckoutButton();
      return;
    }
    await Promise.allSettled([loadPackages(), refreshFinancialData(), refreshPaymentsOnly()]);
  }

  function bind() {
    dom.providerGrid?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-payment-provider]");
      if (!button) return;
      haptic();
      selectProvider(button.dataset.paymentProvider);
    });
    dom.checkoutButton.addEventListener("click", () => {
      haptic("medium");
      checkout();
    });

    document.addEventListener("click", (event) => {
      const walletNav = event.target.closest('[data-shell-nav="wallet"]');
      if (walletNav) setTimeout(loadWalletPayments, 0);
    });

    const observer = new MutationObserver(() => {
      if (walletVisible()) loadWalletPayments();
      else stopPolling();
    });
    observer.observe(dom.walletView, { attributes: true, attributeFilter: ["hidden"] });

    tg?.onEvent?.("activated", () => {
      if (walletVisible()) loadWalletPayments();
    });
    window.addEventListener("online", () => {
      if (walletVisible()) loadWalletPayments();
    });
  }

  ensureWalletStyles();
  bind();
  syncCheckoutButton();
})();
