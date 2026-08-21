(() => {
  const state = { hidePrompt: true };
  window.__roxyPublishPrivacy = state;

  function bindPromptToggle(label) {
    if (!label || label.dataset.roxyPrivacyReady === "true") return;
    const strong = label.querySelector("strong");
    const small = label.querySelector("small");
    const input = label.querySelector('input[type="checkbox"]');
    if (!input) return;

    label.dataset.roxyPrivacyReady = "true";
    label.dataset.roxyHidePrompt = "true";
    if (strong) strong.textContent = "Скрыть промпт";
    if (small) small.textContent = "Включено — prompt не будет виден в публикации";
    input.checked = state.hidePrompt;
  }

  function polishPreviewPrivacy() {
    document.querySelectorAll(".preview-card .panel").forEach((panel) => {
      const rows = Array.from(panel.querySelectorAll("label.toggle-row"));
      const promptRow = rows.find((row) => /Показать промпт|Скрыть промпт/.test(row.textContent || ""));
      const referenceRow = rows.find((row) => /Показать референсы/.test(row.textContent || ""));
      if (referenceRow) referenceRow.remove();
      bindPromptToggle(promptRow);
    });
  }

  document.addEventListener(
    "change",
    (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) return;
      if (!target.closest('[data-roxy-hide-prompt="true"]')) return;
      state.hidePrompt = Boolean(target.checked);
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
        body.prompt_visible = !state.hidePrompt;
        body.references_visible = false;
        init = { ...init, body: JSON.stringify(body) };
      }
    } catch (_) {
      // Keep publishing functional even if an old WebView cannot parse something here.
    }
    return nativeFetch(input, init);
  };

  polishPreviewPrivacy();
  new MutationObserver(polishPreviewPrivacy).observe(document.documentElement, { childList: true, subtree: true });
})();
