(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    overview: null,
    economy: null,
    creator: null,
    loading: false,
    creatorSubmitting: false,
    mounted: false,
    observer: null,
  };
  const dom = {};

  function authHeaders(json = false) {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    if (json) headers["Content-Type"] = "application/json";
    return headers;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { ...authHeaders(options.body !== undefined), ...(options.headers || {}) },
      credentials: "same-origin",
      cache: "no-store",
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
    return payload;
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

  function format(value, digits = 2) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "0";
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(number);
  }

  function dateLabel(value) {
    const parsed = new Date(value || "");
    if (Number.isNaN(parsed.getTime())) return "";
    return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", year: "numeric" }).format(parsed);
  }

  function haptic(kind = "light") {
    try { tg?.HapticFeedback?.impactOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function notify(kind = "success") {
    try { tg?.HapticFeedback?.notificationOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function openRoute(route) {
    haptic(route === "wallet" ? "medium" : "light");
    window.RoxyCustomerNavigation?.open?.(route);
  }

  function scrollTo(id) {
    const node = document.getElementById(id);
    if (!node) return false;
    node.scrollIntoView({ behavior: "smooth", block: "start" });
    return true;
  }

  function quickAction(icon, title, note, handler, primary = false) {
    const card = button("", handler, `roxy-cabinet-action${primary ? " primary" : ""}`);
    card.append(
      el("span", "roxy-cabinet-action-icon", icon),
      el("span", "roxy-cabinet-action-copy"),
      el("span", "roxy-cabinet-action-arrow", "›"),
    );
    const copy = card.querySelector(".roxy-cabinet-action-copy");
    copy.append(el("strong", "", title), el("small", "", note));
    return card;
  }

  function metric(label, value, note = "") {
    const card = el("article", "roxy-cabinet-metric");
    card.append(el("span", "", label), el("strong", "", value));
    if (note) card.appendChild(el("small", "", note));
    return card;
  }

  function build() {
    const root = el("section", "roxy-profile-cabinet");
    root.id = "roxyProfileCabinet";

    const head = el("div", "roxy-cabinet-head");
    const copy = el("div");
    copy.append(
      el("span", "section-kicker", "ROXY Cabinet"),
      el("h2", "", "Всё важное в одном месте"),
      el("p", "", "Баланс ROX, партнёрский заработок, платежи и настройки без путаницы."),
    );
    const refresh = button("↻", () => void load(true), "roxy-cabinet-refresh");
    refresh.setAttribute("aria-label", "Обновить кабинет");
    head.append(copy, refresh);

    const balances = el("div", "roxy-cabinet-balances");
    balances.id = "roxyCabinetBalances";
    balances.append(
      metric("Баланс ROX", "—", "Для генераций внутри ROXY"),
      metric("Заработок партнёра", "—", "Рубли: вывести или перевести в ROX"),
    );

    const actions = el("div", "roxy-cabinet-actions");
    actions.append(
      quickAction("💎", "Мои ROX", "Баланс, пополнение и операции", () => openRoute("wallet"), true),
      quickAction("≡", "История", "Все генерации", () => openRoute("history")),
      quickAction("👥", "Партнёры ROXY", "30% / 5%, заработок и вывод", () => scrollPartner()),
      quickAction("⚙", "Настройки", "Профиль и уведомления", () => scrollSettings()),
    );

    const activity = el("section", "roxy-cabinet-section");
    const activityHead = el("div", "roxy-cabinet-section-head");
    activityHead.append(el("span", "section-kicker", "Активность"), el("h3", "", "Мой ROXY"));
    const metrics = el("div", "roxy-cabinet-metrics");
    metrics.id = "roxyCabinetMetrics";
    activity.append(activityHead, metrics);

    const creator = el("section", "roxy-creator-partnership-card");
    creator.id = "creatorPartnershipEntry";
    creator.setAttribute("aria-live", "polite");

    const message = el("div", "roxy-cabinet-message");
    message.id = "roxyCabinetMessage";
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");

    root.append(head, balances, actions, activity, creator, message);
    return root;
  }

  function mount() {
    if (state.mounted) return;
    const profile = document.getElementById("profileView");
    const profileCard = document.getElementById("profileCard");
    if (!profile || !profileCard) return;
    state.mounted = true;
    document.body?.classList.add("roxy-profile-cabinet-ready");
    const kicker = profile.querySelector(".view-heading .section-kicker");
    if (kicker) kicker.textContent = "Кабинет ROXY";
    dom.root = build();
    profileCard.insertAdjacentElement("afterend", dom.root);
    markReferralProgram();
    renderCreator();
  }

  function markReferralProgram() {
    const heading = document.getElementById("partnerPreviewHeading");
    if (heading) heading.textContent = "Партнёры ROXY";
    const section = document.getElementById("partnerPreview")?.closest(".home-section");
    const kicker = section?.querySelector(".section-kicker");
    if (kicker) kicker.textContent = "Заработок 30% / 5%";
  }

  function paymentSuccessCount(payments) {
    const currencies = payments?.currencies || {};
    return Object.values(currencies).reduce((sum, item) => sum + Number(item?.successful_count || 0), 0);
  }

  function render() {
    const economy = state.economy || {};
    const overview = state.overview || {};
    const balances = document.getElementById("roxyCabinetBalances");
    if (balances) {
      balances.replaceChildren(
        metric("Баланс ROX", `${format(economy.rox_balance ?? economy.bonus_rox)} ROX`, "Бонусы и пополнения уже внутри баланса"),
        metric("Заработок партнёра", `${format(economy.partner_balance_rub ?? economy.available)} ₽`, "Вывести деньгами или перевести в ROX"),
      );
    }

    const generations = overview.generations || {};
    const statuses = generations.statuses || {};
    const active = Number(statuses.queued || 0) + Number(statuses.retry || 0) + Number(statuses.submitting || 0) + Number(statuses.generating || 0);
    const support = overview.support || {};
    const supportStatuses = support.statuses || {};
    const metrics = document.getElementById("roxyCabinetMetrics");
    if (metrics) {
      metrics.replaceChildren(
        metric("Генерации", format(generations.total, 0), `${format(statuses.succeeded || 0, 0)} готово`),
        metric("Пополнения", format(paymentSuccessCount(overview.payments), 0), "Успешных покупок ROX"),
        metric("Партнёры", `${format(economy.first_line || 0, 0)} + ${format(economy.second_line || 0, 0)}`, "1-я + 2-я линия"),
        metric("Сейчас в работе", format(active, 0), "Генераций"),
        metric("Поддержка", format(Number(supportStatuses.open || 0) + Number(supportStatuses.in_progress || 0), 0), "Открытых обращений"),
        metric("Повторы промптов", format(economy.prompt_repeats || 0, 0), "Использований ваших работ"),
      );
    }
    renderCreator();
  }

  function creatorShell(title, body) {
    const copy = el("div", "roxy-creator-partnership-copy");
    copy.append(
      el("span", "section-kicker", "Для авторов и каналов"),
      el("h3", "", title),
      el("p", "", body),
    );
    return copy;
  }

  function formField(label, name, type = "text", placeholder = "") {
    const wrapper = el("label", "roxy-creator-field");
    wrapper.appendChild(el("span", "", label));
    const input = document.createElement(type === "textarea" ? "textarea" : "input");
    input.name = name;
    if (type !== "textarea") input.type = type;
    if (placeholder) input.placeholder = placeholder;
    wrapper.appendChild(input);
    return wrapper;
  }

  function renderCreatorApplicationForm(root, rejected = false) {
    const form = el("form", "roxy-creator-application-form");
    form.id = "creatorPartnershipForm";
    const row = el("div", "roxy-creator-fields-row");
    row.append(
      formField("Название канала / проекта", "channel_name", "text", "Например: ROXY Media"),
      formField("Ссылка", "channel_url", "url", "https://t.me/..."),
    );
    const stats = el("div", "roxy-creator-fields-row");
    stats.append(
      formField("Подписчики", "audience_size", "number", "2000"),
      formField("Средние просмотры", "average_views", "number", "1200"),
    );
    const formatField = formField("Формат сотрудничества", "cooperation_format", "text", "Обзоры, интеграции, контент, амбассадорство"),
      messageField = formField("Комментарий", "message", "textarea", "Расскажите об аудитории и как хотите сотрудничать");
    const submit = button(rejected ? "Подать новую заявку" : "Отправить заявку", () => {}, "roxy-creator-primary");
    submit.type = "submit";
    submit.disabled = state.creatorSubmitting;
    form.append(row, stats, formatField, messageField, submit);
    form.addEventListener("submit", submitCreatorApplication);
    root.appendChild(form);
  }

  function statusBadge(status) {
    const labels = {
      pending: "На рассмотрении",
      approved: "Одобрено",
      rejected: "Отклонено",
      canceled: "Отменено",
      active: "Активно",
      paused: "Приостановлено",
      ended: "Завершено",
    };
    return el("span", `roxy-creator-status ${status || "unknown"}`, labels[status] || status || "—");
  }

  function renderGrantList(grants) {
    const list = el("div", "roxy-creator-grants");
    list.appendChild(el("strong", "", "Начисления по соглашению"));
    if (!Array.isArray(grants) || !grants.length) {
      list.appendChild(el("small", "", "Начислений пока нет."));
      return list;
    }
    grants.slice(0, 6).forEach((grant) => {
      const row = el("div", "roxy-creator-grant-row");
      row.append(el("span", "", grant.period), el("strong", "", `+${format(grant.amount_rox)} ROX`));
      list.appendChild(row);
    });
    return list;
  }

  function renderCreator() {
    const root = document.getElementById("creatorPartnershipEntry");
    if (!root) return;
    root.replaceChildren();
    const creator = state.creator;
    if (!creator) {
      root.appendChild(creatorShell(
        "Creator-партнёрство",
        "Отдельная программа, не реферальные 30% / 5%. Условия рассчитываются индивидуально по каналу, аудитории, просмотрам и формату сотрудничества.",
      ));
      root.appendChild(el("div", "roxy-creator-loading", tg?.initData ? "Загружаю статус…" : "Открой ROXY через Telegram, чтобы подать заявку."));
      return;
    }

    const application = creator.application;
    const agreement = creator.agreement;
    if (agreement) {
      const copy = creatorShell(
        "Creator-партнёрство",
        "Это отдельный договорной контур. Ежемесячные ROX начисляются только по согласованным персональным условиям и не являются реферальным заработком в рублях.",
      );
      const summary = el("div", "roxy-creator-agreement-summary");
      summary.append(
        statusBadge(agreement.status),
        metric("Ежемесячно", `${format(agreement.monthly_rox)} ROX`, "ROX на контент"),
        metric("Начало", agreement.starts_on || "—", agreement.ends_on ? `до ${agreement.ends_on}` : "Без даты окончания"),
        metric("Всего начислено", `${format(creator.total_granted_rox)} ROX`, "По Creator-партнёрству"),
      );
      const terms = el("div", "roxy-creator-terms");
      terms.append(el("strong", "", "Ваши условия"), el("p", "", agreement.terms_summary || "Индивидуальные условия согласованы."));
      root.append(copy, summary, terms, renderGrantList(creator.grants));
      return;
    }

    if (application?.status === "pending") {
      root.append(
        creatorShell("Creator-партнёрство", "Заявка отправлена и сейчас проверяется вручную. Условия не назначаются автоматически — они зависят от вашего канала и формата сотрудничества."),
        statusBadge("pending"),
        metric("Канал", application.channel_name, `${format(application.audience_size, 0)} подписчиков`),
        el("small", "roxy-creator-meta", `Отправлено ${dateLabel(application.created_at)}`),
      );
      return;
    }

    if (application?.status === "rejected") {
      root.append(
        creatorShell("Creator-партнёрство", "Сейчас сотрудничество не подтверждено. Можно скорректировать предложение и отправить новую заявку."),
        statusBadge("rejected"),
      );
      if (application.decision_note) root.appendChild(el("p", "roxy-creator-decision-note", application.decision_note));
      renderCreatorApplicationForm(root, true);
      return;
    }

    root.appendChild(creatorShell(
      "Creator-партнёрство",
      "Расскажите о канале. ROXY не назначает всем одинаковые начисления: условия и ежемесячный ROX-лимит согласуются индивидуально.",
    ));
    renderCreatorApplicationForm(root, false);
  }

  async function submitCreatorApplication(event) {
    event.preventDefault();
    if (state.creatorSubmitting) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const audience = Number(data.get("audience_size"));
    const averageRaw = String(data.get("average_views") || "").trim();
    const payload = {
      channel_name: String(data.get("channel_name") || "").trim(),
      channel_url: String(data.get("channel_url") || "").trim(),
      audience_size: audience,
      average_views: averageRaw ? Number(averageRaw) : null,
      cooperation_format: String(data.get("cooperation_format") || "").trim(),
      message: String(data.get("message") || "").trim(),
    };
    if (!payload.channel_name || !payload.channel_url || !Number.isFinite(audience) || audience < 1 || !payload.cooperation_format) {
      message("Заполни канал, HTTPS-ссылку, аудиторию и формат сотрудничества.", true);
      return;
    }
    state.creatorSubmitting = true;
    renderCreator();
    message("Отправляю заявку…");
    try {
      await api("/api/v1/creator-partnership/applications", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(payload),
      });
      state.creator = await api("/api/v1/creator-partnership");
      renderCreator();
      message("Заявка принята. ROXY уведомит о решении.");
      notify("success");
    } catch (error) {
      message(error.message || "Не удалось отправить заявку.", true);
      notify("error");
    } finally {
      state.creatorSubmitting = false;
      renderCreator();
    }
  }

  function message(text = "", error = false) {
    const node = document.getElementById("roxyCabinetMessage");
    if (!node) return;
    node.textContent = text;
    node.classList.toggle("is-error", error);
  }

  async function load(force = false) {
    const profile = document.getElementById("profileView");
    if (!profile || profile.hidden || !tg?.initData || state.loading) return;
    if (!force && state.overview && state.economy && state.creator) return;
    state.loading = true;
    message("Обновляю кабинет…");
    try {
      const [overview, economy, creator] = await Promise.all([
        api("/api/v1/me/overview"),
        api("/api/v1/referrals/stats"),
        api("/api/v1/creator-partnership"),
      ]);
      state.overview = overview;
      state.economy = economy;
      state.creator = creator;
      render();
      message();
    } catch (error) {
      message(error.message || "Не удалось обновить кабинет.", true);
    } finally {
      state.loading = false;
    }
  }

  function scrollPartner() {
    markReferralProgram();
    if (scrollTo("partnerPreview")) return;
    window.setTimeout(() => scrollTo("partnerPreview"), 100);
  }

  function scrollSettings() {
    if (scrollTo("profileTools")) return;
    window.setTimeout(() => scrollTo("profileTools"), 120);
  }

  function syncVisibility() {
    const profile = document.getElementById("profileView");
    if (!profile || profile.hidden) return;
    mount();
    markReferralProgram();
    void load(false);
  }

  function init() {
    mount();
    syncVisibility();
    const profile = document.getElementById("profileView");
    if (profile && !state.observer) {
      state.observer = new MutationObserver(syncVisibility);
      state.observer.observe(profile, { attributes: true, attributeFilter: ["hidden"] });
    }
    tg?.onEvent?.("activated", syncVisibility);
  }

  window.RoxyProfileCabinet = Object.freeze({ reload: () => load(true) });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();