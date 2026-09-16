"use client";

import { useEffect, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { compactNumber, customerRequest } from "@/lib/customer-api";
import type { ActivePromo } from "@/lib/types";

type PromoActivation = {
  status: "activated" | "already_active";
  code: string;
  reward_rox: string;
  welcome_rox: string;
  first_line_percent: string;
  topup_partner_rox: string;
  balance_rox: string;
  message?: string;
};

export default function PromocodesPage() {
  const [code, setCode] = useState("");
  const [result, setResult] = useState<PromoActivation | null>(null);
  const [activePromo, setActivePromo] = useState<ActivePromo | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refreshActive = async () => {
    const state = await customerRequest<ActivePromo>("/api/v1/promocodes/active");
    setActivePromo(state);
    if (state.active && state.code) setCode(state.code);
    return state;
  };

  const loadActive = async () => {
    setLoading(true);
    setError("");
    try {
      await refreshActive();
    } catch (reason) {
      setActivePromo(null);
      setError(reason instanceof Error ? reason.message : "Не удалось проверить активный промокод");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void loadActive(); }, []);

  const activate = async () => {
    if (!code.trim() || busy || activePromo?.active) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const next = await customerRequest<PromoActivation>("/api/v1/promocodes/redeem", {
        method: "POST",
        body: JSON.stringify({ code: code.trim() }),
      });
      setResult(next);
      setCode(next.code);
      await refreshActive();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось активировать промокод");
    } finally {
      setBusy(false);
    }
  };

  return (
    <StandaloneShell
      kicker="Промокод"
      title="Партнёрские бонусы"
      copy="Активируйте промокод, чтобы бонус выбранного пакета начислился после успешной оплаты."
    >
      <div className="panel tool-panel">
        {loading ? <p className="muted" role="status">Проверяем активный промокод…</p> : null}
        {!loading && error && !activePromo ? <div className="form-stack">
          <div className="action-error" role="alert">{error}</div>
          <button className="secondary" type="button" onClick={() => void loadActive()}>Повторить загрузку</button>
        </div> : null}

        {!loading && !error && activePromo?.active ? <div className="form-stack">
          <span className="kicker">Промокод применён</span>
          <h2>{activePromo.code}</h2>
          <p className="muted">
            Промокод закреплён за аккаунтом. Бонус пакета начислится только после успешной оплаты.
          </p>
          {!activePromo.program_active ? <p className="muted">
            Бонусная программа временно приостановлена, привязка промокода сохранена.
          </p> : null}
          <button
            className="primary wide"
            type="button"
            onClick={() => window.location.assign("/mini-app/payments/")}
          >
            Перейти к пополнению
          </button>
        </div> : null}

        {!loading && !error && !activePromo?.active ? <div className="form-stack">
          <label className="field">
            <span className="label">Промокод</span>
            <input
              className="control"
              maxLength={64}
              value={code}
              onChange={(event) => {
                setCode(event.target.value.toUpperCase());
                setResult(null);
              }}
              placeholder="Например, KSENIA50"
              autoCapitalize="characters"
            />
          </label>
          {error ? <div className="action-error" role="alert">{error}</div> : null}
          {result ? <p className="muted">
            {result.message || ("Промокод " + result.code + " активирован.")} Бонус пакета будет начислен после успешной оплаты.
          </p> : null}
          <button className="secondary wide" type="button" disabled={busy || !code.trim()} onClick={() => void activate()}>
            {busy ? "Активирую…" : "Активировать промокод"}
          </button>
        </div> : null}
      </div>
    </StandaloneShell>
  );
}
