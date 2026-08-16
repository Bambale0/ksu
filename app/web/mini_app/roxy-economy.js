(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  // RoxyCustomerNavigation is the sole owner of visible primary menus.
  // Economy only reacts to route changes and enriches wallet/partner surfaces.
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
    ["earn", "Заработать", scrollToPartner],
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

  function ruleRow(icon, label, amount, withdrawable) {
    const row = el("div", "roxy-rule-row");
    const source = el("div", "roxy-rule-source");
    source.append(el("span", "roxy-rule-icon", icon), el("span", "", label));
    row.append(
      source,
      el("strong", "roxy-rule-amount", amount),
      el("span", `roxy-rule-withdraw ${withdrawable ? "yes" : "no"}`, withdrawable ? "✓" : "×"),
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
    if (partnerHeading) partnerHeading.textContent = "Заработать ROX";

    let root = document.getElementById("roxyEconomyOverview");
    if (root) return root;

    root = el("section", "roxy-economy-overview");
    root.id = "roxyEconomyOverview";

    const rate = el("div", "roxy-rate-card");
    rate.append(el("span", "", "Курс ROXY"), el("strong", "", "1 ROX = 1 ₽"));

    const balances = el("div", "roxy-balance-grid");
    const bonus = el("article", "roxy-balance-card bonus");
    bonus.append(
      el("span", "roxy-balance-type", "Бонусные ROX"),
      el("strong", "roxy-balance-number", "—"),
      el("small", "", "Тратятся только внутри ROXY"),
    );
    bonus.querySelector("strong").id = "roxyBonusRox";

    const withdrawable = el("article", "roxy-balance-card withdrawable");
    withdrawable.append(
      el("span", "roxy-balance-type", "Выводимые ROX"),
      el("strong", "roxy-balance-number", "—"),
      el("small", "", "Только доход с реальных пополнений по реферальной системе"),
    );
    withdrawable.querySelector("strong").id = "roxyWithdrawableRox";
    balances.append(bonus, withdrawable);

    const status = el("div", "roxy-economy-stats");
    status.id = "roxyEconomyStats";

    const rules = el("section", "roxy-rules-card");
    rules.id = "roxyEconomyRules";
    rules.append(el("span", "section-kicker", "Как получить ROX"), el("h2", "", "Понятная система заработка"));
    const header = el("div", "roxy-rule-row header");
    header.append(el("strong", "", "Как получил ROX"), el("strong", "", "Сколько"), el("strong", "", "Вывод"));
    const rows = el("div", "roxy-rule-list");
    rows.id = "roxyRuleRows";
    rules.append(header, rows);

    const actions = el("div", "roxy-economy-actions");
    const topup = el("button", "roxy-economy-action", "Пополнить ROX");
    topup.type = "button";
    topup.addEventListener("click", () => document.getElementById("topupHeading")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    const earn = el("button", "roxy-economy-action primary", "Заработать ROX");
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
    const bonus = document.getElementById("roxyBonusRox");
    const withdrawable = document.getElementById("roxyWithdrawableRox");
    if (bonus) bonus.textContent = `${format(stats.bonus_rox)} ROX`;
    if (withdrawable) withdrawable.textContent = `${format(stats.withdrawable_rox)} ROX`;

    const status = document.getElementById("roxyEconomyStats");
    if (status) {
      status.replaceChildren(
        el("span", "", `Создано промптов: ${stats.prompts_created ?? 0}`),
        el("span", "", `Повторов промптов: ${stats.prompt_repeats ?? 0}`),
        el("span", "", `1 линия: ${stats.first_line ?? 0}`),
        el("span", "", `2 линия: ${stats.second_line ?? 0}`),
      );
    }

    const rows = document.getElementById("roxyRuleRows");
    if (rows) {
      rows.replaceChildren(
        ruleRow("+", "Приветственный бонус", `${format(stats.welcome_bonus_rox)} ROX`, false),
        ruleRow("+", "Приглашённый друг", `${format(stats.invite_bonus_rox)} ROX`, false),
        ruleRow("↻", "Повтор промпта", `${format(stats.prompt_repeat_bonus_rox)} ROX`, false),
        ruleRow("1", "1 уровень", `${format(stats.first_line_percent)}%`, true),
        ruleRow("2", "2 уровень", `${format(stats.second_line_percent)}%`, true),
        ruleRow("↓", "Минимальный вывод", `${format(stats.minimum_withdrawal_rox)} ROX`, true),
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