(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const profileView = document.getElementById("profileView");
  const mount = document.getElementById("partnerPreview");
  if (!profileView || !mount) return;

  const state = {
    loaded: false,
    loading: false,
    stats: null,
    invitations: [],
    rewards: [],
    withdrawals: [],
    transfers: [],
    activeTab: "rewards",
    withdrawSubmitting: false,
    transferSubmitting: false,
  };

  function ensureStyles() {
    if (document.querySelector('link[href="/mini-app/partner.css"]')) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/mini-app/partner.css";
    document.head.appendChild(link);
  }

  function authHeaders(extra = {}) {
    const headers = { Accept: "application/json", ...extra };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      headers: authHeaders(options.headers || {}),
    });
    let payload = null;
    try { payload = await response.json(); } catch (_error) { payload = null; }
    if (!response.ok) {
      const error = new Error(typeof payload?.detail === "string" ? payload.detail : `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function number(value, digits = 2) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return "0";
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(parsed);
  }

  function date(value) {
    const parsed = new Date(value || "");
    if (Number.isNaN(parsed.getTime())) return "";
    return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", year: "numeric" }).format(parsed);
  }

  function statusLabel(status) {
    return {
      pending: "Ожидает",
      processing: "В обработке",
      paid: "Выплачено",
      rejected: "Отклонено",
      canceled: "Отменено",
      available: "Доступно",
      reversed: "Скорректировано",
    }[status] || status || "—";
  }

  function clear(node) { node.replaceChildren(); }

  function stat(label, value) {
    const card = document.createElement("div");
    card.className = "partner-stat";
    const caption = document.createElement("span");
    caption.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value;
    card.append(caption, strong);
    return card;
  }

  function button(text, onClick, className = "") {
    const item = document.createElement("button");
    item.type = "button";
    item.textContent = text;
    if (className) item.className = className;
    item.addEventListener("click", onClick);
    return item;
  }

  async function copyText(text) {
    if (!text) return false;
    try {
      await navigator.clipboard.writeText(text);
      tg?.HapticFeedback?.notificationOccurred?.("success");
      return true;
    } catch (_error) {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (_copyError) { ok = false; }
      area.remove();
      return ok;
    }
  }

  function referralText() {
    return state.stats?.referral_link || state.stats?.referral_payload || "";
  }

  function shareReferral() {
    const link = state.stats?.referral_link;
    if (!link) {
      void copyText(referralText());
      return;
    }
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent("Присоединяйся к ROXY · AI Creative Studio")}`;
    if (tg?.openTelegramLink) tg.openTelegramLink(shareUrl);
    else window.open(shareUrl, "_blank", "noopener,noreferrer");
  }

  function openPartnerChat() {
    const url = state.stats?.partner_chat_url;
    if (!url) return;
    if (tg?.openTelegramLink) tg.openTelegramLink(url);
    else window.open(url, "_blank", "noopener,noreferrer");
  }

  function render() {
    clear(mount);
    mount.className = "partner-preview shell-panel partner-cabinet";

    if (!tg?.initData) {
      const empty = document.createElement("div");
      empty.className = "partner-empty";
      empty.textContent = "Партнёрский кабинет доступен при открытии Mini App через Telegram.";
      mount.appendChild(empty);
      return;
    }
    if (!state.stats) {
      const empty = document.createElement("div");
      empty.className = "partner-empty";
      empty.textContent = "Не удалось загрузить партнёрский кабинет.";
      mount.append(empty, button("Повторить", load));
      return;
    }

    const summary = document.createElement("div");
    summary.className = "partner-summary-grid";
    summary.append(
      stat("Доступно", `${number(state.stats.partner_balance_rub ?? state.stats.available)} ₽`),
      stat("Всего заработано", `${number(state.stats.total_earned)} ₽`),
      stat("Переведено в ROX", `${number(state.stats.transferred_to_rox)} ₽`),
      stat("На выводе", `${number(state.stats.pending_withdrawals)} ₽`),
      stat("1-я линия", `${state.stats.first_line} · ${number(state.stats.first_line_percent)}%`),
      stat("2-я линия", `${state.stats.second_line} · ${number(state.stats.second_line_percent)}%`),
    );

    const referral = document.createElement("div");
    referral.className = "partner-link";
    const title = document.createElement("strong");
    title.textContent = "Ваша реферальная ссылка";
    const code = document.createElement("code");
    code.textContent = referralText() || "Укажите BOT_USERNAME на сервере, чтобы сформировать ссылку";
    const actions = document.createElement("div");
    actions.className = "partner-actions";
    actions.append(
      button("Скопировать", async () => {
        const ok = await copyText(referralText());
        showMessage(ok ? "Ссылка скопирована" : "Не удалось скопировать", ok ? "ok" : "error");
      }),
      button("Пригласить", shareReferral, "primary"),
    );
    if (state.stats.partner_chat_url) {
      actions.appendChild(button("Партнёры ROXY", openPartnerChat));
    }
    referral.append(title, code, actions);

    const tabs = document.createElement("div");
    tabs.className = "partner-tabs";
    tabs.setAttribute("role", "tablist");
    [
      ["rewards", "Начисления"],
      ["invitations", "Партнёры"],
      ["money", "Деньги"],
    ].forEach(([key, label]) => {
      const tab = button(label, () => {
        state.activeTab = key;
        render();
      });
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", state.activeTab === key ? "true" : "false");
      tabs.appendChild(tab);
    });

    const panel = document.createElement("div");
    panel.className = "partner-panel";
    panel.setAttribute("role", "tabpanel");
    if (state.activeTab === "invitations") renderInvitations(panel);
    else if (state.activeTab === "money") renderMoney(panel);
    else renderRewards(panel);

    const message = document.createElement("div");
    message.id = "partnerMessage";
    message.className = "partner-validation";
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");

    mount.append(summary, referral, tabs, panel, message);
  }

  function sectionHeading(title, note = "") {
    const head = document.createElement("div");
    head.className = "partner-section-title";
    const h3 = document.createElement("h3");
    h3.textContent = title;
    const small = document.createElement("span");
    small.textContent = note;
    head.append(h3, small);
    return head;
  }

  function renderRewards(panel) {
    panel.appendChild(sectionHeading("Начисления в ₽", "только с реальных пополнений 1-й и 2-й линии"));
    const list = document.createElement("div");
    list.className = "partner-list";
    if (!state.rewards.length) {
      list.innerHTML = '<div class="partner-empty">Начислений пока нет.</div>';
    } else {
      state.rewards.slice(0, 30).forEach((reward) => {
        const row = document.createElement("div");
        row.className = "partner-row";
        const copy = document.createElement("div");
        copy.className = "partner-row-copy";
        const source = document.createElement("strong");
        source.textContent = reward.source_user?.username
          ? `@${reward.source_user.username}`
          : reward.source_user?.first_name || "Партнёр";
        const meta = document.createElement("small");
        meta.textContent = `${reward.line}-я линия · ${number(reward.percent)}% · ${date(reward.created_at)}`;
        copy.append(source, meta);
        const value = document.createElement("div");
        value.className = "partner-row-value";
        const amount = document.createElement("strong");
        amount.textContent = `+${number(reward.net_amount)} ₽`;
        const status = document.createElement("small");
        status.textContent = statusLabel(reward.status);
        value.append(amount, status);
        row.append(copy, value);
        list.appendChild(row);
      });
    }
    panel.appendChild(list);
  }

  function renderInvitations(panel) {
    panel.appendChild(sectionHeading("Партнёры", `${state.stats.first_line} + ${state.stats.second_line}`));
    const list = document.createElement("div");
    list.className = "partner-list";
    if (!state.invitations.length) {
      list.innerHTML = '<div class="partner-empty">Пока никто не зарегистрировался по вашей ссылке.</div>';
    } else {
      state.invitations.slice(0, 50).forEach((invite) => {
        const row = document.createElement("div");
        row.className = "partner-row";
        const copy = document.createElement("div");
        copy.className = "partner-row-copy";
        const name = document.createElement("strong");
        name.textContent = invite.username ? `@${invite.username}` : invite.first_name || "Пользователь";
        const joined = document.createElement("small");
        joined.textContent = `Регистрация ${date(invite.joined_at)}`;
        copy.append(name, joined);
        const badge = document.createElement("span");
        badge.className = "partner-line-badge";
        badge.textContent = `${invite.line}-я линия`;
        row.append(copy, badge);
        list.appendChild(row);
      });
    }
    panel.appendChild(list);
  }

  function renderTransferForm(panel) {
    const available = Number(state.stats.partner_balance_rub ?? state.stats.available ?? 0);
    panel.appendChild(sectionHeading("Перевести в ROX", "1 ₽ заработка = 1 ROX на баланс"));
    const form = document.createElement("form");
    form.className = "partner-withdrawal-form partner-transfer-form";
    form.noValidate = true;
    const amountLabel = document.createElement("label");
    amountLabel.textContent = "Сумма из заработка, ₽";
    const amount = document.createElement("input");
    amount.type = "number";
    amount.inputMode = "decimal";
    amount.min = "0.01";
    amount.step = "0.01";
    amount.max = String(available);
    amount.placeholder = `Доступно ${number(available)} ₽`;
    amountLabel.appendChild(amount);
    const preview = document.createElement("div");
    preview.className = "partner-validation";
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.className = "primary";
    submit.textContent = "Перевести в ROX";

    const validate = () => {
      const value = Number(amount.value);
      let error = "";
      if (!Number.isFinite(value) || value <= 0) error = "Введите сумму перевода.";
      else if (value > available) error = "Сумма больше доступного заработка.";
      preview.textContent = error || `На баланс поступит ${number(value)} ROX`;
      preview.classList.toggle("error", Boolean(error));
      submit.disabled = Boolean(error) || state.transferSubmitting;
      return !error;
    };
    amount.addEventListener("input", validate);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!validate() || state.transferSubmitting) return;
      state.transferSubmitting = true;
      submit.disabled = true;
      submit.textContent = "Переводим…";
      const idempotencyKey = globalThis.crypto?.randomUUID?.()
        || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      try {
        await api("/api/v1/referrals/wallet-transfers", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ amount: amount.value, idempotency_key: idempotencyKey }),
        });
        tg?.HapticFeedback?.notificationOccurred?.("success");
        await load(true);
        state.activeTab = "money";
        render();
        showMessage("Заработок переведён на баланс ROX.", "ok");
      } catch (error) {
        preview.textContent = error.message || "Не удалось перевести заработок в ROX.";
        preview.classList.add("error");
      } finally {
        state.transferSubmitting = false;
        submit.textContent = "Перевести в ROX";
        validate();
      }
    });
    form.append(amountLabel, preview, submit);
    validate();
    panel.appendChild(form);
  }

  function renderPayoutForm(panel) {
    const minimum = Number(state.stats.minimum_withdrawal || 0);
    const available = Number(state.stats.partner_balance_rub ?? state.stats.available ?? 0);
    panel.appendChild(sectionHeading("Вывести деньгами", minimum > 0 ? `на карту / по реквизитам · минимум ${number(minimum)} ₽` : "на карту / по реквизитам"));

    const form = document.createElement("form");
    form.className = "partner-withdrawal-form";
    form.noValidate = true;
    const amountLabel = document.createElement("label");
    amountLabel.textContent = "Сумма, ₽";
    const amount = document.createElement("input");
    amount.type = "number";
    amount.inputMode = "decimal";
    amount.min = minimum > 0 ? String(minimum) : "0.01";
    amount.step = "0.01";
    amount.max = String(available);
    amount.placeholder = `Доступно ${number(available)} ₽`;
    amountLabel.appendChild(amount);
    const requisitesLabel = document.createElement("label");
    requisitesLabel.textContent = "Куда вывести";
    const requisites = document.createElement("textarea");
    requisites.maxLength = 1000;
    requisites.placeholder = "Карта, СБП или другие реквизиты для выплаты";
    requisitesLabel.appendChild(requisites);
    const validation = document.createElement("div");
    validation.className = "partner-validation";
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.className = "primary";
    submit.textContent = "Оформить вывод";

    const validate = () => {
      const value = Number(amount.value);
      let error = "";
      if (!Number.isFinite(value) || value <= 0) error = "Введите сумму вывода.";
      else if (minimum > 0 && value < minimum) error = `Минимальная сумма — ${number(minimum)} ₽.`;
      else if (value > available) error = "Сумма больше доступного заработка.";
      else if (requisites.value.trim().length < 3) error = "Укажите реквизиты для выплаты.";
      validation.textContent = error;
      validation.classList.toggle("error", Boolean(error));
      submit.disabled = Boolean(error) || state.withdrawSubmitting;
      return !error;
    };
    amount.addEventListener("input", validate);
    requisites.addEventListener("input", validate);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!validate() || state.withdrawSubmitting) return;
      state.withdrawSubmitting = true;
      submit.disabled = true;
      submit.textContent = "Отправляем…";
      try {
        await api("/api/v1/referrals/withdrawals", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ amount: amount.value, requisites: requisites.value.trim() }),
        });
        tg?.HapticFeedback?.notificationOccurred?.("success");
        await load(true);
        state.activeTab = "money";
        render();
        showMessage("Заявка на выплату создана. Сумма зарезервирована.", "ok");
      } catch (error) {
        validation.textContent = error.message || "Не удалось создать заявку.";
        validation.classList.add("error");
      } finally {
        state.withdrawSubmitting = false;
        submit.textContent = "Оформить вывод";
        validate();
      }
    });
    form.append(amountLabel, requisitesLabel, validation, submit);
    validate();
    panel.appendChild(form);
  }

  function renderMoneyHistory(panel) {
    if (state.transfers.length) {
      panel.appendChild(sectionHeading("Переводы в ROX"));
      const transfers = document.createElement("div");
      transfers.className = "partner-list";
      state.transfers.slice(0, 15).forEach((transfer) => {
        const row = document.createElement("div");
        row.className = "partner-row";
        const copy = document.createElement("div");
        copy.className = "partner-row-copy";
        copy.append(
          Object.assign(document.createElement("strong"), { textContent: `${number(transfer.amount_rub)} ₽ → ${number(transfer.rox_amount)} ROX` }),
          Object.assign(document.createElement("small"), { textContent: date(transfer.created_at) }),
        );
        row.appendChild(copy);
        transfers.appendChild(row);
      });
      panel.appendChild(transfers);
    }

    panel.appendChild(sectionHeading("Заявки на выплату"));
    const list = document.createElement("div");
    list.className = "partner-list";
    if (!state.withdrawals.length) {
      list.innerHTML = '<div class="partner-empty">Заявок на выплату пока нет.</div>';
    } else {
      state.withdrawals.slice(0, 30).forEach((withdrawal) => {
        const row = document.createElement("div");
        row.className = "partner-row";
        const copy = document.createElement("div");
        copy.className = "partner-row-copy";
        const amountText = document.createElement("strong");
        amountText.textContent = `${number(withdrawal.amount)} ₽`;
        const meta = document.createElement("small");
        meta.textContent = `${statusLabel(withdrawal.status)} · ${date(withdrawal.created_at)}`;
        copy.append(amountText, meta);
        if (withdrawal.can_cancel) {
          const cancel = button("Отменить", async () => {
            cancel.disabled = true;
            try {
              await api(`/api/v1/referrals/withdrawals/${encodeURIComponent(withdrawal.id)}/cancel`, { method: "POST" });
              await load(true);
              state.activeTab = "money";
              render();
              showMessage("Заявка отменена, сумма снова доступна.", "ok");
            } catch (error) {
              showMessage(error.message || "Не удалось отменить заявку.", "error");
              cancel.disabled = false;
            }
          });
          row.append(copy, cancel);
        } else {
          const badge = document.createElement("span");
          badge.className = "partner-status";
          badge.textContent = statusLabel(withdrawal.status);
          row.append(copy, badge);
        }
        list.appendChild(row);
      });
    }
    panel.appendChild(list);
  }

  function renderMoney(panel) {
    renderTransferForm(panel);
    renderPayoutForm(panel);
    renderMoneyHistory(panel);
  }

  function showMessage(text, kind = "") {
    const node = document.getElementById("partnerMessage");
    if (!node) return;
    node.textContent = text;
    node.className = `partner-validation ${kind}`.trim();
  }

  async function load(force = false) {
    if (!tg?.initData || state.loading || (state.loaded && !force)) {
      if (!state.loaded) render();
      return;
    }
    state.loading = true;
    try {
      const [stats, invitations, rewards, withdrawals, transfers] = await Promise.all([
        api("/api/v1/referrals/stats"),
        api("/api/v1/referrals/invitations?limit=50"),
        api("/api/v1/referrals/rewards?limit=50"),
        api("/api/v1/referrals/withdrawals?limit=50"),
        api("/api/v1/referrals/wallet-transfers?limit=30"),
      ]);
      state.stats = stats;
      state.invitations = invitations?.items || [];
      state.rewards = rewards?.items || [];
      state.withdrawals = withdrawals?.items || [];
      state.transfers = transfers?.items || [];
      state.loaded = true;
    } catch (_error) {
      if (!state.loaded) state.stats = null;
    } finally {
      state.loading = false;
      render();
    }
  }

  const observer = new MutationObserver(() => {
    if (!profileView.hidden) void load(true);
  });
  observer.observe(profileView, { attributes: true, attributeFilter: ["hidden"] });
  tg?.onEvent?.("activated", () => { if (!profileView.hidden) void load(true); });
  window.addEventListener("online", () => { if (!profileView.hidden) void load(true); });

  ensureStyles();
  if (!profileView.hidden) void load();
})();