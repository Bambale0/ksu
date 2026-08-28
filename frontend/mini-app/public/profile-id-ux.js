(() => {
  const MARK_ATTR = "data-roxy-profile-user-id";
  const STYLE_ID = "roxy-profile-user-id-style";

  const currentUserId = () => {
    try {
      const value = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
      return value === undefined || value === null ? "" : String(value).trim();
    } catch {
      return "";
    }
  };

  const ensureStyle = () => {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .profile-screen .profile-copy [${MARK_ATTR}] {
        display: block;
        margin-top: 3px;
        color: rgba(255, 255, 255, .5);
        font-size: 10px;
        font-weight: 650;
        line-height: 1.25;
        letter-spacing: .015em;
        user-select: text;
        -webkit-user-select: text;
      }
    `;
    document.head.appendChild(style);
  };

  const decorate = () => {
    const id = currentUserId();
    if (!id) return false;

    let found = false;
    for (const profileCopy of document.querySelectorAll(".profile-screen .profile-copy")) {
      found = true;
      let label = profileCopy.querySelector(`[${MARK_ATTR}]`);
      if (!label) {
        label = document.createElement("span");
        label.setAttribute(MARK_ATTR, "");
        profileCopy.appendChild(label);
      }
      label.textContent = `ID ${id}`;
      label.setAttribute("aria-label", `Telegram ID ${id}`);
      label.setAttribute("title", `Telegram ID ${id}`);
    }
    return found;
  };

  const install = () => {
    ensureStyle();
    decorate();

    const observer = new MutationObserver(() => decorate());
    observer.observe(document.body, { childList: true, subtree: true });

    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      decorate();
      if (currentUserId() || attempts >= 40) window.clearInterval(timer);
    }, 250);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", install, { once: true });
  } else {
    install();
  }
})();
