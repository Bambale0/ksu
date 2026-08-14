(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    latestGeneration: null,
    pickerTarget: null,
    references: [],
    referencesLoaded: false,
    decoratingResult: false,
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function button(label, handler, className = "studio-action secondary compact") {
    const node = el("button", className, label);
    node.type = "button";
    node.addEventListener("click", handler);
    return node;
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
      const error = new Error(payload?.detail || payload?.message || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function toast(message) {
    const node = byId("toast");
    if (!node) return;
    node.textContent = message;
    node.hidden = false;
    window.setTimeout(() => {
      if (node.textContent === message) node.hidden = true;
    }, 2800);
  }

  function notify(kind = "success") {
    try {
      tg?.HapticFeedback?.notificationOccurred?.(kind);
    } catch (_error) {
      // Optional Telegram capability.
    }
  }

  function generationRequestInfo(input, init) {
    const raw = typeof input === "string" ? input : input?.url;
    if (!raw) return null;
    let url;
    try {
      url = new URL(raw, window.location.origin);
    } catch (_error) {
      return null;
    }
    if (!url.pathname.startsWith("/api/v1/generations")) return null;
    const method = String(
      init?.method || (typeof input !== "string" ? input?.method : "GET") || "GET",
    ).toUpperCase();
    return { url, method };
  }

  function installGenerationObserver() {
    if (window.__ksuStudioWorkspaceFetchObserver) return;
    window.__ksuStudioWorkspaceFetchObserver = true;
    const previousFetch = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const response = await previousFetch(input, init);
      const info = generationRequestInfo(input, init);
      if (!info || !response.ok) return response;
      response
        .clone()
        .json()
        .then((payload) => {
          const detailMatch = info.url.pathname.match(/^\/api\/v1\/generations\/([0-9a-f-]+)$/i);
          if (info.method === "GET" && detailMatch && payload?.id) {
            state.latestGeneration = payload;
            requestAnimationFrame(decorateResultActions);
            return;
          }
          if (info.method === "POST" && info.url.pathname === "/api/v1/generations" && payload?.id) {
            state.latestGeneration = {
              id: payload.id,
              status: payload.status,
              result_urls: [],
            };
            requestAnimationFrame(decorateResultActions);
          }
        })
        .catch(() => {
          // Progressive enhancement must not affect generation transport.
        });
      return response;
    };
  }

  function resultUrls(generation) {
    if (Array.isArray(generation?.result_urls)) return generation.result_urls.filter(Boolean);
    return generation?.result_url ? [generation.result_url] : [];
  }

  function resultKind(generation, url) {
    const mediaType = String(generation?.model?.media_type || "").toLowerCase();
    if (["image", "video", "audio"].includes(mediaType)) return mediaType;
    if (/\.(mp4|webm|mov|m4v)(\?|$)/i.test(url)) return "video";
    if (/\.(mp3|wav|m4a|ogg|aac)(\?|$)/i.test(url)) return "audio";
    return "image";
  }

  async function publishGeneration(generation, scope, action) {
    if (!generation?.id || action.disabled) return;
    action.disabled = true;
    const original = action.textContent;
    action.textContent = "Публикую…";
    try {
      const payload = await api(`/api/v1/feed/${encodeURIComponent(generation.id)}/publish`, {
        method: "POST",
        body: JSON.stringify({
          publication_scope: scope,
          prompt_visible: false,
          references_visible: false,
        }),
      });
      notify("success");
      const actual = payload?.publication_scope === "feed" ? "ленте" : "профиле";
      action.textContent = payload?.publication_scope === "feed" ? "✓ В ленте" : "✓ В профиле";
      toast(payload?.downgraded_to_profile
        ? "Публикация размещена в профиле по правилам производного контента."
        : `Опубликовано в ${actual}.`);
    } catch (error) {
      notify("error");
      action.textContent = original;
      action.disabled = false;
      toast(error.message || "Не удалось опубликовать результат");
    }
  }

  async function saveResultReference(generation, action) {
    const url = resultUrls(generation)[0];
    if (!url || action.disabled) return;
    action.disabled = true;
    const original = action.textContent;
    action.textContent = "Сохраняю…";
    try {
      await api("/api/v1/references", {
        method: "POST",
        body: JSON.stringify({
          source_url: url,
          kind: resultKind(generation, url),
          label: generation?.model?.title
            ? `${generation.model.title} · результат`
            : "Результат генерации",
        }),
      });
      state.referencesLoaded = false;
      notify("success");
      action.textContent = "✓ В референсах";
      toast("Результат сохранён в библиотеку референсов.");
    } catch (error) {
      notify("error");
      action.textContent = original;
      action.disabled = false;
      toast(error.message || "Не удалось сохранить референс");
    }
  }

  function decorateResultActions() {
    if (state.decoratingResult) return;
    const generation = state.latestGeneration;
    const result = byId("resultCard");
    if (!generation?.id || !result || result.hidden || generation.status !== "succeeded") return;
    const urls = resultUrls(generation);
    if (!urls.length) return;
    const actions = result.querySelector(".ksu-result-actions");
    if (!actions || actions.querySelector(".studio-result-product-actions")) return;

    state.decoratingResult = true;
    try {
      const group = el("div", "studio-result-product-actions");
      const profile = button("В профиль", () => publishGeneration(generation, "profile", profile));
      const feed = button("В ленту", () => publishGeneration(generation, "feed", feed), "studio-action primary compact");
      const reference = button("В референсы", () => saveResultReference(generation, reference));
      group.append(profile, feed, reference);
      actions.appendChild(group);
    } finally {
      state.decoratingResult = false;
    }
  }

  function observeResultCard() {
    const result = byId("resultCard");
    if (!result) return;
    const observer = new MutationObserver(() => requestAnimationFrame(decorateResultActions));
    observer.observe(result, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["hidden"],
    });
  }

  function acceptedKind(row, kind) {
    const input = row.querySelector(".file-input");
    const accept = String(input?.accept || "").toLowerCase();
    if (!accept || accept === "*/*") return true;
    return accept.includes(`${kind}/*`) || accept.includes(`${kind}/`);
  }

  async function loadReferences(force = false) {
    if (state.referencesLoaded && !force) return state.references;
    const payload = await api("/api/v1/references?limit=100");
    state.references = Array.isArray(payload?.items) ? payload.items : [];
    state.referencesLoaded = true;
    return state.references;
  }

  function referencePreview(item) {
    const preview = el("span", "studio-picker-preview");
    if (item.kind === "image") {
      const image = document.createElement("img");
      image.src = item.url;
      image.alt = "";
      image.loading = "lazy";
      preview.appendChild(image);
    } else if (item.kind === "video") {
      preview.textContent = "▶";
    } else {
      preview.textContent = "♪";
    }
    return preview;
  }

  function ensurePicker() {
    let dialog = byId("studioReferencePicker");
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.id = "studioReferencePicker";
    dialog.className = "studio-reference-picker";
    dialog.setAttribute("aria-labelledby", "studioReferencePickerTitle");

    const panel = el("div", "studio-reference-picker-panel");
    const head = el("div", "studio-reference-picker-head");
    const copy = el("div");
    const title = el("h2", "", "Выбрать референс");
    title.id = "studioReferencePickerTitle";
    copy.append(title, el("p", "", "Сохранённые медиа, совместимые с этим полем."));
    const close = button("Закрыть", () => dialog.close(), "studio-action secondary compact");
    head.append(copy, close);
    const list = el("div", "studio-reference-picker-list");
    list.id = "studioReferencePickerList";
    list.setAttribute("aria-live", "polite");
    panel.append(head, list);
    dialog.appendChild(panel);
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    document.body.appendChild(dialog);
    return dialog;
  }

  function applyReferenceToTarget(item) {
    const row = state.pickerTarget;
    const urlInput = row?.querySelector(".upload-url");
    if (!row || !urlInput) return;
    urlInput.value = item.url;
    urlInput.dispatchEvent(new KeyboardEvent("keydown", {
      key: "Enter",
      code: "Enter",
      bubbles: true,
      cancelable: true,
    }));
    ensurePicker().close();
    notify("success");
  }

  async function openReferencePicker(row) {
    state.pickerTarget = row;
    const dialog = ensurePicker();
    const list = byId("studioReferencePickerList");
    list.replaceChildren(el("div", "studio-library-state", "Загружаю референсы…"));
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    try {
      const references = await loadReferences();
      const compatible = references.filter((item) => acceptedKind(row, item.kind));
      list.replaceChildren();
      if (!compatible.length) {
        const empty = el("div", "studio-library-state", "Подходящих референсов пока нет.");
        const openLibrary = button("Открыть библиотеку", () => {
          dialog.close?.();
          window.KsuStudioShell?.openLibrary?.("references");
        }, "studio-action secondary compact");
        empty.appendChild(openLibrary);
        list.appendChild(empty);
        return;
      }
      for (const item of compatible) {
        const choose = button("", () => applyReferenceToTarget(item), "studio-picker-item");
        const copy = el("span", "studio-picker-copy");
        copy.append(
          el("strong", "", item.label || item.filename || "Без названия"),
          el("small", "", item.kind),
        );
        choose.append(referencePreview(item), copy, el("span", "studio-picker-use", "Выбрать"));
        list.appendChild(choose);
      }
    } catch (error) {
      list.replaceChildren(el("div", "studio-library-state error", error.message || "Не удалось загрузить референсы."));
    }
  }

  function decorateUploadRows() {
    document.querySelectorAll("#dynamicForm .upload-row").forEach((row) => {
      if (row.querySelector(".studio-saved-reference-button")) return;
      const open = button(
        "Из библиотеки",
        () => openReferencePicker(row),
        "upload-button studio-saved-reference-button",
      );
      const fileInput = row.querySelector(".file-input");
      if (fileInput) row.insertBefore(open, fileInput);
      else row.appendChild(open);
    });
  }

  function observeDynamicForm() {
    const form = byId("dynamicForm");
    if (!form) return;
    const observer = new MutationObserver(() => requestAnimationFrame(decorateUploadRows));
    observer.observe(form, { childList: true, subtree: true });
    decorateUploadRows();
  }

  function init() {
    installGenerationObserver();
    observeResultCard();
    observeDynamicForm();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();