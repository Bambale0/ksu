(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  tg?.ready();
  tg?.expand();

  const initData = tg?.initData || "";
  const tabs = document.getElementById("toolTabs");
  const panel = document.getElementById("toolPanel");
  const result = document.getElementById("toolResult");
  const queryMode = new URLSearchParams(window.location.search).get("mode");

  let mode = queryMode === "prompt" ? "prompt_builder" : "image_analysis";
  let catalog = {};
  let uploadedImageUrl = "";
  let pollToken = 0;
  let requestKey = "";

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("X-Telegram-Init-Data", initData);
    if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
    const response = await fetch(path, { ...options, headers });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(typeof body.detail === "string" ? body.detail : "Запрос не выполнен");
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function toolInfo(id) {
    return catalog[id] || { enabled: false, cost_credits: null, cost_rub: null };
  }

  function renderTabs() {
    clear(tabs);
    [
      ["image_analysis", "🖼 Промпт по фото"],
      ["prompt_builder", "✨ Улучшить промпт"],
    ].forEach(([id, label]) => {
      const button = element("button", `tool-tab${mode === id ? " is-active" : ""}`, label);
      button.type = "button";
      button.addEventListener("click", () => {
        mode = id;
        uploadedImageUrl = "";
        requestKey = "";
        pollToken += 1;
        result.hidden = true;
        renderTabs();
        renderPanel();
      });
      tabs.appendChild(button);
    });
  }

  function addPrice(target, info) {
    if (info.enabled) {
      target.appendChild(element("div", "tool-price", `${info.cost_credits} кр. · ≈ ${info.cost_rub} ₽`));
    } else {
      target.appendChild(element("div", "tool-disabled", "Инструмент временно отключён: цена ещё не опубликована администратором."));
    }
  }

  function uploadField(labelText, optional = false) {
    const label = element("label", "tool-upload");
    label.appendChild(element("strong", "", `${labelText}${optional ? " · необязательно" : ""}`));
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    const status = element("div", "tool-upload-status");
    input.addEventListener("change", async () => {
      uploadedImageUrl = "";
      requestKey = "";
      const file = input.files?.[0];
      if (!file) {
        status.textContent = "";
        return;
      }
      status.textContent = "Загружаю изображение…";
      try {
        const form = new FormData();
        form.append("file", file);
        const uploaded = await api("/api/v1/uploads/kie", { method: "POST", body: form });
        uploadedImageUrl = String(uploaded.url || "");
        status.textContent = uploadedImageUrl ? "Изображение готово." : "Сервис загрузки не вернул URL.";
      } catch (error) {
        status.textContent = error.message || "Не удалось загрузить изображение.";
        status.classList.add("tool-error");
      }
    });
    label.appendChild(input);
    label.appendChild(status);
    return label;
  }

  function renderPanel() {
    clear(panel);
    const info = toolInfo(mode);
    const imageMode = mode === "image_analysis";
    panel.appendChild(element("h2", "", imageMode ? "Разобрать фото" : "Собрать сильный промпт"));
    panel.appendChild(element(
      "p",
      "tool-copy",
      imageMode
        ? "Загрузите изображение — Ксю разберёт композицию, стиль, свет, цвета, ракурс и детали."
        : "Опишите идею своими словами. Можно добавить изображение как визуальный контекст."
    ));
    addPrice(panel, info);

    if (imageMode) {
      panel.appendChild(uploadField("Исходное изображение"));
      const field = element("label", "tool-field");
      field.appendChild(element("span", "", "Что разобрать особенно внимательно · необязательно"));
      const input = document.createElement("textarea");
      input.id = "toolInstruction";
      input.maxLength = 1000;
      input.placeholder = "Например: свет, композицию и стилистику для рекламной съёмки";
      field.appendChild(input);
      panel.appendChild(field);
    } else {
      const field = element("label", "tool-field");
      field.appendChild(element("span", "", "Идея или черновик промпта"));
      const input = document.createElement("textarea");
      input.id = "toolText";
      input.maxLength = 8000;
      input.placeholder = "Например: кинематографичный портрет девушки в дождливом Токио ночью…";
      input.addEventListener("input", () => { requestKey = ""; });
      field.appendChild(input);
      panel.appendChild(field);
      panel.appendChild(uploadField("Визуальный референс", true));
    }

    panel.appendChild(element("div", "tool-status"));
    const submit = element("button", "primary-button tool-submit", imageMode ? "🔎 Анализировать" : "✨ Улучшить промпт");
    submit.type = "button";
    submit.disabled = !info.enabled;
    submit.addEventListener("click", () => submitTool(submit));
    panel.appendChild(submit);
  }

  function setStatus(text, isError = false) {
    const node = panel.querySelector(".tool-status");
    if (!node) return;
    node.textContent = text || "";
    node.classList.toggle("tool-error", isError);
  }

  async function submitTool(button) {
    const imageMode = mode === "image_analysis";
    const text = String(document.getElementById("toolText")?.value || "").trim();
    const instruction = String(document.getElementById("toolInstruction")?.value || "").trim();
    if (imageMode && !uploadedImageUrl) {
      setStatus("Сначала загрузите изображение.", true);
      return;
    }
    if (!imageMode && !text && !uploadedImageUrl) {
      setStatus("Введите идею или добавьте изображение.", true);
      return;
    }

    if (!requestKey) requestKey = crypto.randomUUID();
    button.disabled = true;
    setStatus("Создаю задачу…");
    try {
      const endpoint = imageMode ? "/api/v1/prompt-tools/image-analysis" : "/api/v1/prompt-tools/prompt-builder";
      const body = imageMode
        ? { image_url: uploadedImageUrl, instruction }
        : { text, image_url: uploadedImageUrl || null };
      const task = await api(endpoint, {
        method: "POST",
        headers: { "Idempotency-Key": requestKey },
        body: JSON.stringify(body),
      });
      setStatus(`Задача принята · ${task.cost_credits} кр.`);
      tg?.HapticFeedback?.notificationOccurred("success");
      await pollTask(task.id);
    } catch (error) {
      setStatus(error.status === 409 ? "Недостаточно кредитов или запрос конфликтует с предыдущим." : error.message, true);
      tg?.HapticFeedback?.notificationOccurred("error");
    } finally {
      button.disabled = false;
    }
  }

  async function pollTask(taskId) {
    const token = ++pollToken;
    result.hidden = false;
    clear(result);
    result.appendChild(element("h2", "", "Задача выполняется…"));
    for (let attempt = 0; attempt < 90 && token === pollToken; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, attempt < 8 ? 1200 : 2200));
      let task;
      try {
        task = await api(`/api/v1/prompt-tools/${encodeURIComponent(taskId)}`);
      } catch (error) {
        if (attempt < 3) continue;
        showError(error.message || "Не удалось получить статус задачи.");
        return;
      }
      if (task.status === "failed") {
        showError(task.error || "Анализ не выполнен. Списанные кредиты возвращены.");
        return;
      }
      if (task.status !== "succeeded") continue;
      requestKey = "";
      renderResult(task);
      tg?.HapticFeedback?.notificationOccurred("success");
      return;
    }
  }

  function showError(message) {
    clear(result);
    result.appendChild(element("div", "tool-error", message));
  }

  function addResultBlock(title, value) {
    if (!value || (Array.isArray(value) && !value.length)) return;
    const block = element("div", "tool-result-block");
    block.appendChild(element("h3", "", title));
    if (Array.isArray(value)) {
      const list = element("ul", "tool-result-list");
      value.forEach((item) => list.appendChild(element("li", "", item)));
      block.appendChild(list);
    } else {
      const text = element("p", "", value);
      block.appendChild(text);
      const copy = element("button", "tool-copy-button", "Копировать");
      copy.type = "button";
      copy.addEventListener("click", async () => {
        await navigator.clipboard?.writeText(String(value));
        copy.textContent = "Скопировано ✓";
        window.setTimeout(() => { copy.textContent = "Копировать"; }, 1200);
      });
      block.appendChild(copy);
    }
    result.appendChild(block);
  }

  function renderResult(task) {
    clear(result);
    result.appendChild(element("h2", "", task.tool === "prompt_builder" ? "Готовые промпты ✨" : "Разбор изображения ✨"));
    const data = task.result || {};
    if (task.tool === "prompt_builder") {
      addResultBlock("Русский", data.prompt_ru);
      addResultBlock("English", data.prompt_en);
      return;
    }
    addResultBlock("Кратко", data.summary);
    addResultBlock("Композиция", data.composition);
    addResultBlock("Объекты и персонажи", data.subjects);
    addResultBlock("Стиль", data.style);
    addResultBlock("Свет", data.lighting);
    addResultBlock("Цвета", data.colors);
    addResultBlock("Камера и ракурс", data.camera);
    addResultBlock("Детали", data.details);
    addResultBlock("Что учесть при генерации", data.generation_notes);
  }

  async function load() {
    renderTabs();
    try {
      const payload = await api("/api/v1/prompt-tools");
      catalog = Object.fromEntries((payload.items || []).map((item) => [item.id, item]));
    } catch (error) {
      catalog = {};
      setStatus(error.message || "Не удалось загрузить настройки инструментов.", true);
    }
    renderTabs();
    renderPanel();
  }

  if (!initData) {
    clear(panel);
    panel.appendChild(element("div", "tool-error", "Откройте AI-инструменты внутри Telegram."));
    return;
  }
  load();
})();
