(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const state = {
    token: null,
    me: null,
    models: [],
    trends: [],
    editing: null,
  };

  const ids = [
    "trendAuth", "trendLogin", "trendOtp", "trendRecovery", "trendLoginMessage",
    "trendShell", "trendIdentity", "trendRefresh", "trendLogout", "trendForm",
    "trendId", "trendTitle", "trendDescription", "trendPreviewUrl", "trendModel",
    "trendModelInfo", "trendPrompt", "trendInputMode", "trendReferenceFields",
    "trendMinReferences", "trendMaxReferences", "trendBillingSeconds", "trendSortOrder",
    "trendTags", "trendParameters", "trendKnownFields", "trendActiveRow", "trendActive",
    "trendPreview", "trendFormMessage", "trendSubmit", "trendReset", "trendFormKicker",
    "trendFormTitle", "trendSearch", "trendStatusFilter", "trendList", "trendToast",
  ];
  const dom = Object.fromEntries(ids.map((id) => [id, document.getElementById(id)]));

  const REFERENCE_FIELDS = new Set([
    "image_input", "image_urls", "input_urls", "reference_image_urls", "reference_image",
    "image_url", "first_frame_url", "first_frame",
  ]);
  const SINGLE_REFERENCE_FIELDS = new Set(["image_url", "first_frame_url", "first_frame"]);
  const RESERVED_PARAMETER_FIELDS = new Set(["prompt", "model", "model_id", "kind", "user_input", "count"]);

  function telegramHeaders() {
    return tg?.initData ? { "X-Telegram-Init-Data": tg.initData } : {};
  }

  function detailMessage(payload, fallback) {
    const detail = payload?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      return detail.map((item) => item?.msg || String(item)).filter(Boolean).join("; ") || fallback;
    }
    return fallback;
  }

  async function api(path, options = {}) {
    const { auth = true, telegram = false, ...fetchOptions } = options;
    const headers = { Accept: "application/json", ...(fetchOptions.headers || {}) };
    if (fetchOptions.body !== undefined && !(fetchOptions.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }
    if (auth && state.token) headers.Authorization = `Bearer ${state.token}`;
    if (telegram) Object.assign(headers, telegramHeaders());
    const response = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...fetchOptions,
      headers,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(detailMessage(payload, `HTTP ${response.status}`));
    return payload;
  }

  function uuid() {
    return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function writeHeaders() {
    return {
      "Idempotency-Key": `admin-trend:${uuid()}`,
      "X-Admin-Confirm": "true",
      "X-Request-Id": `trend-ui:${uuid()}`,
    };
  }

  function setMessage(node, message, kind = "") {
    node.textContent = message || "";
    node.classList.remove("error", "ok");
    if (kind) node.classList.add(kind);
  }

  function toast(message) {
    dom.trendToast.textContent = message;
    dom.trendToast.hidden = false;
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => { dom.trendToast.hidden = true; }, 3200);
    try { tg?.HapticFeedback?.notificationOccurred?.("success"); } catch (_error) { /* optional */ }
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function currentModel() {
    return state.models.find((model) => model.id === dom.trendModel.value) || null;
  }

  function modelAcceptsReferences(model) {
    return Boolean(model?.known_fields?.some((field) => REFERENCE_FIELDS.has(field)));
  }

  function modelReferenceCapacity(model) {
    const fields = model?.known_fields || [];
    return fields.some((field) => SINGLE_REFERENCE_FIELDS.has(field)) ? 1 : 8;
  }

  function renderModelInfo() {
    const model = currentModel();
    dom.trendModelInfo.replaceChildren();
    if (!model) {
      dom.trendModelInfo.textContent = "Выберите модель — ROXY покажет её возможности.";
      return;
    }
    dom.trendModelInfo.append(
      el("strong", "", `${model.title} · ${model.media_type === "video" ? "Видео" : "Фото"}`),
      document.createTextNode(`${model.price_rox} ROX${model.price_mode === "per_second" ? " / сек" : ""} · ${model.operation}`),
    );
    if (model.required_fields?.length) {
      dom.trendModelInfo.append(document.createElement("br"), document.createTextNode(`Обязательные поля: ${model.required_fields.join(", ")}`));
    }
    if (model.notes?.length) {
      dom.trendModelInfo.append(document.createElement("br"), document.createTextNode(model.notes.join(" ")));
    }
    dom.trendKnownFields.textContent = model.known_fields?.length
      ? `Поддерживаемые поля: ${model.known_fields.join(", ")}`
      : "У модели нет дополнительных параметров.";

    const imageOption = Array.from(dom.trendInputMode.options).find((option) => option.value === "image");
    if (imageOption) imageOption.disabled = !modelAcceptsReferences(model);
    if (!modelAcceptsReferences(model) && dom.trendInputMode.value === "image") {
      dom.trendInputMode.value = "none";
    }
    syncReferenceFields();
    renderPreview();
  }

  function syncReferenceFields() {
    const wantsImage = dom.trendInputMode.value === "image";
    const model = currentModel();
    const capacity = modelReferenceCapacity(model);
    for (const input of dom.trendReferenceFields.querySelectorAll("input")) input.disabled = !wantsImage;
    if (!wantsImage) {
      dom.trendMinReferences.value = "0";
      dom.trendMaxReferences.value = "0";
    } else {
      const min = Math.max(1, Number(dom.trendMinReferences.value || 1));
      const max = Math.min(capacity, Math.max(min, Number(dom.trendMaxReferences.value || capacity)));
      dom.trendMinReferences.value = String(Math.min(min, capacity));
      dom.trendMaxReferences.value = String(max);
    }
  }

  function renderPreview() {
    dom.trendPreview.replaceChildren();
    const url = dom.trendPreviewUrl.value.trim();
    if (!url) {
      dom.trendPreview.append(el("div", "trend-preview-empty", "Превью появится здесь"));
      return;
    }
    const model = currentModel();
    const mediaType = model?.media_type || (/\.(mp4|webm|mov)(\?|$)/i.test(url) ? "video" : "image");
    const media = document.createElement(mediaType === "video" ? "video" : "img");
    media.src = url;
    if (mediaType === "video") {
      media.controls = true;
      media.muted = true;
      media.playsInline = true;
      media.preload = "metadata";
    } else {
      media.alt = "Превью тренда";
      media.loading = "lazy";
    }
    media.addEventListener("error", () => {
      dom.trendPreview.replaceChildren(el("div", "trend-preview-empty", "Не удалось загрузить превью. Проверьте URL."));
    }, { once: true });
    dom.trendPreview.append(media);
  }

  function populateModels() {
    dom.trendModel.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Выберите модель";
    dom.trendModel.append(placeholder);
    for (const mediaType of ["image", "video"]) {
      const group = document.createElement("optgroup");
      group.label = mediaType === "image" ? "Фото" : "Видео";
      for (const model of state.models.filter((item) => item.media_type === mediaType)) {
        const option = document.createElement("option");
        option.value = model.id;
        option.textContent = `${model.title} · ${model.price_rox} ROX${model.price_mode === "per_second" ? "/сек" : ""}`;
        group.append(option);
      }
      dom.trendModel.append(group);
    }
  }

  function parseParameters() {
    const raw = dom.trendParameters.value.trim() || "{}";
    let parameters;
    try {
      parameters = JSON.parse(raw);
    } catch (_error) {
      throw new Error("Дополнительные настройки должны быть корректным JSON.");
    }
    if (!parameters || Array.isArray(parameters) || typeof parameters !== "object") {
      throw new Error("Parameters JSON должен быть объектом.");
    }
    for (const key of RESERVED_PARAMETER_FIELDS) delete parameters[key];
    return parameters;
  }

  function buildRecipe() {
    const model = currentModel();
    if (!model) throw new Error("Выберите модель тренда.");
    const parameters = parseParameters();
    const billingRaw = dom.trendBillingSeconds.value.trim();
    const tags = dom.trendTags.value.split(",").map((item) => item.trim().toLowerCase()).filter(Boolean).slice(0, 20);
    const recipe = {
      description: dom.trendDescription.value.trim(),
      preview_url: dom.trendPreviewUrl.value.trim(),
      media_type: model.media_type,
      model_id: model.id,
      prompt: dom.trendPrompt.value.trim(),
      parameters,
      input_mode: dom.trendInputMode.value,
      min_references: Number(dom.trendMinReferences.value || 0),
      max_references: Number(dom.trendMaxReferences.value || 0),
      tags,
      sort_order: Number(dom.trendSortOrder.value || 0),
      usage_count: Number(state.editing?.payload?.usage_count || 0),
    };
    if (billingRaw) recipe.billing_seconds = Number(billingRaw);
    return recipe;
  }

  function resetForm() {
    state.editing = null;
    dom.trendForm.reset();
    dom.trendId.value = "";
    dom.trendParameters.value = "{}";
    dom.trendSortOrder.value = "0";
    dom.trendInputMode.value = "none";
    dom.trendMinReferences.value = "0";
    dom.trendMaxReferences.value = "0";
    dom.trendActive.checked = true;
    dom.trendActiveRow.hidden = true;
    dom.trendFormKicker.textContent = "Новый тренд";
    dom.trendFormTitle.textContent = "Добавить тренд";
    dom.trendSubmit.textContent = "Опубликовать тренд";
    setMessage(dom.trendFormMessage, "");
    renderModelInfo();
    renderPreview();
  }

  function fillForm(item, duplicate = false) {
    const payload = item.payload || {};
    state.editing = duplicate ? null : item;
    dom.trendId.value = duplicate ? "" : item.id;
    dom.trendTitle.value = duplicate ? `${item.title} — копия` : item.title;
    dom.trendDescription.value = payload.description || "";
    dom.trendPreviewUrl.value = payload.preview_url || "";
    dom.trendModel.value = payload.model_id || "";
    dom.trendPrompt.value = payload.prompt || "";
    dom.trendInputMode.value = payload.input_mode || "none";
    dom.trendMinReferences.value = String(payload.min_references ?? 0);
    dom.trendMaxReferences.value = String(payload.max_references ?? 0);
    dom.trendBillingSeconds.value = payload.billing_seconds ?? "";
    dom.trendSortOrder.value = String(payload.sort_order ?? 0);
    dom.trendTags.value = Array.isArray(payload.tags) ? payload.tags.join(", ") : "";
    dom.trendParameters.value = JSON.stringify(payload.parameters || {}, null, 2);
    dom.trendActive.checked = item.is_active !== false;
    dom.trendActiveRow.hidden = duplicate;
    dom.trendFormKicker.textContent = duplicate ? "Копия тренда" : "Редактирование";
    dom.trendFormTitle.textContent = duplicate ? "Создать на основе существующего" : item.title;
    dom.trendSubmit.textContent = duplicate ? "Опубликовать копию" : "Сохранить изменения";
    setMessage(dom.trendFormMessage, "");
    renderModelInfo();
    syncReferenceFields();
    renderPreview();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function createMediaPreview(item) {
    const box = el("div", "trend-card-preview");
    const payload = item.payload || {};
    if (!payload.preview_url) {
      box.textContent = "Без превью";
      return box;
    }
    const media = document.createElement(payload.media_type === "video" ? "video" : "img");
    media.src = payload.preview_url;
    if (payload.media_type === "video") {
      media.muted = true;
      media.playsInline = true;
      media.preload = "metadata";
    } else {
      media.alt = "";
      media.loading = "lazy";
    }
    media.addEventListener("error", () => { box.replaceChildren(document.createTextNode("Превью недоступно")); }, { once: true });
    box.append(media);
    return box;
  }

  function actionButton(label, handler, dangerous = false) {
    const button = el("button", `table-action${dangerous ? " trend-danger" : ""}`, label);
    button.type = "button";
    button.addEventListener("click", handler);
    return button;
  }

  function filteredTrends() {
    const query = dom.trendSearch.value.trim().toLowerCase();
    const status = dom.trendStatusFilter.value;
    return state.trends.filter((item) => {
      if (status === "active" && !item.is_active) return false;
      if (status === "inactive" && item.is_active) return false;
      if (!query) return true;
      const payload = item.payload || {};
      return `${item.title} ${payload.model_id || ""} ${(payload.tags || []).join(" ")}`.toLowerCase().includes(query);
    });
  }

  function renderTrends() {
    dom.trendList.replaceChildren();
    const items = filteredTrends();
    if (!items.length) {
      dom.trendList.append(el("div", "trend-empty", state.trends.length ? "Ничего не найдено" : "Трендов пока нет. Создайте первый слева."));
      return;
    }
    for (const item of items) {
      const payload = item.payload || {};
      const card = el("article", `trend-card${item.is_active ? "" : " inactive"}`);
      card.append(createMediaPreview(item));
      const main = el("div", "trend-card-main");
      const head = el("div", "trend-card-head");
      const title = el("div", "trend-card-title");
      title.append(el("strong", "", item.title), el("small", "", payload.model_id || "Модель не указана"));
      head.append(title, el("span", `badge ${item.is_active ? "ok" : "warn"}`, item.is_active ? "Активен" : "Скрыт"));
      main.append(head);

      const meta = el("div", "trend-card-meta");
      meta.append(
        el("span", "trend-tag", payload.media_type === "video" ? "Видео" : "Фото"),
        el("span", "trend-tag", `Приоритет ${payload.sort_order || 0}`),
        el("span", "trend-tag", `${payload.usage_count || 0} запусков`),
      );
      for (const tag of (payload.tags || []).slice(0, 5)) meta.append(el("span", "trend-tag", `#${tag}`));
      main.append(meta);
      if (payload.description) main.append(el("p", "trend-card-description", payload.description));

      const actions = el("div", "trend-card-actions");
      actions.append(
        actionButton("Редактировать", () => fillForm(item)),
        actionButton("Дублировать", () => fillForm(item, true)),
      );
      if (item.is_active) {
        actions.append(actionButton("Скрыть", () => deactivateTrend(item), true));
      } else {
        actions.append(actionButton("Вернуть", () => activateTrend(item)));
      }
      main.append(actions);
      card.append(main);
      dom.trendList.append(card);
    }
  }

  async function loadAll() {
    const [options, trends] = await Promise.all([
      api("/api/v1/admin/trends/options"),
      api("/api/v1/admin/trends"),
    ]);
    state.models = Array.isArray(options.models) ? options.models : [];
    state.trends = Array.isArray(trends.items) ? trends.items : [];
    populateModels();
    if (state.editing) {
      const fresh = state.trends.find((item) => item.id === state.editing.id);
      if (fresh) fillForm(fresh);
    } else {
      renderModelInfo();
    }
    renderTrends();
  }

  async function submitTrend(event) {
    event.preventDefault();
    setMessage(dom.trendFormMessage, "Проверяю сценарий…");
    dom.trendSubmit.disabled = true;
    try {
      const title = dom.trendTitle.value.trim();
      if (!title) throw new Error("Укажите название тренда.");
      const recipe = buildRecipe();
      if (!recipe.preview_url) throw new Error("Добавьте URL превью.");
      if (!recipe.prompt) throw new Error("Добавьте скрытый prompt.");
      if (state.editing) {
        await api(`/api/v1/admin/trends/${state.editing.id}`, {
          method: "PATCH",
          headers: writeHeaders(),
          body: JSON.stringify({ title, payload: recipe, is_active: dom.trendActive.checked }),
        });
        toast("Тренд обновлён");
      } else {
        await api("/api/v1/admin/trends", {
          method: "POST",
          headers: writeHeaders(),
          body: JSON.stringify({ title, payload: recipe }),
        });
        toast("Тренд опубликован");
      }
      resetForm();
      await loadAll();
      setMessage(dom.trendFormMessage, "Готово.", "ok");
    } catch (error) {
      setMessage(dom.trendFormMessage, error.message || "Не удалось сохранить тренд.", "error");
      try { tg?.HapticFeedback?.notificationOccurred?.("error"); } catch (_error) { /* optional */ }
    } finally {
      dom.trendSubmit.disabled = false;
    }
  }

  async function deactivateTrend(item) {
    if (!window.confirm(`Скрыть тренд «${item.title}»? Пользователи больше не увидят его в каталоге.`)) return;
    try {
      await api(`/api/v1/admin/trends/${item.id}`, { method: "DELETE", headers: writeHeaders() });
      toast("Тренд скрыт");
      await loadAll();
    } catch (error) {
      toast(error.message || "Не удалось скрыть тренд");
    }
  }

  async function activateTrend(item) {
    if (!window.confirm(`Вернуть тренд «${item.title}» в каталог?`)) return;
    try {
      await api(`/api/v1/admin/trends/${item.id}/activate`, { method: "POST", headers: writeHeaders() });
      toast("Тренд снова активен");
      await loadAll();
    } catch (error) {
      toast(error.message || "Не удалось вернуть тренд");
    }
  }

  async function login(event) {
    event.preventDefault();
    setMessage(dom.trendLoginMessage, "Проверяю доступ…");
    try {
      const otp = dom.trendOtp.value.trim();
      const recovery = dom.trendRecovery.value.trim();
      const body = {};
      if (otp) body.otp = otp;
      if (recovery) body.recovery_code = recovery;
      const result = await api("/api/v1/admin/auth/login", {
        method: "POST",
        auth: false,
        telegram: true,
        body: JSON.stringify(body),
      });
      state.token = result.token;
      if (result.mfa_setup_required) {
        await api("/api/v1/admin/auth/logout", { method: "POST" }).catch(() => undefined);
        state.token = null;
        throw new Error("Сначала настройте дополнительную защиту в основной админке, затем вернитесь в «Тренды».");
      }
      if (!(result.permissions || []).includes("social.moderate")) {
        await api("/api/v1/admin/auth/logout", { method: "POST" }).catch(() => undefined);
        state.token = null;
        throw new Error("У этого администратора нет права управлять трендами.");
      }
      state.me = await api("/api/v1/admin/auth/me");
      dom.trendIdentity.textContent = state.me.username ? `@${state.me.username}` : state.me.role || "Администратор";
      dom.trendAuth.hidden = true;
      dom.trendShell.hidden = false;
      dom.trendOtp.value = "";
      dom.trendRecovery.value = "";
      await loadAll();
      resetForm();
    } catch (error) {
      setMessage(dom.trendLoginMessage, error.message || "Не удалось войти.", "error");
    }
  }

  async function logout() {
    if (state.token) await api("/api/v1/admin/auth/logout", { method: "POST" }).catch(() => undefined);
    state.token = null;
    state.me = null;
    state.models = [];
    state.trends = [];
    state.editing = null;
    dom.trendShell.hidden = true;
    dom.trendAuth.hidden = false;
    setMessage(dom.trendLoginMessage, "Сессия завершена.", "ok");
  }

  dom.trendLogin.addEventListener("submit", login);
  dom.trendForm.addEventListener("submit", submitTrend);
  dom.trendReset.addEventListener("click", resetForm);
  dom.trendRefresh.addEventListener("click", () => loadAll().catch((error) => toast(error.message || "Не удалось обновить")));
  dom.trendLogout.addEventListener("click", logout);
  dom.trendModel.addEventListener("change", renderModelInfo);
  dom.trendInputMode.addEventListener("change", syncReferenceFields);
  dom.trendPreviewUrl.addEventListener("change", renderPreview);
  dom.trendPreviewUrl.addEventListener("blur", renderPreview);
  dom.trendSearch.addEventListener("input", renderTrends);
  dom.trendStatusFilter.addEventListener("change", renderTrends);

  try {
    tg?.ready?.();
    tg?.expand?.();
  } catch (_error) { /* optional */ }
  resetForm();
})();
