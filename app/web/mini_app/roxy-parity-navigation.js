(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const MINI_ROOT = "/mini-app/";
  let mounted = false;

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function haptic() {
    try { tg?.HapticFeedback?.impactOccurred?.("light"); } catch (_error) { /* optional */ }
  }

  function openProfile() {
    window.RoxyCustomerNavigation?.open?.("profile", { feedback: false });
    window.KsuStudioShell?.open?.("profile");
  }

  function scrollToTarget(selectors) {
    openProfile();
    let attempt = 0;
    const find = () => {
      for (const selector of selectors) {
        const node = document.querySelector(selector);
        const target = node?.closest?.(".profile-tools-section, .home-section") || node;
        if (target) {
          haptic();
          target.scrollIntoView({ behavior: "smooth", block: "start" });
          return;
        }
      }
      attempt += 1;
      if (attempt <= 24) window.setTimeout(find, 80);
    };
    window.setTimeout(find, 0);
  }

  function openLibrary(tab) {
    haptic();
    if (window.KsuStudioShell?.openLibrary) {
      window.KsuStudioShell.openLibrary(tab);
      return;
    }
    window.setTimeout(() => window.KsuStudioShell?.openLibrary?.(tab), 100);
  }

  function openMiniPage(path) {
    haptic();
    const url = new URL(path, window.location.origin).toString();
    window.location.assign(url);
  }

  function card(glyph, title, note, handler) {
    const button = el("button", "roxy-parity-card");
    button.type = "button";
    button.append(
      el("span", "roxy-parity-glyph", glyph),
      el("span", "roxy-parity-copy"),
      el("span", "roxy-parity-arrow", "›"),
    );
    const copy = button.querySelector(".roxy-parity-copy");
    copy.append(el("strong", "", title), el("small", "", note));
    button.addEventListener("click", handler);
    return button;
  }

  function mount() {
    if (mounted) return true;
    const cabinet = document.getElementById("roxyProfileCabinet");
    if (!cabinet) return false;

    const section = el("section", "roxy-parity-section");
    section.id = "roxyParityNavigation";
    const head = el("div", "roxy-parity-head");
    const copy = el("div");
    copy.append(
      el("span", "section-kicker", "Все возможности"),
      el("h3", "", "Инструменты ROXY"),
      el("p", "", "Весь пользовательский функционал backend доступен из Mini App."),
    );
    head.appendChild(copy);

    const grid = el("div", "roxy-parity-grid");
    grid.append(
      card("🔔", "Уведомления", "Новые события и статусы", () => scrollToTarget(["#profileNotificationList", "#profileTools"])),
      card("🎟", "Промокод", "Активировать ROX-бонус", () => scrollToTarget([".promo-section"])),
      card("💬", "Поддержка", "Тикеты, переписка, статусы", () => scrollToTarget(["#supportComposeForm", "#profileSupportTickets"])),
      card("👤", "Подписки", "Публичные профили и авторы", () => scrollToTarget([".social-profile-section"])),
      card("◇", "Референсы", "Личная media-библиотека", () => openLibrary("references")),
      card("▣", "Пресеты", "Сохранённые настройки моделей", () => openLibrary("presets")),
      card("↗", "Тренды", "Готовые сценарии генераций", () => openMiniPage(`${MINI_ROOT}trends.html`)),
      card("✦", "Prompt Tools", "Анализ и улучшение промптов", () => openMiniPage(`${MINI_ROOT}prompt-tools.html`)),
      card("▦", "Batch", "Пакетные генерации", () => openMiniPage(`${MINI_ROOT}batch.html`)),
      card("👥", "Рефералы", "30% / 5%, начисления и вывод", () => scrollToTarget(["#partnerPreview"])),
      card("★", "Creator", "Персональное партнёрство", () => scrollToTarget(["#creatorPartnershipEntry"])),
      card("⚙", "Настройки", "Язык, уведомления, публичность", () => scrollToTarget(["#profileUiLanguage", "#profileTools"])),
    );

    section.append(head, grid);
    cabinet.appendChild(section);
    mounted = true;
    document.body?.classList.add("roxy-parity-navigation-ready");
    return true;
  }

  function init() {
    if (mount()) return;
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      if (mount() || attempts >= 30) window.clearInterval(timer);
    }, 100);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
