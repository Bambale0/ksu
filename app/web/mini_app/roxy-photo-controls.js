(() => {
  "use strict";

  const STORAGE_KEY = "roxy-photo-controls-v1";
  const DRAFTS_KEY = "ksu-generation-drafts-v1";
  const PHOTO_MODEL_IDS = new Set([
    "nano-banana",
    "nano-banana-edit",
    "nano-banana-pro",
    "nano-banana-2",
    "nano-banana-2-lite",
    "seedream-3-t2i",
    "seedream-4-t2i",
    "seedream-4-edit",
    "seedream-4.5-t2i",
    "seedream-4.5-edit",
    "seedream-5-lite-t2i",
    "seedream-5-lite-i2i",
    "seedream-5-pro-t2i",
    "seedream-5-pro-i2i",
    "seedream-5-pro-layers",
    "gpt-image-1.5-t2i",
    "gpt-image-1.5-i2i",
    "gpt-image-2-t2i",
    "gpt-image-2-i2i",
    "wan-2.7-image",
    "wan-2.7-image-pro",
    "grok-image-t2i",
    "grok-image-i2i",
  ]);

  const RATIO_LEGACY_NANO = options(["auto", "1:1", "9:16", "16:9", "3:4", "4:3", "3:2", "2:3", "5:4", "4:5", "21:9"]);
  const RATIO_NANO_PRO = options(["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]);
  const RATIO_NANO_2 = options(["auto", "1:1", "2:3", "3:2", "1:4", "4:1", "3:4", "4:3", "4:5", "5:4", "1:8", "8:1", "9:16", "16:9", "21:9"]);
  const RATIO_SEEDREAM = options(["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"]);
  const RATIO_GPT_15 = options(["1:1", "2:3", "3:2"]);
  const RATIO_GPT_2 = options(["auto", "1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16", "2:1", "1:2", "3:1", "1:3", "21:9", "9:21", "5:4", "4:5"]);
  const RATIO_WAN = options(["1:1", "3:4", "4:3", "1:8", "8:1", "9:16", "16:9", "21:9"]);
  const RATIO_GROK = options(["2:3", "3:2", "1:1", "9:16", "16:9"]);
  const SEEDREAM_SIZE_OPTIONS = [
    { value: "square_hd", label: "1:1" },
    { value: "portrait_4_3", label: "3:4" },
    { value: "portrait_3_2", label: "2:3" },
    { value: "portrait_16_9", label: "9:16" },
    { value: "landscape_4_3", label: "4:3" },
    { value: "landscape_3_2", label: "3:2" },
    { value: "landscape_16_9", label: "16:9" },
    { value: "landscape_21_9", label: "21:9" },
  ];
  const SEEDREAM_3_SIZE_OPTIONS = SEEDREAM_SIZE_OPTIONS.filter((item) => !["portrait_3_2", "landscape_3_2", "landscape_21_9"].includes(item.value));

  const GROUPS = {
    "nano-banana": "nano-banana",
    "nano-banana-edit": "nano-banana",
    "seedream-4-t2i": "seedream-4",
    "seedream-4-edit": "seedream-4",
    "seedream-4.5-t2i": "seedream-4.5",
    "seedream-4.5-edit": "seedream-4.5",
    "seedream-5-lite-t2i": "seedream-5-lite",
    "seedream-5-lite-i2i": "seedream-5-lite",
    "seedream-5-pro-t2i": "seedream-5-pro",
    "seedream-5-pro-i2i": "seedream-5-pro",
    "gpt-image-1.5-t2i": "gpt-image-1.5",
    "gpt-image-1.5-i2i": "gpt-image-1.5",
    "gpt-image-2-t2i": "gpt-image-2",
    "gpt-image-2-i2i": "gpt-image-2",
    "grok-image-t2i": "grok-image",
    "grok-image-i2i": "grok-image",
  };

  const CONFIG = {
    "nano-banana": {
      uploadMax: 0,
      controls: [
        select("aspect_ratio", "Соотношение сторон", RATIO_LEGACY_NANO, "1:1"),
        select("output_format", "Формат", options(["png", "jpeg"], { png: "PNG", jpeg: "JPEG" }), "png", { compact: true }),
      ],
    },
    "nano-banana-edit": {
      uploadMax: 10,
      controls: [
        select("aspect_ratio", "Соотношение сторон", RATIO_LEGACY_NANO, "1:1"),
        select("output_format", "Формат", options(["png", "jpeg"], { png: "PNG", jpeg: "JPEG" }), "png", { compact: true }),
      ],
    },
    "nano-banana-pro": {
      uploadMax: 8,
      controls: [
        select("aspect_ratio", "Соотношение сторон", RATIO_NANO_PRO, "auto"),
        segmented("resolution", "Качество", options(["1K", "2K", "4K"]), "2K"),
        select("output_format", "Формат", options(["png", "jpg"], { png: "PNG", jpg: "JPG" }), "png", { compact: true }),
      ],
    },
    "nano-banana-2": {
      uploadMax: 14,
      controls: [
        select("aspect_ratio", "Соотношение сторон", RATIO_NANO_2, "auto"),
        segmented("resolution", "Качество", options(["1K", "2K", "4K"]), "2K"),
        select("output_format", "Формат", options(["jpg", "png"], { jpg: "JPG", png: "PNG" }), "png", { compact: true }),
      ],
    },
    "nano-banana-2-lite": {
      uploadMax: 10,
      note: "Nano Banana 2 Lite генерирует в фиксированном 1K.",
      controls: [select("aspect_ratio", "Соотношение сторон", RATIO_NANO_2, "auto")],
    },
    "seedream-3-t2i": {
      uploadMax: 0,
      note: "Seedream 3.0 работает в нативном 2K.",
      controls: [select("image_size", "Соотношение сторон", SEEDREAM_3_SIZE_OPTIONS, "square_hd")],
    },
    "seedream-4-t2i": seedream4Config(0),
    "seedream-4-edit": seedream4Config(10),
    "seedream-4.5-t2i": seedream45Config(0),
    "seedream-4.5-edit": seedream45Config(14),
    "seedream-5-lite-t2i": seedream5LiteConfig(0),
    "seedream-5-lite-i2i": seedream5LiteConfig(14),
    "seedream-5-pro-t2i": seedream5ProConfig(0),
    "seedream-5-pro-i2i": seedream5ProConfig(10),
    "seedream-5-pro-layers": {
      uploadMax: 1,
      note: "Спецрежим разложения на слои использует собственный размер результата.",
      controls: [select("output_format", "Формат", options(["png", "jpeg"], { png: "PNG", jpeg: "JPEG" }), "png", { compact: true })],
    },
    "gpt-image-1.5-t2i": gpt15Config(0),
    "gpt-image-1.5-i2i": gpt15Config(16),
    "gpt-image-2-t2i": gpt2Config(0),
    "gpt-image-2-i2i": gpt2Config(16),
    "wan-2.7-image": wanConfig(false),
    "wan-2.7-image-pro": wanConfig(true),
    "grok-image-t2i": {
      uploadMax: 0,
      controls: [
        select("aspect_ratio", "Соотношение сторон", RATIO_GROK, "1:1"),
        segmented("enable_pro", "Качество", [{ value: false, label: "Быстро" }, { value: true, label: "Pro" }], false, { extra: true }),
      ],
    },
    "grok-image-i2i": {
      uploadMax: 1,
      note: "Grok Image-to-Image сам определяет формат результата по референсу.",
      controls: [],
    },
  };

  let scheduled = false;
  let values = readValues();
  const nativeFetch = window.fetch.bind(window);

  function options(items, labels = {}) {
    return items.map((value) => ({ value, label: labels[value] || value }));
  }

  function select(key, label, itemOptions, defaultValue, extra = {}) {
    return { key, label, options: itemOptions, defaultValue, kind: "select", ...extra };
  }

  function segmented(key, label, itemOptions, defaultValue, extra = {}) {
    return { key, label, options: itemOptions, defaultValue, kind: "segmented", ...extra };
  }

  function seedream4Config(uploadMax) {
    return {
      uploadMax,
      controls: [
        select("image_size", "Соотношение сторон", SEEDREAM_SIZE_OPTIONS, "square_hd"),
        segmented("image_resolution", "Качество", options(["1K", "2K", "4K"]), "2K"),
        segmented("max_images", "Сколько фото за раз", options([1, 2, 3, 4, 5, 6]), 1),
      ],
      note: "Количество автоматически передаётся модели и дублируется в служебной части промпта — руками писать число не нужно.",
    };
  }

  function seedream45Config(uploadMax) {
    return {
      uploadMax,
      controls: [
        select("aspect_ratio", "Соотношение сторон", RATIO_SEEDREAM, "1:1"),
        segmented("quality", "Качество", [{ value: "basic", label: "2K" }, { value: "high", label: "4K" }], "basic"),
      ],
    };
  }

  function seedream5LiteConfig(uploadMax) {
    return {
      uploadMax,
      controls: [
        select("aspect_ratio", "Соотношение сторон", RATIO_SEEDREAM, "1:1"),
        segmented("quality", "Качество", [{ value: "basic", label: "2K" }, { value: "high", label: "3K" }, { value: "ultra", label: "4K" }], "basic"),
        select("output_format", "Формат", options(["png", "jpeg"], { png: "PNG", jpeg: "JPEG" }), "png", { extra: true, compact: true }),
      ],
    };
  }

  function seedream5ProConfig(uploadMax) {
    return {
      uploadMax,
      controls: [
        select("aspect_ratio", "Соотношение сторон", RATIO_SEEDREAM, "1:1"),
        segmented("quality", "Качество", [{ value: "basic", label: "1K" }, { value: "high", label: "2K" }], "high"),
        select("output_format", "Формат", options(["png", "jpeg"], { png: "PNG", jpeg: "JPEG" }), "png", { compact: true }),
      ],
    };
  }

  function gpt15Config(uploadMax) {
    return {
      uploadMax,
      controls: [
        select("aspect_ratio", "Соотношение сторон", RATIO_GPT_15, "1:1"),
        segmented("quality", "Качество", [{ value: "medium", label: "Среднее" }, { value: "high", label: "Высокое" }], "medium"),
      ],
    };
  }

  function gpt2Config(uploadMax) {
    return {
      uploadMax,
      controls: [
        select("aspect_ratio", "Соотношение сторон", RATIO_GPT_2, "auto", { dependsOnResolution: true }),
        segmented("resolution", "Качество", options(["1K", "2K", "4K"]), "1K", { extra: true }),
      ],
      note: "Для 2K/4K ROXY автоматически убирает неподдерживаемые форматы.",
    };
  }

  function wanConfig(pro) {
    return {
      uploadMax: 9,
      controls: [
        select("aspect_ratio", "Соотношение сторон", RATIO_WAN, "1:1", { extra: true }),
        segmented("resolution", "Качество", options(pro ? ["1K", "2K", "4K"] : ["1K", "2K"]), "2K", { wanResolution: true }),
        segmented("n", "Сколько фото за раз", options([1, 2, 3, 4]), 1),
      ],
      note: pro ? "4K доступно только без входных фото. При добавлении референса ROXY автоматически вернёт 2K." : "Стандартная WAN 2.7 поддерживает до 2K.",
    };
  }

  function currentModelId() {
    return document.getElementById("modelSelect")?.value || localStorage.getItem("ksu-selected-model") || "";
  }

  function groupKey(modelId) {
    return GROUPS[modelId] || modelId;
  }

  function readValues() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (_error) {
      return {};
    }
  }

  function persistValues() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(values));
    } catch (_error) {
      // UI preferences are non-critical.
    }
  }

  function savedValue(modelId, control) {
    const bucket = values[groupKey(modelId)] || {};
    if (Object.prototype.hasOwnProperty.call(bucket, control.key)) return bucket[control.key];
    return control.defaultValue;
  }

  function saveValue(modelId, key, value) {
    const bucket = values[groupKey(modelId)] || {};
    bucket[key] = value;
    values[groupKey(modelId)] = bucket;
    persistValues();
  }

  function readDraft(modelId) {
    try {
      const drafts = JSON.parse(localStorage.getItem(DRAFTS_KEY) || "{}");
      return drafts?.[modelId] || null;
    } catch (_error) {
      return null;
    }
  }

  function hasSourceImages(modelId) {
    const draft = readDraft(modelId);
    if (!draft?.values) return false;
    for (const key of ["input_urls", "image_urls", "image_input", "image_url"]) {
      const value = draft.values[key];
      if (Array.isArray(value) && value.length) return true;
      if (typeof value === "string" && value) return true;
    }
    return false;
  }

  function availableOptions(modelId, control) {
    let result = [...control.options];
    if (control.dependsOnResolution) {
      const resolution = savedValue(modelId, { key: "resolution", defaultValue: "1K" });
      if (resolution === "2K" || resolution === "4K") {
        const blocked = new Set(["5:4", "4:5", "3:1", "1:3", "9:21"]);
        result = result.filter((item) => !blocked.has(String(item.value)));
      }
    }
    if (control.wanResolution && modelId === "wan-2.7-image-pro" && hasSourceImages(modelId)) {
      result = result.filter((item) => item.value !== "4K");
    }
    return result;
  }

  function normalizeSaved(modelId, control) {
    const available = availableOptions(modelId, control);
    const current = savedValue(modelId, control);
    if (available.some((item) => Object.is(item.value, current) || String(item.value) === String(current))) return current;
    const fallback = available.some((item) => String(item.value) === String(control.defaultValue))
      ? control.defaultValue
      : available[0]?.value;
    saveValue(modelId, control.key, fallback);
    return fallback;
  }

  function findNativeField(control) {
    const labels = {
      aspect_ratio: ["Соотношение сторон"],
      resolution: ["Разрешение"],
      image_resolution: ["Разрешение изображения"],
      image_size: ["Размер изображения"],
      quality: ["Качество"],
      output_format: ["Формат результата"],
      n: ["Количество вариантов"],
      max_images: ["Количество изображений"],
    }[control.key] || [];
    for (const wrapper of document.querySelectorAll("#dynamicForm .field")) {
      const label = wrapper.querySelector(".field-label")?.textContent?.trim() || "";
      if (labels.includes(label)) return wrapper;
    }
    return null;
  }

  function setNativeValue(wrapper, value) {
    const input = wrapper?.querySelector("input.input");
    if (!input) return false;
    const normalized = typeof value === "boolean" ? String(value) : String(value ?? "");
    if (input.value !== normalized) input.value = normalized;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
  }

  function triggerQuoteRefresh() {
    const prompt = [...document.querySelectorAll("#dynamicForm textarea")].find((node) => !node.classList.contains("json-input"));
    if (prompt) prompt.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function buildSelect(modelId, control, wrapper) {
    const selectEl = document.createElement("select");
    selectEl.className = "roxy-photo-select";
    selectEl.setAttribute("aria-label", control.label);
    const current = normalizeSaved(modelId, control);
    for (const item of availableOptions(modelId, control)) {
      const option = document.createElement("option");
      option.value = String(item.value);
      option.textContent = item.label;
      option.selected = String(item.value) === String(current);
      selectEl.appendChild(option);
    }
    selectEl.addEventListener("change", () => {
      const item = availableOptions(modelId, control).find((candidate) => String(candidate.value) === selectEl.value);
      const value = item?.value ?? selectEl.value;
      saveValue(modelId, control.key, value);
      if (!control.extra && setNativeValue(wrapper, value)) scheduleEnhance();
      else triggerQuoteRefresh();
      if (control.key === "resolution") scheduleEnhance();
      window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.();
    });
    return selectEl;
  }

  function buildSegments(modelId, control, wrapper) {
    const root = document.createElement("div");
    root.className = "roxy-photo-segments";
    root.setAttribute("role", "group");
    root.setAttribute("aria-label", control.label);
    const current = normalizeSaved(modelId, control);
    for (const item of availableOptions(modelId, control)) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "roxy-photo-segment";
      button.textContent = item.label;
      const active = String(item.value) === String(current);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
      button.addEventListener("click", () => {
        saveValue(modelId, control.key, item.value);
        if (!control.extra && setNativeValue(wrapper, item.value)) scheduleEnhance();
        else triggerQuoteRefresh();
        scheduleEnhance();
        window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.();
      });
      root.appendChild(button);
    }
    return root;
  }

  function enhanceNativeControl(modelId, control, wrapper) {
    if (!wrapper) return false;
    const signature = `${modelId}:${control.key}:${JSON.stringify(availableOptions(modelId, control).map((item) => item.value))}`;
    if (wrapper.dataset.roxyPhotoSignature === signature) return true;
    wrapper.dataset.roxyPhotoSignature = signature;
    wrapper.classList.add("roxy-photo-field");
    const label = wrapper.querySelector(".field-label");
    if (label) label.textContent = control.label;
    wrapper.querySelector(".roxy-photo-control")?.remove();
    const nativeInput = wrapper.querySelector("input.input");
    const dataListId = nativeInput?.getAttribute("list");
    if (nativeInput) {
      nativeInput.classList.add("roxy-photo-native-hidden");
      nativeInput.tabIndex = -1;
      const stored = normalizeSaved(modelId, control);
      if (nativeInput.value && control.options.some((item) => String(item.value) === nativeInput.value)) {
        saveValue(modelId, control.key, control.options.find((item) => String(item.value) === nativeInput.value)?.value ?? stored);
      } else if (nativeInput.value !== String(stored)) {
        setNativeValue(wrapper, stored);
      }
    }
    if (dataListId) document.getElementById(dataListId)?.setAttribute("hidden", "");
    const shell = document.createElement("div");
    shell.className = `roxy-photo-control${control.compact ? " is-compact" : ""}`;
    shell.appendChild(control.kind === "segmented" ? buildSegments(modelId, control, wrapper) : buildSelect(modelId, control, wrapper));
    wrapper.appendChild(shell);
    return true;
  }

  function ensureExtraControls(modelId, config) {
    const dynamicForm = document.getElementById("dynamicForm");
    if (!dynamicForm) return;
    const outputGroup = [...dynamicForm.querySelectorAll(".form-group")].find((group) => group.querySelector(".group-title")?.textContent?.trim() === "Результат");
    if (!outputGroup) return;
    let root = outputGroup.querySelector(":scope > .roxy-photo-extra-controls");
    if (!root) {
      root = document.createElement("div");
      root.className = "roxy-photo-extra-controls";
      outputGroup.appendChild(root);
    }
    root.replaceChildren();
    for (const control of config.controls.filter((item) => item.extra)) {
      const field = document.createElement("div");
      field.className = "field roxy-photo-field roxy-photo-extra-field";
      const label = document.createElement("label");
      label.className = "field-label";
      label.textContent = control.label;
      field.appendChild(label);
      const shell = document.createElement("div");
      shell.className = `roxy-photo-control${control.compact ? " is-compact" : ""}`;
      shell.appendChild(control.kind === "segmented" ? buildSegments(modelId, control, null) : buildSelect(modelId, control, null));
      field.appendChild(shell);
      root.appendChild(field);
    }
    root.hidden = !root.children.length;
  }

  function ensureModelNote(modelId, config) {
    let note = document.getElementById("roxyPhotoModelNote");
    if (!config.note && !config.uploadMax) {
      note?.remove();
      return;
    }
    const form = document.getElementById("dynamicForm");
    if (!form) return;
    if (!note) {
      note = document.createElement("div");
      note.id = "roxyPhotoModelNote";
      note.className = "roxy-photo-model-note";
      form.prepend(note);
    }
    const parts = [];
    if (config.uploadMax) parts.push(`Референсы: до ${config.uploadMax} фото`);
    if (config.note) parts.push(config.note);
    note.textContent = parts.join(" · ");
  }

  function prettifySummary(modelId, config) {
    const lookup = new Map();
    for (const control of config.controls) {
      const current = savedValue(modelId, control);
      const item = availableOptions(modelId, control).find((candidate) => String(candidate.value) === String(current));
      if (item) lookup.set(control.key, item.label);
    }
    for (const chip of document.querySelectorAll("#summaryChips .summary-chip")) {
      let text = chip.textContent || "";
      if (text.startsWith("Размер изображения:")) text = `Соотношение сторон: ${lookup.get("image_size") || text.split(": ")[1]}`;
      if (text.startsWith("Разрешение изображения:")) text = `Качество: ${lookup.get("image_resolution") || text.split(": ")[1]}`;
      if (text.startsWith("Количество изображений:")) text = `Фото за раз: ${lookup.get("max_images") || text.split(": ")[1]}`;
      if (text.startsWith("Количество вариантов:")) text = `Фото за раз: ${lookup.get("n") || text.split(": ")[1]}`;
      if (text.startsWith("Качество:") && lookup.has("quality")) text = `Качество: ${lookup.get("quality")}`;
      chip.textContent = text;
    }
  }

  function enhance() {
    scheduled = false;
    const modelId = currentModelId();
    const config = CONFIG[modelId];
    document.body?.classList.toggle("roxy-photo-controls-active", Boolean(config && PHOTO_MODEL_IDS.has(modelId)));
    if (!config || !PHOTO_MODEL_IDS.has(modelId)) {
      document.getElementById("roxyPhotoModelNote")?.remove();
      return;
    }
    for (const control of config.controls.filter((item) => !item.extra)) {
      enhanceNativeControl(modelId, control, findNativeField(control));
    }
    ensureExtraControls(modelId, config);
    ensureModelNote(modelId, config);
    prettifySummary(modelId, config);
  }

  function scheduleEnhance() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(enhance);
  }

  function applyExtraParameters(payload) {
    const modelId = String(payload?.model_id || "");
    const config = CONFIG[modelId];
    if (!config || !payload.parameters || typeof payload.parameters !== "object") return payload;
    for (const control of config.controls.filter((item) => item.extra)) {
      const value = normalizeSaved(modelId, control);
      if (value !== undefined && value !== null && value !== "") payload.parameters[control.key] = value;
    }
    if (modelId === "wan-2.7-image-pro" && hasSourceImages(modelId) && payload.parameters.resolution === "4K") {
      payload.parameters.resolution = "2K";
      saveValue(modelId, "resolution", "2K");
    }
    if ((modelId === "gpt-image-2-t2i" || modelId === "gpt-image-2-i2i") && ["2K", "4K"].includes(String(payload.parameters.resolution || "1K"))) {
      const blocked = new Set(["5:4", "4:5", "3:1", "1:3", "9:21"]);
      if (blocked.has(String(payload.parameters.aspect_ratio || ""))) {
        payload.parameters.aspect_ratio = "auto";
        saveValue(modelId, "aspect_ratio", "auto");
      }
    }
    return payload;
  }

  window.fetch = function roxyPhotoFetch(input, init) {
    try {
      const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
      const isGenerationWrite = url.pathname === "/api/v1/generations" || url.pathname === "/api/v1/generations/quote";
      if (!isGenerationWrite || !init?.body || typeof init.body !== "string") return nativeFetch(input, init);
      const payload = JSON.parse(init.body);
      if (!PHOTO_MODEL_IDS.has(String(payload?.model_id || ""))) return nativeFetch(input, init);
      const next = { ...init, body: JSON.stringify(applyExtraParameters(payload)) };
      return nativeFetch(input, next);
    } catch (_error) {
      return nativeFetch(input, init);
    }
  };

  const observer = new MutationObserver(scheduleEnhance);
  function init() {
    const target = document.getElementById("builderView") || document.body;
    if (target) observer.observe(target, { childList: true, subtree: true });
    document.getElementById("modelSelect")?.addEventListener("change", scheduleEnhance);
    window.addEventListener("storage", scheduleEnhance);
    window.addEventListener("roxy:route-changed", scheduleEnhance);
    window.addEventListener("roxy:shell-route-changed", scheduleEnhance);
    for (const delay of [0, 60, 180, 450, 900]) window.setTimeout(scheduleEnhance, delay);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();