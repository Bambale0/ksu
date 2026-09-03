(() => {
  if (window.__roxyUnpublishFeedbackPreflight) return;

  const WRONG = "Работа опубликована в профиле";
  const SUCCESS = "Публикация убрана";
  const WINDOW_MS = 10000;
  const originalFetch = window.fetch.bind(window);
  let removeSucceededAt = 0;
  let correctionPending = false;

  const requestUrl = (input) => {
    if (typeof input === "string" || input instanceof URL) return String(input);
    return input && typeof input.url === "string" ? input.url : "";
  };
  const requestMethod = (input, init) => String(
    (init && init.method) || (typeof Request !== "undefined" && input instanceof Request ? input.method : "GET")
  ).toUpperCase();
  const isRemove = (input, init) => {
    if (requestMethod(input, init) !== "POST") return false;
    try {
      const url = new URL(requestUrl(input), window.location.href);
      return /^\/api\/v1\/feed\/[^/]+\/remove$/.test(url.pathname);
    } catch {
      return false;
    }
  };
  const correct = () => {
    if (!correctionPending) return;
    if (!removeSucceededAt || Date.now() - removeSucceededAt > WINDOW_MS) {
      correctionPending = false;
      return;
    }
    const toast = document.querySelector('.toast[role="status"]');
    if (!toast || String(toast.textContent || "").trim() !== WRONG) return;
    toast.textContent = SUCCESS;
    toast.dataset.roxyUnpublishFeedback = "true";
    correctionPending = false;
  };

  window.fetch = async (input, init) => {
    const removing = isRemove(input, init);
    const response = await originalFetch(input, init);
    if (removing && response.ok) {
      removeSucceededAt = Date.now();
      correctionPending = true;
      queueMicrotask(correct);
    }
    return response;
  };

  const installObserver = () => {
    const root = document.documentElement;
    if (!root) return;
    const observer = new MutationObserver(correct);
    observer.observe(root, { childList: true, subtree: true, characterData: true });
    window.__roxyUnpublishFeedbackPreflight.observer = observer;
  };

  window.__roxyUnpublishFeedbackPreflight = { observer: null };
  if (document.documentElement) installObserver();
  else document.addEventListener("DOMContentLoaded", installObserver, { once: true });
})();
