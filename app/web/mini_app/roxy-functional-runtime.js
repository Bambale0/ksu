(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const nativeReplaceState = window.history.replaceState.bind(window.history);
  let notificationObserver = null;

  function randomUuid() {
    const cryptoApi = globalThis.crypto;
    if (
      typeof cryptoApi?.randomUUID === "function"
      && cryptoApi.randomUUID !== randomUuid
    ) {
      return cryptoApi.randomUUID();
    }
    const bytes = new Uint8Array(16);
    if (cryptoApi?.getRandomValues) {
      cryptoApi.getRandomValues(bytes);
    } else {
      for (let index = 0; index < bytes.length; index += 1) {
        bytes[index] = Math.floor(Math.random() * 256);
      }
    }
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map((item) => item.toString(16).padStart(2, "0"));
    return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
  }

  function installRandomUuidFallback() {
    if (!globalThis.crypto || typeof globalThis.crypto.randomUUID === "function") return;
    try {
      Object.defineProperty(globalThis.crypto, "randomUUID", {
        configurable: true,
        enumerable: false,
        value: randomUuid,
      });
    } catch (_error) {
      // Modules added after this runtime should use RoxyFunctionalRuntime.requestId.
    }
  }

  async function copyText(value) {
    const text = String(value ?? "");
    if (!text) return false;
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (_error) {
        // Telegram iOS/Android WebViews can expose Clipboard API but reject writes.
      }
    }

    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    let copied = false;
    try { copied = document.execCommand("copy"); } catch (_error) { copied = false; }
    area.remove();
    if (copied) return true;

    try {
      tg?.showPopup?.({ title: "Текст", message: text.slice(0, 4000), buttons: [{ type: "close" }] });
      return Boolean(tg?.showPopup);
    } catch (_error) {
      return false;
    }
  }

  function protectCanonicalHistory() {
    window.history.replaceState = function replaceState(data, title, url) {
      const current = window.history.state;
      const topLevelLegacyShellWrite = Boolean(
        data?.ksuShell
        && !data?.nested
        && current?.roxyNavigation
        && window.RoxyCustomerNavigation,
      );
      if (topLevelLegacyShellWrite) return;
      nativeReplaceState(data, title, url);
    };
  }

  function routeCatalogControl(event) {
    const control = event.target.closest?.(
      "#roxyCatalogView .roxy-template-card, #roxyCatalogView .roxy-catalog-quick-card, #roxyCatalogView .text-button",
    );
    if (!control) return;
    const text = (control.textContent || "").toLowerCase();
    let route = null;
    if (control.classList.contains("roxy-template-card") || text.includes("тренд")) route = "trends";
    else if (text.includes("prompt")) route = "prompt-tools";
    if (!route || !window.RoxyCustomerNavigation?.open) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    window.RoxyCustomerNavigation.open(route);
  }

  function patchReadNotifications(root = document) {
    const nodes = [];
    if (root instanceof Element && root.matches("button.notification-item")) nodes.push(root);
    root.querySelectorAll?.("button.notification-item")?.forEach((node) => nodes.push(node));
    for (const button of nodes) {
      const unread = button.classList.contains("is-unread");
      button.disabled = !unread;
      if (unread) {
        button.removeAttribute("aria-disabled");
        button.removeAttribute("tabindex");
      } else {
        button.setAttribute("aria-disabled", "true");
        button.tabIndex = -1;
      }
    }
  }

  function observeNotificationSemantics() {
    patchReadNotifications(document);
    if (notificationObserver || !document.body) return;
    notificationObserver = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "attributes") patchReadNotifications(record.target);
        for (const node of record.addedNodes || []) {
          if (node instanceof Element) patchReadNotifications(node);
        }
      }
    });
    notificationObserver.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class"],
    });
  }

  async function interceptPromptToolCopy(event) {
    const button = event.target.closest?.(".tool-copy-button");
    if (!button) return;
    const value = button.closest(".tool-result-block")?.querySelector("p")?.textContent || "";
    event.preventDefault();
    event.stopImmediatePropagation();
    button.disabled = true;
    const original = button.textContent || "Копировать";
    const copied = await copyText(value);
    button.textContent = copied ? "Скопировано ✓" : "Не удалось скопировать";
    window.setTimeout(() => {
      button.textContent = original;
      button.disabled = false;
    }, 1200);
  }

  function addKeyboardParity(event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    const card = event.target.closest?.('[role="button"]');
    if (!card || card.matches("button,a,input,select,textarea")) return;
    event.preventDefault();
    card.click();
  }

  function initDomRuntime() {
    observeNotificationSemantics();
    document.addEventListener("click", routeCatalogControl, true);
    document.addEventListener("click", (event) => { void interceptPromptToolCopy(event); }, true);
    document.addEventListener("keydown", addKeyboardParity);
  }

  window.RoxyFunctionalRuntime = Object.freeze({
    requestId: randomUuid,
    copyText,
    patchReadNotifications,
  });

  // Critical compatibility patches must run during this defer script itself. Waiting for
  // DOMContentLoaded would let app.js/shell.js mutate history or request UUIDs first.
  installRandomUuidFallback();
  protectCanonicalHistory();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initDomRuntime, { once: true });
  } else {
    initDomRuntime();
  }
})();