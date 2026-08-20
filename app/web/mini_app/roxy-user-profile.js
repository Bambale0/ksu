(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const PAGE_SIZE = 24;
  const ACTIVE_TAB_STORAGE_KEY = "roxy.profile.activeTab";

  const state = {
    mounted: false,
    loadingIdentity: false,
    loadingWorks: false,
    loadingPublications: false,
    me: null,
    overview: null,
    works: [],
    worksCursor: null,
    worksHasMore: false,
    publications: [],
    publicationsOffset: 0,
    publicationsHasMore: false,
    activeTab: "works",
    preview: null,
    loadedOnce: false,
  };

  const dom = {};

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function icon(name, size = 20) {
    return window.RoxyIcons?.create?.(name, { size }) || null;
  }

  function iconButton(name, label, handler, className = "") {
    const button = el("button", className);
    button.type = "button";
    button.setAttribute("aria-label", label);
    const glyph = icon(name, 20);
    if (glyph) button.appendChild(glyph);
    button.addEventListener("click", handler);
    return button;
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
      credentials: "same-origin",
      cache: "no-store",
      headers: { ...authHeaders(options.body !== undefined), ...(options.headers || {}) },
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const error = new Error(payload?.detail || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function haptic(kind = "light") {
    try { tg?.HapticFeedback?.impactOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function notify(kind = "success") {
    try { tg?.HapticFeedback?.notificationOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function formatCompact(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number)) return "0";
    return new Intl.NumberFormat("ru-RU", {
      notation: number >= 1000 ? "compact" : "standard",
      maximumFractionDigits: 1,
    }).format(number);
  }

  function formatDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "short",
      year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
    }).format(date);
  }

  function displayName(user) {
    return [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.username || "Профиль ROXY";
  }

  function initials(user) {
    const value = `${user?.first_name?.[0] || ""}${user?.last_name?.[0] || ""}` || user?.username?.[0] || "R";
    return value.toUpperCase();
  }

  function telegramPhotoUrl() {
    const value = tg?.initDataUnsafe?.user?.photo_url;
    return typeof value === "string" && /^https:\/\//i.test(value) ? value : "";
  }

  function isVideo(item) {
    const mediaType = String(item?.model?.media_type || item?.gen_type || "").toLowerCase();
    if (mediaType === "video") return true;
    const url = String(item?.preview_url || item?.result_url || item?.result_urls?.[0] || "");
    return /\.(mp4|webm|mov)(\?|$)/i.test(url);
  }

  function isAudio(item) {
    const mediaType = String(item?.model?.media_type || item?.gen_type || "").toLowerCase();
    if (mediaType === "audio") return true;
    const url = String(item?.preview_url || item?.result_url || item?.result_urls?.[0] || "");
    return /\.(mp3|wav|m4a|aac|ogg)(\?|$)/i.test(url);
  }

  function mediaUrl(item) {
    return item?.preview_url || item?.result_url || item?.result_urls?.[0] || item?.media?.[0]?.url || "";
  }

  function modelLabel(item) {
    return item?.model?.title || item?.model || item?.gen_type || "AI работа";
  }

  function publicationTotals() {
    return state.publications.reduce(
      (total, item) => ({
        likes: total.likes + Number(item.likes_count || 0),
        shares: total.shares + Number(item.shares_count || 0),
      }),
      { likes: 0, shares: 0 },
    );
  }

  function workTotal() {
    const total = Number(state.overview?.generations?.total);
    if (Number.isFinite(total)) return total;
    return state.works.length + (state.worksHasMore ? 1 : 0);
  }

  function publicationCountLabel() {
    const count = state.publications.length;
    return state.publicationsHasMore ? `${formatCompact(count)}+` : formatCompact(count);
  }

  function renderAvatar(container, user) {
    container.replaceChildren();
    const photo = telegramPhotoUrl();
    if (photo) {
      const image = document.createElement("img");
      image.src = photo;
      image.alt = "";
      image.loading = "eager";
      image.referrerPolicy = "no-referrer";
      image.addEventListener("error", () => {
        container.replaceChildren(el("span", "", initials(user)));
      }, { once: true });
      container.appendChild(image);
      return;
    }
    container.appendChild(el("span", "", initials(user)));
  }

  function renderIdentity() {
    if (!state.me || !dom.identity) return;
    renderAvatar(dom.avatar, state.me);
    dom.name.textContent = displayName(state.me);
    dom.handle.textContent = state.me.username ? `@${state.me.username}` : `Telegram ID ${state.me.telegram_id}`;

    const discoverable = Boolean(state.me.preferences?.profile_discoverable);
    dom.visibility.textContent = discoverable ? "Публичный профиль" : "Личный профиль";
    dom.visibility.classList.toggle("is-public", discoverable);

    const totals = publicationTotals();
    dom.stats.replaceChildren(
      stat("Работы", formatCompact(workTotal())),
      stat("Публикации", publicationCountLabel()),
      stat("Лайки", formatCompact(totals.likes)),
      stat("ROX", formatCompact(state.me.balance_rox || 0)),
    );
  }

  function stat(label, value) {
    const item = el("div", "roxy-user-profile-stat");
    item.append(el("strong", "", value), el("span", "", label));
    return item;
  }

  function buildIdentity() {
    const card = el("section", "roxy-user-profile-hero");
    const top = el("div", "roxy-user-profile-top");
    const avatar = el("div", "roxy-user-profile-avatar");
    const copy = el("div", "roxy-user-profile-copy");
    const name = el("h2", "", "Профиль");
    const handle = el("div", "roxy-user-profile-handle", "");
    const visibility = el("span", "roxy-user-profile-visibility", "Личный профиль");
    copy.append(name, handle, visibility);

    const share = iconButton("share", "Поделиться профилем", () => void shareProfile(), "roxy-user-profile-share");
    top.append(avatar, copy, share);

    const stats = el("div", "roxy-user-profile-stats");
    card.append(top, stats);
    Object.assign(dom, { identity: card, avatar, name, handle, visibility, stats, share });
    return card;
  }

  function buildTabs() {
    const tabs = el("div", "roxy-user-profile-tabs");
    tabs.setAttribute("role", "tablist");
    const config = [
      ["works", "grid", "Работы"],
      ["publications", "feed", "Публикации"],
    ];
    for (const [key, iconName, label] of config) {
      const button = el("button", "roxy-user-profile-tab");
      button.type = "button";
      button.dataset.profileTab = key;
      button.setAttribute("role", "tab");
      const glyph = icon(iconName, 18);
      if (glyph) button.appendChild(glyph);
      button.appendChild(el("span", "", label));
      button.addEventListener("click", () => switchTab(key));
      tabs.appendChild(button);
    }
    dom.tabs = tabs;
    return tabs;
  }

  function buildWorksSection() {
    const section = el("section", "roxy-user-profile-works");
    const head = el("div", "roxy-user-profile-section-head");
    const copy = el("div");
    copy.append(el("span", "section-kicker", "Портфолио"), el("h2", "", "Мои работы"));
    const create = el("button", "text-button", "Создать");
    create.type = "button";
    create.addEventListener("click", () => {
      haptic();
      window.RoxyCustomerNavigation?.open?.("create") || document.querySelector('[data-shell-nav="create"]')?.click();
    });
    head.append(copy, create);

    const grid = el("div", "roxy-user-profile-grid");
    grid.id = "roxyUserProfileGrid";
    grid.setAttribute("aria-live", "polite");

    const loadMore = el("button", "quiet-button roxy-user-profile-more", "Показать ещё");
    loadMore.type = "button";
    loadMore.hidden = true;
    loadMore.addEventListener("click", () => void loadMoreActive());

    section.append(head, grid, loadMore);
    Object.assign(dom, { worksSection: section, sectionTitle: copy.querySelector("h2"), grid, loadMore });
    return section;
  }

  function mount() {
    if (state.mounted) return true;
    const profileView = document.getElementById("profileView");
    const profileCard = document.getElementById("profileCard");
    if (!profileView || !profileCard) return false;

    state.mounted = true;
    try {
      const stored = localStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
      if (stored === "publications" || stored === "works") state.activeTab = stored;
    } catch (_error) { /* storage optional */ }

    const root = el("div", "roxy-user-profile");
    root.id = "roxyUserProfile";
    root.append(buildIdentity(), buildTabs(), buildWorksSection());

    const accountHeading = el("div", "roxy-user-profile-account-heading");
    accountHeading.append(
      el("span", "section-kicker", "Аккаунт"),
      el("h2", "", "Настройки и возможности"),
    );
    root.appendChild(accountHeading);

    profileCard.insertAdjacentElement("beforebegin", root);
    // The legacy shell card only repeats Telegram name and balance. The richer
    // profile hero above owns identity now; account/cabinet modules remain below.
    profileCard.hidden = true;
    profileCard.setAttribute("aria-hidden", "true");

    const preview = buildPreview();
    document.body.appendChild(preview);

    dom.root = root;
    dom.profileView = profileView;
    dom.legacyCard = profileCard;
    syncTabs();
    return true;
  }

  function syncTabs() {
    dom.tabs?.querySelectorAll("[data-profile-tab]").forEach((button) => {
      const active = button.dataset.profileTab === state.activeTab;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", String(active));
      button.tabIndex = active ? 0 : -1;
    });
    if (dom.sectionTitle) {
      dom.sectionTitle.textContent = state.activeTab === "works" ? "Мои работы" : "Мои публикации";
    }
  }

  async function switchTab(tab) {
    if (tab !== "works" && tab !== "publications") return;
    if (state.activeTab === tab) return;
    state.activeTab = tab;
    try { localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, tab); } catch (_error) { /* optional */ }
    haptic();
    syncTabs();
    renderActiveGrid();
    if (tab === "works" && !state.works.length && !state.loadingWorks) await loadWorks(true);
    if (tab === "publications" && !state.publications.length && !state.loadingPublications) await loadPublications(true);
  }

  function skeletonGrid() {
    dom.grid.replaceChildren();
    for (let index = 0; index < 9; index += 1) {
      dom.grid.appendChild(el("div", "roxy-user-profile-tile roxy-user-profile-skeleton"));
    }
    dom.loadMore.hidden = true;
  }

  function emptyGrid(title, note, withCreate = false) {
    const empty = el("div", "roxy-user-profile-empty");
    const glyph = el("div", "roxy-user-profile-empty-icon");
    const mediaIcon = icon("image", 28);
    if (mediaIcon) glyph.appendChild(mediaIcon);
    empty.append(glyph, el("strong", "", title), el("p", "", note));
    if (withCreate) {
      const action = el("button", "primary-button", "Создать первую работу");
      action.type = "button";
      action.addEventListener("click", () => window.RoxyCustomerNavigation?.open?.("create"));
      empty.appendChild(action);
    }
    dom.grid.replaceChildren(empty);
    dom.loadMore.hidden = true;
  }

  function renderActiveGrid() {
    if (!dom.grid) return;
    const items = state.activeTab === "works" ? state.works : state.publications;
    const loading = state.activeTab === "works" ? state.loadingWorks : state.loadingPublications;
    if (loading && !items.length) {
      skeletonGrid();
      return;
    }
    if (!items.length) {
      emptyGrid(
        state.activeTab === "works" ? "Работ пока нет" : "Публикаций пока нет",
        state.activeTab === "works"
          ? "Готовые изображения, видео и музыка появятся здесь автоматически."
          : "Опубликованные в профиль работы появятся здесь. Приватные генерации остаются только у вас.",
        state.activeTab === "works",
      );
      return;
    }
    dom.grid.replaceChildren(...items.map((item) => buildTile(item, state.activeTab)));
    const hasMore = state.activeTab === "works" ? state.worksHasMore : state.publicationsHasMore;
    dom.loadMore.hidden = !hasMore;
    dom.loadMore.disabled = loading;
    dom.loadMore.textContent = loading ? "Загрузка…" : "Показать ещё";
  }

  function buildTile(item, surface) {
    const button = el("button", "roxy-user-profile-tile");
    button.type = "button";
    button.dataset.generationId = item.id;
    button.dataset.profileSurface = surface;
    button.setAttribute("aria-label", `${modelLabel(item)} · ${formatDate(item.created_at)}`);

    const url = mediaUrl(item);
    if (url && isVideo(item)) {
      const video = document.createElement("video");
      video.src = url;
      video.muted = true;
      video.playsInline = true;
      video.preload = "metadata";
      video.tabIndex = -1;
      button.appendChild(video);
      const play = el("span", "roxy-user-profile-play");
      const playIcon = icon("create", 17) || icon("video", 17);
      if (playIcon) play.appendChild(playIcon);
      button.appendChild(play);
    } else if (url && !isAudio(item)) {
      const image = document.createElement("img");
      image.src = url;
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";
      image.addEventListener("error", () => button.classList.add("is-media-error"), { once: true });
      button.appendChild(image);
    } else {
      const placeholder = el("span", "roxy-user-profile-placeholder");
      const mediaIcon = icon(isAudio(item) ? "music" : "image", 26);
      if (mediaIcon) placeholder.appendChild(mediaIcon);
      placeholder.appendChild(el("small", "", isAudio(item) ? "Музыка" : "Результат"));
      button.appendChild(placeholder);
    }

    const overlay = el("span", "roxy-user-profile-tile-overlay");
    overlay.appendChild(el("span", "", modelLabel(item)));
    if (surface === "publications") {
      const reactions = el("span", "roxy-user-profile-reactions");
      const heart = icon("like", 13);
      if (heart) reactions.appendChild(heart);
      reactions.appendChild(el("span", "", formatCompact(item.likes_count || 0)));
      overlay.appendChild(reactions);
    }
    button.appendChild(overlay);
    button.addEventListener("click", () => void openPreview(item, surface));
    return button;
  }

  async function loadIdentity() {
    if (state.loadingIdentity || !tg?.initData) return;
    state.loadingIdentity = true;
    try {
      const [me, overview] = await Promise.all([
        api("/api/v1/me"),
        api("/api/v1/me/overview").catch(() => null),
      ]);
      state.me = me;
      state.overview = overview;
      renderIdentity();
    } catch (_error) {
      if (dom.identity) {
        dom.name.textContent = "Профиль ROXY";
        dom.handle.textContent = "Откройте Mini App через Telegram";
      }
    } finally {
      state.loadingIdentity = false;
    }
  }

  async function loadWorks(reset = false) {
    if (state.loadingWorks || !tg?.initData) return;
    state.loadingWorks = true;
    if (reset) {
      state.works = [];
      state.worksCursor = null;
      state.worksHasMore = false;
    }
    if (state.activeTab === "works") renderActiveGrid();
    try {
      const cursor = state.worksCursor ? `&before=${encodeURIComponent(state.worksCursor)}` : "";
      const payload = await api(`/api/v1/generations?limit=${PAGE_SIZE}&status=succeeded${cursor}`);
      const next = Array.isArray(payload?.items)
        ? payload.items.filter((item) => Boolean(mediaUrl(item)) || isAudio(item))
        : [];
      const seen = new Set(state.works.map((item) => String(item.id)));
      state.works.push(...next.filter((item) => !seen.has(String(item.id))));
      state.worksHasMore = Boolean(payload?.has_more);
      state.worksCursor = payload?.next_before || null;
    } catch (_error) {
      if (!state.works.length && state.activeTab === "works") {
        emptyGrid("Не удалось загрузить работы", "Проверьте соединение и откройте профиль ещё раз.");
      }
    } finally {
      state.loadingWorks = false;
      if (state.activeTab === "works") renderActiveGrid();
      renderIdentity();
    }
  }

  async function loadPublications(reset = false) {
    if (state.loadingPublications || !tg?.initData) return;
    state.loadingPublications = true;
    if (reset) {
      state.publications = [];
      state.publicationsOffset = 0;
      state.publicationsHasMore = false;
    }
    if (state.activeTab === "publications") renderActiveGrid();
    try {
      if (!state.me) await loadIdentity();
      if (!state.me?.telegram_id) throw new Error("Profile code unavailable");
      const payload = await api(
        `/api/v1/profiles/${encodeURIComponent(state.me.telegram_id)}/feed?limit=${PAGE_SIZE}&offset=${state.publicationsOffset}`,
      );
      const next = Array.isArray(payload?.items) ? payload.items : [];
      const seen = new Set(state.publications.map((item) => String(item.id)));
      state.publications.push(...next.filter((item) => !seen.has(String(item.id))));
      state.publicationsOffset += next.length;
      state.publicationsHasMore = next.length === PAGE_SIZE;
    } catch (_error) {
      if (!state.publications.length && state.activeTab === "publications") {
        emptyGrid("Публикации недоступны", "Публичная витрина загрузится, когда профиль и публикации будут доступны.");
      }
    } finally {
      state.loadingPublications = false;
      if (state.activeTab === "publications") renderActiveGrid();
      renderIdentity();
    }
  }

  async function loadMoreActive() {
    if (state.activeTab === "works") await loadWorks(false);
    else await loadPublications(false);
  }

  async function refresh({ force = false } = {}) {
    if (!mount()) return;
    if (!tg?.initData) {
      dom.grid.replaceChildren(el("div", "roxy-user-profile-empty", "Профиль доступен при открытии Mini App через Telegram."));
      return;
    }
    if (state.loadedOnce && !force) return;
    state.loadedOnce = true;
    await loadIdentity();
    await Promise.allSettled([loadWorks(true), loadPublications(true)]);
    renderActiveGrid();
    renderIdentity();
  }

  async function shareProfile() {
    if (!state.me?.telegram_id) return;
    haptic();
    try {
      const payload = await api(`/api/v1/profiles/${encodeURIComponent(state.me.telegram_id)}/link`);
      if (!payload?.link) throw new Error("Ссылка пока недоступна");
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(payload.link);
      else tg?.showPopup?.({ title: "Профиль", message: payload.link, buttons: [{ type: "close" }] });
      notify("success");
      toast("Ссылка на профиль скопирована");
    } catch (error) {
      notify("error");
      toast(error.message || "Не удалось получить ссылку на профиль");
    }
  }

  function toast(message) {
    let node = document.getElementById("roxyUserProfileToast");
    if (!node) {
      node = el("div", "feed-toast roxy-user-profile-toast");
      node.id = "roxyUserProfileToast";
      document.body.appendChild(node);
    }
    node.textContent = message;
    node.hidden = false;
    window.setTimeout(() => {
      if (node.textContent === message) node.hidden = true;
    }, 2600);
  }

  function buildPreview() {
    const overlay = el("section", "roxy-user-work-preview");
    overlay.id = "roxyUserWorkPreview";
    overlay.hidden = true;
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "Просмотр работы");

    const backdrop = el("button", "roxy-user-work-preview-backdrop");
    backdrop.type = "button";
    backdrop.setAttribute("aria-label", "Закрыть просмотр");
    backdrop.addEventListener("click", closePreview);

    const panel = el("div", "roxy-user-work-preview-panel");
    const close = iconButton("close", "Закрыть", closePreview, "roxy-user-work-preview-close");
    const content = el("div", "roxy-user-work-preview-content");
    panel.append(close, content);
    overlay.append(backdrop, panel);
    Object.assign(dom, { preview: overlay, previewPanel: panel, previewContent: content, previewClose: close });
    return overlay;
  }

  async function openPreview(item, surface) {
    if (!item?.id) return;
    haptic();
    state.preview = { item, surface };
    dom.preview.hidden = false;
    document.body.classList.add("roxy-profile-preview-open");
    dom.previewContent.replaceChildren(el("div", "shell-skeleton tall"));
    try { tg?.BackButton?.show?.(); } catch (_error) { /* optional */ }

    try {
      const detail = surface === "works"
        ? await api(`/api/v1/generations/${encodeURIComponent(item.id)}`)
        : await api(`/api/v1/feed/${encodeURIComponent(item.id)}?surface=profile`);
      if (!state.preview || String(state.preview.item.id) !== String(item.id)) return;
      renderPreview(detail, surface);
    } catch (error) {
      dom.previewContent.replaceChildren(
        el("div", "roxy-user-profile-empty", error.message || "Не удалось открыть работу"),
      );
    }
  }

  function renderPreview(item, surface) {
    dom.previewContent.replaceChildren();
    const media = el("div", "roxy-user-work-preview-media");
    const url = mediaUrl(item);
    if (url && isVideo(item)) {
      const video = document.createElement("video");
      video.src = url;
      video.controls = true;
      video.playsInline = true;
      video.preload = "metadata";
      media.appendChild(video);
    } else if (url && isAudio(item)) {
      const audioWrap = el("div", "roxy-user-work-audio");
      const glyph = icon("music", 34);
      if (glyph) audioWrap.appendChild(glyph);
      const audio = document.createElement("audio");
      audio.src = url;
      audio.controls = true;
      audio.preload = "metadata";
      audioWrap.appendChild(audio);
      media.appendChild(audioWrap);
    } else if (url) {
      const image = document.createElement("img");
      image.src = url;
      image.alt = "Результат генерации";
      media.appendChild(image);
    } else {
      media.appendChild(el("div", "roxy-user-profile-placeholder", "Результат недоступен"));
    }

    const body = el("div", "roxy-user-work-preview-body");
    body.append(
      el("span", "section-kicker", surface === "works" ? "Моя работа" : "Публикация"),
      el("h2", "", modelLabel(item)),
    );
    const meta = el("div", "roxy-user-work-preview-meta");
    if (item.created_at) meta.appendChild(el("span", "", formatDate(item.created_at)));
    if (surface === "publications") {
      meta.append(
        reaction("like", item.likes_count || 0),
        reaction("comment", item.comments_count || 0),
        reaction("share", item.shares_count || 0),
      );
    }
    body.appendChild(meta);

    // Prompts are intentionally never exposed from the public/profile publication
    // surface. The owner may see the prompt only while viewing their private work.
    if (surface === "works" && item.prompt && !item.prompt_hidden) {
      const prompt = el("p", "roxy-user-work-preview-prompt", item.prompt);
      body.appendChild(prompt);
    }

    const actions = el("div", "roxy-user-work-preview-actions");
    if (url) {
      const open = el("a", "shell-action primary", "Открыть результат");
      open.href = url;
      open.target = "_blank";
      open.rel = "noopener noreferrer";
      actions.appendChild(open);
    }
    if (surface === "publications") {
      const share = el("button", "shell-action", "Поделиться");
      share.type = "button";
      share.addEventListener("click", () => void sharePublication(item));
      actions.appendChild(share);
    }
    body.appendChild(actions);
    dom.previewContent.append(media, body);
    window.setTimeout(() => dom.previewClose?.focus?.(), 0);
  }

  function reaction(iconName, count) {
    const node = el("span", "roxy-user-work-reaction");
    const glyph = icon(iconName, 15);
    if (glyph) node.appendChild(glyph);
    node.appendChild(el("span", "", formatCompact(count)));
    return node;
  }

  async function sharePublication(item) {
    if (!item?.id) return;
    try {
      const payload = await api(`/api/v1/feed/${encodeURIComponent(item.id)}/share`, {
        method: "POST",
        body: JSON.stringify({ surface: "profile" }),
      });
      if (payload?.link) {
        if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(payload.link);
        else tg?.showPopup?.({ title: "Публикация", message: payload.link, buttons: [{ type: "close" }] });
      }
      notify("success");
      toast(payload?.link ? "Ссылка скопирована" : "Публикацией поделились");
      const current = state.publications.find((entry) => String(entry.id) === String(item.id));
      if (current && payload?.shares_count != null) current.shares_count = payload.shares_count;
      renderIdentity();
    } catch (error) {
      notify("error");
      toast(error.message || "Не удалось поделиться");
    }
  }

  function closePreview() {
    if (!dom.preview || dom.preview.hidden) return;
    state.preview = null;
    dom.preview.hidden = true;
    document.body.classList.remove("roxy-profile-preview-open");
    try { tg?.BackButton?.hide?.(); } catch (_error) { /* canonical mobile runtime will resync */ }
  }

  function profileVisible() {
    return Boolean(dom.profileView && !dom.profileView.hidden);
  }

  function handleRouteChange() {
    window.setTimeout(() => {
      if (profileVisible()) void refresh({ force: false });
    }, 0);
  }

  function init() {
    if (!mount()) {
      window.setTimeout(init, 80);
      return;
    }
    if (profileVisible()) void refresh({ force: false });
    window.addEventListener("roxy:route-changed", handleRouteChange);
    window.addEventListener("roxy:shell-route-changed", handleRouteChange);
    window.addEventListener("roxy:feed-changed", () => {
      state.loadedOnce = false;
      if (profileVisible()) void refresh({ force: true });
    });
    tg?.onEvent?.("activated", () => {
      if (profileVisible()) void refresh({ force: true });
    });
    document.addEventListener("click", (event) => {
      const target = event.target.closest?.('[data-roxy-customer-route="profile"], [data-shell-nav="profile"]');
      if (target) handleRouteChange();
    }, true);
    tg?.BackButton?.onClick?.(() => {
      if (!dom.preview?.hidden) closePreview();
    });

    window.RoxyUserProfile = Object.freeze({
      refresh: () => refresh({ force: true }),
      openWork: (id) => {
        const item = state.works.find((entry) => String(entry.id) === String(id));
        if (item) void openPreview(item, "works");
      },
      get me() { return state.me; },
      get works() { return [...state.works]; },
      get publications() { return [...state.publications]; },
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
