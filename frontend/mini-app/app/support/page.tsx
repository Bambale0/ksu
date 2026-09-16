"use client";

import { useEffect, useRef, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { customerRequest, dateTime } from "@/lib/customer-api";
import { telegram } from "@/lib/telegram";

type SupportContact = { configured: boolean; url?: string | null; handle?: string | null };

type Ticket = {
  id: string;
  topic: string;
  status: string;
  created_at: string;
  updated_at: string;
  can_reply: boolean;
  can_close: boolean;
  can_reopen: boolean;
};
type Message = { id: string; body: string; author: "support" | "user"; created_at: string };
type TicketDetail = Ticket & { messages: Message[] };

function openTelegramSupport(url: string) {
  const tg = telegram();
  if (tg?.openTelegramLink) {
    tg.openTelegramLink(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

export default function SupportPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [ticketsLoading, setTicketsLoading] = useState(true);
  const ticketsLoadInFlight = useRef(false);
  const [selected, setSelected] = useState<TicketDetail | null>(null);
  const [topic, setTopic] = useState("");
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [contact, setContact] = useState<SupportContact | null>(null);
  const [contactLoading, setContactLoading] = useState(true);
  const [contactError, setContactError] = useState("");

  const loadTickets = async () => {
    if (ticketsLoadInFlight.current) return;
    ticketsLoadInFlight.current = true;
    setTicketsLoading(true);
    try {
      const payload = await customerRequest<{ items: Ticket[] }>("/api/v1/support/tickets?limit=100");
      setTickets(payload.items || []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить обращения");
    } finally {
      ticketsLoadInFlight.current = false;
      setTicketsLoading(false);
    }
  };

  const openTicket = async (id: string) => {
    setError("");
    try {
      setSelected(await customerRequest<TicketDetail>(`/api/v1/support/tickets/${encodeURIComponent(id)}`));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось открыть обращение");
    }
  };

  const loadContact = async () => {
    setContactLoading(true);
    setContactError("");
    try {
      setContact(await customerRequest<SupportContact>("/api/v1/support/contact"));
    } catch (reason) {
      setContact(null);
      setContactError(reason instanceof Error ? reason.message : "Прямая связь временно недоступна");
    } finally {
      setContactLoading(false);
    }
  };

  useEffect(() => {
    void loadTickets();
    void loadContact();
  }, []);

  const create = async () => {
    if (!topic.trim() || !message.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const ticket = await customerRequest<Ticket>("/api/v1/support/tickets", {
        method: "POST",
        body: JSON.stringify({ topic: topic.trim(), message: message.trim() }),
      });
      setTopic("");
      setMessage("");
      await loadTickets();
      await openTicket(ticket.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось создать обращение");
    } finally { setBusy(false); }
  };

  const sendReply = async () => {
    if (!selected || !reply.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      await customerRequest(`/api/v1/support/tickets/${encodeURIComponent(selected.id)}/messages`, {
        method: "POST",
        body: JSON.stringify({ message: reply.trim() }),
      });
      setReply("");
      await openTicket(selected.id);
      await loadTickets();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отправить сообщение");
    } finally { setBusy(false); }
  };

  const changeState = async (action: "close" | "reopen") => {
    if (!selected || busy) return;
    setBusy(true);
    setError("");
    try {
      await customerRequest(`/api/v1/support/tickets/${encodeURIComponent(selected.id)}/${action}`, { method: "POST" });
      await openTicket(selected.id);
      await loadTickets();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось обновить обращение");
    } finally { setBusy(false); }
  };

  return (
    <StandaloneShell kicker="Поддержка" title="Помощь ROXY" copy="Все обращения сохраняются в одном месте. Можно продолжить диалог, закрыть вопрос или переоткрыть его позже.">
      {error ? <div className="action-error" role="alert">{error}</div> : null}

      {contactLoading ? <div className="panel tool-panel" data-support-contact style={{ marginBottom: 18 }}>
        <p className="muted">Проверяем доступные способы связи…</p>
      </div> : null}

      {!contactLoading && contact?.configured && contact.url ? <div className="panel tool-panel" data-support-contact style={{ marginBottom: 18 }}>
        <div className="section-title"><div><span className="kicker">Быстрая связь</span><h2>Поддержка в Telegram</h2></div></div>
        <p className="muted">Если нужен быстрый ответ, откройте прямой контакт{contact.handle ? <>: <strong>{contact.handle}</strong></> : "."}</p>
        <button className="primary wide" type="button" onClick={() => openTelegramSupport(contact.url!)}>
          {contact.handle ? `Написать ${contact.handle}` : "Открыть Telegram"}
        </button>
      </div> : null}

      {!contactLoading && contactError ? <div className="panel tool-panel" data-support-contact style={{ marginBottom: 18 }}>
        <div className="action-error" role="status">{contactError}</div>
        <p className="muted">Внутренние обращения ROXY ниже продолжают работать.</p>
        <button className="secondary" type="button" onClick={() => void loadContact()}>Повторить</button>
      </div> : null}

      <div className="tool-grid">
        <div className="panel tool-panel">
          <div className="section-title"><div><span className="kicker">Новое обращение</span><h2>Написать в поддержку</h2></div></div>
          <div className="form-stack">
            <label className="field"><span className="label">Тема</span><input className="control" maxLength={64} value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Например: оплата или генерация" /></label>
            <label className="field"><span className="label">Сообщение</span><textarea className="control textarea" maxLength={8000} value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Опишите, что произошло" /></label>
            <button className="primary wide" type="button" disabled={busy || !topic.trim() || !message.trim()} onClick={() => void create()}>{busy ? "Отправляю…" : "Создать обращение"}</button>
          </div>
        </div>

        <div className="panel tool-panel">
          <div className="section-title"><div><span className="kicker">История</span><h2>Мои обращения</h2></div><button type="button" disabled={ticketsLoading} onClick={() => void loadTickets()}>{ticketsLoading ? "Обновляю…" : "Обновить"}</button></div>
          {ticketsLoading ? <p className="muted" role="status">Загружаем обращения…</p> : <div className="transaction-list">
            {tickets.length ? tickets.map((ticket) => (
              <button className="transaction" type="button" key={ticket.id} onClick={() => void openTicket(ticket.id)} style={{ width: "100%", textAlign: "left" }}>
                <div><strong>{ticket.topic}</strong><small>{dateTime(ticket.updated_at)}</small></div><span>{ticket.status}</span>
              </button>
            )) : <p className="muted">Обращений пока нет.</p>}
          </div>}
        </div>

        {selected ? <div className="panel tool-panel">
          <div className="section-title"><div><span className="kicker">Диалог · {selected.status}</span><h2>{selected.topic}</h2></div><button type="button" onClick={() => setSelected(null)}>Закрыть окно</button></div>
          <div className="transaction-list">
            {(selected.messages || []).map((item) => (
              <div className="transaction" key={item.id}>
                <div><strong>{item.author === "support" ? "Поддержка ROXY" : "Вы"}</strong><small>{dateTime(item.created_at)}</small><small>{item.body}</small></div>
              </div>
            ))}
          </div>
          {selected.can_reply ? <div className="form-stack">
            <label className="field"><span className="label">Ответ</span><textarea className="control textarea" maxLength={8000} value={reply} onChange={(event) => setReply(event.target.value)} placeholder="Написать ответ" /></label>
            <button className="primary wide" type="button" disabled={busy || !reply.trim()} onClick={() => void sendReply()}>{busy ? "Отправляю…" : "Отправить"}</button>
          </div> : null}
          <div className="tool-actions">
            {selected.can_close ? <button className="secondary" type="button" disabled={busy} onClick={() => void changeState("close")}>Закрыть обращение</button> : null}
            {selected.can_reopen ? <button className="secondary" type="button" disabled={busy} onClick={() => void changeState("reopen")}>Переоткрыть</button> : null}
          </div>
        </div> : null}
      </div>
    </StandaloneShell>
  );
}
