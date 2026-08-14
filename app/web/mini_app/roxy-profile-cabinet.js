(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    overview: null,
    economy: null,
    loading: false,
    mounted: false,
    observer: null,
  };
  const dom = {};

  function authHeaders() {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function api(path) {
    const response = await fetch(path, {
      headers: authHeaders(),
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
      el("p", "", "Баланс, заработок, платежи и настройки без перегруженного меню."),
    );
    const refresh = button("↻", () => void load(true), "roxy-cabinet-refresh");
    refresh.setAttribute("aria-label", "Обновить кабинет");
    head.append(copy, refresh);

    const balances = el("div", "roxy-cabinet-balances");
    balances.id = "roxyCabinetBalances";
    balances.append(metric("Бонусные ROX", "—", "Только внутри ROXY"), metric("Выводимые ROX", "—", "Реферальный доход"));

    const actions = el("div", "roxy-cabinet-actions");
    actions.append(
      quickAction("💎", "Мои ROX", "Баланс, пополнение и операции", () => openRoute("wallet"), true),
      quickAction("≡", "История", "Все генерации", () => openRoute("history")),
      quickAction("👥", "Реферальная программа", "30% / 5% и вывод", () => scrollPartner()),
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
    const creatorCopy = el("div", "roxy-creator-partnership-copy");
    creatorCopy.append(
      el("span", "section-kicker", "Для авторов и каналов"),
      el("h3", "", "Creator-партнёрство"),
      el("p", "", "Это отдельная программа, не реферальные 30% / 5%. Условия зависят от канала, аудитории и формата сотрудничества; после согласования возможны ежемесячные начисления ROX."),
    );
    const creatorActions = el("div", "roxy-creator-partnership-actions");
    creatorActions.append(
      button("Связаться по партнёрству", contactPartnership, "roxy-creator-primary"),
      el("small", "", "Персональные условия согласуются вручную"),
    );
    creator.append(creatorCopy, creatorActions);

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
  }

  function markReferralProgram() {
    const heading = document.getElementById("partnerPreviewHeading");
    if (heading) heading.textContent = "Автоматическая реферальная программа";
    const section = document.getElementById("partnerPreview")?.closest(".home-section");
    const kicker = section?.querySelector(".section-kicker");
    if (kicker) kicker.textContent = "Рефералы 30% / 5%";
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
        metric("Бонусные ROX", `${format(economy.bonus_rox)} ROX`, "Тратятся только внутри ROXY"),
        metric("Выводимые ROX", `${format(economy.withdrawable_rox)} ROX`, `Вывод от ${format(economy.minimum_withdrawal_rox)} ROX`),
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
        metric("Платежи", format(paymentSuccessCount(overview.payments), 0), "Успешных пополнений"),
        metric("Рефералы", `${format(economy.first_line || 0, 0)} + ${format(economy.second_line || 0, 0)}`, "1-я + 2-я линия"),
        metric("Сейчас в работе", format(active, 0), "Генераций"),
        metric("Поддержка", format(Number(supportStatuses.open || 0) + Number(supportStatuses.in_progress || 0), 0), "Открытых обращений"),
        metric("Повторы промптов", format(economy.prompt_repeats || 0, 0), "Использований ваших работ"),
      );
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
    if (!force && state.overview && state.economy) return;
    state.loading = true;
    message("Обновляю кабинет…");
    try {
      const [overview, economy] = await Promise.all([
        api("/api/v1/me/overview"),
        api("/api/v1/referrals/stats"),
      ]);
      state.overview = overview;
      state.economy = economy;
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

  function contactPartnership() {
    haptic("medium");
    const tryOpen = (attempt = 0) => {
      const form = document.getElementById("supportComposeForm");
      if (!form) {
        if (attempt < 30) window.setTimeout(() => tryOpen(attempt + 1), 80);
        return;
      }
      const topic = form.querySelector('input[type="text"]');
      const body = form.querySelector("textarea");
      if (topic && !topic.value.trim()) topic.value = "Creator-партнёрство ROXY";
      if (body && !body.value.trim()) body.value = "Хочу обсудить индивидуальные условия партнёрства. Канал / аудитория / формат сотрудничества: ";
      form.scrollIntoView({ behavior: "smooth", block: "start" });
      topic?.focus({ preventScroll: true });
      notify("success");
    };
    scrollSettings();
    tryOpen();
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
