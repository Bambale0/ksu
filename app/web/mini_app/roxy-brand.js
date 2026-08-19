(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const BRAND = "ROXY";
  const BRAND_LOGO_SRC = "/mini-app/assets/roxy-rx-logo-v5.webp?v=5";

  function mountLayer({ css, js }) {
    if (css && !document.querySelector(`link[href="${css}"]`)) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = css;
      document.head.appendChild(stylesheet);
    }
    if (!js || document.querySelector(`script[src="${js}"]`)) return;
    const script = document.createElement("script");
    script.src = js;
    script.defer = true;
    script.async = false;
    document.head.appendChild(script);
  }

  function mountProductLayers() {
    mountLayer({ css: "/mini-app/roxy-boot-logo-v5.css" });
    mountLayer({ js: "/mini-app/roxy-icons.js" });
    mountLayer({ js: "/mini-app/roxy-generation-context.js" });
    mountLayer({ js: "/mini-app/roxy-author-profile.js" });
    mountLayer({ css: "/mini-app/roxy-child-screens.css", js: "/mini-app/roxy-child-screens.js" });
    mountLayer({ css: "/mini-app/roxy-customer-navigation.css", js: "/mini-app/roxy-customer-navigation.js" });
    mountLayer({ css: "/mini-app/roxy-discovery.css", js: "/mini-app/roxy-discovery.js" });
    mountLayer({ css: "/mini-app/roxy-create-center.css", js: "/mini-app/roxy-create-center.js" });
    mountLayer({ css: "/mini-app/roxy-music.css", js: "/mini-app/roxy-music.js" });
    mountLayer({ css: "/mini-app/roxy-profile-cabinet.css", js: "/mini-app/roxy-profile-cabinet.js" });
    mountLayer({ css: "/mini-app/roxy-parity-navigation.css", js: "/mini-app/roxy-parity-navigation.js" });
    mountLayer({ css: "/mini-app/roxy-history-management.css", js: "/mini-app/roxy-history-management.js" });
    mountLayer({ js: "/mini-app/roxy-preset-editor.js" });
    mountLayer({ js: "/mini-app/roxy-notification-badge-bridge.js" });
    mountLayer({ css: "/mini-app/roxy-fhd-density.css" });
    mountLayer({ css: "/mini-app/roxy-home-density-v3.css" });
    mountLayer({ css: "/mini-app/roxy-mobile-runtime.css", js: "/mini-app/roxy-mobile-runtime.js" });
    mountLayer({ css: "/mini-app/roxy-mature-ui.css" });
    mountLayer({ css: "/mini-app/roxy-approved-theme.css", js: "/mini-app/roxy-approved-home.js" });
    mountLayer({ css: "/mini-app/roxy-approved-surfaces.css" });
    mountLayer({ css: "/mini-app/roxy-client-feedback.css" });
    mountLayer({ css: "/mini-app/roxy-unified-controls.css" });
    mountLayer({ css: "/mini-app/roxy-partner-promo.css?v=5", js: "/mini-app/roxy-partner-promo.js?v=5" });
    mountLayer({ css: "/mini-app/roxy-iphone-polish.css", js: "/mini-app/roxy-model-categories.js" });
    mountLayer({ css: "/mini-app/roxy-header-logo.css?v=5" });
  }

  function setTelegramChrome() {
    try {
      tg?.setHeaderColor?.("#0B0B10");
      tg?.setBackgroundColor?.("#0B0B10");
      tg?.setBottomBarColor?.("#0B0B10");
    } catch (_error) {
      // Progressive enhancement for older Telegram clients.
    }
  }

  function setText(selector, text, root = document) {
    const node = root.querySelector(selector);
    if (!node || node.textContent === text) return node;
    node.textContent = text;
    return node;
  }

  function ensureBrandLogo(selector, root = document) {
    const mark = root.querySelector(selector);
    if (!mark) return null;

    let logo = mark.querySelector("img[data-roxy-brand-logo]");
    if (!logo) {
      logo = document.createElement("img");
      logo.alt = "";
      logo.className = "roxy-brand-mark-logo";
      logo.dataset.roxyBrandLogo = "true";
      logo.setAttribute("aria-hidden", "true");
      mark.replaceChildren(logo);
    }
    if (logo.getAttribute("src") !== BRAND_LOGO_SRC) logo.src = BRAND_LOGO_SRC;
    logo.width = 256;
    logo.height = 256;
    logo.decoding = "async";
    logo.loading = "eager";
    return mark;
  }

  function styleMainBrand() {
    const headerBrand = document.getElementById("brandHomeButton");
    if (headerBrand) {
      ensureBrandLogo(".brand-mark", headerBrand);
      setText(".brand-copy strong", BRAND, headerBrand);
      setText(".brand-copy small", "AI CREATIVE STUDIO", headerBrand);
      headerBrand.setAttribute("aria-label", "На главную ROXY");
    }

    const sidebar = document.getElementById("studioSidebar");
    if (sidebar) {
      ensureBrandLogo(".studio-sidebar-mark", sidebar);
      setText(".studio-sidebar-copy strong", BRAND, sidebar);
      setText(".studio-sidebar-copy small", "AI CREATIVE STUDIO", sidebar);
      sidebar.setAttribute("aria-label", "Навигация ROXY Studio");
    }
  }

  function styleHomeHero() {
    const home = document.getElementById("createHome");
    const hero = home?.querySelector(".hero-card");
    const copy = hero?.querySelector(".hero-copy");
    if (!home || !hero || !copy) return;

    setText(".eyebrow", "ROXY · AI CREATIVE STUDIO", hero);
    setText(".hero-copy h1", "Привет! Это ROXY ✨", hero);
    setText(".hero-copy p", "Твори. Генерируй. Зарабатывай.", hero);
    document.getElementById("roxyHomeBalance")?.remove();

    let cta = document.getElementById("roxyCreateCta");
    if (!cta) {
      cta = document.createElement("button");
      cta.type = "button";
      cta.className = "roxy-create-cta";
      cta.id = "roxyCreateCta";
      cta.textContent = "✦ Создать";
      cta.addEventListener("click", () => {
        try { tg?.HapticFeedback?.impactOccurred?.("medium"); } catch (_error) { /* optional */ }
        if (window.RoxyCustomerNavigation?.open) {
          window.RoxyCustomerNavigation.open("create");
          return;
        }
        if (window.KsuStudioShell?.open) {
          window.KsuStudioShell.open("create");
          return;
        }
        document.querySelector('[data-shell-nav="create"]')?.click();
      });
    }
    if (cta.parentElement !== copy) copy.appendChild(cta);
  }

  function arrangeHomeDashboard() {
    const home = document.getElementById("createHome");
    const families = home?.querySelector('.home-section[aria-labelledby="familiesHeading"]');
    const promo = document.getElementById("roxyPromoSection");
    if (!home || !families || !promo) return;
    if (families.nextElementSibling !== promo) families.insertAdjacentElement("afterend", promo);
  }

  function styleWalletCopy() {
    const walletNote = document.querySelector("#walletHero small");
    if (walletNote) walletNote.textContent = "Внутренняя валюта ROXY";
  }

  function refreshBrandChrome() {
    document.documentElement.classList.add("roxy-brand-ready");
    document.body?.classList.add("roxy-brand-ready");
    if (document.title !== "ROXY · AI Creative Studio") document.title = "ROXY · AI Creative Studio";
    styleMainBrand();
    styleHomeHero();
    arrangeHomeDashboard();
    styleWalletCopy();
  }

  function scheduleRefreshes() {
    for (const delay of [0, 80, 180, 420, 900, 1600]) {
      window.setTimeout(refreshBrandChrome, delay);
    }
  }

  function init() {
    mountProductLayers();
    setTelegramChrome();
    refreshBrandChrome();
    scheduleRefreshes();
    tg?.onEvent?.("activated", refreshBrandChrome);
    window.addEventListener("roxy:shell-route-changed", refreshBrandChrome);
    window.addEventListener("roxy:route-changed", refreshBrandChrome);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
