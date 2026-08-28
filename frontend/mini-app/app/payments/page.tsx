"use client";

import { useEffect, useMemo, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import {
  compactNumber,
  customerIdempotencyKey,
  customerRequest,
  dateTime,
} from "@/lib/customer-api";
import { openPaymentLink } from "@/lib/telegram";

type Currency = "RUB" | "USD" | "EUR";
type Provider = "card" | "cryptobot";
type Package = {
  credits: string;
  bonus_credits: string;
  total_credits: string;
  prices: Record<string, string>;
};
type PackageResponse = {
  provider: string;
  label: string;
  configured?: boolean;
  currencies: Currency[];
  packages: Record<string, Package>;
};
type Payment = {
  id: string;
  status: string;
  provider: string;
  label?: string;
  package_id: string;
  amount: string;
  currency: string;
  credits?: string;
  rox?: string;
  base_credits?: string;
  bonus_credits?: string;
  payment_url?: string;
  created_at?: string;
  updated_at?: string;
};

const TERMINAL = new Set(["succeeded", "refunded", "partially_refunded", "failed", "canceled"]);

function initialProvider(): Provider {
  return "card";
}

export default function PaymentsPage() {
  const [cardCatalog, setCardCatalog] = useState<PackageResponse | null>(null);
  const [cryptoCatalog, setCryptoCatalog] = useState<PackageResponse | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [provider, setProvider] = useState<Provider>(initialProvider);
  const [packageId, setPackageId] = useState("");
  const [currency, setCurrency] = useState<Currency>("RUB");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = async () => {
    setError("");
    try {
      const [cardResult, cryptoResult, paymentsResult] = await Promise.all([
        customerRequest<PackageResponse>("/api/v1/payments/card/packages"),
        customerRequest<PackageResponse>("/api/v1/payments/crypto/packages"),
        customerRequest<{ items: Payment[] }>("/api/v1/payments?limit=50"),
      ]);
      setCardCatalog(cardResult);
      setCryptoCatalog(cryptoResult);
      setPayments(paymentsResult.items || []);

      const cardAvailable = Object.keys(cardResult.packages || {}).length > 0;
      const cryptoAvailable = Boolean(
        cryptoResult.configured && Object.keys(cryptoResult.packages || {}).length > 0,
      );
      setProvider((current) => {
        if (current === "cryptobot" && cryptoAvailable) return current;
        if (current === "card" && cardAvailable) return current;
        return cardAvailable ? "card" : cryptoAvailable ? "cryptobot" : "card";
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить оплаты");
    }
  };

  useEffect(() => {
    const savedEmail = typeof localStorage !== "undefined"
      ? localStorage.getItem("roxy-billing-email") || ""
      : "";
    setEmail(savedEmail);
    void load();
  }, []);

  const catalog = provider === "cryptobot" ? cryptoCatalog : cardCatalog;
  const activeCurrency: Currency = provider === "cryptobot" ? "RUB" : currency;
  const cardAvailable = Boolean(cardCatalog && Object.keys(cardCatalog.packages || {}).length);
  const cryptoAvailable = Boolean(
    cryptoCatalog?.configured && Object.keys(cryptoCatalog.packages || {}).length,
  );

  useEffect(() => {
    const ids = Object.keys(catalog?.packages || {});
    setPackageId((current) => current && catalog?.packages[current] ? current : ids[0] || "");
    if (provider === "cryptobot") setCurrency("RUB");
  }, [catalog, provider]);

  const selected = packageId ? catalog?.packages[packageId] : null;
  const price = selected?.prices[activeCurrency];
  const providerLabel = provider === "card" ? "Lava Top" : "CryptoBot";
  const supportedPayments = useMemo(
    () => payments.filter((item) => item.provider === "card" || item.provider === "cryptobot"),
    [payments],
  );

  const checkout = async () => {
    if (!packageId || !price || busy || (provider === "card" && !email.trim())) return;
    setBusy("checkout");
    setError("");
    setNotice("");
    try {
      const payment = provider === "cryptobot"
        ? await customerRequest<Payment>("/api/v1/payments/crypto/checkout", {
          method: "POST",
          headers: { "Idempotency-Key": customerIdempotencyKey() },
          body: JSON.stringify({ package_id: packageId }),
        })
        : await customerRequest<Payment>("/api/v1/payments/card/checkout", {
          method: "POST",
          headers: { "Idempotency-Key": customerIdempotencyKey() },
          body: JSON.stringify({
            package_id: packageId,
            currency,
            billing_email: email.trim(),
          }),
        });

      if (provider === "card") {
        localStorage.setItem("roxy-billing-email", email.trim());
      }
      setPayments((current) => [
        payment,
        ...current.filter((item) => item.id !== payment.id),
      ]);
      if (payment.payment_url && !openPaymentLink(payment.payment_url)) {
        throw new Error("Не удалось открыть платёжную ссылку");
      }
      setNotice(
        provider === "cryptobot"
          ? "Счёт CryptoBot создан. После оплаты вернитесь сюда — ROX начислятся автоматически."
          : "Оплата создана. После оплаты вернитесь сюда и нажмите «Проверить статус».",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось создать оплату");
    } finally {
      setBusy(null);
    }
  };

  const reconcile = async (payment: Payment) => {
    setBusy(payment.id);
    setError("");
    setNotice("");
    try {
      const path = payment.provider === "cryptobot"
        ? `/api/v1/payments/crypto/${encodeURIComponent(payment.id)}/reconcile`
        : `/api/v1/payments/card/${encodeURIComponent(payment.id)}/reconcile`;
      const next = await customerRequest<Payment>(path, { method: "POST" });
      setPayments((current) => current.map((item) => (
        item.id === next.id ? { ...item, ...next } : item
      )));
      setNotice(
        next.status === "succeeded"
          ? "Оплата подтверждена, ROX начислены."
          : `Текущий статус: ${next.status}`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось обновить статус оплаты");
    } finally {
      setBusy(null);
    }
  };

  return (
    <StandaloneShell
      kicker="Баланс"
      title="Пополнения ROX"
      copy="Основной способ оплаты — Lava Top. CryptoBot доступен как резервный вариант."
    >
      {error ? <div className="action-error" role="alert">{error}</div> : null}
      {notice ? <div className="panel"><p className="muted">{notice}</p></div> : null}

      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">Пополнение</span><h2>Способ оплаты</h2></div></div>
        <div className="segmented providers" aria-label="Способ оплаты">
          {cardAvailable ? <button type="button" className={provider === "card" ? "active" : ""} onClick={() => setProvider("card")}>Lava Top</button> : null}
          {cryptoAvailable ? <button type="button" className={provider === "cryptobot" ? "active" : ""} onClick={() => setProvider("cryptobot")}>CryptoBot</button> : null}
        </div>

        {!cardAvailable && !cryptoAvailable ? <p className="muted">Пополнение сейчас недоступно.</p> : null}
        {(provider === "card" ? cardAvailable : cryptoAvailable) ? <>
          <div className="section-title"><div><span className="kicker">{providerLabel}</span><h2>Выберите пакет</h2></div></div>
          <div className="package-grid">{Object.entries(catalog?.packages || {}).map(([id, item]) => <button type="button" key={id} className={id === packageId ? "package active" : "package"} onClick={() => setPackageId(id)}>
            <strong>{compactNumber(item.total_credits || item.credits)} ROX</strong>
            <small>{Number(item.bonus_credits || 0) > 0 ? `${compactNumber(item.credits)} + ${compactNumber(item.bonus_credits)} бонус` : `${compactNumber(item.credits)} ROX`}</small>
            <small>{item.prices[activeCurrency] ? `${compactNumber(item.prices[activeCurrency])} ${activeCurrency}` : "Недоступно"}</small>
          </button>)}</div>

          {provider === "card" ? <div className="segmented scrollable">{(catalog?.currencies || []).map((item) => <button type="button" key={item} className={currency === item ? "active" : ""} onClick={() => setCurrency(item)}>{item}</button>)}</div> : <p className="muted">CryptoBot принимает TON, USDT, BTC, ETH и другие доступные монеты. Цена пакета фиксируется в RUB.</p>}

          {selected ? <div className="profile-stats"><div><strong>{compactNumber(selected.credits)}</strong><span>базовые ROX</span></div><div><strong>+{compactNumber(selected.bonus_credits || 0)}</strong><span>бонус</span></div><div><strong>{compactNumber(selected.total_credits || selected.credits)}</strong><span>итого ROX</span></div></div> : null}

          <div className="form-stack">
            {provider === "card" ? <label className="field"><span className="label">Email для чека</span><input className="control" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label> : null}
            <button className="primary wide" type="button" disabled={busy !== null || !packageId || !price || (provider === "card" && !email.trim())} onClick={() => void checkout()}>{busy === "checkout" ? "Создаю оплату…" : provider === "cryptobot" ? `Оплатить ${compactNumber(price)} RUB через CryptoBot` : price ? `Оплатить ${compactNumber(price)} ${currency} через Lava Top` : "Пакет недоступен"}</button>
          </div>
        </> : null}
      </div>

      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">История</span><h2>Пополнения</h2></div><button type="button" onClick={() => void load()}>Обновить</button></div>
        <div className="transaction-list">{supportedPayments.length ? supportedPayments.map((payment) => <div className="transaction" key={payment.id}>
          <div><strong>{compactNumber(payment.amount)} {payment.currency}</strong><small>{payment.provider === "cryptobot" ? "CryptoBot" : "Lava Top"} · {dateTime(payment.created_at)} · {payment.status}</small><small>{payment.credits || payment.rox ? `${compactNumber(payment.credits || payment.rox)} ROX` : payment.package_id}</small></div>
          <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {payment.payment_url && !TERMINAL.has(payment.status) ? <button type="button" onClick={() => { if (!openPaymentLink(payment.payment_url || "")) setError("Не удалось открыть платёжную ссылку"); }}>Оплатить</button> : null}
            {!TERMINAL.has(payment.status) ? <button type="button" disabled={busy === payment.id} onClick={() => void reconcile(payment)}>{busy === payment.id ? "…" : "Проверить статус"}</button> : <strong>{payment.status === "succeeded" ? "✓" : payment.status}</strong>}
          </span>
        </div>) : <p className="muted">Пополнений пока нет.</p>}</div>
      </div>
    </StandaloneShell>
  );
}
