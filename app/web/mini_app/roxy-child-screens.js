(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const CONFIG = Object.freeze({
    notifications: {
      parent: "profile",
      kicker: "События",
      title: "Уведомления",
      selector: "#profileNotificationList",
      closest: ".profile-tools-section",
    },
    support: {
      parent: "profile",
      kicker: "Помощь",
      title: "Поддержка",
      selector: "#supportComposeForm",
      closest: ".profile-tools-section",
    },
    creator: {
      parent: "profile",
      kicker: "Партнёрство",
      title: "Creator",
      selector: "#creatorPartnershipEntry",
    },
    subscriptions: {
      parent: "profile",
      kicker: "Сообщество",
      title: "Подписки и авторы",
      selector: ".social-profile-section",
    },
    references: {
      parent: "create",
      kicker: "Библиотека",
      title: "Референсы",
      libraryTab: "references",
    },
    presets: {
      parent: "create",
      kicker: "Библиотека",
      title: "Пресеты",
      libraryTab: "presets",
    },
    batch: {
      parent: "create",
      kicker: "Пакетная работа",
      title: "Batch",
      batch: true,
    },
    trends: {
      parent: "catalog",
      kicker: "Каталог",
      title: "Тренды",
      legacyApp: "trends",
    },
    "prompt-tools": {
      parent: "catalog",
      kicker: "AI-инструменты",
      title: "Prompt Tools",
      legacyApp: "prompt-tools",
    },
  });

  const LEGACY_APPS = Object.freeze({
    trends: {
      rootId: "trendsApp",
      css: "/mini-app/trends.css",
      script: "/mini-app/trends.js",
      build() {
        const root = el("main");
        root.id = "trendsApp";
        const filters = el("div");
        filters.id = "trendFilters";
        const catalog = el("section");
        catalog.id = "trendCatalog";
        catalog.setAttribute("aria-live", "polite");
        const runner = el("aside");
        runner.id = "trendRunner";
        runner.hidden = true;
        runner.setAttribute("aria-live", "polite");
        const result = el("section");
        result.id = "trendResult";
        result.hidden = true;
        result.setAttribute("aria-live", "polite");
        root.append(filters, catalog, runner, result);
        return root;
      },
    },
    "prompt-tools": {
      rootId: "promptToolsApp",
      css: "/mini-app/prompt-tools.css",
      script: "/mini-app/prompt-tools.js",
      build() {
        const root = el("main");
        root.id = "promptToolsApp";
        const tabs = el("nav", "tool-tabs");
        tabs.id = "toolTabs";
        tabs.setAttribute("aria-label", "AI-инструменты");
        const panel = el("section", "tool-panel");
        panel.id = "toolPanel";
        panel.setAttribute("aria-live", "polite");
        const result = el("section", "tool-result");
        result.id = "toolResult";
        result.hidden = true;
        result.setAttribute("aria-live", "polite");
        root.append(tabs, panel, result);
        return root;
      },
    },
  });

  const state = {
    mounted: false,
    route: null,
    target: null,
    placeholder: null,
    openToken: 0,
    appRoots: new Map(),
  };
  const dom = {};

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function ensureStylesheet(href) {
    if (!href || document.querySelector(`link[href="${href}"]`)) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    document.head.appendChild(link);
  }

  function ensureScript(src) {
    if (!src || document.querySelector(`script[src="${src}"]`)) return;
    const script = document.createElement("script");
    script.src = src;
    script.dataset.roxyChildRuntime = "true";
    document.head.appendChild(script);
  }

  function mount() {
    if (state.mounted) return true;
    const main = document.getElementById("appMain");
    if (!main) return false;

    const view = el("section", "app-view roxy-child-screen");
    view.id = "roxyChildScreen";
    view.dataset.view = "roxy-child";
    view.hidden = true;
    view.setAttribute("aria-live", "polite");

    const head = el("header", "roxy-child-screen-head");
    const back = el("button", "roxy-child-screen-back", "←");
    back.type = "button";
    back.setAttribute("aria-label", "Назад");
    back.addEventListener("click", () => {
      try { tg?.HapticFeedback?.impactOccurred?.("light"); } catch (_error) { /* optional */ }
      window.history.back();
    });
    const title = el("div", "roxy-child-screen-title");
    const kicker = el("span", "section-kicker");
    const heading = el("h1");
    title.append(kicker, heading);
    head.append(back, title);

    const body = el("div", "roxy-child-screen-body");
    body.id = "roxyChildScreenBody";
    view.append(head, body);
    main.appendChild(view);

    Object.assign(dom, { view, body, kicker, heading, back });
    state.mounted = true;
    return true;
  }

  function restoreMovedTarget() {
    if (!state.target || !state.placeholder) {
      state.target = null;
      state.placeholder = null;
      return;
    }
    const placeholder = state.placeholder;
    if (placeholder.parentNode) {
      placeholder.parentNode.insertBefore(state.target, placeholder);
      placeholder.remove();
    }
    state.target = null;
    state.placeholder = null;
  }

  function hideBaseViews() {
    document.querySelectorAll("#appMain > .app-view").forEach((view) => {
      if (view === dom.view) return;
      view.hidden = true;
      view.classList.remove("is-active");
    });
    dom.view.hidden = false;
    dom.view.classList.add("is-active");
  }

  function showState(message) {
    dom.body.replaceChildren(el("div", "roxy-child-screen-state", message));
  }

  function targetFor(config) {
    const anchor = document.querySelector(config.selector);
    if (!anchor) return null;
    if (!config.closest) return anchor;
    return anchor.closest(config.closest) || anchor;
  }

  function moveTarget(target) {
    restoreMovedTarget();
    const placeholder = document.createComment("roxy-child-screen-placeholder");
    target.parentNode?.insertBefore(placeholder, target);
    state.target = target;
    state.placeholder = placeholder;
    dom.body.replaceChildren(target);
  }

  function openDomRoute(route, config, token, attempt = 0) {
    if (token !== state.openToken || state.route !== route) return;
    const target = targetFor(config);
    if (!target) {
      if (attempt < 40) {
        showState("Загружаю раздел…");
        window.setTimeout(() => openDomRoute(route, config, token, attempt + 1), 75);
        return;
      }
      showState("Раздел временно недоступен. Вернитесь назад и попробуйте ещё раз.");
      return;
    }
    moveTarget(target);
    hideBaseViews();
  }

  function openLibrary(config) {
    restoreMovedTarget();
    dom.view.hidden = true;
    dom.view.classList.remove("is-active");
    window.KsuStudioShell?.openLibrary?.(config.libraryTab);
  }

  function openBatch() {
    restoreMovedTarget();
    dom.view.hidden = true;
    dom.view.classList.remove("is-active");
    let attempt = 0;
    const run = () => {
      if (state.route !== "batch") return;
      if (window.RoxyBatchEmbedded?.open) {
        window.RoxyBatchEmbedded.open({ manageHistory: false });
        return;
      }
      if (attempt++ < 40) window.setTimeout(run, 75);
    };
    run();
  }

  function openLegacyApp(route, config) {
    restoreMovedTarget();
    const app = LEGACY_APPS[config.legacyApp];
    if (!app) {
      showState("Раздел не настроен.");
      hideBaseViews();
      return;
    }
    let root = state.appRoots.get(config.legacyApp);
    const firstMount = !root;
    if (!root) {
      root = app.build();
      state.appRoots.set(config.legacyApp, root);
    }
    dom.body.replaceChildren(root);
    hideBaseViews();
    ensureStylesheet(app.css);
    if (firstMount) ensureScript(app.script);
  }

  function closeSpecial(route) {
    window.dispatchEvent(new CustomEvent("roxy:child-route-closing", { detail: { route } }));
    if (route === "batch") {
      window.RoxyBatchEmbedded?.close?.({ historyBack: false });
    }
  }

  function open(route) {
    const config = CONFIG[route];
    if (!config) return false;
    if (!mount()) return false;

    if (state.route && state.route !== route) closeSpecial(state.route);
    state.route = route;
    const token = ++state.openToken;
    document.body?.classList.add("roxy-child-screen-open");
    document.body.dataset.roxyChildRoute = route;

    dom.kicker.textContent = config.kicker;
    dom.heading.textContent = config.title;
    showState("Загружаю раздел…");

    if (config.libraryTab) {
      openLibrary(config);
      return true;
    }
    if (config.batch) {
      openBatch();
      return true;
    }
    if (config.legacyApp) {
      openLegacyApp(route, config);
      return true;
    }

    window.KsuStudioShell?.open?.(config.parent);
    window.setTimeout(() => openDomRoute(route, config, token), 0);
    return true;
  }

  function close() {
    if (!state.route) return;
    const previous = state.route;
    state.route = null;
    state.openToken += 1;
    closeSpecial(previous);
    restoreMovedTarget();
    if (dom.view) {
      dom.view.hidden = true;
      dom.view.classList.remove("is-active");
      dom.body.replaceChildren();
    }
    document.body?.classList.remove("roxy-child-screen-open");
    if (document.body) delete document.body.dataset.roxyChildRoute;
  }

  function parentFor(route) {
    return CONFIG[route]?.parent || null;
  }

  function interceptLegacyLinks(event) {
    const anchor = event.target.closest?.("a[href]");
    if (!anchor) return;
    let url;
    try { url = new URL(anchor.href, window.location.href); } catch (_error) { return; }
    const route = url.pathname.endsWith("/mini-app/trends.html")
      ? "trends"
      : url.pathname.endsWith("/mini-app/prompt-tools.html")
        ? "prompt-tools"
        : url.pathname.endsWith("/mini-app/batch.html")
          ? "batch"
          : null;
    if (!route) return;
    event.preventDefault();
    window.RoxyCustomerNavigation?.open?.(route);
  }

  function init() {
    document.addEventListener("click", interceptLegacyLinks, true);
    if (mount()) return;
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      if (mount() || attempts >= 40) window.clearInterval(timer);
    }, 100);
  }

  window.RoxyChildScreens = Object.freeze({
    open,
    close,
    parentFor,
    routes: Object.freeze(Object.keys(CONFIG)),
    get route() {
      return state.route;
    },
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
