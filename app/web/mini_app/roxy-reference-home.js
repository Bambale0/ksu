(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = { mounted: false, trendsLoaded: false };

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function button(className, handler) {
    const node = el("button", className);
    node.type = "button";
    node.addEventListener("click", handler);
    return node;
  }

  function haptic(kind = "light") {
    try { tg?.HapticFeedback?.impactOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function openRoute(route) {
    haptic(route === "create" ? "medium" : "light");
    window.RoxyCustomerNavigation?.open?.(route);
  }

  function openStandalone(path) {
    haptic();
    window.location.assign(path);
  }

  function svgIcon(name) {
    const icons = {
      template: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l1.2 4.1L17 8.5l-3.8 1.4L12 14l-1.2-4.1L7 8.5l3.8-1.4L12 3Z"/><path d="M18.5 14l.7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7.7-2.3Z"/></svg>',
      create: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="4"/><path d="M12 8v8M8 12h8"/></svg>',
      trend: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 17l4-4 3 3 6-7"/><path d="M14 9h4v4"/></svg>',
      prompt: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19l3.5-.8L18 8.7 15.3 6 5.8 15.5 5 19Z"/><path d="M13.8 7.5l2.7 2.7"/></svg>',
      batch: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="6" height="6" rx="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><rect x="14" y="14" width="6" height="6" rx="1.5"/></svg>',
      reference: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4h8a3 3 0 0 1 3 3v10a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3Z"/><path d="M7 15l3-3 2.5 2.5L15 12l3 3"/><circle cx="9" cy="9" r="1"/></svg>',
      support: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 6.5A3.5 3.5 0 0 1 8.5 3h7A3.5 3.5 0 0 1 19 6.5v7A3.5 3.5 0 0 1 15.5 17H11l-4.5 3v-3.6A3.5 3.5 0 0 1 5 13.5v-7Z"/><path d="M9 9.5h6M9 12.5h4"/></svg>',
    };
    const wrap = el("span", "roxy-reference-icon");
    wrap.innerHTML = icons[name] || icons.template;
    return wrap;
  }

  function startCard({ icon, eyebrow, title, copy, route, featured = false }) {
    const card = button(`roxy-reference-start-card${featured ? " is-featured" : ""}`, () => openRoute(route));
    card.append(svgIcon(icon));
    const text = el("span", "roxy-reference-start-copy");
    if (eyebrow) text.appendChild(el("small", "roxy-reference-eyebrow", eyebrow));
    text.append(el("strong", "", title), el("span", "", copy));
    const arrow = el("span", "roxy-reference-arrow", "→");
    arrow.setAttribute("aria-hidden", "true");
    card.append(text, arrow);
    return card;
  }

  function toolButton(icon, label, handler) {
    const node = button("roxy-reference-tool", handler);
    node.append(svgIcon(icon), el("span", "", label));
    return node;
  }

  function trendMedia(item) {
    const mediaType = item?.media_type === "video" ? "video" : "image";
    const media = document.createElement(mediaType === "video" ? "video" : "img");
    media.className = "roxy-reference-trend-media";
    media.src = item?.preview_url || "";
    if (mediaType === "video") {
      media.muted = true;
      media.playsInline = true;
      media.preload = "metadata";
    } else {
      media.alt = item?.title || "Шаблон ROXY";
      media.loading = "lazy";
    }
    return media;
  }

  function trendCard(item) {
    const card = button("roxy-reference-trend-card", () => {
      openStandalone(`/mini-app/trends.html?trend=${encodeURIComponent(item.id)}`);
    });
    const mediaWrap = el("span", "roxy-reference-trend-media-wrap");
    mediaWrap.appendChild(trendMedia(item));
    const type = el("span", "roxy-reference-trend-type");
    type.innerHTML = item?.media_type === "video"
      ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 7.5A2.5 2.5 0 0 1 8.5 5h5A2.5 2.5 0 0 1 16 7.5v9a2.5 2.5 0 0 1-2.5 2.5h-5A2.5 2.5 0 0 1 6 16.5v-9Z"/><path d="M16 10l4-2v8l-4-2v-4Z"/></svg>'
      : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 8a2 2 0 0 1 2-2h2l1-2h4l1 2h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V8Z"/><circle cx="12" cy="12" r="3"/></svg>';
    mediaWrap.appendChild(type);
    const title = el("span", "roxy-reference-trend-title", item?.title || "Шаблон");
    card.append(mediaWrap, title);
    return card;
  }

  async function loadTrends() {
    if (state.trendsLoaded || !tg?.initData) return;
    state.trendsLoaded = true;
    const grid = document.getElementById("roxyReferenceTrendGrid");
    const count = document.getElementById("roxyReferenceTrendCount");
    if (!grid) return;
    try {
      const response = await fetch("/api/v1/trends?limit=100", {
        headers: { "X-Telegram-Init-Data": tg.initData, Accept: "application/json" },
        credentials: "same-origin",
        cache: "no-store",
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      const items = Array.isArray(payload?.items) ? payload.items : [];
      if (count) count.textContent = `· ${items.length} шаблонов`;
      const visible = items.slice(0, 6);
      if (!visible.length) {
        grid.replaceChildren(el("div", "roxy-reference-empty", "Шаблоны скоро появятся."));
        return;
      }
      grid.replaceChildren(...visible.map(trendCard));
    } catch (_error) {
      grid.replaceChildren(el("div", "roxy-reference-empty", "Не удалось загрузить подборку."));
    }
  }

  function mount() {
    if (state.mounted) return true;
    const home = document.getElementById("createHome");
    if (!home) return false;

    const root = el("section", "roxy-reference-home");
    root.id = "roxyReferenceHome";

    const start = el("section", "roxy-reference-start");
    const startHead = el("header", "roxy-reference-section-head");
    startHead.append(el("span", "roxy-reference-section-mark"), el("h2", "", "С чего начать"));
    const startStack = el("div", "roxy-reference-start-stack");
    startStack.append(
      startCard({
        icon: "template",
        eyebrow: "ПРОЩЕ ВСЕГО",
        title: "По шаблону",
        copy: "Выбери готовый сценарий и добавь референс",
        route: "catalog",
        featured: true,
      }),
      startCard({
        icon: "create",
        title: "С нуля",
        copy: "Свой промпт, модель и точные настройки",
        route: "create",
      }),
    );
    const trends = startCard({
      icon: "trend",
      eyebrow: "ПОПУЛЯРНОЕ",
      title: "Тренды",
      copy: "Готовые фото- и видео-сценарии сообщества",
      route: "catalog",
      featured: true,
    });
    trends.classList.add("is-wide");
    start.append(startHead, startStack, trends);

    const trendSection = el("section", "roxy-reference-trends");
    const trendHead = el("header", "roxy-reference-list-head");
    const trendTitle = el("div", "roxy-reference-list-title");
    trendTitle.append(svgIcon("trend"), el("h2", "", "Шаблоны"), el("span", "", ""));
    trendTitle.lastChild.id = "roxyReferenceTrendCount";
    const all = button("roxy-reference-all", () => openStandalone("/mini-app/trends.html"));
    all.textContent = "все →";
    trendHead.append(trendTitle, all);
    const trendGrid = el("div", "roxy-reference-trend-grid");
    trendGrid.id = "roxyReferenceTrendGrid";
    trendGrid.appendChild(el("div", "roxy-reference-empty", "Загружаю подборку…"));
    trendSection.append(trendHead, trendGrid);

    const tools = el("section", "roxy-reference-tools");
    const toolsHead = el("header", "roxy-reference-list-head");
    const toolsTitle = el("div", "roxy-reference-list-title");
    toolsTitle.append(svgIcon("prompt"), el("h2", "", "Инструменты"));
    toolsHead.appendChild(toolsTitle);
    const toolsGrid = el("div", "roxy-reference-tools-grid");
    toolsGrid.append(
      toolButton("prompt", "Prompt", () => openStandalone("/mini-app/prompt-tools.html")),
      toolButton("batch", "Batch", () => openStandalone("/mini-app/batch.html")),
      toolButton("reference", "Референсы", () => window.KsuStudioShell?.openLibrary?.("references")),
      toolButton("support", "Поддержка", () => {
        window.RoxyCustomerNavigation?.open?.("profile");
        window.setTimeout(() => document.getElementById("supportComposeForm")?.scrollIntoView({ behavior: "smooth", block: "start" }), 120);
      }),
    );
    tools.append(toolsHead, toolsGrid);

    root.append(start, trendSection, tools);
    home.appendChild(root);
    state.mounted = true;

    const align = () => {
      const promo = document.getElementById("roxyPromoSection");
      const hero = home.querySelector(":scope > .hero-card");
      const anchor = promo || hero;
      if (anchor && root.previousElementSibling !== anchor) anchor.insertAdjacentElement("afterend", root);
    };
    align();
    [100, 300, 800].forEach((delay) => window.setTimeout(align, delay));
    void loadTrends();
    return true;
  }

  function init() {
    if (mount()) return;
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      if (mount() || attempts >= 40) window.clearInterval(timer);
    }, 100);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
