(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  tg?.ready(); tg?.expand();
  const initData = tg?.initData || "";
  const INPUT_FIELDS = new Set(["image_url", "image_urls", "image_input", "input_urls"]);
  const dom = {
    files: document.getElementById("batchFiles"), upload: document.getElementById("batchUpload"), uploads: document.getElementById("batchUploads"), count: document.getElementById("batchCount"),
    model: document.getElementById("batchModel"), prompt: document.getElementById("batchPrompt"), fields: document.getElementById("batchFields"), quote: document.getElementById("batchQuote"),
    message: document.getElementById("batchMessage"), start: document.getElementById("batchStart"), progress: document.getElementById("batchProgress"),
  };
  const state = { models: [], model: null, uploads: [], values: {}, billingSeconds: null, quote: null, quoteTimer: null, requestKey: "", pollToken: 0, currentBatchId: null };

  function node(tag, className = "", text = "") { const element = document.createElement(tag); if (className) element.className = className; if (text) element.textContent = text; return element; }
  function clear(element) { while (element.firstChild) element.removeChild(element.firstChild); }
  function setMessage(text = "", error = false) { dom.message.textContent = text; dom.message.classList.toggle("is-error", error); }
  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {}); headers.set("Accept", "application/json"); headers.set("X-Telegram-Init-Data", initData);
    if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
    const response = await fetch(path, { ...options, headers }); const body = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (!response.ok) { const error = new Error(body?.detail || `HTTP ${response.status}`); error.status = response.status; throw error; } return body;
  }
  function supportsBatch(model) { return model.media_type === "image" && (model.known_fields || []).some((name) => INPUT_FIELDS.has(name)); }
  function schema() { return state.model?.ui_schema || {}; }

  function renderUploads() {
    clear(dom.uploads); dom.count.textContent = `${state.uploads.length} / 20`;
    state.uploads.forEach((item, index) => {
      const card = node("div", "batch-upload"); const image = document.createElement("img"); image.src = item.url; image.alt = item.name || `Изображение ${index + 1}`;
      const remove = node("button", "", "×"); remove.type = "button"; remove.addEventListener("click", () => { state.uploads.splice(index, 1); state.requestKey = ""; renderUploads(); scheduleQuote(); });
      card.append(image, remove); dom.uploads.appendChild(card);
    }); dom.upload.disabled = state.uploads.length >= 20;
  }
  async function uploadFiles(files) {
    for (const file of files.slice(0, 20 - state.uploads.length)) {
      setMessage(`Загружаю ${file.name}…`); const form = new FormData(); form.append("file", file, file.name);
      try { const uploaded = await api("/api/v1/uploads/kie", { method: "POST", body: form }); if (uploaded.url && !state.uploads.some((item) => item.url === uploaded.url)) state.uploads.push({ url: uploaded.url, name: uploaded.name || file.name }); }
      catch (error) { setMessage(error.message || "Не удалось загрузить изображение", true); break; }
    }
    state.requestKey = ""; renderUploads(); scheduleQuote();
  }
  function renderModels() { clear(dom.model); state.models.forEach((model) => { const option = node("option", "", model.title); option.value = model.id; dom.model.appendChild(option); }); if (state.model) dom.model.value = state.model.id; }
  function setValue(name, value) { if (value === "" || value === null) delete state.values[name]; else state.values[name] = value; state.requestKey = ""; scheduleQuote(); }

  function renderFields() {
    clear(dom.fields);
    for (const field of schema().fields || []) {
      if (field.name === "prompt" || INPUT_FIELDS.has(field.name) || field.control === "file" || field.control === "files") continue;
      const wrap = node("label", "batch-field"); wrap.appendChild(node("span", "field-label", field.label || field.name)); let input;
      if (field.control === "toggle") { input = document.createElement("input"); input.type = "checkbox"; input.checked = Boolean(state.values[field.name]); input.addEventListener("change", () => setValue(field.name, input.checked)); }
      else if (field.control === "textarea" || field.control === "json") { input = document.createElement("textarea"); input.className = "textarea"; input.value = field.control === "json" && typeof state.values[field.name] === "object" ? JSON.stringify(state.values[field.name], null, 2) : (state.values[field.name] ?? ""); input.addEventListener("input", () => setValue(field.name, input.value)); }
      else {
        input = document.createElement("input"); input.className = "input"; input.type = field.control === "number" ? "number" : "text";
        if (field.min !== undefined) input.min = String(field.min); if (field.max !== undefined) input.max = String(field.max); if (field.step !== undefined) input.step = String(field.step); input.value = state.values[field.name] ?? "";
        if (field.suggestions?.length) { const list = document.createElement("datalist"); list.id = `batch-${field.name}`; field.suggestions.forEach((value) => { const option = document.createElement("option"); option.value = value; list.appendChild(option); }); input.setAttribute("list", list.id); wrap.appendChild(list); }
        input.addEventListener("input", () => setValue(field.name, field.control === "number" && input.value !== "" ? Number(input.value) : input.value));
      }
      wrap.appendChild(input); dom.fields.appendChild(wrap);
    }
    const billing = schema().billing_seconds;
    if (billing) { const wrap = node("label", "batch-field"); wrap.appendChild(node("span", "field-label", billing.label || "Длительность")); const input = document.createElement("input"); input.className = "input"; input.type = "number"; input.min = String(billing.min || 1); input.max = String(billing.max || 600); input.value = state.billingSeconds ?? ""; input.addEventListener("input", () => { state.billingSeconds = input.value === "" ? null : Number(input.value); state.requestKey = ""; scheduleQuote(); }); wrap.appendChild(input); dom.fields.appendChild(wrap); }
  }
  function resetModel() { state.values = { ...(schema().defaults || {}) }; INPUT_FIELDS.forEach((name) => delete state.values[name]); state.billingSeconds = schema().billing_seconds?.default || null; state.quote = null; state.requestKey = ""; renderFields(); scheduleQuote(); }
  function requestPayload() { const parameters = {}; Object.entries(state.values).forEach(([key, value]) => { if (!INPUT_FIELDS.has(key) && value !== null && value !== "") parameters[key] = value; }); return { model_id: state.model?.id || "", prompt: dom.prompt.value.trim(), parameters, billing_seconds: state.billingSeconds, input_urls: state.uploads.map((item) => item.url), reference_ids: [] }; }

  function renderQuote() {
    clear(dom.quote); if (state.uploads.length < 2) dom.quote.textContent = "Добавьте минимум 2 изображения."; else if (!state.quote) dom.quote.textContent = "Рассчитываю стоимость…";
    else dom.quote.append(node("strong", "", `${state.quote.total_cost_credits} кр. · ≈ ${state.quote.total_cost_rub} ₽`), node("div", "", `${state.quote.input_count} изображений · ${state.quote.model.title}`));
    dom.start.disabled = !state.quote || state.uploads.length < 2;
  }
  function scheduleQuote() { clearTimeout(state.quoteTimer); state.quote = null; renderQuote(); if (state.uploads.length < 2 || !state.model) return; state.quoteTimer = setTimeout(loadQuote, 350); }
  async function loadQuote() { try { state.quote = await api("/api/v1/batch-generations/quote", { method: "POST", body: JSON.stringify(requestPayload()) }); setMessage(); } catch (error) { state.quote = null; setMessage(error.message || "Не удалось рассчитать цену", true); } renderQuote(); }

  async function retryFailed(batchId) {
    try {
      const quote = await api(`/api/v1/batch-generations/${encodeURIComponent(batchId)}/retry-quote`);
      if (!quote.failed_count) { setMessage("Ошибок для повтора нет."); return; }
      const ok = window.confirm(`Повторить ${quote.failed_count} неудачных задач за ${quote.total_cost_credits} кр. (≈ ${quote.total_cost_rub} ₽)?`);
      if (!ok) return;
      const batch = await api(`/api/v1/batch-generations/${encodeURIComponent(batchId)}/retry`, { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() } });
      renderProgress(batch); setMessage(`Повтор запущен: ${batch.retried_count} задач.`); await pollBatch(batch.id);
    } catch (error) { setMessage(error.message || "Не удалось повторить ошибки", true); }
  }

  async function hideBatchHistory(batchId, action) {
    if (!batchId || action.disabled) return;
    const ok = window.confirm("Убрать этот пакет из истории? Генерации и списания не удаляются.");
    if (!ok) return;
    action.disabled = true;
    try {
      await api(`/api/v1/batch-generations/${encodeURIComponent(batchId)}/history`, { method: "DELETE" });
      state.pollToken += 1;
      state.currentBatchId = null;
      dom.progress.hidden = true;
      clear(dom.progress);
      setMessage("Пакет убран из истории.");
      tg?.HapticFeedback?.notificationOccurred?.("success");
    } catch (error) {
      action.disabled = false;
      setMessage(error.message || "Не удалось убрать пакет из истории", true);
      tg?.HapticFeedback?.notificationOccurred?.("error");
    }
  }

  function renderProgress(batch) {
    state.currentBatchId = batch.id;
    dom.progress.hidden = false; clear(dom.progress);
    const head = node("div", "batch-progress-head"); head.append(node("h2", "", `Пакет · ${batch.progress_percent}%`), node("span", "", `${batch.succeeded_count}/${batch.input_count}`)); dom.progress.appendChild(head);
    const bar = node("div", "batch-progress-bar"); const fill = node("span"); fill.style.width = `${batch.progress_percent}%`; bar.appendChild(fill); dom.progress.appendChild(bar);
    const results = node("div", "batch-results");
    (batch.items || []).forEach((item) => { const row = node("div", "batch-result"); row.append(node("strong", "", String(item.ordinal + 1)), node("span", "", item.generation.status)); const action = node("a", "", item.generation.result_url ? "Открыть" : "—"); if (item.generation.result_url) { action.href = item.generation.result_url; action.target = "_blank"; action.rel = "noopener noreferrer"; } row.appendChild(action); results.appendChild(row); }); dom.progress.appendChild(results);
    if (batch.status !== "running") {
      const actions = node("div", "batch-progress-actions");
      if (batch.failed_count > 0) { const retry = node("button", "upload-button batch-retry", `Повторить ошибки · ${batch.failed_count}`); retry.type = "button"; retry.addEventListener("click", () => retryFailed(batch.id)); actions.appendChild(retry); }
      const hide = node("button", "upload-button batch-history-hide", "Убрать из истории"); hide.type = "button"; hide.addEventListener("click", () => hideBatchHistory(batch.id, hide)); actions.appendChild(hide);
      dom.progress.appendChild(actions);
    }
  }
  async function pollBatch(batchId) {
    const token = ++state.pollToken;
    for (let attempt = 0; attempt < 180 && token === state.pollToken; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, attempt < 10 ? 1500 : 3000));
      try { const batch = await api(`/api/v1/batch-generations/${encodeURIComponent(batchId)}`); renderProgress(batch); if (batch.status !== "running") { state.requestKey = ""; setMessage(batch.status === "succeeded" ? "Пакет готов." : `Готово с ошибками: ${batch.failed_count}`); return; } }
      catch (error) { if (attempt > 3) { setMessage(error.message || "Не удалось получить статус", true); return; } }
    }
  }
  async function startBatch() {
    if (!state.quote) return; if (!state.requestKey) state.requestKey = crypto.randomUUID(); dom.start.disabled = true; setMessage("Создаю пакет…");
    try { const batch = await api("/api/v1/batch-generations", { method: "POST", headers: { "Idempotency-Key": state.requestKey }, body: JSON.stringify(requestPayload()) }); tg?.HapticFeedback?.notificationOccurred?.("success"); renderProgress(batch); await pollBatch(batch.id); }
    catch (error) { setMessage(error.message || "Не удалось запустить пакет", true); tg?.HapticFeedback?.notificationOccurred?.("error"); dom.start.disabled = false; }
  }

  async function load() {
    if (!initData) { setMessage("Откройте пакетную обработку внутри Telegram.", true); return; }
    try { const catalog = await api("/api/v1/generations/models"); state.models = (catalog.models || []).filter(supportsBatch); state.model = state.models[0] || null; renderModels(); resetModel(); renderUploads(); if (!state.model) setMessage("Нет доступных image-to-image моделей.", true); }
    catch (error) { setMessage(error.message || "Не удалось загрузить модели", true); }
  }

  dom.upload.addEventListener("click", () => dom.files.click()); dom.files.addEventListener("change", async () => { await uploadFiles([...(dom.files.files || [])]); dom.files.value = ""; });
  dom.model.addEventListener("change", () => { state.model = state.models.find((model) => model.id === dom.model.value) || null; resetModel(); }); dom.prompt.addEventListener("input", () => { state.requestKey = ""; scheduleQuote(); }); dom.start.addEventListener("click", startBatch);
  load();
})();
