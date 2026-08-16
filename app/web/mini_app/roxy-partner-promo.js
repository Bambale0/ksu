(() => {
  "use strict";

  const PROMO_ID = "partner-referrals-35";
  const PROMO_IMAGE = "/mini-app/roxy-partner-referrals-slide.jpg";
  const PROMO_LABEL = "ROXY · До 35% с пополнений рефералов";
  let observer = null;
  let frame = 0;

  function haptic() {
    try { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.("light"); } catch (_error) { /* optional */ }
  }

  function openPartnerCabinet() {
    haptic();
    if (window.RoxyCustomerNavigation?.open) {
      window.RoxyCustomerNavigation.open("profile");
      return;
    }
    window.KsuStudioShell?.open?.("profile");
  }

  function buildCard() {
    const card = document.createElement("article");
    card.className = "roxy-promo-card roxy-promo-artwork";
    card.dataset.roxyFixedPromo = PROMO_ID;
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", `${PROMO_LABEL}. Стать партнёром`);

    const image = document.createElement("img");
    image.className = "roxy-promo-art";
    image.src = PROMO_IMAGE;
    image.alt = PROMO_LABEL;
    image.loading = "eager";
    image.decoding = "async";
    image.draggable = false;
    card.appendChild(image);

    card.addEventListener("click", openPartnerCabinet);
    card.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      openPartnerCabinet();
    });
    return card;
  }

  function rebuildDots(viewport, dots) {
    const cards = [...viewport.querySelectorAll(".roxy-promo-card")];
    dots.replaceChildren(...cards.map((card, index) => {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = `roxy-promo-dot${index === 0 ? " is-active" : ""}`;
      const title = card.dataset.roxyFixedPromo === PROMO_ID
        ? PROMO_LABEL
        : (card.querySelector("h2")?.textContent || "ROXY");
      dot.setAttribute("aria-label", `Слайд ${index + 1}: ${title}`);
      dot.setAttribute("aria-current", index === 0 ? "true" : "false");
      dot.addEventListener("click", () => {
        card.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "start" });
      });
      return dot;
    }));
  }

  function ensureSecondSlide() {
    frame = 0;
    const viewport = document.getElementById("roxyPromoViewport");
    const dots = document.getElementById("roxyPromoDots");
    if (!viewport || !dots) return false;

    let fixed = viewport.querySelector(`[data-roxy-fixed-promo="${PROMO_ID}"]`);
    const sourceCards = [...viewport.querySelectorAll(".roxy-promo-card:not([data-roxy-fixed-promo])")];
    if (!sourceCards.length) return false;

    if (!fixed) fixed = buildCard();
    const first = sourceCards[0];
    if (first.nextElementSibling !== fixed) first.insertAdjacentElement("afterend", fixed);

    const cards = [...viewport.querySelectorAll(".roxy-promo-card")];
    cards.forEach((card, index) => { card.dataset.promoIndex = String(index); });
    viewport.classList.add("roxy-partner-promo-ready");
    rebuildDots(viewport, dots);
    return true;
  }

  function schedule() {
    if (frame) return;
    frame = window.requestAnimationFrame(ensureSecondSlide);
  }

  function attach() {
    const viewport = document.getElementById("roxyPromoViewport");
    if (!viewport) return false;
    if (!observer) {
      observer = new MutationObserver(schedule);
      observer.observe(viewport, { childList: true });
    }
    schedule();
    return true;
  }

  function init() {
    if (attach()) return;
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      if (attach() || attempts >= 50) window.clearInterval(timer);
    }, 80);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();