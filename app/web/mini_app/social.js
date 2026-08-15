(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const state = {
    historyItems: [],
    latestGeneration: null,
    subscriptions: [],
    profileTarget: null,
    mountedProfile: false,
  };

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
    try {
      tg?.HapticFeedback?.impactOccurred?.(kind);
    } catch (_error) {
      // Optional Telegram capability.
    }
  }

  function notify(kind = "success") {
    try {
      tg?.HapticFeedback?.notificationOccurred?.(kind);
    } catch (_error) {
      // Optional Telegram capability.
    }
  }

  function toast(message) {
    const node = document.getElementById("toast");
    if (!node) return;
    node.textContent = message;
    node.hidden = false;
    window.setTimeout(() => {
      if (node.textContent === message) node.hidden = true;
    }, 2600);
  }

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function applyHistoryContext(items) {
    state.historyItems = Array.isArray(items) ? items : [];
    requestAnimationFrame(decorateHistory);
  }

  function applyGenerationContext(generation) {
    state.latestGeneration = generation || null;
    requestAnimationFrame(decorateResult);
  }

  function hydrateGenerationContext() {
    const context = window.RoxyGenerationContext;
    if (!context) return false;
    applyHistoryContext(context.historyItems || []);
    applyGenerationContext(context.current || null);
    void context.refreshHistory?.();
    void context.refreshResult?.();
    return true;
  }

  function attachGenerationContext() {
    window.addEventListener("roxy:history-context", (event) => {
      applyHistoryContext(event.detail?.items || []);
    });
    window.addEventListener("roxy:generation-context", (event) => {
      applyGenerationContext(event.detail?.generation || null);
    });
    window.addEventListener("roxy:generation-context-ready", hydrateGenerationContext);
    hydrateGenerationContext();
  }

  function actionButton(label, handler, className = "ksu-history-action") {
    const button = el("button", className, label);
    button.type = "button";
    button.addEventListener("click", handler);
    return button;
  }

  function ensureEmptyHistoryCta() {
    const list = document.getElementById("ksuHistoryList");
    if (!list || state.historyItems.length || list.querySelector(".social-history-empty-cta")) return;
    const button = actionButton("Создать контент", () => {
      document.getElementById("ksuHistoryOverlay")?.setAttribute("hidden", "");
      window.RoxyCustomerNavigation?.open?.("create") || document.querySelector('[data-shell-nav="create"]')?.click();
    }, "ksu-history-action social-history-empty-cta");
    list.appendChild(button);
  }

  function decorateHistory() {
    const list = document.getElementById("ksuHistoryList");
    if (!list) return;
    const cards = [...list.querySelectorAll(".ksu-history-card")];
    cards.forEach((card, index) => {
      const generation = state.historyItems[index];
      if (!generation?.id) return;
      card.dataset.generationId = generation.id;
      const actions = card.querySelector(".ksu-history-card-actions");
      if (!actions || actions.querySelector(".social-delete-history")) return;
      const remove = actionButton(
        "Удалить",
        () => confirmHistoryRemoval(generation.id, card),
        "ksu-history-action social-delete-history",
      );
      actions.appendChild(remove);
    });
    ensureEmptyHistoryCta();
  }

  function ensureConfirmDialog() {
    let dialog = document.getElementById("socialHistoryConfirm");
    if (dialog) return dialog;
    dialog = el("dialog", "social-confirm-dialog");
    dialog.id = "socialHistoryConfirm";
    const panel = el("div", "social-confirm-panel");
    panel.append(
      el("h3", "", "Удалить из истории?"),
      el("p", "", "Карточка исчезнет из вашей истории. Финансовая и техническая запись задачи останется на сервере."),
    );
    const actions = el("div", "social-confirm-actions");
    const cancel = actionButton("Отмена", () => dialog.close("cancel"), "social-secondary-button");
    const confirm = actionButton("Удалить", () => dialog.close("confirm"), "social-danger-button");
    actions.append(cancel, confirm);
    panel.appendChild(actions);
    dialog.appendChild(panel);
    document.body.appendChild(dialog);
    return dialog;
  }

  async function askRemovalConfirmation() {
    const dialog = ensureConfirmDialog();
    if (typeof dialog.showModal !== "function") {
      return window.confirm("Удалить контент из истории?");
    }
    return new Promise((resolve) => {
      const onClose = () => {
        dialog.removeEventListener("close", onClose);
        resolve(dialog.returnValue === "confirm");
      };
      dialog.addEventListener("close", onClose);
      dialog.showModal();
    });
  }

  async function confirmHistoryRemoval(generationId, card = null) {
    if (!(await askRemovalConfirmation())) return;
    haptic("medium");
    try {
      await api(`/api/v1/generations/${encodeURIComponent(generationId)}/history`, {
        method: "DELETE",
      });
      state.historyItems = state.historyItems.filter((item) => item.id !== generationId);
      card?.remove();
      ensureEmptyHistoryCta();
      void window.RoxyGenerationContext?.refreshHistory?.();
      notify("success");
      toast("Удалено из истории");
    } catch (error) {
      notify("error");
      toast(error.message || "Не удалось удалить из истории");
    }
  }

  async function loadGenerationSocialState(generationId) {
    return api(`/api/v1/social/generations/${encodeURIComponent(generationId)}`);
  }

  function syncLikeButton(button, social) {
    button.dataset.liked = social.liked_by_me ? "true" : "false";
    const count = Number(social.like_count || 0);
    button.textContent = `${social.liked_by_me ? "♥" : "♡"} ${social.liked_by_me ? "Нравится" : "Поставить лайк"}${count ? ` · ${count}` : ""}`;
    button.setAttribute("aria-pressed", String(Boolean(social.liked_by_me)));
  }

  async function toggleLike(generationId, button) {
    if (button.disabled) return;
    button.disabled = true;
    haptic();
    const liked = button.dataset.liked === "true";
    try {
      const social = await api(`/api/v1/social/generations/${encodeURIComponent(generationId)}/like`, {
        method: liked ? "DELETE" : "POST",
      });
      syncLikeButton(button, social);
      notify("success");
    } catch (error) {
      notify("error");
      toast(error.message || "Не удалось изменить лайк");
    } finally {
      button.disabled = false;
    }
  }

  async function decorateResult() {
    const generation = state.latestGeneration;
    const result = document.getElementById("resultCard");
    if (!generation?.id || !result || result.hidden) return;
    const actions = result.querySelector(".ksu-result-actions");
    if (!actions) return;

    if (!actions.querySelector(".social-delete-result")) {
      actions.appendChild(
        actionButton(
          "Удалить из истории",
          async () => {
            await confirmHistoryRemoval(generation.id);
            window.RoxyCustomerNavigation?.open?.("history") || document.querySelector('[data-shell-nav="history"]')?.click();
          },
          "ksu-history-action social-delete-result",
        ),
      );
    }

    if (generation.status !== "succeeded") return;
    let like = actions.querySelector(".social-like-button");
    if (!like) {
      like = actionButton("♡ Поставить лайк", () => toggleLike(generation.id, like), "ksu-history-action social-like-button");
      like.setAttribute("aria-pressed", "false");
      actions.prepend(like);
    }
    if (like.dataset.socialLoaded === generation.id) return;
    like.dataset.socialLoaded = generation.id;
    try {
      const social = await loadGenerationSocialState(generation.id);
      syncLikeButton(like, social);
    } catch (_error) {
      like.remove();
    }
  }

  function formatSubscriptionName(item) {
    const username = item.username ? ` · @${item.username}` : "";
    return `${item.display_name || "Пользователь"}${username}`;
  }

  function mountProfileSocial() {
    if (state.mountedProfile) return;
    const profileView = document.getElementById("profileView");
    if (!profileView) return;
    state.mountedProfile = true;

    const section = el("section", "home-section social-profile-section");
    const head = el("div", "home-section-head");
    const copy = el("div");
    copy.append(el("span", "section-kicker", "Сообщество"), el("h2", "", "Подписки"));
    head.appendChild(copy);

    const panel = el("div", "shell-panel social-profile-panel");
    const search = el("form", "social-author-search");
    const input = document.createElement("input");
    input.type = "text";
    input.maxLength = 65;
    input.placeholder = "@username автора";
    input.autocomplete = "off";
    input.setAttribute("aria-label", "Telegram username автора");
    const submit = actionButton("Найти", () => {}, "profile-action-button");
    submit.type = "submit";
    search.append(input, submit);

    const message = el("div", "profile-message");
    const target = el("div", "social-profile-target");
    target.hidden = true;
    const listHead = el("div", "social-subscriptions-head");
    listHead.append(el("strong", "", "Мои подписки"));
    const refresh = actionButton("Обновить", () => loadSubscriptions(true), "profile-action-button secondary");
    listHead.appendChild(refresh);
    const list = el("div", "social-subscriptions-list");
    list.setAttribute("aria-live", "polite");

    panel.append(search, message, target, listHead, list);
    section.append(head, panel);
    profileView.appendChild(section);

    Object.assign(profileDom, { section, search, input, submit, message, target, list, refresh });
    search.addEventListener("submit", findAuthor);
    loadSubscriptions(true);

    const requestedAuthor = new URLSearchParams(window.location.search).get("author");
    if (requestedAuthor && /^[0-9a-f-]{36}$/i.test(requestedAuthor)) {
      openProfileById(requestedAuthor);
    }
  }

  const profileDom = {};

  function setProfileMessage(text = "", tone = "") {
    if (!profileDom.message) return;
    profileDom.message.textContent = text;
    profileDom.message.className = `profile-message${tone ? ` ${tone}` : ""}`;
  }

  async function findAuthor(event) {
    event.preventDefault();
    const username = profileDom.input.value.trim().replace(/^@/, "");
    if (!username) {
      setProfileMessage("Введите @username", "error");
      return;
    }
    profileDom.submit.disabled = true;
    setProfileMessage("Ищу публичный профиль…");
    try {
      const profile = await api(`/api/v1/social/profiles?username=${encodeURIComponent(username)}`);
      renderProfileTarget(profile);
      setProfileMessage();
    } catch (error) {
      profileDom.target.hidden = true;
      setProfileMessage(error.status === 404 ? "Публичный профиль не найден" : (error.message || "Ошибка поиска"), "error");
    } finally {
      profileDom.submit.disabled = false;
    }
  }

  async function openProfileById(id) {
    if (!tg?.initData) return;
    try {
      const profile = await api(`/api/v1/social/profiles/${encodeURIComponent(id)}`);
      renderProfileTarget(profile);
    } catch (_error) {
      // Deep-link target can become private; do not leak its existence.
    }
  }

  function renderProfileTarget(profile) {
    state.profileTarget = profile;
    profileDom.target.hidden = false;
    profileDom.target.replaceChildren();
    const title = el("div", "social-profile-title");
    title.append(el("strong", "", profile.display_name || "Пользователь"));
    if (profile.username) title.append(el("small", "", `@${profile.username}`));
    profileDom.target.append(
      title,
      el("small", "", `${Number(profile.follower_count || 0)} подписчиков`),
    );

    if (profile.is_self) {
      profileDom.target.appendChild(
        el("div", "profile-identity-note", profile.profile_discoverable ? "Ваш профиль доступен для точного поиска по @username." : "Ваш профиль приватный. Включите «Публичный профиль» в настройках выше, чтобы другие пользователи могли открыть его."),
      );
      return;
    }

    const button = actionButton(
      profile.subscribed_by_me ? "Отписаться" : "Подписаться",
      () => toggleSubscription(profile.id, button),
      profile.subscribed_by_me ? "profile-action-button secondary" : "profile-action-button",
    );
    button.dataset.subscribed = profile.subscribed_by_me ? "true" : "false";
    profileDom.target.appendChild(button);
  }

  async function toggleSubscription(authorId, button) {
    button.disabled = true;
    const subscribed = button.dataset.subscribed === "true";
    haptic();
    try {
      const profile = await api(`/api/v1/social/profiles/${encodeURIComponent(authorId)}/subscribe`, {
        method: subscribed ? "DELETE" : "POST",
      });
      renderProfileTarget(profile);
      await loadSubscriptions(false);
      notify("success");
    } catch (error) {
      notify("error");
      setProfileMessage(error.message || "Не удалось изменить подписку", "error");
      button.disabled = false;
    }
  }

  async function loadSubscriptions(showLoading = false) {
    if (!profileDom.list || !tg?.initData) return;
    if (showLoading) profileDom.list.replaceChildren(el("div", "shell-skeleton"));
    try {
      const payload = await api("/api/v1/social/subscriptions?limit=50");
      state.subscriptions = Array.isArray(payload?.items) ? payload.items : [];
      renderSubscriptions();
    } catch (error) {
      profileDom.list.replaceChildren(el("div", "profile-empty", error.message || "Не удалось загрузить подписки"));
    }
  }

  function renderSubscriptions() {
    profileDom.list.replaceChildren();
    if (!state.subscriptions.length) {
      profileDom.list.appendChild(el("div", "profile-empty", "Подписок пока нет. Найдите автора по публичному @username."));
      return;
    }
    for (const item of state.subscriptions) {
      const row = el("div", "social-subscription-row");
      const copy = el("div");
      copy.append(el("strong", "", formatSubscriptionName(item)));
      copy.append(el("small", "", item.profile_discoverable ? "Публичный профиль" : "Профиль скрыт"));
      const actions = el("div", "social-subscription-actions");
      if (item.profile_discoverable) {
        actions.appendChild(actionButton("Открыть", () => openProfileById(item.id), "profile-action-button secondary"));
      }
      actions.appendChild(
        actionButton("Отписаться", async () => {
          try {
            await api(`/api/v1/social/profiles/${encodeURIComponent(item.id)}/subscribe`, { method: "DELETE" });
            await loadSubscriptions(false);
            if (state.profileTarget?.id === item.id) await openProfileById(item.id);
            notify("success");
          } catch (error) {
            notify("error");
            setProfileMessage(error.message || "Не удалось отписаться", "error");
          }
        }, "profile-action-button secondary"),
      );
      row.append(copy, actions);
      profileDom.list.appendChild(row);
    }
  }

  mountProfileSocial();
  attachGenerationContext();
  requestAnimationFrame(() => {
    decorateHistory();
    decorateResult();
  });
})();
