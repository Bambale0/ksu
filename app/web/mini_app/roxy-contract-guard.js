(() => {
  "use strict";

  const ZERO_PRICE = /^(?:от\s+)?0(?:[.,]0+)?\s*ROX(?:\/с)?$/i;
  const LEGACY_CREDIT = /(?:кр\.|кредит(?:ы|ов|а)?)/gi;
  let observer = null;
  let scheduled = false;

  function normalizePriceNode(node) {
    if (!(node instanceof Element)) return;
    const text = (node.textContent || "").trim();
    if (ZERO_PRICE.test(text) && text !== "Бесплатно") node.textContent = "Бесплатно";
  }

  function normalizeRoxText(root) {
    if (!(root instanceof Element) && root !== document) return;
    const scopes = [];
    if (root === document) {
      document.querySelectorAll("#walletView, #balanceValue, #walletBalance").forEach((node) => scopes.push(node));
    } else {
      if (root.matches?.("#walletView, #balanceValue, #walletBalance")) scopes.push(root);
      root.querySelectorAll?.("#walletView, #balanceValue, #walletBalance").forEach((node) => scopes.push(node));
    }

    for (const scope of scopes) {
      const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      for (const textNode of nodes) {
        const value = textNode.nodeValue || "";
        const normalized = value
          .replace(/1\s*кр\.\s*=\s*/gi, "1 ROX = ")
          .replace(LEGACY_CREDIT, "ROX");
        if (normalized !== value) textNode.nodeValue = normalized;
      }
    }
  }

  function normalize(root = document) {
    if (root === document) {
      document.querySelectorAll(".roxy-flow-model-price").forEach(normalizePriceNode);
    } else if (root instanceof Element) {
      if (root.matches(".roxy-flow-model-price")) normalizePriceNode(root);
      root.querySelectorAll(".roxy-flow-model-price").forEach(normalizePriceNode);
    }
    normalizeRoxText(root);
  }

  function schedule(root = document) {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(() => {
      scheduled = false;
      normalize(root);
    });
  }

  function init() {
    normalize(document);
    if (!document.body || observer) return;
    observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "characterData") {
          schedule(record.target.parentElement || document);
          return;
        }
        for (const node of record.addedNodes || []) {
          if (node instanceof Element) {
            schedule(node);
            return;
          }
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    window.addEventListener("roxy:shell-route-changed", () => schedule(document));
    window.addEventListener("roxy:route-changed", () => schedule(document));
  }

  window.RoxyContractGuard = Object.freeze({ normalize });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
