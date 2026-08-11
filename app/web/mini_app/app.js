(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const STORAGE_KEY = "ksu-generation-drafts-v1";
  const FAMILY_LABELS = {
    nanobanana: "Nano Banana",
    seedream: "Seedream",
    "gpt-image": "GPT Image",
    wan: "Wan",
    seedance: "Seedance",
    kling: "Kling Motion",
    grok: "Grok",
  };

  const dom = {
    balance: document.getElementById("balanceValue"),
    familyTabs: document.getElementById("familyTabs"),
    modelSelect: document.getElementById("modelSelect"),
    modelMeta: document.getElementById("modelMeta"),
    modelCount: document.getElementById("modelCount"),
    scenarioBlock: document.getElementById("scenarioBlock"),
    dynamicForm: document.getElementById("dynamicForm"),
    resetButton: document.getElementById("resetButton"),
    summaryModel: document.getElementById("summaryModel"),
    summaryChips: document.getElementById("summaryChips"),
    quoteStatus: document.getElementById("quoteStatus"),
    priceCredits: document.getElementById("priceCredits"),
    priceRub: document.getElementById("priceRub"),
    validation: document.getElementById("validationMessage"),
    createButton: document.getElementById("createButton"),
    resultCard: document.getElementById("resultCard"),
    toast: document.getElementById("toast"),
  };

  const state = {
    models: [],
    modelById: new Map(),
    selectedFamily: null,
    selectedModelId: null,
    drafts: loadDrafts(),
    quote: null,
    quoteError: null,
    quoteSeq: 0,
    quoteTimer: null,
    submitting: false,
    uploading: 0,
  };

  function loadDrafts() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (_error) {
      return {};
    }
  }

  function persistDrafts() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.drafts));
    } catch (_error) {
      // Storage is a convenience. The form remains fully functional without it.
    }
  }

  function currentModel() {
    return state.modelById.get(state.selectedModelId) || null;
  }

  function isEmpty(value) {
    if (value === undefined || value === null || value === "") return true;
    if (Array.isArray(value)) return value.length === 0;
    return false;
  }

  function defaultDraft(model) {
    const schema = model.ui_schema || {};
    return {
      values: { ...(schema.defaults || {}) },
      touched: {},
      files: {},
      scenario: schema.scenario?.default || null,
      billing_seconds: null,
    };
  }

  function sanitizeDraft(model, source) {
    const fresh = defaultDraft(model);
    const draft = source && typeof source === "object" ? source : {};
    const allowed = new Set((model.ui_schema?.fields || []).map((field) => field.name));
    const values = { ...fresh.values };
    for (const [name, value] of Object.entries(draft.values || {})) {
      if (allowed.has(name)) values[name] = value;
    }
    const validScenarios = new Set((model.ui_schema?.scenario?.items || []).map((item) => item.id));
    const scenario = validScenarios.has(draft.scenario)
      ? draft.scenario
      : fresh.scenario;
    return {
      values,
      touched: { ...(draft.touched || {}) },
      files: { ...(draft.files || {}) },
      scenario,
      billing_seconds: draft.billing_seconds ?? fresh.billing_seconds,
    };
  }

  function currentDraft() {
    const model = currentModel();
    if (!model) return null;
    if (!state.drafts[model.id]) {
      state.drafts[model.id] = defaultDraft(model);
    }
    state.drafts[model.id] = sanitizeDraft(model, state.drafts[model.id]);
    return state.drafts[model.id];
  }

  function selectedScenario(model, draft) {
    const scenario = model.ui_schema?.scenario;
    if (!scenario) return null;
    return scenario.items.find((item) => item.id === draft.scenario) || scenario.items[0] || null;
  }

  function scenarioControlledFields(model) {
    const names = new Set();
    for (const item of model.ui_schema?.scenario?.items || []) {
      for (const name of item.visible_fields || []) names.add(name);
      for (const name of item.clear_fields || []) names.add(name);
    }
    return names;
  }

  function fieldIsVisible(model, draft, fieldName) {
    const scenario = selectedScenario(model, draft);
    if (!scenario) return true;
    const controlled = scenarioControlledFields(model);
    if (!controlled.has(fieldName)) return true;
    return (scenario.visible_fields || []).includes(fieldName);
  }

  function apiHeaders({ json = false, auth = false } = {}) {
    const headers = {};
    if (json) headers["Content-Type"] = "application/json";
    if (auth && tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function apiFetch(path, options = {}) {
    const response = await fetch(path, options);
    let body = null;
    try {
      body = await response.json();
    } catch (_error) {
      body = null;
    }
    if (!response.ok) {
      const detail = body?.detail || body?.message || `HTTP ${response.status}`;
      throw new Error(String(detail));
    }
    return body;
  }

  function familyLabel(family) {
    return FAMILY_LABELS[family] || family;
  }

  function operationLabel(operation) {
    const labels = {
      text_to_image: "Текст → изображение",
      image_edit: "Редактирование",
      generate_or_edit: "Генерация / редактирование",
      image_to_image: "Изображение → изображение",
      layer_decomposition: "Разбор на слои",
      text_to_video: "Текст → видео",
      image_to_video: "Изображение → видео",
      video_edit: "Редактирование видео",
      reference_to_video: "Референсы → видео",
      text_or_image_to_video: "Текст / изображение → видео",
      multimodal_video: "Мультимодальное видео",
      motion_control: "Motion Control",
      video_upscale: "Апскейл видео",
      video_extend: "Расширение видео",
    };
    return labels[operation] || operation.replaceAll("_", " ");
  }

  function initTelegram() {
    if (!tg) return;
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor("secondary_bg_color");
      tg.setBackgroundColor("bg_color");
    } catch (_error) {
      // Older Telegram clients may not support all color APIs.
    }
    if (tg.MainButton) {
      tg.MainButton.onClick(submitGeneration);
    }
  }

  async function loadModels() {
    const catalog = await apiFetch("/api/v1/generations/models");
    state.models = Array.isArray(catalog.models) ? catalog.models : [];
    state.modelById = new Map(state.models.map((model) => [model.id, model]));
    if (!state.models.length) throw new Error("Каталог моделей пуст");

    for (const model of state.models) {
      if (state.drafts[model.id]) {
        state.drafts[model.id] = sanitizeDraft(model, state.drafts[model.id]);
      }
    }

    const rememberedModel = localStorage.getItem("ksu-selected-model");
    state.selectedModelId = state.modelById.has(rememberedModel)
      ? rememberedModel
      : state.models[0].id;
    state.selectedFamily = currentModel().family;
    renderAll();
    scheduleQuote();
  }

  async function loadMe() {
    if (!tg?.initData) {
      dom.balance.textContent = "Telegram";
      return;
    }
    try {
      const me = await apiFetch("/api/v1/me", {
        headers: apiHeaders({ auth: true }),
      });
      dom.balance.textContent = `${Number(me.balance_rox || 0).toLocaleString("ru-RU")} кр.`;
    } catch (_error) {
      dom.balance.textContent = "—";
    }
  }

  function renderAll() {
    renderFamilyTabs();
    renderModelSelect();
    renderModelMeta();
    renderScenario();
    renderDynamicForm();
    renderSummary();
    renderValidation();
    updateCreateControls();
  }

  function renderFamilyTabs() {
    const families = [...new Set(state.models.map((model) => model.family))];
    dom.familyTabs.replaceChildren();
    for (const family of families) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "family-tab";
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", String(family === state.selectedFamily));
      button.textContent = familyLabel(family);
      button.addEventListener("click", () => {
        state.selectedFamily = family;
        const current = currentModel();
        if (!current || current.family !== family) {
          const first = state.models.find((model) => model.family === family);
          if (first) selectModel(first.id);
        } else {
          renderFamilyTabs();
          renderModelSelect();
        }
      });
      dom.familyTabs.appendChild(button);
    }
  }

  function renderModelSelect() {
    const models = state.models.filter((model) => model.family === state.selectedFamily);
    dom.modelSelect.replaceChildren();
    for (const model of models) {
      const option = document.createElement("option");
      option.value = model.id;
      option.textContent = model.title;
      option.selected = model.id === state.selectedModelId;
      dom.modelSelect.appendChild(option);
    }
    dom.modelCount.textContent = `${models.length} моделей`;
  }

  function renderModelMeta() {
    const model = currentModel();
    if (!model) return;
    dom.modelMeta.replaceChildren(
      metaPill(operationLabel(model.operation)),
      metaPill(model.media_type === "video" ? "Видео" : "Изображение"),
      metaPill(
        model.price_mode === "per_second"
          ? `${model.price_credits} кр./сек`
          : `${model.price_credits} кр.`,
      ),
    );
  }

  function metaPill(text) {
    const item = document.createElement("span");
    item.className = "meta-pill";
    item.textContent = text;
    return item;
  }

  function selectModel(modelId) {
    const model = state.modelById.get(modelId);
    if (!model) return;
    state.selectedModelId = model.id;
    state.selectedFamily = model.family;
    state.quote = null;
    state.quoteError = null;
    localStorage.setItem("ksu-selected-model", model.id);
    currentDraft();
    persistDrafts();
    renderAll();
    scheduleQuote();
    tg?.HapticFeedback?.selectionChanged?.();
  }

  function renderScenario() {
    const model = currentModel();
    const draft = currentDraft();
    const scenario = model?.ui_schema?.scenario;
    if (!model || !draft || !scenario?.items?.length) {
      dom.scenarioBlock.hidden = true;
      dom.scenarioBlock.replaceChildren();
      return;
    }

    dom.scenarioBlock.hidden = false;
    const title = document.createElement("div");
    title.className = "scenario-title";
    title.textContent = "Режим входных данных";
    const segmented = document.createElement("div");
    segmented.className = "segmented";

    for (const item of scenario.items) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = item.id === draft.scenario ? "active" : "";
      button.textContent = item.title;
      button.addEventListener("click", () => setScenario(item.id));
      segmented.appendChild(button);
    }
    dom.scenarioBlock.replaceChildren(title, segmented);
  }

  function setScenario(scenarioId) {
    const model = currentModel();
    const draft = currentDraft();
    const scenario = model?.ui_schema?.scenario?.items?.find((item) => item.id === scenarioId);
    if (!model || !draft || !scenario) return;

    draft.scenario = scenarioId;
    for (const field of scenario.clear_fields || []) {
      delete draft.values[field];
      delete draft.files[field];
      delete draft.touched[field];
    }
    state.quote = null;
    state.quoteError = null;
    persistDrafts();
    renderScenario();
    renderDynamicForm();
    renderSummary();
    renderValidation();
    updateCreateControls();
    scheduleQuote();
    tg?.HapticFeedback?.selectionChanged?.();
  }

  function renderDynamicForm() {
    const model = currentModel();
    const draft = currentDraft();
    if (!model || !draft) return;
    dom.dynamicForm.replaceChildren();
    const schema = model.ui_schema || {};

    for (const group of schema.groups || []) {
      const fields = (schema.fields || []).filter(
        (field) => field.group === group.id && fieldIsVisible(model, draft, field.name),
      );
      if (!fields.length) continue;

      const groupEl = document.createElement("section");
      groupEl.className = "form-group";
      const heading = document.createElement("h3");
      heading.className = "group-title";
      heading.textContent = group.title;
      groupEl.appendChild(heading);
      for (const field of fields) groupEl.appendChild(renderField(field, model, draft));
      dom.dynamicForm.appendChild(groupEl);
    }

    if (schema.billing_seconds) {
      const group = document.createElement("section");
      group.className = "form-group";
      const heading = document.createElement("h3");
      heading.className = "group-title";
      heading.textContent = "Расчёт видео";
      group.appendChild(renderBillingSeconds(schema.billing_seconds, draft));
      dom.dynamicForm.appendChild(group);
    }
  }

  function fieldLabel(field) {
    const label = document.createElement("label");
    label.className = `field-label${field.required ? " required" : ""}`;
    label.textContent = field.label;
    return label;
  }

  function renderField(field, model, draft) {
    const wrapper = document.createElement("div");
    wrapper.className = "field";
    const value = draft.values[field.name];

    if (field.control === "toggle") {
      const row = document.createElement("div");
      row.className = "toggle-row";
      row.appendChild(fieldLabel(field));
      const toggle = document.createElement("label");
      toggle.className = "toggle";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = Boolean(value);
      input.addEventListener("change", () => setFieldValue(field.name, input.checked));
      const track = document.createElement("span");
      track.className = "toggle-track";
      toggle.append(input, track);
      row.appendChild(toggle);
      wrapper.appendChild(row);
      return wrapper;
    }

    wrapper.appendChild(fieldLabel(field));

    if (field.control === "textarea" || field.control === "json") {
      const input = document.createElement("textarea");
      input.className = field.control === "json" ? "json-input" : "textarea";
      input.placeholder = field.placeholder || "";
      input.value = value == null ? "" : field.control === "json" && typeof value !== "string"
        ? JSON.stringify(value, null, 2)
        : String(value);
      input.addEventListener("input", () => setFieldValue(field.name, input.value, false));
      wrapper.appendChild(input);
      return wrapper;
    }

    if (field.control === "file" || field.control === "files") {
      wrapper.appendChild(renderFileControl(field, model, draft));
      return wrapper;
    }

    const input = document.createElement("input");
    input.className = "input";
    input.type = field.control === "number" ? "number" : "text";
    input.placeholder = field.placeholder || "";
    if (field.min !== undefined) input.min = String(field.min);
    if (field.max !== undefined) input.max = String(field.max);
    if (field.step !== undefined) input.step = String(field.step);
    input.value = value ?? "";

    if (field.control === "combobox" && field.suggestions?.length) {
      const listId = `choices-${model.id}-${field.name}`.replace(/[^a-zA-Z0-9_-]/g, "-");
      input.setAttribute("list", listId);
      const dataList = document.createElement("datalist");
      dataList.id = listId;
      for (const suggestion of field.suggestions) {
        const option = document.createElement("option");
        option.value = String(suggestion);
        dataList.appendChild(option);
      }
      wrapper.append(input, dataList);
    } else {
      wrapper.appendChild(input);
    }

    input.addEventListener("input", () => {
      if (field.control === "number") {
        setFieldValue(field.name, input.value === "" ? null : Number(input.value), false);
      } else {
        setFieldValue(field.name, input.value, false);
      }
    });

    if (field.suffix) {
      const help = document.createElement("div");
      help.className = "field-help";
      help.textContent = `Единица: ${field.suffix}`;
      wrapper.appendChild(help);
    }
    return wrapper;
  }

  function renderBillingSeconds(config, draft) {
    const wrapper = document.createElement("div");
    wrapper.className = "field";
    const label = document.createElement("label");
    label.className = `field-label${config.required ? " required" : ""}`;
    label.textContent = config.label || "Длительность для расчёта";
    const input = document.createElement("input");
    input.className = "input";
    input.type = "number";
    input.step = "1";
    input.min = String(config.min || 1);
    input.max = String(config.max || 600);
    input.value = draft.billing_seconds ?? "";
    input.addEventListener("input", () => {
      draft.billing_seconds = input.value === "" ? null : Number(input.value);
      persistDrafts();
      onDraftChanged(false);
    });
    const help = document.createElement("div");
    help.className = "field-help";
    help.textContent = "Используется только для серверного расчёта цены за секунду.";
    wrapper.append(label, input, help);
    return wrapper;
  }

  function renderFileControl(field, model, draft) {
    const box = document.createElement("div");
    box.className = "upload-box";
    const row = document.createElement("div");
    row.className = "upload-row";
    const fileInput = document.createElement("input");
    fileInput.className = "file-input";
    fileInput.type = "file";
    fileInput.accept = field.accept || "image/*,video/*,audio/*";
    fileInput.multiple = field.control === "files" && (field.max_items || 99) > 1;
    const choose = document.createElement("button");
    choose.type = "button";
    choose.className = "upload-button";
    choose.textContent = "Загрузить";
    choose.addEventListener("click", () => fileInput.click());
    const urlInput = document.createElement("input");
    urlInput.className = "input upload-url";
    urlInput.type = "url";
    urlInput.placeholder = "или вставьте URL";
    urlInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        addRemoteUrl(field, urlInput.value);
        urlInput.value = "";
      }
    });
    row.append(choose, urlInput, fileInput);
    box.appendChild(row);

    const items = document.createElement("div");
    items.className = "upload-items";
    const metadata = Array.isArray(draft.files[field.name]) ? draft.files[field.name] : [];
    const urls = field.control === "files"
      ? (Array.isArray(draft.values[field.name]) ? draft.values[field.name] : [])
      : (draft.values[field.name] ? [draft.values[field.name]] : []);

    urls.forEach((url, index) => {
      const item = document.createElement("div");
      item.className = "upload-item";
      const name = document.createElement("span");
      name.textContent = metadata[index]?.name || shortUrl(url);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "remove-upload";
      remove.textContent = "Удалить";
      remove.addEventListener("click", () => removeUpload(field, index));
      item.append(name, remove);
      items.appendChild(item);
    });
    box.appendChild(items);

    fileInput.addEventListener("change", async () => {
      const files = [...(fileInput.files || [])];
      if (!files.length) return;
      const maxItems = field.max_items || (field.control === "file" ? 1 : 20);
      const existing = field.control === "files" ? urls.length : 0;
      const accepted = files.slice(0, Math.max(0, maxItems - existing));
      for (const file of accepted) {
        if (field.max_size_mb && file.size > field.max_size_mb * 1024 * 1024) {
          showToast(`Файл ${file.name} больше ${field.max_size_mb} МБ`);
          continue;
        }
        await uploadLocalFile(field, file);
      }
      fileInput.value = "";
    });

    return box;
  }

  function shortUrl(url) {
    try {
      const parsed = new URL(url);
      return `${parsed.hostname}${parsed.pathname}`.slice(-60);
    } catch (_error) {
      return String(url).slice(-60);
    }
  }

  function addRemoteUrl(field, rawUrl) {
    const value = rawUrl.trim();
    if (!value) return;
    try {
      const parsed = new URL(value);
      if (!/^https?:$/.test(parsed.protocol)) throw new Error("protocol");
    } catch (_error) {
      showToast("Нужен корректный HTTP/HTTPS URL");
      return;
    }
    const draft = currentDraft();
    const maxItems = field.max_items || (field.control === "file" ? 1 : 20);
    if (field.control === "files") {
      const current = Array.isArray(draft.values[field.name]) ? [...draft.values[field.name]] : [];
      if (current.length >= maxItems) {
        showToast(`Максимум файлов: ${maxItems}`);
        return;
      }
      current.push(value);
      draft.values[field.name] = current;
      draft.files[field.name] = [
        ...(Array.isArray(draft.files[field.name]) ? draft.files[field.name] : []),
        { url: value, name: shortUrl(value) },
      ];
    } else {
      draft.values[field.name] = value;
      draft.files[field.name] = [{ url: value, name: shortUrl(value) }];
    }
    draft.touched[field.name] = true;
    persistDrafts();
    onDraftChanged(true);
  }

  async function uploadLocalFile(field, file) {
    if (!tg?.initData) {
      showToast("Загрузка доступна при открытии Mini App через Telegram");
      return;
    }
    const draft = currentDraft();
    state.uploading += 1;
    updateCreateControls();
    showToast(`Загружаю ${file.name}…`, 1200);

    try {
      const duration = file.type.startsWith("video/") ? await readVideoDuration(file) : null;
      const form = new FormData();
      form.append("file", file, file.name);
      const uploaded = await apiFetch("/api/v1/uploads/kie", {
        method: "POST",
        headers: apiHeaders({ auth: true }),
        body: form,
      });

      const meta = {
        url: uploaded.url,
        name: uploaded.name || file.name,
        mime_type: uploaded.mime_type || file.type,
        size: uploaded.size || file.size,
      };
      if (field.control === "files") {
        const urls = Array.isArray(draft.values[field.name]) ? [...draft.values[field.name]] : [];
        const files = Array.isArray(draft.files[field.name]) ? [...draft.files[field.name]] : [];
        urls.push(uploaded.url);
        files.push(meta);
        draft.values[field.name] = urls;
        draft.files[field.name] = files;
      } else {
        draft.values[field.name] = uploaded.url;
        draft.files[field.name] = [meta];
      }
      draft.touched[field.name] = true;
      maybeApplyVideoDuration(duration);
      persistDrafts();
      tg?.HapticFeedback?.notificationOccurred?.("success");
    } catch (error) {
      showToast(error.message || "Не удалось загрузить файл");
      tg?.HapticFeedback?.notificationOccurred?.("error");
    } finally {
      state.uploading -= 1;
      renderDynamicForm();
      onDraftChanged(false);
    }
  }

  function removeUpload(field, index) {
    const draft = currentDraft();
    if (field.control === "files") {
      const urls = Array.isArray(draft.values[field.name]) ? [...draft.values[field.name]] : [];
      const files = Array.isArray(draft.files[field.name]) ? [...draft.files[field.name]] : [];
      urls.splice(index, 1);
      files.splice(index, 1);
      if (urls.length) draft.values[field.name] = urls;
      else delete draft.values[field.name];
      draft.files[field.name] = files;
    } else {
      delete draft.values[field.name];
      delete draft.files[field.name];
    }
    draft.touched[field.name] = true;
    persistDrafts();
    renderDynamicForm();
    onDraftChanged(false);
  }

  function readVideoDuration(file) {
    return new Promise((resolve) => {
      const url = URL.createObjectURL(file);
      const video = document.createElement("video");
      video.preload = "metadata";
      video.onloadedmetadata = () => {
        const value = Number.isFinite(video.duration) ? Math.max(1, Math.round(video.duration)) : null;
        URL.revokeObjectURL(url);
        resolve(value);
      };
      video.onerror = () => {
        URL.revokeObjectURL(url);
        resolve(null);
      };
      video.src = url;
    });
  }

  function maybeApplyVideoDuration(duration) {
    if (!duration) return;
    const model = currentModel();
    const draft = currentDraft();
    const config = model?.ui_schema?.billing_seconds;
    if (!model || !draft || !config) return;
    const min = Number(config.min || 1);
    const max = Number(config.max || 600);
    draft.billing_seconds = Math.min(max, Math.max(min, duration));
  }

  function setFieldValue(name, value, rerender = false) {
    const draft = currentDraft();
    if (!draft) return;
    if (value === null || value === "") delete draft.values[name];
    else draft.values[name] = value;
    draft.touched[name] = true;
    persistDrafts();
    if (rerender) renderDynamicForm();
    onDraftChanged(false);
  }

  function onDraftChanged(renderForm = false) {
    state.quote = null;
    state.quoteError = null;
    if (renderForm) renderDynamicForm();
    renderSummary();
    renderValidation();
    updateCreateControls();
    scheduleQuote();
  }

  function scenarioValidation(model, draft) {
    const scenario = selectedScenario(model, draft);
    if (!scenario) return [];
    const missing = [];
    for (const name of scenario.required_fields || []) {
      if (isEmpty(draft.values[name])) missing.push(name);
    }
    const any = scenario.required_any || [];
    if (any.length && !any.some((name) => !isEmpty(draft.values[name]))) {
      missing.push(any.join("|"));
    }
    return missing;
  }

  function validationErrors() {
    const model = currentModel();
    const draft = currentDraft();
    if (!model || !draft) return ["Модель не выбрана"];
    const errors = [];
    const fields = model.ui_schema?.fields || [];
    for (const field of fields) {
      if (!fieldIsVisible(model, draft, field.name)) continue;
      if (field.required && isEmpty(draft.values[field.name])) {
        errors.push(`Заполните «${field.label}»`);
      }
      if (field.control === "json" && !isEmpty(draft.values[field.name])) {
        try {
          JSON.parse(draft.values[field.name]);
        } catch (_error) {
          errors.push(`Исправьте JSON в «${field.label}»`);
        }
      }
    }

    for (const rule of scenarioValidation(model, draft)) {
      if (rule.includes("|")) errors.push("Добавьте хотя бы один референс для выбранного режима");
      else {
        const field = fields.find((item) => item.name === rule);
        errors.push(`Заполните «${field?.label || rule}»`);
      }
    }

    const billing = model.ui_schema?.billing_seconds;
    if (billing?.required && !draft.billing_seconds) {
      errors.push(`Заполните «${billing.label || "Длительность"}»`);
    }
    if (draft.billing_seconds && billing) {
      if (billing.min && draft.billing_seconds < billing.min) errors.push(`Минимум ${billing.min} сек.`);
      if (billing.max && draft.billing_seconds > billing.max) errors.push(`Максимум ${billing.max} сек.`);
    }
    return [...new Set(errors)];
  }

  function buildPayload() {
    const model = currentModel();
    const draft = currentDraft();
    if (!model || !draft) return null;
    const parameters = {};
    for (const field of model.ui_schema?.fields || []) {
      if (field.name === "prompt" || !fieldIsVisible(model, draft, field.name)) continue;
      const value = draft.values[field.name];
      if (isEmpty(value)) continue;
      if (field.control === "json") parameters[field.name] = JSON.parse(value);
      else parameters[field.name] = value;
    }
    const payload = {
      model_id: model.id,
      prompt: String(draft.values.prompt || ""),
      parameters,
    };
    if (draft.billing_seconds) payload.billing_seconds = Number(draft.billing_seconds);
    return payload;
  }

  function scheduleQuote() {
    clearTimeout(state.quoteTimer);
    const errors = validationErrors();
    if (errors.length || state.uploading) {
      renderQuote();
      return;
    }
    state.quoteTimer = setTimeout(refreshQuote, 350);
  }

  async function refreshQuote() {
    const payload = buildPayload();
    if (!payload) return;
    const seq = ++state.quoteSeq;
    dom.quoteStatus.textContent = "Считаю…";
    try {
      const quote = await apiFetch("/api/v1/generations/quote", {
        method: "POST",
        headers: apiHeaders({ json: true }),
        body: JSON.stringify(payload),
      });
      if (seq !== state.quoteSeq) return;
      state.quote = quote;
      state.quoteError = null;
    } catch (error) {
      if (seq !== state.quoteSeq) return;
      state.quote = null;
      state.quoteError = error.message;
    }
    renderQuote();
    renderValidation();
    updateCreateControls();
  }

  function renderQuote() {
    if (state.quote) {
      dom.quoteStatus.textContent = "Актуально";
      dom.priceCredits.textContent = `${formatNumber(state.quote.cost_credits)} кр.`;
      dom.priceRub.textContent = `≈ ${formatMoney(state.quote.cost_rub)} ₽`;
      return;
    }
    dom.quoteStatus.textContent = state.quoteError ? "Нужно исправить" : "";
    dom.priceCredits.textContent = "—";
    dom.priceRub.textContent = "";
  }

  function renderSummary() {
    const model = currentModel();
    const draft = currentDraft();
    if (!model || !draft) return;
    const scenario = selectedScenario(model, draft);
    dom.summaryModel.textContent = scenario
      ? `${model.title} · ${scenario.title}`
      : model.title;
    dom.summaryChips.replaceChildren();

    const fields = new Map((model.ui_schema?.fields || []).map((field) => [field.name, field]));
    for (const name of model.ui_schema?.summary_fields || []) {
      const field = fields.get(name);
      if (!field || !fieldIsVisible(model, draft, name)) continue;
      const value = draft.values[name];
      const touched = Boolean(draft.touched[name]);
      if (field.control === "toggle" && !touched && isEmpty(value)) continue;
      if (isEmpty(value) && field.control !== "toggle") continue;
      const chip = document.createElement("span");
      chip.className = "summary-chip";
      chip.textContent = `${field.label}: ${formatSettingValue(field, value, draft)}`;
      dom.summaryChips.appendChild(chip);
    }

    if (draft.billing_seconds) {
      const chip = document.createElement("span");
      chip.className = "summary-chip";
      chip.textContent = `Расчёт: ${draft.billing_seconds} сек.`;
      dom.summaryChips.appendChild(chip);
    }
    if (!dom.summaryChips.children.length) {
      const chip = document.createElement("span");
      chip.className = "summary-chip";
      chip.textContent = "Заполните настройки";
      dom.summaryChips.appendChild(chip);
    }
    renderQuote();
  }

  function formatSettingValue(field, value, draft) {
    if (field.control === "toggle") return value ? "Да" : "Нет";
    if (field.control === "file" || field.control === "files") {
      const files = Array.isArray(draft.files[field.name]) ? draft.files[field.name] : [];
      const count = field.control === "files"
        ? (Array.isArray(value) ? value.length : 0)
        : (value ? 1 : 0);
      if (count === 1) return files[0]?.name || "1 файл";
      return `${count} файла`;
    }
    if (Array.isArray(value)) return `${value.length} шт.`;
    return String(value);
  }

  function renderValidation() {
    const errors = validationErrors();
    dom.validation.className = "validation-message";
    if (state.uploading) {
      dom.validation.textContent = "Дождитесь завершения загрузки файлов";
      return;
    }
    if (errors.length) {
      dom.validation.classList.add("error");
      dom.validation.textContent = errors[0];
      return;
    }
    if (state.quoteError) {
      dom.validation.classList.add("error");
      dom.validation.textContent = state.quoteError;
      return;
    }
    if (state.quote) {
      dom.validation.classList.add("ok");
      dom.validation.textContent = "Настройки готовы к запуску";
    } else {
      dom.validation.textContent = "Проверяю настройки…";
    }
  }

  function updateCreateControls() {
    const ready = !state.submitting && !state.uploading && !validationErrors().length && Boolean(state.quote);
    dom.createButton.disabled = !ready;
    dom.createButton.textContent = state.submitting
      ? "Запускаю…"
      : state.quote
        ? `Создать · ${formatNumber(state.quote.cost_credits)} кр.`
        : "Создать";

    if (!tg?.MainButton) return;
    if (!tg.initData) {
      tg.MainButton.hide();
      return;
    }
    tg.MainButton.setParams({
      text: state.quote ? `Создать · ${formatNumber(state.quote.cost_credits)} кр.` : "Создать",
      is_active: ready,
      is_visible: true,
    });
    if (ready) tg.MainButton.enable();
    else tg.MainButton.disable();
    if (state.submitting) tg.MainButton.showProgress();
    else tg.MainButton.hideProgress();
  }

  async function submitGeneration() {
    if (state.submitting || state.uploading) return;
    const errors = validationErrors();
    if (errors.length) {
      showToast(errors[0]);
      return;
    }
    if (!tg?.initData) {
      showToast("Откройте этот экран через Telegram-бота");
      return;
    }
    const payload = buildPayload();
    if (!payload) return;

    state.submitting = true;
    dom.resultCard.hidden = true;
    updateCreateControls();
    try {
      const result = await apiFetch("/api/v1/generations", {
        method: "POST",
        headers: apiHeaders({ json: true, auth: true }),
        body: JSON.stringify(payload),
      });
      dom.resultCard.hidden = false;
      dom.resultCard.innerHTML = "";
      const title = document.createElement("h3");
      title.textContent = "Генерация запущена";
      const text = document.createElement("p");
      text.textContent = `Задача ${result.id} поставлена в очередь. Списано ${formatNumber(result.cost_credits)} кр.`;
      dom.resultCard.append(title, text);
      tg.HapticFeedback?.notificationOccurred?.("success");
      showToast("Задача отправлена в генерацию");
      await loadMe();
    } catch (error) {
      tg.HapticFeedback?.notificationOccurred?.("error");
      showToast(error.message || "Не удалось запустить генерацию");
    } finally {
      state.submitting = false;
      updateCreateControls();
    }
  }

  function resetCurrentDraft() {
    const model = currentModel();
    if (!model) return;
    state.drafts[model.id] = defaultDraft(model);
    state.quote = null;
    state.quoteError = null;
    persistDrafts();
    renderScenario();
    renderDynamicForm();
    renderSummary();
    renderValidation();
    updateCreateControls();
    scheduleQuote();
    tg?.HapticFeedback?.impactOccurred?.("light");
  }

  function formatNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value ?? "—");
    return number.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
  }

  function formatMoney(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value ?? "—");
    return number.toLocaleString("ru-RU", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  }

  let toastTimer = null;
  function showToast(message, duration = 2600) {
    clearTimeout(toastTimer);
    dom.toast.textContent = message;
    dom.toast.hidden = false;
    toastTimer = setTimeout(() => {
      dom.toast.hidden = true;
    }, duration);
  }

  dom.modelSelect.addEventListener("change", () => selectModel(dom.modelSelect.value));
  dom.resetButton.addEventListener("click", resetCurrentDraft);
  dom.createButton.addEventListener("click", submitGeneration);

  initTelegram();
  Promise.all([loadModels(), loadMe()]).catch((error) => {
    dom.validation.className = "validation-message error";
    dom.validation.textContent = error.message || "Не удалось загрузить экран";
    showToast(error.message || "Ошибка загрузки");
  });
})();
