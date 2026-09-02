"use client";

import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { getStartParamFallback, haptic, initTelegram, notify, openExternalLink } from "@/lib/telegram";
import type { Me } from "@/lib/types";
import styles from "./user-onboarding.module.css";

type OnboardingStatus = {
  enabled?: boolean;
  version?: string;
  completed?: boolean;
  rules_url?: string | null;
  privacy_url?: string | null;
};

type Step = {
  eyebrow: string;
  title: string;
  text: string;
  visual: "welcome" | "create" | "prompt" | "result" | "social" | "rox";
};

const STEPS: Step[] = [
  {
    eyebrow: "Добро пожаловать",
    title: "ROXY — ваша AI-студия в Telegram",
    text: "Создавайте фото, видео и музыку, собирайте идеи в одном месте и возвращайтесь к готовым работам без лишних сервисов.",
    visual: "welcome",
  },
  {
    eyebrow: "Создание",
    title: "Выберите задачу — ROXY подберёт нужный инструмент",
    text: "Начните через «Создать» или откройте «Каталог», если хотите посмотреть все возможности. Модель, формат и настройки всегда можно выбрать перед запуском.",
    visual: "create",
  },
  {
    eyebrow: "Промпт и референсы",
    title: "Опишите идею и добавьте свои материалы",
    text: "Фото, видео и другие референсы можно прикрепить прямо к генерации. Если сложно сформулировать запрос, Prompt Tools помогут собрать понятный промпт.",
    visual: "prompt",
  },
  {
    eyebrow: "Результат",
    title: "Готовая работа не потеряется",
    text: "Результат приходит в Telegram и остаётся в истории. Оттуда можно скачать его, повторить генерацию, изменить работу или продолжить с теми же настройками.",
    visual: "result",
  },
  {
    eyebrow: "Профиль и лента",
    title: "Публикуйте только то, чем хотите делиться",
    text: "Работу можно оставить приватной, показать только в профиле или опубликовать в общей ленте. Перед публикацией ROXY явно показывает, что станет публичным.",
    visual: "social",
  },
  {
    eyebrow: "Баланс ROX",
    title: "Стоимость видна до запуска",
    text: "ROX используются для генераций. Цена рассчитывается заранее — никаких неожиданных списаний. Пополнить баланс можно в любой момент из верхней панели.",
    visual: "rox",
  },
];

function progressKey(version: string) {
  return `roxy.onboarding.${version || "current"}.step`;
}

function readSavedStep(version: string): number {
  try {
    const value = Number(window.localStorage.getItem(progressKey(version)) || 0);
    return Number.isFinite(value) ? Math.max(0, Math.min(STEPS.length - 1, Math.floor(value))) : 0;
  } catch {
    return 0;
  }
}

function saveStep(version: string, step: number) {
  try {
    window.localStorage.setItem(progressKey(version), String(step));
  } catch {}
}

function clearSavedStep(version: string) {
  try {
    window.localStorage.removeItem(progressKey(version));
  } catch {}
}

function creatorName(me: Me | null): string {
  return me?.first_name?.trim() || me?.username?.trim() || "креатор";
}

function formattedBalance(balance?: string | null): string {
  const value = Number(balance);
  return Number.isFinite(value) ? value.toLocaleString("ru-RU") : "50";
}

function hasContentLaunchTarget(): boolean {
  try {
    return /^(feed_|remix_|repeat_|profile_|posts_)/i.test(getStartParamFallback());
  } catch {
    return false;
  }
}

