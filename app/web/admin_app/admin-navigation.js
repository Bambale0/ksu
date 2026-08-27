(() => {
  "use strict";

  function preserveLaunchData() {
    const source = new URL(window.location.href);
    if (!source.search && !source.hash) return;
    for (const anchor of document.querySelectorAll("a[data-preserve-launch]")) {
      const raw = anchor.getAttribute("href");
      if (!raw) continue;
      const target = new URL(raw, window.location.origin);
      if (target.origin !== window.location.origin) continue;
      if (!target.search && source.search) target.search = source.search;
      if (!target.hash && source.hash) target.hash = source.hash;
      anchor.href = `${target.pathname}${target.search}${target.hash}`;
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", preserveLaunchData, { once: true });
  } else {
    preserveLaunchData();
  }
})();
