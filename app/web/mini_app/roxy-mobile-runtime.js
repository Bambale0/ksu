(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const vv = window.visualViewport ?? null;
  const state = {
    nestedVisible: false,
    keyboardOpen: false,
    bodyObserver: null,
    surfaceObserver: null,
    surfaceRoots: new Set(),
    scrollTimer: null,
    backFrame: 0,
  };

  const FOCUSABLE_INPUTS = new Set(["INPUT", "TEXTAREA", "SELECT"]);
  const NAV_MUTATION_SELECTOR = "#builderView, #generationDetailView, #feedOverlay, dialog";

  function px(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) && number > 0 ? `${Math.round(number)}px` : "0px";
  }

  function setVar(name, value) {
    const root = document.documentElement;
    if (root.style.getPropertyValue(name) !== value) root.style.setProperty(name, value);
  }

  function syncTelegramMetrics() {
    const safe = tg?.safeAreaInset || {};
    const content = tg?.contentSafeAreaInset || {};
    setVar("--roxy-safe-top", px(safe.top));
    setVar("--roxy-safe-right", px(safe.right));
    setVar("--roxy-safe-bottom", px(safe.bottom));
    setVar("--roxy-safe-left", px(safe.left));
    setVar("--roxy-content-safe-top", px(content.top));
    setVar("--roxy-content-safe-right", px(content.right));
    setVar("--roxy-content-safe-bottom", px(content.bottom));
    setVar("--roxy-content-safe-left", px(content.left));

    const stable = Number(tg?.viewportStableHeight || 0);
    if (stable > 0) setVar("--roxy-stable-height", `${Math.round(stable)}px`);
    document.documentElement.dataset.roxyPlatform = String(tg?.platform || "web").toLowerCase();
  }

  function focusedControl() {
    const active = document.activeElement;
    return active && FOCUSABLE_INPUTS.has(active.tagName) ? active : null;
  }

  function keyboardHeight() {
    if (!vv) return 0;
    return Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
  }

  function keepFocusedControlVisible() {
    const control = focusedControl();
    if (!control || !state.keyboardOpen) return;
    window.clearTimeout(state.scrollTimer);
    state.scrollTimer = window.setTimeout(() => {
      const rect = control.getBoundingClientRect();
      const visibleBottom = vv ? vv.height + vv.offsetTop : window.innerHeight;
      const topGuard = 72;
      const bottomGuard = 24;
      if (rect.bottom > visibleBottom - bottomGuard || rect.top < topGuard) {
        control.scrollIntoView({ block: "center", behavior: "smooth" });
      }
    }, 80);
  }

  function syncKeyboard() {
    const height = keyboardHeight();
    const open = height >= 120 && focusedControl() !== null;
    state.keyboardOpen = open;
    setVar("--roxy-keyboard-height", `${Math.round(height)}px`);
    document.body?.classList.toggle("roxy-keyboard-open", open);
    if (open) keepFocusedControlVisible();
  }

  function nestedVisible() {
    const builder = document.getElementById("builderView");
    const detail = document.getElementById("generationDetailView");
    const feed = document.getElementById("feedOverlay");
    const dialog = document.querySelector("dialog[open]");
    return Boolean(
      (builder && !builder.hidden)
      || (detail && !detail.hidden)
      || (feed && !feed.hidden)
      || dialog,
    );
  }

  function walletVisible() {
    const wallet = document.querySelector('.app-view[data-view="wallet"]');
    return Boolean(wallet && !wallet.hidden);
  }

  function activeRoute() {
    if (document.body?.classList.contains("roxy-discovery-catalog-open")) return "catalog";
    if (document.body?.classList.contains("roxy-create-center-open")) return "create";
    if (walletVisible()) return "wallet";
    return window.RoxyCustomerNavigation?.active || "home";
  }

  function syncNestedSnapshot() {
    state.nestedVisible = nestedVisible();
  }

  function syncBackButton() {
    const back = tg?.BackButton;
    if (!back) return;
    attachSurfaceObservers();
    syncNestedSnapshot();
    const route = activeRoute();
    const visible = state.nestedVisible || route !== "home";
    try {
      if (visible) back.show();
      else back.hide();
    } catch (_error) {
      // Telegram clients older than BackButton support keep native close behavior.
    }
  }

  function scheduleBackSync() {
    if (state.backFrame) return;
    state.backFrame = window.requestAnimationFrame(() => {
      state.backFrame = 0;
      syncBackButton();
    });
  }

  function hideKeyboardForNavigation() {
    const control = focusedControl();
    if (control) control.blur();
    try {
      tg?.hideKeyboard?.();
    } catch (_error) {
      // hideKeyboard was added after the original Mini App API and is optional.
    }
    window.requestAnimationFrame(syncKeyboard);
  }

  function onBackButton() {
    // shell.js and Feed own nested history. The snapshot covers the case where their
    // handler runs first and closes synchronously; the direct check covers a just-opened
    // nested surface before the scoped observer has published the next snapshot.
    if (state.nestedVisible || nestedVisible()) return;
    const route = activeRoute();
    if (route === "home") return;
    hideKeyboardForNavigation();

    // Primary ROXY navigation seeds and owns browser history entries. Using the same
    // history stack here keeps Telegram BackButton and browser Back behavior identical.
    if (window.history.state?.roxyNavigation) {
      window.history.back();
      scheduleBackSync();
      return;
    }

    // Fail-safe for legacy entry points that predate the route-history owner.
    if (route === "wallet") {
      window.RoxyCustomerNavigation?.open?.("profile", { feedback: false, historyMode: "replace" });
    } else {
      window.RoxyCustomerNavigation?.open?.("home", { feedback: false, historyMode: "replace" });
    }
    scheduleBackSync();
  }

  function markPerformanceClass() {
    const cores = Number(navigator.hardwareConcurrency || 0);
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    const constrainedAndroid = String(tg?.platform || "").toLowerCase() === "android"
      && cores > 0
      && cores <= 4;
    document.documentElement.classList.toggle("roxy-low-motion", Boolean(reduce || constrainedAndroid));
  }

  function onDocumentClick(event) {
    const routeButton = event.target.closest?.("[data-roxy-customer-route], [data-shell-nav]");
    if (!routeButton) return;
    hideKeyboardForNavigation();
    scheduleBackSync();
    window.setTimeout(syncBackButton, 80);
  }

  function onFocusIn(event) {
    if (!FOCUSABLE_INPUTS.has(event.target?.tagName)) return;
    window.setTimeout(syncKeyboard, 40);
    window.setTimeout(keepFocusedControlVisible, 180);
  }

  function onFocusOut() {
    window.setTimeout(syncKeyboard, 80);
  }

  function bindTelegram() {
    try {
      tg?.ready?.();
      tg?.expand?.();
    } catch (_error) {
      // Browser preview and older Telegram versions may not expose these methods.
    }
    tg?.BackButton?.onClick?.(onBackButton);
    for (const eventName of [
      "viewportChanged",
      "safeAreaChanged",
      "contentSafeAreaChanged",
      "fullscreenChanged",
      "activated",
    ]) {
      tg?.onEvent?.(eventName, () => {
        syncTelegramMetrics();
        syncKeyboard();
        syncBackButton();
      });
    }
  }

  function nodeAffectsNavigation(node) {
    if (!(node instanceof Element)) return false;
    return node.matches(NAV_MUTATION_SELECTOR) || Boolean(node.querySelector?.(NAV_MUTATION_SELECTOR));
  }

  function mutationAffectsNavigation(mutation) {
    if (mutation.type === "attributes") {
      return mutation.target === document.body && mutation.attributeName === "class";
    }
    return [...mutation.addedNodes, ...mutation.removedNodes].some(nodeAffectsNavigation);
  }

  function surfaceRoots() {
    return [
      document.getElementById("builderView"),
      document.getElementById("generationDetailView"),
      document.getElementById("feedOverlay"),
      ...document.querySelectorAll("dialog"),
    ].filter(Boolean);
  }

  function attachSurfaceObservers() {
    if (!state.surfaceObserver) {
      state.surfaceObserver = new MutationObserver(scheduleBackSync);
    }
    for (const root of surfaceRoots()) {
      if (state.surfaceRoots.has(root)) continue;
      state.surfaceRoots.add(root);
      state.surfaceObserver.observe(root, {
        attributes: true,
        attributeFilter: root.tagName === "DIALOG" ? ["open"] : ["hidden"],
      });
    }
  }

  function attachBodyObserver() {
    if (state.bodyObserver || !document.body) return;
    state.bodyObserver = new MutationObserver((mutations) => {
      if (!mutations.some(mutationAffectsNavigation)) return;
      attachSurfaceObservers();
      scheduleBackSync();
    });
    state.bodyObserver.observe(document.body, {
      childList: true,
      attributes: true,
      attributeFilter: ["class"],
    });
  }

  function init() {
    document.documentElement.classList.add("roxy-mobile-runtime");
    document.body?.classList.add("roxy-mobile-runtime");
    syncTelegramMetrics();
    markPerformanceClass();
    syncNestedSnapshot();
    syncKeyboard();
    bindTelegram();
    attachSurfaceObservers();
    attachBodyObserver();
    syncBackButton();

    vv?.addEventListener("resize", syncKeyboard, { passive: true });
    vv?.addEventListener("scroll", syncKeyboard, { passive: true });
    window.addEventListener("resize", () => {
      syncTelegramMetrics();
      syncKeyboard();
      syncBackButton();
    }, { passive: true });
    window.addEventListener("orientationchange", () => window.setTimeout(() => {
      syncTelegramMetrics();
      syncKeyboard();
      syncBackButton();
    }, 120), { passive: true });
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);
    document.addEventListener("click", onDocumentClick, true);
  }

  window.RoxyMobileRuntime = Object.freeze({
    sync: () => {
      syncTelegramMetrics();
      syncKeyboard();
      syncBackButton();
    },
    get keyboardOpen() {
      return state.keyboardOpen;
    },
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
