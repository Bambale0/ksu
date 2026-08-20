(() => {
  "use strict";

  const STORAGE_PREFIX = "roxy-model-family-choice-v1:";
  const CENTER_ID = "roxyCreateCenterView";
  let observedCenter = null;
  let centerObserver = null;
  let scanScheduled = false;

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function button(label, handler, className = "") {
    const node = el("button", className, label);
    node.type = "button";
    node.addEventListener("click", handler);
    return node;
  }

  function haptic() {
    try { window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.(); } catch (_error) { /* optional */ }
  }

  function slug(value) {
    return String(value || "roxy")
      .toLocaleLowerCase("en-US")
      .replace(/[^a-z0-9а-яё]+/gi, "-")
      .replace(/^-+|-+$/g, "") || "roxy";
  }

  function pluralRu(value, one, few, many) {
    const n = Math.abs(Number(value)) % 100;
    const tail = n % 10;
    if (n > 10 && n < 20) return many;
    if (tail === 1) return one;
    if (tail >= 2 && tail <= 4) return few;
    return many;
  }

  function currentMediaType(center) {
    const kicker = center.querySelector(".roxy-flow-topbar .section-kicker")?.textContent || "";
    return /видео/i.test(kicker) ? "video" : "image";
  }

  function productInfo(card) {
    const title = (card.querySelector(".roxy-flow-model-title strong")?.textContent || "").trim();
    const family = (card.querySelector(".roxy-flow-model-title small")?.textContent || title || "ROXY").trim();
    return {
      card,
      productId: card.dataset.productId || title,
      title: title || family,
      family,
    };
  }

  function versionLabel(family, title) {
    const familyText = String(family || "").trim();
    const titleText = String(title || "").trim();
    if (!titleText || titleText.localeCompare(familyText, undefined, { sensitivity: "accent" }) === 0) return "Base";
    const escaped = familyText.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const stripped = titleText.replace(new RegExp(`^${escaped}(?:\\s+|\\s*[·:\-]\\s*)?`, "i"), "").trim();
    return stripped || "Base";
  }

  function storageKey(mediaType, family) {
    return `${STORAGE_PREFIX}${mediaType}:${slug(family)}`;
  }

  function rememberedItem(items, mediaType, family) {
    const remembered = localStorage.getItem(storageKey(mediaType, family));
    return items.find((item) => item.productId === remembered) || items[0];
  }

  function cloneSingleton(item) {
    const clone = item.card.cloneNode(true);
    clone.removeAttribute("data-roxy-family-source");
    clone.addEventListener("click", () => item.card.click());
    return clone;
  }

  function familyCard(items, mediaType) {
    const family = items[0].family;
    let selected = rememberedItem(items, mediaType, family);
    const card = el("article", "roxy-flow-model-card roxy-flow-family-card");
    card.dataset.family = family;

    const open = button("", () => selected.card.click(), "roxy-flow-family-open");
    const pickerBlock = el("div", "roxy-flow-version-block");
    const pickerLabel = el("span", "roxy-flow-version-label", "Версия");
    const picker = el("div", "roxy-flow-version-picker");
    picker.setAttribute("role", "radiogroup");
    picker.setAttribute("aria-label", `Версия ${family}`);
    if (items.length > 5) picker.classList.add("is-scrollable");
    pickerBlock.append(pickerLabel, picker);

    const chips = new Map();

    function renderSelected() {
      const head = selected.card.querySelector(".roxy-flow-model-head")?.cloneNode(true) || el("span", "roxy-flow-model-head");
      const title = head.querySelector(".roxy-flow-model-title");
      const strong = title?.querySelector("strong");
      const small = title?.querySelector("small");
      if (strong) strong.textContent = family;
      if (small) small.textContent = `Выбрано: ${selected.title}`;

      const modes = selected.card.querySelector(".roxy-flow-model-scenarios")?.cloneNode(true) || el("span", "roxy-flow-model-scenarios");
      const footer = selected.card.querySelector(".roxy-flow-model-footer")?.cloneNode(true) || el("span", "roxy-flow-model-footer");
      const footerCopy = footer.querySelector("span:not(.roxy-flow-model-arrow)");
      if (footerCopy) footerCopy.textContent = "Открыть выбранную версию";

      open.replaceChildren(head, modes, footer);
      open.setAttribute("aria-label", `Открыть ${selected.title}`);
      card.dataset.selectedProductId = selected.productId;

      for (const [productId, chip] of chips) {
        const active = productId === selected.productId;
        chip.classList.toggle("is-active", active);
        chip.setAttribute("aria-checked", active ? "true" : "false");
        chip.tabIndex = active ? 0 : -1;
      }
    }

    for (const item of items) {
      const chip = button(versionLabel(family, item.title), () => {
        if (selected.productId === item.productId) return;
        selected = item;
        localStorage.setItem(storageKey(mediaType, family), item.productId);
        haptic();
        renderSelected();
      }, "roxy-flow-version-chip");
      chip.setAttribute("role", "radio");
      chip.setAttribute("aria-label", item.title);
      chips.set(item.productId, chip);
      picker.appendChild(chip);
    }

    picker.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
      const controls = [...chips.values()];
      if (!controls.length) return;
      let index = controls.indexOf(document.activeElement);
      if (index < 0) index = controls.indexOf(chips.get(selected.productId));
      if (event.key === "Home") index = 0;
      else if (event.key === "End") index = controls.length - 1;
      else if (["ArrowRight", "ArrowDown"].includes(event.key)) index = (index + 1 + controls.length) % controls.length;
      else index = (index - 1 + controls.length) % controls.length;
      event.preventDefault();
      controls[index].click();
      controls[index].focus();
    });

    renderSelected();
    card.append(open, pickerBlock);
    return card;
  }

  function groupCards(cards) {
    const groups = [];
    const byFamily = new Map();
    for (const card of cards) {
      const item = productInfo(card);
      const key = item.family.toLocaleLowerCase("ru-RU");
      let group = byFamily.get(key);
      if (!group) {
        group = [];
        byFamily.set(key, group);
        groups.push(group);
      }
      group.push(item);
    }
    return groups;
  }

  function updateCount(center, familyCount, versionCount) {
    const count = center.querySelector(":scope > .roxy-flow-count");
    if (!count) return;
    const familiesWord = pluralRu(familyCount, "семейство", "семейства", "семейств");
    const versionsWord = pluralRu(versionCount, "версия", "версии", "версий");
    count.textContent = `${familyCount} ${familiesWord} · ${versionCount} ${versionsWord}`;
  }

  function decorateGrid(center, grid) {
    if (grid.dataset.roxyFamilyPickerSource === "1") return;
    const cards = [...grid.querySelectorAll(":scope > .roxy-flow-model-card[data-product-id]")];
    if (cards.length < 2) return;
    const groups = groupCards(cards);
    if (!groups.some((group) => group.length > 1)) return;

    const mediaType = currentMediaType(center);
    const familyGrid = el("div", "roxy-flow-model-grid roxy-family-picker-grid");
    familyGrid.dataset.roxyFamilyPickerView = "1";
    for (const group of groups) {
      familyGrid.appendChild(group.length > 1 ? familyCard(group, mediaType) : cloneSingleton(group[0]));
    }

    grid.dataset.roxyFamilyPickerSource = "1";
    grid.classList.add("roxy-family-picker-original");
    grid.insertAdjacentElement("beforebegin", familyGrid);
    updateCount(center, groups.length, cards.length);
  }

  function scan() {
    scanScheduled = false;
    const center = document.getElementById(CENTER_ID);
    if (!center) return;
    const grids = [...center.querySelectorAll(":scope > .roxy-flow-model-grid:not(.roxy-family-picker-grid)")];
    grids.forEach((grid) => decorateGrid(center, grid));
  }

  function scheduleScan() {
    if (scanScheduled) return;
    scanScheduled = true;
    window.requestAnimationFrame(scan);
  }

  function attachCenterObserver() {
    const center = document.getElementById(CENTER_ID);
    if (!center) return false;
    if (observedCenter === center && centerObserver) {
      scheduleScan();
      return true;
    }
    centerObserver?.disconnect();
    observedCenter = center;
    centerObserver = new MutationObserver(scheduleScan);
    centerObserver.observe(center, { childList: true });
    scheduleScan();
    return true;
  }

  function init() {
    for (const delay of [0, 80, 180, 420, 900, 1600]) {
      window.setTimeout(attachCenterObserver, delay);
    }
    window.addEventListener("roxy:shell-route-changed", attachCenterObserver);
    window.addEventListener("roxy:route-changed", attachCenterObserver);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
