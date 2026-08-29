"use client";

import { useEffect, useRef, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { compactNumber, customerIdempotencyKey, customerRequest, dateTime } from "@/lib/customer-api";

type PartnerStats = {
  partner_balance_rub: string;
  pending: string;
  total_earned: string;
  transferred_to_rox: string;
  pending_withdrawals: string;
  minimum_withdrawal: string;
  rub_per_rox: string;
};
type Withdrawal = { id: string; amount: string; amount_rox: string; status: string; created_at: string; updated_at: string; can_cancel: boolean };
type Transfer = { id: string; amount_rub: string; rox_amount: string; created_at: string };

export default function PartnerWalletPage() {
  const [stats, setStats] = useState<PartnerStats | null>(null);
  const [withdrawals, setWithdrawals] = useState<Withdrawal[]>([]);
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [transferAmount, setTransferAmount] = useState("");
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [requisites, setRequisites] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const withdrawalKey = useRef<string | null>(null);

  const load = async () => {
    setError("");
    try {
      const [statsResult, withdrawalResult, transferResult] = await Promise.all([
        customerRequest<PartnerStats>("/api/v1/referrals/stats"),
        customerRequest<{ items: Withdrawal[] }>("/api/v1/referrals/withdrawals?limit=50"),
        customerRequest<{ items: Transfer[] }>("/api/v1/referrals/wallet-transfers?limit=50"),
      ]);
      setStats(statsResult);
      setWithdrawals(withdrawalResult.items || []);
      setTransfers(transferResult.items || []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить партнёрский баланс");
    }
  };

  useEffect(() => { void load(); }, []);

  const resetWithdrawalIntent = () => {
    withdrawalKey.current = null;
  };

  const transferToRox = async () => {
    const amount = Number(transferAmount);
    if (!(amount > 0) || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await customerRequest<Transfer>("/api/v1/referrals/wallet-transfers", {
        method: "POST",
        body: JSON.stringify({ amount, idempotency_key: customerIdempotencyKey() }),
      });
      setTransferAmount("");
      setNotice(`${compactNumber(result.amount_rub)} ₽ переведено в ${compactNumber(result.rox_amount)} ROX`);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось перевести баланс в ROX");
    } finally { setBusy(false); }
  };

  const withdraw = async () => {
    const amount = Number(withdrawAmount);
    if (!(amount > 0) || !requisites.trim() || busy) return;
    const requestKey = withdrawalKey.current ?? customerIdempotencyKey();
    withdrawalKey.current = requestKey;
    setBusy(true); setError(""); setNotice("");
    try {
      await customerRequest<Withdrawal>("/api/v1/referrals/withdrawals", {
        method: "POST",
        headers: { "Idempotency-Key": requestKey },
        body: JSON.stringify({ amount, requisites: requisites.trim() }),
      });
      withdrawalKey.current = null;
      setWithdrawAmount(""); setRequisites("");
      setNotice("Заявка на выплату создана");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось создать выплату");
    } finally { setBusy(false); }
  };

  const cancel = async (id: string) => {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await customerRequest(`/api/v1/referrals/withdrawals/${encodeURIComponent(id)}/cancel`, { method: "POST" });
      setNotice("Заявка отменена");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отменить выплату");
    } finally { setBusy(false); }
  };

  return (
    <StandaloneShell kicker="Партнёрам" title="Доход и выплаты" copy="Партнёрский доход хранится отдельно от ROX. Его можно вывести или добровольно перевести в баланс ROX.">
      {stats ? <div className="profile-stats panel"><div><strong>{compactNumber(stats.partner_balance_rub)} ₽</strong><span>доступно</span></div><div><strong>{compactNumber(stats.pending)} ₽</strong><span>ожидается</span></div><div><strong>{compactNumber(stats.total_earned)} ₽</strong><span>заработано</span></div></div> : null}
      {error ? <div className="action-error" role="alert">{error}</div> : null}
      {notice ? <div className="panel"><p className="muted">{notice}</p></div> : null}

      <div className="tool-grid">
        <div className="panel tool-panel">
          <div className="section-title"><div><span className="kicker">ROX</span><h2>Перевести в баланс</h2></div></div>
          <p className="muted">Конвертация списывает указанную сумму из партнёрского RUB-баланса и зачисляет ROX по текущему курсу.</p>
          <div className="form-stack">
            <label className="field"><span className="label">Сумма, ₽</span><input className="control" type="number" min="0.01" step="0.01" value={transferAmount} onChange={(event) => setTransferAmount(event.target.value)} /></label>
            <button className="primary wide" type="button" disabled={busy || !(Number(transferAmount) > 0)} onClick={() => void transferToRox()}>{busy ? "Выполняю…" : "Перевести в ROX"}</button>
          </div>
        </div>

        <div className="panel tool-panel">
          <div className="section-title"><div><span className="kicker">Выплата</span><h2>Вывести деньги</h2></div></div>
          <p className="muted">Минимальная сумма: {compactNumber(stats?.minimum_withdrawal)} ₽. Укажите реквизиты так, как их должна увидеть поддержка выплат.</p>
          <div className="form-stack">
            <label className="field"><span className="label">Сумма, ₽</span><input className="control" type="number" min={stats?.minimum_withdrawal || "0.01"} step="0.01" value={withdrawAmount} onChange={(event) => { resetWithdrawalIntent(); setWithdrawAmount(event.target.value); }} /></label>
            <label className="field"><span className="label">Реквизиты</span><textarea className="control textarea" maxLength={1000} value={requisites} onChange={(event) => { resetWithdrawalIntent(); setRequisites(event.target.value); }} placeholder="Карта / СБП / другие согласованные реквизиты" /></label>
            <button className="primary wide" type="button" disabled={busy || !(Number(withdrawAmount) > 0) || !requisites.trim()} onClick={() => void withdraw()}>{busy ? "Создаю…" : "Создать заявку"}</button>
          </div>
        </div>

        <div className="panel tool-panel">
          <div className="section-title"><div><span className="kicker">Выплаты</span><h2>История заявок</h2></div><button type="button" onClick={() => void load()}>Обновить</button></div>
          <div className="transaction-list">{withdrawals.length ? withdrawals.map((item) => <div className="transaction" key={item.id}><div><strong>{compactNumber(item.amount)} ₽</strong><small>{dateTime(item.created_at)} · {item.status}</small></div><span>{item.can_cancel ? <button type="button" disabled={busy} onClick={() => void cancel(item.id)}>Отменить</button> : item.status}</span></div>) : <p className="muted">Заявок пока нет.</p>}</div>
        </div>

        <div className="panel tool-panel">
          <div className="section-title"><div><span className="kicker">ROX</span><h2>История переводов</h2></div></div>
          <div className="transaction-list">{transfers.length ? transfers.map((item) => <div className="transaction" key={item.id}><div><strong>{compactNumber(item.amount_rub)} ₽ → {compactNumber(item.rox_amount)} ROX</strong><small>{dateTime(item.created_at)}</small></div></div>) : <p className="muted">Переводов пока нет.</p>}</div>
        </div>
      </div>
    </StandaloneShell>
  );
}
