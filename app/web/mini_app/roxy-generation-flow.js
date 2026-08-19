(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const RETURN_KEY = "roxy-generation-flow-return";
  const state = {
    models: [],
    loaded: false,
    loading: false,
    mediaType: null,
    lane: "all",
    legacy: null,
    center: null,
    observer: null,
  };

  function haptic(kind = "light") {
    try { tg?.HapticFeedback?.impactOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function authHeaders() {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function api(path) {
    const response = await fetch(path, {
      headers: authHeaders(),
      credentials: "same-origin",
      cache: "no-store",
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
      state.loaded = true;
      return state.models;
    } finally {
      state.loading = false;
    }
  }

  function mediaModels(mediaType) {
    return state.models.filter((model) => model.media_type === mediaType);
  }

  function operationLane(model) {
    const operation = String(model?.operation || "").toLowerCase();
    const id = String(model?.id || "").toLowerCase();
    if (model?.media_type === "image") {
      if (operation.includes("edit") || operation.includes("image_to_image") || operation.includes("generate_or_edit")) return "edit";
      if (operation.includes("reference") || id.includes("reference")) return "reference";
      return "text";
    }
    if (operation.includes("motion") || id.includes("motion")) return "motion";
    if (operation.includes("video_edit") || operation.includes("video_upscale") || operation.includes("video_extend") || operation.includes("multimodal")) return "video";
    if (operation.includes("image_to_video") || operation.includes("reference_to_video") || operation.includes("text_or_image_to_video")) return "image";
    return "text";
  }

  function laneDefinitions(mediaType) {
    if (mediaType === "image") {
      return [
        ["all", "Все"],
        ["text", "Текст → фото"],
        ["edit", "Редактирование"],
        ["reference", "Референсы"],
      ];
    }
    return [
      ["all", "Все"],
      ["text", "Текст → видео"],
      ["image", "Фото → видео"],
      ["video", "Видео → видео"],
      ["motion", "Motion"],
    ];
  }

  function operationLabel(operation) {
    return {
      text_to_image: "Текст → изображение",
      image_edit: "Редактирование фото",
      generate_or_edit: "Генерация / edit",
      image_to_image: "Фото → фото",
      layer_decomposition: "Разбор на слои",
      text_to_video: "Текст → видео",
      image_to_video: "Фото → видео",
      video_edit: "Видео → видео",
      reference_to_video: "Референсы → видео",
      text_or_image_to_video: "Текст / фото → видео",
      multimodal_video: "Мультимодальное видео",
      motion_control: "Motion Control",
      video_upscale: "Апскейл видео",
      video_extend: "Продление видео",
    }[operation] || String(operation || "Генерация").replaceAll("_", " ");
  }

  function priceLabel(model) {
    const value = Number(model?.price_credits || 0);
    const formatted = Number.isFinite(value)
      ? value.toLocaleString("ru-RU", { maximumFractionDigits: 2 })
      : "—";
    return model?.price_mode === "per_second" ? `от ${formatted} ROX/сек` : `от ${formatted} ROX`;
  }

  function modelScenarioTitles(model) {
    const items = model?.ui_schema?.scenario?.items || [];
    return items.map((item) => String(item?.title || "").trim()).filter(Boolean).slice(0, 4);
  }

  function buildFormatCard({ type, icon, title, copy, disabled = false }) {
    const card = button("", () => {
      if (!disabled) void openMedia(type);
    }, `roxy-media-card roxy-flow-format-card${disabled ? " is-disabled" : ""}`);
    card.dataset.roxyMedia = type;
    if (disabled) {
      card.disabled = true;
      card.setAttribute("aria-disabled", "true");
    }
    card.append(
      el("span", "roxy-media-card-icon", icon),
      (() => {
        const copyNode = el("span", "roxy-media-card-copy");
        copyNode.append(el("strong", "", title), el("small", "", copy));
        return copyNode;
      })(),
      el("span", "roxy-media-card-count", disabled ? "Скоро" : `${mediaModels(type).length} моделей`),
    );
    return card;
  }

  function renderStart() {
    const center = ensureCenter();
    if (!center) return;
    state.mediaType = null;
    state.lane = "all";
    center.dataset.roxyGenerationFlow = "start";

    const heading = el("header", "roxy-create-center-heading roxy-flow-heading");
    heading.append(
      el("span", "section-kicker", "ROXY Create"),
      el("h1", "", "Что создаём?"),
      el("p", "", "Фото и видео — отдельные генерационные контуры. Сначала формат, затем модель, режим, входные данные и параметры."),
    );

    const grid = el("div", "roxy-media-grid roxy-flow-format-grid");
    grid.append(
      buildFormatCard({ type: "image", icon: "▧", title: "Фото", copy: "Text-to-Image, edit и референсы" }),
      buildFormatCard({ type: "video", icon: "▶", title: "Видео", copy: "Text/Image/Video-to-Video и Motion" }),
      buildFormatCard({ type: "audio", icon: "♪", title: "Музыка", copy: "Отдельный генерационный контур", disabled: true }),
    );

    const steps = el("div", "roxy-flow-steps");
    ["Формат", "Модель", "Режим", "Медиа", "Параметры", "Цена", "Запуск"].forEach((label, index) => {
      const item = el("span", "roxy-flow-step");
      item.append(el("b", "", index + 1), el("span", "", label));
      steps.appendChild(item);
    });

    const note = el("div", "roxy-create-center-note roxy-flow-note");
    note.append(
      el("strong", "", "Полный flow без возврата на главную"),
      el("span", "", "После выбора модели ROXY открывает её рабочий экран напрямую. Динамические поля, загрузки, проверка обязательных входов и стоимость остаются серверно-авторитетными."),
    );

    center.replaceChildren(heading, grid, steps, note);
  }

  function flowTitle(mediaType) {
    return mediaType === "video" ? "Видео" : "Фото";
  }

  function flowDescription(mediaType) {
    return mediaType === "video"
      ? "Выбери конкретную модель. На следующем шаге появятся только её режимы, референсы, длительность, разрешение и остальные поддерживаемые параметры."
      : "Выбери конкретную модель. На следующем шаге появятся только её режимы, референсы, качество, формат и остальные поддерживаемые параметры.";
  }

  function renderLaneTabs(mediaType, models) {
    const available = new Map();
    for (const model of models) available.set(operationLane(model), (available.get(operationLane(model)) || 0) + 1);
    const row = el("div", "roxy-flow-lanes");
    for (const [id, label] of laneDefinitions(mediaType)) {
      if (id !== "all" && !available.get(id)) continue;
      const count = id === "all" ? models.length : available.get(id);
      const tab = button(`${label} · ${count}`, () => {
        state.lane = id;
        renderMediaFlow(mediaType);
      }, `roxy-flow-lane${state.lane === id ? " is-active" : ""}`);
      tab.setAttribute("aria-pressed", String(state.lane === id));
      row.appendChild(tab);
    }
    return row;
  }

  function renderModelCard(model) {
    const card = button("", () => openModel(model), "roxy-flow-model-card");
    card.dataset.modelId = model.id;
    card.dataset.mediaType = model.media_type;
    const head = el("span", "roxy-flow-model-head");
    const icon = el("span", "roxy-flow-model-icon", model.media_type === "video" ? "▶" : "✦");
    const title = el("span", "roxy-flow-model-title");
    title.append(el("strong", "", model.title || model.id), el("small", "", model.family || "ROXY"));
    head.append(icon, title, el("span", "roxy-flow-model-price", priceLabel(model)));

    const operation = el("span", "roxy-flow-model-operation", operationLabel(model.operation));
    const scenarios = el("span", "roxy-flow-model-scenarios");
    const scenarioTitles = modelScenarioTitles(model);
    if (scenarioTitles.length) {
      scenarioTitles.forEach((titleText) => scenarios.appendChild(el("em", "", titleText)));
    } else {
      scenarios.appendChild(el("em", "", model.media_type === "video" ? "Динамические video-параметры" : "Динамические image-параметры"));
    }

    const footer = el("span", "roxy-flow-model-footer");
    footer.append(el("span", "", "Открыть настройки"), el("span", "roxy-flow-model-arrow", "→"));
    card.append(head, operation, scenarios, footer);
    return card;
  }

  function renderFlowLoading(mediaType) {
    const center = ensureCenter();
    if (!center) return;
    const heading = el("header", "roxy-flow-topbar");
    heading.append(button("←", renderStart, "roxy-flow-back"), el("div", "roxy-flow-topbar-copy", `Загружаю ${flowTitle(mediaType).toLowerCase()}…`));
    const skeletons = el("div", "roxy-flow-model-grid");
    for (let index = 0; index < 4; index += 1) skeletons.appendChild(el("div", "roxy-flow-model-skeleton"));
    center.replaceChildren(heading, skeletons);
  }

  function renderMediaFlow(mediaType) {
    const center = ensureCenter();
    if (!center) return;
    state.mediaType = mediaType;
    center.dataset.roxyGenerationFlow = mediaType;
    const allModels = mediaModels(mediaType);
    const filtered = state.lane === "all" ? allModels : allModels.filter((model) => operationLane(model) === state.lane);

    const top = el("header", "roxy-flow-topbar");
    const back = button("←", renderStart, "roxy-flow-back");
    back.setAttribute("aria-label", "Назад к выбору формата");
    const copy = el("div", "roxy-flow-topbar-copy");
    copy.append(el("span", "section-kicker", `ROXY · ${flowTitle(mediaType)}`), el("h1", "", flowTitle(mediaType)), el("p", "", flowDescription(mediaType)));
    top.append(back, copy);

    const lanes = renderLaneTabs(mediaType, allModels);
    const count = el("div", "roxy-flow-count", `${filtered.length} из ${allModels.length} моделей`);
    const grid = el("div", "roxy-flow-model-grid");
    if (filtered.length) filtered.forEach((model) => grid.appendChild(renderModelCard(model)));
    else grid.appendChild(el("div", "roxy-flow-empty", "Для этого режима сейчас нет доступных моделей."));

    const footer = el("div", "roxy-flow-footer-note");
    footer.append(
      el("strong", "", "Дальше — рабочий экран модели"),
      el("span", "", "ROXY покажет только поддерживаемые этой моделью поля: prompt, режим входа, файлы, длительность, качество/разрешение, дополнительные параметры, валидацию и актуальную цену."),
    );
    center.replaceChildren(top, lanes, count, grid, footer);
  }

  async function openMedia(mediaType) {
    if (mediaType !== "image" && mediaType !== "video") return;
    haptic("medium");
    state.mediaType = mediaType;
    state.lane = "all";
    renderFlowLoading(mediaType);
    try {
      await loadModels();
      renderMediaFlow(mediaType);
    } catch (error) {
      const center = ensureCenter();
      if (!center) return;
      const message = el("div", "roxy-flow-empty is-error");
      message.append(el("strong", "", "Не удалось загрузить модели"), el("span", "", error.message || "Попробуй ещё раз."));
      const retry = button("Повторить", () => void openMedia(mediaType), "roxy-flow-retry");
      center.append(message, retry);
    }
  }

  function selectExactModel(modelId, attempt = 0) {
    const select = document.getElementById("modelSelect");
    const builder = document.getElementById("builderView");
    const option = select ? [...select.options].find((item) => item.value === modelId) : null;
    if (select && builder && !builder.hidden && option) {
      if (select.value !== modelId) {
        select.value = modelId;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
      window.scrollTo({ top: 0, behavior: "auto" });
      return;
    }
    if (attempt < 80) window.setTimeout(() => selectExactModel(modelId, attempt + 1), 50);
  }

  function openModel(model) {
    if (!model?.id) return;
    haptic("medium");
    localStorage.setItem("ksu-selected-model", model.id);
    localStorage.setItem("ksu-generation-media-scope", model.media_type || state.mediaType || "");
    sessionStorage.setItem(RETURN_KEY, model.media_type || state.mediaType || "image");
    state.legacy?.close?.();

    if (window.KsuStudioShell?.open) {
      window.KsuStudioShell.open("create");
      selectExactModel(model.id, 0);
      return;
    }

    document.querySelector('.bottom-nav-item[data-shell-nav="create"]')?.click();
    const familyCard = [...document.querySelectorAll(".shell-family-card")]
      .find((card) => card.dataset.family === model.family);
    familyCard?.click();
    selectExactModel(model.id, 0);
  }

  function returnFromBuilder(mediaType) {
    if (mediaType !== "image" && mediaType !== "video") return;
    sessionStorage.removeItem(RETURN_KEY);
    state.legacy?.open?.();
    state.mediaType = mediaType;
    state.lane = "all";
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
    if (routeName && routeName !== "create") sessionStorage.removeItem(RETURN_KEY);
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
        sessionStorage.removeItem(RETURN_KEY);
        state.mediaType = null;
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
    if (installLegacyBridge()) {
      void loadModels().catch(() => null);
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
