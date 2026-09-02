(() => {
  const state = { promptVisible: false };
  window.__roxyPublishPrivacy = state;

  function findPromptToggle() {
    const rows = Array.from(document.querySelectorAll("label.toggle-row"));
    return rows.find((row) => /Показать описание|Показать промпт|Скрыть промпт/.test(row.textContent || "")) || null;
  }

  function readPromptVisibility() {
    const row = findPromptToggle();
    const input = row?.querySelector('input[type="checkbox"]');
    if (!row || !input) return false;
    const text = row.textContent || "";
    if (/Скрыть промпт/.test(text)) return !input.checked;
    return Boolean(input.checked);
  }

  function syncPromptVisibility() {
    state.promptVisible = readPromptVisibility();
  }

  document.addEventListener(
    "change",
    (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) return;
      if (!target.closest("label.toggle-row")) return;
      syncPromptVisibility();
    },
    true,
  );

  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    try {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      const isPublish = /\/api\/v1\/feed\/[^/]+\/publish(?:\?|$)/.test(url);
      if (isPublish && typeof init.body === "string") {
        const body = JSON.parse(init.body);
        state.promptVisible = readPromptVisibility();
        body.prompt_visible = state.promptVisible;
        init = { ...init, body: JSON.stringify(body) };
      }
    } catch (_) {
      // Privacy-safe fallback: if this compatibility layer cannot read the UI,
      // keep publishing functional and never expose a prompt accidentally.
      try {
        if (typeof init.body === "string") {
          const body = JSON.parse(init.body);
          body.prompt_visible = false;
          init = { ...init, body: JSON.stringify(body) };
        }
      } catch (_) {}
    }
    return nativeFetch(input, init);
  };

  syncPromptVisibility();
  new MutationObserver(syncPromptVisibility).observe(document.documentElement, { childList: true, subtree: true });
})();
