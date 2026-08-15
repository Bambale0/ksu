(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    observer: null,
    loading: false,
    items: [],
    dialog: null,
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
    const body = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) {
      const detail = body?.detail;
      throw new Error(typeof detail === "string" ? detail : `HTTP ${response.status}`);
    }
    return body;
  }

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function button(label, className = "studio-action secondary compact") {
    const node = el("button", className, label);
    node.type = "button";
    return node;
  }

  function notify(kind) {
    try { tg?.HapticFeedback?.notificationOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function field(label, control) {
    const wrap = el("label", "studio-library-field");
    wrap.append(el("span", "", label), control);
    return wrap;
  }

  function textInput(value = "") {
    const input = document.createElement("input");
    input.className = "input";
    input.type = "text";
    input.value = value;
    return input;
  }

  function ensureDialog() {
    if (state.dialog) return state.dialog;
    const dialog = el("dialog", "social-confirm-dialog roxy-preset-editor-dialog");
    dialog.id = "roxyPresetEditorDialog";
    const panel = el("form", "social-confirm-panel roxy-preset-editor-panel");
    panel.method = "dialog";
    panel.append(el("h3", "", "Редактировать пресет"));

    const name = textInput();
    name.required = true;
    name.maxLength = 80;
    const model = textInput();
    model.readOnly = true;
    const prompt = document.createElement("textarea");
    prompt.className = "input";
    prompt.maxLength = 8000;
    const billing = document.createElement("input");
    billing.className = "input";
    billing.type = "number";
    billing.min = "1";
    billing.placeholder = "Не задано";
    const parameters = document.createElement("textarea");
    parameters.className = "input";
    parameters.rows = 6;
    parameters.spellcheck = false;
    const references = document.createElement("textarea");
    references.className = "input";
    references.rows = 3;
    references.spellcheck = false;
    const message = el("div", "studio-library-message");

    panel.append(
      field("Название", name),
      field("Модель", model),
      field("Prompt", prompt),
      field("Длительность / billing seconds", billing),
      field("Параметры · JSON object", parameters),
      field("Reference IDs · JSON array", references),
      message,
    );

    const actions = el("div", "social-confirm-actions");
    const cancel = button("Отмена", "studio-action secondary");
    const save = button("Сохранить изменения", "studio-action primary");
    cancel.addEventListener("click", () => dialog.close("cancel"));
    actions.append(cancel, save);
    panel.appendChild(actions);
    dialog.appendChild(panel);
    document.body.appendChild(dialog);

    Object.assign(dialog, {
      presetFields: { name, model, prompt, billing, parameters, references, message, save },
      presetItem: null,
    });
    save.addEventListener("click", () => savePreset(dialog));
    state.dialog = dialog;
    return dialog;
  }

  function openEditor(item) {
    const dialog = ensureDialog();
    const fields = dialog.presetFields;
    dialog.presetItem = item;
    fields.name.value = item.name || "";
    fields.model.value = item.model_id || "";
    fields.prompt.value = item.prompt || "";
    fields.billing.value = item.billing_seconds == null ? "" : String(item.billing_seconds);
    fields.parameters.value = JSON.stringify(item.parameters || {}, null, 2);
    fields.references.value = JSON.stringify(item.reference_ids || [], null, 2);
    fields.message.textContent = "";
    fields.save.disabled = false;
    try {
      dialog.showModal();
    } catch (_error) {
      dialog.setAttribute("open", "");
    }
  }

  async function savePreset(dialog) {
    const item = dialog.presetItem;
    const fields = dialog.presetFields;
    if (!item?.id || fields.save.disabled) return;

    let parameters;
    let referenceIds;
    try {
      parameters = JSON.parse(fields.parameters.value || "{}");
      referenceIds = JSON.parse(fields.references.value || "[]");
      if (!parameters || Array.isArray(parameters) || typeof parameters !== "object") {
        throw new Error("Параметры должны быть JSON object");
      }
      if (!Array.isArray(referenceIds)) throw new Error("Reference IDs должны быть JSON array");
    } catch (error) {
      fields.message.textContent = error.message || "Проверьте JSON.";
      return;
    }

    const name = fields.name.value.trim();
    if (!name) {
      fields.message.textContent = "Введите название пресета.";
      return;
    }

    const billingRaw = fields.billing.value.trim();
    const billingSeconds = billingRaw ? Number(billingRaw) : null;
    if (billingSeconds !== null && (!Number.isInteger(billingSeconds) || billingSeconds < 1)) {
      fields.message.textContent = "Длительность должна быть целым числом больше нуля.";
      return;
    }

    fields.save.disabled = true;
    fields.message.textContent = "Сохраняю…";
    try {
      await api(`/api/v1/presets/${encodeURIComponent(item.id)}`, {
        method: "PUT",
        body: JSON.stringify({
          name,
          model_id: item.model_id,
          prompt: fields.prompt.value,
          parameters,
          reference_ids: referenceIds,
          billing_seconds: billingSeconds,
        }),
      });
      notify("success");
      dialog.close("saved");
      window.KsuStudioShell?.openLibrary?.("presets");
    } catch (error) {
      notify("error");
      fields.message.textContent = error.message || "Не удалось обновить пресет.";
    } finally {
      fields.save.disabled = false;
    }
  }

  async function loadAndDecorate(body) {
    if (!tg?.initData || state.loading) return;
    const cards = [...body.querySelectorAll(".studio-library-card.preset")];
    if (!cards.length) return;
    if (cards.every((card) => card.dataset.presetEditorBound === "true")) return;

    state.loading = true;
    try {
      const payload = await api("/api/v1/presets");
      state.items = Array.isArray(payload?.items) ? payload.items : [];
      cards.forEach((card, index) => {
        if (card.dataset.presetEditorBound === "true") return;
        const item = state.items[index];
        if (!item?.id) return;
        const actions = card.querySelector(".studio-library-card-actions");
        if (!actions) return;
        const edit = button("Редактировать");
        edit.classList.add("roxy-preset-edit");
        edit.addEventListener("click", () => openEditor(item));
        actions.insertBefore(edit, actions.lastElementChild || null);
        card.dataset.presetEditorBound = "true";
        card.dataset.presetId = item.id;
      });
    } catch (_error) {
      // Existing preset UI remains usable if the progressive editor cannot load.
    } finally {
      state.loading = false;
    }
  }

  function attach(body) {
    if (state.observer) return;
    state.observer = new MutationObserver(() => {
      window.requestAnimationFrame(() => void loadAndDecorate(body));
    });
    state.observer.observe(body, { childList: true, subtree: true });
    void loadAndDecorate(body);
  }

  function init() {
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      const body = document.getElementById("studioLibraryBody");
      if (body) {
        window.clearInterval(timer);
        attach(body);
      } else if (attempts >= 60) {
        window.clearInterval(timer);
      }
    }, 100);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
