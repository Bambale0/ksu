(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const profileView = document.getElementById("profileView");
  const partnerMount = document.getElementById("partnerPreview");
  if (!profileView || !partnerMount) return;

  const statusMount = document.createElement("section");
  statusMount.className = "partner-approval-banner shell-panel";
  statusMount.hidden = true;
  partnerMount.parentNode?.insertBefore(statusMount, partnerMount);

  let current = null;
  let submitting = false;

  function headers(json = false) {
    const result = { Accept: "application/json" };
    if (tg?.initData) result["X-Telegram-Init-Data"] = tg.initData;
    if (json) result["Content-Type"] = "application/json";
    return result;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { ...headers(Boolean(options.body)), ...(options.headers || {}) },
      credentials: "same-origin",
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    return payload;
  }

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function applyGate() {
    const approved = current?.status === "approved";
    partnerMount.querySelectorAll(".partner-withdrawal-form input, .partner-withdrawal-form textarea, .partner-withdrawal-form button").forEach((node) => {
      node.disabled = !approved;
    });
  }

  function render() {
    statusMount.replaceChildren();
    if (!current || current.status === "approved") {
      statusMount.hidden = true;
      applyGate();
      return;
    }
    statusMount.hidden = false;
    const title = el("h3", "", "Партнёрская программа");
    statusMount.appendChild(title);

    if (current.status === "pending") {
      statusMount.append(
        el("strong", "", "Заявка отправлена"),
        el("p", "", "Мы проверяем заявку. Реферальная статистика доступна, вывод откроется после одобрения."),
      );
    } else if (current.status === "suspended") {
      statusMount.append(
        el("strong", "", "Партнёрский статус приостановлен"),
        el("p", "", current.decision_reason || "Вывод временно недоступен. Обратитесь в поддержку, если нужен пересмотр."),
      );
    } else {
      statusMount.appendChild(
        el(
          "p",
          "",
          current.status === "rejected"
            ? (current.decision_reason || "Предыдущая заявка отклонена. Можно отправить её повторно после исправления данных.")
            : "Чтобы получать партнёрские выплаты, примите условия программы и отправьте заявку на проверку.",
        ),
      );
      const consent = el("label", "partner-consent");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      consent.append(checkbox, document.createTextNode(` Принимаю условия партнёрской программы · версия ${current.terms_version || "1"}`));
      const submit = el("button", "primary", current.status === "rejected" ? "Отправить повторно" : "Стать партнёром");
      submit.type = "button";
      submit.disabled = true;
      checkbox.addEventListener("change", () => { submit.disabled = !checkbox.checked || submitting; });
      submit.addEventListener("click", async () => {
        if (!checkbox.checked || submitting) return;
        submitting = true;
        submit.disabled = true;
        submit.textContent = "Отправляем…";
        try {
          current = await api("/api/v1/partner-approval", {
            method: "POST",
            body: JSON.stringify({ accepted: true }),
          });
          tg?.HapticFeedback?.notificationOccurred?.("success");
          render();
        } catch (error) {
          statusMount.appendChild(el("div", "partner-validation error", error.message || "Не удалось отправить заявку."));
        } finally {
          submitting = false;
        }
      });
      statusMount.append(consent, submit);
    }
    applyGate();
  }

  async function load() {
    if (!tg?.initData) return;
    try {
      current = await api("/api/v1/partner-approval");
    } catch (_error) {
      current = null;
    }
    render();
  }

  const cabinetObserver = new MutationObserver(applyGate);
  cabinetObserver.observe(partnerMount, { childList: true, subtree: true });
  const profileObserver = new MutationObserver(() => {
    if (!profileView.hidden) load();
  });
  profileObserver.observe(profileView, { attributes: true, attributeFilter: ["hidden"] });
  tg?.onEvent?.("activated", () => { if (!profileView.hidden) load(); });
  if (!profileView.hidden) load();
})();
