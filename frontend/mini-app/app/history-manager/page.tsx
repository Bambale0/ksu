"use client";

import { useEffect, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { customerRequest, dateTime } from "@/lib/customer-api";
import type { Generation } from "@/lib/types";

function resultUrl(item: Generation): string {
  return item.result_url || item.result_urls?.[0] || item.media?.[0]?.url || "";
}

export default function HistoryManagerPage() {
  const [active, setActive] = useState<Generation[]>([]);
  const [hidden, setHidden] = useState<Generation[]>([]);
  const [tab, setTab] = useState<"active" | "hidden">("active");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = async () => {
    setError("");
    try {
      const [visible, archived] = await Promise.all([
        customerRequest<{ items: Generation[] }>("/api/v1/generations?limit=50"),
        customerRequest<{ items: Generation[] }>("/api/v1/generation-history/hidden?limit=50"),
      ]);
      setActive(visible.items || []);
      setHidden(archived.items || []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить историю");
    }
  };

  useEffect(() => { void load(); }, []);

  const hide = async (id: string) => {
    setBusy(id); setError("");
    try {
      await customerRequest(`/api/v1/generations/${encodeURIComponent(id)}/history`, { method: "DELETE" });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось скрыть работу");
    } finally { setBusy(null); }
  };

  const restore = async (id: string) => {
    setBusy(id); setError("");
    try {
      await customerRequest(`/api/v1/generations/${encodeURIComponent(id)}/history/restore`, { method: "POST" });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось восстановить работу");
    } finally { setBusy(null); }
  };

  const rows = tab === "active" ? active : hidden;

  return (
    <StandaloneShell kicker="История" title="Управление работами" copy="Скрытие убирает работу из обычной истории, но не удаляет генерацию. Её всегда можно восстановить.">
      <div className="segmented scrollable">
        <button type="button" className={tab === "active" ? "active" : ""} onClick={() => setTab("active")}>История · {active.length}</button>
        <button type="button" className={tab === "hidden" ? "active" : ""} onClick={() => setTab("hidden")}>Скрытые · {hidden.length}</button>
      </div>
      {error ? <div className="action-error" role="alert">{error}</div> : null}
      <div className="panel tool-panel">
        <div className="transaction-list">
          {rows.length ? rows.map((item) => {
            const url = resultUrl(item);
            const model = typeof item.model === "object" ? item.model?.title : String(item.model || "ROXY");
            return <div className="transaction" key={item.id}>
              <div><strong>{model || "ROXY"}</strong><small>{dateTime(item.created_at)} · {item.status}</small>{item.prompt && !item.prompt_hidden ? <small>{item.prompt.slice(0, 120)}</small> : null}</div>
              <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {url ? <a href={url} target="_blank" rel="noreferrer">Открыть</a> : null}
                {tab === "active" ? <button type="button" disabled={busy === item.id} onClick={() => void hide(item.id)}>{busy === item.id ? "…" : "Скрыть"}</button> : <button type="button" disabled={busy === item.id} onClick={() => void restore(item.id)}>{busy === item.id ? "…" : "Восстановить"}</button>}
              </span>
            </div>;
          }) : <p className="muted">Здесь пока пусто.</p>}
        </div>
      </div>
    </StandaloneShell>
  );
}
