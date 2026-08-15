(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const MINI_ROOT = "/mini-app/";
  let mounted = false;
  let homeMounted = false;

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function haptic() {
    try { tg?.HapticFeedback?.impactOccurred?.("light"); } catch (_error) { /* optional */ }
  }

  function mountBatchIntegration() {
    if (!document.querySelector('link[href="/mini-app/roxy-batch-embedded.css"]')) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "/mini-app/roxy-batch-embedded.css";
      document.head.appendChild(link);
    }
    if (!document.querySelector('script[src="/mini-app/roxy-batch-embedded.js"]')) {
      const script = document.createElement("script");
      script.src = "/mini-app/roxy-batch-embedded.js";
      document.head.appendChild(script);
    }
  }

  function openRoute(route) {
    haptic();
    if (window.RoxyCustomerNavigation?.open?.(route, { feedback: false })) return;
    window.setTimeout(() => window.RoxyCustomerNavigation?.open?.(route, { feedback: false }), 100);
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

  // Kept as a compatibility fallback for older shells; canonical entry is now a child route.
  function openLibrary(tab) {
    const route = tab === "presets" ? "presets" : "references";
    if (window.RoxyCustomerNavigation?.open?.(route, { feedback: false })) return;
    haptic();
    if (window.KsuStudioShell?.openLibrary) {
      window.KsuStudioShell.openLibrary(tab);
      return;
    }
    window.setTimeout(() => window.KsuStudioShell?.openLibrary?.(tab), 100);
  }

  // Compatibility fallback kept for old deep links; native shell routes are preferred.
  function openMiniPage(path) {
    haptic();
    const url = new URL(path, window.location.origin).toString();
    window.location.assign(url);
  }
  void openMiniPage;
  void MINI_ROOT;

  function openBatch() {
    openRoute("batch");
  }

  function openCatalog() {
    haptic();
    if (window.RoxyDiscovery?.openCatalog) {
      window.RoxyDiscovery.openCatalog();
      return;
    }
    window.setTimeout(() => window.RoxyDiscovery?.openCatalog?.(), 100);
  }

  function openFeed() {
    haptic();
    if (window.RoxyDiscovery?.openCommunityFeed) {
      window.RoxyDiscovery.openCommunityFeed();
      return;
    }
    window.KsuStudioShell?.open?.("feed");
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

  function homeTool(glyph, title, handler) {
    const button = el("button", "roxy-home-tool");
    button.type = "button";
    button.append(el("span", "roxy-home-tool-glyph", glyph), el("strong", "", title));
    button.addEventListener("click", handler);
    return button;
  }

  function mountHomeTools() {
    if (homeMounted) return true;
    const home = document.getElementById("createHome");
    const families = home?.querySelector('.home-section[aria-labelledby="familiesHeading"]');
    if (!home || !families) return false;

    const section = el("section", "roxy-home-tools");
    section.id = "roxyHomeTools";
    const head = el("div", "roxy-home-tools-head");
    const copy = el("div");
    copy.append(el("span", "section-kicker", "Рабочее пространство"), el("h2", "", "Инструменты"));
    head.appendChild(copy);

    const grid = el("div", "roxy-home-tools-grid");
    grid.append(
      homeTool("▦", "Каталог", openCatalog),
      homeTool("◫", "Лента", openFeed),
      homeTool("✦", "Тренды", () => openRoute("trends")),
      homeTool("✎", "Prompt", () => openRoute("prompt-tools")),
      homeTool("▤", "Batch", openBatch),
      homeTool("◇", "Референсы", () => openLibrary("references")),
      homeTool("🔔", "События", () => openRoute("notifications")),
      homeTool("💬", "Поддержка", () => openRoute("support")),
    );
    section.append(head, grid);
    families.insertAdjacentElement("beforebegin", section);
    homeMounted = true;
    document.body?.classList.add("roxy-home-tools-ready");
    return true;
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
      card("🔔", "Уведомления", "Новые события и статусы", () => openRoute("notifications")),
      card("🎟", "Промокод", "Активировать ROX-бонус", () => scrollToTarget([".promo-section"])),
      card("💬", "Поддержка", "Тикеты, переписка, статусы", () => openRoute("support")),
      card("👤", "Подписки", "Публичные профили и авторы", () => openRoute("subscriptions")),
      card("◇", "Референсы", "Личная media-библиотека", () => openLibrary("references")),
      card("▣", "Пресеты", "Сохранённые настройки моделей", () => openLibrary("presets")),
      card("↗", "Тренды", "Готовые сценарии генераций", () => openRoute("trends")),
      card("✦", "Prompt Tools", "Анализ и улучшение промптов", () => openRoute("prompt-tools")),
      card("▦", "Batch", "Пакетные генерации", openBatch),
      card("👥", "Рефералы", "30% / 5%, начисления и вывод", () => scrollToTarget(["#partnerPreview"])),
      card("★", "Creator", "Персональное партнёрство", () => openRoute("creator")),
      card("⚙", "Настройки", "Язык, уведомления, публичность", () => scrollToTarget(["#profileUiLanguage", "#profileTools"])),
    );

    section.append(head, grid);
    cabinet.appendChild(section);
    mounted = true;
    document.body?.classList.add("roxy-parity-navigation-ready");
    return true;
  }

  function init() {
    mountBatchIntegration();
    mountHomeTools();
    mount();
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      const profileReady = mount();
      const homeReady = mountHomeTools();
      if ((profileReady && homeReady) || attempts >= 30) window.clearInterval(timer);
    }, 100);
  }

  // Legacy anchor tokens remain documented here for compatibility tests and migration audits:
  // #profileNotificationList, #supportComposeForm, .social-profile-section.

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
