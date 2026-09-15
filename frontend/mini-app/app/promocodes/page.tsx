"use client";

import { useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { compactNumber, customerRequest } from "@/lib/customer-api";

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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const activate = async () => {
    if (!code.trim() || busy) return;
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
      copy="Промокод один раз закрепляет партнёра и включает бонусную программу. Сам пакет пополнения при этом не меняется."
    >
      <div className="panel tool-panel">
        <div className="form-stack">
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
          {result ? <div className="profile-stats">
            <div><strong>+{compactNumber(result.welcome_rox)}</strong><span>ROX за активацию</span></div>
            <div><strong>{compactNumber(result.first_line_percent)}%</strong><span>партнёру с пополнений</span></div>
            <div><strong>+{compactNumber(result.topup_partner_rox)}</strong><span>ROX партнёру за пополнение</span></div>
          </div> : null}
          {result ? <p className="muted">{result.message || ("Промокод " + result.code + " активирован.")}</p> : null}
          <button className="secondary wide" type="button" disabled={busy || !code.trim()} onClick={() => void activate()}>
            {busy ? "Активирую…" : result ? ("Промокод " + result.code + " активирован") : "Активировать промокод"}
          </button>
          {result ? <button
            className="primary wide"
            type="button"
            onClick={() => window.location.assign("/mini-app/payments/")}
          >
            Перейти к пополнению
          </button> : null}
        </div>
      </div>
    </StandaloneShell>
  );
}
