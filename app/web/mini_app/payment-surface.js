(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const walletView = document.getElementById("walletView");
  const lavaSection = document.querySelector(".primary-card-section");
  const cryptoSection = document.getElementById("topupHeading")?.closest(".home-section");
  if (!walletView || !lavaSection || !cryptoSection) return;

  document.documentElement.dataset.ksuTheme = tg?.colorScheme === "light" ? "light" : "dark";
  tg?.onEvent?.("themeChanged", () => {
    document.documentElement.dataset.ksuTheme = tg?.colorScheme === "light" ? "light" : "dark";
  });

  document.querySelectorAll('[data-payment-provider="tbank"], [data-payment-provider="yookassa"]').forEach((node) => node.remove());

  const cryptoProvider = cryptoSection.querySelector('[data-payment-provider="cryptobot"]');
  if (cryptoProvider) {
    cryptoProvider.classList.add("is-selected");
    cryptoProvider.setAttribute("aria-checked", "true");
    const strong = cryptoProvider.querySelector("strong");
    const small = cryptoProvider.querySelector("small");
    const mark = cryptoProvider.querySelector(".provider-mark");
    if (strong) strong.textContent = "CryptoBot";
    if (small) small.textContent = "USDT · TON · BTC и другие";
    if (mark) mark.textContent = "◈";
  }

  const legacyHeading = document.getElementById("topupHeading");
  const legacyKicker = cryptoSection.querySelector(".section-kicker");
  if (legacyHeading) legacyHeading.textContent = "CryptoBot";
  if (legacyKicker) legacyKicker.textContent = "Криптовалюта";

  const lavaHeading = document.getElementById("primaryCardHeading");
  const lavaKicker = lavaSection.querySelector(".section-kicker");
  const lavaBadge = lavaSection.querySelector(".primary-card-badge");
  if (lavaHeading) lavaHeading.textContent = "Lava.top";
  if (lavaKicker) lavaKicker.textContent = "Карта / СБП";
  if (lavaBadge) lavaBadge.textContent = "Основной";

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
  title.textContent = "Как хотите оплатить?";
  const description = document.createElement("p");
  description.textContent = "Два понятных способа без лишних платёжных экранов.";
  copy.append(kicker, title, description);

  const methods = document.createElement("div");
  methods.className = "payment-method-switcher";
  methods.setAttribute("role", "tablist");
  methods.setAttribute("aria-label", "Способ оплаты");

  function methodButton(id, titleText, subtitle, glyph) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "payment-method-choice";
    button.dataset.checkoutMethod = id;
    button.setAttribute("role", "tab");
    const icon = document.createElement("span");
    icon.className = `payment-method-icon ${id}`;
    icon.textContent = glyph;
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

  const lavaButton = methodButton("lava", "Lava.top", "Карта · СБП · RUB / USD / EUR", "L");
  const cryptoButton = methodButton("crypto", "CryptoBot", "Криптовалюта внутри Telegram", "◈");
  methods.append(lavaButton, cryptoButton);
  switcher.append(copy, methods);
  lavaSection.before(switcher);

  const allowedProvider = new Set(["cryptobot"]);
  const providerObserver = new MutationObserver(() => {
    cryptoSection.querySelectorAll("[data-payment-provider]").forEach((node) => {
      if (!allowedProvider.has(node.dataset.paymentProvider)) node.remove();
    });
  });
  providerObserver.observe(cryptoSection, { childList: true, subtree: true });

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
      (next === "lava" ? lavaSection : cryptoSection).scrollIntoView({ behavior: "smooth", block: "start" });
      tg?.HapticFeedback?.impactOccurred?.("light");
    }
  }

  lavaButton.addEventListener("click", () => setMethod("lava", true));
  cryptoButton.addEventListener("click", () => setMethod("crypto", true));

  methods.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const next = document.body.dataset.checkoutMethod === "lava" ? "crypto" : "lava";
    setMethod(next, false);
    (next === "lava" ? lavaButton : cryptoButton).focus();
  });

  let initial = "lava";
  try { initial = sessionStorage.getItem("ksu-payment-method") || "lava"; } catch (_error) { /* optional */ }
  setMethod(initial, false);
})();
