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
  const resumeKey = "__roxy_browser_resume_v1";
  function resumeDestination() {
    if (query.get("resume") !== "1") return "";
    try {
      const raw = sessionStorage.getItem(resumeKey) || "";
      if (!raw.startsWith("/mini-app/") || raw.startsWith("//")) return "";
      const url = new URL(raw, location.origin);
      if (url.origin !== location.origin || !/^\/mini-app\/(?:[a-z-]+\/)?$/.test(url.pathname)) return "";
      const safe = new URLSearchParams();
      for (const name of ["route", "id", "token", "generation", "action", "action_context_id", "create_media", "startapp", "start_payload", "ref", "onboarding", "start", "tgWebAppStartParam", "model", "model_id", "media", "tab"]) {
        const value = url.searchParams.get(name);
        if (value && value.length <= 512) safe.set(name, value);
      }
      const search = safe.toString();
      return url.pathname + (search ? "?" + search : "");
    } catch { return ""; }
  }
  function clearResume() {
    try { sessionStorage.removeItem(resumeKey); } catch {}
  }
  const resumed = resumeDestination();
  const destination = resumed || target.pathname + target.search;
  const status = document.getElementById("login-status");
  const widget = document.getElementById("login-widget");
  const retry = document.getElementById("login-retry");
  const proceed = document.getElementById("login-continue");
  const hint = document.getElementById("login-target");
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
    const credential = savedCredential();
    if (!credential) return false;
    try {
      const result = await fetch("/api/v1/me", {credentials:"same-origin",cache:"no-store",headers:{"X-Telegram-Init-Data":credential}});
      if (result.ok) {
        proceed.href = destination;
        proceed.addEventListener("click", clearResume, {once:true});
        proceed.hidden = false;
        message("Ты уже вошёл в аккаунт. Продолжи в студии.");
        return true;
      }
      if (result.status === 401 || result.status === 403) sessionStorage.removeItem(key);
    } catch {}
    return false;
  }
  window.onRoxyTelegramAuth = async (user) => {
    if (busy) return;
    busy = true;
    message("Входим в ROXY…");
    try {
      const response = await fetch("/api/v1/browser-auth", {
        method:"POST", credentials:"same-origin", cache:"no-store",
        headers:{"Accept":"application/json","Content-Type":"application/json"},
        body:JSON.stringify({telegram_auth:user}),
      });
      const payload = await response.json();
      const ttl = Number(payload.expires_in);
      if (!response.ok || !payload.ok || typeof payload.init_data !== "string" || !payload.init_data || !Number.isFinite(ttl) || ttl <= 0) throw new Error("invalid auth response");
      sessionStorage.setItem(key, JSON.stringify({initData:payload.init_data,expiresAt:Date.now()+ttl*1000}));
      clearResume();
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
    message("Подключаем безопасный вход…");
    try {
      if (await existingSession()) return;
      const response = await fetch("/api/v1/browser-auth/config",{credentials:"same-origin",cache:"no-store",headers:{Accept:"application/json"}});
      const config = await response.json();
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
