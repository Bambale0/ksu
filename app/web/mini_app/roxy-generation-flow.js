(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const RETURN_KEY = "roxy-generation-flow-return";
  const PRODUCT_KEY = "roxy-generation-product-context";
  const SMART_SOURCE_KEY = "roxy-generation-smart-source";
  const DRAFTS_KEY = "ksu-generation-drafts-v1";

  const FAMILY_LABELS = {
    nanobanana: "Nano Banana",
    seedream: "Seedream",
    "gpt-image": "GPT Image",
    wan: "Wan",
    seedance: "Seedance",
    kling: "Kling Motion",
    grok: "Grok",
    veo: "Veo",
    gemini: "Gemini",
  };

  const PRODUCT_GROUPS = [
    { key: "nano-banana-classic", title: "Nano Banana", ids: ["nano-banana", "nano-banana-edit"] },
    { key: "seedream-4", title: "Seedream 4.0", ids: ["seedream-4-t2i", "seedream-4-edit"] },
    { key: "seedream-4.5", title: "Seedream 4.5", ids: ["seedream-4.5-t2i", "seedream-4.5-edit"] },
    { key: "seedream-5-lite", title: "Seedream 5.0 Lite", ids: ["seedream-5-lite-t2i", "seedream-5-lite-i2i"] },
    { key: "seedream-5-pro", title: "Seedream 5 Pro", ids: ["seedream-5-pro-t2i", "seedream-5-pro-i2i"] },
    { key: "gpt-image-1.5", title: "GPT Image 1.5", ids: ["gpt-image-1.5-t2i", "gpt-image-1.5-i2i"] },
    { key: "gpt-image-2", title: "GPT Image 2", ids: ["gpt-image-2-t2i", "gpt-image-2-i2i"] },
    { key: "wan-2.7-video", title: "Wan 2.7 Video", ids: ["wan-2.7-t2v", "wan-2.7-i2v", "wan-2.7-video-edit"] },
    { key: "grok-image", title: "Grok Imagine", ids: ["grok-image-t2i", "grok-image-i2i"] },
    { key: "grok-video", title: "Grok Video", ids: ["grok-video-t2v", "grok-video-i2v"] },
  ];

  const state = {
    models: [],
    modelById: new Map(),
    loaded: false,
    loading: false,
    mediaType: null,
    legacy: null,
    center: null,
    activeProduct: null,
    observer: null,
    smartSourceBusy: false,
  };

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

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function button(text, handler, className = "") {
    const node = el("button", className, text);
    node.type = "button";
    node.addEventListener("click", handler);
    return node;
  }

  function ensureCenter() {
    state.center = document.getElementById("roxyCreateCenterView");
    return state.center;
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

  function mediaModels(mediaType) {
    return state.models.filter((model) => model.media_type === mediaType);
  }

  function operationLabel(operation) {
    return {
      text_to_image: "По тексту",
      image_edit: "С фото",
      generate_or_edit: "Текст или фото",
      image_to_image: "С фото",
      layer_decomposition: "Слои",
      text_to_video: "По тексту",
      image_to_video: "С фото",
      video_edit: "С видео",
      reference_to_video: "С референсами",
      text_or_image_to_video: "Текст или фото",
      multimodal_video: "Мультимодально",
      motion_control: "Motion Control",
      video_upscale: "Апскейл",
      video_extend: "Продление",
    }[operation] || "Генерация";
  }

  function priceLabel(product) {
    const prices = product.variants.map((model) => Number(model?.price_credits || 0)).filter(Number.isFinite);
    if (!prices.length) return "—";
    const min = Math.min(...prices).toLocaleString("ru-RU", { maximumFractionDigits: 2 });
    const perSecond = product.variants.some((model) => model.price_mode === "per_second");
    return perSecond ? `от ${min} ROX/сек` : `от ${min} ROX`;
  }

  function buildProducts(mediaType) {
    const models = mediaModels(mediaType);
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
      products.push({ key: model.id, title: model.title || model.id, mediaType, variants: [model] });
    }
    return products;
  }

  function textVariant(product) {
    return product.variants.find((model) => ["generate_or_edit", "text_or_image_to_video", "multimodal_video"].includes(model.operation))
      || product.variants.find((model) => ["text_to_image", "text_to_video"].includes(model.operation))
      || product.variants[0];
  }

  function sourceVariant(product, kind) {
    if (kind === "video") {
      return product.variants.find((model) => model.operation === "video_edit") || null;
    }
    if (product.mediaType === "video") {
      return product.variants.find((model) => ["image_to_video", "text_or_image_to_video", "multimodal_video"].includes(model.operation)) || null;
    }
    return product.variants.find((model) => ["image_edit", "image_to_image", "generate_or_edit"].includes(model.operation)) || null;
  }

  function productModes(product) {
    return [...new Set(product.variants.map((model) => operationLabel(model.operation)))];
  }

  function readDrafts() {
    try {
      const parsed = JSON.parse(localStorage.getItem(DRAFTS_KEY) || "{}");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (_error) {
      return {};
    }
  }

  function writeDrafts(drafts) {
    try { localStorage.setItem(DRAFTS_KEY, JSON.stringify(drafts)); } catch (_error) { /* optional */ }
  }

  function hasValue(value) {
    if (Array.isArray(value)) return value.length > 0;
    return value !== undefined && value !== null && value !== "";
  }

  function sourceField(model, kind) {
    const fields = model?.ui_schema?.fields || [];
    const names = kind === "video"
      ? ["video_url", "first_clip_url", "video_urls", "reference_video", "reference_video_urls"]
      : model?.operation === "image_to_video"
        ? ["first_frame_url", "image_urls", "input_urls", "image_input", "image_url", "reference_image"]
        : ["image_urls", "input_urls", "image_input", "image_url", "first_frame_url", "reference_image", "reference_image_urls"];
    for (const name of names) {
      const field = fields.find((item) => item.name === name);
      if (field) return field;
    }
    return fields.find((field) => String(field.accept || "").startsWith(`${kind}/`)) || null;
  }

  function existingVariant(product) {
    const drafts = readDrafts();
    for (const model of product.variants) {
      const draft = drafts[model.id];
      if (!draft?.values) continue;
      const image = sourceField(model, "image");
      const video = sourceField(model, "video");
      if ((image && hasValue(draft.values[image.name])) || (video && hasValue(draft.values[video.name]))) return model;
    }
    return textVariant(product);
  }

  function renderStart() {
    const center = ensureCenter();
    if (!center) return;
    state.mediaType = null;
    state.activeProduct = null;
    document.body?.classList.remove("roxy-focused-model-flow", "roxy-focused-model-pending");
    center.dataset.roxyGenerationFlow = "start";

    const heading = el("header", "roxy-create-center-heading roxy-flow-heading");
    heading.append(
      el("span", "section-kicker", "ROXY Create"),
      el("h1", "", "Что создаём?"),
      el("p", "", "Выбери формат, затем саму модель. Режим Text-to-X / Image-to-X ROXY определит автоматически по входным данным."),
    );

    const grid = el("div", "roxy-media-grid roxy-flow-format-grid");
    const image = button("", () => void openMedia("image"), "roxy-media-card roxy-flow-format-card");
    image.dataset.roxyMedia = "image";
    image.append(el("span", "roxy-media-card-icon", "▧"), el("strong", "", "Фото"), el("small", "", "Генерация и редактирование"));
    const video = button("", () => void openMedia("video"), "roxy-media-card roxy-flow-format-card");
    video.dataset.roxyMedia = "video";
    video.append(el("span", "roxy-media-card-icon", "▶"), el("strong", "", "Видео"), el("small", "", "Генерация, motion и edit"));
    grid.append(image, video);
    center.replaceChildren(heading, grid);
  }

  function renderModelCard(product) {
    const card = button("", () => openProduct(product), "roxy-flow-model-card");
    card.dataset.productId = product.key;
    const head = el("span", "roxy-flow-model-head");
    const icon = el("span", "roxy-flow-model-icon", product.mediaType === "video" ? "▶" : "✦");
    const title = el("span", "roxy-flow-model-title");
    const family = product.variants[0]?.family || "ROXY";
    title.append(el("strong", "", product.title), el("small", "", FAMILY_LABELS[family] || family));
    head.append(icon, title, el("span", "roxy-flow-model-price", priceLabel(product)));

    const modes = el("span", "roxy-flow-model-scenarios");
    productModes(product).forEach((label) => modes.appendChild(el("em", "", label)));
    const footer = el("span", "roxy-flow-model-footer");
    footer.append(
      el("span", "", product.variants.length > 1 ? "Режим выберется автоматически" : "Открыть модель"),
      el("span", "roxy-flow-model-arrow", "→"),
    );
    card.append(head, modes, footer);
    return card;
  }

  function renderMediaFlow(mediaType) {
    const center = ensureCenter();
    if (!center) return;
    state.mediaType = mediaType;
    center.dataset.roxyGenerationFlow = mediaType;
    const products = buildProducts(mediaType);

    const top = el("header", "roxy-flow-topbar");
    const back = button("←", renderStart, "roxy-flow-back");
    const copy = el("div", "roxy-flow-topbar-copy");
    copy.append(
      el("span", "section-kicker", mediaType === "video" ? "ROXY · Видео" : "ROXY · Фото"),
      el("h1", "", mediaType === "video" ? "Выбери видеомодель" : "Выбери модель изображений"),
      el("p", "", "Одна модель показывается одной карточкой. Ее Text/Image/Video режимы больше не раскиданы по каталогу."),
    );
    top.append(back, copy);

    const count = el("div", "roxy-flow-count", `${products.length} моделей`);
    const grid = el("div", "roxy-flow-model-grid");
    products.forEach((product) => grid.appendChild(renderModelCard(product)));
    center.replaceChildren(top, count, grid);
  }

  async function openMedia(mediaType) {
    if (mediaType !== "image" && mediaType !== "video") return;
    haptic("medium");
    state.mediaType = mediaType;
    const center = ensureCenter();
    if (center) center.replaceChildren(el("div", "roxy-flow-empty", "Загружаю модели…"));
    try {
      await loadModels();
      renderMediaFlow(mediaType);
    } catch (error) {
      if (!center) return;
      const retry = button("Повторить", () => void openMedia(mediaType), "roxy-flow-retry");
      center.replaceChildren(el("div", "roxy-flow-empty is-error", error.message || "Не удалось загрузить модели"), retry);
    }
  }

  function familyLabel(family) {
    return FAMILY_LABELS[family] || family;
  }

  function ensureFamilySelected(model) {
    const select = document.getElementById("modelSelect");
    if (select && [...select.options].some((option) => option.value === model.id)) return true;
    const targetLabel = familyLabel(model.family);
    const tab = [...document.querySelectorAll(".family-tab")]
      .find((buttonNode) => (buttonNode.textContent || "").trim() === targetLabel);
    if (tab) tab.click();
    return false;
  }

  function selectExactModel(modelId, attempt = 0) {
    const model = state.modelById.get(modelId);
    const select = document.getElementById("modelSelect");
    const builder = document.getElementById("builderView");
    if (!model || !select || !builder || builder.hidden) {
      if (attempt < 100) window.setTimeout(() => selectExactModel(modelId, attempt + 1), 40);
      return;
    }

    if (!ensureFamilySelected(model)) {
      if (attempt < 100) window.setTimeout(() => selectExactModel(modelId, attempt + 1), 35);
      return;
    }

    const option = [...select.options].find((item) => item.value === modelId);
    if (!option) {
      if (attempt < 100) window.setTimeout(() => selectExactModel(modelId, attempt + 1), 35);
      return;
    }
    if (select.value !== modelId) {
      select.value = modelId;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    localStorage.setItem("ksu-selected-model", modelId);
    window.setTimeout(mountFocusedBuilder, 0);
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function saveProductContext(product) {
    const context = { key: product.key, title: product.title, mediaType: product.mediaType, variantIds: product.variants.map((model) => model.id) };
    sessionStorage.setItem(PRODUCT_KEY, JSON.stringify(context));
  }

  function restoreProductContext() {
    try {
      const raw = JSON.parse(sessionStorage.getItem(PRODUCT_KEY) || "null");
      if (!raw?.variantIds?.length) return null;
      const variants = raw.variantIds.map((id) => state.modelById.get(id)).filter(Boolean);
      if (!variants.length) return null;
      return { key: raw.key, title: raw.title, mediaType: raw.mediaType, variants };
    } catch (_error) {
      return null;
    }
  }

  function openProduct(product) {
    if (!product?.variants?.length) return;
    haptic("medium");
    state.activeProduct = product;
    saveProductContext(product);
    sessionStorage.setItem(RETURN_KEY, product.mediaType);
    const model = existingVariant(product);
    localStorage.setItem("ksu-selected-model", model.id);
    document.body?.classList.add("roxy-focused-model-pending");
    state.legacy?.close?.();
    if (window.KsuStudioShell?.open) {
      window.KsuStudioShell.open("create");
      selectExactModel(model.id, 0);
      return;
    }
    document.querySelector('.bottom-nav-item[data-shell-nav="create"]')?.click();
    selectExactModel(model.id, 0);
  }

  function compatibleValues(sourceModel, targetModel, sourceDraft) {
    const allowed = new Set((targetModel.ui_schema?.fields || []).map((field) => field.name));
    const values = {};
    for (const [name, value] of Object.entries(sourceDraft?.values || {})) {
      if (allowed.has(name)) values[name] = value;
    }
    return values;
  }

  function moveDraftToVariant(target, uploaded = null, kind = null) {
    const currentId = document.getElementById("modelSelect")?.value || localStorage.getItem("ksu-selected-model");
    const current = state.modelById.get(currentId) || target;
    const drafts = readDrafts();
    const sourceDraft = drafts[current.id] || { values: {}, touched: {}, files: {}, billing_seconds: null };
    const targetDraft = drafts[target.id] || { values: {}, touched: {}, files: {}, billing_seconds: null };
    const values = { ...targetDraft.values, ...compatibleValues(current, target, sourceDraft) };
    const touched = { ...targetDraft.touched, ...sourceDraft.touched };
    const files = { ...targetDraft.files };

    if (uploaded && kind) {
      const field = sourceField(target, kind);
      if (!field) throw new Error("Эта модель не принимает выбранный тип входного файла");
      values[field.name] = field.control === "files" ? [uploaded.url] : uploaded.url;
      touched[field.name] = true;
      files[field.name] = [{ url: uploaded.url, name: uploaded.name, mime_type: uploaded.mime_type, size: uploaded.size }];
    }

    drafts[target.id] = {
      ...targetDraft,
      values,
      touched,
      files,
      billing_seconds: sourceDraft.billing_seconds ?? targetDraft.billing_seconds ?? null,
    };
    writeDrafts(drafts);
  }

  async function uploadSmartSource(file, kind) {
    const product = state.activeProduct || restoreProductContext();
    if (!product || state.smartSourceBusy) return;
    if (!tg?.initData) {
      showSmartStatus("Загрузка доступна при открытии ROXY через Telegram.", true);
      return;
    }
    const target = sourceVariant(product, kind);
    if (!target) {
      showSmartStatus(kind === "video" ? "Эта модель не поддерживает входное видео." : "Эта модель не поддерживает входное фото.", true);
      return;
    }

    state.smartSourceBusy = true;
    renderSmartSourcePanel();
    showSmartStatus(`Загружаю ${file.name}…`);
    try {
      const form = new FormData();
      form.append("file", file, file.name);
      const uploaded = await api("/api/v1/uploads/kie", { method: "POST", body: form });
      moveDraftToVariant(target, uploaded, kind);
      sessionStorage.setItem(SMART_SOURCE_KEY, JSON.stringify({ kind, url: uploaded.url, name: uploaded.name || file.name }));
      localStorage.setItem("ksu-selected-model", target.id);
      selectExactModel(target.id, 0);
      notify("success");
    } catch (error) {
      showSmartStatus(error.message || "Не удалось загрузить файл.", true);
      notify("error");
    } finally {
      state.smartSourceBusy = false;
      window.setTimeout(mountFocusedBuilder, 0);
    }
  }

  function smartSource() {
    try { return JSON.parse(sessionStorage.getItem(SMART_SOURCE_KEY) || "null"); } catch (_error) { return null; }
  }

  function clearSmartSource() {
    const product = state.activeProduct || restoreProductContext();
    if (!product) return;
    sessionStorage.removeItem(SMART_SOURCE_KEY);
    const target = textVariant(product);
    const drafts = readDrafts();
    for (const model of product.variants) {
      const draft = drafts[model.id];
      if (!draft?.values) continue;
      for (const kind of ["image", "video"]) {
        const field = sourceField(model, kind);
        if (!field) continue;
        delete draft.values[field.name];
        delete draft.files?.[field.name];
        delete draft.touched?.[field.name];
      }
    }
    writeDrafts(drafts);
    localStorage.setItem("ksu-selected-model", target.id);
    selectExactModel(target.id, 0);
    renderSmartSourcePanel();
  }

  function showSmartStatus(message, error = false) {
    const status = document.getElementById("roxySmartSourceStatus");
    if (!status) return;
    status.textContent = message || "";
    status.classList.toggle("is-error", error);
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

    const imageTarget = sourceVariant(product, "image");
    const videoTarget = sourceVariant(product, "video");
    if ((!imageTarget || imageTarget.id === textVariant(product)?.id) && !videoTarget) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;

    const head = el("div", "roxy-smart-source-head");
    const copy = el("div");
    copy.append(el("span", "section-kicker", "Входные данные"), el("strong", "", "Режим выбирается автоматически"));
    head.appendChild(copy);
    panel.appendChild(head);

    const actions = el("div", "roxy-smart-source-actions");
    if (imageTarget && imageTarget.id !== textVariant(product)?.id) {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = "image/*";
      input.hidden = true;
      input.addEventListener("change", () => {
        const file = input.files?.[0];
        input.value = "";
        if (file) void uploadSmartSource(file, "image");
      });
      const add = button("Добавить фото", () => input.click(), "roxy-smart-source-button");
      add.disabled = state.smartSourceBusy;
      actions.append(add, input);
    }
    if (videoTarget) {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = "video/*";
      input.hidden = true;
      input.addEventListener("change", () => {
        const file = input.files?.[0];
        input.value = "";
        if (file) void uploadSmartSource(file, "video");
      });
      const add = button("Добавить видео", () => input.click(), "roxy-smart-source-button");
      add.disabled = state.smartSourceBusy;
      actions.append(add, input);
    }
    panel.appendChild(actions);

    const source = smartSource();
    const status = el("div", "roxy-smart-source-status");
    status.id = "roxySmartSourceStatus";
    if (source?.url) {
      const info = el("span", "", `${source.kind === "video" ? "Видео" : "Фото"}: ${source.name || "загружено"}`);
      const remove = button("Убрать", clearSmartSource, "roxy-smart-source-remove");
      status.append(info, remove);
    } else {
      status.textContent = "Без файла ROXY использует текстовый режим. Добавишь фото/видео — нужный режим переключится сам.";
    }
    panel.appendChild(status);
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
    const back = button("←", () => returnFromBuilder(product.mediaType), "roxy-flow-back");
    const copy = el("div", "roxy-focused-model-copy");
    copy.append(el("span", "section-kicker", product.mediaType === "video" ? "Видео" : "Фото"), el("h2", "", product.title));
    const modes = el("div", "roxy-focused-model-modes");
    productModes(product).forEach((label) => modes.appendChild(el("span", "", label)));
    header.append(back, copy, modes);
  }

  function hideDuplicateNativeSource() {
    const product = state.activeProduct || restoreProductContext();
    const selected = state.modelById.get(document.getElementById("modelSelect")?.value || "");
    if (!product || !selected) return;
    const labels = [sourceField(selected, "image"), sourceField(selected, "video")]
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
    hideDuplicateNativeSource();
  }

  function returnFromBuilder(mediaType) {
    sessionStorage.removeItem(RETURN_KEY);
    sessionStorage.removeItem(PRODUCT_KEY);
    sessionStorage.removeItem(SMART_SOURCE_KEY);
    state.activeProduct = null;
    document.body?.classList.remove("roxy-focused-model-flow", "roxy-focused-model-pending");
    state.legacy?.open?.();
    state.mediaType = mediaType;
    if (state.loaded) renderMediaFlow(mediaType);
    else void openMedia(mediaType);
  }

  function interceptClicks(event) {
    const mediaCard = event.target.closest?.("#roxyCreateCenterView .roxy-media-card[data-roxy-media]");
    if (mediaCard && !mediaCard.disabled) {
      const type = mediaCard.dataset.roxyMedia;
      if (type === "image" || type === "video") {
        event.preventDefault();
        event.stopImmediatePropagation();
        void openMedia(type);
        return;
      }
    }

    const builderHome = event.target.closest?.("#builderHomeButton");
    const mediaType = sessionStorage.getItem(RETURN_KEY);
    if (builderHome && mediaType && !document.getElementById("builderView")?.hidden) {
      event.preventDefault();
      event.stopImmediatePropagation();
      returnFromBuilder(mediaType);
      return;
    }

    const route = event.target.closest?.("[data-shell-nav], [data-studio-route]");
    const routeName = route?.dataset?.shellNav || route?.dataset?.studioRoute;
    if (routeName && routeName !== "create") {
      sessionStorage.removeItem(RETURN_KEY);
      sessionStorage.removeItem(PRODUCT_KEY);
      sessionStorage.removeItem(SMART_SOURCE_KEY);
      state.activeProduct = null;
      document.body?.classList.remove("roxy-focused-model-flow", "roxy-focused-model-pending");
    }
  }

  function installLegacyBridge() {
    const legacy = window.RoxyCreateCenter;
    if (!legacy?.open || legacy.__roxyGenerationFlowBridge) return false;
    state.legacy = legacy;
    const bridge = {
      __roxyGenerationFlowBridge: true,
      open() {
        legacy.open();
        window.setTimeout(() => {
          if (state.loaded) renderStart();
          else void loadModels().then(renderStart).catch(renderStart);
        }, 0);
      },
      close() {
        legacy.close();
      },
      chooseMedia(mediaType) {
        if (mediaType === "image" || mediaType === "video") return openMedia(mediaType);
        return legacy.chooseMedia?.(mediaType);
      },
      openMedia,
    };
    window.RoxyCreateCenter = Object.freeze(bridge);
    return true;
  }

  function init() {
    document.addEventListener("click", interceptClicks, true);
    if (!state.observer && document.body) {
      state.observer = new MutationObserver(() => {
        if (!document.getElementById("builderView")?.hidden) mountFocusedBuilder();
      });
      state.observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
    }
    if (installLegacyBridge()) {
      void loadModels().then(() => {
        const restored = restoreProductContext();
        if (restored) {
          state.activeProduct = restored;
          window.setTimeout(mountFocusedBuilder, 0);
        }
      }).catch(() => null);
      return;
    }
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      if (installLegacyBridge() || attempts >= 80) {
        window.clearInterval(timer);
        if (window.RoxyCreateCenter) void loadModels().catch(() => null);
      }
    }, 50);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
