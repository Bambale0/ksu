(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = { stats: null, loading: false, activeMenu: "create", observer: null };

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
    const response = await fetch(path, {
      headers: authHeaders(),
      credentials: "same-origin",
      cache: "no-store",
    });
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
    ["create", "✨", "Создать", () => openStudio("create")],
    ["prompts", "🔁", "Промпты", () => openStudio("feed")],
    ["rox", "💎", "Мои ROX", () => openStudio("wallet")],
    ["earn", "👥", "Заработать", scrollToPartner],
    ["profile", "👤", "Профиль", () => openStudio("profile")],
  ];

  function menuButton([key, glyph, label, handler]) {
    const button = el("button", "studio-nav-item roxy-menu-item");
    button.type = "button";
    button.dataset.roxyMenu = key;
    const icon = el("span", "studio-nav-icon", glyph);
    icon.setAttribute("aria-hidden", "true");
    button.append(icon, el("span", "", label));
    button.addEventListener("click", () => {
      state.activeMenu = key;
      syncMenuActive();
      try { tg?.HapticFeedback?.impactOccurred?.("light"); } catch (_error) { /* optional */ }
      handler();
      if (key === "rox") window.setTimeout(loadStats, 0);
    });
    return button;
  }

  function syncMenuActive() {
    document.querySelectorAll("[data-roxy-menu]").forEach((button) => {
      const active = button.dataset.roxyMenu === state.activeMenu;
      button.classList.toggle("is-active", active);
      if (active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
  }

  function mountMenus() {
    const bottom = document.getElementById("studioBottomNav");
    if (bottom && bottom.dataset.roxyEconomy !== "true") {
      bottom.dataset.roxyEconomy = "true";
      bottom.replaceChildren(...MENU.map(menuButton));
    }
    const sidebar = document.querySelector("#studioSidebar .studio-sidebar-nav:not(.studio-sidebar-secondary)");
    if (sidebar && sidebar.dataset.roxyEconomy !== "true") {
      sidebar.dataset.roxyEconomy = "true";
      sidebar.replaceChildren(...MENU.map(menuButton));
      const label = sidebar.previousElementSibling;
      if (label?.classList.contains("studio-nav-label")) label.textContent = "Главное меню";
    }
    syncMenuActive();
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

    let root = document.getElementById("roxyEconomyOverview");
    if (root) return root;

    root = el("section", "roxy-economy-overview");
    root.id = "roxyEconomyOverview";

    const rate = el("div", "roxy-rate-card");
    rate.append(el("span", "", "Курс ROXY"), el("strong", "", "1 ROX = 1 ₽"));

    const balances = el("div", "roxy-balance-grid");
    const bonus = el("article", "roxy-balance-card bonus");
    bonus.append(
      el("span", "roxy-balance-type", "🟣 Бонусные ROX"),
      el("strong", "roxy-balance-number", "—"),
      el("small", "", "Тратятся только внутри ROXY"),
    );
    bonus.querySelector("strong").id = "roxyBonusRox";

    const withdrawable = el("article", "roxy-balance-card withdrawable");
    withdrawable.append(
      el("span", "roxy-balance-type", "🟢 Выводимые ROX"),
      el("strong", "roxy-balance-number", "—"),
      el("small", "", "Только доход с реальных пополнений по реферальной системе"),
    );
    withdrawable.querySelector("strong").id = "roxyWithdrawableRox";
    balances.append(bonus, withdrawable);

    const status = el("div", "roxy-economy-stats");
    status.id = "roxyEconomyStats";

    const rules = el("section", "roxy-rules-card");
    rules.id = "roxyEconomyRules";
    rules.append(
      el("span", "section-kicker", "Как получить ROX"),
      el("h2", "", "Понятная система заработка"),
    );
    const header = el("div", "roxy-rule-row header");
    header.append(el("strong", "", "Как получил ROX"), el("strong", "", "Сколько"), el("strong", "", "Вывод"));
    const rows = el("div", "roxy-rule-list");
    rows.id = "roxyRuleRows";
    rules.append(header, rows);

    const actions = el("div", "roxy-economy-actions");
    const topup = el("button", "roxy-economy-action", "💎 Пополнить ROX");
    topup.type = "button";
    topup.addEventListener("click", () => document.getElementById("topupHeading")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    const earn = el("button", "roxy-economy-action primary", "👥 Заработать ROX");
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
        ruleRow("🎁", "Приветственный бонус", `${format(stats.welcome_bonus_rox)} ROX`, false),
        ruleRow("👤", "Приглашённый друг", `${format(stats.invite_bonus_rox)} ROX`, false),
        ruleRow("🔁", "Повтор промпта", `${format(stats.prompt_repeat_bonus_rox)} ROX`, false),
        ruleRow("👥", "1 уровень", `${format(stats.first_line_percent)}%`, true),
        ruleRow("👥", "2 уровень", `${format(stats.second_line_percent)}%`, true),
        ruleRow("💰", "Минимальный вывод", `${format(stats.minimum_withdrawal_rox)} ROX`, true),
      );
    }
  }

  function rewritePartnerCurrency(root = document.getElementById("partnerPreview")) {
    if (!root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      const current = node.nodeValue || "";
      const next = current
        .replaceAll(" ₽", " ROX")
        .replaceAll("Сумма, ₽", "Сумма, ROX")
        .replaceAll("Присоединяйся к Ксю AI Studio", "Присоединяйся к ROXY AI Creative Studio");
      if (next !== current) node.nodeValue = next;
    }
    const heading = document.getElementById("partnerPreviewHeading");
    if (heading) heading.textContent = "Заработать ROX";
  }

  function rewriteWalletCreditCopy() {
    const wallet = document.getElementById("walletView");
    if (!wallet) return;
    const walker = document.createTreeWalker(wallet, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      const current = node.nodeValue || "";
      const next = current.replaceAll(" кр.", " ROX").replaceAll("кредиты", "ROX");
      if (next !== current) node.nodeValue = next;
    }
  }

  async function loadStats() {
    if (!tg?.initData || state.loading) return;
    state.loading = true;
    try {
      state.stats = await api("/api/v1/referrals/stats");
      renderStats(state.stats);
    } catch (_error) {
      // The existing wallet/partner views remain usable if this enhancement fails.
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
    ensureStyles();
    mountMenus();
    ensureWalletEconomy();
    rewritePartnerCurrency();
    rewriteWalletCreditCopy();
    syncVisibleRoute();
    const wallet = document.getElementById("walletView");
    if (wallet && !wallet.hidden) void loadStats();
  }

  function init() {
    apply();
    if (state.observer || !document.body) return;
    state.observer = new MutationObserver(() => window.requestAnimationFrame(apply));
    state.observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["hidden"] });
    tg?.onEvent?.("activated", () => {
      void loadStats();
      apply();
    });
    window.addEventListener("online", () => void loadStats());
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
