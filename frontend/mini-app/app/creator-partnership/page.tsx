"use client";

import { useEffect, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { compactNumber, customerIdempotencyKey, customerRequest, dateTime } from "@/lib/customer-api";

type Application = { id: string; channel_name: string; channel_url: string; audience_size: number; average_views?: number | null; cooperation_format: string; message: string; status: string; decision_note?: string | null; created_at: string };
type Agreement = { id: string; status: string; terms_summary: string; monthly_rox: string; starts_on: string; ends_on?: string | null };
type Grant = { id: string; period: string; amount_rox: string; source: string; note?: string | null; created_at: string };
type Status = { application?: Application | null; agreement?: Agreement | null; grants: Grant[]; total_granted_rox: string };

export default function CreatorPartnershipPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [channelName, setChannelName] = useState("");
  const [channelUrl, setChannelUrl] = useState("");
  const [audienceSize, setAudienceSize] = useState("");
  const [averageViews, setAverageViews] = useState("");
  const [format, setFormat] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setError("");
    try { setStatus(await customerRequest<Status>("/api/v1/creator-partnership")); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось загрузить статус партнёрства"); }
  };

  useEffect(() => { void load(); }, []);

  const submit = async () => {
    if (!channelName.trim() || !channelUrl.trim() || !(Number(audienceSize) > 0) || !format.trim() || busy) return;
    setBusy(true); setError("");
    try {
      await customerRequest("/api/v1/creator-partnership/applications", {
        method: "POST",
        headers: { "Idempotency-Key": customerIdempotencyKey() },
        body: JSON.stringify({
          channel_name: channelName.trim(),
          channel_url: channelUrl.trim(),
          audience_size: Number(audienceSize),
          average_views: averageViews ? Number(averageViews) : null,
          cooperation_format: format.trim(),
          message: message.trim(),
        }),
      });
      setChannelName(""); setChannelUrl(""); setAudienceSize(""); setAverageViews(""); setFormat(""); setMessage("");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отправить заявку");
    } finally { setBusy(false); }
  };

  const application = status?.application || null;
  const agreement = status?.agreement || null;
  const canApply = !agreement && (!application || application.status !== "pending");

  return (
    <StandaloneShell kicker="Для авторов" title="Creator-партнёрство" copy="Индивидуальные условия для каналов и авторов. Заявка проверяется вручную, а согласованные ROX начисляются через официальный партнёрский контур.">
      {error ? <div className="action-error" role="alert">{error}</div> : null}
      {agreement ? <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">Договор · {agreement.status}</span><h2>{compactNumber(agreement.monthly_rox)} ROX / месяц</h2></div></div>
        <p>{agreement.terms_summary}</p><p className="muted">Действует с {agreement.starts_on}{agreement.ends_on ? ` до ${agreement.ends_on}` : ""}.</p>
      </div> : null}
      {application ? <div className="panel tool-panel"><span className="kicker">Последняя заявка</span><h2>{application.channel_name}</h2><p className="muted">{application.status} · {dateTime(application.created_at)}</p>{application.decision_note ? <p>{application.decision_note}</p> : null}</div> : null}

      {canApply ? <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">Заявка</span><h2>Предложить сотрудничество</h2></div></div>
        <div className="form-stack">
          <label className="field"><span className="label">Канал / площадка</span><input className="control" maxLength={160} value={channelName} onChange={(event) => setChannelName(event.target.value)} placeholder="Название канала" /></label>
          <label className="field"><span className="label">Ссылка</span><input className="control" type="url" value={channelUrl} onChange={(event) => setChannelUrl(event.target.value)} placeholder="https://..." /></label>
          <div className="structured-row-grid"><label className="field"><span className="label">Аудитория</span><input className="control" type="number" min="1" value={audienceSize} onChange={(event) => setAudienceSize(event.target.value)} /></label><label className="field"><span className="label">Средние просмотры</span><input className="control" type="number" min="0" value={averageViews} onChange={(event) => setAverageViews(event.target.value)} /></label></div>
          <label className="field"><span className="label">Формат сотрудничества</span><input className="control" maxLength={160} value={format} onChange={(event) => setFormat(event.target.value)} placeholder="Обзоры, интеграции, контент для ROXY…" /></label>
          <label className="field"><span className="label">Комментарий</span><textarea className="control textarea" maxLength={4000} value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Расскажите о канале и идее сотрудничества" /></label>
          <button className="primary wide" type="button" disabled={busy || !channelName.trim() || !channelUrl.trim() || !(Number(audienceSize) > 0) || !format.trim()} onClick={() => void submit()}>{busy ? "Отправляю…" : "Отправить заявку"}</button>
        </div>
      </div> : null}

      <div className="panel tool-panel">
        <div className="section-title"><div><span className="kicker">Начисления</span><h2>{compactNumber(status?.total_granted_rox)} ROX всего</h2></div></div>
        <div className="transaction-list">{status?.grants?.length ? status.grants.map((grant) => <div className="transaction" key={grant.id}><div><strong>{grant.period}</strong><small>{grant.source}{grant.note ? ` · ${grant.note}` : ""}</small></div><span>+{compactNumber(grant.amount_rox)} ROX</span></div>) : <p className="muted">Начислений пока нет.</p>}</div>
      </div>
    </StandaloneShell>
  );
}
