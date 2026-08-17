(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const MEDIA_LABELS = Object.freeze({ image: "Фото", video: "Видео", audio: "Музыка" });
  const FAMILY_LABELS = Object.freeze({
    nanobanana: "Nano Banana",
    seedream: "Seedream",
    "gpt-image": "GPT Image",
    wan: "Wan",
    seedance: "Seedance",
    kling: "Kling Motion",
    grok: "Grok",
  });

  const state = {
    models: [],
    byId: new Map(),
    activeMedia: null,
    observer: null,
    scheduled: false,
  };

  function familyLabel(family) {
    return FAMILY_LABELS[family] || family;
  }

  function categoryOrder(type) {
    return { image: 0, video: 1, audio: 2 }[type] ?? 99;
  }

  async function loadModels() {
    try {
      const headers = { Accept: "application/json" };
      if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
      const response = await fetch("/api/v1/generations/models", {
        headers,
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) return;
      const payload = await response.json();
      state.models = Array.isArray(payload?.models) ? payload.models : [];
      state.byId = new Map(state.models.map((model) => [model.id, model]));
      const selected = state.byId.get(document.getElementById("modelSelect")?.value || "");
      state.activeMedia = selected?.media_type || state.models[0]?.media_type || null;
      apply();
    } catch (_error) {
      // Core builder already remains fully functional without this presentation layer.
    }
  }

  function availableMedia() {
    return [...new Set(state.models.map((model) => model.media_type).filter(Boolean))]
      .sort((a, b) => categoryOrder(a) - categoryOrder(b));
  }

  function ensureTabs() {
    const familyTabs = document.getElementById("familyTabs");
    if (!familyTabs || !state.models.length) return null;
    let tabs = document.getElementById("roxyModelCategoryTabs");
    if (tabs) return tabs;

    tabs = document.createElement("div");
    tabs.id = "roxyModelCategoryTabs";
    tabs.className = "roxy-model-category-tabs";
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "Категории моделей");
    familyTabs.insertAdjacentElement("beforebegin", tabs);
    return tabs;
  }

  function pickMedia(mediaType) {
    const model = state.models.find((item) => item.media_type === mediaType);
    if (!model) return;
    state.activeMedia = mediaType;
    const familyTabs = document.getElementById("familyTabs");
    const targetFamilyLabel = familyLabel(model.family);
    const familyButton = [...(familyTabs?.querySelectorAll(".family-tab") || [])]
      .find((button) => button.textContent?.trim() === targetFamilyLabel);

    try { tg?.HapticFeedback?.selectionChanged?.(); } catch (_error) { /* optional */ }
    if (familyButton) familyButton.click();
    window.setTimeout(() => {
      const select = document.getElementById("modelSelect");
      if (!select) return;
      const option = [...select.options].find((item) => item.value === model.id);
      if (option) {
        select.value = model.id;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
      scheduleApply();
    }, 0);
  }

  function renderTabs() {
    const tabs = ensureTabs();
    if (!tabs) return;
    const media = availableMedia();
    tabs.replaceChildren(...media.map((type) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `roxy-model-category-tab${type === state.activeMedia ? " is-active" : ""}`;
      button.dataset.roxyModelMedia = type;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", String(type === state.activeMedia));
      const count = state.models.filter((model) => model.media_type === type).length;
      button.textContent = `${MEDIA_LABELS[type] || type} · ${count}`;
      button.addEventListener("click", () => pickMedia(type));
      return button;
    }));
  }

  function filterFamilies() {
    const familyTabs = document.getElementById("familyTabs");
    if (!familyTabs || !state.activeMedia) return;
    for (const button of familyTabs.querySelectorAll(".family-tab")) {
      const label = button.textContent?.trim() || "";
      const visible = state.models.some(
        (model) => model.media_type === state.activeMedia && familyLabel(model.family) === label,
      );
      button.hidden = !visible;
      button.setAttribute("aria-hidden", String(!visible));
    }
    familyTabs.setAttribute("aria-label", `Семейства моделей · ${MEDIA_LABELS[state.activeMedia] || state.activeMedia}`);
  }

  function filterOptions() {
    const select = document.getElementById("modelSelect");
    if (!select || !state.activeMedia) return;
    let visibleCount = 0;
    for (const option of select.options) {
      const model = state.byId.get(option.value);
      const visible = !model || model.media_type === state.activeMedia;
      option.hidden = !visible;
      option.disabled = !visible;
      if (visible) visibleCount += 1;
    }
    const count = document.getElementById("modelCount");
    if (count) {
      const total = state.models.filter((model) => model.media_type === state.activeMedia).length;
      count.textContent = `${total} моделей`;
    }
  }

  function syncActiveMedia() {
    const selected = state.byId.get(document.getElementById("modelSelect")?.value || "");
    if (selected?.media_type) state.activeMedia = selected.media_type;
  }

  function apply() {
    state.scheduled = false;
    if (!state.models.length) return;
    syncActiveMedia();
    renderTabs();
    filterFamilies();
    filterOptions();
  }

  function scheduleApply() {
    if (state.scheduled) return;
    state.scheduled = true;
    window.requestAnimationFrame(apply);
  }

  function init() {
    void loadModels();
    const builder = document.getElementById("builderView");
    if (builder && !state.observer) {
      state.observer = new MutationObserver(scheduleApply);
      state.observer.observe(builder, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden", "aria-selected"] });
    }
    document.getElementById("modelSelect")?.addEventListener("change", scheduleApply);
    window.addEventListener("roxy:route-changed", scheduleApply);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
