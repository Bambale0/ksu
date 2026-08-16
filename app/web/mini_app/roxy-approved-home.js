(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const LEGACY_BRAND_RE = /\u041a\u0441\u044e|\u041a\u0421\u042e/g;
  let observer = null;
  let queued = false;

  function nav(route) {
    try { tg?.HapticFeedback?.impactOccurred?.(route === "create" ? "medium" : "light"); } catch (_error) { /* optional */ }
    if (window.RoxyCustomerNavigation?.open) {
      window.RoxyCustomerNavigation.open(route);
      return;
    }
    document.querySelector(`[data-roxy-customer-route="${route}"]`)?.click();
  }

  function button(label, className, route) {
    const node = document.createElement("button");
    node.type = "button";
    node.className = className;
    node.textContent = label;
    node.addEventListener("click", () => nav(route));
    return node;
  }

  function ensureHero(home) {
    let hero = document.getElementById("roxyApprovedHero");
    if (!hero) {
      hero = document.createElement("section");
      hero.id = "roxyApprovedHero";
      hero.className = "roxy-approved-hero";
      hero.setAttribute("aria-labelledby", "roxyApprovedHeroTitle");

      const kicker = document.createElement("span");
      kicker.className = "roxy-approved-hero-kicker";
      kicker.textContent = "ROXY · AI CREATIVE STUDIO";

      const title = document.createElement("h1");
      title.id = "roxyApprovedHeroTitle";
      title.append("Создавай. Публикуй.");
      const accent = document.createElement("span");
      accent.textContent = "Зарабатывай.";
      title.appendChild(accent);

      const copy = document.createElement("p");
      copy.textContent = "Генерируй контент, публикуй работы и получай ROX за повторы и активность сообщества.";

      const actions = document.createElement("div");
      actions.className = "roxy-approved-hero-actions";
      actions.append(
        button("✦ Создать", "roxy-approved-hero-primary", "create"),
        button("Каталог", "roxy-approved-hero-secondary", "catalog"),
      );

      hero.append(kicker, title, copy, actions);
    }

    const oldHero = home.querySelector(":scope > .hero-card");
    if (oldHero) oldHero.hidden = true;
    if (home.firstElementChild !== hero) home.prepend(hero);
    return hero;
  }

  function sectionByHeading(home, patterns) {
    const headings = [...home.querySelectorAll("h1,h2,h3,strong")];
    const heading = headings.find((node) => {
      const text = (node.textContent || "").trim().toLowerCase();
      return patterns.some((pattern) => text.includes(pattern));
    });
    if (!heading) return null;
    return heading.closest("section, .home-section, [data-roxy-section]") || heading.parentElement;
  }

  function ensureEarnSection(home) {
    let section = document.getElementById("roxyEarnSection");
    if (!section) {
      section = document.createElement("section");
      section.id = "roxyEarnSection";
      section.className = "roxy-earn-section";
      section.setAttribute("aria-labelledby", "roxyEarnHeading");
      section.innerHTML = `
        <div class="roxy-earn-head">
          <div>
            <span class="section-kicker">Creator economy</span>
            <h2 id="roxyEarnHeading">Как заработать ROX</h2>
          </div>
          <small>Создал → опубликовал → заработал</small>
        </div>
        <div class="roxy-earn-grid">
          <article class="roxy-earn-step">
            <span class="roxy-earn-step-number">01</span>
            <strong>Создай работу</strong>
            <span>Выбери модель, шаблон или начни с собственного промпта.</span>
          </article>
          <article class="roxy-earn-step">
            <span class="roxy-earn-step-number">02</span>
            <strong>Опубликуй</strong>
            <span>Покажи результат сообществу ROXY и дай другим повторить идею.</span>
          </article>
          <article class="roxy-earn-step">
            <span class="roxy-earn-step-number">03</span>
            <strong>Получай ROX</strong>
            <span>ROX начисляются за повторы и активность вокруг твоих работ.</span>
            <span class="roxy-rox-chip">RX · creator rewards</span>
          </article>
        </div>
      `;
    }

    const start = sectionByHeading(home, ["с чего начать"]);
    if (start && start.nextElementSibling !== section) {
      start.insertAdjacentElement("afterend", section);
    } else if (!section.isConnected) {
      document.getElementById("roxyApprovedHero")?.insertAdjacentElement("afterend", section);
    }
    return section;
  }

  function normalizeBalanceNode(node) {
    if (!node) return;
    const raw = (node.textContent || "").trim();
    if (!raw || raw === "—" || raw === "Telegram") return;
    const numeric = raw.match(/-?[\d\s.,]+/u)?.[0]?.trim();
    if (!numeric) return;
    const next = `${numeric} ROX`;
    if (node.textContent !== next) node.textContent = next;
  }

  function normalizeCopyString(value) {
    if (typeof value !== "string" || !value) return value;
    return value
      .replace(LEGACY_BRAND_RE, "ROXY")
      .replace(/(-?[\d\s.,]+)\s*кр\.(?=\s|$|[·,;:)])/giu, "$1 ROX")
      .replace(/(-?[\d\s.,]+)\s+кредит(?:а|ов|ы)?\b/giu, "$1 ROX")
      .replace(/\/\s*кредит\b/giu, "/ ROX");
  }

  function normalizeVisibleCopy(root = document.body) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      const parent = root.parentElement;
      if (!parent || parent.closest("script,style,textarea,option")) return;
      const next = normalizeCopyString(root.nodeValue || "");
      if (next !== root.nodeValue) root.nodeValue = next;
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) return;
    if (root.nodeType === Node.ELEMENT_NODE && root.closest("script,style,textarea")) return;

    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || parent.closest("script,style,textarea,option")) return NodeFilter.FILTER_REJECT;
        const value = node.nodeValue || "";
        return normalizeCopyString(value) !== value ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      const next = normalizeCopyString(node.nodeValue || "");
      if (next !== node.nodeValue) node.nodeValue = next;
    }

    const elements = root.querySelectorAll?.("[aria-label], [title], [placeholder]") || [];
    for (const element of elements) {
      for (const attribute of ["aria-label", "title", "placeholder"]) {
        const value = element.getAttribute(attribute);
        const next = normalizeCopyString(value);
        if (next && next !== value) element.setAttribute(attribute, next);
      }
    }
  }

  function normalizeBalance() {
    normalizeBalanceNode(document.getElementById("balanceValue"));
    normalizeBalanceNode(document.getElementById("walletBalance"));
    normalizeBalanceNode(document.querySelector(".studio-sidebar-balance-value"));
    const walletNote = document.querySelector("#walletHero small");
    if (walletNote && walletNote.textContent !== "Внутренняя валюта ROXY") {
      walletNote.textContent = "Внутренняя валюта ROXY";
    }
  }

  function apply() {
    queued = false;
    document.documentElement.classList.add("roxy-approved-brand");
    document.body?.classList.add("roxy-approved-brand");
    const home = document.getElementById("createHome");
    if (home) {
      ensureHero(home);
      ensureEarnSection(home);
    }
    normalizeBalance();
    normalizeVisibleCopy(document.body);
  }

  function schedule() {
    if (queued) return;
    queued = true;
    window.requestAnimationFrame(apply);
  }

  function init() {
    document.documentElement.classList.add("roxy-approved-brand");
    document.body?.classList.add("roxy-approved-brand");
    apply();
    if (observer || !document.body) return;
    observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    tg?.onEvent?.("activated", schedule);
    window.addEventListener("roxy:route-changed", schedule);
    window.addEventListener("online", schedule);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();