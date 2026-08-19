(() => {
  "use strict";

  function loadStyle(href) {
    if (document.querySelector(`link[href="${href}"]`)) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    document.head.appendChild(link);
  }

  function loadExtension(src, onload = null) {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      if (onload) {
        if (existing.dataset.loaded === "true") onload();
        else existing.addEventListener("load", onload, { once: true });
      }
      return existing;
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = false;
    script.addEventListener("load", () => {
      script.dataset.loaded = "true";
      onload?.();
    }, { once: true });
    document.head.appendChild(script);
    return script;
  }

  // Product payment assets are part of the Mini App surface, not of Telegram
  // authorization itself. Mount them even in browser preview/fallback mode so
  // the wallet never falls back to the legacy multi-provider appearance.
  loadStyle("/mini-app/payment-surface.css");
  loadExtension("/mini-app/primary-card-checkout.js", () => {
    loadExtension("/mini-app/payment-surface.js");
  });

  const tg = window.Telegram?.WebApp;
  if (!tg) return;

  // Account data is authenticated and remains Telegram-scoped.
  loadExtension("/mini-app/account-overview.js");

  let directUserActivation = false;

  function isAllowedPaymentUrl(rawUrl) {
    try {
      const parsed = new URL(String(rawUrl), window.location.href);
      return parsed.protocol === "https:";
    } catch (_error) {
      return false;
    }
  }

  function withDirectActivation(callback) {
    return function guardedPaymentOpen(rawUrl, ...rest) {
      if (!directUserActivation || !isAllowedPaymentUrl(rawUrl)) return false;
      return callback.call(this, rawUrl, ...rest);
    };
  }

  function markActivation() {
    directUserActivation = true;
    queueMicrotask(() => {
      directUserActivation = false;
    });
  }

  window.addEventListener("click", markActivation, true);
  window.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") markActivation();
  }, true);

  if (typeof tg.openLink === "function") tg.openLink = withDirectActivation(tg.openLink);
  if (typeof tg.openTelegramLink === "function") {
    tg.openTelegramLink = withDirectActivation(tg.openTelegramLink);
  }

  window.KsuPaymentLinkGuard = Object.freeze({
    isAllowedPaymentUrl,
  });
})();
