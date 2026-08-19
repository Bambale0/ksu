(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const root = document.documentElement;
  const VISIBLE_PROVIDER = "cryptobot";
  const PALETTES = {
    dark: {
      bg: "#090b10",
      header: "#0b0e14",
      bottom: "#0d1118",
    },
    light: {
      bg: "#f6f7fb",
      header: "#f8f9fc",
      bottom: "#ffffff",
    },
  };

  function resolvedTheme() {
    if (tg?.colorScheme === "light" || tg?.colorScheme === "dark") return tg.colorScheme;
    return window.matchMedia?.("(prefers-color-scheme: light)")?.matches ? "light" : "dark";
  }

  function applyTheme() {
    const theme = resolvedTheme();
    const palette = PALETTES[theme];
    root.dataset.ksuTheme = theme;
    const meta = document.querySelector('meta[name="theme-color"]');
    meta?.setAttribute("content", palette.bg);
    try { tg?.setHeaderColor?.(palette.header); } catch (_error) { /* optional Telegram chrome */ }
    try { tg?.setBackgroundColor?.(palette.bg); } catch (_error) { /* optional Telegram chrome */ }
    try { tg?.setBottomBarColor?.(palette.bottom); } catch (_error) { /* optional Telegram chrome */ }
  }

  function setText(node, value) {
    if (node && node.textContent !== value) node.textContent = value;
  }

  applyTheme();
  tg?.onEvent?.("themeChanged", applyTheme);

  function removeLegacyProviders(scope) {
    scope.querySelectorAll('[data-payment-provider="tbank"], [data-payment-provider="yookassa"]').forEach((node) => node.remove());
    scope.querySelectorAll("[data-payment-provider]").forEach((node) => {
      if (node.dataset.paymentProvider !== VISIBLE_PROVIDER) node.remove();
    });
  }

  function methodButton(id, titleText, subtitle, glyph) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "payment-method-choice";
    button.dataset.checkoutMethod = id;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", "false");

    const icon = document.createElement("span");
    icon.className = `payment-method-icon ${id}`;
    icon.textContent = glyph;
    icon.setAttribute("aria-hidden", "true");

    const text = document.createElement("span");
    text.className = "payment-method-text";
    const strong = document.createElement("strong");
    strong.textContent = titleText;
    const small = document.createElement("small");
    small.textContent = subtitle;
    text.append(strong, small);
    button.append(icon, text);
    return button;
  }

  function brandLava(lavaSection) {
    const heading = document.getElementById("primaryCardHeading");
    const kicker = lavaSection.querySelector(".section-kicker");
    const badge = lavaSection.querySelector(".primary-card-badge");
    const note = lavaSection.querySelector(".primary-card-summary small");
    setText(heading, "Lava.top");
    setText(kicker, "Карта / СБП");
    setText(badge, "Основной");
    setText(note, "RUB · USD · EUR");
    lavaSection.dataset.checkoutProvider = "lavatop";
  }

  function brandCrypto(cryptoSection) {
    const heading = document.getElementById("topupHeading");
    const kicker = cryptoSection.querySelector(".section-kicker");
    setText(heading, "CryptoBot");
    setText(kicker, "Криптовалюта");

    removeLegacyProviders(cryptoSection);
    const provider = cryptoSection.querySelector('[data-payment-provider="cryptobot"]');
    if (!provider) return;
    provider.classList.add("is-selected");
    provider.setAttribute("aria-checked", "true");
    setText(provider.querySelector("strong"), "CryptoBot");
    setText(provider.querySelector("small"), "USDT · TON · BTC и другие");
    setText(provider.querySelector(".provider-mark"), "◈");
  }

  function mount(attempt = 0) {
    const walletView = document.getElementById("walletView");
    const lavaSection = document.querySelector(".primary-card-section");
    const cryptoSection = document.getElementById("topupHeading")?.closest(".home-section");
    if (!walletView || !lavaSection || !cryptoSection) {
      if (attempt < 50) window.setTimeout(() => mount(attempt + 1), 60);
      return;
    }
    if (walletView.dataset.paymentSurfaceReady === "true") return;
    walletView.dataset.paymentSurfaceReady = "true";

    brandLava(lavaSection);
    brandCrypto(cryptoSection);

    const providerObserver = new MutationObserver(() => {
      removeLegacyProviders(cryptoSection);
      brandCrypto(cryptoSection);
    });
    providerObserver.observe(cryptoSection, { childList: true, subtree: true });

    const switcher = document.createElement("section");
    switcher.className = "payment-method-shell";
    switcher.setAttribute("aria-labelledby", "paymentMethodTitle");

    const copy = document.createElement("div");
    copy.className = "payment-method-copy";
    const kicker = document.createElement("span");
    kicker.className = "section-kicker";
    kicker.textContent = "Пополнение";
    const title = document.createElement("h2");
    title.id = "paymentMethodTitle";
    title.textContent = "Выберите способ оплаты";
    const description = document.createElement("p");
    description.textContent = "Только два способа: Lava.top для карты и СБП, CryptoBot для криптовалюты.";
    copy.append(kicker, title, description);

    const methods = document.createElement("div");
    methods.className = "payment-method-switcher";
    methods.setAttribute("role", "tablist");
    methods.setAttribute("aria-label", "Способ оплаты");

    const lavaButton = methodButton("lava", "Lava.top", "Карта · СБП · RUB / USD / EUR", "L");
    const cryptoButton = methodButton("crypto", "CryptoBot", "Криптовалюта внутри Telegram", "◈");
    methods.append(lavaButton, cryptoButton);
    switcher.append(copy, methods);
    lavaSection.before(switcher);

    function setMethod(method, focus = false) {
      const next = method === "crypto" ? "crypto" : "lava";
      lavaSection.hidden = next !== "lava";
      cryptoSection.hidden = next !== "crypto";
      document.body.dataset.checkoutMethod = next;
      for (const button of [lavaButton, cryptoButton]) {
        const active = button.dataset.checkoutMethod === next;
        button.classList.toggle("is-selected", active);
        button.setAttribute("aria-selected", String(active));
        button.tabIndex = active ? 0 : -1;
      }
      try { sessionStorage.setItem("ksu-payment-method", next); } catch (_error) { /* optional */ }
      if (focus) {
        const target = next === "lava" ? lavaSection : cryptoSection;
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        try { tg?.HapticFeedback?.impactOccurred?.("light"); } catch (_error) { /* optional */ }
      }
    }

    lavaButton.addEventListener("click", () => setMethod("lava", true));
    cryptoButton.addEventListener("click", () => setMethod("crypto", true));
    methods.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
      event.preventDefault();
      const next = document.body.dataset.checkoutMethod === "lava" ? "crypto" : "lava";
      setMethod(next, false);
      (next === "lava" ? lavaButton : cryptoButton).focus();
    });

    let initial = "lava";
    try { initial = sessionStorage.getItem("ksu-payment-method") || "lava"; } catch (_error) { /* optional */ }
    setMethod(initial, false);
  }

  mount();
})();
