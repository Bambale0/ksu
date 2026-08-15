(() => {
  "use strict";

  const state = {
    sourceObserver: null,
    navObserver: null,
    frame: 0,
  };

  function mountStylesheet(href) {
    if (document.querySelector(`link[href="${href}"]`)) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    document.head.appendChild(link);
  }

  function mountReferenceHomeLayer() {
    const js = "/mini-app/roxy-reference-home.js";
    mountStylesheet("/mini-app/roxy-reference-home.css");
    mountStylesheet("/mini-app/roxy-reference-order.css");
    if (!document.querySelector(`script[src="${js}"]`)) {
      const script = document.createElement("script");
      script.src = js;
      script.defer = true;
      document.head.appendChild(script);
    }
  }

  function unreadValue() {
    const source = document.getElementById("profileUnreadBadge");
    if (!source || source.hidden) return 0;
    const raw = String(source.textContent || "0").trim();
    if (raw.endsWith("+")) return Number.parseInt(raw, 10) || 0;
    return Math.max(0, Number.parseInt(raw, 10) || 0);
  }

  function sync() {
    state.frame = 0;
    const value = unreadValue();
    document.querySelectorAll('[data-roxy-customer-route="profile"]').forEach((nav) => {
      let badge = nav.querySelector(".profile-nav-badge");
      if (value <= 0) {
        badge?.remove();
        return;
      }
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "profile-nav-badge";
        badge.setAttribute("aria-hidden", "true");
        nav.appendChild(badge);
      }
      badge.textContent = value > 9 ? "9+" : String(value);
    });
  }

  function schedule() {
    if (state.frame) return;
    state.frame = window.requestAnimationFrame(sync);
  }

  function attachSource() {
    if (state.sourceObserver) return true;
    const source = document.getElementById("profileUnreadBadge");
    if (!source) return false;
    state.sourceObserver = new MutationObserver(schedule);
    state.sourceObserver.observe(source, {
      childList: true,
      characterData: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["hidden"],
    });
    schedule();
    return true;
  }

  function attachNavigation() {
    if (state.navObserver) return true;
    const nav = document.getElementById("studioBottomNav");
    if (!nav) return false;
    state.navObserver = new MutationObserver(schedule);
    state.navObserver.observe(nav, { childList: true, subtree: true });
    schedule();
    return true;
  }

  function init() {
    mountReferenceHomeLayer();
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      const sourceReady = attachSource();
      const navReady = attachNavigation();
      if ((sourceReady && navReady) || attempts >= 80) window.clearInterval(timer);
    }, 100);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
