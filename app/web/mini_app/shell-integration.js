(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const overlay = document.getElementById("ksuHistoryOverlay");
  const createHome = document.getElementById("createHome");
  const builder = document.getElementById("builderView");
  const detail = document.getElementById("generationDetailView");
  let historyActionInFlight = false;
  let bridgedBuilder = false;

  if (!overlay || !createHome || !builder) return;

  function historyNavIsActive() {
    return document.querySelector('[data-shell-nav="history"].is-active') !== null;
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

  const observer = new MutationObserver(() => {
    if (!overlay.hidden || !historyActionInFlight || !historyNavIsActive()) return;
    historyActionInFlight = false;
    switchToCreateShell();
  });
  observer.observe(overlay, { attributes: true, attributeFilter: ["hidden"] });

  tg?.BackButton?.onClick?.(() => {
    if (!bridgedBuilder) return;
    closeBridgedBuilder();
  });

  window.addEventListener("popstate", (event) => {
    if (bridgedBuilder && event.state?.ksuShellBridge !== "builder") closeBridgedBuilder();
  });
})();
