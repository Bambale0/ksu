"use client";

import { useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { compactNumber, customerRequest } from "@/lib/customer-api";

type RedeemResult = { status: string; reward_rox: string; balance_rox: string };

export default function PromocodesPage() {
  const [code, setCode] = useState("");
  const [result, setResult] = useState<RedeemResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const redeem = async () => {
    if (!code.trim() || busy) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const next = await customerRequest<RedeemResult>("/api/v1/promocodes/redeem", {
        method: "POST",
        body: JSON.stringify({ code: code.trim() }),
      });
      setResult(next);
      setCode("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось применить промокод");
    } finally { setBusy(false); }
  };

  return (
    <StandaloneShell kicker="Промокод" title="Получить ROX" copy="Введите код — бонус сразу зачислится на общий баланс ROX.">
      <div className="panel tool-panel">
        <div className="form-stack">
          <label className="field"><span className="label">Промокод</span><input className="control" maxLength={64} value={code} onChange={(event) => setCode(event.target.value)} placeholder="ROXY2026" autoCapitalize="characters" /></label>
          {error ? <div className="action-error" role="alert">{error}</div> : null}
          {result ? <div className="profile-stats"><div><strong>+{compactNumber(result.reward_rox)}</strong><span>ROX начислено</span></div><div><strong>{compactNumber(result.balance_rox)}</strong><span>ROX на балансе</span></div></div> : null}
          <button className="primary wide" type="button" disabled={busy || !code.trim()} onClick={() => void redeem()}>{busy ? "Проверяю…" : "Применить промокод"}</button>
        </div>
      </div>
    </StandaloneShell>
  );
}
