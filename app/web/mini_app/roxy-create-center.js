(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    models: [],
    toolCatalog: new Map(),
    loaded: false,
    loading: false,
    selectedMedia: null,
    helperImageUrl: "",
    helperBusy: false,
    pollToken: 0,
    observer: null,
  };
  const dom = {};

  function authHeaders(json = false) {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    if (json) headers["Content-Type"] = "application/json";
    return headers;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { ...authHeaders(options.body !== undefined && !(options.body instanceof FormData)), ...(options.headers || {}) },
      credentials: "same-origin",
      cache: "no-store",
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const error = new Error(payload?.detail || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
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

  function haptic(kind = "light") {
    try { tg?.HapticFeedback?.impactOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function notify(kind = "success") {
    try { tg?.HapticFeedback?.notificationOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  async function loadContracts() {
    if (state.loaded || state.loading) return;
    state.loading = true;
    try {
      const [models, tools] = await Promise.all([
        api("/api/v1/generations/models"),
        api("/api/v1/prompt-tools").catch(() => ({ items: [] })),
      ]);
      state.models = Array.isArray(models?.models) ? models.models : [];
      state.toolCatalog = new Map((tools?.items || []).map((item) => [item.id, item]));
      state.loaded = true;
      renderMediaCounts();
      renderHelper();
    } finally {
      state.loading = false;
    }
  }

  function mediaModels(mediaType) {
    return state.models.filter((model) => model.media_type === mediaType);
  }

  function preferredModel(mediaType) {
    const remembered = localStorage.getItem("ksu-selected-model");
    return state.models.find((model) => model.id === remembered && model.media_type === mediaType)
      || mediaModels(mediaType)[0]
      || null;
  }

  function mediaCard({ type, icon, title, copy, disabled = false }) {
    const card = button("", () => {
      if (disabled) return;
      void chooseMedia(type);
    }, `roxy-media-card${disabled ? " is-disabled" : ""}`);
    card.dataset.roxyMedia = type;
    if (disabled) {
      card.disabled = true;
      card.setAttribute("aria-disabled", "true");
    }
    const iconNode = el("span", "roxy-media-card-icon", icon);
    const copyNode = el("span", "roxy-media-card-copy");
    copyNode.append(el("strong", "", title), el("small", "", copy));
    const count = el("span", "roxy-media-card-count", disabled ? "Скоро" : "…");
    count.dataset.roxyMediaCount = type;
    card.append(iconNode, copyNode, count);
    return card;
  }

  function buildCreateView() {
    const section = el("section", "roxy-create-center-view");
    section.id = "roxyCreateCenterView";
    section.hidden = true;

    const heading = el("header", "roxy-create-center-heading");
    heading.append(
      el("span", "section-kicker", "ROXY Create"),
      el("h1", "", "Что создаём?"),
      el("p", "", "Сначала выбери формат. Модель и точные настройки ROXY покажет следующим шагом."),
    );

    const grid = el("div", "roxy-media-grid");
    grid.append(
      mediaCard({ type: "image", icon: "▧", title: "Фото", copy: "Генерация, редактирование и референсы" }),
      mediaCard({ type: "video", icon: "▶", title: "Видео", copy: "Text/Image-to-Video, motion и video edit" }),
      mediaCard({ type: "audio", icon: "♪", title: "Музыка", copy: "Отдельный генерационный контур", disabled: true }),
    );

    const note = el("div", "roxy-create-center-note");
    note.append(el("strong", "", "AI-помощник встроен в создание"), el("span", "", "Можно улучшить идею, собрать промпт по фото или подготовить промпт именно для видео."));
    section.append(heading, grid, note);
    return section;
  }

  function mountCreateView() {
    const appMain = document.getElementById("appMain");
    if (!appMain || document.getElementById("roxyCreateCenterView")) return;
    dom.createCenter = buildCreateView();
    appMain.appendChild(dom.createCenter);
  }

  function renderMediaCounts() {
    for (const type of ("image", "video")) {
      const node = document.querySelector(`[data-roxy-media-count="${type}"]`);
      if (node) node.textContent = `${mediaModels(type).length} моделей`;
    }
  }

  function close() {
    state.pollToken += 1;
    const view = document.getElementById("roxyCreateCenterView");
    if (view) view.hidden = true;
    document.body?.classList.remove("roxy-create-center-open");
  }

  function open() {
    mountCreateView();
    window.RoxyDiscovery?.closeCatalog?.();
    window.KsuStudioShell?.open?.("home");
    const createView = document.getElementById("createView");
    if (createView) createView.hidden = true;
    if (dom.createCenter) dom.createCenter.hidden = false;
    document.body?.classList.add("roxy-create-center-open");
    window.scrollTo({ top: 0, behavior: "auto" });
    void loadContracts();
  }

  async function chooseMedia(mediaType) {
    await loadContracts();
    const model = preferredModel(mediaType);
    if (!model) {
      showHelperStatus(`Для формата «${mediaType}» сейчас нет доступных моделей.`, true);
      return;
    }
    state.selectedMedia = mediaType;
    localStorage.setItem("ksu-selected-model", model.id);
    close();
    const createView = document.getElementById("createView");
    if (createView) createView.hidden = false;
    window.KsuStudioShell?.open?.("home");
    haptic("medium");
    openBuilderModel(model, 0);
  }

  function openBuilderModel(model, attempt) {
    const familyCard = [...document.querySelectorAll(".shell-family-card")]
      .find((card) => card.dataset.family === model.family);
    if (!familyCard) {
      if (attempt < 50) window.setTimeout(() => openBuilderModel(model, attempt + 1), 60);
      return;
    }
    familyCard.click();
    selectBuilderModel(model.id, 0);
  }

  function selectBuilderModel(modelId, attempt) {
    const select = document.getElementById("modelSelect");
    if (!select) return;
    const option = [...select.options].find((item) => item.value === modelId);
    if (!option) {
      if (attempt < 50) window.setTimeout(() => selectBuilderModel(modelId, attempt + 1), 50);
      return;
    }
    if (select.value !== modelId) {
      select.value = modelId;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    state.selectedMedia = currentModel()?.media_type || state.selectedMedia;
    renderHelper();
  }

  function currentModel() {
    const selected = document.getElementById("modelSelect")?.value;
    return state.models.find((model) => model.id === selected) || null;
  }

  function promptField() {
    const model = currentModel();
    const promptSchema = model?.ui_schema?.fields?.find((field) => field.name === "prompt");
    if (!promptSchema) return null;
    const fields = [...document.querySelectorAll("#dynamicForm .field")];
    const wrapper = fields.find((field) => field.querySelector(".field-label")?.textContent?.trim() === String(promptSchema.label || "").trim());
    return wrapper?.querySelector("textarea, input") || null;
  }

  function currentPrompt() {
    return String(promptField()?.value || "").trim();
  }

  function applyPrompt(value) {
    const input = promptField();
    if (!input) {
      showHelperStatus("Поле промпта для выбранной модели не найдено.", true);
      return;
    }
    input.value = String(value || "");
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.focus({ preventScroll: true });
    input.scrollIntoView({ behavior: "smooth", block: "center" });
    notify("success");
    showHelperStatus("Промпт применён к текущей генерации.");
  }

  function helperPrice() {
    const tool = state.toolCatalog.get("prompt_builder");
    if (!tool?.enabled) return "Недоступно";
    return `${Number(tool.cost_credits || 0).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ROX`;
  }

  function helperPanel() {
    const panel = el("section", "roxy-prompt-helper");
    panel.id = "roxyPromptHelper";
    const head = el("div", "roxy-prompt-helper-head");
    const copy = el("div");
    copy.append(el("span", "section-kicker", "AI-помощник"), el("h3", "", "Собрать сильный промпт"));
    const price = el("span", "roxy-prompt-helper-price", "—");
    price.id = "roxyPromptHelperPrice";
    head.append(copy, price);

    const controls = el("div", "roxy-prompt-helper-controls");
    const improve = button("✨ Улучшить текущий", () => void runPromptBuilder(false), "roxy-helper-action primary");
    improve.id = "roxyImprovePrompt";
    const photo = button("🖼 Промпт по фото", () => dom.helperFile?.click(), "roxy-helper-action");
    photo.id = "roxyPromptFromPhoto";
    const file = document.createElement("input");
    file.type = "file";
    file.accept = "image/*";
    file.hidden = true;
    file.addEventListener("change", () => void uploadHelperImage(file));
    dom.helperFile = file;
    controls.append(improve, photo, file);

    const imageState = el("div", "roxy-helper-image-state", "Фото-референс не выбран");
    imageState.id = "roxyHelperImageState";
    const status = el("div", "roxy-helper-status");
    status.id = "roxyHelperStatus";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    const result = el("div", "roxy-helper-result");
    result.id = "roxyHelperResult";
    result.hidden = true;
    panel.append(head, controls, imageState, status, result);
    return panel;
  }

  function mountHelper() {
    const dynamic = document.getElementById("dynamicForm");
    if (!dynamic || document.getElementById("roxyPromptHelper")) return;
    const panel = helperPanel();
    dynamic.insertAdjacentElement("beforebegin", panel);
    dom.helper = panel;
    dom.helperResult = document.getElementById("roxyHelperResult");
    renderHelper();
  }

  function showHelperStatus(message, error = false) {
    const status = document.getElementById("roxyHelperStatus");
    if (!status) return;
    status.textContent = message || "";
    status.classList.toggle("is-error", error);
  }

  function renderHelper() {
    mountHelper();
    const model = currentModel();
    const purpose = model?.media_type === "video" ? "video" : "image";
    const action = document.getElementById("roxyImprovePrompt");
    if (action) action.textContent = purpose === "video" ? "🎬 Промпт для видео" : "✨ Улучшить промпт";
    const price = document.getElementById("roxyPromptHelperPrice");
    if (price) price.textContent = helperPrice();
    const tool = state.toolCatalog.get("prompt_builder");
    if (action) action.disabled = Boolean(tool && !tool.enabled) || state.helperBusy;
    const photo = document.getElementById("roxyPromptFromPhoto");
    if (photo) photo.disabled = state.helperBusy;
  }

  async function uploadHelperImage(input) {
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    if (!tg?.initData) {
      showHelperStatus("Открой ROXY через Telegram, чтобы загрузить фото.", true);
      return;
    }
    state.helperBusy = true;
    renderHelper();
    showHelperStatus("Загружаю фото…");
    try {
      const form = new FormData();
      form.append("file", file, file.name);
      const uploaded = await api("/api/v1/uploads/kie", { method: "POST", body: form });
      state.helperImageUrl = String(uploaded?.url || "");
      const imageState = document.getElementById("roxyHelperImageState");
      if (imageState) imageState.textContent = state.helperImageUrl ? `Фото готово: ${file.name}` : "Фото не загружено";
      showHelperStatus("Фото добавлено. Нажми кнопку AI-помощника — он учтёт референс.");
      notify("success");
    } catch (error) {
      state.helperImageUrl = "";
      showHelperStatus(error.message || "Не удалось загрузить фото.", true);
      notify("error");
    } finally {
      state.helperBusy = false;
      renderHelper();
    }
  }

  async function runPromptBuilder(requireImage) {
    if (state.helperBusy) return;
    const tool = state.toolCatalog.get("prompt_builder");
    if (tool && !tool.enabled) {
      showHelperStatus("AI-помощник временно отключён: цена не опубликована.", true);
      return;
    }
    if (!tg?.initData) {
      showHelperStatus("AI-помощник доступен при открытии ROXY через Telegram.", true);
      return;
    }
    if (requireImage && !state.helperImageUrl) {
      dom.helperFile?.click();
      return;
    }
    const model = currentModel();
    const purpose = model?.media_type === "video" ? "video" : "image";
    const text = currentPrompt();
    if (!text && !state.helperImageUrl) {
      showHelperStatus("Напиши идею в поле промпта или добавь фото.", true);
      return;
    }

    state.helperBusy = true;
    state.pollToken += 1;
    const token = state.pollToken;
    renderHelper();
    clearHelperResult();
    showHelperStatus("Собираю промпт…");
    try {
      const task = await api("/api/v1/prompt-tools/prompt-builder", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ text, image_url: state.helperImageUrl || null, purpose }),
      });
      await pollPromptTask(task.id, token);
    } catch (error) {
      showHelperStatus(error.message || "Не удалось запустить AI-помощника.", true);
      notify("error");
      state.helperBusy = false;
      renderHelper();
    }
  }

  async function pollPromptTask(taskId, token) {
    for (let attempt = 0; attempt < 90 && token === state.pollToken; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, attempt < 8 ? 1100 : 2000));
      let task;
      try {
        task = await api(`/api/v1/prompt-tools/${encodeURIComponent(taskId)}`);
      } catch (error) {
        if (attempt < 3) continue;
        showHelperStatus(error.message || "Не удалось получить результат.", true);
        break;
      }
      if (task.status === "failed") {
        showHelperStatus(task.error || "AI-помощник не завершил задачу. ROX возвращены.", true);
        notify("error");
        break;
      }
      if (task.status !== "succeeded") continue;
      renderHelperResult(task.result || {});
      showHelperStatus("Готово. Выбери версию и примени её к генерации.");
      notify("success");
      break;
    }
    if (token === state.pollToken) {
      state.helperBusy = false;
      renderHelper();
    }
  }

  function clearHelperResult() {
    const result = document.getElementById("roxyHelperResult");
    if (!result) return;
    result.hidden = true;
    result.replaceChildren();
  }

  function promptResultBlock(label, value) {
    const block = el("article", "roxy-helper-result-block");
    block.append(el("strong", "", label), el("p", "", value));
    block.appendChild(button("Применить", () => applyPrompt(value), "roxy-helper-apply"));
    return block;
  }

  function renderHelperResult(result) {
    const target = document.getElementById("roxyHelperResult");
    if (!target) return;
    const ru = String(result.prompt_ru || "").trim();
    const en = String(result.prompt_en || "").trim();
    target.replaceChildren();
    if (ru) target.appendChild(promptResultBlock("Русский", ru));
    if (en) target.appendChild(promptResultBlock("English", en));
    target.hidden = !target.children.length;
  }

  function syncModelFromBuilder() {
    if (!state.loaded) return;
    const model = currentModel();
    if (model) state.selectedMedia = model.media_type;
    renderHelper();
  }

  function init() {
    mountCreateView();
    void loadContracts();
    const modelSelect = document.getElementById("modelSelect");
    modelSelect?.addEventListener("change", () => window.setTimeout(syncModelFromBuilder, 0));
    if (!state.observer && document.body) {
      state.observer = new MutationObserver(() => {
        if (!document.getElementById("roxyCreateCenterView")) mountCreateView();
        if (!document.getElementById("roxyPromptHelper") && !document.getElementById("builderView")?.hidden) mountHelper();
      });
      state.observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
    }
  }

  window.RoxyCreateCenter = Object.freeze({
    open,
    close,
    chooseMedia,
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
