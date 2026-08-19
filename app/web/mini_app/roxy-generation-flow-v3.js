(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const RETURN_KEY = "roxy-generation-flow-return";
  const PRODUCT_KEY = "roxy-generation-product-context";
  const DRAFTS_KEY = "ksu-generation-drafts-v1";
  const RESUME_KEY = "ksu-studio-open-builder";

  const FAMILY_LABELS = {
    nanobanana: "Nano Banana",
    seedream: "Seedream",
    "gpt-image": "GPT Image",
    wan: "Wan",
    seedance: "Seedance",
    kling: "Kling",
    grok: "Grok",
    veo: "Veo",
    gemini: "Gemini",
  };

  const MODEL_TITLE_OVERRIDES = {
    "nano-banana-pro": "Nano Banana Pro",
    "nano-banana-2": "Nano Banana 2",
    "nano-banana-2-lite": "Nano Banana 2 Lite",
    "seedream-3-t2i": "Seedream 3.0",
    "wan-2.7-image": "Wan 2.7",
    "wan-2.7-image-pro": "Wan 2.7 Pro",
  };

  const PRODUCT_GROUPS = [
    { key: "nano-banana", title: "Nano Banana", ids: ["nano-banana", "nano-banana-edit"] },
    { key: "seedream-4", title: "Seedream 4.0", ids: ["seedream-4-t2i", "seedream-4-edit"] },
    { key: "seedream-4.5", title: "Seedream 4.5", ids: ["seedream-4.5-t2i", "seedream-4.5-edit"] },
    { key: "seedream-5-lite", title: "Seedream 5.0 Lite", ids: ["seedream-5-lite-t2i", "seedream-5-lite-i2i"] },
    { key: "seedream-5-pro", title: "Seedream 5 Pro", ids: ["seedream-5-pro-t2i", "seedream-5-pro-i2i", "seedream-5-pro-layers"] },
    { key: "gpt-image-1.5", title: "GPT Image 1.5", ids: ["gpt-image-1.5-t2i", "gpt-image-1.5-i2i"] },
    { key: "gpt-image-2", title: "GPT Image 2", ids: ["gpt-image-2-t2i", "gpt-image-2-i2i"] },
    { key: "wan-2.7-video", title: "Wan 2.7", ids: ["wan-2.7-t2v", "wan-2.7-i2v", "wan-2.7-video-edit"] },
    { key: "grok-image", title: "Grok Imagine", ids: ["grok-image-t2i", "grok-image-i2i"] },
    { key: "grok-video", title: "Grok Video", ids: ["grok-video-t2v", "grok-video-i2v"] },
  ];

  const SPECIAL_OPERATION_LABELS = {
    layer_decomposition: "Разложить на слои",
  };

  const state = {
    models: [],
    modelById: new Map(),
    loaded: false,
    loading: false,
    mediaType: null,
    activeProduct: null,
    legacy: null,
    builderObserver: null,
    formObserver: null,
    uploadBusy: false,
  };

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function button(label, handler, className = "") {
    const node = el("button", className, label);
    node.type = "button";
    node.addEventListener("click", handler);
    return node;
  }

  function haptic(kind = "light") {
    try { tg?.HapticFeedback?.impactOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function notify(kind = "success") {
    try { tg?.HapticFeedback?.notificationOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function authHeaders() {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      headers: { ...authHeaders(), ...(options.headers || {}) },
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
    return payload;
  }

  function readDrafts() {
    try {
      const value = JSON.parse(localStorage.getItem(DRAFTS_KEY) || "{}");
      return value && typeof value === "object" ? value : {};
    } catch (_error) {
      return {};
    }
  }

  function writeDrafts(drafts) {
    localStorage.setItem(DRAFTS_KEY, JSON.stringify(drafts));
  }

  async function loadModels() {
    if (state.loaded) return state.models;
    if (state.loading) {
      for (let attempt = 0; attempt < 80 && state.loading; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 40));
      }
      return state.models;
    }
    state.loading = true;
    try {
      const payload = await api("/api/v1/generations/models");
      state.models = Array.isArray(payload?.models) ? payload.models : [];
      state.modelById = new Map(state.models.map((model) => [model.id, model]));
      state.loaded = true;
      return state.models;
    } finally {
      state.loading = false;
    }
  }

  function displayModelTitle(model) {
    const override = MODEL_TITLE_OVERRIDES[model?.id];
    if (override) return override;
    return String(model?.title || model?.id || "ROXY")
      .replace(/\s*·\s*(Text to Image|Image to Image|Edit|Layer Decomposition)$/i, "")
      .trim();
  }

  function buildProducts(mediaType) {
    const models = state.models.filter((model) => model.media_type === mediaType);
    const consumed = new Set();
    const products = [];
    for (const group of PRODUCT_GROUPS) {
      const variants = group.ids.map((id) => state.modelById.get(id)).filter((model) => model?.media_type === mediaType);
      if (!variants.length) continue;
      variants.forEach((model) => consumed.add(model.id));
      products.push({ key: group.key, title: group.title, mediaType, variants });
    }
    for (const model of models) {
      if (consumed.has(model.id)) continue;
      products.push({ key: model.id, title: displayModelTitle(model), mediaType, variants: [model] });
    }
    return products;
  }

  function operationLabel(operation) {
    return {
      text_to_image: "Текст",
      image_edit: "Фото",
      generate_or_edit: "Текст / фото",
      image_to_image: "Фото",
      layer_decomposition: "Слои",
      text_to_video: "Текст",
      image_to_video: "Фото",
      video_edit: "Видео",
      reference_to_video: "Референсы",
      text_or_image_to_video: "Текст / фото",
      multimodal_video: "Мультимедиа",
      motion_control: "Motion",
      video_upscale: "Апскейл",
      video_extend: "Продление",
    }[operation] || "Генерация";
  }

  function productModes(product) {
    return [...new Set(product.variants.map((model) => operationLabel(model.operation)))];
  }

  function specialVariants(product) {
    return product.variants.filter((model) => Boolean(SPECIAL_OPERATION_LABELS[model.operation]));
  }

  function selectedProductVariant(product) {
    const selectedId = document.getElementById("modelSelect")?.value || localStorage.getItem("ksu-selected-model");
    return product.variants.find((model) => model.id === selectedId) || null;
  }

  function priceLabel(product) {
    const prices = product.variants.map((model) => Number(model?.price_credits || 0)).filter(Number.isFinite);
    if (!prices.length) return "—";
    const min = Math.min(...prices).toLocaleString("ru-RU", { maximumFractionDigits: 2 });
    return product.variants.some((model) => model.price_mode === "per_second") ? `от ${min} ROX/с` : `от ${min} ROX`;
  }

  function textTarget(product) {
    return product.variants.find((model) => ["generate_or_edit", "text_or_image_to_video", "multimodal_video"].includes(model.operation))
      || product.variants.find((model) => ["text_to_image", "text_to_video"].includes(model.operation))
      || product.variants[0]
      || null;
  }

  function fieldCandidates(model, kind) {
    const fields = model?.ui_schema?.fields || [];
    const preferredNames = kind === "video"
      ? ["video_url", "first_clip_url", "video_urls", "reference_video", "reference_video_urls", "video_list"]
      : model?.operation === "image_to_video"
        ? ["first_frame_url", "image_urls", "input_urls", "image_input", "image_url", "reference_image", "reference_image_urls", "first_frame"]
        : ["image_urls", "input_urls", "image_input", "image_url", "first_frame_url", "reference_image", "reference_image_urls", "first_frame", "last_frame_url"];
    const preferred = preferredNames.map((name) => fields.find((field) => field.name === name)).filter(Boolean);
    const accepted = fields.filter((field) => String(field.accept || "").startsWith(`${kind}/`));
    return [...new Map([...preferred, ...accepted].map((field) => [field.name, field])).values()];
  }

  function scenarioItem(model, draft) {
    const scenario = model?.ui_schema?.scenario;
    if (!scenario?.items?.length) return null;
    return scenario.items.find((item) => item.id === draft?.scenario)
      || scenario.items.find((item) => item.id === scenario.default)
      || scenario.items[0];
  }

  function sourceField(model, kind, draft = null) {
    const candidates = fieldCandidates(model, kind);
    if (!candidates.length) return null;
    const scenario = scenarioItem(model, draft);
    const visible = new Set(scenario?.visible_fields || []);
    const scoped = visible.size ? candidates.filter((field) => visible.has(field.name)) : candidates;
    const pool = scoped.length ? scoped : candidates;
    const values = draft?.values || {};
    return pool.find((field) => {
      const value = values[field.name];
      return Array.isArray(value) ? value.length === 0 : !value;
    }) || pool[0];
  }

  function sourceTarget(product, kind) {
    const selected = selectedProductVariant(product);
    if (selected && SPECIAL_OPERATION_LABELS[selected.operation] && fieldCandidates(selected, kind).length) return selected;
    if (kind === "video") {
      const edit = product.variants.find((model) => model.operation === "video_edit");
      if (edit) return edit;
      return product.variants.find((model) => ["multimodal_video", "motion_control", "reference_to_video"].includes(model.operation) && fieldCandidates(model, "video").length) || null;
    }
    if (product.mediaType === "video") {
      return product.variants.find((model) => ["image_to_video", "text_or_image_to_video", "multimodal_video", "motion_control", "reference_to_video"].includes(model.operation) && fieldCandidates(model, "image").length) || null;
    }
    return product.variants.find((model) => ["image_edit", "image_to_image", "generate_or_edit"].includes(model.operation) && fieldCandidates(model, "image").length) || null;
  }

  function hasValue(value) {
    return Array.isArray(value) ? value.length > 0 : value !== undefined && value !== null && value !== "";
  }

  function automaticTarget(product) {
    const regularVariants = product.variants.filter((model) => !SPECIAL_OPERATION_LABELS[model.operation]);
    const drafts = readDrafts();
    for (const model of regularVariants) {
      const draft = drafts[model.id];
      if (!draft?.values) continue;
      const fields = [...fieldCandidates(model, "image"), ...fieldCandidates(model, "video")];
      if (fields.some((field) => hasValue(draft.values[field.name]))) return model;
    }
    return textTarget({ ...product, variants: regularVariants }) || regularVariants[0] || textTarget(product);
  }

  function existingTarget(product) {
    const selected = selectedProductVariant(product);
    if (selected && SPECIAL_OPERATION_LABELS[selected.operation]) return selected;
    const drafts = readDrafts();
    for (const model of product.variants) {
      const draft = drafts[model.id];
      if (!draft?.values) continue;
      const fields = [...fieldCandidates(model, "image"), ...fieldCandidates(model, "video")];
      if (fields.some((field) => hasValue(draft.values[field.name]))) return model;
    }
    return textTarget(product);
  }

  function compatibleValues(target, sourceDraft) {
    const allowed = new Set((target?.ui_schema?.fields || []).map((field) => field.name));
    const values = {};
    for (const [name, value] of Object.entries(sourceDraft?.values || {})) {
      if (allowed.has(name)) values[name] = value;
    }
    return values;
  }

  function applyScenarioForField(target, draft, field) {
    const scenario = target?.ui_schema?.scenario;
    if (!scenario?.items?.length) return;
    const match = scenario.items.find((item) => (item.visible_fields || []).includes(field.name));
    if (match) draft.scenario = match.id;
  }

  function applyAutomaticDiscriminators(target, draft, hasSource) {
    if (target?.id === "veo-3.1") {
      draft.values.generation_type = hasSource ? "REFERENCE_2_VIDEO" : "TEXT_2_VIDEO";
      draft.touched.generation_type = true;
    }
  }

  function sourceSummary(product) {
    const drafts = readDrafts();
    const items = [];
    for (const model of product.variants) {
      const draft = drafts[model.id];
      if (!draft?.values) continue;
      for (const kind of ["image", "video"]) {
        for (const field of fieldCandidates(model, kind)) {
          const value = draft.values[field.name];
          if (!hasValue(value)) continue;
          const count = Array.isArray(value) ? value.length : 1;
          items.push(`${kind === "video" ? "видео" : "фото"} ×${count}`);
        }
      }
    }
    return [...new Set(items)];
  }

  function saveProductContext(product) {
    sessionStorage.setItem(PRODUCT_KEY, JSON.stringify({
      key: product.key,
      title: product.title,
      mediaType: product.mediaType,
      variantIds: product.variants.map((model) => model.id),
    }));
  }

  function restoreProductContext() {
    try {
      const raw = JSON.parse(sessionStorage.getItem(PRODUCT_KEY) || "null");
      if (!raw?.variantIds?.length) return null;
      const variants = raw.variantIds.map((id) => state.modelById.get(id)).filter(Boolean);
      return variants.length ? { key: raw.key, title: raw.title, mediaType: raw.mediaType, variants } : null;
    } catch (_error) {
      return null;
    }
  }

  function renderStart() {
    const center = document.getElementById("roxyCreateCenterView");
    if (!center) return;
    state.mediaType = null;
    state.activeProduct = null;
    document.body?.classList.remove("roxy-focused-model-flow", "roxy-focused-model-pending");
    const heading = el("header", "roxy-create-center-heading roxy-flow-heading");
    heading.append(
      el("span", "section-kicker", "ROXY Create"),
      el("h1", "", "Что создаём?"),
      el("p", "", "Выбираешь модель один раз. Текст, фото или видео сами определяют нужный режим."),
    );
    const grid = el("div", "roxy-media-grid roxy-flow-format-grid");
    const image = button("", () => void openMedia("image"), "roxy-media-card roxy-flow-format-card");
    image.dataset.roxyMedia = "image";
    image.append(el("span", "roxy-media-card-icon", "▧"), el("strong", "", "Фото"), el("small", "", "Создание и редактирование"));
    const video = button("", () => void openMedia("video"), "roxy-media-card roxy-flow-format-card");
    video.dataset.roxyMedia = "video";
    video.append(el("span", "roxy-media-card-icon", "▶"), el("strong", "", "Видео"), el("small", "", "Создание, motion и edit"));
    grid.append(image, video);
    center.replaceChildren(heading, grid);
  }

  function renderProductCard(product) {
    const card = button("", () => openProduct(product), "roxy-flow-model-card");
    card.dataset.productId = product.key;
    const head = el("span", "roxy-flow-model-head");
    const icon = el("span", "roxy-flow-model-icon", product.mediaType === "video" ? "▶" : "✦");
    const title = el("span", "roxy-flow-model-title");
    title.append(el("strong", "", product.title), el("small", "", FAMILY_LABELS[product.variants[0]?.family] || product.variants[0]?.family || "ROXY"));
    head.append(icon, title, el("span", "roxy-flow-model-price", priceLabel(product)));
    const modes = el("span", "roxy-flow-model-scenarios");
    productModes(product).forEach((mode) => modes.appendChild(el("em", "", mode)));
    const footer = el("span", "roxy-flow-model-footer");
    const hasSpecial = specialVariants(product).length > 0;
    const footerLabel = hasSpecial
      ? "Обычный режим — автоматически · спецрежим внутри"
      : product.variants.length > 1 ? "Режим определится автоматически" : "Открыть";
    footer.append(el("span", "", footerLabel), el("span", "roxy-flow-model-arrow", "→"));
    card.append(head, modes, footer);
    return card;
  }

  function renderMedia(mediaType) {
    const center = document.getElementById("roxyCreateCenterView");
    if (!center) return;
    state.mediaType = mediaType;
    const products = buildProducts(mediaType);
    const top = el("header", "roxy-flow-topbar");
    const back = button("←", renderStart, "roxy-flow-back");
    const copy = el("div", "roxy-flow-topbar-copy");
    copy.append(
      el("span", "section-kicker", mediaType === "video" ? "ROXY · Видео" : "ROXY · Фото"),
      el("h1", "", "Выбери модель"),
      el("p", "", mediaType === "video"
        ? "Выбирай модель один раз. ROXY сама переключит текст, фото, видео и motion-сценарии."
        : "Выбирай модель один раз. ROXY сама переключит создание, редактирование и работу с фото."),
    );
    top.append(back, copy);
    const grid = el("div", "roxy-flow-model-grid");
    products.forEach((product) => grid.appendChild(renderProductCard(product)));
    center.replaceChildren(top, el("div", "roxy-flow-count", `${products.length} моделей`), grid);
  }

  async function openMedia(mediaType) {
    if (!["image", "video"].includes(mediaType)) return;
    haptic("medium");
    const center = document.getElementById("roxyCreateCenterView");
    if (center) center.replaceChildren(el("div", "roxy-flow-empty", "Загружаю модели…"));
    try {
      await loadModels();
      renderMedia(mediaType);
    } catch (error) {
      if (!center) return;
      center.replaceChildren(el("div", "roxy-flow-empty is-error", error.message || "Не удалось загрузить модели"), button("Повторить", () => void openMedia(mediaType), "roxy-flow-retry"));
    }
  }

  function familyLabel(family) {
    return FAMILY_LABELS[family] || family;
  }

  function ensureFamily(model) {
    const select = document.getElementById("modelSelect");
    if (select && [...select.options].some((option) => option.value === model.id)) return true;
    const tab = [...document.querySelectorAll(".family-tab")].find((node) => (node.textContent || "").trim() === familyLabel(model.family));
    tab?.click();
    return false;
  }

  function selectExactModel(modelId, attempt = 0) {
    const model = state.modelById.get(modelId);
    const select = document.getElementById("modelSelect");
    const builder = document.getElementById("builderView");
    if (!model || !select || !builder || builder.hidden) {
      if (attempt < 100) window.setTimeout(() => selectExactModel(modelId, attempt + 1), 35);
      return;
    }
    if (!ensureFamily(model)) {
      if (attempt < 100) window.setTimeout(() => selectExactModel(modelId, attempt + 1), 35);
      return;
    }
    if (![...select.options].some((option) => option.value === model.id)) {
      if (attempt < 100) window.setTimeout(() => selectExactModel(modelId, attempt + 1), 35);
      return;
    }
    if (select.value !== model.id) {
      select.value = model.id;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    localStorage.setItem("ksu-selected-model", model.id);
    window.setTimeout(mountFocusedBuilder, 0);
  }

  function switchProductVariant(product, target) {
    if (!product || !target) return;
    haptic("light");
    const drafts = readDrafts();
    const currentId = localStorage.getItem("ksu-selected-model");
    const sourceDraft = drafts[currentId] || null;
    const targetDraft = drafts[target.id] || {
      values: {},
      touched: {},
      files: {},
      scenario: target.ui_schema?.scenario?.default || null,
      billing_seconds: null,
    };
    if (sourceDraft && currentId !== target.id) {
      const copied = compatibleValues(target, sourceDraft);
      targetDraft.values = { ...(targetDraft.values || {}), ...copied };
      targetDraft.touched = { ...(targetDraft.touched || {}) };
      for (const name of Object.keys(copied)) {
        if (sourceDraft.touched?.[name]) targetDraft.touched[name] = true;
      }
      if (targetDraft.billing_seconds == null && sourceDraft.billing_seconds != null) {
        targetDraft.billing_seconds = sourceDraft.billing_seconds;
      }
      drafts[target.id] = targetDraft;
      writeDrafts(drafts);
    }
    state.activeProduct = product;
    saveProductContext(product);
    localStorage.setItem("ksu-selected-model", target.id);
    document.body?.classList.add("roxy-focused-model-pending");
    selectExactModel(target.id);
  }

  function openProduct(product) {
    if (!product?.variants?.length) return;
    haptic("medium");
    state.activeProduct = product;
    saveProductContext(product);
    sessionStorage.setItem(RETURN_KEY, product.mediaType);
    const target = existingTarget(product) || textTarget(product);
    if (!target) return;
    localStorage.setItem("ksu-selected-model", target.id);
    document.body?.classList.add("roxy-focused-model-pending");
    state.legacy?.close?.();
    if (window.KsuStudioShell?.open) window.KsuStudioShell.open("create");
    else document.querySelector('.bottom-nav-item[data-shell-nav="create"]')?.click();
    selectExactModel(target.id);
  }

  function setSmartStatus(message, error = false) {
    const node = document.getElementById("roxySmartSourceStatus");
    if (!node) return;
    node.textContent = message;
    node.classList.toggle("is-error", error);
  }

  async function uploadSource(file, kind) {
    if (state.uploadBusy) return;
    const product = state.activeProduct || restoreProductContext();
    if (!product) return;
    if (!tg?.initData) {
      setSmartStatus("Загрузка доступна при открытии ROXY через Telegram.", true);
      return;
    }
    const target = sourceTarget(product, kind);
    if (!target) {
      setSmartStatus(kind === "video" ? "Эта модель не принимает входное видео." : "Эта модель не принимает входное фото.", true);
      return;
    }

    state.uploadBusy = true;
    renderSmartSourcePanel();
    setSmartStatus(`Загружаю ${file.name}…`);
    try {
      const form = new FormData();
      form.append("file", file, file.name);
      const uploaded = await api("/api/v1/uploads/kie", { method: "POST", body: form });
      const drafts = readDrafts();
      const currentId = localStorage.getItem("ksu-selected-model");
      const sourceDraft = drafts[currentId] || { values: {}, touched: {}, files: {}, billing_seconds: null };
      const targetDraft = drafts[target.id] || { values: {}, touched: {}, files: {}, scenario: target.ui_schema?.scenario?.default || null, billing_seconds: null };
      const next = {
        ...targetDraft,
        values: { ...targetDraft.values, ...compatibleValues(target, sourceDraft) },
        touched: { ...targetDraft.touched, ...sourceDraft.touched },
        files: { ...targetDraft.files },
        billing_seconds: sourceDraft.billing_seconds ?? targetDraft.billing_seconds ?? null,
      };
      const field = sourceField(target, kind, next);
      if (!field) throw new Error("У модели нет подходящего поля для этого файла.");
      const meta = {
        url: uploaded.url,
        name: uploaded.name || file.name,
        mime_type: uploaded.mime_type || file.type,
        size: uploaded.size || file.size,
      };
      if (field.control === "files") {
        const values = Array.isArray(next.values[field.name]) ? [...next.values[field.name]] : [];
        const files = Array.isArray(next.files[field.name]) ? [...next.files[field.name]] : [];
        const max = Number(field.max_items || 20);
        if (values.length >= max) throw new Error(`Максимум файлов: ${max}`);
        values.push(uploaded.url);
        files.push(meta);
        next.values[field.name] = values;
        next.files[field.name] = files;
      } else {
        next.values[field.name] = uploaded.url;
        next.files[field.name] = [meta];
      }
      next.touched[field.name] = true;
      applyScenarioForField(target, next, field);
      applyAutomaticDiscriminators(target, next, true);
      drafts[target.id] = next;
      writeDrafts(drafts);
      localStorage.setItem("ksu-selected-model", target.id);
      sessionStorage.setItem(RESUME_KEY, "1");
      notify("success");
      document.body?.classList.add("roxy-focused-model-pending");
      window.location.reload();
    } catch (error) {
      state.uploadBusy = false;
      renderSmartSourcePanel();
      setSmartStatus(error.message || "Не удалось загрузить файл.", true);
      notify("error");
    }
  }

  function clearSources() {
    const product = state.activeProduct || restoreProductContext();
    if (!product) return;
    const drafts = readDrafts();
    for (const model of product.variants) {
      const draft = drafts[model.id];
      if (!draft) continue;
      draft.values ||= {};
      draft.files ||= {};
      draft.touched ||= {};
      for (const field of model.ui_schema?.fields || []) {
        if (!["file", "files"].includes(field.control)) continue;
        if (!/^(image|video)\//.test(String(field.accept || ""))) continue;
        delete draft.values[field.name];
        delete draft.files[field.name];
        delete draft.touched[field.name];
      }
      if (model.ui_schema?.scenario?.default) draft.scenario = model.ui_schema.scenario.default;
      applyAutomaticDiscriminators(model, draft, false);
    }
    const target = automaticTarget(product) || textTarget(product);
    if (!target) return;
    writeDrafts(drafts);
    localStorage.setItem("ksu-selected-model", target.id);
    sessionStorage.setItem(RESUME_KEY, "1");
    document.body?.classList.add("roxy-focused-model-pending");
    window.location.reload();
  }

  function smartInput(kind, label) {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = `${kind}/*`;
    input.hidden = true;
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      input.value = "";
      if (file) void uploadSource(file, kind);
    });
    const trigger = button(label, () => input.click(), "roxy-smart-source-button");
    trigger.disabled = state.uploadBusy;
    const wrap = document.createDocumentFragment();
    wrap.append(trigger, input);
    return wrap;
  }

  function renderSmartSourcePanel() {
    const product = state.activeProduct || restoreProductContext();
    const modelCard = document.querySelector("#builderView .model-card");
    if (!product || !modelCard) return;
    state.activeProduct = product;
    let panel = document.getElementById("roxySmartSourcePanel");
    if (!panel) {
      panel = el("section", "roxy-smart-source");
      panel.id = "roxySmartSourcePanel";
      modelCard.insertAdjacentElement("afterend", panel);
    }
    panel.replaceChildren();
    const imageTarget = sourceTarget(product, "image");
    const videoTarget = sourceTarget(product, "video");
    const specials = specialVariants(product);
    if (!imageTarget && !videoTarget && !specials.length) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;
    const head = el("div", "roxy-smart-source-head");
    const copy = el("div");
    copy.append(el("span", "section-kicker", "Входные данные"), el("strong", "", "ROXY сама выбирает режим"));
    head.appendChild(copy);
    const actions = el("div", "roxy-smart-source-actions");
    if (imageTarget) actions.appendChild(smartInput("image", "Добавить фото"));
    if (videoTarget) actions.appendChild(smartInput("video", "Добавить видео"));

    const selected = selectedProductVariant(product);
    const modeActions = el("div", "roxy-smart-mode-actions");
    if (specials.length) {
      const autoButton = button("Авто", () => {
        const target = automaticTarget(product);
        if (target) switchProductVariant(product, target);
      }, "roxy-smart-mode-button");
      autoButton.classList.toggle("is-active", !selected || !SPECIAL_OPERATION_LABELS[selected.operation]);
      autoButton.setAttribute("aria-pressed", String(!selected || !SPECIAL_OPERATION_LABELS[selected.operation]));
      modeActions.appendChild(autoButton);
      specials.forEach((variant) => {
        const active = selected?.id === variant.id;
        const specialButton = button(SPECIAL_OPERATION_LABELS[variant.operation], () => switchProductVariant(product, variant), "roxy-smart-mode-button");
        specialButton.classList.toggle("is-active", active);
        specialButton.setAttribute("aria-pressed", String(active));
        modeActions.appendChild(specialButton);
      });
    }

    const status = el("div", "roxy-smart-source-status");
    status.id = "roxySmartSourceStatus";
    const summary = sourceSummary(product);
    if (summary.length) {
      status.append(el("span", "", `Вход: ${summary.join(" · ")}`), button("Убрать все", clearSources, "roxy-smart-source-remove"));
    } else if (selected && SPECIAL_OPERATION_LABELS[selected.operation]) {
      status.textContent = `${SPECIAL_OPERATION_LABELS[selected.operation]}: добавь фото — ROXY оставит этот режим и откроет только его параметры.`;
    } else {
      status.textContent = "Без файла — текстовый режим. Добавляешь фото или видео — ROXY переключает backend сама.";
    }
    panel.append(head, actions);
    if (specials.length) panel.append(modeActions);
    panel.append(status);
  }

  function focusedHeader() {
    const product = state.activeProduct || restoreProductContext();
    const modelCard = document.querySelector("#builderView .model-card");
    if (!product || !modelCard) return;
    let header = document.getElementById("roxyFocusedModelHeader");
    if (!header) {
      header = el("div", "roxy-focused-model-header");
      header.id = "roxyFocusedModelHeader";
      modelCard.prepend(header);
    }
    header.replaceChildren();
    const copy = el("div", "roxy-focused-model-copy");
    copy.append(el("span", "section-kicker", product.mediaType === "video" ? "Видео" : "Фото"), el("h2", "", product.title));
    const modes = el("div", "roxy-focused-model-modes");
    productModes(product).forEach((mode) => modes.appendChild(el("span", "", mode)));
    header.append(button("←", () => returnFromBuilder(product.mediaType), "roxy-flow-back"), copy, modes);
  }

  function hidePrimaryNativeSources() {
    const product = state.activeProduct || restoreProductContext();
    const selectedId = document.getElementById("modelSelect")?.value || localStorage.getItem("ksu-selected-model");
    const selected = state.modelById.get(selectedId);
    if (!product || !selected) return;
    const draft = readDrafts()[selected.id] || null;
    const labels = [sourceField(selected, "image", draft), sourceField(selected, "video", draft)]
      .filter(Boolean)
      .map((field) => String(field.label || "").trim());
    document.querySelectorAll("#dynamicForm .field").forEach((field) => {
      const label = field.querySelector(".field-label")?.textContent?.trim() || "";
      field.classList.toggle("roxy-native-source-hidden", labels.includes(label));
    });
  }

  function mountFocusedBuilder() {
    const builder = document.getElementById("builderView");
    if (!builder || builder.hidden) return;
    const product = state.activeProduct || restoreProductContext();
    if (!product) return;
    state.activeProduct = product;
    document.body?.classList.remove("roxy-focused-model-pending");
    document.body?.classList.add("roxy-focused-model-flow");
    focusedHeader();
    renderSmartSourcePanel();
    hidePrimaryNativeSources();
  }

  function returnFromBuilder(mediaType) {
    sessionStorage.removeItem(RETURN_KEY);
    sessionStorage.removeItem(PRODUCT_KEY);
    sessionStorage.removeItem(RESUME_KEY);
    state.activeProduct = null;
    document.body?.classList.remove("roxy-focused-model-flow", "roxy-focused-model-pending");
    state.legacy?.open?.();
    if (state.loaded) renderMedia(mediaType);
    else void openMedia(mediaType);
  }

  function intercept(event) {
    const media = event.target.closest?.("#roxyCreateCenterView .roxy-media-card[data-roxy-media]");
    if (media && !media.disabled) {
      const type = media.dataset.roxyMedia;
      if (["image", "video"].includes(type)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        void openMedia(type);
        return;
      }
    }
    const home = event.target.closest?.("#builderHomeButton");
    const mediaType = sessionStorage.getItem(RETURN_KEY);
    if (home && mediaType && !document.getElementById("builderView")?.hidden) {
      event.preventDefault();
      event.stopImmediatePropagation();
      returnFromBuilder(mediaType);
      return;
    }
    const nav = event.target.closest?.("[data-shell-nav], [data-studio-route]");
    const route = nav?.dataset?.shellNav || nav?.dataset?.studioRoute;
    if (route && route !== "create") {
      sessionStorage.removeItem(RETURN_KEY);
      sessionStorage.removeItem(PRODUCT_KEY);
      sessionStorage.removeItem(RESUME_KEY);
      state.activeProduct = null;
      document.body?.classList.remove("roxy-focused-model-flow", "roxy-focused-model-pending");
    }
  }

  function installLegacyBridge() {
    const legacy = window.RoxyCreateCenter;
    if (!legacy?.open || legacy.__roxyGenerationFlowV3) return false;
    state.legacy = legacy;
    window.RoxyCreateCenter = Object.freeze({
      __roxyGenerationFlowV3: true,
      open() {
        legacy.open();
        window.setTimeout(() => {
          if (state.loaded) renderStart();
          else void loadModels().then(renderStart).catch(renderStart);
        }, 0);
      },
      close() { legacy.close(); },
      chooseMedia(mediaType) {
        if (["image", "video"].includes(mediaType)) return openMedia(mediaType);
        return legacy.chooseMedia?.(mediaType);
      },
      openMedia,
    });
    return true;
  }

  function installObservers() {
    const builder = document.getElementById("builderView");
    const form = document.getElementById("dynamicForm");
    if (builder && !state.builderObserver) {
      state.builderObserver = new MutationObserver(() => {
        if (!builder.hidden) window.setTimeout(mountFocusedBuilder, 0);
      });
      state.builderObserver.observe(builder, { attributes: true, attributeFilter: ["hidden"] });
    }
    if (form && !state.formObserver) {
      state.formObserver = new MutationObserver(() => window.setTimeout(hidePrimaryNativeSources, 0));
      state.formObserver.observe(form, { childList: true, subtree: true });
    }
  }

  function init() {
    document.addEventListener("click", intercept, true);
    if (sessionStorage.getItem(PRODUCT_KEY)) document.body?.classList.add("roxy-focused-model-pending");
    installObservers();
    if (installLegacyBridge()) {
      void loadModels().then(() => {
        const restored = restoreProductContext();
        if (restored) {
          state.activeProduct = restored;
          window.setTimeout(() => {
            const modelId = localStorage.getItem("ksu-selected-model");
            if (modelId) selectExactModel(modelId);
            mountFocusedBuilder();
          }, 0);
        }
      }).catch(() => null);
      return;
    }
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      installObservers();
      if (installLegacyBridge() || attempts >= 80) {
        window.clearInterval(timer);
        if (window.RoxyCreateCenter) void loadModels().catch(() => null);
      }
    }, 50);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
