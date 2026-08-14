(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    models: [],
    musicModel: null,
    loading: false,
    observer: null,
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
      apply();
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
    apply();
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
    enableCreateCard();
    patchFamilyCards();
    patchBuilder();
    restoreGenericBuilderHeading();
    patchResultContainer(document.getElementById("resultCard"));
    patchResultContainer(document.getElementById("generationDetailView"));
    patchResultContainer(document.getElementById("ksuHistoryOverlay"));
    patchRecentCards();
  }

  function interceptMusicCard(event) {
    const card = event.target.closest?.('[data-roxy-media="audio"]');
    if (!card || !musicModel()) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    openMusicBuilder();
  }

  function init() {
    document.addEventListener("click", interceptMusicCard, true);
    document.getElementById("modelSelect")?.addEventListener("change", () => window.requestAnimationFrame(apply));
    void loadCatalog();
    apply();
    if (!state.observer && document.body) {
      state.observer = new MutationObserver(() => window.requestAnimationFrame(apply));
      state.observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    }
    tg?.onEvent?.("activated", apply);
  }

  window.RoxyMusic = Object.freeze({ open: openMusicBuilder, refresh: loadCatalog });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
