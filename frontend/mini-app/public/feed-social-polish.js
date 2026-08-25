(() => {
  if (window.__roxySocialFeedPolish) return;
  window.__roxySocialFeedPolish = true;

  const state = {
    mode: "feed",
    profile: null,
    profileAuthor: null,
    items: [],
    loading: false,
    error: "",
    subscribed: new Set(),
    subscriptions: [],
    booted: false,
    rendering: false,
  };

  const money = new Intl.NumberFormat("ru-RU", { notation: "compact", maximumFractionDigits: 1 });

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
    return item.preview_url || item.result_url || item.result_urls?.[0] || item.media?.[0]?.url || "";
  }

  function mediaType(item) {
    const explicit = item.model && typeof item.model === "object" ? item.model.media_type : "";
    if (explicit) return explicit;
    const url = mediaUrl(item);
    if (/\.(mp4|webm|mov)(\?|$)/i.test(url)) return "video";
    if (/\.(mp3|wav|m4a|aac|ogg|flac|opus)(\?|$)/i.test(url)) return "audio";
    return item.gen_type === "music" ? "audio" : "image";
  }

  function modelLabel(item) {
    if (item.model && typeof item.model === "object") return item.model.title || item.model.id || "ROXY";
    return String(item.model || item.gen_type || "ROXY").replaceAll("_", " ");
  }

  function authorName(item) {
    return item.author?.username ? `@${item.author.username}` : item.author?.display_name || "Пользователь ROXY";
  }

  function authorInitial(item) {
    return authorName(item).replace("@", "").trim().charAt(0).toUpperCase() || "R";
  }

  function isSubscribed(item) {
    const id = item.author?.id || item.user_id;
    return id ? state.subscribed.has(String(id)) : false;
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
    const authorId = item.author?.id || item.user_id || "";
    const referral = item.author_referral_code || item.author?.referral_code || item.author?.telegram_id || "";
    const mine = Boolean(item.is_mine);
    const subscribed = isSubscribed(item);
    const openable = Boolean(mediaUrl(item));
    return `
      <article class="rsf-card" data-id="${escapeHtml(item.id)}" data-surface="${escapeHtml(item.surface || "feed")}">
        <div class="rsf-media" ${openable ? `data-action="preview" data-id="${escapeHtml(item.id)}"` : ""}>
          ${mediaMarkup(item)}
          <div class="rsf-side-actions">
            <button type="button" class="${item.liked_by_me ? "active" : ""}" data-action="like" data-id="${escapeHtml(item.id)}" aria-label="Лайк"><span>♥</span><b>${compact(item.likes_count)}</b></button>
            <button type="button" data-action="comments" data-id="${escapeHtml(item.id)}" aria-label="Комментарии"><span>☰</span><b>${compact(item.comments_count)}</b></button>
            <button type="button" data-action="share" data-id="${escapeHtml(item.id)}" aria-label="Поделиться"><span>➤</span><b>${compact(item.shares_count)}</b></button>
            <button type="button" class="gold" data-action="repeat" data-id="${escapeHtml(item.id)}" aria-label="Повторить"><span>↻</span><b>${compact(item.remixes)}</b></button>
          </div>
          <button type="button" class="rsf-repeat" data-action="repeat" data-id="${escapeHtml(item.id)}">Повторить</button>
        </div>
        <footer class="rsf-author-row">
          <button type="button" class="rsf-author" data-action="profile" data-referral="${escapeHtml(referral)}">
            <span class="rsf-avatar">${escapeHtml(authorInitial(item))}</span>
            <span><strong>${escapeHtml(authorName(item))}</strong><small>${escapeHtml(modelLabel(item))}</small></span>
          </button>
          ${mine ? `<span class="rsf-self">Моё</span>` : `<button type="button" class="rsf-follow ${subscribed ? "subscribed" : ""}" data-action="follow" data-author-id="${escapeHtml(authorId)}">${subscribed ? "Вы подписаны" : "Подписаться"}</button>`}
        </footer>
      </article>`;
  }

  function emptyMarkup(text) {
    return `<div class="rsf-empty"><span>✦</span><p>${escapeHtml(text)}</p></div>`;
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
    const subtitle = state.profile ? "Работы автора в ROXY" : "Кто выложил, лайки, подписки и быстрый повтор.";
    const items = state.items || [];
    host.innerHTML = `
      <div class="rsf-shell">
        <div class="rsf-tabs">
          ${state.profile ? `<button type="button" data-action="back-feed">‹ Назад</button>` : ""}
          <button type="button" class="${!state.profile && state.mode === "feed" ? "active" : ""}" data-action="tab-feed">Лента</button>
          <button type="button" class="${!state.profile && state.mode === "subscriptions" ? "active" : ""}" data-action="tab-subscriptions">Подписки</button>
        </div>
        <header class="rsf-head"><span>ROXY SOCIAL</span><h1>${escapeHtml(title)}</h1><p>${escapeHtml(subtitle)}</p></header>
        ${state.loading ? emptyMarkup("Загружаю ленту…") : state.error ? emptyMarkup(state.error) : items.length ? `<div class="rsf-list">${items.map(cardMarkup).join("")}</div>` : emptyMarkup(state.mode === "subscriptions" ? "Подпишись на авторов — их работы появятся здесь." : "Публикаций пока нет.")}
      </div>`;
    state.rendering = false;
  }

  async function loadSubscriptions() {
    const payload = await request("/api/v1/social/subscriptions?limit=50&offset=0");
    state.subscriptions = payload.items || [];
    state.subscribed = new Set(state.subscriptions.map((item) => String(item.id)).filter(Boolean));
    return state.subscriptions;
  }

  async function loadFeed() {
    state.loading = true;
    state.error = "";
    render();
    try {
      const [feed] = await Promise.all([
        request("/api/v1/feed?sort=recent&limit=24&offset=0"),
        loadSubscriptions().catch(() => []),
      ]);
      state.items = feed.items || [];
    } catch (error) {
      state.error = error instanceof Error ? error.message : "Не удалось загрузить ленту";
    } finally {
      state.loading = false;
      render();
    }
  }

  async function loadSubscriptionFeed() {
    state.loading = true;
    state.error = "";
    render();
    try {
      const subscriptions = await loadSubscriptions();
      const feeds = await Promise.allSettled(
        subscriptions
          .filter((item) => item.referral_code)
          .slice(0, 20)
          .map((item) => request(`/api/v1/profiles/${encodeURIComponent(item.referral_code)}/feed?limit=12&offset=0`))
      );
      state.items = feeds
        .flatMap((result) => result.status === "fulfilled" ? (result.value.items || []) : [])
        .sort((a, b) => new Date(b.feed_published_at || b.created_at || 0).getTime() - new Date(a.feed_published_at || a.created_at || 0).getTime());
    } catch (error) {
      state.error = error instanceof Error ? error.message : "Не удалось загрузить подписки";
    } finally {
      state.loading = false;
      render();
    }
  }

  async function loadProfile(referral) {
    if (!referral) return;
    state.loading = true;
    state.error = "";
    state.profile = referral;
    render();
    try {
      const payload = await request(`/api/v1/profiles/${encodeURIComponent(referral)}/feed?limit=24&offset=0`);
      state.profileAuthor = payload.author || null;
      state.items = payload.items || [];
      await loadSubscriptions().catch(() => []);
    } catch (error) {
      state.error = error instanceof Error ? error.message : "Не удалось открыть профиль";
    } finally {
      state.loading = false;
      render();
    }
  }

  function itemById(id) {
    return (state.items || []).find((item) => String(item.id) === String(id));
  }

  async function toggleFollow(authorId) {
    if (!authorId) return;
    const subscribed = state.subscribed.has(String(authorId));
    try {
      await request(`/api/v1/social/profiles/${encodeURIComponent(authorId)}/subscribe`, { method: subscribed ? "DELETE" : "POST" });
      if (subscribed) state.subscribed.delete(String(authorId));
      else state.subscribed.add(String(authorId));
      haptic("medium");
      render();
    } catch (error) {
      notify("error");
      toast(error instanceof Error ? error.message : "Не удалось изменить подписку");
    }
  }

  async function toggleLike(id) {
    const item = itemById(id);
    if (!item) return;
    const surface = item.surface || "feed";
    try {
      const result = await request(`/api/v1/feed/${encodeURIComponent(id)}/like${item.liked_by_me ? `?surface=${encodeURIComponent(surface)}` : ""}`, {
        method: item.liked_by_me ? "DELETE" : "POST",
        body: item.liked_by_me ? undefined : JSON.stringify({ surface }),
      });
      item.liked_by_me = result.liked_by_me;
      item.likes_count = result.likes_count;
      haptic("light");
      render();
    } catch (error) {
      notify("error");
      toast(error instanceof Error ? error.message : "Не удалось поставить лайк");
    }
  }

  async function share(id) {
    const item = itemById(id);
    if (!item) return;
    try {
      const result = await request(`/api/v1/feed/${encodeURIComponent(id)}/share`, {
        method: "POST",
        body: JSON.stringify({ surface: item.surface || "feed" }),
      });
      item.shares_count = result.shares_count;
      const url = result.link || window.location.href;
      const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(url)}`;
      if (tg()?.openTelegramLink) tg().openTelegramLink(shareUrl);
      else window.open(shareUrl, "_blank", "noopener,noreferrer");
      render();
    } catch (error) {
      notify("error");
      toast(error instanceof Error ? error.message : "Не удалось поделиться");
    }
  }

  async function repeat(id) {
    const item = itemById(id);
    if (!item) return;
    try {
      await request(`/api/v1/feed/${encodeURIComponent(id)}/remix`, {
        method: "POST",
        body: JSON.stringify({ surface: item.surface || "feed" }),
      });
      item.remixes = Number(item.remixes || 0) + 1;
      notify("success");
      toast("Повтор запущен. Готовый результат появится в Истории.");
      render();
    } catch (error) {
      notify("error");
      toast(error instanceof Error ? error.message : "Не удалось повторить");
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

  function toast(text) {
    const old = document.querySelector(".rsf-toast");
    if (old) old.remove();
    const node = document.createElement("div");
    node.className = "rsf-toast";
    node.textContent = text;
    document.body.appendChild(node);
    window.setTimeout(() => node.remove(), 2800);
  }

  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target.closest("[data-action]") : null;
    if (!target) return;
    const action = target.getAttribute("data-action");
    if (!target.closest(".rsf-shell") && !target.closest(".rsf-modal")) return;
    event.preventDefault();
    event.stopPropagation();
    if (action === "tab-feed") { state.mode = "feed"; state.profile = null; void loadFeed(); }
    if (action === "tab-subscriptions") { state.mode = "subscriptions"; state.profile = null; void loadSubscriptionFeed(); }
    if (action === "back-feed") { state.mode = "feed"; state.profile = null; void loadFeed(); }
    if (action === "profile") void loadProfile(target.getAttribute("data-referral") || "");
    if (action === "follow") void toggleFollow(target.getAttribute("data-author-id") || "");
    if (action === "like") void toggleLike(target.getAttribute("data-id") || "");
    if (action === "share") void share(target.getAttribute("data-id") || "");
    if (action === "repeat") void repeat(target.getAttribute("data-id") || "");
    if (action === "preview") preview(target.getAttribute("data-id") || "");
    if (action === "comments") toast("Комментарии откроются в карточке публикации.");
    if (action === "close-preview") target.closest(".rsf-modal")?.remove();
  }, true);

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
    if (isFeedRoute()) {
      const host = screen();
      if (host?.classList.contains("roxy-social-feed-screen")) return;
    }
    window.requestAnimationFrame(boot);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("popstate", () => { state.booted = false; window.setTimeout(boot, 0); });
  window.addEventListener("pushstate", () => { state.booted = false; window.setTimeout(boot, 0); });
  window.setInterval(patchNavLabel, 1000);
  window.setTimeout(boot, 0);
})();
