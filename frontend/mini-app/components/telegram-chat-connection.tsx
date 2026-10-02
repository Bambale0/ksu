"use client";

import { useEffect, useRef, useState } from "react";
import { CLIENT_REQUEST_TIMEOUT_MS } from "@/lib/http-errors";
import { getInitDataFallback, openTelegramShare, telegram } from "@/lib/telegram";
import type { Me } from "@/lib/types";
import styles from "./telegram-chat-connection.module.css";

type Status = "hidden" | "idle" | "requesting" | "granted" | "denied" | "unavailable";

function permissionKnown(): boolean {
  // UI hints only. The backend never accepts a client permission claim.
  if (telegram()?.initDataUnsafe?.user?.allows_write_to_pm === true) return true;
  try {
    const user = JSON.parse(new URLSearchParams(getInitDataFallback()).get("user") || "{}");
    return user?.allows_write_to_pm === true;
  } catch {
    return false;
  }
}

function safeChatLink(value?: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && ["t.me", "telegram.me"].includes(url.hostname)
      && /^\/[A-Za-z0-9_]+$/.test(url.pathname) ? url.toString() : null;
  } catch {
    return null;
  }
}

export function TelegramChatConnection({ me }: { me: Me }) {
  const [status, setStatus] = useState<Status>("hidden");
  const timer = useRef<number | null>(null);
  const requestEpoch = useRef(0);
  const inFlight = useRef(false);
  const storageKey = `roxy.telegram-write-granted.${me.telegram_id}`;
  const chatLink = safeChatLink(me.bot_chat_link);

  useEffect(() => {
    // Render only after the parent has authenticated /me. This prevents the
    // consent service message from racing first-touch referral registration.
    if (!getInitDataFallback() || !telegram()) return;
    let known = permissionKnown();
    try { known ||= window.sessionStorage.getItem(storageKey) === "1"; } catch { /* optional */ }
    setStatus(known ? "hidden" : "idle");
    return () => {
      requestEpoch.current += 1;
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, [storageKey]);

  const connect = () => {
    if (inFlight.current) return;
    const tg = telegram();
    const epoch = ++requestEpoch.current;
    let settled = false;
    const finish = (allowed: boolean) => {
      if (settled || epoch !== requestEpoch.current) return;
      settled = true;
      inFlight.current = false;
      if (timer.current !== null) window.clearTimeout(timer.current);
      if (allowed === true) {
        try { window.sessionStorage.setItem(storageKey, "1"); } catch { /* optional */ }
        setStatus("granted");
      } else {
        setStatus("denied");
      }
    };
    try {
      if (!tg?.requestWriteAccess || tg.isVersionAtLeast?.("6.9") === false) {
        setStatus("unavailable");
        return;
      }
      inFlight.current = true;
      setStatus("requesting");
      // Do not leave an endless spinner when a client omits its callback. A
      // late real callback may still resolve this request; never auto-retry it.
      timer.current = window.setTimeout(() => {
        if (!settled && epoch === requestEpoch.current) setStatus("unavailable");
      }, CLIENT_REQUEST_TIMEOUT_MS);
      tg.requestWriteAccess(finish);
    } catch {
      if (settled || epoch !== requestEpoch.current) return;
      settled = true;
      inFlight.current = false;
      if (timer.current !== null) window.clearTimeout(timer.current);
      setStatus("unavailable");
    }
  };

  if (status === "hidden") return null;
  return <section className={`panel ${styles.card}`} aria-label="Чат Telegram">
    <div className={styles.copy}>
      <h2>{status === "granted" ? "Сообщения в Telegram разрешены" : "Готовые работы — в чат Telegram"}</h2>
      <p aria-live="polite">{status === "granted"
        ? "Бот сможет присылать результаты. Все работы также остаются в истории приложения."
        : status === "denied"
          ? "Разрешение не получено. Можно продолжить без чата или открыть бота и нажать «Запустить»."
          : status === "unavailable"
            ? "Telegram не подтвердил разрешение. Откройте чат вручную и нажмите «Запустить»."
            : "Подключите чат ROXY для получения результатов. Сами работы всегда доступны в истории."}</p>
    </div>
    <div className={styles.actions}>
      {status !== "granted" && status !== "unavailable" && <button className="primary" type="button" disabled={status === "requesting"} onClick={connect}>
        {status === "requesting" ? "Ожидаю разрешение…" : "Подключить чат Telegram"}
      </button>}
      {chatLink && status !== "idle" && status !== "requesting" && <button className="secondary" type="button" onClick={() => openTelegramShare(chatLink)}>
        {status === "granted" ? "Открыть чат ROXY" : "Открыть чат вручную"}
      </button>}
    </div>
  </section>;
}
