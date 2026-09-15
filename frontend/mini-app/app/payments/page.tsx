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

function promoTopupBonusForPackage(item: Package | null | undefined, activePromo: ActivePromo | null): number {
  if (!item || !activePromo?.active || !activePromo.program_active) return 0;
  const minimumRub = Number(activePromo.topup_user_min_rub || 0);
  const rewardRox = Number(activePromo.topup_user_rox || 0);
  const rubBasis = Number(item.prices.RUB || item.credits || 0);
  return rubBasis >= minimumRub ? rewardRox : 0;
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
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = async () => {
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
  };

  const validatePromo = async (rawCode = promoCode) => {
    const normalized = rawCode.trim().toUpperCase();
    if (!normalized || busy) return;
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
      setNotice(next.message || `Промокод активирован. Бонус +${compactNumber(next.reward_rox)} ROX начисляется отдельно от оплаты.`);
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
  const packageBaseRox = Number(selected?.credits || 0);
  const packageBonusRox = Number(selected?.bonus_credits || 0);
  const promoTopupBonusRox = promoTopupBonusForPackage(selected, activePromo);
  const totalRox = Number(selected?.total_credits || packageBaseRox + packageBonusRox) + promoTopupBonusRox;
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
    if (!packageId || !price || busy || (provider === "card" && !email.trim())) return;
    if (!activePromo?.active && promoCode.trim() && !promo) {
      setError("Сначала примените промокод или очистите поле.");
      return;
    }
    // Persisted promo attribution is part of the payment intent because it
    // changes partner accounting. Re-send the stored code automatically so
    // checkout idempotency remains stable across reloads/deploys without asking
    // the user to enter the code again.
    const effectivePromo = activePromo?.code || promo?.code || "";
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
      const promoHint = effectivePromo
        ? promoTopupBonusRox > 0
          ? ` Промокод добавит ещё +${compactNumber(promoTopupBonusRox)} ROX после успешной оплаты.`
          : " Промокод активен, но выбранный пакет ниже порога дополнительного промо-бонуса."
        : "";
      setNotice(
        provider === "card"
          ? `Оплата создана. После оплаты вернитесь сюда и нажмите «Проверить статус».${promoHint}`
          : `Счёт ${providerLabel} создан. После оплаты вернитесь сюда — ROX начислятся автоматически.${promoHint}`,
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
      copy="ЮKassa — основной способ оплаты. Lava Top доступна как резерв, CryptoBot — для оплаты криптовалютой. Обычный бонус пакета начисляется независимо от промокода. Активный партнёрский промокод добавляет ещё отдельный ROX-бонус к подходящему пополнению."
    >
      {error ? <div className="action-error" role="alert">{error}</div> : null}
      {notice ? <div className="panel"><p className="muted">{notice}</p></div> : null}
      {activePromo?.active ? <div className="panel">
        <span className="kicker">Промокод применён</span>
        <h2>{activePromo.code}</h2>
        <div className="profile-stats">
          <div><strong>+{compactNumber(activePromo.welcome_rox_granted || 0)}</strong><span>ROX уже начислено</span></div>
          <div><strong>+{compactNumber(activePromo.topup_user_rox || 0)}</strong><span>ROX от {compactNumber(activePromo.topup_user_min_rub || 0)} ₽</span></div>
          <div><strong>{activePromo.program_active ? "Активна" : "Пауза"}</strong><span>партнёрская программа</span></div>
        </div>
        <p className="muted">Обычный бонус выбранного пакета сохраняется. При оплате от {compactNumber(activePromo.topup_user_min_rub || 0)} ₽ промокод добавит ещё +{compactNumber(activePromo.topup_user_rox || 0)} ROX сверху.</p>
      </div> : null}

      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">Пополнение</span><h2>Способ оплаты</h2></div></div>
        <div className="segmented providers" aria-label="Способ оплаты">
          {yooKassaAvailable ? <button type="button" className={provider === "yookassa" ? "active" : ""} onClick={() => setProvider("yookassa")}>ЮKassa</button> : null}
          {cardAvailable ? <button type="button" className={provider === "card" ? "active" : ""} onClick={() => setProvider("card")}>Lava Top · резерв</button> : null}
          {cryptoBotAvailable ? <button type="button" className={provider === "cryptobot" ? "active" : ""} onClick={() => setProvider("cryptobot")}>CryptoBot</button> : null}
        </div>

        {yooKassaAvailable && cardAvailable ? <p className="muted">Основной способ — ЮKassa. Lava Top используйте как резерв, если основной платёж не проходит.</p> : null}
        {!yooKassaAvailable && cardAvailable ? <p className="muted">ЮKassa сейчас недоступна — включён резервный способ Lava Top.</p> : null}
        {!yooKassaAvailable && !cardAvailable && cryptoBotAvailable ? <p className="muted">Оплата картой сейчас недоступна. Можно пополнить через CryptoBot.</p> : null}
        {!yooKassaAvailable && !cardAvailable && !cryptoBotAvailable ? <p className="muted">Пополнение сейчас недоступно.</p> : null}
        {providerAvailable ? <>
          <div className="section-title"><div><span className="kicker">{providerLabel}</span><h2>Выберите пакет</h2></div></div>
          <div className="package-grid">{Object.entries(catalog?.packages || {}).map(([id, item]) => <button type="button" key={id} className={id === packageId ? "package active" : "package"} onClick={() => setPackageId(id)}>
            <strong>{compactNumber(item.credits)} ROX</strong>
            {Number(item.bonus_credits || 0) > 0 ? <small>+{compactNumber(item.bonus_credits)} ROX 🎁</small> : null}
            {promoTopupBonusForPackage(item, activePromo) > 0 ? <small>+{compactNumber(promoTopupBonusForPackage(item, activePromo))} ROX по промокоду 🎟️</small> : null}
            <small><strong>Итого {compactNumber(Number(item.total_credits || item.credits) + promoTopupBonusForPackage(item, activePromo))} ROX</strong></small>
            <small>{item.prices[activeCurrency] ? `${compactNumber(item.prices[activeCurrency])} ${activeCurrency}` : "Недоступно"}</small>
          </button>)}</div>

          {provider === "card" ? <div className="segmented scrollable">{(catalog?.currencies || []).map((item) => <button type="button" key={item} className={currency === item ? "active" : ""} onClick={() => setCurrency(item)}>{item}</button>)}</div> : <p className="muted">{providerHint}</p>}

          {selected ? <div className="profile-stats">
            <div><strong>{compactNumber(packageBaseRox)}</strong><span>базовые ROX</span></div>
            <div><strong>+{compactNumber(packageBonusRox)}</strong><span>бонус пакета</span></div>
            {activePromo?.active ? <div><strong>+{compactNumber(promoTopupBonusRox)}</strong><span>по промокоду {activePromo.code}</span></div> : promo ? <div><strong>{promo.code}</strong><span>партнёрская программа активна</span></div> : null}
            <div><strong>{compactNumber(totalRox)}</strong><span>получите после оплаты</span></div>
          </div> : null}

          <div className="form-stack">
            {!activePromo?.active ? <>
              <label className="field">
                <span className="label">Есть промокод?</span>
                <input
                  className="control"
                  maxLength={64}
                  value={promoCode}
                  onChange={(event) => {
                    setPromoCode(event.target.value.toUpperCase());
                    setPromo(null);
                    setNotice("");
                  }}
                  placeholder="Например, KSENIA50"
                  autoCapitalize="characters"
                />
              </label>
              <button className="secondary wide" type="button" disabled={busy !== null || !promoCode.trim()} onClick={() => void validatePromo()}>
                {busy === "promo" ? "Активирую…" : promo ? `Промокод ${promo.code} активирован` : "Активировать промокод"}
              </button>
              {promo ? <small className="muted">Бонус +{compactNumber(promo.reward_rox)} ROX относится к активации промокода, а не к пакету пополнения.</small> : null}
            </> : <small className="muted">Промокод {activePromo.code} уже закреплён за аккаунтом и применяется автоматически.</small>}

            {provider === "card" ? <label className="field"><span className="label">Email для чека без + и дефиса</span><input className="control" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label> : null}
            <button className="primary wide" type="button" disabled={busy !== null || !packageId || !price || (provider === "card" && !email.trim())} onClick={() => void checkout()}>{busy === "checkout" ? "Создаю оплату…" : price ? `Оплатить ${compactNumber(price)} ${activeCurrency} через ${providerLabel}` : "Пакет недоступен"}</button>
          </div>
        </> : null}
      </div>

      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">История</span><h2>Пополнения</h2></div><button type="button" onClick={() => void load()}>Обновить</button></div>
        <div className="transaction-list">{supportedPayments.length ? supportedPayments.map((payment) => <div className="transaction" key={payment.id}>
          <div>
            <strong>{compactNumber(payment.amount)} {payment.currency}</strong>
            <small>{paymentProviderLabel(payment)} · {dateTime(payment.created_at)} · {payment.status}</small>
            <small>{paymentRoxSummary(payment)}</small>
          </div>
          <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {payment.payment_url && !TERMINAL.has(payment.status) ? <button type="button" onClick={() => { if (!openPaymentLink(payment.payment_url || "")) setError("Не удалось открыть платёжную ссылку"); }}>Оплатить</button> : null}
            {!TERMINAL.has(payment.status) ? <button type="button" disabled={busy === payment.id} onClick={() => void reconcile(payment)}>{busy === payment.id ? "…" : "Проверить статус"}</button> : <strong>{payment.status === "succeeded" ? "✓" : payment.status}</strong>}
          </span>
        </div>) : <p className="muted">Пополнений пока нет.</p>}</div>
      </div>
    </StandaloneShell>
  );
}
