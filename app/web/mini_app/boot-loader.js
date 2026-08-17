(() => {
  "use strict";

  const MIN_VISIBLE_MS = 760;
  const HARD_TIMEOUT_MS = 5200;
  const TRANSITION_MS = 460;
  const startedAt = performance.now();
  let finishing = false;

  document.documentElement.classList.add("rx-booting");

  const polish = document.createElement("style");
  polish.dataset.rxBootPolish = "true";
  polish.textContent = `
    html.rx-booting #appShell { visibility: hidden !important; }
    .rx-loader-core {
      border-radius: 50% !important;
      background:
        url("/mini-app/roxy-logo.svg") center / 58% 58% no-repeat,
        radial-gradient(circle at 48% 42%, rgba(155,92,255,.14), rgba(11,11,16,.98) 68%) !important;
    }
    .rx-loader-core img { opacity: 0 !important; visibility: hidden !important; }
  `;
  document.head.appendChild(polish);

  function getLoader() {
    return document.getElementById("rxBootLoader");
  }

  function finishLoader() {
    if (finishing) return;
    const loader = getLoader();
    if (!loader) {
      finishing = true;
      document.documentElement.classList.remove("rx-booting");
      return;
    }

    const elapsed = performance.now() - startedAt;
    if (elapsed < MIN_VISIBLE_MS) {
      window.setTimeout(finishLoader, MIN_VISIBLE_MS - elapsed);
      return;
    }

    finishing = true;
    document.documentElement.classList.remove("rx-booting");
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
