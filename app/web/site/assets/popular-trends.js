/* Public ROXY AI STUDIO gallery. No Telegram SDK, private API or app bundle. */
(() => {
  "use strict";

  const gallery = document.getElementById("popular-trends");
  const status = document.getElementById("popular-trends-status");
  if (!gallery || !status) return;

  const limit = gallery.dataset.limit === "12" ? 12 : 6;
  const endpoint = limit === 12 ? "/api/v1/public-site/popular-trends?limit=12" : "/api/v1/public-site/popular-trends?limit=6";
  const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const saveData = navigator.connection?.saveData === true;
  const activeVideos = new Set();
  let controller;
  let loading = false;
  let videoObserver;

  const metric = (count) => {
    const num = Number.isFinite(Number(count)) ? Math.max(0, Math.trunc(Number(count))) : 0;
    if (!num) return "Новый тренд";
    return new Intl.NumberFormat("ru-RU").format(num) + " запусков";
  };

  const openTrendUrl = (id) => {
    const url = new URL("/mini-app/trend/", location.origin);
    url.searchParams.set("id", id);
    const current = new URLSearchParams(location.search);
    for (const name of ["startapp", "start_payload", "ref"]) {
      const value = current.get(name);
      if (value && value.length <= 256) url.searchParams.set(name, value);
    }
    return url.pathname + url.search;
  };

  const validMedia = (value) => {
    if (typeof value !== "string" || !value || value.length > 4000) return null;
    try {
      const src = new URL(value, location.origin);
      if (src.protocol !== "https:" && !(src.protocol === location.protocol && src.origin === location.origin)) return null;
      if (src.username || src.password) return null;
      return src.href;
    } catch { return null; }
  };

  const pauseAll = () => {
    for (const video of activeVideos) video.pause();
  };

  const playVisible = (video) => {
    if (document.visibilityState !== "visible" || reducedMotion.matches || saveData || !video.dataset.visible) {
      video.pause();
      return;
    }
    if (!video.src && video.dataset.src) {
      video.src = video.dataset.src;
    }
    const promise = video.play();
    if (promise && typeof promise.catch === "function") promise.catch(() => {});
  };

  const createObserver = () => {
    videoObserver?.disconnect();
    if (!("IntersectionObserver" in window)) return null;
    videoObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const video = entry.target;
        if (!(video instanceof HTMLVideoElement)) continue;
        if (entry.isIntersecting && entry.intersectionRatio >= 0.3) {
          video.dataset.visible = "1";
          playVisible(video);
        } else {
          delete video.dataset.visible;
          video.pause();
        }
      }
    }, { threshold: [0, 0.3, 0.55] });
    return videoObserver;
  };

  const buildTile = (item) => {
    if (!item || !uuid.test(String(item.id || ""))) return null;
    const mediaUrl = validMedia(item.preview_url);
    if (!mediaUrl) return null;

    const figure = document.createElement("figure");
    figure.className = "gallery-item live-trend-tile";
    const link = document.createElement("a");
    link.className = "live-trend-link";
    link.href = openTrendUrl(item.id);
    const title = String(item.title || "Тренд ROXY").trim().slice(0, 80) || "Тренд ROXY";
    link.setAttribute("aria-label", title + ". Открыть тренд");

    const isVideo = item.preview_kind === "video";
    if (isVideo) {
      const video = document.createElement("video");
      video.className = "live-trend-media";
      video.muted = true;
      video.loop = true;
      video.playsInline = true;
      video.preload = "none";
      video.setAttribute("muted", "");
      video.setAttribute("playsinline", "");
      video.setAttribute("disablepictureinpicture", "");
      video.dataset.src = mediaUrl;
      const poster = validMedia(item.poster_url);
      if (poster) video.poster = poster;
      video.setAttribute("aria-hidden", "true");
      video.tabIndex = -1;
      link.appendChild(video);
      activeVideos.add(video);
      if (videoObserver) videoObserver.observe(video);
    } else {
      const img = document.createElement("img");
      img.className = "live-trend-media";
      img.loading = "lazy";
      img.decoding = "async";
      img.alt = "";
      img.src = mediaUrl;
      link.appendChild(img);
    }

    const marker = document.createElement("span");
    marker.className = "live-trend-kind";
    marker.textContent = isVideo ? "▶ ВИДЕО" : "✦ ФОТО";
    marker.setAttribute("aria-hidden", "true");
    link.appendChild(marker);

    const caption = document.createElement("figcaption");
    const heading = document.createElement("strong");
    heading.textContent = title;
    const usage = document.createElement("span");
    usage.textContent = metric(item.usage_count);
    caption.append(heading, usage);
    figure.append(link, caption);
    return figure;
  };

  const showStatus = (message, retry = false) => {
    status.replaceChildren();
    status.hidden = false;
    const text = document.createElement("p");
    text.textContent = message;
    status.appendChild(text);
    if (retry) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button button-outline";
      button.textContent = "Попробовать ещё раз";
      button.addEventListener("click", () => void load());
      status.appendChild(button);
    }
  };

  const load = async () => {
    if (loading) return;
    loading = true;
    controller?.abort();
    controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    showStatus("Загружаем популярные тренды…");
    try {
      const response = await fetch(endpoint, {
        signal: controller.signal,
        credentials: "omit",
        cache: "default",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const body = await response.json();
      if (!body || !Array.isArray(body.items)) throw new TypeError("Invalid trend response");
      const unique = new Set();
      const items = body.items.filter((item) => {
        if (!item || !uuid.test(String(item.id)) || unique.has(item.id)) return false;
        unique.add(item.id);
        return true;
      }).slice(0, limit);
      activeVideos.clear();
      createObserver();
      const tiles = items.map(buildTile).filter(Boolean);
      if (!tiles.length) {
        gallery.replaceChildren();
        gallery.dataset.loaded = "empty";
        showStatus("Пока нет доступных трендов с превью. Загляни в каталог ROXY.");
        return;
      }
      gallery.replaceChildren(...tiles);
      gallery.dataset.loaded = "true";
      status.hidden = true;
    } catch {
      gallery.dataset.loaded = "error";
      showStatus("Не удалось загрузить тренды. Проверь соединение и попробуй снова.", true);
    } finally {
      clearTimeout(timeout);
      loading = false;
    }
  };

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) pauseAll();
    else {
      for (const video of activeVideos) if (video.dataset.visible) playVisible(video);
    }
  });
  reducedMotion.addEventListener?.("change", () => {
    if (reducedMotion.matches) pauseAll();
    else for (const video of activeVideos) if (video.dataset.visible) playVisible(video);
  });
  window.addEventListener("pagehide", pauseAll);

  if ("IntersectionObserver" in window) {
    const bootstrap = new IntersectionObserver((entries) => {
      if (!entries[0]?.isIntersecting) return;
      bootstrap.disconnect();
      void load();
    }, { rootMargin: "850px 0px" });
    bootstrap.observe(gallery);
  } else {
    void load();
  }
})();
