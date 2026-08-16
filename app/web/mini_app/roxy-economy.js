(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    stats: null,
    loading: false,
    activeMenu: "create",
    contentObserver: null,
    routeObserver: null,
    contentRoots: new Set(),
    routeRoots: new Set(),
    frame: 0,
  };

  function ensureStyles() {
    if (document.querySelector('link[href="/mini-app/roxy-economy.css"]')) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/mini-app/roxy-economy.css";
    document.head.appendChild(link);
  }

  function authHeaders() {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function api(path) {
    const response = await fetch(path, { headers: authHeaders(), credentials: "same-origin", cache: "no-store" });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
    return payload;
  }

  function format(value, digits = 2) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return "0";
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(parsed);
  }

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function openStudio(route) {
    const customerRoute = route === "feed" ? "catalog" : route;
    if (window.RoxyCustomerNavigation?.open) {
      window.RoxyCustomerNavigation.open(customerRoute);
      return;
    }
    window.KsuStudioShell?.open?.(route);
  }

  function scrollToPartner() {
    openStudio("profile");
    state.activeMenu = "earn";
    syncMenuActive();
    let attempt = 0;
    const scroll = () => {
      const node = document.getElementById("partnerPreview");
      if (node) {
        node.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      if (attempt++ < 30) window.setTimeout(scroll, 80);
    };
    window.setTimeout(scroll, 50);
  }

  const MENU = [
    ["create", "Создать", () => openStudio("create")],
    ["prompts", "Промпты", () => openStudio("feed")],
    ["rox", "Мои ROX", () => openStudio("wallet")],
    ["earn", "Заработок", scrollToPartner],
    ["profile", "Профиль", () => openStudio("profile")],
  ];
  void MENU;

  function syncMenuActive() {
    document.querySelectorAll("[data-roxy-menu]").forEach((button) => {
      const active = button.dataset.roxyMenu === state.activeMenu;
      button.classList.toggle("is-active", active);
      if (active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
  }

  function ruleRow(icon, label, amount, destination) {
    const row = el("div", "roxy-rule-row");
    const source = el("div", "roxy-rule-source");
    source.append(el("span", "roxy-rule-icon", icon), el("span", "", label));
    row.append(
      source,
      el("strong", "roxy-rule-amount", amount),
      el("span", "roxy-rule-destination", destination),
    );
    return row;
  }

  function ensureWalletEconomy() {
    const wallet = document.getElementById("walletView");
    const legacyHero = document.getElementById("walletHero");
    if (!wallet || !legacyHero) return null;
    const title = document.getElementById("walletViewTitle");
    if (title) title.textContent = "Мои ROX";
    const kicker = wallet.querySelector(".view-heading .section-kicker");
    if (kicker) kicker.textContent = "ROXY";
    const walletNote = legacyHero.querySelector("small");
    if (walletNote) walletNote.textContent = "Внутренняя валюта ROXY";
    const partnerHeading = document.getElementById("partnerPreviewHeading");
    if (partnerHeading) partnerHeading.textContent = "Партнёрский заработок";

    let root = document.getElementById("roxyEconomyOverview");
    if (root) return root;

    root = el("section", "roxy-economy-overview");
    root.id = "roxyEconomyOverview";

    const rate = el("div", "roxy-rate-card");
    rate.append(el("span", "", "Курс ROXY"), el("strong", "", "1 ROX = 1 ₽"));

    const balances = el("div", "roxy-balance-grid");
    const walletCard = el("article", "roxy-balance-card wallet");
    walletCard.append(
      el("span", "roxy-balance-type", "Баланс ROX"),
      el("strong", "roxy-balance-number", "—"),
      el("small", "", "Бонусы и пополнения сразу зачисляются сюда"),
    );
    walletCard.querySelector("strong").id = "roxyWalletRox";

    const earnings = el("article", "roxy-balance-card earnings");
    earnings.append(
      el("span", "roxy-balance-type", "Заработок партнёра"),
      el("strong", "roxy-balance-number", "—"),
      el("small", "", "Можно вывести деньгами или перевести в ROX"),
    );
    earnings.querySelector("strong").id = "roxyPartnerRub";
    balances.append(walletCard, earnings);

    const status = el("div", "roxy-economy-stats");
    status.id = "roxyEconomyStats";

    const rules = el("section", "roxy-rules-card");
    rules.id = "roxyEconomyRules";
    rules.append(el("span", "section-kicker", "Как это работает"), el("h2", "", "ROX отдельно, заработок отдельно"));
    const header = el("div", "roxy-rule-row header");
    header.append(el("strong", "", "Источник"), el("strong", "", "Начисление"), el("strong", "", "Куда"));
    const rows = el("div", "roxy-rule-list");
    rows.id = "roxyRuleRows";
    rules.append(header, rows);

    const actions = el("div", "roxy-economy-actions");
    const topup = el("button", "roxy-economy-action", "Пополнить ROX");
    topup.type = "button";
    topup.addEventListener("click", () => document.getElementById("topupHeading")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    const earn = el("button", "roxy-economy-action primary", "Партнёрский заработок");
    earn.type = "button";
    earn.addEventListener("click", scrollToPartner);
    actions.append(topup, earn);

    root.append(rate, balances, status, rules, actions);
    legacyHero.insertAdjacentElement("beforebegin", root);
    legacyHero.hidden = true;
    wallet.classList.add("roxy-economy-ready");
    return root;
  }

  function renderStats(stats) {
    const root = ensureWalletEconomy();
    if (!root || !stats) return;
    const wallet = document.getElementById("roxyWalletRox");
    const partner = document.getElementById("roxyPartnerRub");
    if (wallet) wallet.textContent = `${format(stats.rox_balance ?? stats.bonus_rox)} ROX`;
    if (partner) partner.textContent = `${format(stats.partner_balance_rub ?? stats.available)} ₽`;

    const status = document.getElementById("roxyEconomyStats");
    if (status) {
      status.replaceChildren(
        el("span", "", `Пополнения покупают ROX напрямую`),
        el("span", "", `1 линия: ${stats.first_line ?? 0}`),
        el("span", "", `2 линия: ${stats.second_line ?? 0}`),
      );
    }

    const rows = document.getElementById("roxyRuleRows");
    if (rows) {
      rows.replaceChildren(
        ruleRow("+", "Приветственный бонус", `+${format(stats.welcome_bonus_rox)} ROX`, "В баланс"),
        ruleRow("+", "Приглашённый друг", `+${format(stats.invite_bonus_rox)} ROX`, "В баланс"),
        ruleRow("↻", "Повтор промпта", `+${format(stats.prompt_repeat_bonus_rox)} ROX`, "В баланс"),
        ruleRow("1", "Пополнение 1-й линии", `${format(stats.first_line_percent)}%`, "В ₽ доход"),
        ruleRow("2", "Пополнение 2-й линии", `${format(stats.second_line_percent)}%`, "В ₽ доход"),
      );
    }
  }

  async function loadStats() {
    if (!tg?.initData || state.loading) return;
    state.loading = true;
    try {
      state.stats = await api("/api/v1/referrals/stats");
      renderStats(state.stats);
    } catch (_error) {
      // Existing wallet/partner views remain usable if this enhancement fails.
    } finally {
      state.loading = false;
    }
  }

  function syncVisibleRoute() {
    const wallet = document.getElementById("walletView");
    const profile = document.getElementById("profileView");
    const builder = document.getElementById("builderView");
    const feed = document.getElementById("feedOverlay");
    if (wallet && !wallet.hidden) state.activeMenu = "rox";
    else if (profile && !profile.hidden && state.activeMenu !== "earn") state.activeMenu = "profile";
    else if (feed && !feed.hidden) state.activeMenu = "prompts";
    else if (builder && !builder.hidden) state.activeMenu = "create";
    syncMenuActive();
  }

  function apply() {
    state.frame = 0;
    ensureStyles();
    ensureWalletEconomy();
    syncVisibleRoute();
    attachScopedObservers();
  }

  function scheduleApply() {
    if (state.frame) return;
    state.frame = window.requestAnimationFrame(apply);
  }

  function routeMutation(mutations) {
    scheduleApply();
    if (mutations.some((mutation) => mutation.target?.id === "walletView" && !mutation.target.hidden)) void loadStats();
  }

  function ensureObservers() {
    if (!state.contentObserver) state.contentObserver = new MutationObserver(scheduleApply);
    if (!state.routeObserver) state.routeObserver = new MutationObserver(routeMutation);
  }

  function attachScopedObservers() {
    ensureObservers();
    for (const root of [document.getElementById("walletView"), document.getElementById("partnerPreview")]) {
      if (!root || state.contentRoots.has(root)) continue;
      state.contentRoots.add(root);
      state.contentObserver.observe(root, { childList: true, subtree: true });
    }
    for (const root of [
      document.getElementById("walletView"),
      document.getElementById("profileView"),
      document.getElementById("builderView"),
      document.getElementById("feedOverlay"),
    ]) {
      if (!root || state.routeRoots.has(root)) continue;
      state.routeRoots.add(root);
      state.routeObserver.observe(root, { attributes: true, attributeFilter: ["hidden"] });
    }
  }

  function init() {
    apply();
    const wallet = document.getElementById("walletView");
    if (wallet && !wallet.hidden) void loadStats();
    for (const delay of [80, 240, 700]) {
      window.setTimeout(() => { attachScopedObservers(); scheduleApply(); }, delay);
    }
    tg?.onEvent?.("activated", () => { void loadStats(); scheduleApply(); });
    window.addEventListener("online", () => void loadStats());
    window.addEventListener("roxy:route-changed", (event) => {
      if (event.detail?.route === "wallet") void loadStats();
      scheduleApply();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();