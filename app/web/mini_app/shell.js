(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const ACTIVE_STATUSES = new Set(["queued", "retry", "submitting", "generating"]);
  const TOP_VIEWS = new Set(["create", "history", "wallet", "profile"]);
  const state = {
    topView: "create",
    nested: null,
    models: [],
    recent: [],
    me: null,
    detailTimer: null,
    shellReady: false,
  };

  const dom = {};

  function byId(id) {
    return document.getElementById(id);
  }

  function cacheDom() {
    dom.appShell = byId("appShell");
    dom.createHome = byId("createHome");
    dom.builderView = byId("builderView");
    dom.generationDetailView = byId("generationDetailView");
    dom.historyMount = byId("historyMount");
    dom.walletBalance = byId("walletBalance");
    dom.transactionList = byId("transactionList");
    dom.profileCard = byId("profileCard");
    dom.partnerPreview = byId("partnerPreview");
    dom.familyGrid = byId("shellFamilyGrid");
    dom.modelCount = byId("shellModelCount");
    dom.recent = byId("recentGenerations");
    dom.activeSection = byId("activeGenerationSection");
    dom.activeCard = byId("activeGenerationCard");
    dom.offline = byId("offlineBanner");
    dom.balanceValue = byId("balanceValue");
    dom.bottomNav = byId("bottomNav");
  }

  function apiHeaders() {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function apiGet(path) {
    const response = await fetch(path, {
      headers: apiHeaders(),
      credentials: "same-origin",
      cache: "no-store",
    });
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

  function haptic(kind = "light") {
    tg?.HapticFeedback?.impactOccurred?.(kind);
  }

  function notify(kind = "success") {
    tg?.HapticFeedback?.notificationOccurred?.(kind);
  }

  function formatNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value ?? "—");
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(number);
  }

  function formatDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function statusLabel(status) {
    return {
      queued: "В очереди",
      retry: "Повтор",
      submitting: "Запускается",
      generating: "Генерируется",
      succeeded: "Готово",
      failed: "Ошибка",
    }[status] || status || "—";
  }

  function statusClass(status) {
    if (ACTIVE_STATUSES.has(status)) return "active";
    if (status === "succeeded") return "success";
    if (status === "failed") return "failed";
    return "";
  }

  function safeText(value, fallback = "") {
    return value == null || value === "" ? fallback : String(value);
  }

  function clear(node) {
    node?.replaceChildren();
  }

  function setShellStableHeight() {
    const stable = Number(tg?.viewportStableHeight || 0);
    if (stable > 0) document.documentElement.style.setProperty("--stable-height", `${stable}px`);
  }

  function syncTelegramChrome() {
    try {
      tg?.ready?.();
      tg?.expand?.();
      tg?.setHeaderColor?.("bg_color");
      tg?.setBackgroundColor?.("bg_color");
      tg?.setBottomBarColor?.("bottom_bar_bg_color");
    } catch (_error) {
      // Old Telegram clients may not implement newer chrome methods.
    }
    setShellStableHeight();
    document.documentElement.dataset.theme = tg?.colorScheme || "system";
  }

  function syncOffline() {
    if (!dom.offline) return;
    dom.offline.hidden = navigator.onLine;
  }

  function updateBackButton() {
    if (!tg?.BackButton) return;
    if (state.nested) tg.BackButton.show();
    else tg.BackButton.hide();
  }

  function setHistoryState({ replace = false } = {}) {
    const payload = { ksuShell: true, topView: state.topView, nested: state.nested };
    if (replace) history.replaceState(payload, "");
    else history.pushState(payload, "");
  }

  function closeLegacyHistory() {
    const overlay = byId("ksuHistoryOverlay");
    if (!overlay || overlay.hidden) return;
    const close = overlay.querySelector(".ksu-history-close");
    close?.click();
  }

  function ensureHistoryMounted() {
    const overlay = byId("ksuHistoryOverlay");
    if (overlay && dom.historyMount && overlay.parentElement !== dom.historyMount) {
      dom.historyMount.appendChild(overlay);
    }
  }

  function openHistoryModule() {
    ensureHistoryMounted();
    const overlay = byId("ksuHistoryOverlay");
    if (!overlay) return;
    if (overlay.hidden) byId("ksuHistoryButton")?.click();
  }

  function activateTopView(view, { replaceHistory = true, focus = true } = {}) {
    if (!TOP_VIEWS.has(view)) return;
    stopDetailPolling();
    if (state.topView === "history" && view !== "history") closeLegacyHistory();
    state.topView = view;
    state.nested = null;

    document.querySelectorAll(".app-view[data-view]").forEach((section) => {
      const active = section.dataset.view === view;
      section.hidden = !active;
      section.classList.toggle("is-active", active);
    });
    document.querySelectorAll("[data-shell-nav]").forEach((button) => {
      if (!button.classList.contains("bottom-nav-item")) return;
      const active = button.dataset.shellNav === view;
      button.classList.toggle("is-active", active);
      if (active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });

    dom.createHome.hidden = false;
    dom.builderView.hidden = true;
    dom.generationDetailView.hidden = true;

    if (view === "history") openHistoryModule();
    if (view === "wallet") loadWallet();
    if (view === "profile") loadProfile();
    if (view === "create") refreshCreateHome();

    updateBackButton();
    if (replaceHistory) setHistoryState({ replace: true });
    if (focus) focusViewHeading(view);
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function focusViewHeading(view) {
    const section = document.querySelector(`.app-view[data-view="${view}"]`);
    const heading = section?.querySelector("h1, h2");
    if (!heading) return;
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }

  function openBuilder(modelId = null, { pushHistory = true } = {}) {
    state.topView = "create";
    state.nested = "builder";
    dom.createHome.hidden = true;
    dom.builderView.hidden = false;
    dom.generationDetailView.hidden = true;
    document.querySelector('[data-view="create"]').hidden = false;
    updateBackButton();
    if (pushHistory) setHistoryState();
    if (modelId) selectBuilderModel(modelId);
    window.scrollTo({ top: 0, behavior: "auto" });
    const heading = dom.builderView.querySelector("h1");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
  }

  function selectBuilderModel(modelId, attempt = 0) {
    const select = byId("modelSelect");
    if (!select) return;
    const hasOption = [...select.options].some((option) => option.value === modelId);
    if (!hasOption && attempt < 30) {
      setTimeout(() => selectBuilderModel(modelId, attempt + 1), 50);
      return;
    }
    if (!hasOption) return;
    select.value = modelId;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function closeNested({ useHistory = true } = {}) {
    stopDetailPolling();
    if (!state.nested) return;
    if (useHistory && history.state?.ksuShell && history.length > 1) {
      history.back();
      return;
    }
    state.nested = null;
    dom.createHome.hidden = false;
    dom.builderView.hidden = true;
    dom.generationDetailView.hidden = true;
    updateBackButton();
    setHistoryState({ replace: true });
    refreshCreateHome();
  }

  function restoreShellState(snapshot) {
    if (!snapshot?.ksuShell) {
      activateTopView("create", { replaceHistory: true });
      return;
    }
    const view = TOP_VIEWS.has(snapshot.topView) ? snapshot.topView : "create";
    activateTopView(view, { replaceHistory: false, focus: false });
    if (view === "create" && snapshot.nested === "builder") {
      openBuilder(null, { pushHistory: false });
    } else if (view === "create" && snapshot.nested?.startsWith?.("generation:")) {
      const id = snapshot.nested.slice("generation:".length);
      openGenerationById(id, { pushHistory: false });
    }
  }

  async function loadModelsForHome() {
    try {
      const payload = await apiGet("/api/v1/generations/models");
      state.models = Array.isArray(payload?.models) ? payload.models : [];
      renderFamilyGrid();
    } catch (error) {
      clear(dom.familyGrid);
      const block = document.createElement("div");
      block.className = "shell-error";
      block.textContent = navigator.onLine
        ? "Не удалось загрузить модели. Переключитесь на другой раздел и вернитесь ещё раз."
        : "Модели загрузятся после восстановления сети.";
      dom.familyGrid.appendChild(block);
      dom.modelCount.textContent = "Недоступно";
    }
  }

  function familyLabel(family) {
    const key = safeText(family).toLowerCase();
    if (key.includes("nano") || key.includes("banana") || key.includes("google")) return "Быстрые фото";
    if (key.includes("gpt") || key.includes("openai")) return "AI-изображения";
    if (key.includes("seed")) return "Seedream / Seedance";
    if (key.includes("wan")) return "Видео Wan";
    if (key.includes("kling")) return "Kling Motion";
    if (key.includes("grok")) return "Grok";
    return family || "Другие модели";
  }

  function familyIcon(family, models) {
    if (models.some((model) => model.media_type === "video")) return "▶";
    const key = safeText(family).toLowerCase();
    if (key.includes("gpt")) return "G";
    if (key.includes("nano") || key.includes("banana")) return "N";
    if (key.includes("seed")) return "S";
    if (key.includes("grok")) return "X";
    return "✦";
  }

  function renderFamilyGrid() {
    clear(dom.familyGrid);
    const groups = new Map();
    for (const model of state.models) {
      const family = safeText(model.family, "Другие");
      if (!groups.has(family)) groups.set(family, []);
      groups.get(family).push(model);
    }
    dom.modelCount.textContent = `${state.models.length} моделей`;
    if (!groups.size) {
      const empty = document.createElement("div");
      empty.className = "shell-empty";
      empty.textContent = "Доступных моделей пока нет.";
      dom.familyGrid.appendChild(empty);
      return;
    }

    for (const [family, models] of groups) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "shell-family-card";
      button.dataset.family = family;
      button.addEventListener("click", () => {
        haptic();
        openBuilder(models[0]?.id || null);
      });

      const icon = document.createElement("span");
      icon.className = "shell-family-icon";
      icon.textContent = familyIcon(family, models);
      const title = document.createElement("strong");
      title.textContent = familyLabel(family);
      const meta = document.createElement("small");
      const video = models.some((model) => model.media_type === "video");
      const image = models.some((model) => model.media_type === "image");
      const type = video && image ? "Фото и видео" : video ? "Видео" : "Изображения";
      meta.textContent = `${type} · ${models.length}`;
      button.append(icon, title, meta);
      dom.familyGrid.appendChild(button);
    }
  }

  async function loadMeForShell() {
    if (!tg?.initData) {
      state.me = null;
      return null;
    }
    try {
      state.me = await apiGet("/api/v1/me");
      const balance = formatNumber(state.me.balance_rox);
      if (dom.balanceValue) dom.balanceValue.textContent = `${balance} кр.`;
      if (dom.walletBalance) dom.walletBalance.textContent = `${balance} кр.`;
      return state.me;
    } catch (_error) {
      return null;
    }
  }

  async function loadRecent() {
    if (!tg?.initData) {
      renderRecentUnavailable();
      return;
    }
    try {
      const payload = await apiGet("/api/v1/generations?limit=6");
      state.recent = Array.isArray(payload?.items) ? payload.items : [];
      renderRecent();
    } catch (_error) {
      clear(dom.recent);
      const error = document.createElement("div");
      error.className = "shell-error";
      error.textContent = "Не удалось обновить последние генерации.";
      dom.recent.appendChild(error);
    }
  }

  function renderRecentUnavailable() {
    clear(dom.recent);
    const empty = document.createElement("div");
    empty.className = "shell-empty";
    empty.textContent = "История и баланс появятся, когда Mini App открыт через Telegram.";
    dom.recent.appendChild(empty);
    dom.activeSection.hidden = true;
  }

  function renderRecent() {
    clear(dom.recent);
    const active = state.recent.find((item) => ACTIVE_STATUSES.has(item.status));
    if (active) {
      dom.activeSection.hidden = false;
      clear(dom.activeCard);
      dom.activeCard.appendChild(generationRow(active, true));
    } else {
      dom.activeSection.hidden = true;
      clear(dom.activeCard);
    }

    const completed = state.recent.filter((item) => !ACTIVE_STATUSES.has(item.status)).slice(0, 4);
    if (!completed.length) {
      const empty = document.createElement("div");
      empty.className = "shell-empty";
      empty.textContent = "Здесь появятся ваши готовые и завершённые генерации.";
      dom.recent.appendChild(empty);
      return;
    }
    completed.forEach((item) => dom.recent.appendChild(generationRow(item, false)));
  }

  function generationRow(generation, active) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = active ? "active-generation-card" : "shell-generation-card";
    button.addEventListener("click", () => openGenerationById(generation.id));

    const thumb = document.createElement("span");
    thumb.className = "generation-thumb";
    const url = generation.result_url || generation.result_urls?.[0];
    if (url && generation.model?.media_type === "image") {
      const image = document.createElement("img");
      image.src = url;
      image.alt = "";
      image.loading = "lazy";
      thumb.appendChild(image);
    } else {
      thumb.textContent = generation.model?.media_type === "video" ? "▶" : "✦";
    }

    const copy = document.createElement("span");
    copy.className = "generation-copy";
    const title = document.createElement("strong");
    title.textContent = generation.model?.title || "Генерация";
    const meta = document.createElement("small");
    const date = formatDate(generation.created_at);
    meta.textContent = `${statusLabel(generation.status)}${date ? ` · ${date}` : ""}`;
    copy.append(title, meta);

    const dot = document.createElement("span");
    dot.className = `status-dot ${statusClass(generation.status)}`.trim();
    dot.setAttribute("aria-label", statusLabel(generation.status));
    button.append(thumb, copy, dot);
    return button;
  }

  async function openGenerationById(id, { pushHistory = true } = {}) {
    if (!id || !tg?.initData) return;
    state.topView = "create";
    state.nested = `generation:${id}`;
    dom.createHome.hidden = true;
    dom.builderView.hidden = true;
    dom.generationDetailView.hidden = false;
    clear(dom.generationDetailView);
    const loading = document.createElement("div");
    loading.className = "shell-skeleton tall";
    dom.generationDetailView.appendChild(loading);
    updateBackButton();
    if (pushHistory) setHistoryState();
    window.scrollTo({ top: 0, behavior: "auto" });

    try {
      const generation = await apiGet(`/api/v1/generations/${encodeURIComponent(id)}`);
      renderGenerationDetail(generation);
      if (ACTIVE_STATUSES.has(generation.status)) startDetailPolling(id);
    } catch (_error) {
      clear(dom.generationDetailView);
      const error = document.createElement("div");
      error.className = "shell-error";
      error.textContent = "Генерация недоступна или была скрыта.";
      dom.generationDetailView.appendChild(error);
    }
  }

  function renderGenerationDetail(generation) {
    clear(dom.generationDetailView);
    const card = document.createElement("article");
    card.className = "shell-detail-card";
    const urls = Array.isArray(generation.result_urls)
      ? generation.result_urls
      : generation.result_url
        ? [generation.result_url]
        : [];

    if (urls[0]) {
      const media = document.createElement("div");
      media.className = "shell-detail-media";
      if (generation.model?.media_type === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(urls[0])) {
        const video = document.createElement("video");
        video.src = urls[0];
        video.controls = true;
        video.playsInline = true;
        video.preload = "metadata";
        media.appendChild(video);
      } else {
        const image = document.createElement("img");
        image.src = urls[0];
        image.alt = "Результат генерации";
        media.appendChild(image);
      }
      card.appendChild(media);
    }

    const body = document.createElement("div");
    body.className = "shell-detail-body";
    const kicker = document.createElement("span");
    kicker.className = "section-kicker";
    kicker.textContent = statusLabel(generation.status);
    const title = document.createElement("h2");
    title.textContent = generation.model?.title || "Генерация";
    body.append(kicker, title);

    if (generation.prompt) {
      const prompt = document.createElement("p");
      prompt.textContent = generation.prompt;
      body.appendChild(prompt);
    }
    if (generation.error) {
      const error = document.createElement("p");
      error.style.color = "var(--danger)";
      error.textContent = generation.error;
      body.appendChild(error);
    }

    const actions = document.createElement("div");
    actions.className = "shell-detail-actions";
    const back = document.createElement("button");
    back.type = "button";
    back.className = "shell-action";
    back.textContent = "Назад";
    back.addEventListener("click", () => closeNested());
    actions.appendChild(back);

    if (urls[0]) {
      const open = document.createElement("a");
      open.className = "shell-action primary";
      open.href = urls[0];
      open.target = "_blank";
      open.rel = "noopener noreferrer";
      open.textContent = generation.result_storage === "owned" ? "Открыть результат" : "Открыть";
      actions.appendChild(open);
    }
    body.appendChild(actions);
    card.appendChild(body);
    dom.generationDetailView.appendChild(card);
    updateBackButton();
  }

  function startDetailPolling(id) {
    stopDetailPolling();
    const tick = async () => {
      if (state.nested !== `generation:${id}`) return;
      try {
        const generation = await apiGet(`/api/v1/generations/${encodeURIComponent(id)}`);
        renderGenerationDetail(generation);
        if (!ACTIVE_STATUSES.has(generation.status)) {
          stopDetailPolling();
          notify(generation.status === "succeeded" ? "success" : "error");
          refreshCreateHome();
          return;
        }
      } catch (_error) {
        // Keep the currently rendered state and retry while the nested view is open.
      }
      state.detailTimer = setTimeout(tick, 3000);
    };
    state.detailTimer = setTimeout(tick, 1800);
  }

  function stopDetailPolling() {
    clearTimeout(state.detailTimer);
    state.detailTimer = null;
  }

  async function refreshCreateHome() {
    await Promise.allSettled([loadMeForShell(), loadRecent()]);
  }

  async function loadWallet() {
    if (!dom.transactionList) return;
    if (!tg?.initData) {
      dom.walletBalance.textContent = "—";
      clear(dom.transactionList);
      const block = document.createElement("div");
      block.className = "shell-empty";
      block.textContent = "Баланс доступен при открытии Mini App через Telegram.";
      dom.transactionList.appendChild(block);
      return;
    }

    try {
      const [me, transactions] = await Promise.all([
        loadMeForShell(),
        apiGet("/api/v1/me/transactions"),
      ]);
      if (me) dom.walletBalance.textContent = `${formatNumber(me.balance_rox)} кр.`;
      renderTransactions(Array.isArray(transactions) ? transactions : []);
    } catch (_error) {
      clear(dom.transactionList);
      const block = document.createElement("div");
      block.className = "shell-error";
      block.textContent = "Не удалось загрузить операции.";
      dom.transactionList.appendChild(block);
    }
  }

  function transactionLabel(kind) {
    return {
      generation: "Генерация",
      generation_debit: "Генерация",
      generation_refund: "Возврат за генерацию",
      payment: "Пополнение",
      payment_credit: "Пополнение",
      promo: "Промокод",
      referral: "Партнёрское начисление",
      adjustment: "Корректировка",
    }[kind] || safeText(kind, "Операция").replaceAll("_", " ");
  }

  function renderTransactions(rows) {
    clear(dom.transactionList);
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "shell-empty";
      empty.textContent = "Операций пока нет.";
      dom.transactionList.appendChild(empty);
      return;
    }
    rows.slice(0, 20).forEach((tx) => {
      const row = document.createElement("div");
      row.className = "transaction-row";
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = transactionLabel(tx.kind);
      const date = document.createElement("small");
      date.textContent = formatDate(tx.created_at);
      copy.append(title, date);
      const amount = document.createElement("div");
      const numeric = Number(tx.amount);
      amount.className = `transaction-amount ${numeric >= 0 ? "positive" : "negative"}`;
      amount.textContent = `${numeric > 0 ? "+" : ""}${formatNumber(tx.amount)} кр.`;
      row.append(copy, amount);
      dom.transactionList.appendChild(row);
    });
  }

  async function loadProfile() {
    if (!tg?.initData) {
      renderProfile(null, null);
      return;
    }
    try {
      const [me, referrals] = await Promise.all([
        loadMeForShell(),
        apiGet("/api/v1/referrals/stats"),
      ]);
      renderProfile(me, referrals);
    } catch (_error) {
      renderProfile(state.me, null);
    }
  }

  function renderProfile(me, referrals) {
    clear(dom.profileCard);
    clear(dom.partnerPreview);
    if (!me) {
      const block = document.createElement("div");
      block.className = "shell-empty";
      block.textContent = "Профиль доступен при открытии Mini App через Telegram.";
      dom.profileCard.appendChild(block);
      const partner = document.createElement("div");
      partner.className = "shell-empty";
      partner.textContent = "Партнёрская статистика появится после авторизации.";
      dom.partnerPreview.appendChild(partner);
      return;
    }

    const head = document.createElement("div");
    head.className = "profile-head";
    const avatar = document.createElement("div");
    avatar.className = "profile-avatar";
    avatar.textContent = safeText(me.first_name, "К").slice(0, 1).toUpperCase();
    const copy = document.createElement("div");
    copy.className = "profile-copy";
    const name = document.createElement("strong");
    name.textContent = safeText(me.first_name, "Пользователь Ксю");
    const username = document.createElement("small");
    username.textContent = me.username ? `@${me.username}` : `Telegram ID ${me.telegram_id}`;
    copy.append(name, username);
    head.append(avatar, copy);

    const meta = document.createElement("div");
    meta.className = "profile-meta";
    meta.append(
      profileStat("Баланс", `${formatNumber(me.balance_rox)} кр.`),
      profileStat("Аккаунт", "Telegram"),
    );
    dom.profileCard.append(head, meta);

    if (!referrals) {
      const empty = document.createElement("div");
      empty.className = "shell-empty";
      empty.textContent = "Партнёрская статистика сейчас недоступна.";
      dom.partnerPreview.appendChild(empty);
      return;
    }
    const grid = document.createElement("div");
    grid.className = "partner-preview-grid";
    grid.append(
      profileStat("1 линия", `${formatNumber(referrals.first_line)} чел.`),
      profileStat("2 линия", `${formatNumber(referrals.second_line)} чел.`),
      profileStat("Доступно", `${formatNumber(referrals.available)} ₽`),
      profileStat("Ставки", `${formatNumber(referrals.first_line_percent)}% / ${formatNumber(referrals.second_line_percent)}%`),
    );
    dom.partnerPreview.appendChild(grid);
  }

  function profileStat(labelText, valueText) {
    const item = document.createElement("div");
    item.className = "profile-stat";
    const label = document.createElement("span");
    label.textContent = labelText;
    const value = document.createElement("strong");
    value.textContent = valueText;
    item.append(label, value);
    return item;
  }

  function bindNavigation() {
    document.addEventListener("click", (event) => {
      const target = event.target.closest("[data-shell-nav]");
      if (!target) return;
      const view = target.dataset.shellNav;
      if (!TOP_VIEWS.has(view)) return;
      event.preventDefault();
      haptic();
      activateTopView(view);
    });

    byId("brandHomeButton")?.addEventListener("click", () => activateTopView("create"));
    byId("builderHomeButton")?.addEventListener("click", () => closeNested());
    byId("builderHomeButton")?.addEventListener("click", haptic);

    tg?.BackButton?.onClick?.(() => closeNested());
    window.addEventListener("popstate", (event) => restoreShellState(event.state));
  }

  function bindTelegramEvents() {
    tg?.onEvent?.("themeChanged", syncTelegramChrome);
    tg?.onEvent?.("viewportChanged", setShellStableHeight);
    tg?.onEvent?.("safeAreaChanged", syncTelegramChrome);
    tg?.onEvent?.("contentSafeAreaChanged", syncTelegramChrome);
    tg?.onEvent?.("activated", () => {
      if (state.topView === "create" && !state.nested) refreshCreateHome();
      else if (state.topView === "wallet") loadWallet();
      else if (state.topView === "profile") loadProfile();
    });
    window.addEventListener("online", () => {
      syncOffline();
      if (state.topView === "create") refreshCreateHome();
    });
    window.addEventListener("offline", syncOffline);
  }

  function init() {
    document.body.classList.add("ksu-shell-mode");
    cacheDom();
    ensureHistoryMounted();
    syncTelegramChrome();
    syncOffline();
    bindNavigation();
    bindTelegramEvents();
    setHistoryState({ replace: true });
    loadModelsForHome();
    refreshCreateHome();
    state.shellReady = true;
  }

  init();
})();
