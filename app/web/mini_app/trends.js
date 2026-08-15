(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  tg?.ready();
  tg?.expand();

  const initData = tg?.initData || "";
  const catalog = document.getElementById("trendCatalog");
  const filters = document.getElementById("trendFilters");
  const runner = document.getElementById("trendRunner");
  const result = document.getElementById("trendResult");

  let items = [];
  let activeFilter = "";
  let selected = null;
  let uploadedUrls = [];
  let pollToken = 0;

  const apiHeaders = () => ({
    "X-Telegram-Init-Data": initData,
  });

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("X-Telegram-Init-Data", initData);
    if (options.body && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(path, { ...options, headers });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof body.detail === "string" ? body.detail : "Запрос не выполнен";
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function mediaNode(item, className) {
    const isVideo = item.media_type === "video";
    const node = document.createElement(isVideo ? "video" : "img");
    node.className = className;
    node.src = item.preview_url;
    if (isVideo) {
      node.muted = true;
      node.loop = true;
      node.playsInline = true;
      node.preload = "metadata";
    } else {
      node.alt = item.title || "Trend preview";
      node.loading = "lazy";
    }
    return node;
  }

  function chip(text) {
    return element("span", "trend-chip", text);
  }

  function renderFilters() {
    clear(filters);
    [
      ["", "Все"],
      ["image", "Фото"],
      ["video", "Видео"],
    ].forEach(([value, label]) => {
      const button = element("button", `trend-filter${activeFilter === value ? " is-active" : ""}`, label);
      button.type = "button";
      button.addEventListener("click", () => {
        activeFilter = value;
        renderFilters();
        renderCatalog();
      });
      filters.appendChild(button);
    });
  }

  function renderCatalog() {
    clear(catalog);
    const visible = items.filter((item) => !activeFilter || item.media_type === activeFilter);
    if (!visible.length) {
      catalog.appendChild(element("div", "trend-empty", "Пока нет опубликованных трендов."));
      return;
    }
    visible.forEach((item) => {
      const card = element("button", "trend-card");
      card.type = "button";
      card.appendChild(mediaNode(item, "trend-card-media"));
      const body = element("div", "trend-card-body");
      body.appendChild(element("strong", "", item.title));
      body.appendChild(element("p", "", item.description || "Готовый AI-шаблон"));
      const meta = element("div", "trend-card-meta");
      meta.appendChild(chip(item.media_type === "video" ? "Видео" : "Фото"));
      meta.appendChild(chip(item.model?.title || "AI"));
      meta.appendChild(chip(`${item.cost_credits} кр.`));
      if (item.billing_seconds) meta.appendChild(chip(`${item.billing_seconds} сек.`));
      body.appendChild(meta);
      card.appendChild(body);
      card.addEventListener("click", () => openRunner(item));
      catalog.appendChild(card);
    });
  }

  function setRunnerMessage(text, isError = false) {
    const node = runner.querySelector(".trend-message");
    if (!node) return;
    node.textContent = text || "";
    node.dataset.error = isError ? "1" : "0";
  }

  function referenceSummary() {
    const node = runner.querySelector(".trend-reference-list");
    if (!node) return;
    node.textContent = uploadedUrls.length ? `Загружено: ${uploadedUrls.length}` : "";
  }

  function closeRunner() {
    pollToken += 1;
    selected = null;
    uploadedUrls = [];
    runner.hidden = true;
    clear(runner);
    const url = new URL(window.location.href);
    url.searchParams.delete("trend");
    window.history.replaceState({ ...(window.history.state || {}) }, "", url);
  }

  function openRunner(item) {
    selected = item;
    uploadedUrls = [];
    clear(runner);
    runner.hidden = false;

    const close = element("button", "trend-runner-close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "Закрыть");
    close.addEventListener("click", closeRunner);
    runner.appendChild(close);
    runner.appendChild(mediaNode(item, "trend-runner-preview"));
    runner.appendChild(element("h2", "trend-runner-title", item.title));
    runner.appendChild(element("p", "trend-runner-description", item.description || ""));

    const meta = element("div", "trend-card-meta");
    meta.appendChild(chip(item.model?.title || "AI"));
    meta.appendChild(chip(`${item.cost_credits} кр. · ≈ ${item.cost_rub} ₽`));
    if (item.billing_seconds) meta.appendChild(chip(`${item.billing_seconds} сек.`));
    runner.appendChild(meta);
    runner.appendChild(element("div", "trend-lock-note", "🔒 Prompt и технические настройки шаблона скрыты."));

    const req = item.reference_requirements || { kind: "none", min: 0, max: 0 };
    if (req.kind === "image") {
      const label = element("label", "trend-upload");
      label.appendChild(element("span", "", `Добавьте референсы: ${req.min}–${req.max}`));
      const input = document.createElement("input");
      input.type = "file";
      input.accept = "image/*";
      input.multiple = Number(req.max || 0) > 1;
      input.addEventListener("change", () => uploadReferences(Array.from(input.files || []), req));
      label.appendChild(input);
      runner.appendChild(label);
      runner.appendChild(element("div", "trend-reference-list"));
    }

    runner.appendChild(element("div", "trend-message"));
    const run = element("button", "primary-button trend-run-button", "🔥 Запустить");
    run.type = "button";
    run.addEventListener("click", () => runTrend(run));
    runner.appendChild(run);

    const url = new URL(window.location.href);
    url.searchParams.set("trend", item.id);
    window.history.replaceState({ ...(window.history.state || {}) }, "", url);
    tg?.HapticFeedback?.impactOccurred("light");
  }

  async function uploadReferences(files, req) {
    uploadedUrls = [];
    referenceSummary();
    if (!files.length) return;
    if (files.length > Number(req.max || 0)) {
      setRunnerMessage(`Можно загрузить не больше ${req.max} изображений.`, true);
      return;
    }
    try {
      for (let index = 0; index < files.length; index += 1) {
        setRunnerMessage(`Загрузка ${index + 1}/${files.length}…`);
        const form = new FormData();
        form.append("file", files[index]);
        const uploaded = await api("/api/v1/uploads/kie", { method: "POST", body: form });
        uploadedUrls.push(uploaded.url);
        referenceSummary();
      }
      setRunnerMessage("Референсы готовы.");
    } catch (error) {
      uploadedUrls = [];
      referenceSummary();
      setRunnerMessage(error.message || "Не удалось загрузить референсы.", true);
    }
  }

  async function runTrend(button) {
    if (!selected) return;
    const req = selected.reference_requirements || { kind: "none", min: 0, max: 0 };
    if (uploadedUrls.length < Number(req.min || 0) || uploadedUrls.length > Number(req.max || 0)) {
      setRunnerMessage(`Нужно референсов: ${req.min}–${req.max}.`, true);
      return;
    }
    button.disabled = true;
    setRunnerMessage("Создаю задачу…");
    try {
      const task = await api(`/api/v1/trends/${encodeURIComponent(selected.id)}/run`, {
        method: "POST",
        body: JSON.stringify({ reference_urls: uploadedUrls }),
      });
      setRunnerMessage(`Задача создана · ${task.cost_credits} кр.`);
      tg?.HapticFeedback?.notificationOccurred("success");
      await pollGeneration(task.id);
    } catch (error) {
      const message = error.status === 409 ? "Недостаточно кредитов для запуска." : error.message;
      setRunnerMessage(message || "Не удалось запустить тренд.", true);
      tg?.HapticFeedback?.notificationOccurred("error");
    } finally {
      button.disabled = false;
    }
  }

  async function pollGeneration(generationId) {
    const token = ++pollToken;
    result.hidden = false;
    clear(result);
    result.appendChild(element("strong", "", "Генерация запущена"));
    result.appendChild(element("p", "", "Результат появится здесь автоматически."));

    for (let attempt = 0; attempt < 150 && token === pollToken; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, attempt < 8 ? 1500 : 2500));
      let generation;
      try {
        generation = await api(`/api/v1/generations/${encodeURIComponent(generationId)}`);
      } catch (error) {
        if (attempt < 3) continue;
        clear(result);
        result.appendChild(element("div", "trend-error", error.message || "Не удалось получить статус."));
        return;
      }
      if (generation.status === "failed") {
        clear(result);
        result.appendChild(element("div", "trend-error", generation.error || "Генерация не удалась. Средства будут возвращены автоматически."));
        return;
      }
      if (generation.status !== "succeeded") continue;

      clear(result);
      result.appendChild(element("strong", "", "Готово ✨"));
      const urls = Array.isArray(generation.result_urls) ? generation.result_urls : [];
      const mediaType = generation.model?.media_type;
      urls.forEach((url) => {
        const node = document.createElement(mediaType === "video" ? "video" : "img");
        node.src = url;
        if (mediaType === "video") {
          node.controls = true;
          node.playsInline = true;
        } else {
          node.alt = "Результат генерации";
        }
        result.appendChild(node);
      });
      tg?.HapticFeedback?.notificationOccurred("success");
      return;
    }
  }

  async function load() {
    renderFilters();
    try {
      const payload = await api("/api/v1/trends?limit=100");
      items = Array.isArray(payload.items) ? payload.items : [];
      renderCatalog();
      const requested = new URLSearchParams(window.location.search).get("trend");
      if (requested) {
        const found = items.find((item) => item.id === requested);
        if (found) openRunner(found);
        else {
          try {
            openRunner(await api(`/api/v1/trends/${encodeURIComponent(requested)}`));
          } catch (_error) {
            // Keep the catalog usable when a soft-deactivated/invalid deep link is opened.
          }
        }
      }
    } catch (error) {
      clear(catalog);
      catalog.appendChild(element("div", "trend-error", error.message || "Не удалось загрузить тренды."));
    }
  }

  if (!initData) {
    clear(catalog);
    catalog.appendChild(element("div", "trend-error", "Откройте Тренды внутри Telegram."));
    return;
  }
  load();
})();