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
type Provider = "card" | "cryptobot" | "2328";
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

const TERMINAL = new Set(["succeeded", "refunded", "partially_refunded", "failed", "canceled", "expired"]);
const CRYPTOBOT_PROVIDER = "cryptobot";

function initialProvider(): Provider {
  if (typeof window !== "undefined") {
    const requested = new URLSearchParams(window.location.search).get("provider");
    if (requested === "cryptobot") return "cryptobot";
    if (requested === "2328") return "2328";
  }
  return "card";
}

function paymentProviderLabel(payment: Payment): string {
  if (payment.label) return payment.label;
  if (payment.provider === CRYPTOBOT_PROVIDER) return "CryptoBot";
  if (payment.provider === "2328") return "2328";
  return "Lava Top";
}

export default function PaymentsPage() {
  const [cardCatalog, setCardCatalog] = useState<PackageResponse | null>(null);
  const [cryptoBotCatalog, setCryptoBotCatalog] = useState<PackageResponse | null>(null);
  const [crypto2328Catalog, setCrypto2328Catalog] = useState<PackageResponse | null>(null);
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
      const [cardResult, cryptoBotResult, crypto2328Result, paymentsResult] = await Promise.all([
        customerRequest<PackageResponse>("/api/v1/payments/card/packages"),
        customerRequest<PackageResponse>("/api/v1/payments/crypto/packages"),
        customerRequest<PackageResponse>("/api/v1/payments/crypto/2328/packages"),
        customerRequest<{ items: Payment[] }>("/api/v1/payments?limit=50"),
      ]);
      setCardCatalog(cardResult);
      setCryptoBotCatalog(cryptoBotResult);
      setCrypto2328Catalog(crypto2328Result);
      setPayments(paymentsResult.items || []);

      const cardAvailable = Object.keys(cardResult.packages || {}).length > 0;
      const cryptoBotAvailable = Boolean(
        cryptoBotResult.configured && Object.keys(cryptoBotResult.packages || {}).length > 0,
      );
      const crypto2328Available = Boolean(
        crypto2328Result.configured && Object.keys(crypto2328Result.packages || {}).length > 0,
      );
      setProvider((current) => {
        if (current === "card" && cardAvailable) return current;
        if (current === "cryptobot" && cryptoBotAvailable) return current;
        if (current === "2328" && crypto2328Available) return current;
        if (cardAvailable) return "card";
        if (cryptoBotAvailable) return "cryptobot";
        if (crypto2328Available) return "2328";
        return "card";
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

  const catalog = provider === "card"
    ? cardCatalog
    : provider === "cryptobot"
      ? cryptoBotCatalog
      : crypto2328Catalog;
  const activeCurrency: Currency = provider === "card" ? currency : "RUB";
  const cardAvailable = Boolean(cardCatalog && Object.keys(cardCatalog.packages || {}).length);
  const cryptoBotAvailable = Boolean(
    cryptoBotCatalog?.configured && Object.keys(cryptoBotCatalog.packages || {}).length,
  );
  const crypto2328Available = Boolean(
    crypto2328Catalog?.configured && Object.keys(crypto2328Catalog.packages || {}).length,
  );

  useEffect(() => {
    const ids = Object.keys(catalog?.packages || {});
    setPackageId((current) => current && catalog?.packages[current] ? current : ids[0] || "");
    if (provider !== "card") setCurrency("RUB");
  }, [catalog, provider]);

  const selected = packageId ? catalog?.packages[packageId] : null;
  const price = selected?.prices[activeCurrency];
  const providerLabel = provider === "card" ? "Lava Top" : catalog?.label || (provider === "cryptobot" ? "CryptoBot" : "2328");
  const providerAvailable = provider === "card"
    ? cardAvailable
    : provider === "cryptobot"
      ? cryptoBotAvailable
      : crypto2328Available;
  const supportedPayments = useMemo(
    () => payments.filter((item) => (
      item.provider === "card"
      || item.provider === CRYPTOBOT_PROVIDER
      || item.provider === "2328"
    )),
    [payments],
  );

  const checkout = async () => {
    if (!packageId || !price || busy || (provider === "card" && !email.trim())) return;
    setBusy("checkout");
    setError("");
    setNotice("");
    try {
      let payment: Payment;
      if (provider === "cryptobot") {
        payment = await customerRequest<Payment>("/api/v1/payments/crypto/checkout", {
          method: "POST",
          headers: { "Idempotency-Key": customerIdempotencyKey() },
          body: JSON.stringify({ package_id: packageId }),
        });
      } else if (provider === "2328") {
        payment = await customerRequest<Payment>("/api/v1/payments/crypto/2328/checkout", {
          method: "POST",
          headers: { "Idempotency-Key": customerIdempotencyKey() },
          body: JSON.stringify({ package_id: packageId }),
        });
      } else {
        payment = await customerRequest<Payment>("/api/v1/payments/card/checkout", {
          method: "POST",
          headers: { "Idempotency-Key": customerIdempotencyKey() },
          body: JSON.stringify({
            package_id: packageId,
            currency,
            billing_email: email.trim(),
          }),
        });
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
        provider === "card"
          ? "Оплата создана. После оплаты вернитесь сюда и нажмите «Проверить статус»."
          : `Счёт ${providerLabel} создан. После оплаты вернитесь сюда — ROX начислятся автоматически.`,
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
      const path = payment.provider === "2328"
        ? `/api/v1/payments/crypto/2328/${encodeURIComponent(payment.id)}/reconcile`
        : payment.provider === CRYPTOBOT_PROVIDER
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

  const cryptoHint = provider === "cryptobot"
    ? "CryptoBot — основной крипто-способ. На странице счёта выберите удобную монету и сеть."
    : "2328 — дополнительный крипто-способ. На странице оплаты выберите удобную монету и сеть.";

  return (
    <StandaloneShell
      kicker="Баланс"
      title="Пополнения ROX"
      copy="Карта и СБП доступны через Lava Top. Для криптовалюты основной способ — CryptoBot, дополнительный — 2328."
    >
      {error ? <div className="action-error" role="alert">{error}</div> : null}
      {notice ? <div className="panel"><p className="muted">{notice}</p></div> : null}

      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">Пополнение</span><h2>Способ оплаты</h2></div></div>
        <div className="segmented providers" aria-label="Способ оплаты">
          {cardAvailable ? <button type="button" className={provider === "card" ? "active" : ""} onClick={() => setProvider("card")}>Lava Top</button> : null}
          {cryptoBotAvailable ? <button type="button" className={provider === "cryptobot" ? "active" : ""} onClick={() => setProvider("cryptobot")}>CryptoBot</button> : null}
          {crypto2328Available ? <button type="button" className={provider === "2328" ? "active" : ""} onClick={() => setProvider("2328")}>2328</button> : null}
        </div>

        {!cardAvailable && !cryptoBotAvailable && !crypto2328Available ? <p className="muted">Пополнение сейчас недоступно.</p> : null}
        {providerAvailable ? <>
          <div className="section-title"><div><span className="kicker">{providerLabel}</span><h2>Выберите пакет</h2></div></div>
          <div className="package-grid">{Object.entries(catalog?.packages || {}).map(([id, item]) => <button type="button" key={id} className={id === packageId ? "package active" : "package"} onClick={() => setPackageId(id)}>
            <strong>{compactNumber(item.total_credits || item.credits)} ROX</strong>
            <small>{Number(item.bonus_credits || 0) > 0 ? `${compactNumber(item.credits)} + ${compactNumber(item.bonus_credits)} бонус` : `${compactNumber(item.credits)} ROX`}</small>
            <small>{item.prices[activeCurrency] ? `${compactNumber(item.prices[activeCurrency])} ${activeCurrency}` : "Недоступно"}</small>
          </button>)}</div>

          {provider === "card" ? <div className="segmented scrollable">{(catalog?.currencies || []).map((item) => <button type="button" key={item} className={currency === item ? "active" : ""} onClick={() => setCurrency(item)}>{item}</button>)}</div> : <p className="muted">{cryptoHint}</p>}

          {selected ? <div className="profile-stats"><div><strong>{compactNumber(selected.credits)}</strong><span>базовые ROX</span></div><div><strong>+{compactNumber(selected.bonus_credits || 0)}</strong><span>бонус</span></div><div><strong>{compactNumber(selected.total_credits || selected.credits)}</strong><span>итого ROX</span></div></div> : null}

          <div className="form-stack">
            {provider === "card" ? <label className="field"><span className="label">Email для чека без + и дефиса</span><input className="control" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label> : null}
            <button className="primary wide" type="button" disabled={busy !== null || !packageId || !price || (provider === "card" && !email.trim())} onClick={() => void checkout()}>{busy === "checkout" ? "Создаю оплату…" : price ? `Оплатить ${compactNumber(price)} ${activeCurrency} через ${providerLabel}` : "Пакет недоступен"}</button>
          </div>
        </> : null}
      </div>

      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">История</span><h2>Пополнения</h2></div><button type="button" onClick={() => void load()}>Обновить</button></div>
        <div className="transaction-list">{supportedPayments.length ? supportedPayments.map((payment) => <div className="transaction" key={payment.id}>
          <div><strong>{compactNumber(payment.amount)} {payment.currency}</strong><small>{paymentProviderLabel(payment)} · {dateTime(payment.created_at)} · {payment.status}</small><small>{payment.credits || payment.rox ? `${compactNumber(payment.credits || payment.rox)} ROX` : payment.package_id}</small></div>
          <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {payment.payment_url && !TERMINAL.has(payment.status) ? <button type="button" onClick={() => { if (!openPaymentLink(payment.payment_url || "")) setError("Не удалось открыть платёжную ссылку"); }}>Оплатить</button> : null}
            {!TERMINAL.has(payment.status) ? <button type="button" disabled={busy === payment.id} onClick={() => void reconcile(payment)}>{busy === payment.id ? "…" : "Проверить статус"}</button> : <strong>{payment.status === "succeeded" ? "✓" : payment.status}</strong>}
          </span>
        </div>) : <p className="muted">Пополнений пока нет.</p>}</div>
      </div>
    </StandaloneShell>
  );
}
