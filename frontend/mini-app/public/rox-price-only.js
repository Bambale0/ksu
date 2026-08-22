(() => {
  function syncQuoteCurrency() {
    document.querySelectorAll(".quote-box > small").forEach((node) => {
      const isRubleEquivalent = (node.textContent || "").includes("₽");
      node.hidden = isRubleEquivalent;
    });
  }

  syncQuoteCurrency();
  new MutationObserver(syncQuoteCurrency).observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
  });
})();
