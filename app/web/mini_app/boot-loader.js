(() => {
  "use strict";

  const MIN_VISIBLE_MS = 760;
  const HARD_TIMEOUT_MS = 5200;
  const TRANSITION_MS = 460;
  const startedAt = performance.now();
  let finishing = false;

  function getLoader() {
    return document.getElementById("rxBootLoader");
  }

  function finishLoader() {
    if (finishing) return;
    const loader = getLoader();
    if (!loader) {
      finishing = true;
      return;
    }

    const elapsed = performance.now() - startedAt;
    if (elapsed < MIN_VISIBLE_MS) {
      window.setTimeout(finishLoader, MIN_VISIBLE_MS - elapsed);
      return;
    }

    finishing = true;
    loader.classList.add("is-leaving");
    loader.setAttribute("aria-hidden", "true");

    window.setTimeout(() => {
      loader.remove();
    }, TRANSITION_MS);
  }

  function finishAfterPaint() {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(finishLoader);
    });
  }

  if (document.readyState === "complete") finishAfterPaint();
  else window.addEventListener("load", finishAfterPaint, { once: true });

  // Never leave a user trapped behind the splash if a late optional asset stalls.
  window.setTimeout(finishLoader, HARD_TIMEOUT_MS);
})();
