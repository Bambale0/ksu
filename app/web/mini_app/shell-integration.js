(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const overlay = document.getElementById("ksuHistoryOverlay");
  const createHome = document.getElementById("createHome");
  const builder = document.getElementById("builderView");
  const detail = document.getElementById("generationDetailView");
  const builderHome = document.getElementById("builderHomeButton");
  let historyActionInFlight = false;
  let bridgedBuilder = false;

  function mountOnboarding() {
    if (!document.querySelector('link[href="/mini-app/onboarding.css"]')) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = "/mini-app/onboarding.css";
      document.head.appendChild(stylesheet);
    }
    if (document.querySelector('script[src="/mini-app/onboarding.js"]')) return;
    const script = document.createElement("script");
    script.src = "/mini-app/onboarding.js";
    script.defer = true;
    document.head.appendChild(script);
  }

  function mountPartnerCabinet() {
    if (!document.getElementById("partnerPreview")) return;
    if (document.querySelector('script[src="/mini-app/partner.js"]')) return;
    const script = document.createElement("script");
    script.src = "/mini-app/partner.js";
    script.defer = true;
    document.head.appendChild(script);
  }

  function mountProfileTools() {
    if (!document.getElementById("profileView")) return;
    if (!document.querySelector('link[href="/mini-app/profile-tools.css"]')) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = "/mini-app/profile-tools.css";
      document.head.appendChild(stylesheet);
    }
    if (document.querySelector('script[src="/mini-app/profile-tools.js"]')) return;
    const script = document.createElement("script");
    script.src = "/mini-app/profile-tools.js";
    script.defer = true;
    document.head.appendChild(script);
  }

  function mountSocialTools() {
    if (!document.querySelector('link[href="/mini-app/social.css"]')) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = "/mini-app/social.css";
      document.head.appendChild(stylesheet);
    }
    if (document.querySelector('script[src="/mini-app/social.js"]')) return;
    const script = document.createElement("script");
    script.src = "/mini-app/social.js";
    script.defer = true;
    document.head.appendChild(script);
  }

  function mountFeedTools() {
    if (!document.querySelector('link[href="/mini-app/feed.css"]')) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = "/mini-app/feed.css";
      document.head.appendChild(stylesheet);
    }
    if (document.querySelector('script[src="/mini-app/feed.js"]')) return;
    const script = document.createElement("script");
    script.src = "/mini-app/feed.js";
    script.defer = true;
    document.head.appendChild(script);
  }

  function mountPromoRecovery() {
    if (!document.querySelector('link[href="/mini-app/promo-recovery.css"]')) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = "/mini-app/promo-recovery.css";
      document.head.appendChild(stylesheet);
    }
    if (document.querySelector('script[src="/mini-app/promo-recovery.js"]')) return;
    const script = document.createElement("script");
    script.src = "/mini-app/promo-recovery.js";
    script.defer = true;
    document.head.appendChild(script);
  }

  function mountStudioShell() {
    if (!document.querySelector('link[href="/mini-app/studio-shell.css"]')) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = "/mini-app/studio-shell.css";
      document.head.appendChild(stylesheet);
    }
    if (document.querySelector('script[src="/mini-app/studio-shell.js"]')) return;
    const script = document.createElement("script");
    script.src = "/mini-app/studio-shell.js";
    script.defer = true;
    document.head.appendChild(script);
  }

  function mountStudioWorkspace() {
    if (!document.querySelector('link[href="/mini-app/studio-workspace.css"]')) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = "/mini-app/studio-workspace.css";
      document.head.appendChild(stylesheet);
    }
    if (document.querySelector('script[src="/mini-app/studio-workspace.js"]')) return;
    const script = document.createElement("script");
    script.src = "/mini-app/studio-workspace.js";
    script.defer = true;
    document.head.appendChild(script);
  }

  function mountRoxyBrand() {
    if (!document.querySelector('link[href="/mini-app/roxy-brand.css"]')) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = "/mini-app/roxy-brand.css";
      document.head.appendChild(stylesheet);
    }
    if (document.querySelector('script[src="/mini-app/roxy-brand.js"]')) return;
    const script = document.createElement("script");
    script.src = "/mini-app/roxy-brand.js";
    script.defer = true;
    document.head.appendChild(script);
  }

  mountOnboarding();
  mountPartnerCabinet();
  mountProfileTools();
  mountSocialTools();
  mountFeedTools();
  mountPromoRecovery();
  mountStudioShell();
  mountStudioWorkspace();
  mountRoxyBrand();

  if (!overlay || !createHome || !builder) return;

  function historyNavIsActive() {
    return document.querySelector('[data-shell-nav="history"].is-active') !== null;
  }

  function syncMainButtonScope() {
    if (!builder.hidden) return;
    try {
      tg?.MainButton?.hide?.();
    } catch (_error) {
      // MainButton is optional outside supported Telegram clients.
    }
  }

  function switchToCreateShell() {
    const createNav = document.querySelector('.bottom-nav-item[data-shell-nav="create"]');
    createNav?.click();
    createHome.hidden = true;
    builder.hidden = false;
    if (detail) detail.hidden = true;
    bridgedBuilder = true;
    try {
      tg?.BackButton?.show?.();
    } catch (_error) {
      // Older clients can ignore BackButton chrome.
    }
    history.pushState({ ksuShellBridge: "builder" }, "");
    requestAnimationFrame(() => {
      const heading = builder.querySelector("h1");
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
      }
      window.scrollTo({ top: 0, behavior: "auto" });
    });
  }

  function closeBridgedBuilder() {
    if (!bridgedBuilder) return;
    bridgedBuilder = false;
    builder.hidden = true;
    createHome.hidden = false;
    if (detail) detail.hidden = true;
    syncMainButtonScope();
    try {
      tg?.BackButton?.hide?.();
    } catch (_error) {
      // No-op outside supported Telegram clients.
    }
  }

  overlay.addEventListener(
    "click",
    (event) => {
      const action = event.target.closest(".ksu-history-action");
      if (!action) return;
      const label = (action.textContent || "").trim().toLowerCase();
      if (label.startsWith("открыть") || label.startsWith("повторить")) {
        historyActionInFlight = true;
      }
    },
    true,
  );

  const historyObserver = new MutationObserver(() => {
    if (!overlay.hidden || !historyActionInFlight || !historyNavIsActive()) return;
    historyActionInFlight = false;
    switchToCreateShell();
  });
  historyObserver.observe(overlay, { attributes: true, attributeFilter: ["hidden"] });

  const builderObserver = new MutationObserver(syncMainButtonScope);
  builderObserver.observe(builder, { attributes: true, attributeFilter: ["hidden"] });
  syncMainButtonScope();

  builderHome?.addEventListener("click", () => {
    if (bridgedBuilder) closeBridgedBuilder();
  });

  document.addEventListener(
    "click",
    (event) => {
      const nav = event.target.closest(".bottom-nav-item[data-shell-nav]");
      if (nav && bridgedBuilder) closeBridgedBuilder();
    },
    true,
  );

  tg?.BackButton?.onClick?.(() => {
    if (!bridgedBuilder) return;
    closeBridgedBuilder();
  });

  window.addEventListener("popstate", (event) => {
    if (bridgedBuilder && event.state?.ksuShellBridge !== "builder") closeBridgedBuilder();
  });
})();