"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "@/lib/api";
import {
  trendAdminApi,
  type TrendAdminItem,
  type TrendAdminPayload,
} from "@/lib/trend-admin-api";

const REFERENCE_FIELDS = new Set([
  "image_input",
  "image_urls",
  "input_urls",
  "reference_image_urls",
  "image_url",
  "first_frame_url",
  "first_frame",
]);
const SINGLE_REFERENCE_FIELDS = new Set(["image_url", "first_frame_url", "first_frame"]);

function previewIsVideo(url: string): boolean {
  return /\.(mp4|webm|mov|m4v)(?:[?#]|$)/i.test(url);
}

function modelAcceptsReferences(model?: TrendAdminModel | null): boolean {
  return Boolean(model?.known_fields?.some((field) => REFERENCE_FIELDS.has(field)));
}

function referenceCapacity(model?: TrendAdminModel | null): number {
  return model?.known_fields?.some((field) => SINGLE_REFERENCE_FIELDS.has(field)) ? 1 : 8;
}

type TrendAdminModel = {
  id: string;
  title?: string;
  family?: string;
  media_type?: string;
  known_fields?: string[];
  required_fields?: string[];
  price_mode?: string;
  min_seconds?: number | null;
  max_seconds?: number | null;
  duration_field?: string | null;
};

type Draft = {
  title: string;
  description: string;
  previewUrl: string;
  modelId: string;
  prompt: string;
  inputMode: "none" | "image";
  minReferences: number;
  maxReferences: number;
  billingSeconds: string;
  sortOrder: number;
  tags: string;
  parameters: string;
  isActive: boolean;
};

function emptyDraft(modelId = ""): Draft {
  return {
    title: "",
    description: "",
    previewUrl: "",
    modelId,
    prompt: "",
    inputMode: "none",
    minReferences: 0,
    maxReferences: 0,
    billingSeconds: "",
    sortOrder: 0,
    tags: "trend",
    parameters: "{}",
    isActive: true,
  };
}

function modelUsesProviderDuration(model?: TrendAdminModel | null): boolean {
  return Boolean(
    model?.media_type === "video"
      && model.known_fields?.includes("duration")
      && model.required_fields?.includes("duration"),
  );
}

function draftFrom(item: TrendAdminItem, duplicate = false): Draft {
  const payload = item.payload || ({} as TrendAdminPayload);
  return {
    title: duplicate ? `${item.title} — копия` : item.title,
    description: String(payload.description || ""),
    previewUrl: String(payload.preview_url || ""),
    modelId: String(payload.model_id || ""),
    prompt: String(payload.prompt || ""),
    inputMode: payload.input_mode === "image" ? "image" : "none",
    minReferences: Number(payload.min_references || 0),
    maxReferences: Number(payload.max_references || 0),
    billingSeconds: payload.billing_seconds ? String(payload.billing_seconds) : "",
    sortOrder: Number(payload.sort_order || 0),
    tags: Array.isArray(payload.tags) ? payload.tags.join(", ") : "trend",
    parameters: JSON.stringify(payload.parameters || {}, null, 2),
    isActive: duplicate ? true : item.is_active !== false,
  };
}

export function InlineTrendAdmin() {
  const [isAdmin, setIsAdmin] = useState(false);
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [open, setOpen] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [items, setItems] = useState<TrendAdminItem[]>([]);
  const [models, setModels] = useState<TrendAdminModel[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    void api.me()
      .then((me) => { if (alive) setIsAdmin(Boolean(me.is_admin)); })
      .catch(() => { if (alive) setIsAdmin(false); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    const sync = () => {
      const title = Array.from(document.querySelectorAll<HTMLElement>(".section-title h2"))
        .find((node) => node.textContent?.trim() === "Готовые сценарии");
      if (!title) {
        setHost(null);
        return;
      }
      const parent = title.closest<HTMLElement>(".section-title");
      if (!parent) return;
      let mount = parent.querySelector<HTMLElement>("[data-inline-trend-admin-host]");
      if (!mount) {
        mount = document.createElement("div");
        mount.dataset.inlineTrendAdminHost = "true";
        parent.appendChild(mount);
      }
      setHost(mount);
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [isAdmin]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await trendAdminApi.list();
      setItems(result.items || []);
      setModels((result.models || []) as TrendAdminModel[]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить тренды");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  const selectedModel = useMemo(
    () => models.find((model) => model.id === draft.modelId) || null,
    [draft.modelId, models],
  );
  const referenceAllowed = modelAcceptsReferences(selectedModel);
  const capacity = referenceCapacity(selectedModel);

  const beginCreate = () => {
    const modelId = models[0]?.id || "";
    setEditingId(null);
    setDraft(emptyDraft(modelId));
    setError("");
    setFormOpen(true);
  };

  const beginEdit = (item: TrendAdminItem, duplicate = false) => {
    setEditingId(duplicate ? null : item.id);
    setDraft(draftFrom(item, duplicate));
    setError("");
    setFormOpen(true);
  };

  const chooseModel = (modelId: string) => {
    const next = models.find((model) => model.id === modelId);
    setDraft((current) => ({
      ...current,
      modelId,
      inputMode: modelAcceptsReferences(next) ? current.inputMode : "none",
      minReferences: modelAcceptsReferences(next) && current.inputMode === "image" ? Math.max(1, current.minReferences || 1) : 0,
      maxReferences: modelAcceptsReferences(next) && current.inputMode === "image" ? Math.min(referenceCapacity(next), Math.max(1, current.maxReferences || 1)) : 0,
    }));
  };

  const chooseInputMode = (inputMode: "none" | "image") => {
    if (inputMode === "image" && !referenceAllowed) return;
    setDraft((current) => ({
      ...current,
      inputMode,
      minReferences: inputMode === "image" ? 1 : 0,
      maxReferences: inputMode === "image" ? Math.min(capacity, Math.max(1, current.maxReferences || capacity)) : 0,
    }));
  };

  const uploadPreview = async (file?: File) => {
    if (!file) return;
    if (!file.type.startsWith("image/") && !file.type.startsWith("video/")) {
      setError("Выберите изображение или видео");
      return;
    }
    setUploading(true);
    setError("");
    try {
      const uploaded = await api.upload(file);
      setDraft((current) => ({ ...current, previewUrl: uploaded.url }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить превью");
    } finally {
      setUploading(false);
    }
  };

  const save = async () => {
    if (saving) return;
    if (!draft.title.trim() || !draft.modelId || !draft.prompt.trim() || !draft.previewUrl.trim()) {
      setError("Добавьте название, превью, модель и скрытый промпт");
      return;
    }
    let parameters: Record<string, unknown>;
    try {
      const parsed = JSON.parse(draft.parameters || "{}");
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error();
      parameters = parsed as Record<string, unknown>;
    } catch {
      setError("Дополнительные параметры должны быть корректным JSON-объектом");
      return;
    }
    const model = selectedModel;
    if (!model?.media_type) {
      setError("Выберите доступную модель");
      return;
    }
    const billingSeconds = draft.billingSeconds.trim() ? Number(draft.billingSeconds) : null;
    if (billingSeconds !== null && (!Number.isFinite(billingSeconds) || billingSeconds <= 0)) {
      setError("Длительность должна быть положительным числом секунд");
      return;
    }
    const payload: TrendAdminPayload = {
      description: draft.description.trim(),
      preview_url: draft.previewUrl.trim(),
      media_type: model.media_type,
      model_id: model.id,
      prompt: draft.prompt.trim(),
      parameters,
      input_mode: draft.inputMode,
      min_references: draft.inputMode === "image" ? Math.max(1, draft.minReferences) : 0,
      max_references: draft.inputMode === "image" ? Math.min(capacity, Math.max(draft.minReferences, draft.maxReferences)) : 0,
      tags: draft.tags.split(",").map((tag) => tag.trim().toLowerCase()).filter(Boolean).slice(0, 20),
      sort_order: Number(draft.sortOrder || 0),
      usage_count: Number(items.find((item) => item.id === editingId)?.payload?.usage_count || 0),
    };
    if (billingSeconds !== null) {
      payload.billing_seconds = billingSeconds;
      if (
        modelUsesProviderDuration(model)
        && (parameters.duration === undefined || parameters.duration === null || parameters.duration === "")
      ) {
        parameters.duration = billingSeconds;
      }
    }

    setSaving(true);
    setError("");
    try {
      const body = { title: draft.title.trim(), payload, is_active: draft.isActive };
      if (editingId) await trendAdminApi.update(editingId, body);
      else await trendAdminApi.create(body);
      setFormOpen(false);
      setEditingId(null);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось сохранить тренд");
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (item: TrendAdminItem) => {
    if (busyId) return;
    setBusyId(item.id);
    setError("");
    try {
      if (item.is_active) await trendAdminApi.hide(item.id);
      else await trendAdminApi.activate(item.id);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось изменить видимость тренда");
    } finally {
      setBusyId(null);
    }
  };

  if (!isAdmin) return null;

  return <>
    {host ? createPortal(
      <button className="inline-trend-add-button" type="button" onClick={() => setOpen(true)} aria-label="Управлять трендами">
        <span>＋</span> Добавить
      </button>,
      host,
    ) : null}

    {open ? <div className="inline-trend-admin-overlay" role="dialog" aria-modal="true" aria-label="Управление трендами">
      <div className="inline-trend-admin-panel">
        <header className="inline-trend-admin-head">
          <div><span className="kicker">Админ</span><h2>Тренды</h2><p>Добавляйте и обновляйте готовые сценарии прямо из ROXY.</p></div>
          <button className="inline-trend-icon-button" type="button" onClick={() => { setOpen(false); setFormOpen(false); }} aria-label="Закрыть">×</button>
        </header>

        <div className="inline-trend-admin-toolbar">
          <button className="inline-trend-primary" type="button" onClick={beginCreate}>＋ Новый тренд</button>
          <button className="inline-trend-secondary" type="button" onClick={() => void refresh()} disabled={loading}>Обновить</button>
        </div>

        {error && !formOpen ? <div className="inline-trend-error" role="alert">{error}</div> : null}
        {loading ? <div className="inline-trend-empty">Загружаю тренды…</div> : null}
        {!loading && !items.length ? <div className="inline-trend-empty">Трендов пока нет. Создайте первый.</div> : null}

        <div className="inline-trend-admin-list">
          {items.map((item) => {
            const payload = item.payload || ({} as TrendAdminPayload);
            const video = previewIsVideo(String(payload.preview_url || ""));
            const model = models.find((entry) => entry.id === payload.model_id);
            return <article className={`inline-trend-admin-card${item.is_active ? "" : " is-hidden"}`} key={item.id}>
              <div className="inline-trend-admin-preview">
                {payload.preview_url ? video
                  ? <video src={payload.preview_url} muted playsInline loop autoPlay preload="metadata" />
                  : <img src={payload.preview_url} alt="" loading="lazy" />
                  : <span>Нет превью</span>}
              </div>
              <div className="inline-trend-admin-card-body">
                <div className="inline-trend-admin-card-title"><strong>{item.title}</strong><span className={item.is_active ? "is-active" : ""}>{item.is_active ? "Активен" : "Скрыт"}</span></div>
                <small>{model?.title || payload.model_id || "Модель"} · {payload.media_type === "video" ? "Видео" : "Фото"}</small>
                {payload.description ? <p>{payload.description}</p> : null}
                <div className="inline-trend-admin-actions">
                  <button type="button" onClick={() => beginEdit(item)}>Редактировать</button>
                  <button type="button" onClick={() => beginEdit(item, true)}>Дублировать</button>
                  <button type="button" className={item.is_active ? "danger" : ""} onClick={() => void toggleActive(item)} disabled={busyId === item.id}>{busyId === item.id ? "…" : item.is_active ? "Скрыть" : "Вернуть"}</button>
                </div>
              </div>
            </article>;
          })}
        </div>
      </div>
    </div> : null}

    {open && formOpen ? <div className="inline-trend-form-overlay" role="dialog" aria-modal="true" aria-label={editingId ? "Редактировать тренд" : "Добавить тренд"}>
      <form className="inline-trend-form" onSubmit={(event) => { event.preventDefault(); void save(); }}>
        <header className="inline-trend-form-head"><div><span className="kicker">{editingId ? "Редактирование" : "Новый тренд"}</span><h2>{editingId ? draft.title || "Тренд" : "Добавить тренд"}</h2></div><button type="button" onClick={() => setFormOpen(false)} aria-label="Закрыть">×</button></header>

        {error ? <div className="inline-trend-error" role="alert">{error}</div> : null}

        <label><span>Название</span><input value={draft.title} maxLength={80} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} placeholder="Например, Киношный портрет" required /></label>
        <label><span>Описание</span><textarea value={draft.description} maxLength={240} rows={2} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} placeholder="Что получит пользователь" /></label>

        <div className="inline-trend-two-cols">
          <label><span>Модель</span><select value={draft.modelId} onChange={(event) => chooseModel(event.target.value)} required><option value="">Выберите модель</option>{["image", "video"].map((kind) => <optgroup label={kind === "image" ? "Фото" : "Видео"} key={kind}>{models.filter((model) => model.media_type === kind).map((model) => <option value={model.id} key={model.id}>{model.title || model.id}</option>)}</optgroup>)}</select></label>
          <label><span>Приоритет</span><input type="number" min={-100000} max={100000} value={draft.sortOrder} onChange={(event) => setDraft((current) => ({ ...current, sortOrder: Number(event.target.value || 0) }))} /></label>
        </div>

        <label><span>Превью</span><input type="file" accept="image/*,video/*" onChange={(event) => void uploadPreview(event.target.files?.[0])} disabled={uploading} /><small>{uploading ? "Сохраняю файл в ROXY…" : "Фото или видео. Файл сохраняется постоянно."}</small></label>
        {draft.previewUrl ? <div className="inline-trend-form-preview">{previewIsVideo(draft.previewUrl) ? <video src={draft.previewUrl} muted playsInline controls /> : <img src={draft.previewUrl} alt="Превью тренда" />}</div> : null}
        <label><span>URL превью</span><input type="url" value={draft.previewUrl} onChange={(event) => setDraft((current) => ({ ...current, previewUrl: event.target.value }))} placeholder="https://…" required /></label>

        <label><span>Скрытый промпт</span><textarea value={draft.prompt} maxLength={8000} rows={5} onChange={(event) => setDraft((current) => ({ ...current, prompt: event.target.value }))} placeholder="Инструкция для модели. Пользователь её не увидит." required /></label>

        <div className="inline-trend-two-cols">
          <label><span>Что загружает пользователь</span><select value={draft.inputMode} onChange={(event) => chooseInputMode(event.target.value as "none" | "image")}><option value="none">Ничего</option><option value="image" disabled={!referenceAllowed}>Фото / референс</option></select><small>{referenceAllowed ? "Модель поддерживает референсы" : "У выбранной модели нет входного изображения"}</small></label>
          <label><span>Длительность, сек</span><input type="number" min={1} value={draft.billingSeconds} onChange={(event) => setDraft((current) => ({ ...current, billingSeconds: event.target.value }))} placeholder="Авто" /></label>
        </div>

        {draft.inputMode === "image" ? <div className="inline-trend-two-cols"><label><span>Минимум фото</span><input type="number" min={1} max={capacity} value={draft.minReferences} onChange={(event) => setDraft((current) => ({ ...current, minReferences: Math.min(capacity, Math.max(1, Number(event.target.value || 1))) }))} /></label><label><span>Максимум фото</span><input type="number" min={draft.minReferences} max={capacity} value={draft.maxReferences} onChange={(event) => setDraft((current) => ({ ...current, maxReferences: Math.min(capacity, Math.max(current.minReferences, Number(event.target.value || current.minReferences))) }))} /></label></div> : null}

        <label><span>Теги</span><input value={draft.tags} onChange={(event) => setDraft((current) => ({ ...current, tags: event.target.value }))} placeholder="trend, portrait" /><small>Через запятую, максимум 20.</small></label>

        <details className="inline-trend-advanced"><summary>Дополнительные параметры модели</summary><label><span>JSON параметров</span><textarea rows={7} spellCheck={false} value={draft.parameters} onChange={(event) => setDraft((current) => ({ ...current, parameters: event.target.value }))} /></label></details>

        {editingId ? <label className="inline-trend-checkbox"><input type="checkbox" checked={draft.isActive} onChange={(event) => setDraft((current) => ({ ...current, isActive: event.target.checked }))} /><span>Показывать пользователям</span></label> : null}

        <div className="inline-trend-form-actions"><button className="inline-trend-secondary" type="button" onClick={() => setFormOpen(false)}>Отмена</button><button className="inline-trend-primary" type="submit" disabled={saving || uploading}>{saving ? "Сохраняю…" : editingId ? "Сохранить" : "Опубликовать тренд"}</button></div>
      </form>
    </div> : null}

    <style jsx global>{`
      [data-inline-trend-admin-host] { display:flex; align-items:center; margin-left:auto; }
      .inline-trend-add-button { border:1px solid rgba(198,120,255,.42); background:rgba(155,74,255,.16); color:#d99aff; border-radius:999px; padding:9px 13px; font:700 13px/1 inherit; box-shadow:0 0 24px rgba(173,83,255,.16); }
      .inline-trend-add-button span { font-size:17px; line-height:0; margin-right:3px; }
      .inline-trend-admin-overlay,.inline-trend-form-overlay { position:fixed; inset:0; z-index:140; background:rgba(2,1,5,.78); backdrop-filter:blur(12px); display:flex; justify-content:center; align-items:flex-end; }
      .inline-trend-form-overlay { z-index:150; }
      .inline-trend-admin-panel,.inline-trend-form { width:min(100%,720px); max-height:94dvh; overflow:auto; background:#0b0910; border:1px solid rgba(255,255,255,.1); border-radius:24px 24px 0 0; padding:18px 16px calc(24px + env(safe-area-inset-bottom)); box-shadow:0 -20px 80px rgba(0,0,0,.5); }
      .inline-trend-admin-head,.inline-trend-form-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
      .inline-trend-admin-head h2,.inline-trend-form-head h2 { margin:2px 0 4px; font-size:26px; }
      .inline-trend-admin-head p { margin:0; color:#aaa2b4; font-size:13px; }
      .inline-trend-icon-button,.inline-trend-form-head>button { width:38px; height:38px; border-radius:50%; border:1px solid rgba(255,255,255,.12); background:#17131d; color:#fff; font-size:24px; }
      .inline-trend-admin-toolbar,.inline-trend-form-actions { display:flex; gap:10px; margin:16px 0; }
      .inline-trend-primary,.inline-trend-secondary { min-height:42px; border-radius:13px; padding:0 15px; font-weight:800; }
      .inline-trend-primary { border:0; background:linear-gradient(135deg,#a84dff,#d66cff); color:#fff; box-shadow:0 10px 30px rgba(172,68,255,.22); }
      .inline-trend-secondary { border:1px solid rgba(255,255,255,.11); background:#17131d; color:#fff; }
      .inline-trend-admin-list { display:grid; gap:12px; }
      .inline-trend-admin-card { display:grid; grid-template-columns:104px minmax(0,1fr); overflow:hidden; border:1px solid rgba(255,255,255,.09); border-radius:18px; background:#110e16; }
      .inline-trend-admin-card.is-hidden { opacity:.62; }
      .inline-trend-admin-preview { min-height:120px; background:#050407; display:grid; place-items:center; color:#766e80; }
      .inline-trend-admin-preview img,.inline-trend-admin-preview video { width:100%; height:100%; min-height:120px; object-fit:cover; }
      .inline-trend-admin-card-body { min-width:0; padding:12px; }
      .inline-trend-admin-card-title { display:flex; gap:8px; justify-content:space-between; align-items:flex-start; }
      .inline-trend-admin-card-title strong { font-size:14px; }
      .inline-trend-admin-card-title span { flex:0 0 auto; border-radius:999px; padding:4px 7px; background:#28212f; color:#aaa2b4; font-size:10px; font-weight:800; }
      .inline-trend-admin-card-title span.is-active { background:rgba(75,214,132,.13); color:#79e6a7; }
      .inline-trend-admin-card-body>small { display:block; margin-top:4px; color:#8f8798; }
      .inline-trend-admin-card-body>p { margin:8px 0; color:#bdb6c6; font-size:12px; }
      .inline-trend-admin-actions { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }
      .inline-trend-admin-actions button { border:1px solid rgba(255,255,255,.1); background:#1b1721; color:#eee9f4; border-radius:9px; padding:7px 9px; font-size:11px; font-weight:700; }
      .inline-trend-admin-actions button.danger { color:#ff9aa9; }
      .inline-trend-empty { padding:26px; text-align:center; color:#91899a; }
      .inline-trend-error { margin:12px 0; border:1px solid rgba(255,95,116,.28); background:rgba(255,78,103,.09); color:#ffb0bc; border-radius:12px; padding:10px 12px; font-size:12px; }
      .inline-trend-form { display:grid; gap:13px; }
      .inline-trend-form label { display:grid; gap:7px; color:#dcd6e3; font-size:12px; font-weight:700; }
      .inline-trend-form label>small { color:#81798b; font-weight:500; }
      .inline-trend-form input:not([type=checkbox]),.inline-trend-form textarea,.inline-trend-form select { width:100%; border:1px solid rgba(255,255,255,.1); background:#15111b; color:#fff; border-radius:12px; padding:11px 12px; outline:none; font:inherit; }
      .inline-trend-form input:focus,.inline-trend-form textarea:focus,.inline-trend-form select:focus { border-color:rgba(203,105,255,.65); box-shadow:0 0 0 3px rgba(174,72,255,.09); }
      .inline-trend-two-cols { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
      .inline-trend-form-preview { max-height:260px; overflow:hidden; border-radius:16px; background:#050407; }
      .inline-trend-form-preview img,.inline-trend-form-preview video { width:100%; max-height:260px; object-fit:contain; display:block; }
      .inline-trend-advanced { border:1px solid rgba(255,255,255,.08); border-radius:14px; padding:11px 12px; }
      .inline-trend-advanced summary { cursor:pointer; color:#bcb4c6; font-size:12px; font-weight:800; }
      .inline-trend-advanced label { margin-top:12px; }
      .inline-trend-checkbox { display:flex!important; grid-template-columns:none!important; align-items:center; gap:9px!important; }
      .inline-trend-checkbox input { width:18px; height:18px; accent-color:#b455ff; }
      .inline-trend-form-actions { justify-content:flex-end; margin-bottom:0; }
      @media (max-width:520px) { .inline-trend-two-cols { grid-template-columns:1fr; } .inline-trend-admin-card { grid-template-columns:88px minmax(0,1fr); } }
    `}</style>
  </>;
}
