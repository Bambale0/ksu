"use client";

import { useEffect, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { customerRequest, dateTime } from "@/lib/customer-api";
import type { Generation } from "@/lib/types";

type ActionItem = { id: string; label: string; derivative?: boolean; description?: string };

export default function GenerationActionsPage() {
  const [items, setItems] = useState<Generation[]>([]);
  const [actions, setActions] = useState<Record<string, ActionItem[]>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void customerRequest<{ items: Generation[] }>("/api/v1/generations?limit=36&status=succeeded")
      .then((payload) => setItems(payload.items || []))
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Не удалось загрузить готовые работы"));
  }, []);

  const loadActions = async (id: string) => {
    if (actions[id]) { setActions((current) => ({ ...current, [id]: [] })); return; }
    setBusy(id); setError("");
    try {
      const payload = await customerRequest<{ actions: ActionItem[] }>(`/api/v1/generations/${encodeURIComponent(id)}/actions`);
      setActions((current) => ({ ...current, [id]: payload.actions || [] }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить действия");
    } finally { setBusy(null); }
  };

  const openAction = (generationId: string, action: string) => {
    const url = new URL("/mini-app/", window.location.origin);
    url.searchParams.set("route", "generation-action");
    url.searchParams.set("generation", generationId);
    url.searchParams.set("action", action);
    window.location.assign(`${url.pathname}${url.search}`);
  };

  return (
    <StandaloneShell kicker="Работы" title="Действия с результатами" copy="Повторить, изменить, оживить, сменить промпт или параметры — ROXY показывает только совместимые действия и модели.">
      {error ? <div className="action-error" role="alert">{error}</div> : null}
      <div className="panel tool-panel">
        <div className="transaction-list">
          {items.length ? items.map((item) => {
            const model = typeof item.model === "object" ? item.model?.title : String(item.model || "ROXY");
            const available = actions[item.id];
            return <div className="transaction" key={item.id} style={{ alignItems: "flex-start" }}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <strong>{model || "ROXY"}</strong>
                <small>{dateTime(item.created_at)} · {item.status}</small>
                {item.prompt && !item.prompt_hidden ? <small>{item.prompt.slice(0, 140)}</small> : null}
                {available?.length ? <div className="tool-actions" style={{ marginTop: 10, flexWrap: "wrap" }}>{available.map((action) => <button className={action.id === "publish" ? "secondary" : "primary"} type="button" key={action.id} onClick={() => openAction(item.id, action.id)}>{action.label || action.id}</button>)}</div> : null}
                {available && !available.length ? <small>Для этой работы дополнительных действий нет.</small> : null}
              </div>
              <button type="button" disabled={busy === item.id} onClick={() => void loadActions(item.id)}>{busy === item.id ? "…" : available ? "Свернуть" : "Действия"}</button>
            </div>;
          }) : <p className="muted">Готовых работ пока нет.</p>}
        </div>
      </div>
    </StandaloneShell>
  );
}
