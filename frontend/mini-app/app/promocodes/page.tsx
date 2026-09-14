"use client";

import { useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { compactNumber, customerRequest } from "@/lib/customer-api";

type PromoPreview = {
  status: "valid";
  code: string;
  reward_rox: string;
  package_id?: string | null;
  package_credits?: string | null;
  remaining_uses?: number | null;
  expires_at?: string | null;
  message?: string;
};

export default function PromocodesPage() {
  const [code, setCode] = useState("");
  const [result, setResult] = useState<PromoPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const validate = async () => {
    if (!code.trim() || busy) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const next = await customerRequest<PromoPreview>("/api/v1/promocodes/validate", {
        method: "POST",
        body: JSON.stringify({ code: code.trim() }),
      });
      setResult(next);
      setCode(next.code);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось проверить промокод");
    } finally {
      setBusy(false);
    }
  };

  return (
    <StandaloneShell
      kicker="Промокод"
      title="Бонус к пополнению"
      copy="Промокод не начисляет ROX сам по себе. Он добавляет бонус только после успешной оплаты."
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
            <div><strong>+{compactNumber(result.reward_rox)}</strong><span>ROX после оплаты</span></div>
            {result.remaining_uses !== null && result.remaining_uses !== undefined
              ? <div><strong>{compactNumber(result.remaining_uses, 0)}</strong><span>активаций осталось</span></div>
              : null}
          </div> : null}
          {result ? <p className="muted">Промокод {result.code} проверен. Бонус будет зарезервирован при создании платежа и начислен только после подтверждения оплаты{result.package_id ? ` пакета ${compactNumber(result.package_credits || result.package_id)} ROX` : ""}.</p> : null}
          <button className="secondary wide" type="button" disabled={busy || !code.trim()} onClick={() => void validate()}>
            {busy ? "Проверяю…" : "Проверить промокод"}
          </button>
          {result ? <button
            className="primary wide"
            type="button"
            onClick={() => {
              const params = new URLSearchParams({ promo: result.code });
              if (result.package_id) params.set("package", result.package_id);
              window.location.assign(`/mini-app/payments/?${params.toString()}`);
            }}
          >
            Перейти к пополнению · +{compactNumber(result.reward_rox)} ROX
          </button> : null}
        </div>
      </div>
    </StandaloneShell>
  );
}