function FeatureVisual({ kind, balance }: { kind: Step["visual"]; balance?: string | null }) {
  if (kind === "welcome") {
    return <div className={`${styles.visual} ${styles.welcomeVisual}`} aria-hidden="true"><div className={styles.logoOrb}>R</div><div className={styles.sparkOne}>✦</div><div className={styles.sparkTwo}>✦</div><div className={styles.sparkThree}>✦</div></div>;
  }
  if (kind === "create") {
    return <div className={`${styles.visual} ${styles.cardVisual}`} aria-hidden="true"><div className={styles.miniCard}><span>◫</span><strong>Фото</strong></div><div className={styles.miniCard}><span>▶</span><strong>Видео</strong></div><div className={styles.miniCard}><span>♫</span><strong>Музыка</strong></div></div>;
  }
  if (kind === "prompt") {
    return <div className={`${styles.visual} ${styles.promptVisual}`} aria-hidden="true"><div className={styles.promptLine}><span>✦</span><i /></div><div className={styles.promptLine}><span>＋</span><i /></div><div className={styles.promptChip}>Prompt Tools</div></div>;
  }
  if (kind === "result") {
    return <div className={`${styles.visual} ${styles.resultVisual}`} aria-hidden="true"><div className={styles.resultFrame}><div className={styles.resultGlow} /></div><div className={styles.resultBadge}>Готово ✓</div></div>;
  }
  if (kind === "social") {
    return <div className={`${styles.visual} ${styles.socialVisual}`} aria-hidden="true"><div className={styles.privacyCard}><span>●</span><div><strong>Приватно</strong><small>видите только вы</small></div></div><div className={styles.privacyCard}><span>◎</span><div><strong>Профиль</strong><small>ваша витрина</small></div></div><div className={styles.privacyCard}><span>✦</span><div><strong>Лента</strong><small>для всех</small></div></div></div>;
  }
  return <div className={`${styles.visual} ${styles.roxVisual}`} aria-hidden="true"><span className={styles.roxLabel}>ROX</span><strong>{formattedBalance(balance)}</strong><small>баланс</small></div>;
}

