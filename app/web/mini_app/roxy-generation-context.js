(() => {
  "use strict";

  const tg = window.Telegram?.WebApp ?? null;
  const state = {
    historyItems: [],
    currentGeneration: null,
    pendingGenerationId: null,
    historyBusy: false,
    resultBusy: false,
    historyFrame: 0,
    resultFrame: 0,
    historyObserver: null,
    resultObserver: null,
    historyRoot: null,
    resultRoot: null,
  };

  function authHeaders() {
    const headers = { Accept: "application/json" };
    if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    return headers;
  }

  async function api(path) {
    const response = await fetch(path, {
      headers: authHeaders(),
      credentials: "same-origin",
      cache: "no-store",
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const error = new Error(typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function emit(name, detail) {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  }

  function publishHistory() {
    emit("roxy:history-context", { items: [...state.historyItems] });
  }

  function publishGeneration(generation) {
    state.currentGeneration = generation || null;
    emit("roxy:generation-context", { generation: state.currentGeneration });
  }

  function historyCards() {
    return [...(state.historyRoot?.querySelectorAll(".ksu-history-card") || [])];
  }

  function decorateHistoryCards() {
    const cards = historyCards();
    cards.forEach((card, index) => {
      const generation = state.historyItems[index];
      if (generation?.id) card.dataset.generationId = generation.id;
    });
  }

  async function fetchHistoryForCardCount(count) {
    const collected = [];
    let before = null;
    let hasMore = true;
    while (hasMore && collected.length < Math.max(count, 1) && collected.length < 200) {
      const query = new URLSearchParams({ limit: "50" });
      if (before) query.set("before", before);
      const page = await api(`/api/v1/generations?${query}`);
      const items = Array.isArray(page?.items) ? page.items : [];
      collected.push(...items);
      hasMore = Boolean(page?.has_more && page?.next_before && items.length);
      before = hasMore ? page.next_before : null;
    }
    return collected;
  }

  async function refreshHistory() {
    if (!tg?.initData || state.historyBusy) return;
    const root = document.getElementById("ksuHistoryList");
    if (!root) return;
    state.historyRoot = root;
    state.historyBusy = true;
    try {
      state.historyItems = await fetchHistoryForCardCount(historyCards().length);
      decorateHistoryCards();
      publishHistory();
    } catch (_error) {
      // Context is progressive enhancement; the base history stays usable.
    } finally {
      state.historyBusy = false;
    }
  }

  function scheduleHistoryRefresh() {
    if (state.historyFrame) return;
    state.historyFrame = window.requestAnimationFrame(() => {
      state.historyFrame = 0;
      void refreshHistory();
    });
  }

  async function generationById(generationId) {
    if (!generationId) return null;
    try {
      return await api(`/api/v1/generations/${encodeURIComponent(generationId)}`);
    } catch (_error) {
      return null;
    }
  }

  async function latestGeneration() {
    try {
      const page = await api("/api/v1/generations?limit=1");
      return Array.isArray(page?.items) ? page.items[0] || null : null;
    } catch (_error) {
      return null;
    }
  }

  async function refreshResult() {
    if (!tg?.initData || state.resultBusy) return;
    const root = document.getElementById("resultCard");
    if (!root || root.hidden || !root.childElementCount) return;
    state.resultRoot = root;
    state.resultBusy = true;
    try {
      let generation = null;
      const targetId = state.pendingGenerationId || state.currentGeneration?.id || null;
      if (targetId) generation = await generationById(targetId);
      if (!generation) generation = await latestGeneration();
      if (!generation) return;
      state.pendingGenerationId = null;
      publishGeneration(generation);
    } finally {
      state.resultBusy = false;
    }
  }

  function scheduleResultRefresh() {
    if (state.resultFrame) return;
    state.resultFrame = window.requestAnimationFrame(() => {
      state.resultFrame = 0;
      void refreshResult();
    });
  }

  function setPendingGenerationId(generationId) {
    state.pendingGenerationId = generationId || null;
    if (generationId) scheduleResultRefresh();
  }

  function onHistoryAction(event) {
    const action = event.target.closest?.(".ksu-history-action");
    if (!action) return;
    const card = action.closest(".ksu-history-card");
    const generationId = card?.dataset.generationId;
    if (!generationId) return;
    const label = String(action.textContent || "").trim().toLowerCase();
    if (label.startsWith("открыть")) {
      state.pendingGenerationId = generationId;
      state.currentGeneration = null;
    }
  }

  function onCreateIntent(event) {
    if (!event.target.closest?.("#createButton")) return;
    state.pendingGenerationId = null;
    state.currentGeneration = null;
  }

  function attachHistoryObserver() {
    const root = document.getElementById("ksuHistoryList");
    if (!root || root === state.historyRoot && state.historyObserver) return Boolean(root);
    state.historyRoot = root;
    state.historyObserver?.disconnect();
    state.historyObserver = new MutationObserver(scheduleHistoryRefresh);
    state.historyObserver.observe(root, { childList: true });
    root.addEventListener("click", onHistoryAction, true);
    scheduleHistoryRefresh();
    return true;
  }

  function attachResultObserver() {
    const root = document.getElementById("resultCard");
    if (!root || root === state.resultRoot && state.resultObserver) return Boolean(root);
    state.resultRoot = root;
    state.resultObserver?.disconnect();
    state.resultObserver = new MutationObserver(scheduleResultRefresh);
    state.resultObserver.observe(root, {
      childList: true,
      attributes: true,
      attributeFilter: ["hidden"],
    });
    scheduleResultRefresh();
    return true;
  }

  function attachUntilReady() {
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      const historyReady = attachHistoryObserver();
      const resultReady = attachResultObserver();
      if ((historyReady && resultReady) || attempts >= 60) window.clearInterval(timer);
    }, 100);
  }

  function init() {
    document.addEventListener("click", onCreateIntent, true);
    attachUntilReady();
    window.addEventListener("roxy:history-changed", scheduleHistoryRefresh);
    window.addEventListener("roxy:route-changed", (event) => {
      if (event.detail?.route === "history") scheduleHistoryRefresh();
    });
    tg?.onEvent?.("activated", () => {
      scheduleHistoryRefresh();
      scheduleResultRefresh();
    });
    window.setTimeout(() => {
      scheduleHistoryRefresh();
      scheduleResultRefresh();
    }, 250);

    window.RoxyGenerationContext = Object.freeze({
      refreshHistory,
      refreshResult,
      setPendingGenerationId,
      get current() {
        return state.currentGeneration;
      },
      get historyItems() {
        return [...state.historyItems];
      },
    });
    emit("roxy:generation-context-ready", {});
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
