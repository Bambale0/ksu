(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    models: [],
    musicModel: null,
    loading: false,
    frame: 0,
  };

  function haptic(kind = "medium") {
    try { tg?.HapticFeedback?.impactOccurred?.(kind); } catch (_error) { /* optional */ }
  }

  function setText(node, value) {
    if (node && node.textContent !== value) node.textContent = value;
  }

  function musicModel() {
    return state.musicModel || state.models.find((model) => model.media_type === "audio") || null;
  }

  async function loadCatalog() {
    if (state.loading || state.musicModel) return;
    state.loading = true;
    try {
      const response = await fetch("/api/v1/generations/models", {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      state.models = Array.isArray(payload?.models) ? payload.models : [];
      state.musicModel = state.models.find((model) => model.media_type === "audio") || null;
    } catch (_error) {
      state.musicModel = null;
    } finally {
      state.loading = false;
      scheduleApply();
    }
  }

  function enableCreateCard() {
    const card = document.querySelector('[data-roxy-media="audio"]');
    if (!card) return;
    const model = musicModel();
    if (card.disabled === Boolean(model)) card.disabled = !model;
    card.classList.toggle("is-disabled", !model);
    const aria = model ? "false" : "true";
    if (card.getAttribute("aria-disabled") !== aria) card.setAttribute("aria-disabled", aria);
    setText(card.querySelector('[data-roxy-media-count="audio"]'), model ? "Suno V5.5" : "Недоступно");
    if (model) setText(card.querySelector(".roxy-media-card-copy small"), "Песня или инструментальный трек через Suno");
  }

  function closeCreateCenter() {
    const center = document.getElementById("roxyCreateCenterView");
    if (center) center.hidden = true;
    document.body?.classList.remove("roxy-create-center-open");
    const createView = document.getElementById("createView");
    if (createView) createView.hidden = false;
  }

  function selectMusicModel(modelId, attempt = 0) {
    const select = document.getElementById("modelSelect");
    if (!select) {
      if (attempt < 50) window.setTimeout(() => selectMusicModel(modelId, attempt + 1), 60);
      return;
    }
    const option = [...select.options].find((item) => item.value === modelId);
    if (!option) {
      if (attempt < 50) window.setTimeout(() => selectMusicModel(modelId, attempt + 1), 60);
      return;
    }
    if (select.value !== modelId) {
      select.value = modelId;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    scheduleApply();
  }

  function openMusicBuilder() {
    const model = musicModel();
    if (!model) {
      void loadCatalog();
      return;
    }
    haptic();
    localStorage.setItem("ksu-selected-model", model.id);
    closeCreateCenter();
    // Keep the canonical route as Create. The legacy shell only exposes the builder host;
    // changing ROXY to Home here made Back skip the Create format chooser.
    window.KsuStudioShell?.open?.("home");

    const enter = (attempt = 0) => {
      const card = [...document.querySelectorAll(".shell-family-card")]
        .find((item) => item.dataset.family === model.family);
      if (card) {
        card.click();
        selectMusicModel(model.id, 0);
        return;
      }
      if (attempt < 50) window.setTimeout(() => enter(attempt + 1), 60);
    };
    enter();
  }

  function selectedIsMusic() {
    const selected = document.getElementById("modelSelect")?.value;
    return Boolean(selected && selected === musicModel()?.id);
  }

  function patchBuilder() {
    const isMusic = selectedIsMusic();
    const helper = document.getElementById("roxyPromptHelper");
    if (helper && helper.hidden !== isMusic) helper.hidden = isMusic;

    if (!isMusic) return;
    setText(document.querySelector("#builderView .view-heading h1"), "Создать музыку");
    setText(document.getElementById("settingsHeading"), "Параметры трека");
    document.querySelectorAll("#modelMeta .meta-pill").forEach((pill) => {
      if (/изображение|image/i.test(pill.textContent || "")) setText(pill, "Музыка");
    });
    setText(document.getElementById("summaryHeading"), "Ваш трек");
  }

  function patchFamilyCards() {
    const model = musicModel();
    if (!model) return;
    const card = [...document.querySelectorAll(".shell-family-card")]
      .find((item) => item.dataset.family === model.family);
    if (card) {
      setText(card.querySelector(".shell-family-icon"), "♪");
      setText(card.querySelector("strong"), "Музыка");
      setText(card.querySelector("small"), "Suno · AI music");
    }
    document.querySelectorAll(".family-tab").forEach((tab) => {
      if (/^suno$/i.test(tab.textContent?.trim() || "")) setText(tab, "Suno Music");
    });
  }

  function audioLike(url) {
    return /\.(mp3|wav|ogg|m4a|flac|aac|opus)(\?|$)/i.test(String(url || ""));
  }

  function musicContainer(container) {
    if (!container) return false;
    const text = container.textContent || "";
    return /Suno V5\.5|Suno.*Music|Музыка/i.test(text);
  }

  function audioPlayer(src, label = "Сгенерированный трек") {
    const audio = document.createElement("audio");
    audio.className = "roxy-audio-player";
    audio.controls = true;
    audio.preload = "metadata";
    audio.src = src;
    audio.setAttribute("aria-label", label);
    return audio;
  }

  function patchResultContainer(container) {
    if (!container) return;
    const isMusic = musicContainer(container);
    container.querySelectorAll(".ksu-result-media img, .shell-detail-media img").forEach((image, index) => {
      const src = image.currentSrc || image.src || "";
      if (!isMusic && !audioLike(src)) return;
      image.replaceWith(audioPlayer(src, `Сгенерированный трек ${index + 1}`));
    });
  }

  function patchRecentCards() {
    if (!musicModel()) return;
    document.querySelectorAll(".shell-generation-card, .active-generation-card").forEach((card) => {
      const title = card.querySelector(".generation-copy strong")?.textContent || "";
      if (!/Suno V5\.5|Suno.*Music/i.test(title)) return;
      const thumb = card.querySelector(".generation-thumb");
      if (thumb && !thumb.querySelector("img,video,audio")) setText(thumb, "♪");
    });
  }

  function restoreGenericBuilderHeading() {
    if (selectedIsMusic()) return;
    const heading = document.querySelector("#builderView .view-heading h1");
    if (heading?.textContent === "Создать музыку") setText(heading, "Настройте генерацию");
    const settings = document.getElementById("settingsHeading");
    if (settings?.textContent === "Параметры трека") setText(settings, "Настройки");
    const summary = document.getElementById("summaryHeading");
    if (summary?.textContent === "Ваш трек") setText(summary, "Вы выбрали");
  }

  function apply() {
    state.frame = 0;
    enableCreateCard();
    patchFamilyCards();
    patchBuilder();
    restoreGenericBuilderHeading();
    patchResultContainer(document.getElementById("resultCard"));
    patchResultContainer(document.getElementById("generationDetailView"));
    patchResultContainer(document.getElementById("ksuHistoryOverlay"));
    patchRecentCards();
  }

  function scheduleApply() {
    if (state.frame) return;
    state.frame = window.requestAnimationFrame(apply);
  }

  function interceptMusicCard(event) {
    const card = event.target.closest?.('[data-roxy-media="audio"]');
    if (!card || !musicModel()) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    openMusicBuilder();
  }

  function handleExplicitUiAction(event) {
    const control = event.target.closest?.(
      [
        "#modelSelect",
        "[data-roxy-customer-route]",
        "[data-shell-nav]",
        ".ksu-history-action",
        ".shell-generation-card",
        ".active-generation-card",
        "#createButton",
      ].join(", "),
    );
    if (!control) return;
    scheduleApply();
  }

  function handleRenderedMedia(event) {
    const media = event.target;
    if (!(media instanceof HTMLImageElement || media instanceof HTMLVideoElement || media instanceof HTMLAudioElement)) return;
    const container = media.closest?.("#resultCard, #generationDetailView, #ksuHistoryOverlay");
    if (!container) return;
    scheduleApply();
  }

  function init() {
    document.addEventListener("click", interceptMusicCard, true);
    document.addEventListener("click", handleExplicitUiAction, true);
    document.addEventListener("change", handleExplicitUiAction, true);
    document.addEventListener("load", handleRenderedMedia, true);
    document.addEventListener("error", handleRenderedMedia, true);
    void loadCatalog();
    scheduleApply();
    for (const delay of [80, 240, 700]) window.setTimeout(scheduleApply, delay);
    tg?.onEvent?.("activated", scheduleApply);
    window.addEventListener("roxy:route-changed", scheduleApply);
    window.addEventListener("roxy:shell-route-changed", scheduleApply);
    window.addEventListener("roxy:generation-updated", scheduleApply);
    window.addEventListener("roxy:history-updated", scheduleApply);
  }

  window.RoxyMusic = Object.freeze({ open: openMusicBuilder, refresh: loadCatalog });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
