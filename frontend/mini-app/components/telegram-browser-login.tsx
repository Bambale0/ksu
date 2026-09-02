"use client";

import { useEffect, useRef, useState } from "react";
import { saveBrowserInitData } from "@/lib/browser-auth-session";
import { getStartParamFallback } from "@/lib/telegram";

type TelegramLoginUser = {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
};

declare global {
  interface Window {
    onRoxyTelegramAuth?: (user: TelegramLoginUser) => void;
  }
}

const features = [
  { icon: "✦", title: "AI Фото", copy: "Создавай изображения с нуля или меняй свои фото по референсу и описанию." },
  { icon: "▶", title: "AI Видео", copy: "Превращай идеи и изображения в ролики с актуальными видеомоделями." },
  { icon: "⌁", title: "Промпты", copy: "Используй готовые идеи и инструменты, чтобы быстрее получать нужный результат." },
  { icon: "↗", title: "Тренды", copy: "Запускай готовые тренды и адаптируй их под собственный контент." },
];

const steps = [
  { title: "Опиши идею", copy: "Напиши, что хочешь получить, или выбери готовый тренд." },
  { title: "Добавь референс", copy: "Если нужно — загрузи фото, видео или используй работу из своей истории." },
  { title: "Создавай и делись", copy: "ROXY запустит подходящую модель, а готовый результат останется в истории." },
];

const styles = ["Киберпанк", "Аниме", "Фэнтези", "3D", "Кинематик", "Портрет"];

function telegramMiniAppUrl(botUsername: string): string {
  const startParam = getStartParamFallback();
  return startParam
    ? `https://t.me/${botUsername}?startapp=${encodeURIComponent(startParam)}`
    : `https://t.me/${botUsername}?startapp`;
}

function TelegramGlyph() {
  return <span className="roxy-telegram-glyph" aria-hidden="true">➤</span>;
}

