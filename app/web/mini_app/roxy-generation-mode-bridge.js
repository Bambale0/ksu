(() => {
  "use strict";

  const PRODUCT_KEY = "roxy-generation-product-context";
  const SMART_SOURCE_KEY = "roxy-generation-smart-source";
  const DRAFTS_KEY = "ksu-generation-drafts-v1";
  const RESUME_KEY = "ksu-studio-open-builder";
  const tg = window.Telegram?.WebApp ?? null;

  let catalogPromise = null;
  let busy = false;

  function productContext() {
    try {
      const value = JSON.parse(sessionStorage.getItem(PRODUCT_KEY) || "null");
      return value?.variantIds?.length ? value : null;
    } catch (_error) {
      return null;
    }
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

  async function catalog() {
    if (!catalogPromise) {
      catalogPromise = fetch("/api/v1/generations/models", {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      }).then(async (response) => {
        const payload = await response.json().catch(() => null);
        if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
        const models = Array.isArray(payload?.models) ? payload.models : [];
        return new Map(models.map((model) => [model.id, model]));
      });
    }
    return catalogPromise;
  }

  function operationTarget(variants, mediaType, kind) {
    if (kind === "video") {
      return variants.find((model) => model.operation === "video_edit") || null;
    }
    if (mediaType === "video") {
      return variants.find((model) => ["image_to_video", "text_or_image_to_video", "multimodal_video"].includes(model.operation)) || null;
    }
    return variants.find((model) => ["image_edit", "image_to_image", "generate_or_edit"].includes(model.operation)) || null;
  }

  function textTarget(variants) {
    return variants.find((model) => ["generate_or_edit", "text_or_image_to_video", "multimodal_video"].includes(model.operation))
      || variants.find((model) => ["text_to_image", "text_to_video"].includes(model.operation))
      || variants[0]
      || null;
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

  function compatibleValues(target, sourceDraft) {
    const allowed = new Set((target?.ui_schema?.fields || []).map((field) => field.name));
    const values = {};
    for (const [key, value] of Object.entries(sourceDraft?.values || {})) {
      if (allowed.has(key)) values[key] = value;
    }
    return values;
  }

  function setStatus(message, isError = false) {
    const status = document.getElementById("roxySmartSourceStatus");
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("is-error", isError);
  }

  function resumeWith(modelId) {
    localStorage.setItem("ksu-selected-model", modelId);
    sessionStorage.setItem(RESUME_KEY, "1");
    document.body?.classList.add("roxy-focused-model-pending");
    window.location.reload();
  }

  async function upload(file, kind) {
    if (busy) return;
    const context = productContext();
    if (!context) return;
    if (!tg?.initData) {
      setStatus("Загрузка доступна при открытии ROXY через Telegram.", true);
      return;
    }

    busy = true;
    setStatus(`Загружаю ${file.name}…`);
    try {
      const models = await catalog();
      const variants = context.variantIds.map((id) => models.get(id)).filter(Boolean);
      const target = operationTarget(variants, context.mediaType, kind);
      if (!target) throw new Error(kind === "video" ? "Эта модель не поддерживает входное видео." : "Эта модель не поддерживает входное фото.");
      const field = sourceField(target, kind);
      if (!field) throw new Error("У модели нет совместимого поля для этого файла.");

      const form = new FormData();
      form.append("file", file, file.name);
      const response = await fetch("/api/v1/uploads/kie", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-Telegram-Init-Data": tg.initData },
        body: form,
      });
      const uploaded = await response.json().catch(() => null);
      if (!response.ok) throw new Error(uploaded?.detail || `HTTP ${response.status}`);

      const drafts = readDrafts();
      const currentId = localStorage.getItem("ksu-selected-model");
      const sourceDraft = drafts[currentId] || { values: {}, touched: {}, files: {}, billing_seconds: null };
      const targetDraft = drafts[target.id] || { values: {}, touched: {}, files: {}, billing_seconds: null };
      const values = { ...targetDraft.values, ...compatibleValues(target, sourceDraft) };
      const touched = { ...targetDraft.touched, ...sourceDraft.touched };
      const files = { ...targetDraft.files };

      values[field.name] = field.control === "files" ? [uploaded.url] : uploaded.url;
      touched[field.name] = true;
      files[field.name] = [{
        url: uploaded.url,
        name: uploaded.name || file.name,
        mime_type: uploaded.mime_type || file.type,
        size: uploaded.size || file.size,
      }];

      drafts[target.id] = {
        ...targetDraft,
        values,
        touched,
        files,
        billing_seconds: sourceDraft.billing_seconds ?? targetDraft.billing_seconds ?? null,
      };
      writeDrafts(drafts);
      sessionStorage.setItem(SMART_SOURCE_KEY, JSON.stringify({
        kind,
        url: uploaded.url,
        name: uploaded.name || file.name,
      }));
      try { tg?.HapticFeedback?.notificationOccurred?.("success"); } catch (_error) { /* optional */ }
      resumeWith(target.id);
    } catch (error) {
      busy = false;
      setStatus(error.message || "Не удалось загрузить файл.", true);
      try { tg?.HapticFeedback?.notificationOccurred?.("error"); } catch (_error) { /* optional */ }
    }
  }

  async function clearSource() {
    if (busy) return;
    const context = productContext();
    if (!context) return;
    busy = true;
    try {
      const models = await catalog();
      const variants = context.variantIds.map((id) => models.get(id)).filter(Boolean);
      const target = textTarget(variants);
      if (!target) throw new Error("Не удалось вернуть текстовый режим.");

      const drafts = readDrafts();
      for (const model of variants) {
        const draft = drafts[model.id];
        if (!draft?.values) continue;
        for (const kind of ["image", "video"]) {
          const field = sourceField(model, kind);
          if (!field) continue;
          delete draft.values[field.name];
          if (draft.files) delete draft.files[field.name];
          if (draft.touched) delete draft.touched[field.name];
        }
      }
      writeDrafts(drafts);
      sessionStorage.removeItem(SMART_SOURCE_KEY);
      resumeWith(target.id);
    } catch (error) {
      busy = false;
      setStatus(error.message || "Не удалось убрать источник.", true);
    }
  }

  function onChange(event) {
    const input = event.target.closest?.("#roxySmartSourcePanel input[type='file']");
    if (!input) return;
    const file = input.files?.[0];
    if (!file) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const kind = file.type.startsWith("video/") || input.accept.includes("video") ? "video" : "image";
    void upload(file, kind);
  }

  function onClick(event) {
    const remove = event.target.closest?.("#roxySmartSourcePanel .roxy-smart-source-remove");
    if (!remove) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    void clearSource();
  }

  function init() {
    if (productContext() && sessionStorage.getItem(RESUME_KEY) === "1") {
      document.body?.classList.add("roxy-focused-model-pending");
    }
    document.addEventListener("change", onChange, true);
    document.addEventListener("click", onClick, true);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
