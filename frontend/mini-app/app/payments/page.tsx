"use client";

import { useEffect, useMemo, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { compactNumber, customerIdempotencyKey, customerRequest, dateTime } from "@/lib/customer-api";
import { telegram } from "@/lib/telegram";

type Currency = "RUB" | "USD" | "EUR";
type Package = { credits: string; bonus_credits: string; total_credits: string; prices: Record<string, string> };
type PackageResponse = { provider: string; label: string; currencies: Currency[]; packages: Record<string, Package> };
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

function openPayment(url: string) {
  const tg = telegram();
  if (tg?.openLink) tg.openLink(url);
  else window.open(url, "_blank", "noopener,noreferrer");
}

export default function PaymentsPage() {
  const [catalog, setCatalog] = useState<PackageResponse | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [packageId, setPackageId] = useState("");
  const [currency, setCurrency] = useState<Currency>("RUB");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = async () => {
    setError("");
    try {
      const [packagesResult, paymentsResult] = await Promise.all([
        customerRequest<PackageResponse>("/api/v1/payments/card/packages"),
        customerRequest<{ items: Payment[] }>("/api/v1/payments?limit=50"),
      ]);
      setCatalog(packagesResult);
      setPayments(paymentsResult.items || []);
      const ids = Object.keys(packagesResult.packages || {});
      setPackageId((current) => current && packagesResult.packages[current] ? current : ids[0] || "");
      setCurrency((current) => packagesResult.currencies.includes(current) ? current : packagesResult.currencies[0] || "RUB");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить оплаты");
    }
  };

  useEffect(() => {
    const savedEmail = typeof localStorage !== "undefined" ? localStorage.getItem("roxy-billing-email") || "" : "";
    setEmail(savedEmail);
    void load();
  }, []);

  const selected = packageId ? catalog?.packages[packageId] : null;
  const price = selected?.prices[currency];
  const supportedPayments = useMemo(() => payments.filter((item) => !catalog?.provider || item.provider === catalog.provider), [catalog?.provider, payments]);

  const checkout = async () => {
    if (!packageId || !price || !email.trim() || busy) return;
    setBusy("checkout"); setError(""); setNotice("");
    try {
      const payment = await customerRequest<Payment>("/api/v1/payments/card/checkout", {
        method: "POST",
        headers: { "Idempotency-Key": customerIdempotencyKey() },
        body: JSON.stringify({ package_id: packageId, currency, billing_email: email.trim() }),
      });
      localStorage.setItem("roxy-billing-email", email.trim());
      setPayments((current) => [payment, ...current.filter((item) => item.id !== payment.id)]);
      if (payment.payment_url) openPayment(payment.payment_url);
      setNotice("Оплата создана. После оплаты вернитесь сюда и нажмите «Проверить статус».");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось создать оплату");
    } finally { setBusy(null); }
  };

  const reconcile = async (payment: Payment) => {
    setBusy(payment.id); setError(""); setNotice("");
    try {
      const next = await customerRequest<Payment>(`/api/v1/payments/card/${encodeURIComponent(payment.id)}/reconcile`, { method: "POST" });
      setPayments((current) => current.map((item) => item.id === next.id ? { ...item, ...next } : item));
      setNotice(next.status === "succeeded" ? "Оплата подтверждена, ROX начислены." : `Текущий статус: ${next.status}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось обновить статус оплаты");
    } finally { setBusy(null); }
  };

  return (
    <StandaloneShell kicker="Баланс" title="Пополнения ROX" copy="До оплаты видно базовое начисление, бонус и итог. Если webhook задержался, статус можно безопасно перепроверить вручную.">
      {error ? <div className="action-error" role="alert">{error}</div> : null}
      {notice ? <div className="panel"><p className="muted">{notice}</p></div> : null}

      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">{catalog?.label || "Оплата картой"}</span><h2>Выберите пакет</h2></div></div>
        <div className="package-grid">{Object.entries(catalog?.packages || {}).map(([id, item]) => <button type="button" key={id} className={id === packageId ? "package active" : "package"} onClick={() => setPackageId(id)}>
          <strong>{compactNumber(item.total_credits)} ROX</strong>
          <small>{compactNumber(item.credits)} + {compactNumber(item.bonus_credits)} бонус</small>
          <small>{item.prices[currency] ? `${compactNumber(item.prices[currency])} ${currency}` : "Недоступно"}</small>
        </button>)}</div>
        <div className="segmented scrollable">{(catalog?.currencies || []).map((item) => <button type="button" key={item} className={currency === item ? "active" : ""} onClick={() => setCurrency(item)}>{item}</button>)}</div>
        {selected ? <div className="profile-stats"><div><strong>{compactNumber(selected.credits)}</strong><span>базовые ROX</span></div><div><strong>+{compactNumber(selected.bonus_credits)}</strong><span>бонус</span></div><div><strong>{compactNumber(selected.total_credits)}</strong><span>итого ROX</span></div></div> : null}
        <div className="form-stack">
          <label className="field"><span className="label">Email для чека</span><input className="control" type="text" inputMode="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label>
          <button className="primary wide" type="button" disabled={busy !== null || !packageId || !price || !email.trim()} onClick={() => void checkout()}>{busy === "checkout" ? "Создаю оплату…" : price ? `Оплатить ${compactNumber(price)} ${currency}` : "Пакет недоступен"}</button>
        </div>
      </div>

      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">История</span><h2>Оплаты картой</h2></div><button type="button" onClick={() => void load()}>Обновить</button></div>
        <div className="transaction-list">{supportedPayments.length ? supportedPayments.map((payment) => <div className="transaction" key={payment.id}>
          <div><strong>{compactNumber(payment.amount)} {payment.currency}</strong><small>{dateTime(payment.created_at)} · {payment.status}</small><small>{payment.credits || payment.rox ? `${compactNumber(payment.credits || payment.rox)} ROX` : payment.package_id}</small></div>
          <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {payment.payment_url && !["succeeded", "refunded", "partially_refunded"].includes(payment.status) ? <button type="button" onClick={() => openPayment(payment.payment_url || "")}>Оплатить</button> : null}
            {!["succeeded", "refunded", "partially_refunded", "failed", "canceled"].includes(payment.status) ? <button type="button" disabled={busy === payment.id} onClick={() => void reconcile(payment)}>{busy === payment.id ? "…" : "Проверить статус"}</button> : <strong>{payment.status === "succeeded" ? "✓" : payment.status}</strong>}
          </span>
        </div>) : <p className="muted">Оплат картой пока нет.</p>}</div>
      </div>
    </StandaloneShell>
  );
}
