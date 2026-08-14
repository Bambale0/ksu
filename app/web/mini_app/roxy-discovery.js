(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    home: null,
    catalogLoaded: false,
    loading: false,
    activePromo: 0,
  };

  const dom = {};

  function authHeaders() {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function api(path) {
    const response = await fetch(path, {
      headers: authHeaders(),
      credentials: "same-origin",
      cache: "no-store",
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
    return payload;
  }

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function button(text, handler, className = "") {
    const node = el("button", className, text);
    node.type = "button";
    node.addEventListener("click", handler);
    return node;
  }

  function haptic(kind = "light") {
    try { tg?.HapticFeedback?.impactOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function openRoute(route) {
    if (route === "catalog") {
      openCatalog();
      return;
    }
    closeCatalog();
    window.RoxyCustomerNavigation?.open?.(route);
  }

  function runAction(action) {
    if (!action || typeof action !== "object") return;
    haptic("light");
    if (action.type === "route") {
      openRoute(action.target || "catalog");
      return;
    }
    if (action.type === "trends") {
      window.location.assign("/mini-app/trends.html");
    }
  }

  function mediaIsVideo(item) {
    const type = String(item?.media?.[0]?.content_type || "");
    if (type.startsWith("video/")) return true;
    return /\.(mp4|webm|mov)(\?|$)/i.test(String(item?.preview_url || item?.result_url || ""));
  }

  function mountHomePromos() {
    const home = document.getElementById("createHome");
    if (!home || document.getElementById("roxyPromoSection")) return;

    const section = el("section", "roxy-promo-section");
    section.id = "roxyPromoSection";
    const viewport = el("div", "roxy-promo-viewport");
    viewport.id = "roxyPromoViewport";
    viewport.setAttribute("aria-live", "polite");
    const dots = el("div", "roxy-promo-dots");
    dots.id = "roxyPromoDots";
    section.append(viewport, dots);

    const cta = document.getElementById("roxyCreateCta");
    const balance = document.getElementById("roxyHomeBalance");
    const anchor = cta || balance || home.querySelector(".hero-card");
    anchor?.insertAdjacentElement("afterend", section);

    dom.promoSection = section;
    dom.promoViewport = viewport;
    dom.promoDots = dots;
    void loadHome();
  }

  function promoCard(slide, index) {
    const card = el("article", "roxy-promo-card");
    card.dataset.promoIndex = String(index);
    if (slide.image_url) {
      card.style.setProperty("--roxy-promo-image", `url("${String(slide.image_url).replaceAll('"', '%22')}")`);
      card.classList.add("has-image");
    }

    const copy = el("div", "roxy-promo-copy");
    copy.append(
      el("span", "section-kicker", slide.eyebrow || "ROXY"),
      el("h2", "", slide.title || "ROXY"),
    );
    if (slide.body) copy.appendChild(el("p", "", slide.body));
    const cta = button(slide.cta || "Открыть", () => runAction(slide.action), "roxy-promo-cta");
    copy.appendChild(cta);
    card.appendChild(copy);
    return card;
  }

  function syncPromoDots() {
    dom.promoDots?.querySelectorAll("button").forEach((dot, index) => {
      const active = index === state.activePromo;
      dot.classList.toggle("is-active", active);
      dot.setAttribute("aria-current", active ? "true" : "false");
    });
  }

  function scrollPromo(index) {
    const cards = [...(dom.promoViewport?.querySelectorAll(".roxy-promo-card") || [])];
    if (!cards.length) return;
    const safe = Math.max(0, Math.min(index, cards.length - 1));
    state.activePromo = safe;
    cards[safe].scrollIntoView({ behavior: "smooth", block: "nearest", inline: "start" });
    syncPromoDots();
  }

  function renderPromos(slides) {
    if (!dom.promoViewport || !dom.promoDots) return;
    const safeSlides = Array.isArray(slides) ? slides : [];
    if (!safeSlides.length) {
      dom.promoSection.hidden = true;
      return;
    }
    dom.promoSection.hidden = false;
    dom.promoViewport.replaceChildren(...safeSlides.map(promoCard));
    dom.promoDots.replaceChildren(...safeSlides.map((slide, index) => {
      const dot = button("", () => scrollPromo(index), "roxy-promo-dot");
      dot.setAttribute("aria-label", `Слайд ${index + 1}: ${slide.title || "ROXY"}`);
      return dot;
    }));
    state.activePromo = 0;
    syncPromoDots();

    let settleTimer = null;
    dom.promoViewport.onscroll = () => {
      window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout(() => {
        const cards = [...dom.promoViewport.querySelectorAll(".roxy-promo-card")];
        if (!cards.length) return;
        const left = dom.promoViewport.scrollLeft;
        let best = 0;
        let distance = Number.POSITIVE_INFINITY;
        cards.forEach((card, index) => {
          const next = Math.abs(card.offsetLeft - left);
          if (next < distance) {
            best = index;
            distance = next;
          }
        });
        state.activePromo = best;
        syncPromoDots();
      }, 80);
    };
  }

  async function loadHome() {
    if (state.loading) return;
    state.loading = true;
    try {
      state.home = await api("/api/v1/discovery/home");
      renderPromos(state.home?.slides || []);
    } catch (_error) {
      if (dom.promoSection) dom.promoSection.hidden = true;
    } finally {
      state.loading = false;
    }
  }

  function catalogShell() {
    const section = el("section", "roxy-catalog-view");
    section.id = "roxyCatalogView";
    section.hidden = true;

    const heading = el("header", "roxy-catalog-heading");
    const copy = el("div");
    copy.append(
      el("span", "section-kicker", "ROXY Discovery"),
      el("h1", "", "Каталог"),
      el("p", "", "Готовые сценарии, тренды и лучшие работы сообщества — начни с идеи, а не с названия модели."),
    );
    heading.appendChild(copy);

    const quick = el("div", "roxy-catalog-quick");
    const trends = button("", () => window.location.assign("/mini-app/trends.html"), "roxy-catalog-quick-card featured");
    trends.append(el("span", "roxy-catalog-icon", "✦"), el("strong", "", "Шаблоны и тренды"), el("small", "", "Готовые recipe для фото и видео"));
    const community = button("", openCommunityFeed, "roxy-catalog-quick-card");
    community.append(el("span", "roxy-catalog-icon", "▦"), el("strong", "", "Лента сообщества"), el("small", "", "Фото и видео пользователей"));
    const tools = button("", () => window.location.assign("/mini-app/prompt-tools.html"), "roxy-catalog-quick-card");
    tools.append(el("span", "roxy-catalog-icon", "✎"), el("strong", "", "Prompt Tools"), el("small", "", "Разбор фото и улучшение промпта"));
    quick.append(trends, community, tools);

    const trendSection = el("section", "roxy-catalog-section");
    const trendHead = el("div", "roxy-catalog-section-head");
    trendHead.append(el("div", "", ""), button("Все тренды", () => window.location.assign("/mini-app/trends.html"), "text-button"));
    trendHead.firstChild.append(el("span", "section-kicker", "Быстрый старт"), el("h2", "", "Популярные шаблоны"));
    const trendGrid = el("div", "roxy-catalog-grid trends");
    trendGrid.id = "roxyCatalogTrends";
    trendSection.append(trendHead, trendGrid);

    const feedSection = el("section", "roxy-catalog-section");
    const feedHead = el("div", "roxy-catalog-section-head");
    feedHead.append(el("div", "", ""), button("Открыть ленту", openCommunityFeed, "text-button"));
    feedHead.firstChild.append(el("span", "section-kicker", "Сообщество"), el("h2", "", "Сейчас в ROXY"));
    const feedGrid = el("div", "roxy-catalog-grid community");
    feedGrid.id = "roxyCatalogCommunity";
    feedSection.append(feedHead, feedGrid);

    section.append(heading, quick, trendSection, feedSection);
    dom.catalog = section;
    dom.trends = trendGrid;
    dom.community = feedGrid;
    return section;
  }

  function mountCatalog() {
    const appMain = document.getElementById("appMain");
    if (!appMain || document.getElementById("roxyCatalogView")) return;
    appMain.appendChild(catalogShell());
  }

  function stateCard(message) {
    return el("div", "roxy-catalog-state", message);
  }

  function trendCard(item) {
    const card = el("article", "roxy-template-card");
    const media = el("div", "roxy-template-media");
    const preview = item?.preview_url || item?.preview_image_url || item?.thumbnail_url;
    if (preview) {
      const image = document.createElement("img");
      image.src = preview;
      image.alt = item?.title || "Шаблон ROXY";
      image.loading = "lazy";
      media.appendChild(image);
    } else {
      media.appendChild(el("span", "roxy-template-placeholder", item?.media_type === "video" ? "▶" : "✦"));
    }
    const copy = el("div", "roxy-template-copy");
    copy.append(el("strong", "", item?.title || "Шаблон"), el("small", "", item?.media_type === "video" ? "Видео" : "Фото"));
    card.append(media, copy);
    card.addEventListener("click", () => window.location.assign("/mini-app/trends.html"));
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") card.click();
    });
    return card;
  }

  function communityCard(item) {
    const card = el("article", "roxy-community-card");
    const url = item?.preview_url || item?.result_url || "";
    if (mediaIsVideo(item)) {
      const video = document.createElement("video");
      video.src = url;
      video.muted = true;
      video.playsInline = true;
      video.preload = "metadata";
      card.appendChild(video);
      card.appendChild(el("span", "roxy-community-video", "▶"));
    } else {
      const image = document.createElement("img");
      image.src = url;
      image.alt = "Работа сообщества ROXY";
      image.loading = "lazy";
      card.appendChild(image);
    }
    const author = el("small", "", item?.author?.display_name || "ROXY creator");
    card.appendChild(author);
    card.addEventListener("click", openCommunityFeed);
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    return card;
  }

  async function loadCatalog() {
    if (state.catalogLoaded) return;
    dom.trends?.replaceChildren(stateCard("Загружаю шаблоны…"));
    dom.community?.replaceChildren(stateCard("Загружаю работы…"));
    const [trends, feed] = await Promise.allSettled([
      api("/api/v1/trends?limit=8"),
      api("/api/v1/feed?sort=top_day&limit=6"),
    ]);

    if (trends.status === "fulfilled") {
      const items = Array.isArray(trends.value?.items) ? trends.value.items : [];
      dom.trends?.replaceChildren(...(items.length ? items.map(trendCard) : [stateCard("Шаблонов пока нет.")]));
    } else {
      dom.trends?.replaceChildren(stateCard("Не удалось загрузить шаблоны."));
    }

    if (feed.status === "fulfilled") {
      const items = Array.isArray(feed.value?.items) ? feed.value.items : [];
      dom.community?.replaceChildren(...(items.length ? items.map(communityCard) : [stateCard("В ленте пока пусто.")]));
    } else {
      dom.community?.replaceChildren(stateCard("Не удалось загрузить ленту."));
    }
    state.catalogLoaded = true;
  }

  function closeCatalog() {
    const catalog = document.getElementById("roxyCatalogView");
    if (catalog) catalog.hidden = true;
    document.body?.classList.remove("roxy-discovery-catalog-open");
  }

  function openCatalog() {
    mountCatalog();
    window.KsuStudioShell?.open?.("home");
    const createView = document.getElementById("createView");
    if (createView) createView.hidden = true;
    if (dom.catalog) dom.catalog.hidden = false;
    document.body?.classList.add("roxy-discovery-catalog-open");
    window.scrollTo({ top: 0, behavior: "auto" });
    void loadCatalog();
  }

  function openCommunityFeed() {
    closeCatalog();
    window.KsuStudioShell?.open?.("feed");
  }

  function init() {
    mountHomePromos();
    mountCatalog();
  }

  window.RoxyDiscovery = Object.freeze({
    openCatalog,
    closeCatalog,
    openCommunityFeed,
    reloadHome: loadHome,
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
