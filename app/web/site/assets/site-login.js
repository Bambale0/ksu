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
  const payment = query.get("section") === "payments" && !validTrend;
  const target = new URL(validTrend ? "/mini-app/trend/" : payment ? "/mini-app/payments/" : "/mini-app/", location.origin);
  if (payment && ["card","cryptobot"].includes(query.get("provider"))) target.searchParams.set("provider",query.get("provider"));
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
  let busy = false;
  let loading = false;
  if (validTrend || payment) hint.hidden = false;
  if (payment) { hint.textContent = "После подтверждения откроется пополнение ROX."; proceed.textContent = "Открыть пополнение ↗"; }

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
        proceed.hidden = false;
        message("Ты уже вошёл в аккаунт. Продолжи в студии.");
        return true;
      }
      if (result.status === 401 || result.status === 403) sessionStorage.removeItem(key);
    } catch {}
    return false;
  }
  const approvalRoot = "/api/v1/browser-auth/approval";
  let pollTimer;
  let deadline = 0;
  let generation = 0;

  async function requestApproval(path, payload) {
    const response = await fetch(approvalRoot + path, {
      credentials: "same-origin", cache: "no-store",
      ...(payload !== undefined ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)} : {}),
      signal: AbortSignal.timeout(10000),
    });
    if (response.status === 404) return null;
    if (!response.ok) throw new Error("approval unavailable");
    return response.json();
  }
  function stopPolling() { generation++; clearTimeout(pollTimer); }
  function showStart() {
    stopPolling();
    widget.replaceChildren();
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button button-primary";
    button.textContent = "Войти через Telegram";
    button.onclick = async () => {
      if (busy) return;
      busy = true;
      button.disabled = true;
      try {
        const ticket = await requestApproval("/start", {purpose:payment ? "payments" : "studio"});
        showTicket(ticket);
      } catch { message("Не удалось создать запрос. Попробуй снова.",true); }
      finally { busy=false; button.disabled=false; }
    };
    widget.append(button);
    message("Подтверди вход через Telegram в чате бота.");
  }
  function showTicket(ticket) {
    if (!ticket || !["pending","approved"].includes(ticket.status) || !/^\d{6}$/.test(ticket.code) ||
        !/^https:\/\/t\.me\/[A-Za-z0-9_]{5,32}\?start=auth_[A-Za-z0-9_-]{43}$/.test(ticket.url) ||
        !Number.isFinite(ticket.expires_in) || ticket.expires_in <= 0 || ticket.expires_in > 300) throw new Error("invalid ticket");
    stopPolling();
    const version = generation;
    deadline = Date.now() + ticket.expires_in*1000;
    widget.replaceChildren();
    const panel = document.createElement("div");
    panel.className = "approval-panel";
    const label = document.createElement("p");
    label.textContent = "Сверь код на сайте и в Telegram:";
    const code = document.createElement("strong");
    code.className = "approval-code";
    code.textContent = ticket.code;
    const link = document.createElement("a");
    link.className = "button button-primary";
    link.href = ticket.url;
    // Direct user-initiated link, no async about:blank popup. Keep the polling tab.
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Открыть Telegram ↗";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "button button-outline";
    cancel.textContent = "Отменить вход";
    cancel.onclick = async () => {
      if (busy) return;
      stopPolling();
      cancel.disabled = true;
      try { await requestApproval("/cancel", {}); showStart(); message("Вход отменён."); }
      catch { showStart(); message("Не подтверждай старый запрос. Попробуй заново.",true); }
    };
    panel.append(label,code,link,cancel);
    widget.append(panel);
    message("Подтверди запрос в личном чате ROXY и вернись сюда. Код действует 5 минут.");
    async function poll() {
      if (version !== generation) return;
      if (Date.now() >= deadline) { showStart(); message("Запрос истёк. Создай новый.",true); return; }
      try {
        const result = await requestApproval("/status");
        if (version !== generation) return;
        if (result?.status === "approved") {
          busy = true;
          cancel.disabled = true;
          message("Вход подтверждён. Открываем ROXY…");
          const claimed = await requestApproval("/claim", {});
          if (version !== generation) return;
          if (!claimed?.ok || typeof claimed.init_data !== "string" || !claimed.init_data ||
              !Number.isFinite(claimed.expires_in) || claimed.expires_in <= 0) throw new Error("claim failed");
          sessionStorage.setItem(key, JSON.stringify({initData:claimed.init_data,expiresAt:Date.now()+claimed.expires_in*1000}));
          stopPolling();
          location.replace(claimed.purpose === "payments" && !payment ? "/mini-app/payments/" : destination);
          return;
        }
        if (result?.status !== "pending") { showStart(); message("Запрос отклонён или уже использован.",true); return; }
      } catch {
        if (version === generation) message("Проверяем соединение. Вернись сюда после подтверждения.");
      } finally { busy = false; cancel.disabled = false; }
      if (version === generation) pollTimer = setTimeout(poll,1500);
    }
    void poll();
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
      stopPolling();
      if (await existingSession()) return;
      const ticket = await requestApproval("/status");
      if (ticket !== null) {
        if (["pending","approved"].includes(ticket.status)) showTicket(ticket);
        else showStart();
        return;
      }
      // During rolling upgrade only, an older server has no approval endpoint.
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
