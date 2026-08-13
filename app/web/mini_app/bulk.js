(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  tg?.ready();
  tg?.expand();
  const initData = tg?.initData || "";
  const INPUT_FIELDS = new Set(["image_url", "image_urls", "image_input", "input_urls"]);
  const dom = {
    files: document.getElementById("batchFiles"),
    upload: document.getElementById("batchUpload"),
    uploads: document.getElementById("batchUploads"),
    count: document.getElementById("batchCount"),
    model: document.getElementById("batchModel"),
    prompt: document.getElementById("batchPrompt"),
    fields: document.getElementById("batchFields"),
    quote: document.getElementById("batchQuote"),
    message: document.getElementById("batchMessage"),
    start: document.getElementById("batchStart"),
    progress: document.getElementById("batchProgress"),
  };
  const state = {
    models: [], model: null, uploads: [], values: {}, billingSeconds: null,
    quote: null, quoteTimer: null, requestKey: "", pollToken: 0,
  };

  function node(tag, className = "", text = "") {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  }
  function clear(element) { while (element.firstChild) element.removeChild(element.firstChild); }
  function setMessage(text = "", error = false) {
    dom.message.textContent = text;
    dom.message.classList.toggle("is-error", error);
  }
  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    headers.set("X-Telegram-Init-Data", initData);
    if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
    const response = await fetch(path, { ...options, headers });
    const body = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(body?.detail || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return body;
  }
  function supportsBatch(model) {
    return model.media_type === "image" && (model.known_fields || []).some((name) => INPUT_FIELDS.has(name));
  }
  function schema() { return state.model?.ui_schema || {}; }

  function renderUploads() {
    clear(dom.uploads);
    dom.count.textContent = `${state.uploads.length} / 20`;
    state.uploads.forEach((item, index) => {
      const card = node("div", "batch-upload");
      const image = document.createElement("img");
      image.src = item.url;
      image.alt = item.name || `Изображение ${index + 1}`;
      const remove = node("button", "", "×");
      remove.type = "button";
      remove.addEventListener("click", () => {
        state.uploads.splice(index, 1);
        state.requestKey = "";
        renderUploads();
        scheduleQuote();
      });
      card.append(image, remove);
      dom.uploads.appendChild(card);
    });
    dom.upload.disabled = state.uploads.length >= 20;
  }

  async function uploadFiles(files) {
    for (const file of files.slice(0, 20 - state.uploads.length)) {
      setMessage(`Загружаю ${file.name}…`);
      const form = new FormData();
      form.append("file", file, file.name);
      try {
        const uploaded = await api("/api/v1/uploads/kie", { method: "POST", body: form });
        if (uploaded.url && !state.uploads.some((item) => item.url === uploaded.url)) {
          state.uploads.push({ url: uploaded.url, name: uploaded.name || file.name });
        }
      } catch (error) {
        setMessage(error.message || "Не удалось загрузить изображение", true);
        break;
      }
    }
    state.requestKey = "";
    renderUploads();
    scheduleQuote();
  }

  dom.upload.addEventListener("click", () => dom.files.click());
  dom.files.addEventListener("change", async () => {
    await uploadFiles([...(dom.files.files || [])]);
    dom.files.value = "";
  });
})();
