"use client";

import { createPortal } from "react-dom";
import { useEffect, useMemo, useRef, useState } from "react";

import { compactNumber, customerIdempotencyKey, customerRequest } from "@/lib/customer-api";

type Invitation = {
  user_id: string;
  username?: string | null;
  first_name?: string | null;
  line: number;
  joined_at: string;
};

type Me = { balance_rox: string };

type TransferResponse = {
  id: string;
  recipient_user_id: string;
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
  const [items, setItems] = useState<Invitation[]>([]);
  const [balance, setBalance] = useState(0);
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
    void Promise.all([
      customerRequest<{ items: Invitation[] }>("/api/v1/referrals/invitations?line=1&limit=100"),
      customerRequest<Me>("/api/v1/me"),
    ]).then(([invites, me]) => {
      if (!active) return;
      const direct = (invites.items || []).filter((item) => item.line === 1);
      setItems(direct);
      setBalance(Number(me.balance_rox || 0));
      setRecipientId((current) => current || direct[0]?.user_id || "");
    }).catch((error) => {
      if (active) setMessage(error instanceof Error ? error.message : "Не удалось загрузить рефералов");
    });
    return () => { active = false; };
  }, [host]);

  const recipient = useMemo(
    () => items.find((item) => item.user_id === recipientId) || null,
    [items, recipientId],
  );
  const amountNumber = Number(amount);
  const validAmount = Number.isInteger(amountNumber) && amountNumber > 0 && amountNumber <= balance;

  const submit = async () => {
    if (!recipient || !validAmount || busy || submittingRef.current) return;
    const label = recipient.first_name || (recipient.username ? `@${recipient.username}` : "рефералу");
    if (!window.confirm(`Перевести ${compactNumber(amountNumber, 0)} ROX ${label}? Перевод необратим.`)) return;
    submittingRef.current = true;
    setBusy(true);
    setMessage("");
    try {
      const result = await customerRequest<TransferResponse>("/api/v1/referrals/rox-transfers", {
        method: "POST",
        body: JSON.stringify({
          recipient_user_id: recipient.user_id,
          amount_rox: amountNumber,
          idempotency_key: intentKey,
        }),
      });
      setBalance(Number(result.balance_rox || 0));
      setAmount("");
      setIntentKey(customerIdempotencyKey());
      setMessage(`Переведено ${compactNumber(result.amount_rox, 0)} ROX ${label}`);
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
      <span className="kicker">Поддержать реферала</span>
      <h3>Перевести ROX</h3>
      <p className="muted">ROX сразу попадут на основной баланс выбранного человека из вашей первой линии.</p>
      <p className="muted">Доступно: <strong>{compactNumber(balance, 0)} ROX</strong></p>
      {items.length ? (
        <>
          <label className="field">
            <span>Кому</span>
            <select value={recipientId} onChange={(event) => { setRecipientId(event.target.value); setIntentKey(customerIdempotencyKey()); setMessage(""); }}>
              {items.map((item) => (
                <option value={item.user_id} key={item.user_id}>
                  {item.first_name || item.username || "Реферал"}{item.username ? ` · @${item.username}` : ""}
                </option>
              ))}
            </select>
          </label>
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
              onChange={(event) => { setAmount(event.target.value.replace(/[^0-9]/g, "")); setIntentKey(customerIdempotencyKey()); setMessage(""); }}
            />
          </label>
          <button className="primary wide" type="button" disabled={!validAmount || busy} onClick={() => void submit()}>
            {busy ? "Перевожу…" : validAmount ? `Перевести ${compactNumber(amountNumber, 0)} ROX` : "Перевести ROX"}
          </button>
          <small>Перевод необратим. Получатель сможет тратить ROX на генерации как обычный баланс.</small>
        </>
      ) : <p className="muted">В первой линии пока нет пользователей, которым можно перевести ROX.</p>}
      {message ? <p role="status">{message}</p> : null}
    </div>,
    host,
  );
}
