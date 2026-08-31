import type { Metadata } from "next";
import Link from "next/link";
import styles from "./landing.module.css";

export const metadata: Metadata = {
  title: "KSU / ROXY — AI для креаторов",
  description: "Создавай изображения, видео, музыку и AI-аватары в ROXY.",
};

const capabilities = [
  { icon: "✦", title: "Изображения", copy: "От идеи до готового визуала" },
  { icon: "▶", title: "Видео", copy: "Клипы, сцены и motion-контент" },
  { icon: "♫", title: "Музыка", copy: "Треки и звук для твоих идей" },
  { icon: "◉", title: "Аватары", copy: "Говорящие персонажи и роли" },
  { icon: "⌁", title: "AI-помощник", copy: "Промпты, идеи и творческие решения" },
];

const models = ["Nano Banana", "GPT Image 2", "Seedream", "Kling", "Veo 3.1", "Grok", "Gemini"];

const feedCards = [
  { title: "Neon Rain", author: "@creator", variant: "city" },
  { title: "Soft Motion", author: "@dreamer", variant: "portrait" },
  { title: "Realm of Light", author: "@visual", variant: "realm" },
  { title: "Beyond Horizon", author: "@motion", variant: "space" },
  { title: "Golden Hour", author: "@studio", variant: "gold" },
  { title: "Violet Dream", author: "@roxy", variant: "violet" },
];

const heroCards = [
  { label: "Cinematic city", variant: "city" },
  { label: "Fantasy world", variant: "realm" },
  { label: "AI portrait", variant: "portrait" },
  { label: "Future motion", variant: "violet" },
  { label: "Product scene", variant: "gold" },
  { label: "Space story", variant: "space" },
];

const steps = [
  ["01", "Придумай", "Опиши идею своими словами"],
  ["02", "Выбери", "Найди подходящую модель"],
  ["03", "Создай", "Запусти генерацию в ROXY"],
  ["04", "Доработай", "Повтори или продолжи результат"],
  ["05", "Поделись", "Публикуй и вдохновляй других"],
];

