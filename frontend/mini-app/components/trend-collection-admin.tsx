"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import {
  TREND_COLLECTION_TARGET_KEY,
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

const emptyDraft = (): FolderDraft => ({
  title: "",
  description: "",
  sortOrder: 100,
  isActive: true,
});

export function TrendCollectionAdmin({ onChanged }: Props) {
  const [isAdmin, setIsAdmin] = useState(false);
  const [open, setOpen] = useState(false);
  const [collections, setCollections] = useState<TrendCollection[]>([]);
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [trends, setTrends] = useState<TrendAdminItem[]>([]);
  const [draft, setDraft] = useState<FolderDraft | null>(null);
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
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить папки");
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
      setError("Введите название папки");
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
      setError(cause instanceof Error ? cause.message : "Не удалось сохранить папку");
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
      setError(cause instanceof Error ? cause.message : "Не удалось изменить папку");
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

  const openTrendEditor = (collectionId = "trends") => {
    try { window.sessionStorage.setItem(TREND_COLLECTION_TARGET_KEY, collectionId); } catch { /* optional */ }
    setOpen(false);
    window.setTimeout(() => {
      const button = document.querySelector<HTMLButtonElement>(".inline-trend-add-button");
      button?.click();
    }, 80);
  };

  if (!isAdmin) return null;

  return <>
    <button className="trend-folder-admin-open" type="button" onClick={() => setOpen(true)}>Папки</button>
    {open ? <div className="trend-folder-admin-overlay" role="dialog" aria-modal="true" aria-label="Управление папками шаблонов">
      <section className="trend-folder-admin-panel">
        <header className="trend-folder-admin-head">
          <div><span className="kicker">Админ</span><h2>Папки шаблонов</h2><p>Пользователи только выбирают готовое. Добавлять и раскладывать контент можете только вы.</p></div>
          <button type="button" onClick={() => { setOpen(false); setDraft(null); }} aria-label="Закрыть">×</button>
        </header>

        <div className="trend-folder-admin-toolbar">
          <button className="primary" type="button" onClick={() => setDraft(emptyDraft())}>＋ Новая папка</button>
          <button type="button" onClick={() => openTrendEditor("trends")}>＋ Новый тренд</button>
          <button type="button" onClick={() => void refresh()} disabled={loading}>Обновить</button>
        </div>

        {error ? <div className="trend-folder-admin-error" role="alert">{error}</div> : null}
        {loading ? <div className="trend-folder-admin-empty">Загружаю…</div> : null}

        {draft ? <form className="trend-folder-admin-form" onSubmit={(event) => { event.preventDefault(); void saveFolder(); }}>
          <strong>{draft.id ? "Редактировать папку" : "Новая папка"}</strong>
          <label><span>Название</span><input value={draft.title} maxLength={80} onChange={(event) => setDraft((current) => current ? { ...current, title: event.target.value } : current)} placeholder="Например, 8 марта" autoFocus /></label>
          <label><span>Описание</span><textarea value={draft.description} maxLength={240} rows={2} onChange={(event) => setDraft((current) => current ? { ...current, description: event.target.value } : current)} placeholder="Что лежит в этой папке" /></label>
          <label><span>Порядок</span><input type="number" min={-100000} max={100000} value={draft.sortOrder} onChange={(event) => setDraft((current) => current ? { ...current, sortOrder: Number(event.target.value || 0) } : current)} /></label>
          <div className="actions"><button type="button" onClick={() => setDraft(null)}>Отмена</button><button className="primary" type="submit" disabled={saving}>{saving ? "Сохраняю…" : "Сохранить"}</button></div>
        </form> : null}

        <div className="trend-folder-admin-list">
          {collections.map((folder) => <article className={`trend-folder-admin-card${folder.is_active ? "" : " is-hidden"}`} key={folder.id}>
            <div><strong>{folder.title}</strong>{folder.system_key ? <small>Системная папка</small> : <small>Ваша папка</small>}</div>
            {folder.description ? <p>{folder.description}</p> : null}
            <div className="actions">
              <button type="button" onClick={() => openTrendEditor(folder.id)}>＋ Шаблон</button>
              <button type="button" onClick={() => setDraft({ id: folder.id, title: folder.title, description: folder.description || "", sortOrder: folder.sort_order, isActive: folder.is_active })}>Редактировать</button>
              <button type="button" className={folder.is_active ? "danger" : ""} disabled={busy === folder.id} onClick={() => void toggleFolder(folder)}>{busy === folder.id ? "…" : folder.is_active ? "Скрыть" : "Показать"}</button>
            </div>
          </article>)}
        </div>

        <div className="trend-folder-admin-assign">
          <div><span className="kicker">Содержимое</span><h3>Разложить шаблоны по папкам</h3><p>Старые тренды по умолчанию остаются в папке «Тренды».</p></div>
          {trends.map((trend) => {
            const currentId = assignments[trend.id] || "trends";
            return <label className="trend-folder-admin-assignment" key={trend.id}>
              <span><strong>{trend.title}</strong><small>{trend.payload?.media_type === "video" ? "Видео" : "Фото"}</small></span>
              <select value={collectionById.has(currentId) ? currentId : "trends"} disabled={busy === `trend:${trend.id}`} onChange={(event) => void assign(trend.id, event.target.value)}>
                {collections.map((folder) => <option key={folder.id} value={folder.id}>{folder.title}{folder.is_active ? "" : " · скрыта"}</option>)}
              </select>
            </label>;
          })}
        </div>
      </section>
      <style jsx global>{`
        .trend-folder-admin-open{border:1px solid rgba(203,135,255,.35);background:rgba(154,76,255,.14);color:#e6c7ff;border-radius:999px;padding:8px 12px;font-weight:800}
        .trend-folder-admin-overlay{position:fixed;inset:0;z-index:155;background:rgba(2,1,5,.8);backdrop-filter:blur(12px);display:flex;align-items:flex-end;justify-content:center}
        .trend-folder-admin-panel{width:min(100%,760px);max-height:94dvh;overflow:auto;background:#0b0910;border:1px solid rgba(255,255,255,.1);border-radius:25px 25px 0 0;padding:18px 16px calc(28px + env(safe-area-inset-bottom));color:#fff}
        .trend-folder-admin-head{display:flex;justify-content:space-between;gap:16px}.trend-folder-admin-head h2{margin:3px 0 4px;font-size:26px}.trend-folder-admin-head p,.trend-folder-admin-assign p{margin:0;color:#aaa2b4;font-size:13px}.trend-folder-admin-head>button{width:38px;height:38px;border-radius:50%;border:1px solid rgba(255,255,255,.12);background:#17131d;color:#fff;font-size:23px}
        .trend-folder-admin-toolbar,.trend-folder-admin-form .actions,.trend-folder-admin-card .actions{display:flex;gap:9px;flex-wrap:wrap}.trend-folder-admin-toolbar{margin:16px 0}.trend-folder-admin-toolbar button,.trend-folder-admin-form button,.trend-folder-admin-card button{min-height:40px;border:1px solid rgba(255,255,255,.11);background:#17131d;color:#fff;border-radius:12px;padding:0 13px;font-weight:800}.trend-folder-admin-toolbar .primary,.trend-folder-admin-form .primary{border:0;background:linear-gradient(135deg,#a84dff,#d66cff)}
        .trend-folder-admin-error{margin:10px 0;padding:11px 12px;border-radius:13px;background:rgba(255,74,110,.1);color:#ffc5d1}.trend-folder-admin-empty{color:#aaa2b4;padding:14px}
        .trend-folder-admin-form{display:grid;gap:10px;margin:12px 0 18px;padding:14px;border:1px solid rgba(190,120,255,.25);border-radius:18px;background:#110e16}.trend-folder-admin-form label{display:grid;gap:6px}.trend-folder-admin-form label span{font-size:11px;color:#bbb2c5;font-weight:800}.trend-folder-admin-form input,.trend-folder-admin-form textarea{width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.11);border-radius:12px;background:#08070b;color:#fff;padding:11px 12px;font:inherit}
        .trend-folder-admin-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}.trend-folder-admin-card{padding:13px;border:1px solid rgba(255,255,255,.09);border-radius:17px;background:#110e16}.trend-folder-admin-card.is-hidden{opacity:.6}.trend-folder-admin-card>div:first-child{display:flex;align-items:center;justify-content:space-between;gap:8px}.trend-folder-admin-card small{color:#9d93a8;font-size:10px}.trend-folder-admin-card p{min-height:34px;color:#aaa2b4;font-size:12px;line-height:1.4}.trend-folder-admin-card .danger{color:#ffbdca;border-color:rgba(255,100,130,.3)}
        .trend-folder-admin-assign{display:grid;gap:9px;margin-top:22px}.trend-folder-admin-assign h3{margin:4px 0;font-size:20px}.trend-folder-admin-assignment{display:grid;grid-template-columns:minmax(0,1fr) minmax(150px,240px);gap:10px;align-items:center;padding:11px 12px;border:1px solid rgba(255,255,255,.08);border-radius:14px;background:#100d14}.trend-folder-admin-assignment>span{display:grid;min-width:0}.trend-folder-admin-assignment strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.trend-folder-admin-assignment small{color:#9d93a8}.trend-folder-admin-assignment select{min-width:0;border:1px solid rgba(255,255,255,.11);border-radius:11px;background:#08070b;color:#fff;padding:10px}
        @media(max-width:520px){.trend-folder-admin-assignment{grid-template-columns:1fr}.trend-folder-admin-list{grid-template-columns:1fr}}
      `}</style>
    </div> : null}
  </>;
}
