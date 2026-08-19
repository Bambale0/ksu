(() => {
  "use strict";

  const SLIDES = [
    {
      id: "partner-referrals-35",
      image: "/mini-app/roxy-partner-referrals-slide-source.webp?v=9",
      label: "ROXY · До 35% с пополнений рефералов",
      action: "partner",
    },
    {
      id: "creator-rewards",
      image: "/mini-app/roxy-creator-rewards-slide-source.webp?v=9",
      label: "ROXY · Создавай. Публикуй. Зарабатывай.",
      action: "feed",
    },
  ];

  let observer = null;
  let frame = 0;

  function haptic() {
    try { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.("light"); } catch (_error) { /* optional */ }
  }

  function openSlideAction(action) {
    haptic();
    if (action === "feed") {
      if (window.KsuStudioShell?.open) {
        window.KsuStudioShell.open("feed");
        return;
      }
      window.RoxyDiscovery?.openCommunityFeed?.();
      return;
    }
    if (window.RoxyCustomerNavigation?.open) {
      window.RoxyCustomerNavigation.open("profile");
      return;
    }
    window.KsuStudioShell?.open?.("profile");
  }

  function buildCard(slide, index) {
    const card = document.createElement("article");
    card.className = "roxy-promo-card roxy-promo-artwork";
    card.dataset.roxyFixedPromo = slide.id;
    card.dataset.promoIndex = String(index);
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", slide.label);

    const image = document.createElement("img");
    image.className = "roxy-promo-art";
    image.src = slide.image;
    image.alt = slide.label;
    image.loading = index === 0 ? "eager" : "lazy";
    image.decoding = "async";
    image.draggable = false;
    if (index === 0) image.fetchPriority = "high";

    const fallback = document.createElement("span");
    fallback.className = "roxy-promo-fallback";
    fallback.hidden = true;
    fallback.textContent = "ROXY";

    image.addEventListener("load", () => {
      card.classList.remove("is-broken");
      fallback.hidden = true;
    }, { once: true });
    image.addEventListener("error", () => {
      console.error("[ROXY] Promo artwork failed to load", slide.image);
      card.classList.add("is-broken");
      image.hidden = true;
      fallback.hidden = false;
    }, { once: true });

    card.append(image, fallback);
    card.addEventListener("click", () => openSlideAction(slide.action));
    card.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      openSlideAction(slide.action);
    });
    return card;
  }

  function rebuildDots(viewport, dots) {
    const cards = [...viewport.querySelectorAll(".roxy-promo-card")];
    dots.replaceChildren(...cards.map((card, index) => {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = `roxy-promo-dot${index === 0 ? " is-active" : ""}`;
      dot.setAttribute("aria-label", `Слайд ${index + 1}: ${SLIDES[index]?.label || "ROXY"}`);
      dot.setAttribute("aria-current", index === 0 ? "true" : "false");
      dot.addEventListener("click", () => {
        card.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "start" });
      });
      return dot;
    }));
  }

  function replaceSlides() {
    frame = 0;
    const viewport = document.getElementById("roxyPromoViewport");
    const dots = document.getElementById("roxyPromoDots");
    if (!viewport || !dots) return false;

    const expected = SLIDES.map((slide) => slide.id).join("|");
    const current = [...viewport.querySelectorAll(".roxy-promo-card")]
      .map((card) => card.dataset.roxyFixedPromo || "")
      .join("|");
    if (current === expected) return true;

    viewport.replaceChildren(...SLIDES.map(buildCard));
    viewport.classList.add("roxy-partner-promo-ready");
    rebuildDots(viewport, dots);
    return true;
  }

  function schedule() {
    if (frame) return;
    frame = window.requestAnimationFrame(replaceSlides);
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
