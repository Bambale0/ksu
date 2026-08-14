(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    mounted: false,
    initialized: false,
    loading: null,
  };

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function mountStylesheet() {
    if (document.querySelector('link[href="/mini-app/batch.css"]')) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/mini-app/batch.css";
    document.head.appendChild(link);
  }

  function batchMarkup() {
    const app = el("main", "batch-app roxy-embedded-batch-app");

    const header = el("header", "batch-header roxy-embedded-batch-header");
    const top = el("div", "roxy-embedded-batch-top");
    const heading = el("div");
    heading.append(el("span", "section-kicker", "BATCH"), el("h1", "", "Пакетная обработка"));
    const close = el("button", "roxy-embedded-batch-close", "Закрыть");
    close.type = "button";
    close.addEventListener("click", () => closeBatch({ historyBack: true }));
    top.append(heading, close);
    header.append(top, el("p", "", "Один промпт и настройки — для серии изображений. Цена считается сервером до запуска."));

    const filesCard = el("section", "card batch-card");
    const filesHeading = el("div", "section-heading");
    const filesCopy = el("div");
    filesCopy.append(el("span", "step", "1"), el("h2", "", "Изображения"));
    filesHeading.append(filesCopy, el("strong", "", "0 / 20"));
    filesHeading.lastElementChild.id = "batchCount";
    const files = document.createElement("input");
    files.id = "batchFiles";
    files.type = "file";
    files.accept = "image/*";
    files.multiple = true;
    files.hidden = true;
    const upload = el("button", "upload-button", "Добавить изображения");
    upload.id = "batchUpload";
    upload.type = "button";
    const uploads = el("div", "batch-uploads");
    uploads.id = "batchUploads";
    uploads.setAttribute("aria-live", "polite");
    filesCard.append(filesHeading, files, upload, uploads);

    const settingsCard = el("section", "card batch-card");
    const settingsHeading = el("div", "section-heading");
    const settingsCopy = el("div");
    settingsCopy.append(el("span", "step", "2"), el("h2", "", "Модель и настройки"));
    settingsHeading.appendChild(settingsCopy);
    const modelLabel = el("label", "field-label", "Модель");
    modelLabel.htmlFor = "batchModel";
    const model = document.createElement("select");
    model.id = "batchModel";
    model.className = "input";
    const promptLabel = el("label", "field-label", "Промпт");
    promptLabel.htmlFor = "batchPrompt";
    const prompt = document.createElement("textarea");
    prompt.id = "batchPrompt";
    prompt.className = "textarea";
    prompt.maxLength = 8000;
    prompt.placeholder = "Что изменить во всех изображениях?";
    const fields = el("div", "dynamic-form");
    fields.id = "batchFields";
    settingsCard.append(settingsHeading, modelLabel, model, promptLabel, prompt, fields);

    const summaryCard = el("section", "card batch-card batch-summary");
    const summaryHeading = el("div", "section-heading");
    const summaryCopy = el("div");
    summaryCopy.append(el("span", "step", "3"), el("h2", "", "Проверка и запуск"));
    summaryHeading.appendChild(summaryCopy);
    const quote = el("div", "batch-quote", "Добавьте минимум 2 изображения.");
    quote.id = "batchQuote";
    const message = el("div", "batch-message");
    message.id = "batchMessage";
    message.setAttribute("aria-live", "polite");
    const start = el("button", "primary-button", "Запустить пакет");
    start.id = "batchStart";
    start.type = "button";
    start.disabled = true;
    summaryCard.append(summaryHeading, quote, message, start);

    const progress = el("section", "card batch-card");
    progress.id = "batchProgress";
    progress.hidden = true;
    progress.setAttribute("aria-live", "polite");

    app.append(header, filesCard, settingsCard, summaryCard, progress);
    return app;
  }

  function mount() {
    if (state.mounted) return document.getElementById("roxyEmbeddedBatch");
    const dialog = document.createElement("dialog");
    dialog.id = "roxyEmbeddedBatch";
    dialog.className = "roxy-embedded-batch";
    dialog.setAttribute("aria-labelledby", "roxyEmbeddedBatchTitle");
    const app = batchMarkup();
    app.querySelector("h1").id = "roxyEmbeddedBatchTitle";
    dialog.appendChild(app);
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      closeBatch({ historyBack: true });
    });
    document.body.appendChild(dialog);
    mountStylesheet();
    state.mounted = true;
    return dialog;
  }

  function ensureRuntime() {
    if (state.initialized) return Promise.resolve();
    if (state.loading) return state.loading;
    state.loading = new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-roxy-batch-runtime="true"]');
      if (existing) {
        state.initialized = true;
        resolve();
        return;
      }
      const script = document.createElement("script");
      script.src = "/mini-app/bulk.js";
      script.dataset.roxyBatchRuntime = "true";
      script.onload = () => {
        state.initialized = true;
        resolve();
      };
      script.onerror = () => reject(new Error("Не удалось загрузить Batch runtime"));
      document.head.appendChild(script);
    }).finally(() => {
      state.loading = null;
    });
    return state.loading;
  }

  function open() {
    const dialog = mount();
    if (!dialog.open) {
      dialog.showModal();
      document.body.classList.add("roxy-embedded-batch-open");
      try { tg?.HapticFeedback?.impactOccurred?.("light"); } catch (_error) { /* optional */ }
      if (!history.state?.roxyEmbeddedBatch) {
        history.pushState({ ...(history.state || {}), roxyEmbeddedBatch: true }, "");
      }
    }
    void ensureRuntime().catch((error) => {
      const message = document.getElementById("batchMessage");
      if (message) {
        message.textContent = error.message || "Не удалось открыть пакетную обработку.";
        message.classList.add("is-error");
      }
    });
  }

  function closeNow() {
    const dialog = document.getElementById("roxyEmbeddedBatch");
    if (dialog?.open) dialog.close();
    document.body.classList.remove("roxy-embedded-batch-open");
  }

  function closeBatch({ historyBack = false } = {}) {
    if (historyBack && history.state?.roxyEmbeddedBatch && history.length > 1) {
      history.back();
      return;
    }
    closeNow();
  }

  function onBackButton() {
    const dialog = document.getElementById("roxyEmbeddedBatch");
    if (!dialog?.open) return;
    // Defer the close so other Telegram BackButton handlers see dialog[open] and
    // correctly treat this as a nested surface rather than navigating the whole app.
    window.setTimeout(() => closeBatch({ historyBack: true }), 0);
  }

  function interceptLegacyBatchLinks(event) {
    const anchor = event.target.closest?.('a[href="/mini-app/batch.html"], a[href$="/mini-app/batch.html"]');
    if (!anchor) return;
    event.preventDefault();
    open();
  }

  function init() {
    document.addEventListener("click", interceptLegacyBatchLinks, true);
    window.addEventListener("popstate", () => {
      if (!history.state?.roxyEmbeddedBatch) closeNow();
    });
    tg?.BackButton?.onClick?.(onBackButton);
  }

  window.RoxyBatchEmbedded = Object.freeze({
    open,
    close: () => closeBatch({ historyBack: true }),
    get active() {
      return Boolean(document.getElementById("roxyEmbeddedBatch")?.open);
    },
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
