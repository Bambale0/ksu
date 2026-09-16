"use client";

import { useEffect, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { customerRequest } from "@/lib/customer-api";

type Preferences = {
  ui_language: string;
  notifications_enabled: boolean;
  marketing_notifications: boolean;
  profile_discoverable: boolean;
};

const defaults: Preferences = {
  ui_language: "auto",
  notifications_enabled: true,
  marketing_notifications: false,
  profile_discoverable: false,
};

export default function SettingsPage() {
  const [value, setValue] = useState<Preferences>(defaults);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setLoaded(false);
    setSaved(false);
    setError("");
    try {
      setValue(await customerRequest<Preferences>("/api/v1/me/preferences"));
      setLoaded(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить настройки");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const save = async () => {
    if (!loaded || loading || busy) return;
    setBusy(true);
    setSaved(false);
    setError("");
    try {
      const next = await customerRequest<Preferences>("/api/v1/me/preferences", {
        method: "PUT",
        body: JSON.stringify(value),
      });
      setValue(next);
      setSaved(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить настройки");
    } finally {
      setBusy(false);
    }
  };

  const toggle = (key: keyof Pick<Preferences, "notifications_enabled" | "marketing_notifications" | "profile_discoverable">) => (
    <label className="toggle-row">
      <span>
        <strong>{key === "notifications_enabled" ? "Системные уведомления" : key === "marketing_notifications" ? "Новости и предложения" : "Показывать профиль в рекомендациях"}</strong>
        <small>{key === "notifications_enabled" ? "Результаты, платежи и важные события" : key === "marketing_notifications" ? "Новые возможности ROXY и промо" : "Разрешить другим пользователям находить ваш профиль"}</small>
      </span>
      <input type="checkbox" checked={value[key]} onChange={(event) => { setSaved(false); setValue((current) => ({ ...current, [key]: event.target.checked })); }} />
      <i />
    </label>
  );

  return (
    <StandaloneShell kicker="Настройки" title="Аккаунт ROXY" copy="Управляйте уведомлениями, языком и видимостью профиля. Telegram-имя и username остаются синхронизированы с Telegram.">
      <div className="panel tool-panel">
        <div className="form-stack">
          {loading ? <p className="muted" role="status">Загружаем настройки…</p> : null}

          {!loading && loaded ? <>
            <label className="field">
              <span className="label">Язык интерфейса</span>
              <select className="control" value={value.ui_language} onChange={(event) => { setSaved(false); setValue((current) => ({ ...current, ui_language: event.target.value })); }}>
                <option value="auto">Как в Telegram</option>
                <option value="ru">Русский</option>
                <option value="en">English</option>
              </select>
            </label>
            {toggle("notifications_enabled")}
            {toggle("marketing_notifications")}
            {toggle("profile_discoverable")}
          </> : null}

          {error ? <div className="action-error" role="alert">{error}</div> : null}
          {!loading && !loaded && error ? <button className="secondary" type="button" onClick={() => void load()}>Повторить загрузку</button> : null}
          {saved ? <p className="muted" role="status">Настройки сохранены.</p> : null}
          <button className="primary wide" type="button" disabled={busy || loading || !loaded} onClick={() => void save()}>
            {busy ? "Сохраняю…" : "Сохранить"}
          </button>
        </div>
      </div>
    </StandaloneShell>
  );
}
