(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const PAGE_SIZE = 24;
  const state = {
    authorId: new URLSearchParams(window.location.search).get("author") || null,
    profile: null,
    items: [],
    offset: 0,
    hasMore: false,
    loading: false,
    loadingMore: false,
  };

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
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const error = new Error(typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function icon(name, size = 18) {
    return window.RoxyIcons?.create?.(name, { size }) || null;
  }

  function setAuthorQuery(authorId) {
    const url = new URL(window.location.href);
    if (authorId) url.searchParams.set("author", authorId);
    else url.searchParams.delete("author");
    window.history.replaceState({ ...(window.history.state || {}) }, "", url);
  }

  function open(authorId) {
    if (!authorId) return false;
    state.authorId = String(authorId);
    state.profile = null;
    state.items = [];
    state.offset = 0;
    state.hasMore = false;
    setAuthorQuery(state.authorId);
    return Boolean(window.RoxyCustomerNavigation?.open?.("author"));
  }

  function renderState(container, message, tone = "") {
    const node = el("div", `roxy-child-screen-state${tone ? ` ${tone}` : ""}`, message);
    container.replaceChildren(node);
  }

  function initials(profile) {
    const value = profile?.display_name || profile?.username || "R";
    const words = String(value).trim().split(/\s+/).filter(Boolean);
    return `${words[0]?.[0] || "R"}${words[1]?.[0] || ""}`.toUpperCase();
  }

  function formatCompact(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number)) return "0";
    return new Intl.NumberFormat("ru-RU", {
      notation: number >= 1000 ? "compact" : "standard",
      maximumFractionDigits: 1,
    }).format(number);
  }

  function mediaUrl(item) {
    return item?.preview_url || item?.result_url || item?.result_urls?.[0] || item?.media?.[0]?.url || "";
  }

  function isVideo(item) {
    const type = String(item?.gen_type || item?.media?.[0]?.content_type || "").toLowerCase();
    if (type.includes("video")) return true;
    return /\.(mp4|webm|mov)(\?|$)/i.test(String(mediaUrl(item)));
  }

  function totals(items) {
    return items.reduce(
      (acc, item) => ({
        likes: acc.likes + Number(item.likes_count || 0),
        shares: acc.shares + Number(item.shares_count || 0),
      }),
      { likes: 0, shares: 0 },
    );
  }

  function stat(label, value) {
    const item = el("div", "roxy-user-profile-stat");
    item.append(el("strong", "", value), el("span", "", label));
    return item;
  }

  function actionButton(label, handler, secondary = false) {
    const button = el("button", secondary ? "profile-action-button secondary" : "profile-action-button", label);
    button.type = "button";
    button.addEventListener("click", handler);
    return button;
  }

  function buildTile(item) {
    const button = el("button", "roxy-user-profile-tile");
    button.type = "button";
    button.dataset.generationId = item.id;
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
      const glyph = icon("create", 17);
      if (glyph) play.appendChild(glyph);
      button.appendChild(play);
    } else if (url) {
      const image = document.createElement("img");
      image.src = url;
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";
      button.appendChild(image);
    } else {
      const placeholder = el("span", "roxy-user-profile-placeholder");
      const glyph = icon("image", 24);
      if (glyph) placeholder.appendChild(glyph);
      button.appendChild(placeholder);
    }

    const overlay = el("span", "roxy-user-profile-tile-overlay");
    const reactions = el("span", "roxy-user-profile-reactions");
    const heart = icon("like", 13);
    if (heart) reactions.appendChild(heart);
    reactions.appendChild(el("span", "", formatCompact(item.likes_count || 0)));
    overlay.append(el("span", "", item.model || item.gen_type || "AI"), reactions);
    button.appendChild(overlay);
    button.addEventListener("click", () => openPublication(item));
    return button;
  }

  function openPublication(item) {
    const url = mediaUrl(item);
    if (!url) return;
    try {
      if (typeof tg?.openLink === "function" && /^https:\/\//i.test(url)) {
        tg.openLink(url);
        return;
      }
    } catch (_error) { /* browser fallback */ }
    window.open(url, "_blank", "noopener,noreferrer");
  }

  async function copyProfileLink(profile) {
    if (!profile?.referral_code) return;
    try {
      const payload = await api(`/api/v1/profiles/${encodeURIComponent(profile.referral_code)}/link`);
      if (!payload?.link) throw new Error("Ссылка недоступна");
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(payload.link);
      else tg?.showPopup?.({ title: "Профиль", message: payload.link, buttons: [{ type: "close" }] });
      tg?.HapticFeedback?.notificationOccurred?.("success");
    } catch (_error) {
      tg?.HapticFeedback?.notificationOccurred?.("error");
    }
  }

  function renderProfile(container, profile) {
    state.profile = profile;
    container.replaceChildren();

    const hero = el("section", "roxy-user-profile-hero roxy-author-showcase");
    const top = el("div", "roxy-user-profile-top");
    const avatar = el("div", "roxy-user-profile-avatar");
    avatar.appendChild(el("span", "", initials(profile)));
    const copy = el("div", "roxy-user-profile-copy");
    copy.append(
      el("h2", "", profile.display_name || "Автор"),
      el("div", "roxy-user-profile-handle", profile.username ? `@${profile.username}` : "Автор ROXY"),
      el("span", "roxy-user-profile-visibility is-public", "Публичный профиль"),
    );

    const share = el("button", "roxy-user-profile-share");
    share.type = "button";
    share.setAttribute("aria-label", "Поделиться профилем");
    const shareIcon = icon("share", 20);
    if (shareIcon) share.appendChild(shareIcon);
    share.addEventListener("click", () => void copyProfileLink(profile));
    top.append(avatar, copy, share);

    const aggregate = totals(state.items);
    const stats = el("div", "roxy-user-profile-stats");
    stats.append(
      stat("Работы", state.hasMore ? `${formatCompact(state.items.length)}+` : formatCompact(state.items.length)),
      stat("Подписчики", formatCompact(profile.follower_count || 0)),
      stat("Лайки", formatCompact(aggregate.likes)),
      stat("Репосты", formatCompact(aggregate.shares)),
    );
    hero.append(top, stats);

    const actions = el("div", "roxy-author-showcase-actions");
    if (profile.is_self) {
      actions.appendChild(actionButton("Мой профиль", () => window.RoxyCustomerNavigation?.open?.("profile"), true));
    } else {
      const subscribe = actionButton(
        profile.subscribed_by_me ? "Отписаться" : "Подписаться",
        () => toggleSubscription(container, subscribe),
        profile.subscribed_by_me,
      );
      subscribe.dataset.subscribed = profile.subscribed_by_me ? "true" : "false";
      actions.appendChild(subscribe);
    }

    const portfolio = el("section", "roxy-author-portfolio");
    const head = el("div", "roxy-user-profile-section-head");
    const headCopy = el("div");
    headCopy.append(el("span", "section-kicker", "Портфолио"), el("h2", "", "Работы автора"));
    head.appendChild(headCopy);
    const grid = el("div", "roxy-user-profile-grid");
    if (state.items.length) {
      grid.append(...state.items.map(buildTile));
    } else {
      const empty = el("div", "roxy-user-profile-empty");
      empty.append(el("strong", "", "Публикаций пока нет"), el("p", "", "У автора пока нет работ, опубликованных в профиле."));
      grid.appendChild(empty);
    }
    portfolio.append(head, grid);

    if (state.hasMore) {
      const more = actionButton(state.loadingMore ? "Загрузка…" : "Показать ещё", () => void loadMore(container), true);
      more.classList.add("roxy-user-profile-more");
      more.disabled = state.loadingMore;
      portfolio.appendChild(more);
    }

    container.append(hero, actions, portfolio);
  }

  async function toggleSubscription(container, button) {
    if (!state.authorId || button.disabled) return;
    button.disabled = true;
    const subscribed = button.dataset.subscribed === "true";
    try {
      tg?.HapticFeedback?.impactOccurred?.("light");
      const profile = await api(`/api/v1/social/profiles/${encodeURIComponent(state.authorId)}/subscribe`, {
        method: subscribed ? "DELETE" : "POST",
      });
      state.profile = profile;
      renderProfile(container, profile);
      tg?.HapticFeedback?.notificationOccurred?.("success");
    } catch (error) {
      button.disabled = false;
      tg?.HapticFeedback?.notificationOccurred?.("error");
      const message = el("div", "profile-message error", error.message || "Не удалось изменить подписку");
      button.insertAdjacentElement("afterend", message);
    }
  }

  async function loadPortfolio(profile, reset = true) {
    if (!profile?.referral_code) return [];
    if (reset) {
      state.items = [];
      state.offset = 0;
      state.hasMore = false;
    }
    const payload = await api(
      `/api/v1/profiles/${encodeURIComponent(profile.referral_code)}/feed?limit=${PAGE_SIZE}&offset=${state.offset}`,
    );
    const next = Array.isArray(payload?.items) ? payload.items : [];
    const seen = new Set(state.items.map((item) => String(item.id)));
    state.items.push(...next.filter((item) => !seen.has(String(item.id))));
    state.offset += next.length;
    state.hasMore = next.length === PAGE_SIZE;
    return next;
  }

  async function loadMore(container) {
    if (!state.profile || state.loadingMore || !state.hasMore) return;
    state.loadingMore = true;
    renderProfile(container, state.profile);
    try {
      await loadPortfolio(state.profile, false);
    } finally {
      state.loadingMore = false;
      renderProfile(container, state.profile);
    }
  }

  async function render(container, authorId = state.authorId) {
    if (!container) return false;
    if (authorId) state.authorId = String(authorId);
    if (!state.authorId) {
      renderState(container, "Автор не выбран.", "error");
      return false;
    }
    if (state.loading) return true;
    state.loading = true;
    renderState(container, "Загружаю профиль…");
    try {
      const profile = await api(`/api/v1/social/profiles/${encodeURIComponent(state.authorId)}`);
      state.profile = profile;
      await loadPortfolio(profile, true);
      renderProfile(container, profile);
      return true;
    } catch (error) {
      renderState(
        container,
        error.status === 404 ? "Публичный профиль недоступен." : (error.message || "Не удалось открыть профиль."),
        "error",
      );
      return false;
    } finally {
      state.loading = false;
    }
  }

  async function authorForFeedCard(card) {
    const generationId = card?.dataset?.generationId;
    if (!generationId) return null;
    const surface = card.dataset.surface === "profile" ? "profile" : "feed";
    const item = await api(`/api/v1/feed/${encodeURIComponent(generationId)}?surface=${encodeURIComponent(surface)}`);
    return item?.author?.id || null;
  }

  async function interceptFeedAuthor(event) {
    const button = event.target.closest?.(".feed-card .feed-secondary, .feed-card .feed-action");
    if (!button) return;
    const action = button.dataset.feedAction;
    const label = String(button.textContent || "").trim();
    if (action !== "author" && action !== "profile" && label !== "Автор" && label !== "Профиль") return;
    const card = button.closest(".feed-card");
    if (!card) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    try {
      const authorId = await authorForFeedCard(card);
      if (!authorId) throw new Error("Профиль автора недоступен");
      open(authorId);
    } catch (error) {
      tg?.HapticFeedback?.notificationOccurred?.("error");
      const toast = document.getElementById("feedToast");
      if (toast) {
        toast.textContent = error.message || "Не удалось открыть автора";
        toast.hidden = false;
      }
    }
  }

  function syncFromUrl() {
    const authorId = new URLSearchParams(window.location.search).get("author");
    if (authorId) state.authorId = authorId;
  }

  function init() {
    document.addEventListener("click", interceptFeedAuthor, true);
    window.addEventListener("popstate", syncFromUrl);
    window.RoxyAuthorProfile = Object.freeze({
      open,
      render,
      get authorId() {
        return state.authorId;
      },
      get profile() {
        return state.profile;
      },
      get items() {
        return [...state.items];
      },
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();