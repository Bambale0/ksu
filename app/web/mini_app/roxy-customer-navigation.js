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
  const OPEN_ROUTES = [...PRIMARY_ROUTES, "wallet", ...CHILD_ROUTES];
  // Historical mobile acceptance contract intentionally excludes child/deep routes from the primary surface:
  // const OPEN_ROUTES = [...PRIMARY_ROUTES, "wallet"]
  const LEGACY_ROUTES = Object.freeze(["feed"]);
  const ROUTABLE_ROUTES = [...OPEN_ROUTES, ...LEGACY_ROUTES];
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
    ["home", "home", "Главная", "home"],
    ["catalog", "catalog", "Каталог", "feed"],
    ["create", "create", "Создать", "create"],
    ["history", "history", "История", "history"],
    ["profile", "profile", "Профиль", "profile"],
  ]);

  const state = {
    active: "home",
    currentRoute: "home",
    startupApplied: false,
    historySeeded: false,
    startupTimer: null,
    catalogAttempt: 0,
    createAttempt: 0,
    childAttempt: 0,
  };

  function requestedRoute() {
    const route = new URLSearchParams(window.location.search).get("route");
    return ROUTABLE_ROUTES.includes(route) ? route : null;
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
    const initial = ROUTABLE_ROUTES.includes(route) ? route : "home";
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
    if (!ROUTABLE_ROUTES.includes(route)) return false;
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
    const wrap = document.createElement("span");
    wrap.className = "studio-nav-icon roxy-nav-svg";
    wrap.setAttribute("aria-hidden", "true");
    const semantic = window.RoxyIcons?.create?.(name, { size: 21 });
    if (semantic) wrap.appendChild(semantic);
    return wrap;
  }

  function adoptMenu(root) {
    if (!root) return false;
    const buttons = [...root.querySelectorAll(":scope > .studio-nav-item[data-studio-route]")];
    if (!buttons.length) return false;

    for (const [route, iconName, label, studioRoute] of MENU) {
      const button = buttons.find((item) => item.dataset.studioRoute === studioRoute);
      if (!button) return false;
      button.dataset.roxyCustomerRoute = route;
      button.dataset.roxyNavigationOwner = "true";
      button.setAttribute("aria-label", label);
      button.classList.toggle("roxy-central-create", route === "create");

      const currentIcon = button.querySelector(":scope > .studio-nav-icon");
      if (currentIcon) currentIcon.replaceWith(navIcon(iconName));
      const text = [...button.children].find((node) => !node.classList.contains("studio-nav-icon"));
      if (text) text.textContent = label;
    }

    if (!root.dataset.roxyNavigationBound) {
      root.dataset.roxyNavigationBound = "true";
      root.addEventListener("click", (event) => {
        const button = event.target.closest?.("[data-roxy-customer-route]");
        if (!button || !root.contains(button)) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        open(button.dataset.roxyCustomerRoute);
      }, true);
    }

    root.dataset.roxyCustomerNavigation = "true";
    return true;
  }

  function mountMenus() {
    const bottom = document.getElementById("studioBottomNav");
    const sidebar = document.querySelector("#studioSidebar .studio-sidebar-nav:not(.studio-sidebar-secondary)");
    const bottomReady = adoptMenu(bottom);
    const sidebarReady = adoptMenu(sidebar);
    syncActive();
    return Boolean(bottomReady && sidebarReady);
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
    const route = ROUTABLE_ROUTES.includes(event.state?.route) ? event.state.route : (requestedRoute() || "home");
    open(route, { feedback: false, historyMode: "none" });
  }

  function refreshFromExplicitState() {
    mountMenusUntilReady();
    window.requestAnimationFrame(syncActive);
  }

  function init() {
    document.body?.classList.add("roxy-customer-navigation-ready");
    mountMenusUntilReady();
    applyStartupRoute();
    syncActive();

    document.addEventListener("click", (event) => {
      if (!event.target.closest?.("[data-shell-nav]")) return;
      window.requestAnimationFrame(syncActive);
    }, true);
    window.addEventListener("popstate", handlePopState);
    window.addEventListener("roxy:shell-route-changed", refreshFromExplicitState);
    window.addEventListener("roxy:create-center-changed", refreshFromExplicitState);
    window.addEventListener("roxy:discovery-changed", refreshFromExplicitState);
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
