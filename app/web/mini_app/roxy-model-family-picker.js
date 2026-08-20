(() => {
  "use strict";

  const STORAGE_PREFIX = "roxy-model-family-choice-v2:";
  const CENTER_ID = "roxyCreateCenterView";
  const productMeta = new Map();
  let catalogLoaded = false;
  let catalogPromise = null;
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

  function operationShort(operation) {
    return {
      text_to_video: "T2V",
      image_to_video: "I2V",
      video_edit: "Edit",
      reference_to_video: "R2V",
      text_to_image: "T2I",
      image_to_image: "I2I",
      image_edit: "Edit",
      layer_decomposition: "Layers",
      motion_control: "Motion",
      audio_driven_avatar: "Avatar",
    }[operation] || "";
  }

  function currentMediaType(center) {
    const kicker = center.querySelector(".roxy-flow-topbar .section-kicker")?.textContent || "";
    return /видео/i.test(kicker) ? "video" : "image";
  }

  async function loadCatalogPresentation() {
    if (catalogLoaded) return;
    if (catalogPromise) return catalogPromise;
    catalogPromise = (async () => {
      try {
        const response = await fetch("/api/v1/generations/models", { cache: "no-store" });
        if (!response.ok) return;
        const payload = await response.json();
        const aggregate = new Map();
        for (const model of payload?.models || []) {
          const presentation = model?.presentation || {};
          const meta = {
            productId: String(model.id || ""),
            productKey: String(presentation.product_key || model.id || ""),
            title: String(presentation.product_title || presentation.title || model.title || model.id || "ROXY"),
            familyGroup: presentation.family_group ? String(presentation.family_group) : null,
            familyTitle: String(presentation.family_title || model.family || "ROXY"),
            version: String(presentation.version_label || presentation.product_title || model.title || model.id || ""),
            operation: String(model.operation || ""),
            adminFree: Boolean(model.admin_free),
          };
          productMeta.set(meta.productId, meta);
          if (!aggregate.has(meta.productKey)) aggregate.set(meta.productKey, meta);
        }
        for (const [key, value] of aggregate) productMeta.set(key, value);

        // The existing create-center grouped WAN T2V/I2V/Edit card predates the
        // server presentation key. Keep it attached to the exact same 2.7 metadata
        // while R2V remains its own explicit operation card until that builder group
        // is intentionally widened.
        if (!productMeta.has("wan-2.7") && productMeta.has("wan-2.7-video")) {
          productMeta.set("wan-2.7", productMeta.get("wan-2.7-video"));
        }
      } catch (_error) {
        // Fail open to original model cards; never invent grouping when authority is unavailable.
      } finally {
        catalogLoaded = true;
        catalogPromise = null;
      }
    })();
    return catalogPromise;
  }

  function productInfo(card) {
    const renderedTitle = (card.querySelector(".roxy-flow-model-title strong")?.textContent || "").trim();
    const renderedFamily = (card.querySelector(".roxy-flow-model-title small")?.textContent || renderedTitle || "ROXY").trim();
    const productId = card.dataset.productId || renderedTitle;
    const meta = productMeta.get(productId) || null;
    return {
      card,
      productId,
      title: meta?.title || renderedTitle || renderedFamily,
      familyGroup: meta?.familyGroup || null,
      family: meta?.familyTitle || renderedFamily,
      version: meta?.version || renderedTitle || "Base",
      operation: meta?.operation || "",
      adminFree: Boolean(meta?.adminFree),
    };
  }

  function storageKey(mediaType, familyGroup) {
    return `${STORAGE_PREFIX}${mediaType}:${slug(familyGroup)}`;
  }

  function rememberedItem(items, mediaType, familyGroup) {
    const remembered = localStorage.getItem(storageKey(mediaType, familyGroup));
    return items.find((item) => item.productId === remembered) || items[0];
  }

  function makeFreeLabel(root, adminFree) {
    if (!adminFree) return;
    const price = root.querySelector?.(".roxy-flow-model-price");
    if (price) price.textContent = "Бесплатно";
  }

  function cloneSingleton(item) {
    const clone = item.card.cloneNode(true);
    clone.removeAttribute("data-roxy-family-source");
    makeFreeLabel(clone, item.adminFree);
    clone.addEventListener("click", () => item.card.click());
    return clone;
  }

  function resolvedVersions(items) {
    const counts = new Map();
    for (const item of items) counts.set(item.version, (counts.get(item.version) || 0) + 1);
    return new Map(items.map((item) => {
      const suffix = counts.get(item.version) > 1 ? operationShort(item.operation) : "";
      return [item.productId, suffix ? `${item.version} · ${suffix}` : item.version];
    }));
  }

  function familyCard(items, mediaType) {
    const familyGroup = items[0].familyGroup;
    const family = items[0].family;
    const versions = resolvedVersions(items);
    let selected = rememberedItem(items, mediaType, familyGroup);
    const card = el("article", "roxy-flow-model-card roxy-flow-family-card");
    card.dataset.family = family;
    card.dataset.familyGroup = familyGroup;

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
      makeFreeLabel(head, selected.adminFree);

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
      const chip = button(versions.get(item.productId), () => {
        if (selected.productId === item.productId) return;
        selected = item;
        localStorage.setItem(storageKey(mediaType, familyGroup), item.productId);
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
    const indexed = new Map();
    for (const card of cards) {
      const item = productInfo(card);
      // Only explicit server family_group values may collapse cards. Rendered
      // family text is presentation copy and must never decide model identity.
      const key = item.familyGroup ? `family:${item.familyGroup}` : `product:${item.productId}`;
      let group = indexed.get(key);
      if (!group) {
        group = [];
        indexed.set(key, group);
        groups.push(group);
      }
      group.push(item);
    }
    return groups;
  }

  function updateCount(center, familyCount, sourceCount) {
    const count = center.querySelector(":scope > .roxy-flow-count");
    if (!count) return;
    const familiesWord = pluralRu(familyCount, "модель", "модели", "моделей");
    const sourceWord = pluralRu(sourceCount, "вариант", "варианта", "вариантов");
    count.textContent = `${familyCount} ${familiesWord} · ${sourceCount} ${sourceWord}`;
  }

  async function decorateGrid(center, grid) {
    if (grid.dataset.roxyFamilyPickerSource === "1") return;
    await loadCatalogPresentation();
    const cards = [...grid.querySelectorAll(":scope > .roxy-flow-model-card[data-product-id]")];
    if (!cards.length) return;
    const groups = groupCards(cards);
    const needsPresentation = groups.some((group) => group.length > 1) || cards.some((card) => productInfo(card).adminFree);
    if (!needsPresentation) return;

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
    grids.forEach((grid) => { void decorateGrid(center, grid); });
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
    void loadCatalogPresentation();
    for (const delay of [0, 80, 180, 420, 900, 1600]) {
      window.setTimeout(attachCenterObserver, delay);
    }
    window.addEventListener("roxy:shell-route-changed", attachCenterObserver);
    window.addEventListener("roxy:route-changed", attachCenterObserver);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();