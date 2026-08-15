(() => {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const ICONS = Object.freeze({
    home: ["M3.5 11.2 12 4l8.5 7.2", "M5.5 10v9.5h5v-5h3v5h5V10"],
    catalog: ["M4 4h6v6H4z", "M14 4h6v6h-6z", "M4 14h6v6H4z", "M14 14h6v6h-6z"],
    create: ["M12 5v14", "M5 12h14"],
    history: ["M5 6h14", "M5 12h14", "M5 18h10"],
    profile: ["M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8", "M4.5 20c.9-4 3.4-6 7.5-6s6.6 2 7.5 6"],
    bell: ["M6 9a6 6 0 0 1 12 0c0 6 2.5 6.5 2.5 6.5h-17S6 15 6 9", "M10 19h4"],
    support: ["M4 12a8 8 0 1 1 16 0v5a2 2 0 0 1-2 2h-3", "M4 13h3v5H5a1 1 0 0 1-1-1z", "M20 13h-3v5h2a1 1 0 0 0 1-1z"],
    users: ["M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7", "M3 20c.7-4 2.7-6 6-6s5.3 2 6 6", "M16 5.5a3 3 0 0 1 0 5.5", "M17 14c2.4.4 3.7 2.3 4 5"],
    user: ["M12 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7", "M5 20c.8-4 3-6 7-6s6.2 2 7 6"],
    image: ["M4 5h16v14H4z", "m6 15 3-3 2.5 2.5 2-2L18 17", "M15.5 9a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3"],
    preset: ["M5 4h14v16H5z", "M8 8h8", "M8 12h8", "M8 16h5"],
    trend: ["M4 18 10 12l4 4 6-8", "M16 8h4v4"],
    prompt: ["M5 19h4l10-10-4-4L5 15z", "m13-13 2-2 4 4-2 2"],
    batch: ["M4 4h6v6H4z", "M14 4h6v6h-6z", "M4 14h6v6H4z", "M14 14h6v6h-6z"],
    creator: ["M12 3 14.2 8l5.3.5-4 3.5 1.2 5.2L12 15.5 7.3 18l1.2-5.2-4-3.5L9.8 8z"],
    settings: ["M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7", "M12 3v2", "M12 19v2", "M3 12h2", "M19 12h2", "m5.6-6.4 1.4 1.4", "m17 17 1.4 1.4", "m18.4 5.6-1.4 1.4", "m7 17-1.4 1.4"],
    wallet: ["M4 7h16v12H4z", "M4 9V6h13v3", "M15 13h5"],
    feed: ["M4 5h16v14H4z", "M8 9h8", "M8 13h8", "M8 17h5"],
    like: ["M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"],
    comment: ["M4 5h16v12H9l-5 4z"],
    share: ["M8 12h9", "m14 8 4 4-4 4", "M5 6v12"],
    repeat: ["M5 8h11l-2.5-2.5", "M19 16H8l2.5 2.5", "M19 8v4", "M5 16v-4"],
    close: ["M6 6l12 12", "M18 6 6 18"],
    back: ["m14 6-6 6 6 6", "M8 12h11"],
    chevron: ["m9 6 6 6-6 6"],
    upload: ["M12 16V5", "m8 9 4-4 4 4", "M5 19h14"],
    music: ["M9 18V6l9-2v12", "M9 18a3 3 0 1 1-3-3", "M18 16a3 3 0 1 1-3-3"],
  });

  function create(name, { size = 20, className = "roxy-icon", label = null } = {}) {
    const paths = ICONS[name];
    if (!paths) return null;
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", String(size));
    svg.setAttribute("height", String(size));
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.7");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.classList.add(className);
    if (label) {
      svg.setAttribute("role", "img");
      svg.setAttribute("aria-label", label);
    } else {
      svg.setAttribute("aria-hidden", "true");
    }
    for (const d of paths) {
      const path = document.createElementNS(NS, "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
    }
    return svg;
  }

  window.RoxyIcons = Object.freeze({
    create,
    names: Object.freeze(Object.keys(ICONS)),
  });
})();
