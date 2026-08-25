(() => {
  if (window.__roxySocialFeedPolish) return;
  window.__roxySocialFeedPolish = true;

  const FEED_PAGE_SIZE = 12;
  const state = {
    mode: "feed",
    source: "recent",
    profile: null,
    profileAuthor: null,
    items: [],
    loading: false,
    loadingMore: false,
    hasMore: false,
    error: "",
    busyId: null,
    subscribed: new Set(),
    subscriptions: [],
    commentsItem: null,
    comments: [],
    commentsLoading: false,
    booted: false,
    rendering: false,
  };

  const money = new Intl.NumberFormat("ru-RU", { notation: "compact", maximumFractionDigits: 1 });
  const sources = [["recent", "Новые"], ["top_day", "Топ дня"], ["top", "Лучшие"]];

  function tg() { return window.Telegram?.WebApp || null; }
  function haptic(kind = "light") { try { tg()?.HapticFeedback?.impactOccurred?.(kind); } catch {} }
  function notify(type = "success") { try { tg()?.HapticFeedback?.notificationOccurred?.(type); } catch {} }

  function headers(json = false) {
    const result = { Accept: "application/json" };
    const initData = tg()?.initData;
    if (initData) result["X-Telegram-Init-Data"] = initData;
    if (json) result["Content-Type"] = "application/json";
    return result;
  }

  async function request(path, init = {}) {
    const response = await fetch(path, {
      ...init,
      credentials: "same-origin",
      cache: "no-store",
      headers: { ...headers(Boolean(init.body)), ...(init.headers || {}) },
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload?.detail || payload?.message || `HTTP ${response.status}`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return payload;
  }

  function route() {
    try { return new URL(window.location.href).searchParams.get("route") || "home"; }
    catch { return "home"; }
  }

  function isFeedRoute() { return route() === "catalog"; }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function compact(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? money.format(number) : "0";
  }

  function dateLabel(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(date);
  }

  function mediaUrl(item) {
    return item?.preview_url || item?.result_url || item?.result_urls?.[0] || item?.media?.[0]?.url || "";
  }

  function mediaType(item) {
    const explicit = item?.model && typeof item.model === "object" ? item.model.media_type : "";
    if (explicit) return explicit;
    const url = mediaUrl(item);
    if (/\.(mp4|webm|mov)(\?|$)/i.test(url)) return "video";
    if (/\.(mp3|wav|m4a|aac|ogg|flac|opus)(\?|$)/i.test(url)) return "audio";
    return item?.gen_type === "music" ? "audio" : item?.gen_type || "image";
  }

  function modelLabel(item) {
    if (item?.model && typeof item.model === "object") return item.model.title || item.model.id || "ROXY";
    return String(item?.model || item?.gen_type || "ROXY").replaceAll("_", " ");
  }

  function authorName(item) {
    return item?.author?.username ? `@${item.author.username}` : item?.author?.display_name || "Пользователь ROXY";
  }

  function authorInitial(item) {
    return authorName(item).replace("@", "").trim().charAt(0).toUpperCase() || "R";
  }

  function authorId(item) { return item?.author?.id || item?.user_id || ""; }
  function authorReferral(item) { return item?.author_referral_code || item?.author?.referral_code || item?.author?.telegram_id || ""; }
  function isSubscribed(item) { const id = authorId(item); return id ? state.subscribed.has(String(id)) : false; }
  function itemById(id) { return (state.items || []).find((item) => String(item.id) === String(id)); }

  function replaceItem(next) {
    if (!next?.id) return;
    state.items = (state.items || []).map((item) => String(item.id) === String(next.id) ? next : item);
    if (state.commentsItem && String(state.commentsItem.id) === String(next.id)) state.commentsItem = next;
  }

  function mergeItems(current, incoming, append = false) {
    const map = new Map();
    const ordered = append ? [...current, ...incoming] : [...incoming, ...current];
    for (const item of ordered) {
      if (!item?.id || map.has(String(item.id))) continue;
      map.set(String(item.id), item);
    }
    return [...map.values()];
  }

  function mediaMarkup(item) {
    const url = mediaUrl(item);
    const type = mediaType(item);
    if (!url) return `<div class="rsf-placeholder">Нет превью</div>`;
    if (type === "video") return `<video src="${escapeHtml(url)}" muted playsinline preload="metadata"></video>`;
    if (type === "audio") return `<div class="rsf-audio"><span>♪</span><small>Аудио</small></div>`;
    return `<img src="${escapeHtml(url)}" alt="" loading="lazy" />`;
  }

  function cardMarkup(item) {
    const id = String(item.id || "");
    const mine = Boolean(item.is_mine);
    const subscribed = isSubscribed(item);
    const openable = Boolean(mediaUrl(item));
    const busy = state.busyId && String(state.busyId) === id;
    return `
      <article class="rsf-card" data-id="${escapeHtml(id)}" data-surface="${escapeHtml(item.surface || "feed")}">
        <div class="rsf-media" ${openable ? `data-action="preview" data-id="${escapeHtml(id)}"` : ""}>
          ${mediaMarkup(item)}
          <div class="rsf-side-actions">
            <button type="button" class="${item.liked_by_me ? "active" : ""}" data-action="like" data-id="${escapeHtml(id)}" aria-label="Лайк"><span>♥</span><b>${compact(item.likes_count)}</b></button>
            <button type="button" data-action="comments" data-id="${escapeHtml(id)}" aria-label="Комментарии"><span>☰</span><b>${compact(item.comments_count)}</b></button>
            <button type="button" data-action="share" data-id="${escapeHtml(id)}" aria-label="Поделиться"><span>➤</span><b>${compact(item.shares_count)}</b></button>
            <button type="button" class="gold" data-action="repeat" data-id="${escapeHtml(id)}" aria-label="Повторить"><span>${busy ? "…" : "↻"}</span><b>${compact(item.remixes)}</b></button>
          </div>
          <button type="button" class="rsf-repeat" data-action="repeat" data-id="${escapeHtml(id)}">${busy ? "Запускаю…" : "Повторить"}</button>
        </div>
        <footer class="rsf-author-row">
          <button type="button" class="rsf-author" data-action="profile" data-referral="${escapeHtml(authorReferral(item))}">
            <span class="rsf-avatar">${escapeHtml(authorInitial(item))}</span>
            <span><strong>${escapeHtml(authorName(item))}</strong><small>${escapeHtml(modelLabel(item))}</small></span>
          </button>
          ${mine ? `<span class="rsf-self">Моё</span>` : `<button type="button" class="rsf-follow ${subscribed ? "subscribed" : ""}" data-action="follow" data-author-id="${escapeHtml(authorId(item))}">${subscribed ? "Вы подписаны" : "Подписаться"}</button>`}
        </footer>
      </article>`;
  }

  function emptyMarkup(text) { return `<div class="rsf-empty"><span>✦</span><p>${escapeHtml(text)}</p></div>`; }

  function commentsMarkup() {
    const item = state.commentsItem;
    if (!item) return "";
    const rows = state.commentsLoading
      ? `<div class="rsf-comments-empty">Загружаю комментарии…</div>`
      : state.comments.length
        ? state.comments.map((comment) => `
          <div class="rsf-comment">
            <strong>${escapeHtml(comment.author?.display_name || comment.author?.username || "Пользователь")}</strong>
            <p>${escapeHtml(comment.text || "")}</p>
            <small>${escapeHtml(dateLabel(comment.created_at))}</small>
          </div>`).join("")
        : `<div class="rsf-comments-empty">Комментариев пока нет.</div>`;
    return `
      <div class="rsf-modal rsf-comments-modal">
        <button class="rsf-modal-bg" type="button" data-action="close-comments"></button>
        <section class="rsf-comments-card">
          <header><div><span>Комментарии</span><h2>${escapeHtml(authorName(item))}</h2></div><button type="button" data-action="close-comments">×</button></header>
          <div class="rsf-comments-list">${rows}</div>
          <form class="rsf-comment-form" data-action="comment-form" data-id="${escapeHtml(item.id)}">
            <input name="text" maxlength="300" autocomplete="off" placeholder="Написать комментарий" />
            <button type="submit">Отправить</button>
          </form>
        </section>
      </div>`;
  }

  function screen() {
    const screens = Array.from(document.querySelectorAll("main .screen"));
    return screens.find((item) => item.classList.contains("roxy-social-feed-screen"))
      || screens.find((item) => item.querySelector(".model-grid") || item.textContent?.includes("Модели и идеи"));
  }

  function patchNavLabel() {
    document.querySelectorAll(".bottom-nav button small").forEach((item) => {
      if (item.textContent?.trim() === "Каталог") item.textContent = "Лента";
    });
  }

  function render() {
    patchNavLabel();
    if (!isFeedRoute()) return;
    const host = screen();
    if (!host || state.rendering) return;
    state.rendering = true;
    host.classList.add("roxy-social-feed-screen");
    const title = state.profile ? (state.profileAuthor?.display_name || "Профиль") : "Лента";
    const subtitle = state.profile ? "Работы автора в ROXY" : "Новые работы, топ, подписки и быстрый повтор.";
    const items = state.items || [];
    host.innerHTML = `
      <div class="rsf-shell">
        <div class="rsf-tabs">
          ${state.profile ? `<button type="button" data-action="back-feed">‹ Назад</button>` : ""}
          <button type="button" class="${!state.profile && state.mode === "feed" ? "active" : ""}" data-action="tab-feed">Лента</button>
          <button type="button" class="${!state.profile && state.mode === "subscriptions" ? "active" : ""}" data-action="tab-subscriptions">Подписки</button>
        </div>
        ${!state.profile && state.mode === "feed" ? `<div class="rsf-source-tabs">${sources.map(([key, label]) => `<button type="button" class="${state.source === key ? "active" : ""}" data-action="source" data-source="${key}">${label}</button>`).join("")}</div>` : ""}
        <header class="rsf-head"><span>ROXY SOCIAL</span><h1>${escapeHtml(title)}</h1><p>${escapeHtml(subtitle)}</p></header>
        ${state.loading ? emptyMarkup("Загружаю ленту…") : state.error ? emptyMarkup(state.error) : items.length ? `<div class="rsf-list">${items.map(cardMarkup).join("")}</div>` : emptyMarkup(state.mode === "subscriptions" ? "Подпишись на авторов — их работы появятся здесь." : "Публикаций пока нет.")}
        ${!state.loading && state.hasMore ? `<button type="button" class="rsf-load-more" data-action="load-more">${state.loadingMore ? "Загружаю…" : "Показать ещё"}</button>` : ""}
      </div>
      ${commentsMarkup()}`;
    state.rendering = false;
  }

  async function loadSubscriptions() {
    const payload = await request("/api/v1/social/subscriptions?limit=100&offset=0");
    state.subscriptions = payload.items || [];
    state.subscribed = new Set(state.subscriptions.map((item) => String(item.id)).filter(Boolean));
    return state.subscriptions;
  }

  async function loadFeed({ append = false, spinner = true } = {}) {
    if (spinner) state.loading = true;
    if (!append) state.error = "";
    render();
    try {
      const offset = append ? state.items.length : 0;
      const [feed] = await Promise.all([
        request(`/api/v1/feed?sort=${encodeURIComponent(state.source)}&limit=${FEED_PAGE_SIZE}&offset=${offset}`),
        loadSubscriptions().catch(() => []),
      ]);
      const incoming = feed.items || [];
      state.items = append ? mergeItems(state.items, incoming, true) : incoming;
      state.hasMore = incoming.length === FEED_PAGE_SIZE;
    } catch (error) {
      state.error = error instanceof Error ? error.message : "Не удалось загрузить ленту";
    } finally {
      state.loading = false;
      state.loadingMore = false;
      render();
    }
  }

  async function loadSubscriptionFeed({ append = false } = {}) {
    if (!append) state.loading = true;
    state.error = "";
    render();
    try {
      const offset = append ? state.items.length : 0;
      await loadSubscriptions().catch(() => []);
      const payload = await request(`/api/v1/social/subscriptions/feed?limit=${FEED_PAGE_SIZE}&offset=${offset}`);
      const incoming = payload.items || [];
      state.items = append ? mergeItems(state.items, incoming, true) : incoming;
      state.hasMore = Boolean(payload.has_more) || incoming.length === FEED_PAGE_SIZE;
    } catch (error) {
      state.error = error instanceof Error ? error.message : "Не удалось загрузить подписки";
    } finally {
      state.loading = false;
      state.loadingMore = false;
      render();
    }
  }

  async function loadProfile(referral) {
    if (!referral) return;
    state.loading = true;
    state.error = "";
    state.profile = referral;
    state.hasMore = false;
    render();
    try {
      const payload = await request(`/api/v1/profiles/${encodeURIComponent(referral)}/feed?limit=24&offset=0`);
      state.profileAuthor = payload.author || null;
      state.items = payload.items || [];
      state.hasMore = Boolean(payload.has_more);
      await loadSubscriptions().catch(() => []);
    } catch (error) {
      state.error = error instanceof Error ? error.message : "Не удалось открыть профиль";
    } finally {
      state.loading = false;
      render();
    }
  }

  async function toggleFollow(id) {
    if (!id) return;
    const subscribed = state.subscribed.has(String(id));
    try {
      const result = await request(`/api/v1/social/profiles/${encodeURIComponent(id)}/subscribe`, { method: subscribed ? "DELETE" : "POST" });
      if (result.subscribed_by_me === false || subscribed) state.subscribed.delete(String(id));
      else state.subscribed.add(String(id));
      haptic("medium");
      render();
      if (state.mode === "subscriptions" && subscribed) void loadSubscriptionFeed();
    } catch (error) {
      notify("error");
      toast(error instanceof Error ? error.message : "Не удалось изменить подписку");
    }
  }

  async function toggleLike(id) {
    const item = itemById(id);
    if (!item || state.busyId) return;
    const surface = item.surface || (state.profile || state.mode === "subscriptions" ? "profile" : "feed");
    state.busyId = id;
    render();
    try {
      const result = await request(`/api/v1/feed/${encodeURIComponent(id)}/like${item.liked_by_me ? `?surface=${encodeURIComponent(surface)}` : ""}`, {
        method: item.liked_by_me ? "DELETE" : "POST",
        body: item.liked_by_me ? undefined : JSON.stringify({ surface }),
      });
      replaceItem(result.feed_item || result.item || { ...item, liked_by_me: result.liked_by_me, likes_count: result.likes_count });
      haptic("light");
    } catch (error) {
      notify("error");
      toast(error instanceof Error ? error.message : "Не удалось поставить лайк");
    } finally {
      state.busyId = null;
      render();
    }
  }

  async function share(id) {
    const item = itemById(id);
    if (!item || state.busyId) return;
    const surface = item.surface || (state.profile || state.mode === "subscriptions" ? "profile" : "feed");
    state.busyId = id;
    render();
    try {
      const result = await request(`/api/v1/feed/${encodeURIComponent(id)}/share`, {
        method: "POST",
        body: JSON.stringify({ surface }),
      });
      replaceItem(result.feed_item || result.item || { ...item, shares_count: result.shares_count });
      const url = result.link || result.post_link || window.location.href;
      await copyToClipboard(url).catch(() => false);
      const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(url)}`;
      if (tg()?.openTelegramLink) tg().openTelegramLink(shareUrl);
      else window.open(shareUrl, "_blank", "noopener,noreferrer");
    } catch (error) {
      notify("error");
      toast(error instanceof Error ? error.message : "Не удалось поделиться");
    } finally {
      state.busyId = null;
      render();
    }
  }

  async function repeat(id) {
    const item = itemById(id);
    if (!item || state.busyId) return;
    const surface = item.surface || (state.profile || state.mode === "subscriptions" ? "profile" : "feed");
    state.busyId = id;
    render();
    try {
      const result = await request(`/api/v1/feed/${encodeURIComponent(id)}/remix`, {
        method: "POST",
        body: JSON.stringify({ surface }),
      });
      replaceItem(result.feed_item || result.source_item || result.item || { ...item, remixes: Number(item.remixes || 0) + 1 });
      notify("success");
      toast("Повтор запущен. Готовый результат появится в Истории.");
    } catch (error) {
      notify("error");
      toast(error instanceof Error ? error.message : "Не удалось повторить");
    } finally {
      state.busyId = null;
      render();
    }
  }

  async function openComments(id) {
    const item = itemById(id);
    if (!item) return;
    const surface = item.surface || (state.profile || state.mode === "subscriptions" ? "profile" : "feed");
    state.commentsItem = item;
    state.comments = [];
    state.commentsLoading = true;
    render();
    try {
      const payload = await request(`/api/v1/feed/${encodeURIComponent(id)}/comments?surface=${encodeURIComponent(surface)}&limit=50`);
      state.comments = payload.items || [];
    } catch (error) {
      toast(error instanceof Error ? error.message : "Не удалось загрузить комментарии");
    } finally {
      state.commentsLoading = false;
      render();
    }
  }

  async function addComment(form) {
    const item = state.commentsItem;
    if (!item) return;
    const input = form.elements.namedItem("text");
    const text = String(input?.value || "").trim();
    if (!text) return;
    const surface = item.surface || (state.profile || state.mode === "subscriptions" ? "profile" : "feed");
    try {
      const comment = await request(`/api/v1/feed/${encodeURIComponent(item.id)}/comments`, {
        method: "POST",
        body: JSON.stringify({ surface, text }),
      });
      state.comments = [comment, ...state.comments];
      item.comments_count = Number(item.comments_count || 0) + 1;
      if (input) input.value = "";
      haptic("light");
      render();
    } catch (error) {
      notify("error");
      toast(error instanceof Error ? error.message : "Не удалось добавить комментарий");
    }
  }

  function preview(id) {
    const item = itemById(id);
    if (!item) return;
    const url = mediaUrl(item);
    const type = mediaType(item);
    const modal = document.createElement("div");
    modal.className = "rsf-modal";
    modal.innerHTML = `
      <button class="rsf-modal-bg" type="button" data-action="close-preview"></button>
      <section class="rsf-modal-card">
        <button class="rsf-modal-close" type="button" data-action="close-preview">×</button>
        <div class="rsf-modal-media">${type === "video" ? `<video src="${escapeHtml(url)}" controls playsinline></video>` : type === "audio" ? `<audio src="${escapeHtml(url)}" controls></audio>` : `<img src="${escapeHtml(url)}" alt="Результат" />`}</div>
        <div class="rsf-modal-copy"><span>Публикация</span><h2>${escapeHtml(modelLabel(item))}</h2><p>${escapeHtml(authorName(item))} · ${escapeHtml(dateLabel(item.feed_published_at || item.created_at))}</p><button type="button" class="rsf-modal-repeat" data-action="repeat" data-id="${escapeHtml(item.id)}">Повторить</button></div>
      </section>`;
    document.body.appendChild(modal);
  }

  async function copyToClipboard(text) {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch {}
    return false;
  }

  function toast(text) {
    const old = document.querySelector(".rsf-toast");
    if (old) old.remove();
    const node = document.createElement("div");
    node.className = "rsf-toast";
    node.textContent = text;
    document.body.appendChild(node);
    window.setTimeout(() => node.remove(), 2800);
  }

  document.addEventListener("submit", (event) => {
    const form = event.target instanceof Element ? event.target.closest("[data-action='comment-form']") : null;
    if (!form) return;
    event.preventDefault();
    void addComment(form);
  }, true);

  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target.closest("[data-action]") : null;
    if (!target) return;
    const action = target.getAttribute("data-action");
    if (!target.closest(".rsf-shell") && !target.closest(".rsf-modal")) return;
    event.preventDefault();
    event.stopPropagation();
    if (action === "tab-feed") { state.mode = "feed"; state.profile = null; state.items = []; state.hasMore = false; void loadFeed(); }
    if (action === "tab-subscriptions") { state.mode = "subscriptions"; state.profile = null; state.items = []; state.hasMore = false; void loadSubscriptionFeed(); }
    if (action === "source") { state.source = target.getAttribute("data-source") || "recent"; state.items = []; state.hasMore = false; void loadFeed(); }
    if (action === "load-more") {
      if (state.loadingMore) return;
      state.loadingMore = true;
      render();
      if (state.mode === "subscriptions") void loadSubscriptionFeed({ append: true });
      else void loadFeed({ append: true, spinner: false });
    }
    if (action === "back-feed") { state.mode = "feed"; state.profile = null; state.items = []; void loadFeed(); }
    if (action === "profile") void loadProfile(target.getAttribute("data-referral") || "");
    if (action === "follow") void toggleFollow(target.getAttribute("data-author-id") || "");
    if (action === "like") void toggleLike(target.getAttribute("data-id") || "");
    if (action === "share") void share(target.getAttribute("data-id") || "");
    if (action === "repeat") void repeat(target.getAttribute("data-id") || "");
    if (action === "preview") preview(target.getAttribute("data-id") || "");
    if (action === "comments") void openComments(target.getAttribute("data-id") || "");
    if (action === "close-preview") target.closest(".rsf-modal")?.remove();
    if (action === "close-comments") { state.commentsItem = null; state.comments = []; render(); }
  }, true);

  function refreshIfVisible() {
    if (!isFeedRoute() || document.visibilityState !== "visible") return;
    if (state.profile) return;
    if (state.mode === "subscriptions") void loadSubscriptionFeed();
    else void loadFeed({ spinner: false });
  }

  function boot() {
    patchNavLabel();
    if (!isFeedRoute()) return;
    render();
    if (!state.booted) {
      state.booted = true;
      void loadFeed();
    }
  }

  const observer = new MutationObserver(() => {
    if (state.rendering) return;
    window.requestAnimationFrame(boot);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("visibilitychange", refreshIfVisible);
  window.addEventListener("focus", refreshIfVisible);
  window.addEventListener("popstate", () => { state.booted = false; window.setTimeout(boot, 0); });
  window.setInterval(refreshIfVisible, 15_000);
  window.setInterval(patchNavLabel, 1000);
  window.setTimeout(boot, 0);
})();
