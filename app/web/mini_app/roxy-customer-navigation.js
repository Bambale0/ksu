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
    observer: null,
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

  function open(route, { feedback = true } = {}) {
    if (!OPEN_ROUTES.includes(route)) return;
    state.active = primaryRouteFor(route);
    syncActive();
    if (feedback) haptic(route === "create" ? "medium" : "light");

    const target = shellRouteFor(route);
    if (window.KsuStudioShell?.open) {
      window.KsuStudioShell.open(target);
      return;
    }

    const fallback = document.querySelector(`[data-shell-nav="${target}"]`);
    fallback?.click();
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
    if (!root || root.dataset.roxyCustomerNavigation === "true") return;
    root.dataset.roxyCustomerNavigation = "true";
    root.replaceChildren(...MENU.map(menuButton));
  }

  function mountMenus() {
    replaceMenu(document.getElementById("studioBottomNav"));
    replaceMenu(
      document.querySelector("#studioSidebar .studio-sidebar-nav:not(.studio-sidebar-secondary)"),
    );
    syncActive();
  }

  function inferredRoute() {
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

  function apply() {
    mountMenus();
    applyStartupRoute();
    syncActive();
  }

  function init() {
    document.body?.classList.add("roxy-customer-navigation-ready");
    apply();
    if (!state.observer && document.body) {
      state.observer = new MutationObserver(() => window.requestAnimationFrame(apply));
      state.observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["hidden", "class"],
      });
    }
    window.setTimeout(apply, 80);
    window.setTimeout(apply, 240);
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
