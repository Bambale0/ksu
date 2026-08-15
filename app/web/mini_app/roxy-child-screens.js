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
  });

  const state = {
    mounted: false,
    route: null,
    target: null,
    placeholder: null,
    openToken: 0,
  };
  const dom = {};

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
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

  function closeSpecial(route) {
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
    delete document.body?.dataset.roxyChildRoute;
  }

  function parentFor(route) {
    return CONFIG[route]?.parent || null;
  }

  function init() {
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
