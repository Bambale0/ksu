"use client";

import { useEffect, useMemo, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { aiReferenceApi, type AiReferenceQuote, type AiReferenceScenario, type AiReferenceSubject } from "@/lib/ai-reference-api";
import { api } from "@/lib/api";
import { haptic } from "@/lib/telegram";

type UploadedReference = { url: string; name: string };

type ScenarioCard = {
  id: AiReferenceScenario;
  title: string;
  copy: string;
  badge: string;
};

const SCENARIOS: ScenarioCard[] = [
  {
    id: "create",
    title: "Создать референс",
    copy: "Соберите чистый референс человека, ребёнка или питомца из ваших фотографий.",
    badge: "Главный старт",
  },
  {
    id: "hd",
    title: "Улучшить качество HD",
    copy: "Повышает детализацию и резкость, сохраняя лицо, композицию и исходный образ.",
    badge: "4K",
  },
  {
    id: "edit",
    title: "Редактор референса",
    copy: "Макияж, причёска, цвет волос и другие точечные изменения готового референса.",
    badge: "Своя инструкция",
  },
];

const SUBJECTS: Array<{ id: AiReferenceSubject; title: string; copy: string }> = [
  { id: "adult", title: "Взрослый", copy: "Сохраняем внешность и естественные черты" },
  { id: "child", title: "Детский", copy: "Сохраняем возраст и детские черты без взрослой стилизации" },
  { id: "pet", title: "Для животных", copy: "Сохраняем породу, окрас, отметины и пропорции" },
];

function scenarioFromUrl(): AiReferenceScenario | null {
  if (typeof window === "undefined") return null;
  const value = new URL(window.location.href).searchParams.get("scenario");
  return value === "create" || value === "hd" || value === "edit" ? value : null;
}

function money(value?: string | null): string {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return value || "—";
  return number.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

function scenarioTitle(scenario: AiReferenceScenario | null): string {
  if (scenario === "create") return "Создание референса";
  if (scenario === "hd") return "Улучшение качества HD";
  if (scenario === "edit") return "Редактор референса";
  return "AI РЕФЕРЕНС";
}

function runLabel(scenario: AiReferenceScenario): string {
  if (scenario === "create") return "Создать референс";
  if (scenario === "hd") return "Улучшить в HD";
  return "Применить изменения";
}

export default function AiReferencePage() {
  const [scenario, setScenario] = useState<AiReferenceScenario | null>(null);
  const [subject, setSubject] = useState<AiReferenceSubject>("adult");
  const [references, setReferences] = useState<UploadedReference[]>([]);
  const [instruction, setInstruction] = useState("");
  const [uploading, setUploading] = useState(false);
  const [quoting, setQuoting] = useState(false);
  const [quote, setQuote] = useState<AiReferenceQuote | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => setScenario(scenarioFromUrl()), []);

  const maxReferences = scenario === "create" ? 4 : 1;
  const ready = Boolean(
    scenario
    && references.length >= 1
    && references.length <= maxReferences
    && (scenario !== "edit" || instruction.trim()),
  );

  const requestBody = useMemo(() => {
    if (!scenario) return null;
    return {
      scenario,
      subject: scenario === "create" ? subject : undefined,
      reference_urls: references.map((item) => item.url),
      instruction: scenario === "edit" ? instruction.trim() : undefined,
    };
  }, [instruction, references, scenario, subject]);

  useEffect(() => {
    if (!ready || !requestBody) {
      setQuote(null);
      setQuoting(false);
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      setQuoting(true);
      void aiReferenceApi.quote(requestBody)
        .then((result) => {
          if (!active) return;
          setQuote(result);
          setError("");
        })
        .catch((cause) => {
          if (!active) return;
          setQuote(null);
          setError(cause instanceof Error ? cause.message : "Не удалось рассчитать стоимость");
        })
        .finally(() => {
          if (active) setQuoting(false);
        });
    }, scenario === "edit" ? 350 : 80);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [ready, requestBody, scenario]);

  const chooseScenario = (next: AiReferenceScenario) => {
    haptic("light");
    setScenario(next);
    setReferences((current) => current.slice(0, next === "create" ? 4 : 1));
    setInstruction("");
    setQuote(null);
    setError("");
    const url = new URL(window.location.href);
    url.searchParams.set("scenario", next);
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  };

  const addFiles = async (files: File[]) => {
    if (!scenario || !files.length || uploading) return;
    const remaining = Math.max(0, maxReferences - references.length);
    const images = files.filter((file) => file.type.startsWith("image/")).slice(0, remaining);
    if (!images.length) {
      setError("Выберите фотографию");
      return;
    }
    setUploading(true);
    setError("");
    try {
      const uploaded: UploadedReference[] = [];
      for (const file of images) {
        const result = await api.upload(file);
        uploaded.push({ url: result.url, name: file.name });
      }
      setReferences((current) => [...current, ...uploaded].slice(0, maxReferences));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить фотографию");
    } finally {
      setUploading(false);
    }
  };

  const run = async () => {
    if (!ready || !requestBody || running) return;
    setRunning(true);
    setError("");
    haptic("medium");
    try {
      const result = await aiReferenceApi.run(requestBody);
      window.location.assign(`/mini-app/?route=history&generation=${encodeURIComponent(result.id)}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось запустить обработку");
      setRunning(false);
    }
  };

  return (
    <StandaloneShell
      kicker="AI РЕФЕРЕНС"
      title={scenarioTitle(scenario)}
      copy={scenario ? "Загрузите фото, проверьте настройки и запустите. Результат появится в истории ROXY." : "Главный набор инструментов для подготовки референса перед дальнейшей генерацией."}
    >
      <style jsx global>{`
        .ai-ref-grid{display:grid;gap:12px}.ai-ref-scenarios{display:grid;grid-template-columns:1fr;gap:11px}.ai-ref-scenario{width:100%;min-height:118px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;align-items:center;padding:18px;border:1px solid rgba(190,112,255,.28);border-radius:24px;background:radial-gradient(circle at 100% 0%,rgba(184,81,255,.18),transparent 42%),#100d16;color:#fff;text-align:left}.ai-ref-scenario strong{display:block;font-size:20px;line-height:1.05}.ai-ref-scenario small{display:block;margin-top:7px;color:var(--muted);font-size:13px;line-height:1.4}.ai-ref-scenario span{align-self:start;padding:6px 9px;border-radius:999px;background:rgba(173,76,255,.18);color:#e7c8ff;font-size:10px;font-weight:900}.ai-ref-change{justify-self:start;border:1px solid rgba(255,255,255,.11);border-radius:999px;background:#17131d;color:#fff;padding:9px 13px;font-weight:850}.ai-ref-panel{display:grid;gap:14px;padding:17px;border:1px solid rgba(255,255,255,.09);border-radius:24px;background:#0f0c14}.ai-ref-panel h2{margin:0;font-size:21px}.ai-ref-panel p{margin:0;color:var(--muted);font-size:13px;line-height:1.45}.ai-ref-subjects{display:grid;grid-template-columns:1fr;gap:9px}.ai-ref-subject{padding:14px;border:1px solid rgba(255,255,255,.1);border-radius:17px;background:#141019;color:#fff;text-align:left}.ai-ref-subject.active{border-color:rgba(205,118,255,.52);background:linear-gradient(135deg,rgba(169,74,255,.22),rgba(20,16,25,.92));box-shadow:0 10px 28px rgba(153,70,255,.12)}.ai-ref-subject strong{display:block}.ai-ref-subject small{display:block;margin-top:4px;color:var(--muted);line-height:1.35}.ai-ref-upload{min-height:120px;display:grid;place-items:center;border:1px dashed rgba(204,135,255,.36);border-radius:20px;background:rgba(144,63,225,.07);color:#ead5fb;cursor:pointer;text-align:center;padding:18px;font-weight:850}.ai-ref-upload small{display:block;margin-top:6px;color:var(--muted);font-weight:500}.ai-ref-upload input{display:none}.ai-ref-files{display:grid;grid-template-columns:repeat(auto-fill,minmax(94px,1fr));gap:9px}.ai-ref-file{position:relative;aspect-ratio:1/1;overflow:hidden;border:1px solid rgba(255,255,255,.1);border-radius:16px;background:#08070b}.ai-ref-file img{width:100%;height:100%;object-fit:cover}.ai-ref-file button{position:absolute;top:6px;right:6px;width:30px;height:30px;border:1px solid rgba(255,255,255,.16);border-radius:50%;background:rgba(5,4,8,.78);color:#fff;font-size:18px}.ai-ref-editor{display:grid;gap:7px}.ai-ref-editor span{font-size:12px;font-weight:850;color:#d9d1df}.ai-ref-editor textarea{width:100%;box-sizing:border-box;min-height:112px;resize:vertical;border:1px solid rgba(255,255,255,.11);border-radius:17px;background:#08070b;color:#fff;padding:13px;font:inherit;line-height:1.45}.ai-ref-editor textarea:focus{outline:none;border-color:rgba(202,114,255,.55);box-shadow:0 0 0 3px rgba(174,76,255,.11)}.ai-ref-summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 14px;border-radius:17px;background:#141019}.ai-ref-summary span{color:var(--muted);font-size:12px}.ai-ref-summary strong{font-size:17px}.ai-ref-error{padding:11px 13px;border-radius:14px;background:rgba(255,80,120,.1);color:#ffc6d3}.ai-ref-run{width:100%;min-height:52px;border:0;border-radius:17px;background:linear-gradient(135deg,#a84dff,#d66cff);color:#fff;font-weight:900;font-size:15px;box-shadow:0 14px 34px rgba(172,68,255,.24)}.ai-ref-run:disabled{opacity:.45;box-shadow:none}.ai-ref-note{font-size:11px!important;text-align:center}@media(min-width:720px){.ai-ref-scenarios{grid-template-columns:repeat(3,minmax(0,1fr))}.ai-ref-scenario{grid-template-columns:1fr;align-content:space-between}.ai-ref-subjects{grid-template-columns:repeat(3,minmax(0,1fr))}}
      `}</style>

      <div className="ai-ref-grid">
        {!scenario ? (
          <div className="ai-ref-scenarios">
            {SCENARIOS.map((item) => (
              <button className="ai-ref-scenario" type="button" key={item.id} onClick={() => chooseScenario(item.id)}>
                <div><strong>{item.title}</strong><small>{item.copy}</small></div>
                <span>{item.badge}</span>
              </button>
            ))}
          </div>
        ) : (
          <>
            <button className="ai-ref-change" type="button" onClick={() => { setScenario(null); setQuote(null); setError(""); }}>← Выбрать другой сценарий</button>

            {scenario === "create" ? (
              <section className="ai-ref-panel">
                <div><h2>Кого готовим?</h2><p>ROXY подстроит правила сохранения внешности под тип референса.</p></div>
                <div className="ai-ref-subjects">
                  {SUBJECTS.map((item) => (
                    <button className={`ai-ref-subject${subject === item.id ? " active" : ""}`} type="button" key={item.id} onClick={() => { haptic("light"); setSubject(item.id); }}>
                      <strong>{item.title}</strong><small>{item.copy}</small>
                    </button>
                  ))}
                </div>
              </section>
            ) : null}

            <section className="ai-ref-panel">
              <div>
                <h2>{scenario === "create" ? "Добавьте исходные фото" : scenario === "hd" ? "Добавьте фото для улучшения" : "Добавьте готовый референс"}</h2>
                <p>{scenario === "create" ? "Можно загрузить до 4 фотографий. Лучше добавить чёткий фронтальный кадр и ещё 1–2 ракурса." : "Нужна одна фотография. Исходник останется без изменений."}</p>
              </div>
              <label className="ai-ref-upload">
                <span>{uploading ? "Загружаю…" : references.length ? `Добавлено ${references.length}/${maxReferences}` : scenario === "create" ? "＋ Добавить фотографии" : "＋ Добавить фотографию"}<small>JPG, PNG, HEIC и другие изображения, которые принимает ROXY</small></span>
                <input
                  type="file"
                  accept="image/*"
                  multiple={scenario === "create"}
                  disabled={uploading || references.length >= maxReferences}
                  onChange={(event) => {
                    const files = Array.from(event.target.files || []);
                    event.target.value = "";
                    void addFiles(files);
                  }}
                />
              </label>
              {references.length ? <div className="ai-ref-files">
                {references.map((item, index) => <div className="ai-ref-file" key={`${item.url}-${index}`}><img src={item.url} alt={item.name || `Фото ${index + 1}`} /><button type="button" aria-label={`Удалить фото ${index + 1}`} onClick={() => setReferences((current) => current.filter((_, i) => i !== index))}>×</button></div>)}
              </div> : null}
            </section>

            {scenario === "edit" ? (
              <section className="ai-ref-panel">
                <label className="ai-ref-editor">
                  <span>Что изменить?</span>
                  <textarea value={instruction} maxLength={1200} onChange={(event) => setInstruction(event.target.value)} placeholder="Например: добавь лёгкий дневной макияж, сделай каре до плеч и поменяй цвет волос на холодный блонд. Остальное не меняй." />
                </label>
              </section>
            ) : null}

            <section className="ai-ref-panel">
              <div className="ai-ref-summary">
                <span>{quoting ? "Считаю стоимость…" : quote?.admin_free ? "Для администратора" : "Стоимость"}</span>
                <strong>{quoting ? "…" : quote ? quote.admin_free ? "Бесплатно" : `${money(quote.effective_cost_rox)} ROX` : "—"}</strong>
              </div>
              {error ? <div className="ai-ref-error" role="alert">{error}</div> : null}
              <button className="ai-ref-run" type="button" disabled={!ready || uploading || quoting || running || !quote} onClick={() => void run()}>
                {running ? "Запускаю…" : runLabel(scenario)}
              </button>
              <p className="ai-ref-note">Генерация запускается только после нажатия кнопки. Готовый результат появится в истории.</p>
            </section>
          </>
        )}
      </div>
    </StandaloneShell>
  );
}
