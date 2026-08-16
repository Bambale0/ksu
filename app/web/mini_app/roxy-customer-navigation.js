(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const PRIMARY_ROUTES = ["home", "catalog", "create", "history", "profile"];
  const CHILD_PARENT = Object.freeze({
    notifications: "profile",
    support: "profile",
    creator: "profile",
    subscriptions: "profile",
    author: "profile",
    references: "create",
    presets: "create",
    batch: "create",
    trends: "catalog",
    "prompt-tools": "catalog",
  });
  const CHILD_ROUTES = Object.freeze(Object.keys(CHILD_PARENT));
  const OPEN_ROUTES = [...PRIMARY_ROUTES, "feed", "wallet", ...CHILD_ROUTES];
  const SHELL_ROUTE = Object.freeze({
    home: "home",
    feed: "feed",
    catalog: "feed",
    create: "create",
    history: "history",
    profile: "profile",
    wallet: "wallet",
  });
  const MENU = Object.freeze([
    ["home", "home", "Главная"],
    ["catalog", "catalog", "Каталог"],
    ["create", "create", "Создать"],
    ["history", "history", "История"],
    ["profile", "profile", "Профиль"],
  ]);

  const state = {
    active: "home",
    currentRoute: "home",
    startupApplied: false,
    historySeeded: false,
    bodyClassObserver: null,
    startupTimer: null,
    catalogAttempt: 0,
    createAttempt: 0,
    childAttempt: 0,
  };

  function requestedRoute() {
    const route = new URLSearchParams(window.location.search).get("route");
    return OPEN_ROUTES.includes(route) ? route : null;
  }

  function haptic(kind = "light") {
    try { tg?.HapticFeedback?.impactOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function shellRouteFor(route) {
    return SHELL_ROUTE[route] || "home";
  }

  function primaryRouteFor(route) {
    if (route === "wallet") return "profile";
    return CHILD_PARENT[route] || route;
  }

  function routeUrl(route) {
    const url = new URL(window.location.href);
    url.searchParams.set("route", route);
    return `${url.pathname}${url.search}${url.hash}`;
  }

  function historyState(route) {
    return { roxyNavigation: true, route };
  }

  function seedBrowserHistory(route) {
    if (state.historySeeded) return;
    state.historySeeded = true;
    const initial = OPEN_ROUTES.includes(route) ? route : "home";
    if (initial === "home") {
      window.history.replaceState(historyState("home"), "", routeUrl("home"));
      return;
    }
    window.history.replaceState(historyState("home"), "", routeUrl("home"));
    window.history.pushState(historyState(initial), "", routeUrl(initial));
  }

  function writeBrowserRoute(route, mode = "push") {
    if (mode === "none") return;
    const current = window.history.state;
    if (current?.roxyNavigation && current.route === route) return;
    const method = mode === "replace" ? "replaceState" : "pushState";
    window.history[method](historyState(route), "", routeUrl(route));
  }

  function emitRoute(route) {
    window.dispatchEvent(new CustomEvent("roxy:route-changed", {
      detail: { route, primary: state.active },
    }));
  }

  function openCatalogWhenReady() {
    if (state.currentRoute !== "catalog") return;
    if (window.RoxyDiscovery?.openCatalog) {
      state.catalogAttempt = 0;
      window.RoxyDiscovery.openCatalog();
      return;
    }
    state.catalogAttempt += 1;
    if (state.catalogAttempt <= 40) {
      window.setTimeout(openCatalogWhenReady, 50);
      return;
    }
    state.catalogAttempt = 0;
    window.KsuStudioShell?.open?.("feed");
  }

  function openCreateWhenReady() {
    if (state.currentRoute !== "create") return;
    if (window.RoxyCreateCenter?.open) {
      state.createAttempt = 0;
      window.RoxyCreateCenter.open();
      return;
    }
    state.createAttempt += 1;
    if (state.createAttempt <= 40) {
      window.setTimeout(openCreateWhenReady, 50);
      return;
    }
    state.createAttempt = 0;
    window.KsuStudioShell?.open?.("create");
  }

  function openChildWhenReady(route) {
    if (state.currentRoute !== route) return;
    if (window.RoxyChildScreens?.open?.(route)) {
      state.childAttempt = 0;
      return;
    }
    state.childAttempt += 1;
    if (state.childAttempt <= 50) {
      window.setTimeout(() => openChildWhenReady(route), 60);
      return;
    }
    state.childAttempt = 0;
    window.KsuStudioShell?.open?.(CHILD_PARENT[route] || "profile");
  }

  function closeTransientSurfaces() {
    window.RoxyDiscovery?.closeCatalog?.();
    window.RoxyCreateCenter?.close?.();
    window.RoxyChildScreens?.close?.();
  }

  function open(route, { feedback = true, historyMode = "push" } = {}) {
    if (!OPEN_ROUTES.includes(route)) return false;
    state.currentRoute = route;
    state.active = primaryRouteFor(route);
    writeBrowserRoute(route, historyMode);
    syncActive();
    if (feedback) haptic(route === "create" ? "medium" : "light");

    if (CHILD_ROUTES.includes(route)) {
      window.RoxyDiscovery?.closeCatalog?.();
      window.RoxyCreateCenter?.close?.();
      state.childAttempt = 0;
      openChildWhenReady(route);
      emitRoute(route);
      return true;
    }

    window.RoxyChildScreens?.close?.();

    if (route === "catalog") {
      window.RoxyCreateCenter?.close?.();
      state.catalogAttempt = 0;
      openCatalogWhenReady();
      emitRoute(route);
      return true;
    }
    if (route === "create") {
      window.RoxyDiscovery?.closeCatalog?.();
      state.createAttempt = 0;
      openCreateWhenReady();
      emitRoute(route);
      return true;
    }

    closeTransientSurfaces();
    const target = shellRouteFor(route);
    if (window.KsuStudioShell?.open) {
      window.KsuStudioShell.open(target);
      emitRoute(route);
      return true;
    }

    document.querySelector(`[data-shell-nav="${target}"]`)?.click();
    emitRoute(route);
    return true;
  }

  function navIcon(name) {
    const icons = {
      home: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11.2 12 5l8 6.2V20h-5.2v-5.5H9.2V20H4v-8.8Z"/></svg>',
      feed: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="4" width="14" height="16" rx="3"/><path d="M8.5 9h7M8.5 12h7M8.5 15h4.5"/></svg>',
      create: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="4"/><path d="M12 8.5v7M8.5 12h7"/></svg>',
      catalog: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7"/><path d="m14.8 9.2-1.4 4.2-4.2 1.4 1.4-4.2 4.2-1.4Z"/></svg>',
      history: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5.2 8.2A7.5 7.5 0 1 1 5 15"/><path d="M5.2 8.2V4.5M5.2 8.2H9"/><path d="M12 8.5V12l2.5 1.8"/></svg>',
      profile: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8.5" r="3.5"/><path d="M5.5 20a6.5 6.5 0 0 1 13 0"/></svg>',
    };
    const icon = document.createElement("span");
    icon.className = "studio-nav-icon roxy-nav-svg";
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML = icons[name] || icons.home;
    return icon;
  }

  function menuButton([route, iconName, label]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `studio-nav-item roxy-customer-nav-item${route === "create" ? " roxy-central-create" : ""}`;
    button.dataset.roxyCustomerRoute = route;
    button.setAttribute("aria-label", label);
    const text = document.createElement("span");
    text.textContent = label;
    button.append(navIcon(iconName), text);
    button.addEventListener("click", () => open(route));
    return button;
  }

  function replaceMenu(root) {
    if (!root) return false;
    const current = [...root.querySelectorAll(":scope > [data-roxy-customer-route]")];
    const complete = current.length === MENU.length && current.every((node, index) => node.dataset.roxyCustomerRoute === MENU[index][0]);
    if (!complete) root.replaceChildren(...MENU.map(menuButton));
    root.dataset.roxyCustomerNavigation = "true";
    return true;
  }

  function mountMenus() {
    const bottom = document.getElementById("studioBottomNav");
    const sidebar = document.querySelector("#studioSidebar .studio-sidebar-nav:not(.studio-sidebar-secondary)");
    replaceMenu(bottom);
    replaceMenu(sidebar);
    syncActive();
    return Boolean(bottom && sidebar);
  }

  function mountMenusUntilReady() {
    if (mountMenus() || state.startupTimer) return;
    let attempts = 0;
    state.startupTimer = window.setInterval(() => {
      attempts += 1;
      if (mountMenus() || attempts >= 50) {
        window.clearInterval(state.startupTimer);
        state.startupTimer = null;
      }
    }, 80);
  }

  function inferredRoute() {
    const childRoute = window.RoxyChildScreens?.route;
    if (childRoute && CHILD_ROUTES.includes(childRoute)) return primaryRouteFor(childRoute);
    if (document.body?.classList.contains("roxy-discovery-catalog-open")) return "catalog";
    if (document.body?.classList.contains("roxy-create-center-open")) return "create";
    const shellRoute = window.KsuStudioShell?.route;
    if (shellRoute === "feed") return "feed";
    if (shellRoute === "wallet") return "profile";
    if (["home", "create", "history", "profile"].includes(shellRoute)) return shellRoute;
    return state.active;
  }

  function syncActive() {
    const inferred = inferredRoute();
    if (PRIMARY_ROUTES.includes(inferred)) state.active = inferred;
    document.querySelectorAll("[data-roxy-customer-route]").forEach((button) => {
      const active = button.dataset.roxyCustomerRoute === state.active;
      button.classList.toggle("is-active", active);
      if (active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
  }

  function applyStartupRoute() {
    if (state.startupApplied || !window.KsuStudioShell?.open) return false;
    state.startupApplied = true;
    const route = requestedRoute() || "home";
    seedBrowserHistory(route);
    window.setTimeout(() => open(route, { feedback: false, historyMode: "none" }), 0);
    return true;
  }

  function handlePopState(event) {
    const route = OPEN_ROUTES.includes(event.state?.route) ? event.state.route : (requestedRoute() || "home");
    open(route, { feedback: false, historyMode: "none" });
  }

  function attachBodyClassObserver() {
    if (state.bodyClassObserver || !document.body) return;
    state.bodyClassObserver = new MutationObserver(() => window.requestAnimationFrame(syncActive));
    state.bodyClassObserver.observe(document.body, { attributes: true, attributeFilter: ["class"] });
  }

  function init() {
    document.body?.classList.add("roxy-customer-navigation-ready");
    mountMenusUntilReady();
    applyStartupRoute();
    syncActive();
    attachBodyClassObserver();

    document.addEventListener("click", (event) => {
      if (!event.target.closest?.("[data-shell-nav]")) return;
      window.requestAnimationFrame(syncActive);
    }, true);
    window.addEventListener("popstate", handlePopState);
    window.addEventListener("roxy:shell-route-changed", () => window.requestAnimationFrame(syncActive));
    window.setTimeout(() => {
      mountMenusUntilReady();
      applyStartupRoute();
      syncActive();
    }, 120);
  }

  window.RoxyCustomerNavigation = Object.freeze({
    open,
    routes: [...PRIMARY_ROUTES],
    childRoutes: [...CHILD_ROUTES],
    refresh: mountMenus,
    get active() { return state.active; },
    get route() { return state.currentRoute; },
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
