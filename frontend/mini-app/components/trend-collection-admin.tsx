"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import {
  clearTrendCollectionTarget,
  setTrendCollectionTarget,
  trendAdminApi,
  type TrendAdminItem,
} from "@/lib/trend-admin-api";
import {
  trendCollectionsApi,
  type TrendCollection,
  type TrendCollectionWrite,
} from "@/lib/trend-collections-api";

type Props = { onChanged?: () => void };

type FolderDraft = {
  id?: string;
  title: string;
  description: string;
  sortOrder: number;
  isActive: boolean;
};

type TrendDraft = {
  id: string;
  title: string;
  description: string;
  tags: string;
};

const emptyDraft = (): FolderDraft => ({
  title: "",
  description: "",
  sortOrder: 100,
  isActive: true,
});

function tagsInput(tags: string[] | undefined): string {
  return (tags || []).map((tag) => `#${String(tag).replace(/^#/, "")}`).join(" ");
}

function parseTags(value: string): string[] {
  return Array.from(new Set(
    value
      .split(/[,\s]+/)
      .map((item) => item.trim().replace(/^#/, "").toLocaleLowerCase())
      .filter(Boolean),
  ));
}

function trendDraft(trend: TrendAdminItem): TrendDraft {
  return {
    id: trend.id,
    title: trend.title,
    description: trend.payload?.description || "",
    tags: tagsInput(trend.payload?.tags),
  };
}

function watchTrendEditorLifecycle(): void {
  let sawAdmin = false;
  let sawForm = false;
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    clearTrendCollectionTarget();
    observer.disconnect();
  };
  const sync = () => {
    const admin = document.querySelector(".inline-trend-admin-overlay");
    const form = document.querySelector(".inline-trend-form-overlay");
    if (admin) sawAdmin = true;
    if (form) sawForm = true;
    if ((sawForm && !form) || (sawAdmin && !admin && !form)) finish();
  };
  const observer = new MutationObserver(sync);
  observer.observe(document.body, { childList: true, subtree: true });
  sync();
  window.setTimeout(() => {
    if (!sawAdmin && !sawForm) finish();
  }, 3000);
}

export function TrendCollectionAdmin({ onChanged }: Props) {
  const [isAdmin, setIsAdmin] = useState(false);
  const [open, setOpen] = useState(false);
  const [collections, setCollections] = useState<TrendCollection[]>([]);
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [trends, setTrends] = useState<TrendAdminItem[]>([]);
  const [draft, setDraft] = useState<FolderDraft | null>(null);
  const [editingTrend, setEditingTrend] = useState<TrendDraft | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    void api.me()
      .then((me) => { if (alive) setIsAdmin(Boolean(me.is_admin)); })
      .catch(() => { if (alive) setIsAdmin(false); });
    return () => { alive = false; };
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [state, trendState] = await Promise.all([
        trendCollectionsApi.manage(),
        trendAdminApi.list(),
      ]);
      setCollections(state.collections || []);
      setAssignments(state.assignments || {});
      setTrends(trendState.items || []);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить категории");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  const collectionById = useMemo(
    () => new Map(collections.map((item) => [item.id, item])),
    [collections],
  );

  const saveFolder = async () => {
    if (!draft || saving) return;
    if (!draft.title.trim()) {
      setError("Введите название категории");
      return;
    }
    setSaving(true);
    setError("");
    const body: TrendCollectionWrite = {
      title: draft.title.trim(),
      description: draft.description.trim(),
      sort_order: draft.sortOrder,
      is_active: draft.isActive,
    };
    try {
      if (draft.id) await trendCollectionsApi.update(draft.id, body);
      else await trendCollectionsApi.create(body);
      setDraft(null);
      await refresh();
      onChanged?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось сохранить категорию");
    } finally {
      setSaving(false);
    }
  };

  const toggleFolder = async (folder: TrendCollection) => {
    if (busy) return;
    setBusy(folder.id);
    setError("");
    try {
      if (folder.is_active) await trendCollectionsApi.hide(folder.id);
      else await trendCollectionsApi.activate(folder.id);
      await refresh();
      onChanged?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось изменить категорию");
    } finally {
      setBusy("");
    }
  };

  const assign = async (trendId: string, collectionId: string) => {
    if (!collectionId || busy) return;
    setBusy(`trend:${trendId}`);
    setError("");
    try {
      await trendCollectionsApi.assign(trendId, collectionId);
      setAssignments((current) => ({ ...current, [trendId]: collectionId }));
      onChanged?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось переместить шаблон");
    } finally {
      setBusy("");
    }
  };

  const saveTrend = async () => {
    if (!editingTrend || busy) return;
    const original = trends.find((item) => item.id === editingTrend.id);
    if (!original) return;
    if (!editingTrend.title.trim()) {
      setError("Введите название шаблона");
      return;
    }
    const busyKey = `trend-save:${original.id}`;
    setBusy(busyKey);
    setError("");
    try {
      await trendAdminApi.update(original.id, {
        title: editingTrend.title.trim(),
        payload: {
          ...original.payload,
          description: editingTrend.description.trim(),
          tags: parseTags(editingTrend.tags),
        },
        is_active: original.is_active,
      });
      setEditingTrend(null);
      await refresh();
      onChanged?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось сохранить шаблон");
    } finally {
      setBusy("");
    }
  };

  const toggleTrend = async (trend: TrendAdminItem) => {
    if (busy) return;
    const busyKey = `trend-status:${trend.id}`;
    setBusy(busyKey);
    setError("");
    try {
      if (trend.is_active) await trendAdminApi.hide(trend.id);
      else await trendAdminApi.activate(trend.id);
      if (editingTrend?.id === trend.id) setEditingTrend(null);
      await refresh();
      onChanged?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось изменить публикацию шаблона");
    } finally {
      setBusy("");
    }
  };

  const openTrendEditor = (collectionId = "trends") => {
    setTrendCollectionTarget(collectionId);
    watchTrendEditorLifecycle();
    setOpen(false);
    window.setTimeout(() => {
      const button = document.querySelector<HTMLButtonElement>(".inline-trend-add-button");
      if (button) button.click();
      else clearTrendCollectionTarget();
    }, 80);
  };

  if (!isAdmin) return null;

  return <>
    <button className="trend-folder-admin-open" type="button" onClick={() => setOpen(true)}>Шаблоны</button>
    {open ? <div className="trend-folder-admin-overlay" role="dialog" aria-modal="true" aria-label="Управление готовыми шаблонами">
      <section className="trend-folder-admin-panel">
        <header className="trend-folder-admin-head">
          <div><span className="kicker">Админ</span><h2>Готовые шаблоны</h2><p>Управляйте трендами прямо здесь: редактируйте подписи и хэштеги, раскладывайте по категориям и временно скрывайте публикации.</p></div>
          <button type="button" onClick={() => { setOpen(false); setDraft(null); setEditingTrend(null); }} aria-label="Закрыть">×</button>
        </header>

        <div className="trend-folder-admin-toolbar">
          <button className="primary" type="button" onClick={() => setDraft(emptyDraft())}>＋ Новая категория</button>
          <button type="button" onClick={() => openTrendEditor("trends")}>＋ Новый тренд</button>
          <button type="button" onClick={() => void refresh()} disabled={loading}>Обновить</button>
        </div>

        {error ? <div className="trend-folder-admin-error" role="alert">{error}</div> : null}
        {loading ? <div className="trend-folder-admin-empty">Загружаю…</div> : null}

        {draft ? <form className="trend-folder-admin-form" onSubmit={(event) => { event.preventDefault(); void saveFolder(); }}>
          <strong>{draft.id ? "Редактировать категорию" : "Новая категория"}</strong>
          <label><span>Название</span><input value={draft.title} maxLength={80} onChange={(event) => setDraft((current) => current ? { ...current, title: event.target.value } : current)} placeholder="Например, День рождения" autoFocus /></label>
          <label><span>Описание и хэштеги</span><textarea value={draft.description} maxLength={240} rows={2} onChange={(event) => setDraft((current) => current ? { ...current, description: event.target.value } : current)} placeholder="Например: Поздравления #др #birthday" /></label>
          <label><span>Порядок</span><input type="number" min={-100000} max={100000} value={draft.sortOrder} onChange={(event) => setDraft((current) => current ? { ...current, sortOrder: Number(event.target.value || 0) } : current)} /></label>
          <div className="actions"><button type="button" onClick={() => setDraft(null)}>Отмена</button><button className="primary" type="submit" disabled={saving}>{saving ? "Сохраняю…" : "Сохранить"}</button></div>
        </form> : null}

        <div className="trend-folder-admin-list">
          {collections.map((folder) => <article className={`trend-folder-admin-card${folder.is_active ? "" : " is-hidden"}`} key={folder.id}>
            <div><strong>{folder.title}</strong>{folder.system_key ? <small>Системная категория</small> : <small>Ваша категория</small>}</div>
            {folder.description ? <p>{folder.description}</p> : null}
            <div className="actions">
              <button type="button" onClick={() => openTrendEditor(folder.id)}>＋ Шаблон</button>
              <button type="button" onClick={() => setDraft({ id: folder.id, title: folder.title, description: folder.description || "", sortOrder: folder.sort_order, isActive: folder.is_active })}>Редактировать</button>
              <button type="button" className={folder.is_active ? "danger" : ""} disabled={busy === folder.id} onClick={() => void toggleFolder(folder)}>{busy === folder.id ? "…" : folder.is_active ? "Скрыть" : "Показать"}</button>
            </div>
          </article>)}
        </div>

        <div className="trend-folder-admin-assign">
          <div><span className="kicker">Содержимое</span><h3>Управление трендами</h3><p>Старые фото и видео не нужно загружать заново. Выберите категорию, поправьте название или хэштеги и при необходимости скройте шаблон. Совпавший #хэштег автоматически переместит сохранённый тренд в нужную категорию.</p></div>
          {trends.map((trend) => {
            const currentId = assignments[trend.id] || "trends";
            const isEditing = editingTrend?.id === trend.id;
            return <article className={`trend-folder-admin-trend${trend.is_active ? "" : " is-hidden"}`} key={trend.id} data-testid={`trend-admin-item-${trend.id}`}>
              <div className="trend-folder-admin-trend-head">
                <span><strong>{trend.title}</strong><small>{trend.payload?.media_type === "video" ? "Видео" : "Фото"} · {trend.is_active ? "Опубликован" : "Скрыт"}</small></span>
                <span className={`trend-folder-admin-status${trend.is_active ? " is-live" : ""}`}>{trend.is_active ? "В трендах" : "Скрыт"}</span>
              </div>

              {isEditing && editingTrend ? <form className="trend-folder-admin-trend-form" onSubmit={(event) => { event.preventDefault(); void saveTrend(); }}>
                <label><span>Название</span><input value={editingTrend.title} maxLength={120} onChange={(event) => setEditingTrend((current) => current ? { ...current, title: event.target.value } : current)} /></label>
                <label><span>Описание</span><textarea value={editingTrend.description} rows={2} onChange={(event) => setEditingTrend((current) => current ? { ...current, description: event.target.value } : current)} /></label>
                <label><span>Хэштеги</span><input value={editingTrend.tags} onChange={(event) => setEditingTrend((current) => current ? { ...current, tags: event.target.value } : current)} placeholder="#др #birthday" /></label>
                <div className="actions">
                  <button type="button" onClick={() => setEditingTrend(null)}>Отмена</button>
                  <button className="primary" type="submit" data-testid={`trend-admin-save-${trend.id}`} disabled={busy === `trend-save:${trend.id}`}>{busy === `trend-save:${trend.id}` ? "Сохраняю…" : "Сохранить"}</button>
                </div>
              </form> : <>
                {trend.payload?.description ? <p className="trend-folder-admin-trend-description">{trend.payload.description}</p> : null}
                {(trend.payload?.tags || []).length ? <div className="trend-folder-admin-tags">{(trend.payload.tags || []).map((tag) => <span key={tag}>#{String(tag).replace(/^#/, "")}</span>)}</div> : null}
              </>}

              <div className="trend-folder-admin-controls">
                <select aria-label={`Категория для ${trend.title}`} data-testid={`trend-admin-category-${trend.id}`} value={collectionById.has(currentId) ? currentId : "trends"} disabled={busy === `trend:${trend.id}`} onChange={(event) => void assign(trend.id, event.target.value)}>
                  {collections.map((folder) => <option key={folder.id} value={folder.id}>{folder.title}{folder.is_active ? "" : " · скрыта"}</option>)}
                </select>
                <button type="button" data-testid={`trend-admin-edit-${trend.id}`} onClick={() => setEditingTrend(trendDraft(trend))}>Редактировать</button>
                <button type="button" data-testid={`trend-admin-visibility-${trend.id}`} className={trend.is_active ? "danger" : ""} disabled={busy === `trend-status:${trend.id}`} onClick={() => void toggleTrend(trend)}>{busy === `trend-status:${trend.id}` ? "…" : trend.is_active ? "Скрыть" : "Опубликовать"}</button>
              </div>
            </article>;
          })}
        </div>
      </section>
      <style jsx global>{`
        .trend-folder-admin-open{border:1px solid rgba(203,135,255,.35);background:rgba(154,76,255,.14);color:#e6c7ff;border-radius:999px;padding:8px 12px;font-weight:800}
        .trend-folder-admin-overlay{position:fixed;inset:0;z-index:155;background:rgba(2,1,5,.8);backdrop-filter:blur(12px);display:flex;align-items:flex-end;justify-content:center}
        .trend-folder-admin-panel{width:min(100%,760px);max-height:94dvh;overflow:auto;background:#0b0910;border:1px solid rgba(255,255,255,.1);border-radius:25px 25px 0 0;padding:18px 16px calc(28px + env(safe-area-inset-bottom));color:#fff}
        .trend-folder-admin-head{display:flex;justify-content:space-between;gap:16px}.trend-folder-admin-head h2{margin:3px 0 4px;font-size:26px}.trend-folder-admin-head p,.trend-folder-admin-assign p{margin:0;color:#aaa2b4;font-size:13px}.trend-folder-admin-head>button{width:38px;height:38px;border-radius:50%;border:1px solid rgba(255,255,255,.12);background:#17131d;color:#fff;font-size:23px}
        .trend-folder-admin-toolbar,.trend-folder-admin-form .actions,.trend-folder-admin-card .actions,.trend-folder-admin-trend-form .actions,.trend-folder-admin-controls{display:flex;gap:9px;flex-wrap:wrap}.trend-folder-admin-toolbar{margin:16px 0}.trend-folder-admin-toolbar button,.trend-folder-admin-form button,.trend-folder-admin-card button,.trend-folder-admin-trend button{min-height:40px;border:1px solid rgba(255,255,255,.11);background:#17131d;color:#fff;border-radius:12px;padding:0 13px;font-weight:800}.trend-folder-admin-toolbar .primary,.trend-folder-admin-form .primary,.trend-folder-admin-trend-form .primary{border:0;background:linear-gradient(135deg,#a84dff,#d66cff)}
        .trend-folder-admin-error{margin:10px 0;padding:11px 12px;border-radius:13px;background:rgba(255,74,110,.1);color:#ffc5d1}.trend-folder-admin-empty{color:#aaa2b4;padding:14px}
        .trend-folder-admin-form,.trend-folder-admin-trend-form{display:grid;gap:10px;margin:12px 0 18px;padding:14px;border:1px solid rgba(190,120,255,.25);border-radius:18px;background:#110e16}.trend-folder-admin-form label,.trend-folder-admin-trend-form label{display:grid;gap:6px}.trend-folder-admin-form label span,.trend-folder-admin-trend-form label span{font-size:11px;color:#bbb2c5;font-weight:800}.trend-folder-admin-form input,.trend-folder-admin-form textarea,.trend-folder-admin-trend-form input,.trend-folder-admin-trend-form textarea{width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.11);border-radius:12px;background:#08070b;color:#fff;padding:11px 12px;font:inherit}
        .trend-folder-admin-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}.trend-folder-admin-card{padding:13px;border:1px solid rgba(255,255,255,.09);border-radius:17px;background:#110e16}.trend-folder-admin-card.is-hidden,.trend-folder-admin-trend.is-hidden{opacity:.62}.trend-folder-admin-card>div:first-child{display:flex;align-items:center;justify-content:space-between;gap:8px}.trend-folder-admin-card small{color:#9d93a8;font-size:10px}.trend-folder-admin-card p{min-height:34px;color:#aaa2b4;font-size:12px;line-height:1.4}.trend-folder-admin-card .danger,.trend-folder-admin-trend .danger{color:#ffbdca;border-color:rgba(255,100,130,.3)}
        .trend-folder-admin-assign{display:grid;gap:9px;margin-top:22px}.trend-folder-admin-assign h3{margin:4px 0;font-size:20px}.trend-folder-admin-trend{display:grid;gap:10px;padding:12px;border:1px solid rgba(255,255,255,.08);border-radius:16px;background:#100d14}.trend-folder-admin-trend-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.trend-folder-admin-trend-head>span:first-child{display:grid;min-width:0}.trend-folder-admin-trend-head strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.trend-folder-admin-trend-head small{color:#9d93a8}.trend-folder-admin-status{flex:0 0 auto;border:1px solid rgba(255,255,255,.1);border-radius:999px;padding:5px 8px;color:#aaa2b4;font-size:10px;font-weight:800}.trend-folder-admin-status.is-live{border-color:rgba(139,255,201,.2);color:#9ff3c9}.trend-folder-admin-trend-description{margin:0;color:#aaa2b4;font-size:12px;line-height:1.45}.trend-folder-admin-tags{display:flex;gap:6px;flex-wrap:wrap}.trend-folder-admin-tags span{padding:4px 7px;border-radius:999px;background:rgba(169,91,255,.12);color:#d9b5ff;font-size:11px}.trend-folder-admin-controls{align-items:center}.trend-folder-admin-controls select{flex:1 1 190px;min-width:0;border:1px solid rgba(255,255,255,.11);border-radius:11px;background:#08070b;color:#fff;padding:10px}
        @media(max-width:520px){.trend-folder-admin-list{grid-template-columns:1fr}.trend-folder-admin-trend-head{align-items:center}.trend-folder-admin-controls{display:grid;grid-template-columns:1fr 1fr}.trend-folder-admin-controls select{grid-column:1/-1;width:100%}}
      `}</style>
    </div> : null}
  </>;
}