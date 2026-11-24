(() => {
  "use strict";
  const key = "__roxy_browser_init_data_v1";
  const query = new URLSearchParams(location.search);
  const approved = new URLSearchParams();
  for (const name of ["startapp", "start_payload", "ref"]) {
    const value = query.get(name);
    if (value && value.length <= 256) approved.set(name, value);
  }
  const trend = query.get("trend") || "";
  const validTrend = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(trend);
  const target = new URL(validTrend ? "/mini-app/trend/" : "/mini-app/", location.origin);
  if (validTrend) target.searchParams.set("id", trend);
  else {
    const tool = query.get("tool") || "";
    if (["partners","profile"].includes(query.get("section"))) {
      target.searchParams.set("route",query.get("section"));
    } else if (["photo","video","text","own-photo","reference"].includes(tool)) {
      target.searchParams.set("route","create");
      if (tool === "video") target.searchParams.set("create_media","video");
      else if (tool === "photo" || tool === "own-photo") target.searchParams.set("create_media","image");
    }
  }
  for (const [name, value] of approved) target.searchParams.set(name, value);
  const destination = target.pathname + target.search;
  const status = document.getElementById("login-status");
  const widget = document.getElementById("login-widget");
  const retry = document.getElementById("login-retry");
  const proceed = document.getElementById("login-continue");
  const hint = document.getElementById("login-target");
  const extra = document.getElementById("login-extra");
  const yandex = document.getElementById("login-yandex");
  const emailForm = document.getElementById("login-email-form");
  const codeForm = document.getElementById("login-code-form");
  const emailInput = document.getElementById("login-email");
  const codeInput = document.getElementById("login-code");
  const link = document.getElementById("login-link");
  const logout = document.getElementById("login-logout");
  let useWeb = false;
  let linkMode = false;
  let cookieSession = false;
  let pendingEmail = "";
  let busy = false;
  let loading = false;
  if (validTrend) hint.hidden = false;

  function message(text, error = false) {
    status.textContent = text;
    status.setAttribute("role", error ? "alert" : "status");
    retry.hidden = !error;
  }
  function savedCredential() {
    try {
      const raw = JSON.parse(sessionStorage.getItem(key) || "null");
      if (typeof raw?.initData === "string" && raw.initData && Number.isFinite(raw.expiresAt) && raw.expiresAt > Date.now()) return raw.initData;
      sessionStorage.removeItem(key);
    } catch {}
    return "";
  }
  async function existingSession() {
    const web = await fetch("/api/v1/web-auth/me", {credentials:"same-origin",cache:"no-store"});
    if (web.status !== 404) {
      if (!web.ok) throw new Error("session unavailable");
      const session = await web.json();
      if (session.authenticated === true) {
        sessionStorage.removeItem(key);
        cookieSession = true;
        linkMode = query.get("mode") === "link";
        logout.hidden = false;
        if (linkMode) return false;
        proceed.href = destination;
        proceed.hidden = false;
        link.hidden = false;
        message("Ты уже вошёл в аккаунт. Продолжи в студии.");
        return true;
      }
    }
    const credential = savedCredential();
    if (!credential) return false;
    const result = await fetch("/api/v1/me", {credentials:"same-origin",cache:"no-store",headers:{"X-Telegram-Init-Data":credential}});
    if (result.ok && query.get("mode") !== "link") {
      proceed.href = destination;
      proceed.hidden = false;
      logout.hidden = false;
      message("Ты уже вошёл в аккаунт. Продолжи в студии.");
      return true;
    }
    if (result.status === 401 || result.status === 403) sessionStorage.removeItem(key);
    return false;
  }
  async function send(path, payload) {
    const response = await fetch(path,{method:"POST",credentials:"same-origin",cache:"no-store",headers:{"Accept":"application/json","Content-Type":"application/json"},body:JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok || data.ok !== true) throw new Error("request failed");
    return data;
  }
  function finishWebLogin() {
    sessionStorage.removeItem(key);
    location.assign(linkMode ? "/login?linked=1" : destination);
  }
  emailForm.addEventListener("submit", async event => {
    event.preventDefault();
    if (busy || !useWeb || !emailForm.checkValidity()) return;
    busy = true;
    const button = emailForm.querySelector("button");
    button.disabled = true;
    try {
      const email = emailInput.value.trim();
      await send("/api/v1/web-auth/email/request",{email});
      pendingEmail = email;
      codeForm.hidden = false;
      codeInput.focus();
      message("Код отправлен. Он действителен 10 минут.");
    } catch { message("Не удалось отправить код. Попробуй позже.",true); }
    finally { busy = false; button.disabled = false; }
  });
  codeForm.addEventListener("submit", async event => {
    event.preventDefault();
    if (busy || !useWeb || !pendingEmail || !codeForm.checkValidity()) return;
    busy = true;
    const button = codeForm.querySelector("button");
    button.disabled = true;
    try {
      await send("/api/v1/web-auth/email/verify",{email:pendingEmail,code:codeInput.value.trim(),link:linkMode});
      finishWebLogin();
    } catch { message("Не удалось подтвердить код или привязать аккаунт. Запроси новый код.",true); }
    finally { busy = false; button.disabled = false; }
  });
  logout.addEventListener("click", async () => {
    if (busy) return;
    busy = true;
    logout.disabled = true;
    try {
      if (cookieSession) await send("/api/v1/web-auth/logout",{});
      sessionStorage.removeItem(key);
      location.replace("/login");
    } catch { message("Сервер не подтвердил выход. Повтори попытку.",true); }
    finally { busy = false; logout.disabled = false; }
  });
  window.onRoxyTelegramAuth = async (user) => {
    if (busy) return;
    busy = true;
    message("Входим в ROXY…");
    try {
      if (useWeb) {
        await send("/api/v1/web-auth/telegram",{telegram_auth:user,link:linkMode});
        finishWebLogin();
        return;
      }
      const response = await fetch("/api/v1/browser-auth", {
        method:"POST", credentials:"same-origin", cache:"no-store",
        headers:{"Accept":"application/json","Content-Type":"application/json"},
        body:JSON.stringify({telegram_auth:user}),
      });
      const payload = await response.json();
      const ttl = Number(payload.expires_in);
      if (!response.ok || !payload.ok || typeof payload.init_data !== "string" || !payload.init_data || !Number.isFinite(ttl) || ttl <= 0) throw new Error("invalid auth response");
      sessionStorage.setItem(key, JSON.stringify({initData:payload.init_data,expiresAt:Date.now()+ttl*1000}));
      location.assign(destination);
    } catch {
      message("Не удалось войти. Повтори вход через Telegram.", true);
    } finally { busy = false; }
  };
  async function load() {
    if (loading || busy) return;
    loading = true;
    retry.hidden = true;
    proceed.hidden = true;
    widget.replaceChildren();
    extra.hidden = true;
    yandex.hidden = true;
    emailForm.hidden = true;
    codeForm.hidden = true;
    link.hidden = true;
    logout.hidden = true;
    linkMode = false;
    cookieSession = false;
    message("Подключаем безопасный вход…");
    try {
      if (await existingSession()) return;
      let response = await fetch("/api/v1/web-auth/config",{credentials:"same-origin",cache:"no-store",headers:{Accept:"application/json"}});
      useWeb = response.status !== 404;
      if (!useWeb) response = await fetch("/api/v1/browser-auth/config",{credentials:"same-origin",cache:"no-store",headers:{Accept:"application/json"}});
      if (!response.ok) throw new Error("unavailable login");
      const config = await response.json();
      const providers = useWeb ? config.providers || {} : {telegram:true};
      if (providers.yandex) {
        yandex.href = "/api/v1/web-auth/yandex/start?" + new URLSearchParams({next:destination,...(linkMode?{link:"true"}:{})});
        yandex.hidden = false;
      }
      if (providers.email) emailForm.hidden = false;
      extra.hidden = !providers.email && !providers.yandex;
      if (!providers.telegram) {
        message(extra.hidden ? "Способы входа пока недоступны." : "Выбери доступный способ входа.",extra.hidden);
        return;
      }
      const bot = String(config.bot_username || "").replace(/^@/,"");
      if (!response.ok || !/^[A-Za-z0-9_]{5,32}$/.test(bot)) throw new Error("unavailable login");
      const script = document.createElement("script");
      script.async = true;
      script.src = "https://telegram.org/js/telegram-widget.js?22";
      script.setAttribute("data-telegram-login",bot);
      script.setAttribute("data-size","large");
      script.setAttribute("data-radius","14");
      script.setAttribute("data-userpic","false");
      script.setAttribute("data-onauth","onRoxyTelegramAuth(user)");
      script.onload = () => message("Подтверди вход через Telegram.");
      script.onerror = () => message("Виджет Telegram недоступен. Попробуй ещё раз.",true);
      widget.appendChild(script);
    } catch { message("Не удалось подключить вход. Проверь соединение и попробуй ещё раз.",true); }
    finally { loading = false; }
  }
  retry.addEventListener("click",load);
  void load();
})();
