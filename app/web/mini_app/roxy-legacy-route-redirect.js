(() => {
  "use strict";

  const script = document.currentScript;
  const route = script?.dataset?.roxyRoute || "";
  if (!route) return;

  const params = new URLSearchParams(window.location.search);
  params.set("route", route);
  const target = `/mini-app/?${params.toString()}`;
  const current = `${window.location.pathname}${window.location.search}`;
  if (current === target) return;
  window.location.replace(target);
})();
