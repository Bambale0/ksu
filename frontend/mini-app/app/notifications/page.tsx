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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setError("");
    try {
      const payload = await customerRequest<{ items: NotificationItem[]; unread_count: number }>("/api/v1/notifications?limit=100");
      setItems(payload.items || []);
      setUnread(Number(payload.unread_count || 0));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить уведомления");
    }
  };

  useEffect(() => { void load(); }, []);

  const markRead = async (item: NotificationItem) => {
    if (item.is_read) return;
    try {
      await customerRequest(`/api/v1/notifications/${encodeURIComponent(item.id)}/read`, { method: "POST" });
      setItems((current) => current.map((row) => row.id === item.id ? { ...row, is_read: true } : row));
      setUnread((current) => Math.max(0, current - 1));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отметить уведомление");
    }
  };

  const markAll = async () => {
    setBusy(true);
    setError("");
    try {
      await customerRequest("/api/v1/notifications/read-all", { method: "POST" });
      setItems((current) => current.map((item) => ({ ...item, is_read: true })));
      setUnread(0);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отметить уведомления");
    } finally { setBusy(false); }
  };

  return (
    <StandaloneShell kicker="Уведомления" title={unread ? `${unread} непрочитанных` : "Всё просмотрено"} copy="Статусы генераций, промокоды, выплаты и важные сообщения ROXY.">
      <div className="panel tool-panel">
        <div className="section-title">
          <div><span className="kicker">Центр событий</span><h2>Все уведомления</h2></div>
          <button type="button" disabled={!unread || busy} onClick={() => void markAll()}>{busy ? "Обновляю…" : "Прочитать все"}</button>
        </div>
        {error ? <div className="action-error" role="alert">{error}</div> : null}
        <div className="transaction-list">
          {items.length ? items.map((item) => (
            <button
              type="button"
              className="transaction"
              key={item.id}
              onClick={() => void markRead(item)}
              style={{ width: "100%", textAlign: "left", opacity: item.is_read ? 0.72 : 1 }}
            >
              <div><strong>{item.title}</strong><small>{dateTime(item.created_at)} · {item.kind}</small><small>{item.body}</small></div>
              <span>{item.is_read ? "✓" : "Новая"}</span>
            </button>
          )) : <p className="muted">Уведомлений пока нет.</p>}
        </div>
      </div>
    </StandaloneShell>
  );
}
