/* First-party ROXY AI STUDIO login. All identity proof is server-side. */
(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const message = byId("auth-message");
  const params = new URLSearchParams(location.search);
  const approved = ["startapp", "start_payload", "ref"];
  const nextUrl = new URL("/mini-app/", location.origin);
  for (const name of approved) {
    const value = params.get(name);
    if (value && value.length <= 256) nextUrl.searchParams.set(name, value);
  }
  const next = nextUrl.pathname + nextUrl.search;
  const linkMode = params.get("mode") === "link";
  let activeLink = linkMode;
  let signedIn = false;
  let pendingEmail = "";

  const announce = (content, kind = "info") => {
    message.hidden = !content;
    message.textContent = content;
    message.dataset.kind = kind;
  };

  const handleResponse = async (response) => {
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = result.detail;
      throw new Error(typeof error === "string" ? error : "Не удалось выполнить запрос. Попробуй позже.");
    }
    return result;
  };

  const send = (url, payload) => fetch(url, {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  }).then(handleResponse);

  const setDisabled = (node, reason) => {
    node.setAttribute("aria-disabled", "true");
    node.setAttribute("title", reason);
    if (node.tagName === "BUTTON") node.disabled = true;
  };

  const goToStudio = () => { window.location.assign(next); };

  function setLinkMode(value) {
    activeLink = Boolean(value);
    byId("auth-existing").hidden = activeLink || !signedIn;
    byId("auth-providers").hidden = signedIn && !activeLink;
    byId("auth-link-notice").hidden = !activeLink;
    byId("auth-yandex-button").href =
      "/api/v1/web-auth/yandex/start?" + new URLSearchParams({
        next, ...(activeLink ? { link: "true" } : {}),
      }).toString();
    announce(activeLink ? "Подтверди дополнительный способ входа, чтобы привязать его к текущему аккаунту." : "");
  }

  async function loadSession() {
    try {
      const response = await fetch("/api/v1/web-auth/me", { credentials: "same-origin", cache: "no-store" });
      const user = await handleResponse(response);
      signedIn = user.authenticated === true;
      if (signedIn) {
        byId("auth-account-name").textContent = String(user.first_name || "ROXY");
        byId("auth-continue").href = next;
      }
      setLinkMode(activeLink && signedIn);
    } catch {
      signedIn = false;
      setLinkMode(false);
    }
  }

  async function setupProviders() {
    try {
      const response = await fetch("/api/v1/web-auth/config", { cache: "no-store" });
      const config = await handleResponse(response);
      const enabled = config.providers || {};

      if (enabled.telegram && /^[A-Za-z0-9_]+$/.test(String(config.bot_username || ""))) {
        window.onRoxyLoginAuth = async (telegramUser) => {
          try {
            announce("Проверяем вход Telegram…");
            await send("/api/v1/web-auth/telegram", {
              telegram_auth: telegramUser,
              link: activeLink,
            });
            if (activeLink) {
              window.location.assign("/login?linked=1");
            } else {
              goToStudio();
            }
          } catch (error) {
            announce(error.message || "Не удалось проверить Telegram.", "error");
          }
        };
        const script = document.createElement("script");
        script.async = true;
        script.src = "https://telegram.org/js/telegram-widget.js?22";
        script.setAttribute("data-telegram-login", config.bot_username);
        script.setAttribute("data-size", "large");
        script.setAttribute("data-radius", "5");
        script.setAttribute("data-onauth", "onRoxyLoginAuth(user)");
        script.setAttribute("data-request-access", "write");
        script.onerror = () => announce("Не удалось загрузить виджет Telegram. Проверь доступ к Telegram и перезагрузи страницу.", "error");
        byId("auth-telegram-widget").appendChild(script);
      } else {
        byId("auth-telegram-widget").textContent = "Вход через Telegram пока не настроен.";
      }

      if (!enabled.yandex) {
        const button = byId("auth-yandex-button");
        setDisabled(button, "Не настроено подключение Яндекс ID");
        button.removeAttribute("href");
        button.querySelectorAll("span")[1].textContent = "Яндекс ID пока недоступен";
      }

      if (!enabled.email) {
        setDisabled(byId("auth-email-send"), "Почтовый провайдер пока не настроен");
        byId("auth-email-input").disabled = true;
        byId("auth-email-form").insertAdjacentHTML(
          "afterend",
          '<p class="auth-note">Вход по почте появится после настройки отправки кодов.</p>',
        );
      }
    } catch {
      announce("Не удалось получить настройки способов входа. Обнови страницу позже.", "error");
      byId("auth-telegram-widget").textContent = "Сервис входа недоступен.";
      setDisabled(byId("auth-email-send"), "Сервис входа недоступен");
      setDisabled(byId("auth-yandex-button"), "Сервис входа недоступен");
      byId("auth-yandex-button").removeAttribute("href");
    }
  }

  byId("auth-email-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = byId("auth-email-input").value.trim();
    if (!byId("auth-email-input").checkValidity()) {
      announce("Введите корректный адрес электронной почты.", "error");
      return;
    }
    byId("auth-email-send").disabled = true;
    try {
      const result = await send("/api/v1/web-auth/email/request", { email });
      pendingEmail = email;
      byId("auth-code-form").hidden = false;
      byId("auth-code-input").focus();
      announce(result.message || "Код отправлен. Проверь почту.");
    } catch (error) {
      announce(error.message || "Не удалось отправить код.", "error");
    } finally {
      byId("auth-email-send").disabled = false;
    }
  });

  byId("auth-code-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const code = byId("auth-code-input").value.trim();
    if (!/^\d{6}$/.test(code) || !pendingEmail) {
      announce("Введите шесть цифр из письма.", "error");
      return;
    }
    byId("auth-code-submit").disabled = true;
    try {
      announce("Подтверждаем почту…");
      await send("/api/v1/web-auth/email/verify", {
        email: pendingEmail, code, link: activeLink,
      });
      if (activeLink) {
        window.location.assign("/login?linked=1");
      } else {
        goToStudio();
      }
    } catch (error) {
      announce(error.message || "Код не подошёл.", "error");
    } finally {
      byId("auth-code-submit").disabled = false;
    }
  });

  byId("auth-link").addEventListener("click", () => {
    const url = new URL(location.href);
    url.searchParams.set("mode", "link");
    history.replaceState({}, "", url);
    setLinkMode(true);
  });

  byId("auth-logout").addEventListener("click", async () => {
    try {
      await send("/api/v1/web-auth/logout", {});
      window.location.replace("/login");
    } catch (error) {
      announce(error.message || "Не удалось выйти.", "error");
    }
  });

  if (params.get("linked") === "1") {
    announce("Способ входа привязан к текущему аккаунту.");
  } else if (params.get("error") === "yandex") {
    announce("Вход через Яндекс отменён или не завершён.", "error");
  }
  void Promise.all([loadSession(), setupProviders()]);
})();
