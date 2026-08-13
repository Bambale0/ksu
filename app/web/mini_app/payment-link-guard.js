(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  if (!tg) return;

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

  function loadExtension(src) {
    if (document.querySelector(`script[src="${src}"]`)) return;
    const script = document.createElement("script");
    script.src = src;
    script.async = false;
    document.head.appendChild(script);
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

  loadExtension("/mini-app/primary-card-checkout.js");
  loadExtension("/mini-app/account-overview.js");
})();
