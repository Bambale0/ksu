"use client";

import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";

import { compactNumber, customerIdempotencyKey, customerRequest } from "@/lib/customer-api";

type Me = {
  telegram_id: number;
  balance_rox: string;
};

type TransferResponse = {
  id: string;
  recipient_user_id: string;
  recipient_telegram_id: number;
  amount_rox: string;
  balance_rox: string;
};

function findPartnerHost(): HTMLElement | null {
  const screens = Array.from(document.querySelectorAll<HTMLElement>("main .screen"));
  const screen = screens.find((item) => item.textContent?.includes("Кабинет автора"));
  if (!screen) return null;
  let host = screen.querySelector<HTMLElement>("[data-partner-rox-transfer-host]");
  if (!host) {
    host = document.createElement("div");
    host.dataset.partnerRoxTransferHost = "true";
    const panels = screen.querySelectorAll(":scope > .panel");
    const anchor = panels.item(Math.min(1, Math.max(0, panels.length - 1)));
    if (anchor?.nextSibling) screen.insertBefore(host, anchor.nextSibling);
    else screen.appendChild(host);
  }
  return host;
}

export function PartnerRoxTransfer() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [balance, setBalance] = useState(0);
  const [senderTelegramId, setSenderTelegramId] = useState<number | null>(null);
  const [recipientId, setRecipientId] = useState("");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [intentKey, setIntentKey] = useState(() => customerIdempotencyKey());
  const submittingRef = useRef(false);

  useEffect(() => {
    let frame = 0;
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setHost(findPartnerHost()));
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("popstate", sync);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("popstate", sync);
    };
  }, []);

  useEffect(() => {
    if (!host) return;
    let active = true;
    void customerRequest<Me>("/api/v1/me").then((me) => {
      if (!active) return;
      setBalance(Number(me.balance_rox || 0));
      setSenderTelegramId(Number(me.telegram_id));
    }).catch((error) => {
      if (active) setMessage(error instanceof Error ? error.message : "Не удалось загрузить баланс");
    });
    return () => { active = false; };
  }, [host]);

  const recipientTelegramId = Number(recipientId);
  const validRecipient = /^\d+$/.test(recipientId)
    && Number.isSafeInteger(recipientTelegramId)
    && recipientTelegramId > 0
    && recipientTelegramId !== senderTelegramId;
  const amountNumber = Number(amount);
  const validAmount = Number.isInteger(amountNumber) && amountNumber > 0 && amountNumber <= balance;

  const resetIntent = () => {
    setIntentKey(customerIdempotencyKey());
    setMessage("");
  };

  const submit = async () => {
    if (!validRecipient || !validAmount || busy || submittingRef.current) return;
    if (!window.confirm(`Перевести ${compactNumber(amountNumber, 0)} ROX пользователю ID ${recipientTelegramId}? Перевод необратим.`)) return;
    submittingRef.current = true;
    setBusy(true);
    setMessage("");
    try {
      const result = await customerRequest<TransferResponse>("/api/v1/referrals/rox-transfers", {
        method: "POST",
        body: JSON.stringify({
          recipient_telegram_id: recipientTelegramId,
          amount_rox: amountNumber,
          idempotency_key: intentKey,
        }),
      });
      setBalance(Number(result.balance_rox || 0));
      setAmount("");
      setRecipientId("");
      setIntentKey(customerIdempotencyKey());
      setMessage(`Переведено ${compactNumber(result.amount_rox, 0)} ROX пользователю ID ${result.recipient_telegram_id}`);
      window.dispatchEvent(new CustomEvent("roxy:wallet-updated", { detail: { balance_rox: result.balance_rox } }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось перевести ROX");
    } finally {
      submittingRef.current = false;
      setBusy(false);
    }
  };

  if (!host) return null;
  return createPortal(
    <div className="panel" data-partner-rox-transfer>
      <span className="kicker">Перевод пользователю</span>
      <h3>Перевести ROX</h3>
      <p className="muted">Введите ID пользователя ROXY. Его можно посмотреть в профиле рядом с именем.</p>
      <p className="muted">Доступно: <strong>{compactNumber(balance, 0)} ROX</strong></p>
      <label className="field">
        <span>ID пользователя</span>
        <input
          inputMode="numeric"
          type="text"
          autoComplete="off"
          value={recipientId}
          placeholder="Например, 123456789"
          onChange={(event) => {
            setRecipientId(event.target.value.replace(/[^0-9]/g, ""));
            resetIntent();
          }}
        />
      </label>
      {recipientId && senderTelegramId !== null && recipientTelegramId === senderTelegramId
        ? <small>Нельзя переводить ROX самому себе.</small>
        : null}
      <label className="field">
        <span>Сколько ROX</span>
        <input
          inputMode="numeric"
          type="number"
          min={1}
          step={1}
          max={Math.max(0, Math.floor(balance))}
          value={amount}
          placeholder="Например, 5500"
          onChange={(event) => {
            setAmount(event.target.value.replace(/[^0-9]/g, ""));
            resetIntent();
          }}
        />
      </label>
      <button className="primary wide" type="button" disabled={!validRecipient || !validAmount || busy} onClick={() => void submit()}>
        {busy ? "Перевожу…" : validAmount ? `Перевести ${compactNumber(amountNumber, 0)} ROX` : "Перевести ROX"}
      </button>
      <small>Перевод необратим. ROX сразу попадут на основной баланс получателя.</small>
      {message ? <p role="status">{message}</p> : null}
    </div>,
    host,
  );
}
