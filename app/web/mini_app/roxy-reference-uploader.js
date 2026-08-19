(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const DRAFTS_KEY = "ksu-generation-drafts-v1";
  const FALLBACK_IMAGE_VARIANTS = {
    "nano-banana": "nano-banana-edit",
    "seedream-4-t2i": "seedream-4-edit",
    "seedream-4.5-t2i": "seedream-4.5-edit",
    "seedream-5-lite-t2i": "seedream-5-lite-i2i",
    "seedream-5-pro-t2i": "seedream-5-pro-i2i",
    "gpt-image-1.5-t2i": "gpt-image-1.5-i2i",
    "gpt-image-2-t2i": "gpt-image-2-i2i",
    "grok-image-t2i": "grok-image-i2i",
    "wan-2.7-t2v": "wan-2.7-i2v",
    "grok-video-t2v": "grok-video-i2v",
  };

  const state = {
    models: [],
    modelById: new Map(),
    loaded: false,
    scheduled: false,
    formObserver: null,
    builderObserver: null,
  };

  function apiHeaders() {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function loadModels() {
    if (state.loaded) return;
    const response = await fetch("/api/v1/generations/models", {
      credentials: "same-origin",
      cache: "no-store",
      headers: apiHeaders(),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.models = Array.isArray(payload?.models) ? payload.models : [];
    state.modelById = new Map(state.models.map((model) => [model.id, model]));
    state.loaded = true;
  }

  function selectedModelId() {
    return document.getElementById("modelSelect")?.value || localStorage.getItem("ksu-selected-model") || "";
  }

  function imageFields(model) {
    return (model?.ui_schema?.fields || []).filter((field) => {
      if (!["file", "files"].includes(field.control)) return false;
      return String(field.accept || "").split(",").some((item) => item.trim().startsWith("image/"));
    });
  }

  function imageTarget(model) {
    if (!model) return null;
    if (imageFields(model).length) return model;
    const fallbackId = FALLBACK_IMAGE_VARIANTS[model.id];
    return fallbackId ? state.modelById.get(fallbackId) || null : null;
  }

  function semanticLabel(field, mediaType) {
    const name = String(field?.name || "");
    if (name === "last_frame_url") return "Последний кадр";
    if (["first_frame_url", "first_frame"].includes(name)) return "Первый кадр";
    if (name === "reference_image") return "Фото-референс";
    if (name === "reference_image_urls") return "Фото-референсы";
    if (["image_urls", "input_urls", "image_input", "image_url"].includes(name)) {
      return mediaType === "video" ? "Фото-референсы" : "Добавить фото";
    }
    return field?.label || "Добавить фото";
  }

  function preferredFields(model) {
    const fields = imageFields(model);
    const priority = new Map([
      ["reference_image_urls", 0],
      ["reference_image", 1],
      ["image_urls", 2],
      ["input_urls", 3],
      ["image_input", 4],
      ["image_url", 5],
      ["first_frame_url", 6],
      ["first_frame", 7],
      ["last_frame_url", 8],
    ]);
    return [...fields].sort((a, b) => (priority.get(a.name) ?? 50) - (priority.get(b.name) ?? 50));
  }

  function matchingScenario(model, field) {
    const items = model?.ui_schema?.scenario?.items || [];
    return items.find((item) => (item.visible_fields || []).includes(field.name)) || null;
  }

  function waitFor(predicate, timeout = 2200) {
    return new Promise((resolve) => {
      const started = performance.now();
      const tick = () => {
        const value = predicate();
        if (value) return resolve(value);
        if (performance.now() - started >= timeout) return resolve(null);
        window.setTimeout(tick, 35);
      };
      tick();
    });
  }

  function setStatus(message, error = false) {
    const status = document.getElementById("roxyReferenceUploadStatus");
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("is-error", error);
  }

  function findFieldWrapper(field) {
    const fields = [...document.querySelectorAll("#dynamicForm .field")];
    return fields.find((wrapper) => {
      const label = wrapper.querySelector(".field-label")?.textContent?.trim() || "";
      return label === String(field.label || "").trim();
    }) || null;
  }

  async function selectTarget(target) {
    const select = document.getElementById("modelSelect");
    if (!select || !target) return false;
    if (select.value === target.id) return true;

    const prompt = [...document.querySelectorAll("#dynamicForm textarea")]
      .find((node) => !node.classList.contains("json-input"))?.value || "";
    const option = [...select.options].find((item) => item.value === target.id);
    if (!option) return false;

    select.value = target.id;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    const switched = await waitFor(() => document.getElementById("modelSelect")?.value === target.id);
    if (!switched) return false;

    if (prompt) {
      const nextPrompt = await waitFor(() => [...document.querySelectorAll("#dynamicForm textarea")]
        .find((node) => !node.classList.contains("json-input")));
      if (nextPrompt && !nextPrompt.value) {
        nextPrompt.value = prompt;
        nextPrompt.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
    return true;
  }

  async function selectScenario(target, field) {
    const scenario = matchingScenario(target, field);
    if (!scenario) return true;
    const items = target.ui_schema?.scenario?.items || [];
    const index = items.findIndex((item) => item.id === scenario.id);
    const buttons = [...document.querySelectorAll("#scenarioBlock .segmented button")];
    const button = buttons[index];
    if (!button) return false;
    if (!button.classList.contains("active")) {
      button.click();
      await waitFor(() => findFieldWrapper(field));
    }
    return true;
  }

  async function openPicker(target, field) {
    setStatus("Открываю выбор фото…");
    const selected = await selectTarget(target);
    if (!selected) {
      setStatus("Не удалось переключить модель в режим с фото-референсом.", true);
      return;
    }
    await selectScenario(target, field);

    const wrapper = await waitFor(() => findFieldWrapper(field));
    const input = wrapper?.querySelector('input[type="file"]')
      || [...document.querySelectorAll('#dynamicForm input[type="file"]')]
        .find((node) => String(node.accept || "").includes("image"));
    if (!input) {
      setStatus("Поле загрузки не найдено. Обнови экран и попробуй ещё раз.", true);
      return;
    }
    wrapper?.classList.remove("roxy-native-source-hidden");
    setStatus("Выбери фото из галереи или файлов.");
    input.click();
  }

  function readReferenceCount(target) {
    try {
      const drafts = JSON.parse(localStorage.getItem(DRAFTS_KEY) || "{}");
      const values = drafts?.[target.id]?.values || {};
      let count = 0;
      for (const field of imageFields(target)) {
        const value = values[field.name];
        if (Array.isArray(value)) count += value.length;
        else if (value) count += 1;
      }
      return count;
    } catch (_error) {
      return 0;
    }
  }

  function promoteNativeReferences() {
    const groups = [...document.querySelectorAll("#dynamicForm .form-group")];
    const references = groups.find((group) => group.querySelector(".group-title")?.textContent?.trim() === "Референсы");
    if (!references) return;
    references.classList.add("roxy-reference-native-group");
    references.querySelectorAll(".roxy-native-source-hidden").forEach((node) => node.classList.remove("roxy-native-source-hidden"));
    references.querySelectorAll(".field").forEach((field) => {
      const file = field.querySelector('input[type="file"]');
      if (!file || !String(file.accept || "").includes("image")) return;
      field.classList.add("roxy-reference-native-image-field");
      const upload = field.querySelector(".upload-button");
      if (upload) upload.textContent = "Выбрать фото";
      const url = field.querySelector(".upload-url");
      if (url) url.placeholder = "или вставьте ссылку на фото";
    });
  }

  function appendUploadAction(actions, target, field, model, usedLabels) {
    const label = semanticLabel(field, model.media_type);
    if (usedLabels.has(label)) return;
    usedLabels.add(label);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "roxy-reference-upload-button";
    const plus = document.createElement("span");
    plus.setAttribute("aria-hidden", "true");
    plus.textContent = "＋";
    const copy = document.createElement("strong");
    copy.textContent = label;
    button.append(plus, copy);
    button.addEventListener("click", () => void openPicker(target, field));
    actions.appendChild(button);
  }

  function render() {
    state.scheduled = false;
    const builder = document.getElementById("builderView");
    const column = builder?.querySelector(".builder-main-column");
    const settings = builder?.querySelector(".settings-card");
    const model = state.modelById.get(selectedModelId());
    if (!builder || builder.hidden || !column || !settings || !model) {
      document.getElementById("roxyReferenceUploadPanel")?.remove();
      return;
    }

    const target = imageTarget(model);
    const fields = target ? preferredFields(target) : [];
    if (!target || !fields.length) {
      document.getElementById("roxyReferenceUploadPanel")?.remove();
      promoteNativeReferences();
      return;
    }

    let panel = document.getElementById("roxyReferenceUploadPanel");
    if (!panel) {
      panel = document.createElement("section");
      panel.id = "roxyReferenceUploadPanel";
      panel.className = "roxy-reference-upload-panel";
    }
    if (settings.previousElementSibling !== panel) column.insertBefore(panel, settings);
    panel.replaceChildren();

    const head = document.createElement("div");
    head.className = "roxy-reference-upload-head";
    const copy = document.createElement("div");
    const kicker = document.createElement("span");
    kicker.className = "section-kicker";
    kicker.textContent = model.media_type === "video" ? "Референсы для видео" : "Фото-референсы";
    const title = document.createElement("strong");
    title.textContent = "Добавь изображение, а не описывай его словами";
    copy.append(kicker, title);
    head.appendChild(copy);
    panel.appendChild(head);

    const hint = document.createElement("p");
    hint.className = "roxy-reference-upload-hint";
    hint.textContent = model.media_type === "video"
      ? "Можно загрузить фото персонажа, стиль, первый или последний кадр — ROXY сама выберет нужный режим модели."
      : "Можно загрузить одно или несколько фото. Если модели нужен отдельный Image-to-Image/Edit режим, ROXY переключит его автоматически.";
    panel.appendChild(hint);

    const actions = document.createElement("div");
    actions.className = "roxy-reference-upload-actions";
    const usedLabels = new Set();
    for (const field of fields) appendUploadAction(actions, target, field, model, usedLabels);
    panel.appendChild(actions);

    const count = readReferenceCount(target);
    const status = document.createElement("div");
    status.id = "roxyReferenceUploadStatus";
    status.className = "roxy-reference-upload-status";
    status.textContent = count ? `Добавлено фото: ${count}. Можно добавить ещё или удалить ниже.` : "Фото пока не добавлены.";
    panel.appendChild(status);

    promoteNativeReferences();
  }

  function schedule() {
    if (state.scheduled) return;
    state.scheduled = true;
    window.requestAnimationFrame(render);
  }

  function installObservers() {
    const builder = document.getElementById("builderView");
    const form = document.getElementById("dynamicForm");
    if (form && !state.formObserver) {
      state.formObserver = new MutationObserver(schedule);
      state.formObserver.observe(form, { childList: true, subtree: true });
    }
    if (builder && !state.builderObserver) {
      state.builderObserver = new MutationObserver(schedule);
      state.builderObserver.observe(builder, { attributes: true, attributeFilter: ["hidden"] });
    }
    document.getElementById("modelSelect")?.addEventListener("change", schedule);
    window.addEventListener("roxy:route-changed", schedule);
    window.addEventListener("roxy:shell-route-changed", schedule);
    tg?.onEvent?.("activated", schedule);
  }

  async function init() {
    try {
      await loadModels();
    } catch (_error) {
      return;
    }
    installObservers();
    schedule();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else void init();
})();