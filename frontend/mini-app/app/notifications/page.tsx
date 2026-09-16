"use client";

import { useEffect, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { customerRequest, dateTime } from "@/lib/customer-api";

type NotificationItem = {
  id: string;
  kind: string;
  title: string;
  body: string;
  is_read: boolean;
  created_at: string;
};

export default function NotificationsPage() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [markingId, setMarkingId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = async () => {
    if (loading && items.length) return;
    setLoading(true);
    setError("");
    try {
      const payload = await customerRequest<{ items: NotificationItem[]; unread_count: number }>("/api/v1/notifications?limit=100");
      setItems(payload.items || []);
      setUnread(Number(payload.unread_count || 0));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить уведомления");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const markRead = async (item: NotificationItem) => {
    if (item.is_read || markingId === item.id || busy) return;
    setMarkingId(item.id);
    setError("");
    try {
      await customerRequest(`/api/v1/notifications/${encodeURIComponent(item.id)}/read`, { method: "POST" });
      setItems((current) => current.map((row) => row.id === item.id ? { ...row, is_read: true } : row));
      setUnread((current) => Math.max(0, current - 1));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отметить уведомление");
    } finally {
      setMarkingId(null);
    }
  };

  const markAll = async () => {
    if (busy || markingId) return;
    setBusy(true);
    setError("");
    try {
      await customerRequest("/api/v1/notifications/read-all", { method: "POST" });
      setItems((current) => current.map((item) => ({ ...item, is_read: true })));
      setUnread(0);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отметить уведомления");
    } finally {
      setBusy(false);
    }
  };

  return (
    <StandaloneShell kicker="Уведомления" title={unread ? `${unread} непрочитанных` : "Всё просмотрено"} copy="Статусы генераций, промокоды, выплаты и важные сообщения ROXY.">
      <div className="panel tool-panel" aria-busy={loading || busy || Boolean(markingId)}>
        <div className="section-title">
          <div><span className="kicker">Центр событий</span><h2>Все уведомления</h2></div>
          <button type="button" disabled={loading || !unread || busy || Boolean(markingId)} onClick={() => void markAll()}>
            {busy ? "Обновляю…" : "Прочитать все"}
          </button>
        </div>

        {loading ? <p className="muted" role="status">Загружаем уведомления…</p> : null}
        {error ? <div className="action-error" role="alert">{error}</div> : null}
        {!loading && error && !items.length ? <button className="secondary" type="button" onClick={() => void load()}>Повторить загрузку</button> : null}

        {!loading ? <div className="transaction-list">
          {items.length ? items.map((item) => (
            <button
              type="button"
              className="transaction"
              key={item.id}
              disabled={markingId === item.id || busy}
              onClick={() => void markRead(item)}
              style={{ width: "100%", textAlign: "left", opacity: item.is_read ? 0.72 : 1 }}
            >
              <div><strong>{item.title}</strong><small>{dateTime(item.created_at)} · {item.kind}</small><small>{item.body}</small></div>
              <span>{markingId === item.id ? "…" : item.is_read ? "✓" : "Новая"}</span>
            </button>
          )) : !error ? <p className="muted">Уведомлений пока нет.</p> : null}
        </div> : null}
      </div>
    </StandaloneShell>
  );
}
