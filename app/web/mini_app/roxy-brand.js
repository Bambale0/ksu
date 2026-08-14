(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const BRAND = "ROXY";
  const BRAND_RE = /Ксю|КСЮ/g;
  const BRAND_TEST_RE = /Ксю|КСЮ/;
  let observer = null;
  let balanceObserver = null;
  let rateObserver = null;
  let brandFrame = 0;
  const pendingBrandRoots = new Set();

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
    document.head.appendChild(script);
  }

  function mountProductLayers() {
    mountLayer({
      css: "/mini-app/roxy-customer-navigation.css",
      js: "/mini-app/roxy-customer-navigation.js",
    });
    mountLayer({
      css: "/mini-app/roxy-discovery.css",
      js: "/mini-app/roxy-discovery.js",
    });
    mountLayer({
      css: "/mini-app/roxy-create-center.css",
      js: "/mini-app/roxy-create-center.js",
    });
    mountLayer({
      css: "/mini-app/roxy-music.css",
      js: "/mini-app/roxy-music.js",
    });
    mountLayer({
      css: "/mini-app/roxy-profile-cabinet.css",
      js: "/mini-app/roxy-profile-cabinet.js",
    });
    // Mount last: acceptance CSS intentionally owns final safe-area/keyboard/mobile
    // overrides without changing the product architecture of any feature surface.
    mountLayer({
      css: "/mini-app/roxy-mobile-runtime.css",
      js: "/mini-app/roxy-mobile-runtime.js",
    });
  }

  function setTelegramChrome() {
    try {
      tg?.setHeaderColor?.("#09080f");
      tg?.setBackgroundColor?.("#09080f");
      tg?.setBottomBarColor?.("#09080f");
    } catch (_error) {
      // Brand chrome is progressive enhancement; older Telegram clients can ignore it.
    }
  }

  function replaceBrandString(value) {
    return typeof value === "string" ? value.replace(BRAND_RE, BRAND) : value;
  }

  function replaceTextNode(node) {
    const parent = node?.parentElement;
    if (!parent || parent.closest("script,style,textarea")) return;
    const value = node.nodeValue || "";
    if (BRAND_TEST_RE.test(value)) node.nodeValue = replaceBrandString(value);
  }

  function replaceBrandAttributes(element) {
    if (!element?.getAttribute) return;
    for (const attribute of ["aria-label", "title", "placeholder"]) {
      const current = element.getAttribute(attribute);
      if (!current || !BRAND_TEST_RE.test(current)) continue;
      element.setAttribute(attribute, replaceBrandString(current));
    }
  }

  function replaceBrandText(root = document.body) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      replaceTextNode(root);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) return;
    if (root.nodeType === Node.ELEMENT_NODE) {
      if (root.closest("script,style,textarea")) return;
      replaceBrandAttributes(root);
    }

    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || parent.closest("script,style,textarea")) return NodeFilter.FILTER_REJECT;
        return BRAND_TEST_RE.test(node.nodeValue || "") ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(replaceTextNode);

    const elements = root.querySelectorAll?.("[aria-label], [title], [placeholder]") || [];
    elements.forEach(replaceBrandAttributes);
  }

  function setText(selector, text, root = document) {
    const node = root.querySelector(selector);
    if (!node || node.textContent === text) return node;
    node.textContent = text;
    return node;
  }

  function styleMainBrand() {
    const headerBrand = document.getElementById("brandHomeButton");
    if (headerBrand) {
      setText(".brand-mark", "X", headerBrand);
      setText(".brand-copy strong", BRAND, headerBrand);
      setText(".brand-copy small", "AI CREATIVE STUDIO", headerBrand);
      if (headerBrand.getAttribute("aria-label") !== "На главную ROXY") {
        headerBrand.setAttribute("aria-label", "На главную ROXY");
      }
    }

    const sidebar = document.getElementById("studioSidebar");
    if (sidebar) {
      setText(".studio-sidebar-mark", "X", sidebar);
      setText(".studio-sidebar-copy strong", BRAND, sidebar);
      setText(".studio-sidebar-copy small", "AI CREATIVE STUDIO", sidebar);
      if (sidebar.getAttribute("aria-label") !== "Навигация ROXY Studio") {
        sidebar.setAttribute("aria-label", "Навигация ROXY Studio");
      }
    }
  }

  function styleHomeHero() {
    const home = document.getElementById("createHome");
    if (!home) return;
    const hero = home.querySelector(".hero-card");
    if (!hero) return;
    setText(".eyebrow", "ROXY · AI CREATIVE STUDIO", hero);
    setText(".hero-copy h1", "Привет! Это ROXY ✨", hero);
    setText(".hero-copy p", "Твори. Генерируй. Зарабатывай.", hero);

    if (!document.getElementById("roxyHomeBalance")) {
      const card = document.createElement("section");
      card.className = "roxy-home-balance";
      card.id = "roxyHomeBalance";
      const label = document.createElement("span");
      label.className = "roxy-home-balance-label";
      label.textContent = "Баланс";
      const value = document.createElement("strong");
      value.className = "roxy-home-balance-value";
      value.id = "roxyHomeBalanceValue";
      value.textContent = "—";
      const note = document.createElement("small");
      note.className = "roxy-home-balance-note";
      note.textContent = "ROX · курс обновляется автоматически";
      card.append(label, value, note);
      hero.insertAdjacentElement("afterend", card);
    }

    if (!document.getElementById("roxyCreateCta")) {
      const cta = document.createElement("button");
      cta.type = "button";
      cta.className = "roxy-create-cta";
      cta.id = "roxyCreateCta";
      cta.textContent = "✦  СОЗДАТЬ";
      cta.addEventListener("click", () => {
        try {
          tg?.HapticFeedback?.impactOccurred?.("medium");
        } catch (_error) {
          // Optional Telegram haptics.
        }
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
      const balance = document.getElementById("roxyHomeBalance");
      balance?.insertAdjacentElement("afterend", cta);
    }
  }

  function roxBalanceText(value) {
    return String(value || "—").trim().replace(/\s*кр\.?$/i, " ROX");
  }

  function roxRateText(value) {
    const raw = String(value || "").trim();
    return raw ? raw.replace(/кр\./i, "ROX") : "ROX · курс обновляется автоматически";
  }

  function syncHomeBalance() {
    const source = document.getElementById("balanceValue");
    const target = document.getElementById("roxyHomeBalanceValue");
    if (!source || !target) return;
    const update = () => {
      const next = roxBalanceText(source.textContent);
      if (target.textContent !== next) target.textContent = next;
    };
    update();
    if (balanceObserver) return;
    balanceObserver = new MutationObserver(update);
    balanceObserver.observe(source, { childList: true, characterData: true, subtree: true });
  }

  function syncHomeRate() {
    const source = document.getElementById("paymentRateLabel");
    const target = document.querySelector(".roxy-home-balance-note");
    if (!source || !target) return;
    const update = () => {
      const next = roxRateText(source.textContent);
      if (target.textContent !== next) target.textContent = next;
    };
    update();
    if (rateObserver) return;
    rateObserver = new MutationObserver(update);
    rateObserver.observe(source, { childList: true, characterData: true, subtree: true });
  }

  function styleWalletCopy() {
    const walletNote = document.querySelector("#walletHero small");
    if (walletNote && walletNote.textContent !== "Внутренние кредиты ROXY") {
      walletNote.textContent = "Внутренние кредиты ROXY";
    }
  }

  function refreshBrandChrome() {
    document.documentElement.classList.add("roxy-brand-ready");
    document.body?.classList.add("roxy-brand-ready");
    if (document.title) document.title = replaceBrandString(document.title);
    styleMainBrand();
    styleHomeHero();
    styleWalletCopy();
    syncHomeBalance();
    syncHomeRate();
  }

  function apply() {
    refreshBrandChrome();
    replaceBrandText(document.body);
  }

  function queueBrandRoot(node) {
    if (!node) return;
    if (node.nodeType === Node.TEXT_NODE || node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.DOCUMENT_FRAGMENT_NODE) {
      pendingBrandRoots.add(node);
    }
  }

  function flushDynamicBranding() {
    brandFrame = 0;
    refreshBrandChrome();
    for (const root of pendingBrandRoots) replaceBrandText(root);
    pendingBrandRoots.clear();
  }

  function scheduleDynamicBranding(mutations) {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) queueBrandRoot(node);
    }
    if (!pendingBrandRoots.size || brandFrame) return;
    brandFrame = window.requestAnimationFrame(flushDynamicBranding);
  }

  function init() {
    mountProductLayers();
    setTelegramChrome();
    apply();
    if (observer || !document.body) return;
    // Dynamic product surfaces are branded incrementally. Do not rescan the full body
    // on balance/progress/text updates: that used to create persistent main-thread jank.
    observer = new MutationObserver(scheduleDynamicBranding);
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
