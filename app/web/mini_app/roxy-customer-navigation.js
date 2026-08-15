(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const PRIMARY_ROUTES = ["home", "catalog", "create", "history", "profile"];
  const OPEN_ROUTES = [...PRIMARY_ROUTES, "wallet"];
  const SHELL_ROUTE = Object.freeze({
    home: "home",
    catalog: "feed",
    create: "create",
    history: "history",
    profile: "profile",
    wallet: "wallet",
  });
  const MENU = Object.freeze([
    ["home", "⌂", "Главная"],
    ["catalog", "▦", "Каталог"],
    ["create", "＋", "Создать"],
    ["history", "≡", "История"],
    ["profile", "○", "Профиль"],
  ]);

  const state = {
    active: "home",
    startupApplied: false,
    bodyClassObserver: null,
    startupTimer: null,
    catalogAttempt: 0,
    createAttempt: 0,
  };

  function requestedRoute() {
    const route = new URLSearchParams(window.location.search).get("route");
    return OPEN_ROUTES.includes(route) ? route : null;
  }

  function haptic(kind = "light") {
    try {
      tg?.HapticFeedback?.impactOccurred?.(kind);
    } catch (_error) {
      // Optional Telegram capability.
    }
  }

  function shellRouteFor(route) {
    return SHELL_ROUTE[route] || "home";
  }

  function primaryRouteFor(route) {
    return route === "wallet" ? "profile" : route;
  }

  function emitRoute(route) {
    window.dispatchEvent(new CustomEvent("roxy:route-changed", {
      detail: { route, primary: state.active },
    }));
  }

  function openCatalogWhenReady() {
    if (state.active !== "catalog") return;
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
    if (state.active !== "create") return;
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

  function open(route, { feedback = true } = {}) {
    if (!OPEN_ROUTES.includes(route)) return;
    state.active = primaryRouteFor(route);
    syncActive();
    if (feedback) haptic(route === "create" ? "medium" : "light");

    if (route === "catalog") {
      window.RoxyCreateCenter?.close?.();
      state.catalogAttempt = 0;
      openCatalogWhenReady();
      emitRoute(route);
      return;
    }
    if (route === "create") {
      window.RoxyDiscovery?.closeCatalog?.();
      state.createAttempt = 0;
      openCreateWhenReady();
      emitRoute(route);
      return;
    }

    window.RoxyDiscovery?.closeCatalog?.();
    window.RoxyCreateCenter?.close?.();
    const target = shellRouteFor(route);
    if (window.KsuStudioShell?.open) {
      window.KsuStudioShell.open(target);
      emitRoute(route);
      return;
    }

    const fallback = document.querySelector(`[data-shell-nav="${target}"]`);
    fallback?.click();
    emitRoute(route);
  }

  function menuButton([route, glyph, label]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `studio-nav-item roxy-customer-nav-item${route === "create" ? " roxy-central-create" : ""}`;
    button.dataset.roxyCustomerRoute = route;
    button.setAttribute("aria-label", label);

    const icon = document.createElement("span");
    icon.className = "studio-nav-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = glyph;

    const text = document.createElement("span");
    text.textContent = label;
    button.append(icon, text);
    button.addEventListener("click", () => open(route));
    return button;
  }

  function replaceMenu(root) {
    if (!root || root.dataset.roxyCustomerNavigation === "true") return Boolean(root);
    root.dataset.roxyCustomerNavigation = "true";
    root.replaceChildren(...MENU.map(menuButton));
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
    if (document.body?.classList.contains("roxy-discovery-catalog-open")) return "catalog";
    if (document.body?.classList.contains("roxy-create-center-open")) return "create";
    const shellRoute = window.KsuStudioShell?.route;
    if (shellRoute === "feed") return "catalog";
    if (shellRoute === "wallet") return "profile";
    if (PRIMARY_ROUTES.includes(shellRoute)) return shellRoute;
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
    const route = requestedRoute();
    if (route) {
      window.setTimeout(() => open(route, { feedback: false }), 0);
    } else {
      state.active = inferredRoute();
      syncActive();
    }
    return true;
  }

  function attachBodyClassObserver() {
    if (state.bodyClassObserver || !document.body) return;
    state.bodyClassObserver = new MutationObserver(() => window.requestAnimationFrame(syncActive));
    state.bodyClassObserver.observe(document.body, {
      attributes: true,
      attributeFilter: ["class"],
    });
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
    window.addEventListener("popstate", () => window.requestAnimationFrame(syncActive));
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
    get active() {
      return state.active;
    },
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
