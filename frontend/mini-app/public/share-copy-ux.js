(() => {
  const PATCH_MARK = "__roxyShareCopyUxPatched";
  const ROOT_ID = "roxy-share-copy-sheet";
  const STYLE_ID = "roxy-share-copy-style";

  const haptic = (kind = "light") => {
    try { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.(kind); } catch {}
  };

  const notify = (kind) => {
    try { window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.(kind); } catch {}
  };

  const copyText = async (text) => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch {}

    try {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      textarea.style.pointerEvents = "none";
      document.body.appendChild(textarea);
      textarea.select();
      textarea.setSelectionRange(0, textarea.value.length);
      const copied = document.execCommand("copy");
      textarea.remove();
      return copied;
    } catch {
      return false;
    }
  };

  const ensureStyle = () => {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      #${ROOT_ID} {
        position: fixed;
        z-index: 10000;
        inset: 0;
        display: flex;
        align-items: flex-end;
        justify-content: center;
        font-family: inherit;
      }
      #${ROOT_ID} .roxy-share-backdrop {
        position: absolute;
        inset: 0;
        border: 0;
        background: rgba(0,0,0,.68);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
      }
      #${ROOT_ID} .roxy-share-sheet {
        position: relative;
        z-index: 1;
        width: min(100%, 620px);
        padding: 12px max(16px, var(--tg-safe-right, 0px)) calc(18px + var(--tg-safe-bottom, 0px)) max(16px, var(--tg-safe-left, 0px));
        border: 1px solid rgba(188,137,255,.24);
        border-bottom: 0;
        border-radius: 26px 26px 0 0;
        background: rgba(15,13,21,.985);
        box-shadow: 0 -28px 80px rgba(0,0,0,.58), 0 0 38px rgba(155,92,255,.08);
        color: #fff;
      }
      #${ROOT_ID} .roxy-share-handle {
        width: 42px;
        height: 4px;
        margin: 0 auto 14px;
        border-radius: 999px;
        background: rgba(255,255,255,.2);
      }
      #${ROOT_ID} .roxy-share-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 14px;
      }
      #${ROOT_ID} .roxy-share-title {
        margin: 0;
        font-size: 19px;
        font-weight: 900;
        letter-spacing: -.02em;
      }
      #${ROOT_ID} .roxy-share-close {
        width: 38px;
        height: 38px;
        padding: 0;
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 50%;
        background: rgba(255,255,255,.045);
        color: #fff;
        font-size: 22px;
        line-height: 1;
      }
      #${ROOT_ID} .roxy-share-actions {
        display: grid;
        gap: 10px;
      }
      #${ROOT_ID} .roxy-share-action {
        width: 100%;
        min-height: 54px;
        padding: 12px 15px;
        border: 1px solid rgba(194,151,255,.23);
        border-radius: 17px;
        display: flex;
        align-items: center;
        justify-content: flex-start;
        gap: 12px;
        background: rgba(255,255,255,.045);
        color: #fff;
        text-align: left;
        font: inherit;
        font-size: 14px;
        font-weight: 850;
      }
      #${ROOT_ID} .roxy-share-action.primary {
        border-color: rgba(190,137,255,.44);
        background: linear-gradient(110deg, rgba(130,72,226,.72), rgba(191,73,207,.5));
        box-shadow: 0 10px 28px rgba(130,72,226,.14);
      }
      #${ROOT_ID} .roxy-share-icon {
        width: 34px;
        height: 34px;
        flex: 0 0 34px;
        display: grid;
        place-items: center;
        border-radius: 11px;
        background: rgba(255,255,255,.1);
        font-size: 17px;
      }
      #${ROOT_ID} .roxy-share-copy {
        min-width: 0;
        display: grid;
        gap: 2px;
      }
      #${ROOT_ID} .roxy-share-copy small {
        color: rgba(255,255,255,.62);
        font-size: 10px;
        font-weight: 650;
      }
      #${ROOT_ID} .roxy-share-status {
        min-height: 18px;
        margin: 10px 2px 0;
        color: rgba(255,255,255,.68);
        font-size: 11px;
        text-align: center;
      }
    `;
    document.head.appendChild(style);
  };

  const closeSheet = () => {
    document.getElementById(ROOT_ID)?.remove();
  };

  const showSheet = (targetLink, continueTelegramShare) => {
    closeSheet();
    ensureStyle();

    const root = document.createElement("div");
    root.id = ROOT_ID;
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute("aria-label", "Поделиться работой");
    root.innerHTML = `
      <button class="roxy-share-backdrop" type="button" aria-label="Закрыть"></button>
      <section class="roxy-share-sheet">
        <div class="roxy-share-handle"></div>
        <div class="roxy-share-head">
          <h2 class="roxy-share-title">Поделиться работой</h2>
          <button class="roxy-share-close" type="button" aria-label="Закрыть">×</button>
        </div>
        <div class="roxy-share-actions">
          <button class="roxy-share-action primary roxy-copy-link" type="button">
            <span class="roxy-share-icon">⧉</span>
            <span class="roxy-share-copy"><strong>Скопировать ссылку</strong><small>Сразу в буфер обмена</small></span>
          </button>
          <button class="roxy-share-action roxy-telegram-share" type="button">
            <span class="roxy-share-icon">↗</span>
            <span class="roxy-share-copy"><strong>Поделиться в Telegram</strong><small>Отправить в чат или канал</small></span>
          </button>
        </div>
        <div class="roxy-share-status" role="status" aria-live="polite"></div>
      </section>
    `;

    const status = root.querySelector(".roxy-share-status");
    const copyButton = root.querySelector(".roxy-copy-link");
    const telegramButton = root.querySelector(".roxy-telegram-share");

    root.querySelector(".roxy-share-backdrop")?.addEventListener("click", closeSheet);
    root.querySelector(".roxy-share-close")?.addEventListener("click", closeSheet);

    copyButton?.addEventListener("click", async () => {
      copyButton.disabled = true;
      const copied = await copyText(targetLink);
      if (copied) {
        if (status) status.textContent = "Ссылка скопирована ✓";
        copyButton.querySelector("strong").textContent = "Скопировано ✓";
        notify("success");
        haptic("light");
        window.setTimeout(closeSheet, 650);
      } else {
        if (status) status.textContent = "Не удалось скопировать ссылку";
        copyButton.disabled = false;
        notify("error");
      }
    });

    telegramButton?.addEventListener("click", () => {
      haptic("light");
      closeSheet();
      continueTelegramShare();
    });

    document.body.appendChild(root);
    haptic("light");
    window.setTimeout(() => copyButton?.focus(), 0);
  };

  const parseTelegramShare = (rawUrl) => {
    try {
      const url = new URL(String(rawUrl || ""), window.location.href);
      const host = url.hostname.toLowerCase();
      if (host !== "t.me" && host !== "telegram.me") return null;
      if (url.pathname.replace(/\/$/, "") !== "/share/url") return null;
      const targetLink = String(url.searchParams.get("url") || "").trim();
      return targetLink ? targetLink : null;
    } catch {
      return null;
    }
  };

  const install = () => {
    const webApp = window.Telegram?.WebApp;
    if (!webApp || typeof webApp.openTelegramLink !== "function") return false;
    if (webApp[PATCH_MARK]) return true;

    const originalOpenTelegramLink = webApp.openTelegramLink.bind(webApp);
    webApp.openTelegramLink = (rawUrl) => {
      const targetLink = parseTelegramShare(rawUrl);
      if (!targetLink) {
        originalOpenTelegramLink(rawUrl);
        return;
      }

      showSheet(targetLink, () => originalOpenTelegramLink(rawUrl));
    };
    webApp[PATCH_MARK] = true;
    return true;
  };

  if (install()) return;

  let attempts = 0;
  const timer = window.setInterval(() => {
    attempts += 1;
    if (install() || attempts >= 40) window.clearInterval(timer);
  }, 250);
})();
