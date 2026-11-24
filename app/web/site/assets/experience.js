(() => {
  "use strict";

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
  const progress = document.getElementById("reading-progress");
  const progressFill = progress?.querySelector("span");
  const trace = document.getElementById("scroll-trace-path");
  const hero = document.querySelector(".hero");
  const layers = Array.from(document.querySelectorAll("[data-parallax]"));
  let scrollFrame = 0;
  let tiltFrame = 0;
  let activeTile = null;
  let point = null;

  const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

  function clearTilt(tile) {
    if (!tile) return;
    tile.style.removeProperty("--rx");
    tile.style.removeProperty("--ry");
    for (const prop of ["--spot-x","--spot-y","--asset-x","--asset-y"]) tile.style.removeProperty(prop);
  }

  function draw() {
    scrollFrame = 0;
    const maximum = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    const fraction = maximum > 0 ? clamp(window.scrollY / maximum, 0, 1) : 0;
    if (progressFill) progressFill.style.transform = `scaleX(${fraction})`;
    progress?.setAttribute("aria-valuenow", String(Math.round(fraction * 100)));

    if (reducedMotion.matches) {
      for (const layer of layers) layer.style.removeProperty("--parallax-y");
      if (trace) {
        trace.setAttribute("d", "M39 0 C22 110 57 195 39 278 C20 365 58 455 39 560");
      }
    } else {
      const travel = clamp(window.scrollY, 0, hero?.offsetHeight || 0);
      for (const layer of layers) {
        const depth = Number(layer.getAttribute("data-depth")) || 0;
        layer.style.setProperty("--parallax-y", `${Math.round(travel * depth)}px`);
      }
      if (trace) {
        // A subtle changing Bézier path, not a fixed stroke mask.
        const wave = Math.sin(fraction * Math.PI * 2) * 12;
        trace.setAttribute("d", `M39 0 C${22 + wave} 110 ${57 - wave} 195 39 278 C${20 - wave} 365 ${58 + wave} 455 39 560`);
      }
    }
    if (trace) {
      const length = trace.getTotalLength();
      trace.style.strokeDasharray = `${length} ${length}`;
      trace.style.strokeDashoffset = String(length * (1 - fraction));
    }
  }

  function schedule() {
    if (!scrollFrame) scrollFrame = requestAnimationFrame(draw);
  }

  function drawTilt() {
    tiltFrame = 0;
    if (!activeTile || !point || reducedMotion.matches || !finePointer.matches) return;
    const rect = activeTile.getBoundingClientRect();
    const x = clamp((point.x - rect.left) / Math.max(rect.width, 1), 0, 1) - 0.5;
    const y = clamp((point.y - rect.top) / Math.max(rect.height, 1), 0, 1) - 0.5;
    activeTile.style.setProperty("--rx", `${(-y * 6).toFixed(2)}deg`);
    activeTile.style.setProperty("--ry", `${(x * 7).toFixed(2)}deg`);
    activeTile.style.setProperty("--spot-x", `${(x + .5) * 100}%`);
    activeTile.style.setProperty("--spot-y", `${(y + .5) * 100}%`);
    activeTile.style.setProperty("--asset-x", `${x * 10}px`);
    activeTile.style.setProperty("--asset-y", `${y * 8}px`);
  }

  // Independent hero pointer depth, sampled at most once per frame.
  let heroFrame = 0;
  let heroPoint = null;
  function drawHeroPointer() {
    heroFrame = 0;
    if (!hero || !heroPoint || reducedMotion.matches || !finePointer.matches) return;
    const rect = hero.getBoundingClientRect();
    const x = clamp((heroPoint.x - rect.left) / Math.max(rect.width,1),0,1) - .5;
    const y = clamp((heroPoint.y - rect.top) / Math.max(rect.height,1),0,1) - .5;
    hero.style.setProperty("--hero-x", `${x * 20}px`);
    hero.style.setProperty("--hero-y", `${y * 12}px`);
  }
  function resetHeroPointer() {
    heroPoint = null;
    hero?.style.removeProperty("--hero-x");
    hero?.style.removeProperty("--hero-y");
  }
  hero?.addEventListener("pointermove", (event) => {
    if (event.pointerType !== "mouse" || reducedMotion.matches || !finePointer.matches) return;
    heroPoint = {x:event.clientX,y:event.clientY};
    if (!heroFrame) heroFrame = requestAnimationFrame(drawHeroPointer);
  }, { passive: true });
  hero?.addEventListener("pointerleave", resetHeroPointer, { passive: true });
  reducedMotion.addEventListener?.("change", resetHeroPointer);
  finePointer.addEventListener?.("change", resetHeroPointer);

  // Delegation includes live trend tiles injected after the page has loaded.
  const tileSelector = ".format-card, .gallery-item, .capability";
  document.addEventListener("pointermove", (event) => {
    if (event.pointerType !== "mouse" || reducedMotion.matches || !finePointer.matches) return;
    const tile = event.target instanceof Element ? event.target.closest(tileSelector) : null;
    if (tile !== activeTile) {
      clearTilt(activeTile);
      activeTile = tile;
    }
    point = { x: event.clientX, y: event.clientY };
    if (activeTile && !tiltFrame) tiltFrame = requestAnimationFrame(drawTilt);
  }, { passive: true });

  document.addEventListener("pointerout", (event) => {
    if (!(event.target instanceof Element)) return;
    const tile = event.target.closest(tileSelector);
    if (tile && tile === activeTile && !(event.relatedTarget instanceof Node && tile.contains(event.relatedTarget))) {
      clearTilt(activeTile);
      activeTile = null;
      point = null;
    }
  }, { passive: true });

  reducedMotion.addEventListener?.("change", () => {
    clearTilt(activeTile);
    activeTile = null;
    schedule();
  });
  finePointer.addEventListener?.("change", () => {
    clearTilt(activeTile);
    activeTile = null;
  });
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule, { passive: true });
  window.addEventListener("load", schedule, { once: true });
  schedule();
})();