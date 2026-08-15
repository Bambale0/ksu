(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const state = {
    open: false,
    sort: "recent",
    surface: "feed",
    authorCode: null,
    latestGeneration: null,
    loading: false,
  };
  const dom = {};

  function authHeaders(json = false) {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    if (json) headers["Content-Type"] = "application/json";
    return headers;
  }

  async function api(path, options = {}) {
    const hasBody = options.body !== undefined;
    const response = await fetch(path, {
      ...options,
      headers: { ...authHeaders(hasBody), ...(options.headers || {}) },
      credentials: "same-origin",
      cache: "no-store",
    });
    let payload = null;
    try { payload = await response.json(); } catch (_error) { payload = null; }
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

  function action(label, handler, className = "feed-action") {
    const button = el("button", className, label);
    button.type = "button";
    button.addEventListener("click", handler);
    return button;
  }

  function toast(message) {
    let node = document.getElementById("feedToast");
    if (!node) {
      node = el("div", "feed-toast");
      node.id = "feedToast";
      document.body.appendChild(node);
    }
    node.textContent = message;
    node.hidden = false;
    window.setTimeout(() => {
      if (node.textContent === message) node.hidden = true;
    }, 2800);
  }

  function haptic(kind = "light") {
    try { tg?.HapticFeedback?.impactOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function notify(kind = "success") {
    try { tg?.HapticFeedback?.notificationOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function mediaIsVideo(item) {
    const type = String(item?.media?.[0]?.content_type || "");
    if (type.startsWith("video/")) return true;
    return /\.(mp4|webm|mov)(\?|$)/i.test(String(item?.result_url || ""));
  }

  function mount() {
    if (document.getElementById("feedOverlay")) return;

    const launcher = action("🌐 Лента", openFeed, "feed-launch");
    launcher.id = "feedLaunch";
    document.body.appendChild(launcher);

    const overlay = el("section", "feed-overlay");
    overlay.id = "feedOverlay";
    overlay.hidden = true;
    overlay.setAttribute("aria-label", "Публичная лента Ксю");

    const shell = el("div", "feed-shell");
    const head = el("header", "feed-head");
    const copy = el("div", "feed-head-copy");
    const title = el("h1", "", "Лента");
    const subtitle = el("small", "", "Публичные работы сообщества");
    copy.append(title, subtitle);
    const close = action("✕", closeFeed, "feed-close");
    close.setAttribute("aria-label", "Закрыть ленту");
    head.append(copy, close);

    const tabs = el("div", "feed-tabs");
    const tabConfig = [
      ["recent", "🆕 Новые"],
      ["top_day", "🔥 Топ дня"],
      ["top", "⭐ Топ"],
    ];
    for (const [key, label] of tabConfig) {
      const button = action(label, () => {
        state.surface = "feed";
        state.authorCode = null;
        state.sort = key;
        syncTabs();
        void loadFeed();
      }, "feed-tab");
      button.dataset.feedSort = key;
      tabs.appendChild(button);
    }

    const body = el("div");
    body.id = "feedBody";
    shell.append(head, tabs, body);
    overlay.appendChild(shell);
    document.body.appendChild(overlay);

    Object.assign(dom, { launcher, overlay, title, subtitle, tabs, body });
    syncTabs();
    tg?.BackButton?.onClick?.(() => {
      if (state.open) closeFeed();
    });
  }

  function syncTabs() {
    dom.tabs?.querySelectorAll("[data-feed-sort]").forEach((button) => {
      button.classList.toggle(
        "is-active",
        state.surface === "feed" && button.dataset.feedSort === state.sort,
      );
    });
  }

  function openFeed() {
    state.open = true;
    state.surface = "feed";
    state.authorCode = null;
    dom.overlay.hidden = false;
    dom.title.textContent = "Лента";
    dom.subtitle.textContent = "Публичные работы сообщества";
    dom.tabs.hidden = false;
    syncTabs();
    try { tg?.BackButton?.show?.(); } catch (_error) { /* optional */ }
    document.body.style.overflow = "hidden";
    void loadFeed();
  }

  function closeFeed() {
    if (!state.open) return;
    state.open = false;
    dom.overlay.hidden = true;
    document.body.style.overflow = "";
    try { tg?.BackButton?.hide?.(); } catch (_error) { /* optional */ }
  }

  function loading(message = "Загружаю ленту…") {
    dom.body.replaceChildren(el("div", "feed-state", message));
  }

  function emptyState(message) {
    dom.body.replaceChildren(el("div", "feed-state", message));
  }

  async function loadFeed() {
    if (state.loading) return;
    state.loading = true;
    loading();
    try {
      const data = await api(`/api/v1/feed?sort=${encodeURIComponent(state.sort)}&limit=30`);
      renderList(data.items || [], "feed");
    } catch (error) {
      emptyState(error.message || "Не удалось загрузить ленту");
    } finally {
      state.loading = false;
    }
  }

  async function loadProfile(code) {
    state.surface = "profile";
    state.authorCode = String(code);
    dom.tabs.hidden = true;
    dom.title.textContent = "Работы автора";
    dom.subtitle.textContent = "Публикации профиля, включая profile-only";
    loading("Загружаю профиль…");
    try {
      const data = await api(`/api/v1/profiles/${encodeURIComponent(code)}/feed?limit=30`);
      const back = action("← Общая лента", () => {
        state.surface = "feed";
        state.authorCode = null;
        dom.title.textContent = "Лента";
        dom.subtitle.textContent = "Публичные работы сообщества";
        dom.tabs.hidden = false;
        syncTabs();
        void loadFeed();
      }, "feed-secondary feed-profile-back");
      const list = buildList(data.items || [], "profile");
      dom.body.replaceChildren(back, list);
    } catch (error) {
      emptyState(error.status === 404 ? "Профиль или публикации недоступны" : (error.message || "Ошибка профиля"));
    }
  }

  function renderList(items, surface) {
    if (!items.length) {
      emptyState(surface === "profile" ? "В профиле пока нет публикаций" : "В публичной ленте пока пусто");
      return;
    }
    dom.body.replaceChildren(buildList(items, surface));
  }

  function buildList(items, surface) {
    const list = el("div", "feed-list");
    for (const item of items) list.appendChild(buildCard(item, surface));
    return list;
  }

  function buildCard(item, surface) {
    const card = el("article", "feed-card");
    card.dataset.generationId = item.id;
    card.dataset.surface = surface;

    const mediaWrap = el("div", `feed-media-wrap${mediaIsVideo(item) ? " is-video" : ""}`);
    let media;
    if (mediaIsVideo(item)) {
      media = document.createElement("video");
      media.controls = true;
      media.playsInline = true;
      media.preload = "metadata";
    } else {
      media = document.createElement("img");
      media.alt = "Публичная AI-работа";
      media.loading = "lazy";
    }
    media.className = `feed-media${item.feed_blurred ? " feed-media-blurred" : ""}`;
    media.src = item.preview_url || item.result_url || "";
    mediaWrap.appendChild(media);
    if (item.feed_blurred) mediaWrap.appendChild(el("span", "feed-blur-label", "Контент скрыт блюром"));

    const body = el("div", "feed-body");
    const authorRow = el("div", "feed-author");
    const authorMain = el("div", "feed-author-main");
    authorMain.append(
      el("strong", "", item.author?.display_name || "Автор"),
      el("small", "", item.author?.username ? `@${item.author.username}` : `ref ${item.author_referral_code}`),
    );
    const authorButton = action("👤 Автор", () => loadProfile(item.author_referral_code), "feed-secondary");
    authorRow.append(authorMain, authorButton);
    body.appendChild(authorRow);

    if (item.prompt) body.appendChild(el("p", "feed-prompt", item.prompt));
    else if (item.prompt_hidden) body.appendChild(el("div", "feed-prompt-note", "Prompt скрыт автором или правилами remix"));

    body.appendChild(
      el(
        "div",
        "feed-meta",
        `${item.model || item.gen_type || "AI"} · ${item.publication_scope === "profile" ? "только профиль" : "публично"}`,
      ),
    );

    const actions = el("div", "feed-actions");
    const like = action(
      `${item.liked_by_me ? "♥" : "♡"} ${item.likes_count || 0}`,
      () => toggleLike(item, like, surface),
    );
    like.classList.toggle("is-liked", Boolean(item.liked_by_me));
    like.setAttribute("aria-pressed", String(Boolean(item.liked_by_me)));
    actions.append(
      like,
      action(`💬 ${item.comments_count || 0}`, () => toggleComments(item, card, surface)),
      action(`🔗 ${item.shares_count || 0}`, () => shareItem(item, surface)),
    );
    if (item.prompt_actions_allowed !== false) {
      actions.appendChild(action("🔁 Повторить", () => remixItem(item, surface)));
    }
    actions.append(
      action("👤 Профиль", () => loadProfile(item.author_referral_code)),
      action("↗ Пост", () => copyPostLink(item, surface)),
    );
    body.appendChild(actions);
    card.append(mediaWrap, body);
    return card;
  }

  async function toggleLike(item, button, surface) {
    if (button.disabled) return;
    button.disabled = true;
    haptic();
    try {
      const method = item.liked_by_me ? "DELETE" : "POST";
      const path = method === "DELETE"
        ? `/api/v1/feed/${encodeURIComponent(item.id)}/like?surface=${encodeURIComponent(surface)}`
        : `/api/v1/feed/${encodeURIComponent(item.id)}/like`;
      const options = method === "DELETE"
        ? { method }
        : { method, body: JSON.stringify({ surface }) };
      const result = await api(path, options);
      item.liked_by_me = result.liked_by_me;
      item.likes_count = result.likes_count;
      button.textContent = `${item.liked_by_me ? "♥" : "♡"} ${item.likes_count || 0}`;
      button.classList.toggle("is-liked", Boolean(item.liked_by_me));
      button.setAttribute("aria-pressed", String(Boolean(item.liked_by_me)));
    } catch (error) {
      notify("error");
      toast(error.message || "Лайк не сохранён");
    } finally {
      button.disabled = false;
    }
  }

  async function shareItem(item, surface) {
    haptic();
    try {
      const result = await api(`/api/v1/feed/${encodeURIComponent(item.id)}/share`, {
        method: "POST",
        body: JSON.stringify({ surface }),
      });
      item.shares_count = result.shares_count;
      if (result.link) await copyText(result.link);
      toast(result.link ? "Ссылка скопирована" : "Share учтён");
    } catch (error) {
      notify("error");
      toast(error.message || "Не удалось создать ссылку");
    }
  }

  async function copyPostLink(item, surface) {
    try {
      const data = await api(
        `/api/v1/feed/${encodeURIComponent(item.id)}/link?kind=post&surface=${encodeURIComponent(surface)}`,
      );
      if (!data.link) throw new Error("BOT_USERNAME не настроен");
      await copyText(data.link);
      toast("Deep link поста скопирован");
    } catch (error) {
      toast(error.message || "Ссылка недоступна");
    }
  }

  async function copyText(value) {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }
    tg?.showPopup?.({ title: "Ссылка", message: value, buttons: [{ type: "close" }] });
  }

  async function remixItem(item, surface) {
    haptic("medium");
    try {
      const result = await api(`/api/v1/feed/${encodeURIComponent(item.id)}/remix`, {
        method: "POST",
        body: JSON.stringify({ surface }),
      });
      notify("success");
      toast(`Remix запущен · ${String(result.id).slice(0, 8)}`);
      closeFeed();
      window.RoxyCustomerNavigation?.open?.("create") || document.querySelector('[data-shell-nav="create"]')?.click();
    } catch (error) {
      notify("error");
      toast(error.message || "Remix не запущен");
    }
  }

  async function toggleComments(item, card, surface) {
    let panel = card.querySelector(".feed-comments-panel");
    if (panel) {
      panel.remove();
      return;
    }
    panel = el("div", "feed-comments-panel");
    panel.appendChild(el("div", "feed-state", "Загружаю комментарии…"));
    card.querySelector(".feed-body")?.appendChild(panel);
    try {
      const data = await api(
        `/api/v1/feed/${encodeURIComponent(item.id)}/comments?surface=${encodeURIComponent(surface)}&limit=30`,
      );
      renderComments(panel, item, surface, data.items || []);
    } catch (error) {
      panel.replaceChildren(el("div", "feed-state", error.message || "Комментарии недоступны"));
    }
  }

  function renderComments(panel, item, surface, comments) {
    const list = el("div", "feed-comments");
    if (!comments.length) list.appendChild(el("div", "feed-prompt-note", "Комментариев пока нет"));
    for (const comment of comments) {
      const row = el("div", "feed-comment");
      row.append(
        el("strong", "", comment.author?.display_name || comment.author?.username || "Пользователь"),
        el("p", "", comment.text || ""),
      );
      list.appendChild(row);
    }
    const form = el("form", "feed-comment-form");
    const input = document.createElement("input");
    input.type = "text";
    input.maxLength = 300;
    input.placeholder = "Комментарий";
    input.autocomplete = "off";
    const submit = action("Отправить", () => {}, "feed-secondary");
    submit.type = "submit";
    form.append(input, submit);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const text = input.value.trim();
      if (!text || submit.disabled) return;
      submit.disabled = true;
      try {
        await api(`/api/v1/feed/${encodeURIComponent(item.id)}/comments`, {
          method: "POST",
          body: JSON.stringify({ surface, text }),
        });
        item.comments_count = Number(item.comments_count || 0) + 1;
        const data = await api(
          `/api/v1/feed/${encodeURIComponent(item.id)}/comments?surface=${encodeURIComponent(surface)}&limit=30`,
        );
        renderComments(panel, item, surface, data.items || []);
      } catch (error) {
        toast(error.message || "Комментарий не отправлен");
      } finally {
        submit.disabled = false;
      }
    });
    panel.replaceChildren(list, form);
  }

  async function publishGeneration(generationId, scope, button) {
    if (button.disabled) return;
    button.disabled = true;
    try {
      const result = await api(`/api/v1/feed/${encodeURIComponent(generationId)}/publish`, {
        method: "POST",
        body: JSON.stringify({
          publication_scope: scope,
          prompt_visible: false,
          references_visible: false,
        }),
      });
      notify("success");
      toast(
        result.downgraded_to_profile
          ? "Публикация ограничена профилем"
          : (scope === "feed" ? "Опубликовано в ленте" : "Добавлено в профиль"),
      );
    } catch (error) {
      notify("error");
      toast(error.message || "Публикация не выполнена");
    } finally {
      button.disabled = false;
    }
  }

  function decorateResult() {
    const generation = state.latestGeneration;
    const result = document.getElementById("resultCard");
    if (!generation?.id || generation.status !== "succeeded" || !result || result.hidden) return;
    const actions = result.querySelector(".ksu-result-actions");
    if (!actions || actions.querySelector(".feed-publish-controls")) return;
    const controls = el("div", "feed-publish-controls");
    const profile = action(
      "👤 В профиль",
      () => publishGeneration(generation.id, "profile", profile),
      "feed-publish-action",
    );
    const feed = action(
      "🌐 В ленту",
      () => publishGeneration(generation.id, "feed", feed),
      "feed-publish-action primary",
    );
    controls.append(profile, feed);
    actions.appendChild(controls);
  }

  function applyGenerationContext(generation) {
    state.latestGeneration = generation || null;
    requestAnimationFrame(decorateResult);
  }

  function hydrateGenerationContext() {
    const context = window.RoxyGenerationContext;
    if (!context) return false;
    applyGenerationContext(context.current || null);
    void context.refreshResult?.();
    return true;
  }

  function attachGenerationContext() {
    window.addEventListener("roxy:generation-context", (event) => {
      applyGenerationContext(event.detail?.generation || null);
    });
    window.addEventListener("roxy:generation-context-ready", hydrateGenerationContext);
    hydrateGenerationContext();
  }

  mount();
  attachGenerationContext();
})();