export function TelegramBrowserLogin() {
  const widgetRef = useRef<HTMLDivElement | null>(null);
  const [botUsername, setBotUsername] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "signing-in" | "error">("loading");

  useEffect(() => {
    let active = true;
    void fetch("/api/v1/browser-auth/config", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => null) as { bot_username?: string } | null;
        if (!response.ok || !payload?.bot_username) throw new Error("Telegram login unavailable");
        if (!active) return;
        setBotUsername(payload.bot_username.replace(/^@/, ""));
      })
      .catch(() => active && setStatus("error"));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!botUsername || !widgetRef.current) return;
    const container = widgetRef.current;
    container.replaceChildren();

    window.onRoxyTelegramAuth = async (user: TelegramLoginUser) => {
      setStatus("signing-in");
      try {
        const response = await fetch("/api/v1/browser-auth", {
          method: "POST",
          credentials: "same-origin",
          cache: "no-store",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({ telegram_auth: user }),
        });
        const payload = await response.json().catch(() => null) as {
          ok?: boolean;
          init_data?: string;
          expires_in?: number;
        } | null;
        if (!response.ok || !payload?.ok || !payload.init_data) throw new Error("Telegram login failed");
        saveBrowserInitData(payload.init_data, Number(payload.expires_in || 0));
        window.location.reload();
      } catch {
        setStatus("error");
      }
    };

    const script = document.createElement("script");
    script.async = true;
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.setAttribute("data-telegram-login", botUsername);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "14");
    script.setAttribute("data-userpic", "false");
    script.setAttribute("data-onauth", "onRoxyTelegramAuth(user)");
    script.onload = () => setStatus("ready");
    script.onerror = () => setStatus("error");
    container.appendChild(script);

    return () => {
      delete window.onRoxyTelegramAuth;
      container.replaceChildren();
    };
  }, [botUsername]);

  const telegramUrl = botUsername ? telegramMiniAppUrl(botUsername) : "";
  const launchHref = telegramUrl || "#telegram-login";
  const launchTarget = telegramUrl ? "_blank" : undefined;
  const launchRel = telegramUrl ? "noreferrer" : undefined;

  return (
    <main className="roxy-browser-landing" aria-labelledby="roxy-landing-title">
      <div className="roxy-landing-glow roxy-landing-glow-a" aria-hidden="true" />
      <div className="roxy-landing-glow roxy-landing-glow-b" aria-hidden="true" />

      <header className="roxy-landing-nav">
        <a className="roxy-landing-logo" href="#top" aria-label="ROXY — начало страницы">
          <span className="roxy-landing-logo-mark" aria-hidden="true">✦</span><strong>ROXY</strong>
        </a>
        <nav className="roxy-landing-links" aria-label="Разделы лендинга">
          <a href="#features">Возможности</a><a href="#how">Как работает</a><a href="#examples">Примеры</a><a href="#telegram-login">Telegram</a>
        </nav>
        <a className="roxy-landing-button roxy-landing-button-small" href={launchHref} target={launchTarget} rel={launchRel}>
          <TelegramGlyph /> Запустить
        </a>
      </header>

      <section className="roxy-landing-hero" id="top">
        <div className="roxy-landing-hero-copy">
          <span className="roxy-landing-pill">✦ AI-креатор в Telegram и браузере</span>
          <h1 id="roxy-landing-title">Создавай фото и видео <em>с AI</em></h1>
          <p>Изображения, видео, референсы, промпты и готовые тренды — в одной творческой студии ROXY.</p>
          <div className="roxy-landing-actions">
            <a className="roxy-landing-button" href={launchHref} target={launchTarget} rel={launchRel}><TelegramGlyph /> Запустить в Telegram</a>
            <a className="roxy-landing-button roxy-landing-button-ghost" href="#features">Смотреть возможности</a>
          </div>
          <div className="roxy-landing-proof" aria-label="Возможности ROXY">
            <span><b>Фото + видео</b><small>в одном приложении</small></span>
            <span><b>Готовые тренды</b><small>для быстрого старта</small></span>
            <span><b>История работ</b><small>всегда под рукой</small></span>
          </div>
        </div>
        <div className="roxy-landing-hero-art">
          <div className="roxy-hero-halo" aria-hidden="true" />
          <img src="/mini-app/roxy-landing/hero.webp" width="420" height="525" alt="ROXY — AI-студия для создания фото и видео" fetchPriority="high" />
        </div>
      </section>

      <section className="roxy-landing-section" id="features">
        <header className="roxy-landing-section-head"><span>Возможности</span><h2>Всё для твоего креатива</h2><p>От первой идеи до готовой публикации — без прыжков между десятком сервисов.</p></header>
        <div className="roxy-feature-grid">
          {features.map((feature) => <article className="roxy-feature-card" key={feature.title}><i aria-hidden="true">{feature.icon}</i><h3>{feature.title}</h3><p>{feature.copy}</p></article>)}
        </div>
        <div className="roxy-landing-showpiece">
          <div><span className="roxy-landing-pill">ROXY Creative Studio</span><h3>Одна идея — много способов воплотить её</h3><p>Выбирай модель вручную или просто добавляй референс: ROXY подстроит сценарий создания под задачу.</p></div>
          <img src="/mini-app/roxy-landing/hero.webp" width="420" height="525" alt="Инструменты ROXY" loading="lazy" />
        </div>
      </section>

      <section className="roxy-landing-section" id="how">
        <header className="roxy-landing-section-head"><span>Как это работает</span><h2>Три шага от идеи до результата</h2></header>
        <div className="roxy-step-layout">
          <div className="roxy-step-grid">{steps.map((step, index) => <article className="roxy-step-card" key={step.title}><b>{index + 1}</b><h3>{step.title}</h3><p>{step.copy}</p></article>)}</div>
          <div className="roxy-css-orbit" aria-hidden="true"><i /><i /><i /></div>
        </div>
      </section>

      <section className="roxy-landing-section" id="examples">
        <div className="roxy-landing-section-head roxy-section-head-row">
          <div><span>Вдохновение</span><h2>Найди свой визуальный стиль</h2></div>
          <div className="roxy-style-chips" aria-label="Популярные стили">{styles.map((style) => <span key={style}>{style}</span>)}</div>
        </div>
        <div className="roxy-example-stage">
          <div className="roxy-example-mosaic" aria-label="Примеры визуального стиля ROXY">
            <figure><img src="/mini-app/roxy-landing/hero.webp" alt="AI изображение в ROXY" width="420" height="525" loading="lazy" /></figure>
            <figure><img src="/mini-app/roxy-landing/hero.webp" alt="AI видео в ROXY" width="420" height="525" loading="lazy" /></figure>
            <figure><img src="/mini-app/roxy-landing/hero.webp" alt="Интерфейс ROXY" width="420" height="525" loading="lazy" /></figure>
          </div>
          <div className="roxy-example-copy"><span className="roxy-landing-pill">Фото · Видео · Тренды</span><h3>Не начинай каждый раз с нуля</h3><p>Выбирай готовую идею, добавляй свой референс и адаптируй результат под себя.</p><a className="roxy-landing-button roxy-landing-button-ghost" href={launchHref} target={launchTarget} rel={launchRel}>Открыть ROXY</a></div>
        </div>
      </section>

      <section className="roxy-telegram-section" id="telegram-login">
        <div className="roxy-telegram-copy">
          <span className="roxy-landing-pill">Telegram Mini App</span><h2>ROXY уже там, где ты общаешься</h2><p>Открывай Mini App в Telegram или войди с Telegram на этом устройстве. Никакого отдельного пароля.</p>
          <ul><li>Один аккаунт в Telegram и браузере</li><li>Работы и баланс остаются с тобой</li><li>Реферальные и контентные ссылки сохраняют свой контекст</li></ul>
          {telegramUrl ? <a className="roxy-landing-button" href={telegramUrl} target="_blank" rel="noreferrer"><TelegramGlyph /> Открыть Mini App</a> : null}
        </div>
        <div className="roxy-login-panel" aria-label="Вход через Telegram">
          <div className="roxy-landing-logo"><span className="roxy-landing-logo-mark" aria-hidden="true">✦</span><strong>ROXY</strong></div>
          <h3>Войти с Telegram</h3><p>Продолжишь с тем же профилем, балансом и историей.</p>
          <div ref={widgetRef} className="browser-login-widget roxy-login-widget" aria-live="polite" />
          {status === "loading" && <small>Готовлю безопасный вход…</small>}
          {status === "signing-in" && <small>Вхожу в ROXY…</small>}
          {status === "ready" && <small>Авторизация проходит через Telegram.</small>}
          {status === "error" && <div className="browser-login-fallback" role="alert"><small>Виджет входа сейчас недоступен.</small>{telegramUrl && <a className="roxy-landing-button roxy-landing-button-ghost" href={telegramUrl} target="_blank" rel="noreferrer">Открыть ROXY в Telegram</a>}</div>}
        </div>
      </section>

      <section className="roxy-final-cta">
        <div className="roxy-final-orb" aria-hidden="true" /><div><div className="roxy-landing-logo"><span className="roxy-landing-logo-mark" aria-hidden="true">✦</span><strong>ROXY</strong></div><h2>Начни создавать уже сегодня</h2><p>Твоя следующая идея может стать изображением или видео через несколько кликов.</p><a className="roxy-landing-button" href={launchHref} target={launchTarget} rel={launchRel}><TelegramGlyph /> Запустить ROXY</a></div>
      </section>

      <footer className="roxy-landing-footer">
        <div><div className="roxy-landing-logo"><span className="roxy-landing-logo-mark" aria-hidden="true">✦</span><strong>ROXY</strong></div><p>AI-студия для изображений, видео, референсов и трендов.</p></div>
        <nav aria-label="Ссылки в подвале"><a href="#features">Возможности</a><a href="#how">Как работает</a><a href="#telegram-login">Войти</a></nav>
        <small>© 2026 ROXY</small>
      </footer>
    </main>
  );
}
