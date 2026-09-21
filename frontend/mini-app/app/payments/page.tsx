"use client";

import { useEffect, useMemo, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import {
  compactNumber,
  customerRequest,
  dateTime,
} from "@/lib/customer-api";
import {
  checkoutIdempotencyKey,
  clearCheckoutIdempotencyKey,
  type CheckoutIntent,
} from "@/lib/payment-idempotency";
import { openPaymentLink } from "@/lib/telegram";
import type { ActivePromo } from "@/lib/types";

type Currency = "RUB" | "USD" | "EUR";
type Provider = "card" | "yookassa" | "cryptobot" | "2328";
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
type PromoPreview = {
  status: "valid" | "activated" | "already_active";
  code: string;
  reward_rox: string;
  welcome_rox?: string;
  first_line_percent?: string;
  topup_partner_rox?: string;
  topup_user_rox?: string;
  topup_user_min_rub?: string;
  remaining_uses?: number | null;
  expires_at?: string | null;
  message?: string;
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
  package_bonus_credits?: string;
  promo_bonus_credits?: string;
  bonus_credits?: string;
  promo_code?: string;
  promo_bonus_status?: string;
  payment_url?: string;
  created_at?: string;
  updated_at?: string;
};

const TERMINAL = new Set(["succeeded", "refunded", "partially_refunded", "failed", "canceled", "expired"]);
const CRYPTOBOT_PROVIDER = "cryptobot";
const AMBIGUOUS_CREATION = new Set(["creating", "creation_unknown"]);

function initialProvider(): Provider {
  if (typeof window !== "undefined") {
    const requested = new URLSearchParams(window.location.search).get("provider");
    if (requested === "card") return "card";
    if (requested === "cryptobot") return "cryptobot";
  }
  return "yookassa";
}

function paymentProviderLabel(payment: Payment): string {
  if (payment.label) return payment.label;
  if (payment.provider === "yookassa") return "ЮKassa";
  if (payment.provider === CRYPTOBOT_PROVIDER) return "CryptoBot";
  if (payment.provider === "2328") return "2328";
  return "Lava Top";
}

function paymentRoxSummary(payment: Payment): string {
  const credited = payment.credits || payment.rox || payment.base_credits;
  const packageBonus = Number(payment.package_bonus_credits || 0);
  const promoBonus = Number(payment.promo_bonus_credits || 0);
  const labels: string[] = [];
  if (packageBonus > 0) labels.push(`+${compactNumber(packageBonus)} пакетный бонус`);
  if (promoBonus > 0 && payment.promo_code) {
    labels.push(`+${compactNumber(promoBonus)} по ${payment.promo_code}`);
  } else if (payment.promo_code && payment.promo_bonus_status === "below_threshold") {
    labels.push(`промокод ${payment.promo_code}: порог не достигнут`);
  } else if (payment.promo_code && payment.promo_bonus_status === "activated") {
    labels.push(`промокод ${payment.promo_code} активен`);
  }
  const suffix = labels.length ? ` · ${labels.join(" · ")}` : "";
  return `${credited ? `${compactNumber(credited)} ROX` : payment.package_id}${suffix}`;
}

export default function PaymentsPage() {
  const [cardCatalog, setCardCatalog] = useState<PackageResponse | null>(null);
  const [yooKassaCatalog, setYooKassaCatalog] = useState<PackageResponse | null>(null);
  const [cryptoBotCatalog, setCryptoBotCatalog] = useState<PackageResponse | null>(null);
  const [crypto2328Catalog, setCrypto2328Catalog] = useState<PackageResponse | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [provider, setProvider] = useState<Provider>(initialProvider);
  const [packageId, setPackageId] = useState("");
  const [currency, setCurrency] = useState<Currency>("RUB");
  const [email, setEmail] = useState("");
  const [promoCode, setPromoCode] = useState("");
  const [promo, setPromo] = useState<PromoPreview | null>(null);
  const [activePromo, setActivePromo] = useState<ActivePromo | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    const [cardResult, yooKassaResult, cryptoBotResult, paymentsResult, promoStateResult] = await Promise.allSettled([
      customerRequest<PackageResponse>("/api/v1/payments/card/packages"),
      customerRequest<PackageResponse>("/api/v1/payments/yookassa/packages"),
      customerRequest<PackageResponse>("/api/v1/payments/crypto/packages"),
      customerRequest<{ items: Payment[] }>("/api/v1/payments?limit=50"),
      customerRequest<ActivePromo>("/api/v1/promocodes/active"),
    ]);

    const nextCardCatalog = cardResult.status === "fulfilled" ? cardResult.value : null;
    const nextYooKassaCatalog = yooKassaResult.status === "fulfilled" ? yooKassaResult.value : null;
    const nextCryptoBotCatalog = cryptoBotResult.status === "fulfilled" ? cryptoBotResult.value : null;
    const cardReady = Boolean(
      nextCardCatalog?.configured && Object.keys(nextCardCatalog.packages || {}).length,
    );
    const yooKassaReady = Boolean(
      nextYooKassaCatalog?.configured && Object.keys(nextYooKassaCatalog.packages || {}).length,
    );
    const cryptoBotReady = Boolean(
      nextCryptoBotCatalog?.configured && Object.keys(nextCryptoBotCatalog.packages || {}).length,
    );

    setCardCatalog(nextCardCatalog);
    setYooKassaCatalog(nextYooKassaCatalog);
    setCryptoBotCatalog(nextCryptoBotCatalog);
    setCrypto2328Catalog(null);
    if (paymentsResult.status === "fulfilled") {
      setPayments(paymentsResult.value.items || []);
    }
    if (promoStateResult.status === "fulfilled") {
      setActivePromo(promoStateResult.value);
    }
    setProvider((current) => {
      if (current === "card" && cardReady) return "card";
      if (current === "cryptobot" && cryptoBotReady) return "cryptobot";
      if (yooKassaReady) return "yookassa";
      if (cardReady) return "card";
      if (cryptoBotReady) return "cryptobot";
      return "yookassa";
    });

    const loadErrors: string[] = [];
    if (!yooKassaReady && !cardReady && !cryptoBotReady) {
      loadErrors.push("Пополнение сейчас недоступно. Попробуйте ещё раз позже.");
    }
    if (paymentsResult.status === "rejected") {
      loadErrors.push("Не удалось загрузить историю пополнений. Обновите экран или попробуйте позже.");
    }
    setError(loadErrors.join(" "));
    setLoading(false);
  };

  const validatePromo = async (rawCode = promoCode) => {
    const normalized = rawCode.trim().toUpperCase();
    if (!normalized || busy || loading) return;
    setBusy("promo");
    setError("");
    setNotice("");
    try {
      const next = await customerRequest<PromoPreview>("/api/v1/promocodes/redeem", {
        method: "POST",
        body: JSON.stringify({ code: normalized }),
      });
      setPromo(next);
      setPromoCode(next.code);
      const persisted = await customerRequest<ActivePromo>("/api/v1/promocodes/active");
      setActivePromo(persisted);
      setNotice(next.message || "Промокод активирован");
    } catch (reason) {
      setPromo(null);
      setError(reason instanceof Error ? reason.message : "Не удалось проверить промокод");
    } finally {
      setBusy(null);
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
    : provider === "yookassa"
      ? yooKassaCatalog
      : provider === "cryptobot"
        ? cryptoBotCatalog
        : crypto2328Catalog;
  const activeCurrency: Currency = provider === "card" ? currency : "RUB";
  const cardAvailable = Boolean(
    cardCatalog?.configured && Object.keys(cardCatalog.packages || {}).length,
  );
  const yooKassaAvailable = Boolean(
    yooKassaCatalog?.configured && Object.keys(yooKassaCatalog.packages || {}).length,
  );
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
  const promoEnabled = Boolean(
    promo?.code && activePromo?.active && activePromo.program_active && activePromo.bonus_eligible !== false,
  );
  const activePromoCode = activePromo?.code || "";
  const hasActivePromoCode = Boolean(activePromo?.active && activePromoCode);
  const providerLabel = provider === "card"
    ? "Lava Top"
    : catalog?.label || (provider === "yookassa" ? "ЮKassa" : provider === "cryptobot" ? "CryptoBot" : "2328");
  const providerAvailable = provider === "card"
    ? cardAvailable
    : provider === "yookassa"
      ? yooKassaAvailable
      : provider === "cryptobot"
        ? cryptoBotAvailable
        : crypto2328Available;
  const supportedPayments = useMemo(
    () => payments.filter((item) => (
      item.provider === "card"
      || item.provider === "yookassa"
      || item.provider === CRYPTOBOT_PROVIDER
      || item.provider === "2328"
    )),
    [payments],
  );

  const checkout = async () => {
    if (loading || !packageId || !price || busy || (provider === "card" && !email.trim())) return;
    if (!activePromo?.active && promoCode.trim() && !promo) {
      setError("Сначала примените промокод или очистите поле.");
      return;
    }
    const effectivePromo = promo?.code || "";
    const intent: CheckoutIntent = {
      provider,
      packageId,
      currency: activeCurrency,
      billingEmail: provider === "card" ? email.trim() : "",
      promoCode: effectivePromo,
    };
    const requestKey = checkoutIdempotencyKey(intent);

    setBusy("checkout");
    setError("");
    setNotice("");
    try {
      let payment: Payment;
      if (provider === "yookassa") {
        payment = await customerRequest<Payment>("/api/v1/payments", {
          method: "POST",
          headers: { "Idempotency-Key": requestKey },
          body: JSON.stringify({
            provider: "yookassa",
            package_id: packageId,
            promo_code: effectivePromo || null,
          }),
        });
      } else if (provider === "cryptobot") {
        payment = await customerRequest<Payment>("/api/v1/payments/crypto/checkout", {
          method: "POST",
          headers: { "Idempotency-Key": requestKey },
          body: JSON.stringify({ package_id: packageId, promo_code: effectivePromo || null }),
        });
      } else if (provider === "2328") {
        payment = await customerRequest<Payment>("/api/v1/payments/crypto/2328/checkout", {
          method: "POST",
          headers: { "Idempotency-Key": requestKey },
          body: JSON.stringify({ package_id: packageId, promo_code: effectivePromo || null }),
        });
      } else {
        payment = await customerRequest<Payment>("/api/v1/payments/card/checkout", {
          method: "POST",
          headers: { "Idempotency-Key": requestKey },
          body: JSON.stringify({
            package_id: packageId,
            currency,
            billing_email: email.trim(),
            promo_code: effectivePromo || null,
          }),
        });
        localStorage.setItem("roxy-billing-email", email.trim());
      }

      setPayments((current) => [
        payment,
        ...current.filter((item) => item.id !== payment.id),
      ]);

      if (AMBIGUOUS_CREATION.has(payment.status)) {
        setNotice(
          "Предыдущая попытка оплаты уже зарегистрирована. Второй счёт не создаём — проверьте её статус в истории ниже.",
        );
        return;
      }

      if (!payment.payment_url) {
        if (TERMINAL.has(payment.status)) {
          clearCheckoutIdempotencyKey(intent, requestKey);
          setNotice(
            payment.status === "succeeded"
              ? "Оплата уже подтверждена, ROX начислены."
              : `Текущий статус оплаты: ${payment.status}`,
          );
        } else {
          setNotice(
            "Оплата уже зарегистрирована, но ссылка ещё не получена. Второй счёт не создаём — проверьте статус в истории ниже.",
          );
        }
        return;
      }

      if (!openPaymentLink(payment.payment_url)) {
        throw new Error("Не удалось открыть платёжную ссылку");
      }
      clearCheckoutIdempotencyKey(intent, requestKey);
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
    if (loading || busy) return;
    setBusy(payment.id);
    setError("");
    setNotice("");
    try {
      const path = payment.provider === "yookassa"
        ? `/api/v1/payments/yookassa/${encodeURIComponent(payment.id)}/reconcile`
        : payment.provider === "2328"
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

  const providerHint = provider === "yookassa"
    ? "ЮKassa — оплата в рублях. Доступный способ выберите на защищённой странице оплаты."
    : provider === "cryptobot"
      ? "CryptoBot — основной крипто-способ. На странице счёта выберите удобную монету и сеть."
      : "2328 — дополнительный крипто-способ. На странице оплаты выберите удобную монету и сеть.";

  return (
    <StandaloneShell
      kicker="Баланс"
      title="Пополнения ROX"
      copy="Выберите пакет и способ оплаты."
    >
      {loading ? <p className="muted" role="status">Загружаем способы оплаты и историю…</p> : null}
      {error ? <div className="action-error" role="alert">{error}</div> : null}
      {!loading && error && !yooKassaAvailable && !cardAvailable && !cryptoBotAvailable ? <button className="secondary" type="button" onClick={() => void load()}>Повторить загрузку</button> : null}
      {notice ? <div className="panel"><p className="muted">{notice}</p></div> : null}
      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">Пополнение</span><h2>Способ оплаты</h2></div></div>
        <div className="segmented providers" aria-label="Способ оплаты">
          {yooKassaAvailable ? <button type="button" disabled={loading} className={provider === "yookassa" ? "active" : ""} onClick={() => setProvider("yookassa")}>ЮKassa</button> : null}
          {cardAvailable ? <button type="button" disabled={loading} className={provider === "card" ? "active" : ""} onClick={() => setProvider("card")}>Lava Top · резерв</button> : null}
          {cryptoBotAvailable ? <button type="button" disabled={loading} className={provider === "cryptobot" ? "active" : ""} onClick={() => setProvider("cryptobot")}>CryptoBot</button> : null}
        </div>

        {yooKassaAvailable && cardAvailable ? <p className="muted">Основной способ — ЮKassa. Lava Top используйте как резерв, если основной платёж не проходит.</p> : null}
        {!yooKassaAvailable && cardAvailable ? <p className="muted">ЮKassa сейчас недоступна — включён резервный способ Lava Top.</p> : null}
        {!yooKassaAvailable && !cardAvailable && cryptoBotAvailable ? <p className="muted">Оплата картой сейчас недоступна. Можно пополнить через CryptoBot.</p> : null}
        {!loading && !yooKassaAvailable && !cardAvailable && !cryptoBotAvailable ? <p className="muted">Пополнение сейчас недоступно.</p> : null}
        {providerAvailable ? <>
          <div className="section-title"><div><span className="kicker">{providerLabel}</span><h2>Выберите пакет</h2></div></div>
          <div className="package-grid">{Object.entries(catalog?.packages || {}).map(([id, item]) => {
            const bonus = promoEnabled ? Number(item.bonus_credits || 0) : 0;
            const total = Number(item.credits || 0) + bonus;
            return <button type="button" disabled={loading} key={id} className={id === packageId ? "package active" : "package"} onClick={() => setPackageId(id)}>
              <strong>{compactNumber(item.credits)} ROX</strong>
              {bonus > 0 ? <small>+{compactNumber(bonus)} ROX 🎁</small> : null}
              <small><strong>Итого {compactNumber(total)} ROX</strong></small>
              <small>{item.prices[activeCurrency] ? `${compactNumber(item.prices[activeCurrency])} ${activeCurrency}` : "Недоступно"}</small>
            </button>;
          })}</div>

          {provider === "card" ? <div className="segmented scrollable">{(catalog?.currencies || []).map((item) => <button type="button" disabled={loading} key={item} className={currency === item ? "active" : ""} onClick={() => setCurrency(item)}>{item}</button>)}</div> : <p className="muted">{providerHint}</p>}

          <div className="form-stack">
            {!hasActivePromoCode ? <>
              <label className="field">
                <span className="label">Есть промокод?</span>
                <input
                  className="control"
                  maxLength={64}
                  value={promoCode}
                  disabled={loading}
                  onChange={(event) => {
                    setPromoCode(event.target.value.toUpperCase());
                    setPromo(null);
                    setNotice("");
                  }}
                  placeholder="Например, KSENIA50"
                  autoCapitalize="characters"
                />
              </label>
              <button className="secondary wide" type="button" disabled={loading || busy !== null || !promoCode.trim()} onClick={() => void validatePromo()}>
                {busy === "promo" ? "Активирую…" : promo ? `Промокод ${promo.code} активирован` : "Активировать промокод"}
              </button>
            </> : <div className="panel">
              <p className="muted">Промокод {activePromoCode} активирован. Примените его к этой оплате, чтобы получить бонус выбранного пакета.</p>
              <button
                className="secondary wide"
                type="button"
                disabled={loading || busy !== null || promo?.code === activePromoCode}
                onClick={() => {
                  setPromoCode(activePromoCode);
                  setPromo({
                    status: "already_active",
                    code: activePromoCode,
                    reward_rox: "0",
                  });
                  setNotice(`Промокод ${activePromoCode} будет применён к этой оплате`);
                }}
              >
                {promo?.code === activePromoCode ? `Промокод ${activePromoCode} выбран` : "Применить к этой оплате"}
              </button>
            </div>}

            {provider === "card" ? <label className="field"><span className="label">Email для чека без + и дефиса</span><input className="control" type="email" autoComplete="email" value={email} disabled={loading} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label> : null}
            <button className="primary wide" type="button" disabled={loading || busy !== null || !packageId || !price || (provider === "card" && !email.trim())} onClick={() => void checkout()}>{busy === "checkout" ? "Создаю оплату…" : price ? `Оплатить ${compactNumber(price)} ${activeCurrency} через ${providerLabel}` : "Пакет недоступен"}</button>
          </div>
        </> : null}
      </div>

      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">История</span><h2>Пополнения</h2></div><button type="button" disabled={loading || busy !== null} onClick={() => void load()}>{loading ? "Обновляю…" : "Обновить"}</button></div>
        <div className="transaction-list">{loading ? null : supportedPayments.length ? supportedPayments.map((payment) => <div className="transaction" key={payment.id}>
          <div>
            <strong>{compactNumber(payment.amount)} {payment.currency}</strong>
            <small>{paymentProviderLabel(payment)} · {dateTime(payment.created_at)} · {payment.status}</small>
            <small>{paymentRoxSummary(payment)}</small>
          </div>
          <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {payment.payment_url && !TERMINAL.has(payment.status) ? <button type="button" disabled={loading || busy !== null} onClick={() => { if (!openPaymentLink(payment.payment_url || "")) setError("Не удалось открыть платёжную ссылку"); }}>Оплатить</button> : null}
            {!TERMINAL.has(payment.status) ? <button type="button" disabled={loading || busy !== null} onClick={() => void reconcile(payment)}>{busy === payment.id ? "…" : "Проверить статус"}</button> : <strong>{payment.status === "succeeded" ? "✓" : payment.status}</strong>}
          </span>
        </div>) : <p className="muted">Пополнений пока нет.</p>}</div>
      </div>
    </StandaloneShell>
  );
}
