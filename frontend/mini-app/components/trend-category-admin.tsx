"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { trendAdminApi, type TrendAdminItem } from "@/lib/trend-admin-api";
import {
  trendCollectionsApi,
  type TrendCollection,
  type TrendCollectionWrite,
} from "@/lib/trend-collections-api";

type Props = { onChanged?: () => void };

type CategoryDraft = {
  id?: string;
  title: string;
  description: string;
  hashtags: string;
  sortOrder: number;
  isActive: boolean;
};

function emptyDraft(): CategoryDraft {
  return {
    title: "",
    description: "",
    hashtags: "",
    sortOrder: 100,
    isActive: true,
  };
}

function normalizeHashtags(value: string): string[] {
  const tags: string[] = [];
  const seen = new Set<string>();
  for (const token of value.split(/[,\s;]+/u)) {
    const tag = token.trim().replace(/^#+/, "").toLocaleLowerCase("ru-RU");
    if (!tag || seen.has(tag)) continue;
    seen.add(tag);
    tags.push(tag);
  }
  return tags;
}

function hashtagsInput(tags: string[] | undefined): string {
  return (tags || []).map((tag) => `#${String(tag).replace(/^#+/, "")}`).join(" ");
}

function searchValue(value: string): string {
  return value.trim().replace(/^#+/, "").toLocaleLowerCase("ru-RU");
}

function searchText(values: Array<string | undefined | null>): string {
  return values.filter(Boolean).join(" ").toLocaleLowerCase("ru-RU");
}

function matchesCategory(category: TrendCollection, query: string): boolean {
  if (!query) return true;
  return searchText([
    category.title,
    category.description,
    ...(category.aliases || []),
  ]).includes(query);
}

function matchesTrend(
  trend: TrendAdminItem,
  query: string,
  category: TrendCollection | undefined,
): boolean {
  if (!query) return false;
  return searchText([
    trend.title,
    trend.payload?.description,
    ...(trend.payload?.tags || []),
    category?.title,
    category?.description,
    ...(category?.aliases || []),
  ]).includes(query);
}

function writeFromCategory(category: TrendCollection, isActive: boolean): TrendCollectionWrite {
  return {
    title: category.title,
    description: category.description || "",
    hashtags: category.aliases || [],
    sort_order: category.sort_order,
    is_active: isActive,
  };
}

export function TrendCategoryAdmin({ onChanged }: Props) {
  const [isAdmin, setIsAdmin] = useState(false);
  const [open, setOpen] = useState(false);
  const [collections, setCollections] = useState<TrendCollection[]>([]);
  const [trends, setTrends] = useState<TrendAdminItem[]>([]);
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState<CategoryDraft | null>(null);
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

  const categories = useMemo(
    () => collections.filter((category) => category.id !== "trends" && category.system_key !== "trends"),
    [collections],
  );
  const collectionById = useMemo(
    () => new Map(collections.map((category) => [category.id, category])),
    [collections],
  );
  const normalizedQuery = searchValue(query);
  const filteredCategories = useMemo(
    () => categories.filter((category) => matchesCategory(category, normalizedQuery)),
    [categories, normalizedQuery],
  );
  const filteredTrends = useMemo(
    () => trends.filter((trend) => matchesTrend(
      trend,
      normalizedQuery,
      collectionById.get(assignments[trend.id] || trend.collection_id || "trends"),
    )),
    [assignments, collectionById, normalizedQuery, trends],
  );

  const close = () => {
    setOpen(false);
    setQuery("");
    setDraft(null);
    setError("");
  };

  const edit = (category: TrendCollection) => {
    setDraft({
      id: category.id,
      title: category.title,
      description: category.description || "",
      hashtags: hashtagsInput(category.aliases),
      sortOrder: category.sort_order,
      isActive: category.is_active,
    });
  };

  const save = async () => {
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
      hashtags: normalizeHashtags(draft.hashtags),
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

  const toggle = async (category: TrendCollection) => {
    if (busy) return;
    setBusy(`toggle:${category.id}`);
    setError("");
    try {
      if (category.is_active) await trendCollectionsApi.update(category.id, writeFromCategory(category, false));
      else await trendCollectionsApi.activate(category.id);
      await refresh();
      onChanged?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось изменить категорию");
    } finally {
      setBusy("");
    }
  };

  const remove = async (category: TrendCollection) => {
    if (busy) return;
    if (!window.confirm(`Удалить категорию «${category.title}»? Шаблоны останутся в общем списке.`)) return;
    setBusy(`delete:${category.id}`);
    setError("");
    try {
      await trendCollectionsApi.remove(category.id);
      if (draft?.id === category.id) setDraft(null);
      await refresh();
      onChanged?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось удалить категорию");
    } finally {
      setBusy("");
    }
  };

  const assignTrend = async (trendId: string, collectionId: string) => {
    if (!collectionId || busy) return;
    setBusy(`assign:${trendId}`);
    setError("");
    try {
      await trendCollectionsApi.assign(trendId, collectionId);
      setAssignments((current) => ({ ...current, [trendId]: collectionId }));
      onChanged?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось назначить категорию");
    } finally {
      setBusy("");
    }
  };

  if (!isAdmin) return null;

  return <>
    <button
      className="trend-category-admin-open"
      type="button"
      onClick={() => setOpen(true)}
      data-testid="trend-category-admin-open"
    >Управлять</button>

    {open ? <div className="trend-category-admin-overlay" role="dialog" aria-modal="true" aria-label="Управление категориями">
      <section className="trend-category-admin-panel">
        <header className="trend-category-admin-head">
          <div>
            <span className="kicker">Админ</span>
            <h2>Категории</h2>
            <p>Создавайте категории и задавайте хэштеги. Новый тренд с совпавшим хэштегом автоматически попадёт в нужную категорию.</p>
          </div>
          <button type="button" onClick={close} aria-label="Закрыть">×</button>
        </header>

        <div className="trend-category-admin-toolbar">
          <button className="primary" type="button" onClick={() => setDraft(emptyDraft())}>＋ Новая категория</button>
          <button type="button" onClick={() => void refresh()} disabled={loading}>Обновить</button>
        </div>

        <label className="trend-category-admin-search">
          <span>Поиск по названию или хэштегу</span>
          <div>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Например, UGC или #ugc"
              aria-label="Поиск категорий и трендов по названию или хэштегу"
              data-testid="trend-category-admin-search"
            />
            {query ? <button type="button" onClick={() => setQuery("")} aria-label="Очистить поиск">×</button> : null}
          </div>
        </label>

        {error ? <div className="trend-category-admin-error" role="alert">{error}</div> : null}

        {draft ? <form className="trend-category-admin-form" onSubmit={(event) => { event.preventDefault(); void save(); }}>
          <strong>{draft.id ? "Редактировать категорию" : "Новая категория"}</strong>
          <label>
            <span>Название</span>
            <input value={draft.title} maxLength={80} onChange={(event) => setDraft((current) => current ? { ...current, title: event.target.value } : current)} placeholder="Например, UGC" autoFocus />
          </label>
          <label>
            <span>Описание</span>
            <textarea value={draft.description} maxLength={240} rows={2} onChange={(event) => setDraft((current) => current ? { ...current, description: event.target.value } : current)} placeholder="Коротко о содержимом категории" />
          </label>
          <label>
            <span>Хэштеги</span>
            <input value={draft.hashtags} onChange={(event) => setDraft((current) => current ? { ...current, hashtags: event.target.value } : current)} placeholder="#ugc #review #распаковка" data-testid="trend-category-admin-hashtags" />
            <small>Через пробел или запятую. Регистр и повторная решётка не важны, дубли убираются.</small>
          </label>
          <label>
            <span>Порядок</span>
            <input type="number" min={-100000} max={100000} value={draft.sortOrder} onChange={(event) => setDraft((current) => current ? { ...current, sortOrder: Number(event.target.value || 0) } : current)} />
          </label>
          <div className="actions">
            <button type="button" onClick={() => setDraft(null)}>Отмена</button>
            <button className="primary" type="submit" disabled={saving} data-testid="trend-category-admin-save">{saving ? "Сохраняю…" : "Сохранить"}</button>
          </div>
        </form> : null}

        {loading ? <div className="trend-category-admin-empty">Загружаю категории…</div> : null}
        {!loading && filteredCategories.length ? <div className="trend-category-admin-list">
          {filteredCategories.map((category) => <article className={`trend-category-admin-card${category.is_active ? "" : " is-hidden"}`} key={category.id} data-testid={`trend-category-admin-card-${category.id}`}>
            <div className="trend-category-admin-card-head">
              <span><strong>{category.title}</strong><small>{category.is_active ? "Показывается" : "Скрыта"}</small></span>
              <span className="trend-category-admin-count">{Number(category.item_count || 0)} шт.</span>
            </div>
            {category.description ? <p>{category.description}</p> : null}
            {(category.aliases || []).length ? <div className="trend-category-admin-tags">{(category.aliases || []).map((tag) => <span key={tag}>#{String(tag).replace(/^#+/, "")}</span>)}</div> : <small className="trend-category-admin-no-tags">Хэштеги не заданы</small>}
            <div className="actions">
              <button type="button" onClick={() => edit(category)}>Редактировать</button>
              <button type="button" disabled={busy === `toggle:${category.id}`} onClick={() => void toggle(category)}>{busy === `toggle:${category.id}` ? "…" : category.is_active ? "Скрыть" : "Показать"}</button>
              <button type="button" className="danger" disabled={busy === `delete:${category.id}`} onClick={() => void remove(category)}>{busy === `delete:${category.id}` ? "Удаляю…" : "Удалить"}</button>
            </div>
          </article>)}
        </div> : null}

        {!loading && normalizedQuery && filteredTrends.length ? <div className="trend-category-admin-trends">
          <div className="trend-category-admin-subhead">
            <strong>Тренды по запросу</strong>
            <small>{filteredTrends.length}</small>
          </div>
          {filteredTrends.map((trend) => {
            const currentId = assignments[trend.id] || trend.collection_id || "trends";
            return <article className="trend-category-admin-trend" key={trend.id} data-testid={`trend-category-admin-trend-${trend.id}`}>
              <div>
                <strong>{trend.title}</strong>
                {trend.payload?.description ? <small>{trend.payload.description}</small> : null}
              </div>
              {(trend.payload?.tags || []).length ? <div className="trend-category-admin-tags">{(trend.payload.tags || []).map((tag) => <span key={tag}>#{String(tag).replace(/^#+/, "")}</span>)}</div> : null}
              <label>
                <span>Категория</span>
                <select
                  aria-label={`Категория для ${trend.title}`}
                  value={collectionById.has(currentId) ? currentId : "trends"}
                  disabled={busy === `assign:${trend.id}`}
                  onChange={(event) => void assignTrend(trend.id, event.target.value)}
                >
                  {collections.map((category) => <option key={category.id} value={category.id}>{category.title}{category.is_active ? "" : " · скрыта"}</option>)}
                </select>
              </label>
            </article>;
          })}
        </div> : null}

        {!loading && normalizedQuery && !filteredCategories.length && !filteredTrends.length ? <div className="trend-category-admin-empty" data-testid="trend-category-admin-empty">По этому названию или хэштегу ничего не найдено.</div> : null}
        {!loading && !normalizedQuery && !categories.length ? <div className="trend-category-admin-empty">Категорий пока нет. Создайте первую.</div> : null}
      </section>

      <style jsx global>{`
        .trend-category-admin-open{border:1px solid rgba(203,135,255,.38);background:rgba(154,76,255,.16);color:#ead2ff;border-radius:999px;padding:8px 12px;font-weight:850;white-space:nowrap}
        .trend-category-admin-overlay{position:fixed;inset:0;z-index:158;background:rgba(2,1,5,.82);backdrop-filter:blur(12px);display:flex;align-items:flex-end;justify-content:center}
        .trend-category-admin-panel{width:min(100%,720px);max-height:94dvh;overflow:auto;background:#0b0910;border:1px solid rgba(255,255,255,.1);border-radius:25px 25px 0 0;padding:18px 16px calc(28px + env(safe-area-inset-bottom));color:#fff}
        .trend-category-admin-head{display:flex;justify-content:space-between;gap:16px}.trend-category-admin-head h2{margin:3px 0 4px;font-size:26px}.trend-category-admin-head p{margin:0;color:#aaa2b4;font-size:13px;line-height:1.45}.trend-category-admin-head>button{width:38px;height:38px;flex:0 0 auto;border-radius:50%;border:1px solid rgba(255,255,255,.12);background:#17131d;color:#fff;font-size:23px}
        .trend-category-admin-toolbar,.trend-category-admin-form .actions,.trend-category-admin-card .actions{display:flex;gap:9px;flex-wrap:wrap}.trend-category-admin-toolbar{margin:16px 0 12px}.trend-category-admin-toolbar button,.trend-category-admin-form button,.trend-category-admin-card button{min-height:40px;border:1px solid rgba(255,255,255,.11);background:#17131d;color:#fff;border-radius:12px;padding:0 13px;font-weight:800}.trend-category-admin-toolbar .primary,.trend-category-admin-form .primary{border:0;background:linear-gradient(135deg,#a84dff,#d66cff)}
        .trend-category-admin-search{display:grid;gap:6px;margin:0 0 14px}.trend-category-admin-search>span,.trend-category-admin-form label>span,.trend-category-admin-trend label>span{font-size:11px;color:#bbb2c5;font-weight:800}.trend-category-admin-search>div{position:relative}.trend-category-admin-search input{width:100%;box-sizing:border-box;border:1px solid rgba(203,135,255,.24);border-radius:14px;background:#08070b;color:#fff;padding:12px 42px 12px 13px;font:inherit;outline:none}.trend-category-admin-search input:focus{border-color:rgba(203,135,255,.62);box-shadow:0 0 0 3px rgba(168,77,255,.1)}.trend-category-admin-search div>button{position:absolute;right:7px;top:50%;transform:translateY(-50%);width:30px;height:30px;border:0;border-radius:50%;background:#17131d;color:#c9c0d2;font-size:18px}
        .trend-category-admin-error{margin:10px 0;padding:11px 12px;border-radius:13px;background:rgba(255,74,110,.1);color:#ffc5d1}.trend-category-admin-empty{padding:15px;border:1px dashed rgba(190,130,255,.22);border-radius:16px;color:#aaa2b4;background:rgba(16,12,22,.68)}
        .trend-category-admin-form{display:grid;gap:10px;margin:12px 0 18px;padding:14px;border:1px solid rgba(190,120,255,.25);border-radius:18px;background:#110e16}.trend-category-admin-form label{display:grid;gap:6px}.trend-category-admin-form label small{font-size:10px;color:#817888;line-height:1.4}.trend-category-admin-form input,.trend-category-admin-form textarea{width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.11);border-radius:12px;background:#08070b;color:#fff;padding:11px 12px;font:inherit}
        .trend-category-admin-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}.trend-category-admin-card{display:grid;gap:10px;padding:13px;border:1px solid rgba(255,255,255,.09);border-radius:17px;background:#110e16}.trend-category-admin-card.is-hidden{opacity:.62}.trend-category-admin-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:9px}.trend-category-admin-card-head>span:first-child{display:grid;gap:2px;min-width:0}.trend-category-admin-card-head strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.trend-category-admin-card-head small,.trend-category-admin-no-tags{color:#9d93a8;font-size:10px}.trend-category-admin-count{flex:0 0 auto;padding:4px 7px;border-radius:999px;background:rgba(169,91,255,.12);color:#d9b5ff;font-size:10px;font-weight:800}.trend-category-admin-card p{margin:0;color:#aaa2b4;font-size:12px;line-height:1.4}.trend-category-admin-tags{display:flex;gap:6px;flex-wrap:wrap}.trend-category-admin-tags span{padding:4px 7px;border-radius:999px;background:rgba(169,91,255,.12);color:#d9b5ff;font-size:11px}.trend-category-admin-card .danger{color:#ffbdca;border-color:rgba(255,100,130,.3)}
        .trend-category-admin-trends{display:grid;gap:9px;margin-top:18px;padding-top:16px;border-top:1px solid rgba(255,255,255,.08)}.trend-category-admin-subhead{display:flex;align-items:center;justify-content:space-between;gap:10px}.trend-category-admin-subhead small{padding:4px 7px;border-radius:999px;background:rgba(169,91,255,.12);color:#d9b5ff}.trend-category-admin-trend{display:grid;gap:9px;padding:12px;border:1px solid rgba(255,255,255,.08);border-radius:16px;background:#100d14}.trend-category-admin-trend>div:first-child{display:grid;gap:3px}.trend-category-admin-trend>div:first-child small{color:#9d93a8;font-size:11px;line-height:1.4}.trend-category-admin-trend label{display:grid;gap:5px}.trend-category-admin-trend select{width:100%;min-width:0;border:1px solid rgba(255,255,255,.11);border-radius:11px;background:#08070b;color:#fff;padding:10px}
        @media(max-width:520px){.trend-category-admin-list{grid-template-columns:1fr}.trend-category-admin-toolbar button{flex:1 1 auto}}
      `}</style>
    </div> : null}
  </>;
}