export function UserOnboardingGate() {
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [statusError, setStatusError] = useState("");
  const [statusAttempt, setStatusAttempt] = useState(0);
  const [me, setMe] = useState<Me | null>(null);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const version = String(status?.version || "current");
  const current = STEPS[step];
  const last = step === STEPS.length - 1;
  const name = useMemo(() => creatorName(me), [me]);

  useEffect(() => {
    const tg = initTelegram();
    tg?.ready?.();
    tg?.expand?.();
    let active = true;
    setStatusError("");
    Promise.allSettled([api.onboarding(), tg?.initData ? api.me() : Promise.resolve(null)]).then(([onboardingResult, meResult]) => {
      if (!active) return;
      if (onboardingResult.status === "fulfilled") {
        const next = onboardingResult.value as OnboardingStatus;
        setStatus(next);
        if (next.enabled && !next.completed) setStep(readSavedStep(String(next.version || "current")));
      } else {
        // Fail closed: a transient status error must never bypass mandatory onboarding.
        setStatus(null);
        setStatusError("Не удалось проверить знакомство с ROXY. Попробуйте ещё раз.");
      }
      if (meResult.status === "fulfilled" && meResult.value) setMe(meResult.value);
    });
    return () => { active = false; };
  }, [statusAttempt]);

  useEffect(() => {
    // The old single-card onboarding is still rendered by the legacy shell while
    // the product migrates to this server-owned v2 gate. Keep that hidden shell
    // inert and remove its shared test/geometry hook so there is exactly one
    // active onboarding card in the DOM at every viewport.
    const neutralizeLegacyOnboarding = () => {
      document.querySelectorAll<HTMLElement>(".onboarding-overlay:not(.roxy-onboarding-v2)").forEach((overlay) => {
        overlay.setAttribute("aria-hidden", "true");
        overlay.setAttribute("inert", "");
        overlay.querySelectorAll(".onboarding-card").forEach((card) => card.classList.remove("onboarding-card"));
      });
    };
    neutralizeLegacyOnboarding();
    const observer = new MutationObserver(neutralizeLegacyOnboarding);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!status?.enabled || status.completed) return;
    saveStep(version, step);
  }, [status?.completed, status?.enabled, step, version]);

  useEffect(() => {
    const tg = initTelegram();
    if (!status?.enabled || status.completed) {
      tg?.BackButton?.hide?.();
      return;
    }
    const back = () => {
      if (step <= 0 || busy) return;
      haptic("light");
      setStep((value) => Math.max(0, value - 1));
    };
    if (step > 0) {
      tg?.BackButton?.show?.();
      tg?.BackButton?.onClick?.(back);
    } else {
      tg?.BackButton?.hide?.();
    }
    return () => tg?.BackButton?.offClick?.(back);
  }, [busy, status?.completed, status?.enabled, step]);

  const finish = async (target: "home" | "create") => {
    setBusy(true);
    setError("");
    try {
      await api.completeOnboarding();
      clearSavedStep(version);
      notify("success");
      haptic("medium");
      if (hasContentLaunchTarget()) {
        window.location.reload();
        return;
      }
      window.location.replace(`/mini-app/?route=${target}`);
    } catch (reason) {
      notify("error");
      setError(reason instanceof Error ? reason.message : "Не удалось завершить знакомство. Попробуйте ещё раз.");
      setBusy(false);
    }
  };

  const next = () => {
    if (last) {
      void finish("create");
      return;
    }
    haptic("light");
    setStep((value) => Math.min(STEPS.length - 1, value + 1));
  };

  if (status === null) {
    return <div className={`onboarding-overlay roxy-onboarding-v2 ${styles.overlay}`} role="dialog" aria-modal="true" aria-labelledby="roxy-onboarding-status-title">
      <div className={`${styles.shell} onboarding-card`}>
        <header className={styles.topline}>
          <div className={styles.brand}><span>R</span><strong>ROXY</strong></div>
        </header>
        <main className={styles.content}>
          <div className={`${styles.visual} ${styles.welcomeVisual}`} aria-hidden="true"><div className={styles.logoOrb}>R</div></div>
          <div className={styles.copy}>
            <span className={styles.eyebrow}>Знакомство с ROXY</span>
            <h1 id="roxy-onboarding-status-title">{statusError ? "Не удалось открыть знакомство" : "Проверяю ваш прогресс…"}</h1>
            <p>{statusError || "Секунду — проверяю, нужно ли показать вводные шаги."}</p>
          </div>
        </main>
        {statusError ? <footer className={styles.footer}><button className={styles.primary} type="button" onClick={() => setStatusAttempt((value) => value + 1)}>Попробовать ещё раз</button></footer> : null}
      </div>
    </div>;
  }

  if (!status.enabled || status.completed) return null;

  return <div className={`onboarding-overlay roxy-onboarding-v2 ${styles.overlay}`} role="dialog" aria-modal="true" aria-labelledby="roxy-onboarding-title">
    <div className={`${styles.shell} onboarding-card`}>
      <header className={styles.topline}>
        <div className={styles.brand}><span>R</span><strong>ROXY</strong></div>
        <button className={styles.skip} type="button" disabled={busy} onClick={() => void finish("home")}>Пропустить</button>
      </header>

      <div className={styles.progress} aria-label={`Шаг ${step + 1} из ${STEPS.length}`}>
        {STEPS.map((_, index) => <span key={index} className={index <= step ? styles.progressActive : ""} />)}
      </div>

      <main className={styles.content}>
        <FeatureVisual kind={current.visual} balance={me?.balance_rox} />
        <div className={styles.copy}>
          <span className={styles.eyebrow}>{current.eyebrow}</span>
          <h1 id="roxy-onboarding-title">{step === 0 ? `${name}, знакомьтесь с ROXY` : current.title}</h1>
          <p>{current.text}</p>
        </div>
      </main>

      <footer className={styles.footer}>
        {error ? <div className={styles.error} role="alert">{error}</div> : null}
        <button className={styles.primary} type="button" disabled={busy} onClick={next}>
          {busy ? "Сохраняю…" : last ? "Начать создавать" : step === 0 ? "Покажите, как всё устроено" : "Дальше"}
        </button>
        <div className={styles.legal}>
          {status.rules_url ? <button type="button" onClick={() => openExternalLink(String(status.rules_url))}>Правила</button> : null}
          {status.privacy_url ? <button type="button" onClick={() => openExternalLink(String(status.privacy_url))}>Конфиденциальность</button> : null}
        </div>
      </footer>
    </div>
  </div>;
}
