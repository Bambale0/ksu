"use client";

import { useEffect, useRef, useState } from "react";
import { saveBrowserInitData } from "@/lib/browser-auth-session";
import { ROXY_MOSAIC_ATLAS } from "@/lib/roxy-mosaic-atlas";
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


const filmTiles = [
  { id: "portrait", label: "Портрет в кинематографическом свете" },
  { id: "chrome-flower", label: "Хромированный цветок" },
  { id: "motion", label: "Кинематографическое движение", video: true },
  { id: "cat", label: "Портрет кота" },
  { id: "fashion", label: "Фэшн-портрет" },
  { id: "rain", label: "Портрет под дождём" },
  { id: "editorial", label: "Редакционная съёмка" },
  { id: "blossom", label: "Макросъёмка цветка" },
  { id: "dream", label: "Сюрреалистическая сцена", video: true },
] as const;

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
      <header className="roxy-landing-nav">
        <a className="roxy-landing-logo" href="#top" aria-label="ROXY — начало страницы">
          <span className="roxy-landing-symbol" aria-hidden="true">✦</span><strong>ROXY</strong>
        </a>
        <nav className="roxy-landing-links" aria-label="Разделы лендинга">
          <a href="#features">Возможности</a>
          <a href="#how">Процесс</a>
          <a href="#examples">Галерея</a>
          <a href="#telegram-login">Вход</a>
        </nav>
        <a className="roxy-landing-button roxy-landing-button-small" href="#telegram-login">Начать <span aria-hidden="true">↗</span></a>
      </header>

      <section className="roxy-film-hero" id="top">
        <div className="roxy-film-mosaic" style={{ "--roxy-art": "url(" + ROXY_MOSAIC_ATLAS + ")" } as React.CSSProperties} role="group" aria-label="Демонстрационный коллаж возможностей ROXY">
          {filmTiles.map((tile) => (
            <div className={"roxy-film-tile roxy-film-tile-" + tile.id} key={tile.id} role="img" aria-label={tile.label}>
              {"video" in tile && tile.video ? <span className="roxy-film-play" aria-hidden="true">▶</span> : null}
            </div>
          ))}
          <div className="roxy-film-chrome" aria-hidden="true">R<span>✦</span></div>
        </div>
        <div className="roxy-film-hero-copy">
          <span className="roxy-film-kicker">ТВОЯ СТУДИЯ · ТВОИ ПРАВИЛА</span>
          <h1 id="roxy-landing-title">Создавай фото и видео с AI</h1>
          <p>Твоя идея превращается в визуал. Создавай, оживляй и переосмысливай в ROXY.</p>
          <div className="roxy-landing-actions">
            <a className="roxy-landing-button roxy-landing-button-primary" href="#telegram-login">Начать создавать <span aria-hidden="true">▶</span></a>
            <a className="roxy-landing-button roxy-landing-button-ghost" href={launchHref} target={launchTarget} rel={launchRel}><TelegramGlyph /> Запустить в Telegram</a>
          </div>
        </div>
        <a className="roxy-film-scroll" href="#features" aria-label="Перейти к возможностям">↓</a>
      </section>

      <section className="roxy-landing-section roxy-feature-section" id="features">
        <header className="roxy-landing-section-head">
          <span className="roxy-film-kicker">01 / ИНСТРУМЕНТЫ</span>
          <h2>Всё для твоего креатива</h2>
          <p>От первого кадра до готового ролика. Один творческий процесс, множество способов воплотить идею.</p>
        </header>
        <div className="roxy-feature-grid">
          {features.map((feature, index) => (
            <article className="roxy-feature-card" key={feature.title}>
              <span className="roxy-feature-counter">0{index + 1}</span>
              <i aria-hidden="true">{feature.icon}</i>
              <h3>{feature.title}</h3>
              <p>{feature.copy}</p>
            </article>
          ))}
        </div>
        <div className="roxy-feature-showcase">
          <div className="roxy-feature-showcase-art" style={{ "--roxy-art": "url(" + ROXY_MOSAIC_ATLAS + ")" } as React.CSSProperties}>
            <span className="roxy-feature-shot roxy-feature-shot-before" role="img" aria-label="Исходный визуальный референс" />
            <span className="roxy-feature-transition" aria-hidden="true">→</span>
            <span className="roxy-feature-shot roxy-feature-shot-after" role="img" aria-label="Результат творческого преобразования" />
          </div>
          <div className="roxy-feature-showcase-copy">
            <span className="roxy-film-kicker">ОТ РЕФЕРЕНСА К РЕЗУЛЬТАТУ</span>
            <h3>Одна идея. Бесконечно много версий.</h3>
            <p>Используй свои кадры, готовые тренды и инструменты редактирования. Экспериментируй без сложного монтажа.</p>
            <a className="roxy-film-text-link" href="#telegram-login">Попробовать ROXY <span aria-hidden="true">↗</span></a>
          </div>
        </div>
      </section>

      <section className="roxy-landing-section roxy-how-section" id="how">
        <header className="roxy-landing-section-head">
          <span className="roxy-film-kicker">02 / КАК ЭТО РАБОТАЕТ</span>
          <h2>Три шага от идеи до результата</h2>
          <p>Не нужно учиться сложным редакторам. Всё начинается с того, что ты хочешь создать.</p>
        </header>
        <div className="roxy-step-grid">
          {steps.map((step, index) => (
            <article className="roxy-step-card" key={step.title}>
              <b>0{index + 1}</b>
              <span className="roxy-step-arrow" aria-hidden="true">↗</span>
              <h3>{step.title}</h3>
              <p>{step.copy}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="roxy-landing-section roxy-examples-section" id="examples">
        <header className="roxy-landing-section-head">
          <span className="roxy-film-kicker">03 / ГАЛЕРЕЯ</span>
          <h2>Найди свой визуальный стиль</h2>
          <p>Портреты, истории, движение и эксперименты. Эти демонстрационные кадры показывают направление возможностей ROXY.</p>
        </header>
        <div className="roxy-style-chips" aria-label="Примеры стилей">
          {styles.map((style) => <span key={style}>{style}</span>)}
        </div>
        <div className="roxy-examples-mosaic" style={{ "--roxy-art": "url(" + ROXY_MOSAIC_ATLAS + ")" } as React.CSSProperties}>
          {filmTiles.slice(0, 6).map((tile) => (
            <figure className={"roxy-example-tile roxy-example-" + tile.id} key={tile.id}>
              <span className="roxy-example-picture" role="img" aria-label={tile.label} />
              <figcaption>{tile.label} <span aria-hidden="true">↗</span></figcaption>
            </figure>
          ))}
        </div>
        <a className="roxy-landing-button roxy-landing-button-primary roxy-examples-cta" href="#telegram-login">Создать свою историю <span aria-hidden="true">✦</span></a>
      </section>

      <section className="roxy-telegram-section" id="telegram-login">
        <div className="roxy-telegram-copy">
          <span className="roxy-film-kicker">04 / ТВОЯ СТУДИЯ</span>
          <h2>Твой следующий кадр начинается здесь.</h2>
          <p>Войди через Telegram на сайте или открой Mini App. История работ и баланс сохраняются в аккаунте.</p>
          <ul>
            <li>Фото, видео, референсы и тренды</li>
            <li>Работы и баланс в одном профиле</li>
            <li>Реферальные переходы сохраняют контекст</li>
          </ul>
          {telegramUrl ? <a className="roxy-landing-button roxy-landing-button-ghost" href={telegramUrl} target="_blank" rel="noreferrer"><TelegramGlyph /> Открыть Mini App</a> : null}
        </div>
        <div className="roxy-login-panel" aria-label="Вход через Telegram">
          <div className="roxy-landing-logo"><span className="roxy-landing-symbol" aria-hidden="true">✦</span><strong>ROXY</strong></div>
          <h3>Войти с Telegram</h3>
          <p>Продолжи с тем же профилем, балансом и историей.</p>
          <div ref={widgetRef} className="browser-login-widget roxy-login-widget" aria-live="polite" />
          {status === "loading" && <small>Готовлю безопасный вход…</small>}
          {status === "signing-in" && <small>Вхожу в ROXY…</small>}
          {status === "ready" && <small>Авторизация проходит через Telegram.</small>}
          {status === "error" && <div className="browser-login-fallback" role="alert"><small>Виджет входа сейчас недоступен.</small>{telegramUrl && <a className="roxy-landing-button roxy-landing-button-ghost" href={telegramUrl} target="_blank" rel="noreferrer">Открыть ROXY в Telegram</a>}</div>}
        </div>
      </section>

      <footer className="roxy-landing-footer">
        <div><a className="roxy-landing-logo" href="#top"><span className="roxy-landing-symbol" aria-hidden="true">✦</span><strong>ROXY</strong></a><p>Пространство для тех, кто создаёт свой визуальный мир.</p></div>
        <nav aria-label="Ссылки в подвале"><a href="#features">Возможности</a><a href="#how">Как работает</a><a href="#examples">Галерея</a><a href="#telegram-login">Войти</a></nav>
        <small>© 2026 ROXY</small>
      </footer>
    </main>
  );
}
