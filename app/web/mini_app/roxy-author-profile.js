(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    authorId: new URLSearchParams(window.location.search).get("author") || null,
    profile: null,
    loading: false,
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

  function setAuthorQuery(authorId) {
    const url = new URL(window.location.href);
    if (authorId) url.searchParams.set("author", authorId);
    else url.searchParams.delete("author");
    window.history.replaceState({ ...(window.history.state || {}) }, "", url);
  }

  function open(authorId) {
    if (!authorId) return false;
    state.authorId = String(authorId);
    setAuthorQuery(state.authorId);
    return Boolean(window.RoxyCustomerNavigation?.open?.("author"));
  }

  function renderState(container, message, tone = "") {
    const node = el("div", `roxy-child-screen-state${tone ? ` ${tone}` : ""}`, message);
    container.replaceChildren(node);
  }

  function renderProfile(container, profile) {
    state.profile = profile;
    container.replaceChildren();

    const card = el("section", "shell-panel social-profile-target roxy-author-profile-card");
    const identity = el("div", "social-profile-title");
    identity.append(el("strong", "", profile.display_name || "Автор"));
    if (profile.username) identity.append(el("small", "", `@${profile.username}`));
    card.append(identity, el("small", "", `${Number(profile.follower_count || 0)} подписчиков`));

    if (profile.is_self) {
      card.appendChild(el(
        "div",
        "profile-identity-note",
        profile.profile_discoverable
          ? "Это ваш публичный профиль."
          : "Ваш профиль сейчас приватный. Управлять публичностью можно в настройках профиля.",
      ));
      container.appendChild(card);
      return;
    }

    const action = el(
      "button",
      profile.subscribed_by_me ? "profile-action-button secondary" : "profile-action-button",
      profile.subscribed_by_me ? "Отписаться" : "Подписаться",
    );
    action.type = "button";
    action.dataset.subscribed = profile.subscribed_by_me ? "true" : "false";
    action.addEventListener("click", () => toggleSubscription(container, action));
    card.appendChild(action);
    container.appendChild(card);
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
      renderProfile(container, profile);
      tg?.HapticFeedback?.notificationOccurred?.("success");
    } catch (error) {
      button.disabled = false;
      tg?.HapticFeedback?.notificationOccurred?.("error");
      const message = el("div", "profile-message error", error.message || "Не удалось изменить подписку");
      button.insertAdjacentElement("afterend", message);
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

  async function authorIdForFeedCard(card) {
    const generationId = card?.dataset?.generationId;
    if (!generationId) return null;
    const surface = card.dataset.surface === "profile" ? "profile" : "feed";
    const item = await api(`/api/v1/feed/${encodeURIComponent(generationId)}?surface=${encodeURIComponent(surface)}`);
    return item?.author?.id || null;
  }

  async function interceptFeedAuthor(event) {
    const button = event.target.closest?.(".feed-card .feed-secondary, .feed-card .feed-action");
    if (!button) return;
    const label = String(button.textContent || "").trim();
    if (label !== "👤 Автор" && label !== "👤 Профиль") return;
    const card = button.closest(".feed-card");
    if (!card) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    try {
      const authorId = await authorIdForFeedCard(card);
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
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
