(() => {
  "use strict";

  const STORAGE_KEY = "roxy-video-controls-v1";
  const DRAFTS_KEY = "ksu-generation-drafts-v1";
  const VIDEO_MODEL_IDS = new Set([
    "wan-2.7-t2v",
    "wan-2.7-i2v",
    "wan-2.7-video-edit",
    "wan-2.7-r2v",
    "seedance-1.5-pro",
    "seedance-2.0",
    "seedance-2.0-fast",
    "seedance-2.0-mini",
    "seedance-2.5",
    "kling-3.0",
    "kling-motion-2.6",
    "kling-motion-3.0",
    "veo-3.1",
    "gemini-omni-video",
    "grok-video-t2v",
    "grok-video-i2v",
    "grok-video-1.5",
    "grok-video-upscale",
    "grok-video-extend",
  ]);

  const GROUPS = {
    "seedance-2.0": "seedance-2",
    "seedance-2.0-fast": "seedance-2",
    "seedance-2.0-mini": "seedance-2",
    "seedance-2.5": "seedance-2",
    "kling-motion-2.6": "kling-motion",
    "kling-motion-3.0": "kling-motion",
    "grok-video-t2v": "grok-video",
    "grok-video-i2v": "grok-video",
  };

  const RATIO_VIDEO = options(["16:9", "9:16", "1:1"]);
  const RATIO_GROK = options(["2:3", "3:2", "1:1", "9:16", "16:9"]);
  const RES_HD = options(["720p", "1080p"]);
  const RES_GROK = options(["480p", "720p"]);

  const CONFIG = {
    "wan-2.7-t2v": {
      note: "WAN 2.7 Text-to-Video: формат, качество и длина передаются отдельными параметрами — писать их в промпте не нужно.",
      controls: [
        segmented("resolution", "Качество", RES_HD, "1080p"),
        select("ratio", "Соотношение сторон", RATIO_VIDEO, "16:9", { nativeIndex: 1 }),
        durationControl(1, 30, [5, 10, 15, 20, 30], 5),
      ],
      hide: [{ label: "Соотношение сторон", index: 0 }],
    },
    "wan-2.7-i2v": {
      note: "Выбери режим выше: первый кадр, первый + последний или продолжение видео. Эти режимы нельзя смешивать.",
      controls: [
        segmented("resolution", "Качество", RES_HD, "1080p"),
        durationControl(1, 30, [5, 10, 15, 20, 30], 5),
      ],
    },
    "wan-2.7-video-edit": {
      note: "WAN Video Edit принимает исходное видео и опциональный референс. Аудио сохраняется автоматически.",
      controls: [
        segmented("resolution", "Качество", RES_HD, "1080p"),
        select("aspect_ratio", "Соотношение сторон", RATIO_VIDEO, "16:9"),
        durationControl(1, 60, [5, 10, 15, 30, 60], 5),
        segmented("audio_setting", "Аудио", [{ value: "auto", label: "Сохранить автоматически" }], "auto", { extra: true }),
      ],
      hide: [{ label: "Настройки аудио", index: 0 }],
    },
    "wan-2.7-r2v": {
      note: "Reference-to-Video поддерживает несколько фото и видео-референсов, первый кадр и референс голоса.",
      controls: [
        segmented("resolution", "Качество", RES_HD, "1080p"),
        select("aspect_ratio", "Соотношение сторон", RATIO_VIDEO, "16:9"),
        durationControl(1, 30, [5, 10, 15, 20, 30], 5),
      ],
      custom: "wanR2v",
      hide: [
        { label: "Референс-изображение", index: 0 },
        { label: "Референс-видео", index: 0 },
      ],
    },
    "seedance-1.5-pro": {
      note: "Seedance 1.5 Pro принимает до двух изображений и отдельно управляет камерой и генерацией звука.",
      controls: [
        segmented("resolution", "Качество", RES_HD, "720p"),
        select("aspect_ratio", "Соотношение сторон", RATIO_VIDEO, "1:1"),
        durationControl(1, 30, [5, 8, 10, 15, 20, 30], 8),
      ],
    },
    "seedance-2.0": seedance2Config(),
    "seedance-2.0-fast": seedance2Config("Fast"),
    "seedance-2.0-mini": seedance2Config("Mini"),
    "seedance-2.5": seedance2Config("2.5"),
    "kling-3.0": {
      note: "Kling 3.0: Std / Pro / 4K, 3–15 секунд, звук, мультишот и до трёх @element-референсов — всё настраивается здесь.",
      controls: [
        segmented("mode", "Качество", [
          { value: "std", label: "Std" },
          { value: "pro", label: "Pro" },
          { value: "4K", label: "4K" },
        ], "pro"),
        select("aspect_ratio", "Соотношение сторон", RATIO_VIDEO, "16:9"),
        durationControl(3, 15, [3, 5, 8, 10, 12, 15], 5),
      ],
      custom: "kling3",
      hide: [
        { label: "Sound", index: 0 },
        { label: "Multi Shots", index: 0 },
        { label: "Multi Prompt", index: 0 },
        { label: "Kling Elements", index: 0 },
      ],
    },
    "kling-motion-2.6": motionConfig(false),
    "kling-motion-3.0": motionConfig(true),
    "veo-3.1": {
      note: "Veo 3.1 использует отдельный Kie Veo API. Режим, вариант модели и формат результата выбираются явно.",
      controls: [
        segmented("veo_model", "Модель", [
          { value: "veo3", label: "Quality" },
          { value: "veo3_fast", label: "Fast" },
          { value: "veo3_lite", label: "Lite" },
        ], "veo3_fast", { extra: true }),
        segmented("generation_type", "Режим", [
          { value: "TEXT_2_VIDEO", label: "Текст / кадр" },
          { value: "FIRST_AND_LAST_FRAMES_2_VIDEO", label: "Первый + последний" },
          { value: "REFERENCE_2_VIDEO", label: "Референсы" },
        ], "TEXT_2_VIDEO", { extra: true }),
        select("aspect_ratio", "Соотношение сторон", [
          { value: "auto", label: "Авто" },
          ...RATIO_VIDEO.filter((item) => item.value !== "1:1"),
        ], "16:9"),
      ],
      custom: "veo",
      hide: [
        { label: "Veo Model", index: 0 },
        { label: "Generation Type", index: 0 },
        { label: "Enable Fallback", index: 0 },
        { label: "Enable Translation", index: 0 },
      ],
    },
    "gemini-omni-video": {
      note: "Gemini Omni: изображения + 2×видео + персонажи должны укладываться в квоту 7; видео — максимум одно, персонажей — максимум три.",
      controls: [durationControl(1, 30, [5, 8, 10, 15, 20, 30], 8)],
      custom: "gemini",
      hide: [
        { label: "Audio Ids", index: 0 },
        { label: "Video List", index: 0 },
        { label: "Character Ids", index: 0 },
      ],
    },
    "grok-video-t2v": grokConfig(false),
    "grok-video-i2v": grokConfig(true),
    "grok-video-1.5": {
      note: "Grok Imagine Video 1.5 принимает текст и опциональный стартовый кадр.",
      controls: [
        segmented("resolution", "Качество", RES_GROK, "480p"),
        select("aspect_ratio", "Соотношение сторон", RATIO_GROK, "16:9"),
        durationControl(1, 30, [5, 6, 8, 10, 15, 20, 30], 8),
      ],
    },
    "grok-video-upscale": {
      note: "Upscale работает только с task ID видео, которое уже было сгенерировано через Kie AI.",
      controls: [],
    },
    "grok-video-extend": {
      note: "Extend работает только с task ID Kie. Точка продолжения и число расширений задаются числами, а не словами start/end.",
      controls: [],
      custom: "grokExtend",
      hide: [
        { label: "Точка расширения", index: 0 },
        { label: "Количество расширений", index: 0 },
      ],
    },
  };

  let scheduled = false;
  let values = readValues();
  const nativeFetch = window.fetch.bind(window);

  function options(items, labels = {}) {
    return items.map((value) => ({ value, label: labels[value] || String(value) }));
  }

  function select(key, label, itemOptions, defaultValue, extra = {}) {
    return { key, label, options: itemOptions, defaultValue, kind: "select", ...extra };
  }

  function segmented(key, label, itemOptions, defaultValue, extra = {}) {
    return { key, label, options: itemOptions, defaultValue, kind: "segmented", ...extra };
  }

  function durationControl(min, max, presets, defaultValue) {
    return {
      key: "duration",
      label: "Длительность",
      kind: "duration",
      min,
      max,
      presets,
      defaultValue,
    };
  }

  function seedance2Config(suffix = "2.0") {
    return {
      note: `Seedance ${suffix}: текст, первый кадр, первый + последний и мультиреференсы переключаются как отдельные сценарии и не смешиваются.`,
      controls: [
        segmented("resolution", "Качество", RES_HD, "720p"),
        select("aspect_ratio", "Соотношение сторон", RATIO_VIDEO, "16:9"),
        durationControl(1, 30, [5, 8, 10, 15, 20, 30], 15),
      ],
    };
  }

  function motionConfig(v3) {
    return {
      note: "Motion Control требует ровно одно фото персонажа и одно видео движения длительностью 3–30 секунд.",
      controls: [
        segmented("mode", "Качество", options(["720p", "1080p"]), "720p"),
        segmented("character_orientation", "Ориентация", [
          { value: "image", label: "По фото" },
          { value: "video", label: "По видео" },
        ], "image"),
        ...(v3 ? [segmented("background_source", "Фон", [
          { value: "input_video", label: "Из видео" },
          { value: "input_image", label: "Из фото" },
        ], "input_video")] : []),
      ],
    };
  }

  function grokConfig(imageMode) {
    return {
      note: imageMode
        ? "Grok Image-to-Video принимает один входной кадр; mode=normal ROXY передаёт сама."
        : "Grok Text-to-Video: mode=normal ROXY передаёт сама — в промпте указывать режим не нужно.",
      controls: [
        segmented("resolution", "Качество", RES_GROK, "480p"),
        select("aspect_ratio", "Соотношение сторон", RATIO_GROK, "16:9"),
        durationControl(1, 30, [5, 6, 8, 10, 15, 20, 30], 6),
        segmented("mode", "Режим", [{ value: "normal", label: "Normal" }], "normal", { extra: true }),
      ],
      hide: [{ label: "Режим", index: 0 }],
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

  function bucket(modelId) {
    const key = groupKey(modelId);
    if (!values[key] || typeof values[key] !== "object") values[key] = {};
    return values[key];
  }

  function savedValue(modelId, control) {
    const data = bucket(modelId);
    if (Object.prototype.hasOwnProperty.call(data, control.key)) return data[control.key];
    return control.defaultValue;
  }

  function saveValue(modelId, key, value) {
    bucket(modelId)[key] = value;
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

  function draftValue(modelId, key) {
    return readDraft(modelId)?.values?.[key];
  }

  function fieldWrappersByLabel(label) {
    return [...document.querySelectorAll("#dynamicForm .field")].filter(
      (wrapper) => (wrapper.querySelector(":scope > .field-label")?.textContent || "").trim() === label,
    );
  }

  function findNativeField(control) {
    const labelMap = {
      resolution: "Разрешение",
      aspect_ratio: "Соотношение сторон",
      ratio: "Соотношение сторон",
      duration: "Длительность",
      mode: "Режим",
      character_orientation: "Ориентация персонажа",
      background_source: "Источник фона",
    };
    const label = control.nativeLabel || labelMap[control.key];
    if (!label) return null;
    return fieldWrappersByLabel(label)[control.nativeIndex || 0] || null;
  }

  function setNativeValue(wrapper, value) {
    const input = wrapper?.querySelector("input.input");
    if (!input) return false;
    const normalized = String(value ?? "");
    if (input.value !== normalized) input.value = normalized;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
  }

  function triggerQuoteRefresh() {
    const prompt = [...document.querySelectorAll("#dynamicForm textarea")].find(
      (node) => !node.classList.contains("json-input"),
    );
    if (prompt) prompt.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function normalizeChoice(modelId, control) {
    const current = savedValue(modelId, control);
    if (!control.options?.length) return current;
    const match = control.options.find((item) => String(item.value) === String(current));
    if (match) return match.value;
    saveValue(modelId, control.key, control.defaultValue);
    return control.defaultValue;
  }

  function buildSelect(modelId, control, wrapper) {
    const selectEl = document.createElement("select");
    selectEl.className = "roxy-video-select";
    selectEl.setAttribute("aria-label", control.label);
    const current = normalizeChoice(modelId, control);
    for (const item of control.options) {
      const option = document.createElement("option");
      option.value = String(item.value);
      option.textContent = item.label;
      option.selected = String(item.value) === String(current);
      selectEl.appendChild(option);
    }
    selectEl.addEventListener("change", () => {
      const item = control.options.find((candidate) => String(candidate.value) === selectEl.value);
      const value = item?.value ?? selectEl.value;
      saveValue(modelId, control.key, value);
      if (!control.extra && setNativeValue(wrapper, value)) scheduleEnhance();
      else triggerQuoteRefresh();
      applyCrossFieldRules(modelId);
      window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.();
    });
    return selectEl;
  }

  function buildSegments(modelId, control, wrapper) {
    const root = document.createElement("div");
    root.className = "roxy-video-segments";
    root.setAttribute("role", "group");
    root.setAttribute("aria-label", control.label);
    const current = normalizeChoice(modelId, control);
    for (const item of control.options) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "roxy-video-segment";
      button.textContent = item.label;
      const active = String(item.value) === String(current);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
      button.addEventListener("click", () => {
        saveValue(modelId, control.key, item.value);
        if (!control.extra && setNativeValue(wrapper, item.value)) scheduleEnhance();
        else triggerQuoteRefresh();
        applyCrossFieldRules(modelId);
        scheduleEnhance();
        window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.();
      });
      root.appendChild(button);
    }
    return root;
  }

  function buildDuration(modelId, control, wrapper) {
    const root = document.createElement("div");
    root.className = "roxy-video-duration-row";
    const input = document.createElement("input");
    input.className = "roxy-video-number";
    input.type = "number";
    input.min = String(control.min);
    input.max = String(control.max);
    input.step = "1";
    input.value = String(savedValue(modelId, control) ?? control.defaultValue);
    const presets = document.createElement("div");
    presets.className = "roxy-video-duration-presets";

    const update = (value) => {
      const numeric = Math.min(control.max, Math.max(control.min, Number(value) || control.defaultValue));
      input.value = String(numeric);
      saveValue(modelId, control.key, numeric);
      setNativeValue(wrapper, numeric);
      for (const button of presets.children) {
        button.classList.toggle("is-active", Number(button.dataset.value) === numeric);
      }
      triggerQuoteRefresh();
    };

    input.addEventListener("change", () => update(input.value));
    input.addEventListener("input", () => {
      if (input.value === "") return;
      saveValue(modelId, control.key, Number(input.value));
      setNativeValue(wrapper, Number(input.value));
    });
    for (const value of control.presets) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "roxy-video-preset";
      button.dataset.value = String(value);
      button.textContent = `${value}с`;
      button.classList.toggle("is-active", Number(input.value) === value);
      button.addEventListener("click", () => update(value));
      presets.appendChild(button);
    }
    root.append(input, presets);
    return root;
  }

  function enhanceNativeControl(modelId, control, wrapper) {
    if (!wrapper) return false;
    const signature = `${modelId}:${control.key}:${JSON.stringify(control.options || control.presets || [])}`;
    if (wrapper.dataset.roxyVideoSignature === signature) return true;
    wrapper.dataset.roxyVideoSignature = signature;
    wrapper.classList.add("roxy-video-field");
    const label = wrapper.querySelector(":scope > .field-label");
    if (label) label.textContent = control.label;
    wrapper.querySelector(":scope > .roxy-video-control")?.remove();
    const nativeInput = wrapper.querySelector("input.input");
    const dataListId = nativeInput?.getAttribute("list");
    if (nativeInput) {
      nativeInput.classList.add("roxy-video-native-hidden");
      nativeInput.tabIndex = -1;
      const stored = savedValue(modelId, control);
      if (nativeInput.value !== "" && control.kind !== "duration") {
        if (!control.options || control.options.some((item) => String(item.value) === nativeInput.value)) {
          saveValue(modelId, control.key, control.options?.find((item) => String(item.value) === nativeInput.value)?.value ?? nativeInput.value);
        }
      } else if (nativeInput.value === "" && stored !== undefined) {
        setNativeValue(wrapper, stored);
      }
    }
    if (dataListId) document.getElementById(dataListId)?.setAttribute("hidden", "");
    const shell = document.createElement("div");
    shell.className = "roxy-video-control";
    if (control.kind === "segmented") shell.appendChild(buildSegments(modelId, control, wrapper));
    else if (control.kind === "duration") shell.appendChild(buildDuration(modelId, control, wrapper));
    else shell.appendChild(buildSelect(modelId, control, wrapper));
    wrapper.appendChild(shell);
    return true;
  }

  function outputGroup() {
    const groups = [...document.querySelectorAll("#dynamicForm .form-group")];
    return groups.find((group) => group.querySelector(".group-title")?.textContent?.trim() === "Результат") || groups.at(-1) || null;
  }

  function ensureExtraControls(modelId, config) {
    const group = outputGroup();
    if (!group) return;
    let root = group.querySelector(":scope > .roxy-video-extra-controls[data-kind='simple']");
    const extras = config.controls.filter((control) => control.extra);
    const signature = `${modelId}:${extras.map((item) => `${item.key}:${savedValue(modelId, item)}`).join("|")}`;
    if (root?.dataset.signature === signature) return;
    if (!root) {
      root = document.createElement("div");
      root.className = "roxy-video-extra-controls";
      root.dataset.kind = "simple";
      group.appendChild(root);
    }
    root.dataset.signature = signature;
    root.replaceChildren();
    for (const control of extras) {
      const field = document.createElement("div");
      field.className = "field roxy-video-field";
      const label = document.createElement("label");
      label.className = "field-label";
      label.textContent = control.label;
      const shell = document.createElement("div");
      shell.className = "roxy-video-control";
      shell.appendChild(control.kind === "segmented" ? buildSegments(modelId, control, null) : buildSelect(modelId, control, null));
      field.append(label, shell);
      root.appendChild(field);
    }
    root.hidden = !extras.length;
  }

  function hideTechnicalFields(config) {
    for (const item of config.hide || []) {
      const wrapper = fieldWrappersByLabel(item.label)[item.index || 0];
      if (wrapper) wrapper.hidden = true;
    }
  }

  function ensureModelNote(modelId, config) {
    const form = document.getElementById("dynamicForm");
    if (!form) return;
    let note = document.getElementById("roxyVideoModelNote");
    if (!config.note) {
      note?.remove();
      return;
    }
    if (!note) {
      note = document.createElement("div");
      note.id = "roxyVideoModelNote";
      note.className = "roxy-video-model-note";
      form.prepend(note);
    }
    note.textContent = config.note;
    note.dataset.modelId = modelId;
  }

  function customRoot(modelId, kind) {
    const group = outputGroup();
    if (!group) return null;
    let root = group.querySelector(`:scope > .roxy-video-extra-controls[data-kind='${kind}']`);
    if (!root) {
      root = document.createElement("div");
      root.className = "roxy-video-extra-controls";
      root.dataset.kind = kind;
      group.appendChild(root);
    }
    root.dataset.modelId = modelId;
    return root;
  }

  function card(title, help = "") {
    const root = document.createElement("section");
    root.className = "roxy-video-custom-card";
    const head = document.createElement("div");
    head.className = "roxy-video-custom-head";
    const strong = document.createElement("strong");
    strong.textContent = title;
    head.appendChild(strong);
    root.appendChild(head);
    if (help) {
      const copy = document.createElement("div");
      copy.className = "roxy-video-custom-help";
      copy.textContent = help;
      root.appendChild(copy);
    }
    return { root, head };
  }

  function textInput(value, placeholder, onInput, className = "roxy-video-text") {
    const input = document.createElement("input");
    input.className = className;
    input.type = "text";
    input.value = value ?? "";
    input.placeholder = placeholder || "";
    input.addEventListener("input", () => onInput(input.value));
    return input;
  }

  function numberInput(value, min, max, onInput) {
    const input = document.createElement("input");
    input.className = "roxy-video-number";
    input.type = "number";
    input.min = String(min);
    input.max = String(max);
    input.step = "1";
    input.value = value ?? "";
    input.addEventListener("input", () => onInput(input.value === "" ? null : Number(input.value)));
    return input;
  }

  function smallButton(label, handler, extraClass = "") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `roxy-video-small-button ${extraClass}`.trim();
    button.textContent = label;
    button.addEventListener("click", handler);
    return button;
  }

  function removeButton(handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "roxy-video-remove";
    button.textContent = "×";
    button.setAttribute("aria-label", "Удалить");
    button.addEventListener("click", handler);
    return button;
  }

  async function uploadFiles(files, accept) {
    if (!files.length) return [];
    const tg = window.Telegram?.WebApp;
    if (!tg?.initData) throw new Error("Загрузка доступна при открытии ROXY через Telegram");
    const result = [];
    for (const file of files) {
      if (accept && !file.type.startsWith(`${accept}/`)) throw new Error(`Нужен файл типа ${accept}`);
      const form = new FormData();
      form.append("file", file, file.name);
      const response = await nativeFetch("/api/v1/uploads/kie", {
        method: "POST",
        headers: { "X-Telegram-Init-Data": tg.initData },
        body: form,
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || !body?.url) throw new Error(body?.detail || `Не удалось загрузить ${file.name}`);
      result.push({ url: body.url, name: body.name || file.name });
    }
    return result;
  }

  function uploadButton(label, accept, multiple, handler) {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = `${accept}/*`;
    input.multiple = multiple;
    input.hidden = true;
    input.addEventListener("change", async () => {
      const files = [...(input.files || [])];
      input.value = "";
      if (!files.length) return;
      try {
        const uploaded = await uploadFiles(files, accept);
        handler(uploaded);
      } catch (error) {
        window.dispatchEvent(new CustomEvent("roxy:toast", { detail: { message: error.message || "Ошибка загрузки" } }));
      }
    });
    const button = document.createElement("button");
    button.type = "button";
    button.className = "roxy-video-upload-button";
    button.textContent = label;
    button.addEventListener("click", () => input.click());
    const fragment = document.createDocumentFragment();
    fragment.append(button, input);
    return fragment;
  }

  function urlList(modelId, key, title, accept, max = 20) {
    const section = card(title);
    const data = bucket(modelId);
    const existing = data[key];
    if (!Array.isArray(existing)) {
      const legacy = draftValue(modelId, key);
      data[key] = Array.isArray(legacy) ? [...legacy] : typeof legacy === "string" && legacy ? [legacy] : [];
      persistValues();
    }
    const list = document.createElement("div");
    list.className = "roxy-video-stack";
    const render = () => {
      list.replaceChildren();
      for (const [index, url] of data[key].entries()) {
        const row = document.createElement("div");
        row.className = "roxy-video-item-row";
        row.append(
          textInput(url, "URL", (value) => {
            data[key][index] = value;
            persistValues();
            triggerQuoteRefresh();
          }),
          removeButton(() => {
            data[key].splice(index, 1);
            persistValues();
            render();
            triggerQuoteRefresh();
          }),
        );
        list.appendChild(row);
      }
    };
    const actions = document.createElement("div");
    actions.className = "roxy-video-upload-row";
    actions.appendChild(uploadButton(`Загрузить ${accept === "image" ? "фото" : "видео"}`, accept, true, (uploaded) => {
      data[key].push(...uploaded.map((item) => item.url));
      data[key] = data[key].slice(0, max);
      persistValues();
      render();
      triggerQuoteRefresh();
    }));
    actions.appendChild(smallButton("Добавить URL", () => {
      if (data[key].length >= max) return;
      data[key].push("");
      persistValues();
      render();
    }, "roxy-video-add-button"));
    render();
    section.root.append(actions, list);
    return section.root;
  }

  function renderWanR2v(modelId, root) {
    const signature = `${modelId}:${JSON.stringify(bucket(modelId).reference_image || [])}:${JSON.stringify(bucket(modelId).reference_video || [])}`;
    if (root.dataset.signature === signature) return;
    root.dataset.signature = signature;
    root.replaceChildren(
      urlList(modelId, "reference_image", "Фото-референсы", "image", 10),
      urlList(modelId, "reference_video", "Видео-референсы", "video", 10),
    );
  }

  function klingShots(modelId) {
    const data = bucket(modelId);
    if (!Array.isArray(data.multi_prompt) || !data.multi_prompt.length) data.multi_prompt = [{ prompt: "", duration: 3 }];
    return data.multi_prompt;
  }

  function renderKling3(modelId, root) {
    const data = bucket(modelId);
    if (typeof data.sound !== "boolean") data.sound = true;
    if (typeof data.multi_shots !== "boolean") data.multi_shots = false;
    if (!Array.isArray(data.kling_elements)) data.kling_elements = [];
    root.replaceChildren();

    const switches = card("Генерация");
    const sound = smallButton(data.sound ? "Звук: включён" : "Звук: выключен", () => {
      data.sound = !data.sound;
      persistValues();
      renderKling3(modelId, root);
      triggerQuoteRefresh();
    });
    sound.classList.toggle("is-active", data.sound);
    const multi = smallButton(data.multi_shots ? "Мультишот: включён" : "Мультишот: выключен", () => {
      data.multi_shots = !data.multi_shots;
      persistValues();
      renderKling3(modelId, root);
      triggerQuoteRefresh();
    });
    multi.classList.toggle("is-active", data.multi_shots);
    switches.root.append(sound, multi);
    root.appendChild(switches.root);

    if (data.multi_shots) {
      const shotsCard = card("Мультишот", "До 6 сцен. У каждой свой промпт и длительность 1–12 секунд; общий duration ROXY посчитает сама.");
      const shotsRoot = document.createElement("div");
      shotsRoot.className = "roxy-video-stack";
      const shots = klingShots(modelId);
      shots.forEach((shot, index) => {
        const item = document.createElement("div");
        item.className = "roxy-video-item";
        const row = document.createElement("div");
        row.className = "roxy-video-item-row";
        const title = document.createElement("strong");
        title.textContent = `Сцена ${index + 1}`;
        row.append(title, removeButton(() => {
          if (shots.length <= 1) return;
          shots.splice(index, 1);
          persistValues();
          renderKling3(modelId, root);
          triggerQuoteRefresh();
        }));
        const prompt = document.createElement("textarea");
        prompt.className = "roxy-video-textarea";
        prompt.maxLength = 500;
        prompt.placeholder = "Что происходит в этой сцене";
        prompt.value = shot.prompt || "";
        prompt.addEventListener("input", () => {
          shot.prompt = prompt.value;
          persistValues();
          triggerQuoteRefresh();
        });
        const duration = numberInput(shot.duration || 3, 1, 12, (value) => {
          shot.duration = value || 1;
          persistValues();
          triggerQuoteRefresh();
        });
        item.append(row, prompt, duration);
        shotsRoot.appendChild(item);
      });
      const add = smallButton("+ Добавить сцену", () => {
        if (shots.length >= 6) return;
        shots.push({ prompt: "", duration: 3 });
        persistValues();
        renderKling3(modelId, root);
      }, "roxy-video-add-button");
      shotsCard.root.append(shotsRoot, add);
      root.appendChild(shotsCard.root);
    }

    const elements = card("@elements", "До трёх персонажей/объектов. Фото: 2–4 файла; видео: один файл с эффективным фрагментом 3–8 секунд; аудио: один файл.");
    const list = document.createElement("div");
    list.className = "roxy-video-stack";
    data.kling_elements.forEach((element, index) => {
      element._type ||= "image";
      element.element_input_urls ||= [];
      element.element_input_audio_urls ||= [];
      const item = document.createElement("div");
      item.className = "roxy-video-item";
      const head = document.createElement("div");
      head.className = "roxy-video-item-row";
      head.append(
        textInput(element.name || `element_${index + 1}`, "Имя без @", (value) => {
          element.name = value.replace(/^@+/, "");
          persistValues();
          triggerQuoteRefresh();
        }),
        removeButton(() => {
          data.kling_elements.splice(index, 1);
          persistValues();
          renderKling3(modelId, root);
          triggerQuoteRefresh();
        }),
      );
      const description = textInput(element.description || "", "Короткое описание", (value) => {
        element.description = value;
        persistValues();
        triggerQuoteRefresh();
      });
      const type = document.createElement("select");
      type.className = "roxy-video-select";
      for (const choice of [
        { value: "image", label: "Фото (2–4)" },
        { value: "video", label: "Видео (1)" },
        { value: "audio", label: "Аудио (1)" },
      ]) {
        const option = document.createElement("option");
        option.value = choice.value;
        option.textContent = choice.label;
        option.selected = element._type === choice.value;
        type.appendChild(option);
      }
      type.addEventListener("change", () => {
        element._type = type.value;
        element.element_input_urls = [];
        element.element_input_audio_urls = [];
        delete element.start_time;
        delete element.end_time;
        persistValues();
        renderKling3(modelId, root);
        triggerQuoteRefresh();
      });
      item.append(head, description, type);

      if (element._type === "audio") {
        const actions = document.createElement("div");
        actions.className = "roxy-video-upload-row";
        actions.appendChild(uploadButton("Загрузить аудио", "audio", false, (uploaded) => {
          element.element_input_audio_urls = uploaded.slice(0, 1).map((entry) => entry.url);
          persistValues();
          renderKling3(modelId, root);
          triggerQuoteRefresh();
        }));
        actions.appendChild(textInput(element.element_input_audio_urls[0] || "", "URL аудио", (value) => {
          element.element_input_audio_urls = value ? [value] : [];
          persistValues();
          triggerQuoteRefresh();
        }));
        item.appendChild(actions);
      } else {
        const accept = element._type === "video" ? "video" : "image";
        const max = accept === "video" ? 1 : 4;
        const actions = document.createElement("div");
        actions.className = "roxy-video-upload-row";
        actions.appendChild(uploadButton(`Загрузить ${accept === "video" ? "видео" : "фото"}`, accept, max > 1, (uploaded) => {
          element.element_input_urls.push(...uploaded.map((entry) => entry.url));
          element.element_input_urls = element.element_input_urls.slice(0, max);
          persistValues();
          renderKling3(modelId, root);
          triggerQuoteRefresh();
        }));
        item.appendChild(actions);
        const files = document.createElement("div");
        files.className = "roxy-video-file-list";
        element.element_input_urls.forEach((url, urlIndex) => {
          const chip = smallButton(`Файл ${urlIndex + 1} ×`, () => {
            element.element_input_urls.splice(urlIndex, 1);
            persistValues();
            renderKling3(modelId, root);
            triggerQuoteRefresh();
          }, "roxy-video-file-chip");
          chip.title = url;
          files.appendChild(chip);
        });
        item.appendChild(files);
        if (accept === "video") {
          const times = document.createElement("div");
          times.className = "roxy-video-grid-2";
          times.append(
            numberInput(element.start_time ?? 0, 0, 600000, (value) => {
              element.start_time = value ?? 0;
              persistValues();
              triggerQuoteRefresh();
            }),
            numberInput(element.end_time ?? 5000, 0, 600000, (value) => {
              element.end_time = value ?? 5000;
              persistValues();
              triggerQuoteRefresh();
            }),
          );
          const help = document.createElement("div");
          help.className = "roxy-video-item-help";
          help.textContent = "Начало / конец эффективного фрагмента в миллисекундах (разница 3–8 сек).";
          item.append(times, help);
        }
      }
      list.appendChild(item);
    });
    const addElement = smallButton("+ Добавить element", () => {
      if (data.kling_elements.length >= 3) return;
      data.kling_elements.push({
        name: `element_${data.kling_elements.length + 1}`,
        description: "",
        _type: "image",
        element_input_urls: [],
        element_input_audio_urls: [],
      });
      persistValues();
      renderKling3(modelId, root);
    }, "roxy-video-add-button");
    elements.root.append(list, addElement);
    root.appendChild(elements.root);
  }

  function renderVeo(modelId, root) {
    const data = bucket(modelId);
    if (typeof data.enable_fallback !== "boolean") data.enable_fallback = false;
    if (typeof data.enable_translation !== "boolean") data.enable_translation = true;
    root.replaceChildren();
    const cardNode = card("Veo 3.1 · дополнительные настройки", "Reference mode доступен на Fast/Lite; при несовместимом выборе ROXY сама переключит вариант на Fast.");
    const fallback = smallButton(data.enable_fallback ? "Fallback: включён" : "Fallback: выключен", () => {
      data.enable_fallback = !data.enable_fallback;
      persistValues();
      renderVeo(modelId, root);
      triggerQuoteRefresh();
    });
    fallback.classList.toggle("is-active", data.enable_fallback);
    const translation = smallButton(data.enable_translation ? "Перевод: включён" : "Перевод: выключен", () => {
      data.enable_translation = !data.enable_translation;
      persistValues();
      renderVeo(modelId, root);
      triggerQuoteRefresh();
    });
    translation.classList.toggle("is-active", data.enable_translation);
    cardNode.root.append(fallback, translation);
    root.appendChild(cardNode.root);
  }

  function imageCountForDraft(modelId) {
    const value = draftValue(modelId, "image_urls");
    return Array.isArray(value) ? value.length : value ? 1 : 0;
  }

  function renderGemini(modelId, root) {
    const data = bucket(modelId);
    if (!Array.isArray(data.audio_ids)) data.audio_ids = [];
    if (!Array.isArray(data.character_ids)) data.character_ids = [];
    if (!Array.isArray(data.video_list)) data.video_list = [];
    root.replaceChildren();

    const quota = document.createElement("div");
    quota.className = "roxy-video-quota";
    const used = imageCountForDraft(modelId) + data.video_list.length * 2 + data.character_ids.length;
    quota.textContent = `Квота: ${used}/7`;
    quota.classList.toggle("is-error", used > 7);
    root.appendChild(quota);

    const idsEditor = (key, title, max, placeholder) => {
      const section = card(title);
      const list = document.createElement("div");
      list.className = "roxy-video-stack";
      data[key].forEach((value, index) => {
        const row = document.createElement("div");
        row.className = "roxy-video-item-row";
        row.append(
          textInput(value, placeholder, (next) => {
            data[key][index] = next;
            persistValues();
            triggerQuoteRefresh();
          }),
          removeButton(() => {
            data[key].splice(index, 1);
            persistValues();
            renderGemini(modelId, root);
            triggerQuoteRefresh();
          }),
        );
        list.appendChild(row);
      });
      const add = smallButton("+ Добавить", () => {
        if (data[key].length >= max) return;
        data[key].push("");
        persistValues();
        renderGemini(modelId, root);
      }, "roxy-video-add-button");
      section.root.append(list, add);
      return section.root;
    };

    root.appendChild(idsEditor("character_ids", "Персонажи", 3, "Character ID"));
    root.appendChild(idsEditor("audio_ids", "Аудио ID", 7, "Audio ID"));

    const video = card("Видео-референс", "Максимум одно видео. При необходимости можно задать начало и конец фрагмента.");
    const videoList = document.createElement("div");
    videoList.className = "roxy-video-stack";
    data.video_list.forEach((item, index) => {
      const block = document.createElement("div");
      block.className = "roxy-video-item";
      const row = document.createElement("div");
      row.className = "roxy-video-item-row";
      row.append(
        textInput(item.url || "", "URL видео", (value) => {
          item.url = value;
          persistValues();
          triggerQuoteRefresh();
        }),
        removeButton(() => {
          data.video_list.splice(index, 1);
          persistValues();
          renderGemini(modelId, root);
          triggerQuoteRefresh();
        }),
      );
      const times = document.createElement("div");
      times.className = "roxy-video-grid-2";
      times.append(
        numberInput(item.start ?? 0, 0, 600, (value) => {
          item.start = value ?? 0;
          persistValues();
          triggerQuoteRefresh();
        }),
        numberInput(item.ends ?? 5, 0, 600, (value) => {
          item.ends = value ?? 5;
          persistValues();
          triggerQuoteRefresh();
        }),
      );
      block.append(row, times);
      videoList.appendChild(block);
    });
    const videoActions = document.createElement("div");
    videoActions.className = "roxy-video-upload-row";
    if (!data.video_list.length) {
      videoActions.appendChild(uploadButton("Загрузить видео", "video", false, (uploaded) => {
        if (!uploaded[0]) return;
        data.video_list = [{ url: uploaded[0].url, start: 0, ends: 5 }];
        persistValues();
        renderGemini(modelId, root);
        triggerQuoteRefresh();
      }));
      videoActions.appendChild(smallButton("Добавить URL", () => {
        data.video_list = [{ url: "", start: 0, ends: 5 }];
        persistValues();
        renderGemini(modelId, root);
      }, "roxy-video-add-button"));
    }
    video.root.append(videoActions, videoList);
    root.appendChild(video.root);
  }

  function renderGrokExtend(modelId, root) {
    const data = bucket(modelId);
    if (!Number.isInteger(data.extend_at)) data.extend_at = 2;
    if (!Number.isInteger(data.extend_times)) data.extend_times = 1;
    root.replaceChildren();
    const section = card("Параметры расширения");
    const grid = document.createElement("div");
    grid.className = "roxy-video-grid-2";
    const at = numberInput(data.extend_at, 0, 600, (value) => {
      data.extend_at = value ?? 0;
      persistValues();
      triggerQuoteRefresh();
    });
    at.setAttribute("aria-label", "Точка расширения");
    const times = numberInput(data.extend_times, 1, 60, (value) => {
      data.extend_times = value ?? 1;
      persistValues();
      triggerQuoteRefresh();
    });
    times.setAttribute("aria-label", "Количество расширений");
    grid.append(at, times);
    const help = document.createElement("div");
    help.className = "roxy-video-custom-help";
    help.textContent = "Слева — числовая точка расширения, справа — количество повторов.";
    section.root.append(grid, help);
    root.appendChild(section.root);
  }

  function renderCustom(modelId, config) {
    if (!config.custom) return;
    const root = customRoot(modelId, config.custom);
    if (!root) return;
    if (config.custom === "wanR2v") renderWanR2v(modelId, root);
    else if (config.custom === "kling3") renderKling3(modelId, root);
    else if (config.custom === "veo") renderVeo(modelId, root);
    else if (config.custom === "gemini") renderGemini(modelId, root);
    else if (config.custom === "grokExtend") renderGrokExtend(modelId, root);
  }

  function applyCrossFieldRules(modelId) {
    if (modelId !== "veo-3.1") return;
    const data = bucket(modelId);
    if (data.generation_type === "REFERENCE_2_VIDEO" && data.veo_model === "veo3") {
      data.veo_model = "veo3_fast";
      persistValues();
    }
  }

  function observeBuilder() {
    const target = document.getElementById("builderView") || document.body;
    if (target) observer.observe(target, { childList: true, subtree: true });
  }

  function enhance() {
    scheduled = false;
    observer.disconnect();
    try {
      const modelId = currentModelId();
      const config = CONFIG[modelId];
      document.body?.classList.toggle("roxy-video-controls-active", Boolean(config && VIDEO_MODEL_IDS.has(modelId)));
      if (!config || !VIDEO_MODEL_IDS.has(modelId)) {
        document.getElementById("roxyVideoModelNote")?.remove();
        return;
      }
      applyCrossFieldRules(modelId);
      for (const control of config.controls.filter((item) => !item.extra)) {
        enhanceNativeControl(modelId, control, findNativeField(control));
      }
      hideTechnicalFields(config);
      ensureExtraControls(modelId, config);
      ensureModelNote(modelId, config);
      renderCustom(modelId, config);
    } finally {
      observeBuilder();
    }
  }

  function scheduleEnhance() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(enhance);
  }

  function cleanKlingElements(items) {
    return (items || []).map((raw) => {
      const item = { ...raw };
      delete item._type;
      if (!item.element_input_audio_urls?.length) delete item.element_input_audio_urls;
      if (!item.element_input_urls?.length) delete item.element_input_urls;
      if (item.start_time == null) delete item.start_time;
      if (item.end_time == null) delete item.end_time;
      return item;
    });
  }

  function applyExtraParameters(payload) {
    const modelId = String(payload?.model_id || "");
    const config = CONFIG[modelId];
    if (!config || !payload.parameters || typeof payload.parameters !== "object") return payload;
    const data = bucket(modelId);

    for (const control of config.controls.filter((item) => item.extra)) {
      const value = savedValue(modelId, control);
      if (value !== undefined && value !== null && value !== "") payload.parameters[control.key] = value;
    }

    if (modelId === "wan-2.7-t2v") delete payload.parameters.aspect_ratio;
    if (["grok-video-t2v", "grok-video-i2v"].includes(modelId)) payload.parameters.mode = "normal";
    if (modelId === "wan-2.7-video-edit") payload.parameters.audio_setting = "auto";

    if (modelId === "wan-2.7-r2v") {
      if (Array.isArray(data.reference_image) && data.reference_image.filter(Boolean).length) {
        payload.parameters.reference_image = data.reference_image.filter(Boolean);
      }
      if (Array.isArray(data.reference_video) && data.reference_video.filter(Boolean).length) {
        payload.parameters.reference_video = data.reference_video.filter(Boolean);
      }
    }

    if (modelId === "kling-3.0") {
      payload.parameters.sound = data.sound !== false;
      payload.parameters.multi_shots = Boolean(data.multi_shots);
      if (data.multi_shots) {
        const shots = klingShots(modelId).map((shot) => ({
          prompt: String(shot.prompt || ""),
          duration: Number(shot.duration || 1),
        }));
        payload.parameters.multi_prompt = shots;
        payload.parameters.duration = shots.reduce((sum, shot) => sum + shot.duration, 0);
      } else {
        delete payload.parameters.multi_prompt;
      }
      const elements = cleanKlingElements(data.kling_elements);
      if (elements.length) payload.parameters.kling_elements = elements;
      else delete payload.parameters.kling_elements;
    }

    if (modelId === "veo-3.1") {
      applyCrossFieldRules(modelId);
      payload.parameters.veo_model = data.veo_model || "veo3_fast";
      payload.parameters.generation_type = data.generation_type || "TEXT_2_VIDEO";
      payload.parameters.enable_fallback = Boolean(data.enable_fallback);
      payload.parameters.enable_translation = data.enable_translation !== false;
    }

    if (modelId === "gemini-omni-video") {
      payload.parameters.audio_ids = (data.audio_ids || []).filter(Boolean);
      payload.parameters.character_ids = (data.character_ids || []).filter(Boolean);
      payload.parameters.video_list = (data.video_list || []).filter((item) => item?.url).map((item) => ({
        url: String(item.url),
        start: Number(item.start || 0),
        ends: Number(item.ends || 0),
      }));
    }

    if (modelId === "grok-video-extend") {
      payload.parameters.extend_at = Number(data.extend_at ?? 2);
      payload.parameters.extend_times = Number(data.extend_times ?? 1);
    }
    return payload;
  }

  window.fetch = function roxyVideoFetch(input, init) {
    try {
      const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
      const isGenerationWrite = url.pathname === "/api/v1/generations" || url.pathname === "/api/v1/generations/quote";
      if (!isGenerationWrite || !init?.body || typeof init.body !== "string") return nativeFetch(input, init);
      const payload = JSON.parse(init.body);
      if (!VIDEO_MODEL_IDS.has(String(payload?.model_id || ""))) return nativeFetch(input, init);
      const next = { ...init, body: JSON.stringify(applyExtraParameters(payload)) };
      return nativeFetch(input, next);
    } catch (_error) {
      return nativeFetch(input, init);
    }
  };

  const observer = new MutationObserver(scheduleEnhance);
  function init() {
    observeBuilder();
    document.getElementById("modelSelect")?.addEventListener("change", scheduleEnhance);
    window.addEventListener("storage", scheduleEnhance);
    window.addEventListener("roxy:route-changed", scheduleEnhance);
    window.addEventListener("roxy:shell-route-changed", scheduleEnhance);
    for (const delay of [0, 60, 180, 450, 900]) window.setTimeout(scheduleEnhance, delay);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();