export default function LandingPage() {
  return (
    <main className={styles.page}>
      <div className={styles.ambient} aria-hidden="true" />
      <header className={styles.header}>
        <Link className={styles.logo} href="/landing/" aria-label="KSU — главная">KSU</Link>
        <nav className={styles.nav} aria-label="Навигация по лендингу">
          <a href="#possibilities">Возможности</a>
          <a href="#models">Модели</a>
          <a href="#feed">Галерея</a>
          <a href="#how">Как это работает</a>
        </nav>
        <Link className={styles.headerCta} href="/">Открыть ROXY <span>↗</span></Link>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <div className={styles.eyebrow}>ROXY · твоя вселенная креатива</div>
          <h1>Вдохновляйся.<br />Создавай.<br /><span>Делись.</span></h1>
          <p>Изображения, видео, музыка и AI‑аватары — в одном месте, где идея быстро становится контентом.</p>
          <div className={styles.heroActions}>
            <Link className={styles.primaryCta} href="/">Открыть ROXY <span>→</span></Link>
            <a className={styles.secondaryCta} href="#how"><span className={styles.play}>▶</span> Как это работает</a>
          </div>
          <div className={styles.creatorProof}>
            <div className={styles.avatars} aria-hidden="true"><i /><i /><i /><i /></div>
            <span>Создано для креаторов, которые хотят больше</span>
          </div>
        </div>

        <div className={styles.heroVisual} aria-label="Примеры контента ROXY">
          <div className={styles.gridFloor} aria-hidden="true" />
          <div className={styles.cardRail}>
            {heroCards.map((card, index) => (
              <article key={card.label} className={`${styles.heroCard} ${styles[card.variant]}`} style={{ "--i": index } as React.CSSProperties}>
                <div className={styles.cardChrome}><span>ROXY</span><span>✦</span></div>
                <div className={styles.cardGlow} />
                <div className={styles.cardMeta}><strong>{card.label}</strong><span>AI creation · ✦</span></div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className={styles.section} id="possibilities">
        <div className={styles.sectionHeading}>
          <span>01 · ВОЗМОЖНОСТИ</span>
          <h2>Создавай любой контент</h2>
          <p>Одна творческая среда вместо десятка разрозненных инструментов.</p>
        </div>
        <div className={styles.capabilityGrid}>
          {capabilities.map((item) => (
            <article className={styles.capability} key={item.title}>
              <span className={styles.capabilityIcon}>{item.icon}</span>
              <h3>{item.title}</h3>
              <p>{item.copy}</p>
              <span className={styles.capabilityArrow}>↗</span>
            </article>
          ))}
        </div>
      </section>

      <section className={`${styles.section} ${styles.modelsSection}`} id="models">
        <div className={styles.sectionHeadingCompact}>
          <span>02 · МОДЕЛИ</span>
          <h2>Лучшие AI‑модели в одном месте</h2>
        </div>
        <div className={styles.modelMarquee}>
          {models.map((model) => <div className={styles.modelChip} key={model}><b>✦</b>{model}</div>)}
        </div>
      </section>

      <section className={styles.stats} aria-label="Преимущества ROXY">
        <div><strong>Фото</strong><span>и редактирование</span></div>
        <div><strong>Видео</strong><span>и анимация</span></div>
        <div><strong>Music</strong><span>и звук</span></div>
        <div><strong>Avatar</strong><span>и персонажи</span></div>
      </section>

      <section className={`${styles.section} ${styles.feedSection}`} id="feed">
        <div className={styles.feedHeading}>
          <div><span>03 · INFINITE FEED</span><h2>Лента вдохновения</h2></div>
          <p>Смотри, что создают другие. Забирай идею, переосмысливай и делай свою версию.</p>
        </div>
        <div className={styles.filters} aria-label="Категории галереи">
          <button type="button" className={styles.activeFilter}>Все</button>
          <button type="button">Фото</button><button type="button">Видео</button><button type="button">Аватары</button><button type="button">Музыка</button>
        </div>
        <div className={styles.feedGrid}>
          {feedCards.map((card, index) => (
            <article className={styles.feedCard} key={card.title}>
              <div className={`${styles.feedArt} ${styles[card.variant]}`}><span>{index % 2 === 0 ? "✦" : "▶"}</span></div>
              <div className={styles.feedMeta}><div><small>{card.author}</small><strong>{card.title}</strong></div><span>♡ {12 + index * 7}</span></div>
            </article>
          ))}
        </div>
      </section>

      <section className={`${styles.section} ${styles.howSection}`} id="how">
        <div className={styles.sectionHeadingCompact}><span>04 · FLOW</span><h2>От идеи до публикации</h2></div>
        <div className={styles.steps}>
          {steps.map(([number, title, copy]) => (
            <article key={number} className={styles.step}><span>{number}</span><div className={styles.stepIcon}>✦</div><h3>{title}</h3><p>{copy}</p></article>
          ))}
        </div>
      </section>

      <section className={styles.quoteSection}>
        <div className={styles.quoteGlow} aria-hidden="true" />
        <p>Не изучай AI.<br /><strong>Создавай с ним.</strong></p>
        <span>ROXY убирает технический шум и оставляет главное — твою идею.</span>
      </section>

      <section className={styles.finalCta}>
        <div className={styles.portal} aria-hidden="true"><i /><i /><i /></div>
        <div className={styles.finalCopy}><span>ТВОЙ МИР · ТВОИ ИДЕИ · ТВОЯ ROXY</span><h2>Готов создавать без границ?</h2><p>Открой ROXY и преврати следующую идею в работу, которой хочется поделиться.</p><Link className={styles.primaryCta} href="/">Открыть ROXY <span>→</span></Link></div>
      </section>

      <footer className={styles.footer}>
        <div><div className={styles.footerLogo}>KSU</div><p>AI‑пространство для вдохновения,<br />создания и смелых идей.</p></div>
        <div><strong>Продукт</strong><a href="#possibilities">Возможности</a><a href="#models">Модели</a><a href="#feed">Галерея</a></div>
        <div><strong>ROXY</strong><Link href="/">Открыть приложение</Link><a href="#how">Как это работает</a></div>
        <div><strong>Создавай</strong><span>Фото · Видео</span><span>Музыка · Аватары</span></div>
        <small>© KSU / ROXY</small>
      </footer>
    </main>
  );
}
