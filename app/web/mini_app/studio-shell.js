(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const MINI_ROOT = "/mini-app/";
  const PRIMARY_ROUTES = ["home", "feed", "create", "history", "profile"];
  const state = {
    route: "home",
    libraryTab: "references",
    mounted: false,
    feedObserver: null,
    resultObserver: null,
  };

  const dom = {};

  function byId(id) {
    return document.getElementById(id);
  }

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function action(label, handler, className = "studio-action") {
    const button = el("button", className, label);
    button.type = "button";
    button.addEventListener("click", handler);
    return button;
  }

  function haptic(kind = "light") {
    try {
      tg?.HapticFeedback?.impactOccurred?.(kind);
    } catch (_error) {
      // Optional Telegram client capability.
    }
  }

  function notify(kind = "success") {
    try {
      tg?.HapticFeedback?.notificationOccurred?.(kind);
    } catch (_error) {
      // Optional Telegram client capability.
    }
  }

  function authHeaders(json = false) {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    if (json) headers["Content-Type"] = "application/json";
    return headers;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        ...authHeaders(options.body !== undefined),
        ...(options.headers || {}),
      },
      credentials: "same-origin",
      cache: "no-store",
    });
    if (response.status === 204) return null;
    let payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }
    if (!response.ok) {
      const error = new Error(payload?.detail || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function nativeNav(view) {
    const candidates = [
      `.bottom-nav-item[data-shell-nav="${view}"]`,
      `[data-shell-nav="${view}"]`,
    ];
    for (const selector of candidates) {
      const node = document.querySelector(selector);
      if (node) {
        node.click();
        return true;
      }
    }
    return false;
  }

  function clearRouteClasses() {
    document.body.classList.remove(
      "studio-route-home",
      "studio-route-feed",
      "studio-route-create",
      "studio-route-history",
      "studio-route-wallet",
      "studio-route-profile",
      "studio-route-library",
    );
  }

  function syncRouteUi() {
    clearRouteClasses();
    document.body.classList.add(`studio-route-${state.route}`);
    document.querySelectorAll("[data-studio-route]").forEach((node) => {
      const active = node.dataset.studioRoute === state.route;
      node.classList.toggle("is-active", active);
      if (active) node.setAttribute("aria-current", "page");
      else node.removeAttribute("aria-current");
    });
    document.querySelectorAll("[data-studio-secondary]").forEach((node) => {
      const key = node.dataset.studioSecondary;
      const active = key === state.route || (
        state.route === "library" && key === state.libraryTab
      );
      node.classList.toggle("is-active", active);
    });
  }

  function closeFeed({ silent = true } = {}) {
    const overlay = byId("feedOverlay");
    if (!overlay || overlay.hidden) return;
    const close = overlay.querySelector(".feed-close");
    if (close) close.click();
    if (!silent && state.route === "feed") openHome();
  }

  function closeLibrary() {
    if (dom.libraryView) dom.libraryView.hidden = true;
  }

  function showNativeContent() {
    if (dom.feedView) dom.feedView.hidden = true;
    closeLibrary();
  }

  function openHome() {
    closeFeed();
    showNativeContent();
    nativeNav("create");
    byId("brandHomeButton")?.click();
    state.route = "home";
    syncRouteUi();
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  let selectedFamilyPromise = null;

  async function preferredFamily() {
    const modelId = localStorage.getItem("ksu-selected-model");
    if (!modelId) return null;
    if (!selectedFamilyPromise) {
      selectedFamilyPromise = api("/api/v1/generations/models")
        .then((payload) => {
          const models = Array.isArray(payload?.models) ? payload.models : [];
          return new Map(models.map((model) => [model.id, model.family]));
        })
        .catch(() => new Map());
    }
    const families = await selectedFamilyPromise;
    return families.get(modelId) || null;
  }

  async function enterBuilder(attempt = 0) {
    const builder = byId("builderView");
    if (builder && !builder.hidden) return;
    const cards = [...document.querySelectorAll(".shell-family-card")];
    if (cards.length) {
      const family = await preferredFamily();
      const card = family
        ? cards.find((item) => item.dataset.family === family) || cards[0]
        : cards[0];
      card.click();
      return;
    }
    if (attempt < 40) {
      window.setTimeout(() => {
        void enterBuilder(attempt + 1);
      }, 75);
    }
  }

  function openCreate() {
    closeFeed();
    showNativeContent();
    nativeNav("create");
    state.route = "create";
    syncRouteUi();
    void enterBuilder();
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function openNativeRoute(view) {
    closeFeed();
    showNativeContent();
    nativeNav(view);
    state.route = view;
    syncRouteUi();
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function ensureFeedEmbedded(attempt = 0) {
    const overlay = byId("feedOverlay");
    const launcher = byId("feedLaunch");
    if (!overlay || !launcher) {
      if (attempt < 60) {
        window.setTimeout(() => ensureFeedEmbedded(attempt + 1), 80);
      }
      return null;
    }

    if (overlay.parentElement !== dom.feedView) dom.feedView.appendChild(overlay);
    overlay.classList.add("studio-feed-overlay");
    launcher.hidden = true;

    if (!state.feedObserver) {
      state.feedObserver = new MutationObserver(() => {
        if (state.route === "feed" && overlay.hidden) openHome();
      });
      state.feedObserver.observe(overlay, { attributes: true, attributeFilter: ["hidden"] });
    }
    return { overlay, launcher };
  }

  function openFeed() {
    showNativeContent();
    const feed = ensureFeedEmbedded();
    if (!feed) {
      state.route = "feed";
      syncRouteUi();
      window.setTimeout(openFeed, 120);
      return;
    }
    state.route = "feed";
    dom.feedView.hidden = false;
    syncRouteUi();
    if (feed.overlay.hidden) feed.launcher.click();
    document.body.style.overflow = "";
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function route(name) {
    if (!PRIMARY_ROUTES.includes(name) && name !== "wallet") return;
    haptic();
    if (name === "home") openHome();
    else if (name === "feed") openFeed();
    else if (name === "create") openCreate();
    else if (name === "history" || name === "profile") openNativeRoute(name);
    else if (name === "wallet") openNativeRoute("wallet");
  }

  function icon(text) {
    const node = el("span", "studio-nav-icon", text);
    node.setAttribute("aria-hidden", "true");
    return node;
  }

  function navButton(routeName, label, glyph) {
    const button = action("", () => route(routeName), "studio-nav-item");
    button.dataset.studioRoute = routeName;
    button.append(icon(glyph), el("span", "", label));
    return button;
  }

  function externalLink(label, glyph, href, key) {
    const link = el("a", "studio-secondary-link");
    link.href = href;
    link.dataset.studioSecondary = key;
    link.append(icon(glyph), el("span", "", label));
    return link;
  }

  function secondaryButton(label, glyph, key, handler) {
    const button = action("", handler, "studio-secondary-link");
    button.dataset.studioSecondary = key;
    button.append(icon(glyph), el("span", "", label));
    return button;
  }

  function mountSidebar() {
    const shell = byId("appShell");
    if (!shell || byId("studioSidebar")) return;
    const aside = el("aside", "studio-sidebar");
    aside.id = "studioSidebar";
    aside.setAttribute("aria-label", "Навигация Ксю Studio");

    const brand = action("", openHome, "studio-sidebar-brand");
    brand.append(el("span", "studio-sidebar-mark", "К"));
    const brandCopy = el("span", "studio-sidebar-copy");
    brandCopy.append(el("strong", "", "Ксю"), el("small", "", "AI Studio"));
    brand.appendChild(brandCopy);

    const balance = action("", () => route("wallet"), "studio-sidebar-balance");
    balance.append(el("span", "", "Баланс"), el("strong", "studio-sidebar-balance-value", "—"));
    dom.sidebarBalance = balance.querySelector("strong");

    const primaryLabel = el("div", "studio-nav-label", "Основное");
    const primary = el("nav", "studio-sidebar-nav");
    primary.append(
      navButton("home", "Главная", "⌂"),
      navButton("feed", "Лента", "◎"),
      navButton("create", "Создать", "＋"),
      navButton("history", "История", "≡"),
      navButton("profile", "Профиль", "○"),
    );

    const secondaryLabel = el("div", "studio-nav-label", "Разделы");
    const secondary = el("nav", "studio-sidebar-nav studio-sidebar-secondary");
    secondary.append(
      secondaryButton("Пополнение", "₽", "wallet", () => route("wallet")),
      externalLink("Тренды", "↗", `${MINI_ROOT}trends.html`, "trends"),
      secondaryButton("Референсы", "◇", "references", () => openLibrary("references")),
      secondaryButton("Пресеты", "▣", "presets", () => openLibrary("presets")),
      externalLink("Batch", "▦", `${MINI_ROOT}batch.html`, "batch"),
      externalLink("Prompt Tools", "✦", `${MINI_ROOT}prompt-tools.html`, "prompt-tools"),
      secondaryButton("Партнёрка", "↔", "partner", () => openProfileAnchor("partner")),
      secondaryButton("Поддержка", "?", "support", () => openProfileAnchor("support")),
    );

    aside.append(brand, balance, primaryLabel, primary, secondaryLabel, secondary);
    shell.insertBefore(aside, shell.firstChild);
    dom.sidebar = aside;
  }

  function mountBottomNav() {
    if (byId("studioBottomNav")) return;
    const nav = el("nav", "studio-bottom-nav");
    nav.id = "studioBottomNav";
    nav.setAttribute("aria-label", "Основная навигация");
    nav.append(
      navButton("home", "Главная", "⌂"),
      navButton("feed", "Лента", "◎"),
      navButton("create", "Создать", "＋"),
      navButton("history", "История", "≡"),
      navButton("profile", "Профиль", "○"),
    );
    document.body.appendChild(nav);
    dom.bottomNav = nav;
  }

  function mountFeedView() {
    const main = byId("appMain");
    if (!main || byId("studioFeedView")) return;
    const section = el("section", "studio-standalone-view studio-feed-view");
    section.id = "studioFeedView";
    section.hidden = true;
    main.appendChild(section);
    dom.feedView = section;
    ensureFeedEmbedded();
  }

  function resultPlaceholder() {
    const stage = el("div", "studio-result-empty");
    stage.id = "studioResultEmpty";
    const glyph = el("div", "studio-result-glyph", "✦");
    const copy = el("div", "studio-result-copy");
    copy.append(
      el("span", "section-kicker", "Результат"),
      el("h2", "", "Здесь появится результат"),
      el("p", "", "Настройте модель слева и запустите генерацию. Результат останется в рабочей области, чтобы сразу продолжить работу."),
    );
    const actions = el("div", "studio-result-empty-actions");
    actions.append(
      action("Открыть историю", () => route("history"), "studio-action secondary"),
      action("Посмотреть ленту", () => route("feed"), "studio-action secondary"),
    );
    stage.append(glyph, copy, actions);
    return stage;
  }

  function mountResultWorkspace() {
    const layout = document.querySelector(".builder-layout");
    const main = document.querySelector(".builder-main-column");
    const side = document.querySelector(".builder-side-column");
    const summary = document.querySelector(".summary-card");
    const result = byId("resultCard");
    if (!layout || !main || !side || !summary || !result) return;
    if (layout.dataset.studioWorkspace === "true") return;
    layout.dataset.studioWorkspace = "true";
    main.classList.add("studio-controls-pane");
    side.classList.add("studio-result-pane");

    main.appendChild(summary);
    const placeholder = resultPlaceholder();
    side.append(placeholder, result);

    const syncResult = () => {
      placeholder.hidden = !result.hidden;
      side.classList.toggle("has-result", !result.hidden);
    };
    state.resultObserver = new MutationObserver(syncResult);
    state.resultObserver.observe(result, { attributes: true, attributeFilter: ["hidden"] });
    syncResult();
  }

  function mountHomeOrchestration() {
    const home = byId("createHome");
    const hero = home?.querySelector(".hero-card");
    if (!home || !hero || byId("studioHomeOrchestration")) return;

    const section = el("section", "studio-home-orchestration");
    section.id = "studioHomeOrchestration";
    const head = el("div", "studio-home-orchestration-head");
    head.append(
      el("div", "", ""),
      el("span", "section-kicker", "Быстрый старт"),
    );
    head.firstChild.append(
      el("h2", "", "С чего начнём?"),
      el("p", "", "Готовый сценарий или чистый генерационный workspace."),
    );

    const grid = el("div", "studio-home-actions");
    const trend = action("", () => {
      window.location.assign(`${MINI_ROOT}trends.html`);
    }, "studio-home-action featured");
    trend.append(el("span", "studio-home-action-icon", "↗"), el("strong", "", "По тренду"), el("small", "", "Готовый recipe и серверные настройки"));

    const scratch = action("", openCreate, "studio-home-action");
    scratch.append(el("span", "studio-home-action-icon", "＋"), el("strong", "", "С нуля"), el("small", "", "Модель, референсы, настройки и prompt"));

    const tools = action("", () => {
      window.location.assign(`${MINI_ROOT}prompt-tools.html`);
    }, "studio-home-action");
    tools.append(el("span", "studio-home-action-icon", "✦"), el("strong", "", "Prompt Tools"), el("small", "", "Анализ и улучшение промптов"));

    const references = action("", () => openLibrary("references"), "studio-home-action");
    references.append(el("span", "studio-home-action-icon", "◇"), el("strong", "", "Референсы"), el("small", "", "Повторно используемые медиа"));

    grid.append(trend, scratch, tools, references);
    section.append(head, grid);
    hero.insertAdjacentElement("afterend", section);
  }

  function openProfileAnchor(kind) {
    openNativeRoute("profile");
    const selectors = kind === "support"
      ? ["#supportComposeForm", "#profileTools"]
      : ["#partnerCabinet", "#partnerPreview"];
    let attempt = 0;
    const scroll = () => {
      for (const selector of selectors) {
        const node = document.querySelector(selector);
        if (node) {
          node.scrollIntoView({ behavior: "smooth", block: "start" });
          return;
        }
      }
      if (attempt++ < 30) window.setTimeout(scroll, 100);
    };
    scroll();
  }

  function libraryShell() {
    const section = el("section", "studio-standalone-view studio-library-view");
    section.id = "studioLibraryView";
    section.hidden = true;

    const head = el("header", "studio-library-head");
    const copy = el("div");
    copy.append(el("span", "section-kicker", "Библиотека"), el("h1", "", "Референсы и пресеты"));
    const close = action("Закрыть", openHome, "studio-action secondary");
    head.append(copy, close);

    const tabs = el("div", "studio-library-tabs");
    for (const [key, label] of [["references", "Референсы"], ["presets", "Пресеты"]]) {
      const button = action(label, () => {
        state.libraryTab = key;
        syncLibraryTab();
        void loadLibrary();
      }, "studio-library-tab");
      button.dataset.libraryTab = key;
      tabs.appendChild(button);
    }

    const body = el("div", "studio-library-body");
    body.id = "studioLibraryBody";
    body.setAttribute("aria-live", "polite");

    section.append(head, tabs, body);
    return section;
  }

  function mountLibrary() {
    const main = byId("appMain");
    if (!main || byId("studioLibraryView")) return;
    const section = libraryShell();
    main.appendChild(section);
    dom.libraryView = section;
    dom.libraryBody = byId("studioLibraryBody");
    dom.libraryTabs = section.querySelector(".studio-library-tabs");
  }

  function syncLibraryTab() {
    dom.libraryTabs?.querySelectorAll("[data-library-tab]").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.libraryTab === state.libraryTab);
    });
    syncRouteUi();
  }

  function openLibrary(tab = "references") {
    closeFeed();
    state.route = "library";
    state.libraryTab = tab;
    dom.feedView.hidden = true;
    dom.libraryView.hidden = false;
    syncLibraryTab();
    window.scrollTo({ top: 0, behavior: "auto" });
    void loadLibrary();
  }

  function libraryState(message, tone = "") {
    dom.libraryBody.replaceChildren(el("div", `studio-library-state${tone ? ` ${tone}` : ""}`, message));
  }

  async function loadLibrary() {
    if (!tg?.initData) {
      libraryState("Откройте Mini App через Telegram, чтобы работать с личной библиотекой.");
      return;
    }
    libraryState("Загружаю…");
    try {
      if (state.libraryTab === "references") {
        const payload = await api("/api/v1/references?limit=100");
        renderReferences(payload?.items || []);
      } else {
        const payload = await api("/api/v1/presets");
        renderPresets(payload?.items || []);
      }
    } catch (error) {
      libraryState(error.message || "Не удалось загрузить библиотеку.", "error");
    }
  }

  function referencePreview(item) {
    const wrap = el("div", "studio-reference-preview");
    if (item.kind === "image") {
      const img = document.createElement("img");
      img.src = item.url;
      img.alt = item.label || item.filename || "Референс";
      img.loading = "lazy";
      wrap.appendChild(img);
    } else if (item.kind === "video") {
      const video = document.createElement("video");
      video.src = item.url;
      video.muted = true;
      video.preload = "metadata";
      wrap.appendChild(video);
    } else {
      wrap.appendChild(el("span", "studio-reference-audio", "♪"));
    }
    return wrap;
  }

  function renderReferences(items) {
    const root = el("div", "studio-library-grid");
    const compose = el("form", "studio-library-compose");
    const title = el("div", "studio-library-section-title");
    title.append(el("h2", "", "Добавить референс"), el("p", "", "HTTPS-ссылка на изображение, видео или аудио."));

    const fields = el("div", "studio-library-form-grid");
    const kind = document.createElement("select");
    kind.className = "input";
    kind.name = "kind";
    kind.setAttribute("aria-label", "Тип референса");
    [["image", "Изображение"], ["video", "Видео"], ["audio", "Аудио"]].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      kind.appendChild(option);
    });

    const url = document.createElement("input");
    url.className = "input";
    url.type = "url";
    url.name = "url";
    url.required = true;
    url.placeholder = "https://…";
    url.setAttribute("aria-label", "HTTPS URL референса");

    const label = document.createElement("input");
    label.className = "input";
    label.type = "text";
    label.name = "label";
    label.maxLength = 120;
    label.placeholder = "Название (необязательно)";
    label.setAttribute("aria-label", "Название референса");

    const submit = action("Сохранить референс", () => {}, "studio-action primary");
    submit.type = "submit";
    const message = el("div", "studio-library-message");
    fields.append(kind, url, label);
    compose.append(title, fields, submit, message);
    compose.addEventListener("submit", async (event) => {
      event.preventDefault();
      submit.disabled = true;
      message.textContent = "Сохраняю…";
      try {
        await api("/api/v1/references", {
          method: "POST",
          body: JSON.stringify({
            source_url: url.value.trim(),
            kind: kind.value,
            label: label.value.trim(),
          }),
        });
        notify("success");
        url.value = "";
        label.value = "";
        message.textContent = "Сохранено.";
        await loadLibrary();
      } catch (error) {
        notify("error");
        message.textContent = error.message || "Не удалось сохранить.";
      } finally {
        submit.disabled = false;
      }
    });
    root.appendChild(compose);

    const listSection = el("section", "studio-library-list-section");
    const listHead = el("div", "studio-library-section-title");
    listHead.append(el("h2", "", `Мои референсы · ${items.length}`), el("p", "", "Owner-scoped библиотека, доступная только вашему аккаунту."));
    listSection.appendChild(listHead);

    const list = el("div", "studio-library-items");
    if (!items.length) {
      list.appendChild(el("div", "studio-library-state", "Референсов пока нет."));
    } else {
      for (const item of items) {
        const card = el("article", "studio-library-card reference");
        const media = referencePreview(item);
        const copy = el("div", "studio-library-card-copy");
        copy.append(
          el("strong", "", item.label || item.filename || "Без названия"),
          el("small", "", `${item.kind} · ${new Date(item.created_at).toLocaleDateString("ru-RU")}`),
        );
        const remove = action("Удалить", async () => {
          remove.disabled = true;
          try {
            await api(`/api/v1/references/${encodeURIComponent(item.id)}`, { method: "DELETE" });
            notify("success");
            await loadLibrary();
          } catch (error) {
            remove.disabled = false;
            libraryState(error.message || "Не удалось удалить референс.", "error");
          }
        }, "studio-action danger compact");
        card.append(media, copy, remove);
        list.appendChild(card);
      }
    }
    listSection.appendChild(list);
    root.appendChild(listSection);
    dom.libraryBody.replaceChildren(root);
  }

  function currentPresetSnapshot() {
    try {
      const modelId = localStorage.getItem("ksu-selected-model");
      const drafts = JSON.parse(localStorage.getItem("ksu-generation-drafts-v1") || "{}");
      const draft = modelId ? drafts?.[modelId] : null;
      if (!modelId || !draft || typeof draft !== "object") return null;
      const values = draft.values && typeof draft.values === "object" ? { ...draft.values } : {};
      const prompt = typeof values.prompt === "string" ? values.prompt : "";
      delete values.prompt;
      return {
        model_id: modelId,
        prompt,
        parameters: values,
        reference_ids: [],
        billing_seconds: Number.isFinite(Number(draft.billing_seconds)) && Number(draft.billing_seconds) > 0
          ? Number(draft.billing_seconds)
          : null,
      };
    } catch (_error) {
      return null;
    }
  }

  function applyPresetSnapshot(item) {
    if (!item?.model_id) throw new Error("В пресете отсутствует model_id");
    let drafts = {};
    try {
      drafts = JSON.parse(localStorage.getItem("ksu-generation-drafts-v1") || "{}");
    } catch (_error) {
      drafts = {};
    }
    const previous = drafts[item.model_id] && typeof drafts[item.model_id] === "object"
      ? drafts[item.model_id]
      : {};
    const previousValues = previous.values && typeof previous.values === "object"
      ? previous.values
      : {};
    const values = {
      ...previousValues,
      ...(item.parameters && typeof item.parameters === "object" ? item.parameters : {}),
    };
    if (typeof item.prompt === "string") values.prompt = item.prompt;
    const touched = { ...(previous.touched || {}) };
    Object.keys(values).forEach((key) => {
      touched[key] = true;
    });
    drafts[item.model_id] = {
      ...previous,
      values,
      touched,
      files: previous.files || {},
      billing_seconds: item.billing_seconds ?? previous.billing_seconds ?? null,
    };
    localStorage.setItem("ksu-generation-drafts-v1", JSON.stringify(drafts));
    localStorage.setItem("ksu-selected-model", item.model_id);
    sessionStorage.setItem("ksu-studio-open-builder", "1");
    window.location.reload();
  }

  function renderPresets(items) {
    const root = el("div", "studio-library-grid");
    const compose = el("form", "studio-library-compose");
    const title = el("div", "studio-library-section-title");
    title.append(
      el("h2", "", "Сохранить текущие настройки"),
      el("p", "", "Пресет сохраняет модель, prompt, параметры и длительность видео."),
    );
    const row = el("div", "studio-library-form-row");
    const name = document.createElement("input");
    name.className = "input";
    name.type = "text";
    name.required = true;
    name.maxLength = 80;
    name.placeholder = "Название пресета";
    name.setAttribute("aria-label", "Название пресета");
    const save = action("Сохранить", () => {}, "studio-action primary");
    save.type = "submit";
    const message = el("div", "studio-library-message");
    row.append(name, save);
    compose.append(title, row, message);
    compose.addEventListener("submit", async (event) => {
      event.preventDefault();
      const snapshot = currentPresetSnapshot();
      if (!snapshot) {
        message.textContent = "Сначала откройте Create и выберите модель.";
        return;
      }
      save.disabled = true;
      message.textContent = "Сохраняю…";
      try {
        await api("/api/v1/presets", {
          method: "POST",
          body: JSON.stringify({ ...snapshot, name: name.value.trim() }),
        });
        notify("success");
        name.value = "";
        message.textContent = "Пресет сохранён.";
        await loadLibrary();
      } catch (error) {
        notify("error");
        message.textContent = error.message || "Не удалось сохранить пресет.";
      } finally {
        save.disabled = false;
      }
    });
    root.appendChild(compose);

    const listSection = el("section", "studio-library-list-section");
    const listHead = el("div", "studio-library-section-title");
    listHead.append(el("h2", "", `Мои пресеты · ${items.length}`), el("p", "", "Применение возвращает вас в Create с серверно-валидируемой моделью."));
    listSection.appendChild(listHead);
    const list = el("div", "studio-library-items");

    if (!items.length) {
      list.appendChild(el("div", "studio-library-state", "Пресетов пока нет."));
    } else {
      for (const item of items) {
        const card = el("article", "studio-library-card preset");
        const copy = el("div", "studio-library-card-copy");
        const prompt = String(item.prompt || "").trim();
        copy.append(
          el("strong", "", item.name),
          el("small", "", item.model_id),
          el("p", "", prompt ? (prompt.length > 180 ? `${prompt.slice(0, 177)}…` : prompt) : "Без prompt"),
        );
        const actions = el("div", "studio-library-card-actions");
        const use = action("Использовать", () => {
          try {
            applyPresetSnapshot(item);
          } catch (error) {
            notify("error");
            libraryState(error.message || "Не удалось применить пресет.", "error");
          }
        }, "studio-action primary compact");
        const remove = action("Удалить", async () => {
          remove.disabled = true;
          try {
            await api(`/api/v1/presets/${encodeURIComponent(item.id)}`, { method: "DELETE" });
            notify("success");
            await loadLibrary();
          } catch (error) {
            remove.disabled = false;
            libraryState(error.message || "Не удалось удалить пресет.", "error");
          }
        }, "studio-action danger compact");
        actions.append(use, remove);
        card.append(copy, actions);
        list.appendChild(card);
      }
    }
    listSection.appendChild(list);
    root.appendChild(listSection);
    dom.libraryBody.replaceChildren(root);
  }

  function syncBalance() {
    const source = byId("balanceValue");
    if (!source || !dom.sidebarBalance) return;
    const update = () => {
      dom.sidebarBalance.textContent = source.textContent || "—";
    };
    const observer = new MutationObserver(update);
    observer.observe(source, { childList: true, characterData: true, subtree: true });
    update();
  }

  function observeBuilderRoute() {
    const builder = byId("builderView");
    const createHome = byId("createHome");
    if (!builder || !createHome) return;
    const observer = new MutationObserver(() => {
      if (state.route === "feed" || state.route === "library") return;
      if (!builder.hidden) state.route = "create";
      else if (!createHome.hidden && state.route === "create") state.route = "home";
      syncRouteUi();
    });
    observer.observe(builder, { attributes: true, attributeFilter: ["hidden"] });
    observer.observe(createHome, { attributes: true, attributeFilter: ["hidden"] });
  }

  function bindGlobalKeys() {
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (state.route === "library" || state.route === "feed") openHome();
    });
  }

  function init() {
    if (state.mounted) return;
    state.mounted = true;
    document.body.classList.add("studio-shell-ready");
    mountSidebar();
    mountBottomNav();
    mountFeedView();
    mountLibrary();
    mountHomeOrchestration();
    mountResultWorkspace();
    syncBalance();
    observeBuilderRoute();
    bindGlobalKeys();
    const resumeBuilder = sessionStorage.getItem("ksu-studio-open-builder") === "1";
    if (resumeBuilder) {
      sessionStorage.removeItem("ksu-studio-open-builder");
      state.route = "create";
      syncRouteUi();
      window.setTimeout(openCreate, 80);
    } else {
      state.route = "home";
      syncRouteUi();
    }

    window.KsuStudioShell = Object.freeze({
      open: route,
      openLibrary,
      get route() {
        return state.route;
      },
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();