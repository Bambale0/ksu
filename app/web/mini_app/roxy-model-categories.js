(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const MEDIA_LABELS = Object.freeze({ image: "Фото", video: "Видео", audio: "Музыка" });
  const MEDIA_ICONS = Object.freeze({ image: "image", video: "create", audio: "music" });
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

  function buildTab(type) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "roxy-model-category-tab";
    button.dataset.roxyModelMedia = type;
    button.setAttribute("role", "tab");
    button.addEventListener("click", () => pickMedia(type));
    return button;
  }

  function renderTabs() {
    const tabs = ensureTabs();
    if (!tabs) return;
    const media = availableMedia();
    const existing = [...tabs.querySelectorAll("[data-roxy-model-media]")];
    const sameShape = existing.length === media.length
      && existing.every((button, index) => button.dataset.roxyModelMedia === media[index]);
    const buttons = sameShape ? existing : media.map(buildTab);
    if (!sameShape) tabs.replaceChildren(...buttons);

    buttons.forEach((button, index) => {
      const type = media[index];
      const active = type === state.activeMedia;
      const count = state.models.filter((model) => model.media_type === type).length;
      const text = `${MEDIA_LABELS[type] || type} · ${count}`;
      button.classList.toggle("is-active", active);
      if (button.getAttribute("aria-selected") !== String(active)) {
        button.setAttribute("aria-selected", String(active));
      }
      if (button.textContent !== text) button.textContent = text;
    });
  }

  function filterFamilies() {
    const familyTabs = document.getElementById("familyTabs");
    if (!familyTabs || !state.activeMedia) return;
    for (const button of familyTabs.querySelectorAll(".family-tab")) {
      const label = button.textContent?.trim() || "";
      const visible = state.models.some(
        (model) => model.media_type === state.activeMedia && familyLabel(model.family) === label,
      );
      if (button.hidden === visible) button.hidden = !visible;
      const ariaHidden = String(!visible);
      if (button.getAttribute("aria-hidden") !== ariaHidden) button.setAttribute("aria-hidden", ariaHidden);
    }
    const ariaLabel = `Семейства моделей · ${MEDIA_LABELS[state.activeMedia] || state.activeMedia}`;
    if (familyTabs.getAttribute("aria-label") !== ariaLabel) familyTabs.setAttribute("aria-label", ariaLabel);
  }

  function filterOptions() {
    const select = document.getElementById("modelSelect");
    if (!select || !state.activeMedia) return;
    for (const option of select.options) {
      const model = state.byId.get(option.value);
      const visible = !model || model.media_type === state.activeMedia;
      if (option.hidden === visible) option.hidden = !visible;
      if (option.disabled !== !visible) option.disabled = !visible;
    }
    const count = document.getElementById("modelCount");
    if (count) {
      const total = state.models.filter((model) => model.media_type === state.activeMedia).length;
      const text = `${total} моделей`;
      if (count.textContent !== text) count.textContent = text;
    }
  }

  function normalizeCreateIcons() {
    for (const card of document.querySelectorAll("[data-roxy-media]")) {
      const mediaType = card.dataset.roxyMedia;
      const label = MEDIA_LABELS[mediaType] || mediaType;
      const ariaLabel = label ? `Создать · ${label}` : "Создать";
      if (card.getAttribute("aria-label") !== ariaLabel) card.setAttribute("aria-label", ariaLabel);
      const iconNode = card.querySelector(".roxy-media-card-icon");
      if (!iconNode || iconNode.querySelector("svg")) continue;
      const icon = window.RoxyIcons?.create?.(MEDIA_ICONS[mediaType], { size: 22 });
      if (icon) iconNode.replaceChildren(icon);
    }
  }

  function syncActiveMedia() {
    const selected = state.byId.get(document.getElementById("modelSelect")?.value || "");
    if (selected?.media_type) state.activeMedia = selected.media_type;
  }

  function apply() {
    state.scheduled = false;
    normalizeCreateIcons();
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
    normalizeCreateIcons();
    void loadModels();
    const builder = document.getElementById("builderView");
    if (builder && !state.observer) {
      state.observer = new MutationObserver(scheduleApply);
      state.observer.observe(builder, { childList: true, subtree: true });
    }
    document.getElementById("modelSelect")?.addEventListener("change", scheduleApply);
    window.addEventListener("roxy:route-changed", scheduleApply);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();