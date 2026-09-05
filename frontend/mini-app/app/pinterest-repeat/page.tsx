"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { api } from "@/lib/api";
import {
  pinterestRepeatApi,
  type PinterestRepeatQuote,
  type PinterestRepeatRequest,
  type PinterestSceneAnalysis,
} from "@/lib/pinterest-repeat-api";
import { haptic } from "@/lib/telegram";

type UploadedPhoto = { url: string; name: string };
type SubmissionIdentity = { requestKey: string; idempotencyKey: string };

function money(value?: string | null): string {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return value || "—";
  return number.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

function isImageFile(file: File): boolean {
  return file.type.startsWith("image/") || /\.(heic|heif)$/i.test(file.name);
}

function createIdempotencyKey(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") return globalThis.crypto.randomUUID();
  return `pin-${Date.now()}-${Math.random().toString(36).slice(2, 14)}`;
}

export default function PinterestRepeatPage() {
  const [reference, setReference] = useState<UploadedPhoto | null>(null);
  const [pinterestUrl, setPinterestUrl] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [identityPhotos, setIdentityPhotos] = useState<UploadedPhoto[]>([]);
  const [heightCm, setHeightCm] = useState("165");
  const [weightKg, setWeightKg] = useState("55");
  const [uploadingReference, setUploadingReference] = useState(false);
  const [uploadingIdentity, setUploadingIdentity] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [analysis, setAnalysis] = useState<PinterestSceneAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const [quoting, setQuoting] = useState(false);
  const [quote, setQuote] = useState<PinterestRepeatQuote | null>(null);
  const [quotedRequestKey, setQuotedRequestKey] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const submissionRef = useRef<SubmissionIdentity | null>(null);

  const parsedHeight = Number(heightCm);
  const parsedWeight = Number(weightKg);
  const ready = Boolean(
    reference
    && identityPhotos.length >= 1
    && identityPhotos.length <= 5
    && Number.isInteger(parsedHeight)
    && parsedHeight >= 120
    && parsedHeight <= 230
    && Number.isInteger(parsedWeight)
    && parsedWeight >= 30
    && parsedWeight <= 250,
  );

  const requestBody = useMemo<PinterestRepeatRequest | null>(() => {
    if (!reference || !ready) return null;
    return {
      scene_reference_url: reference.url,
      identity_reference_urls: identityPhotos.map((item) => item.url),
      height_cm: parsedHeight,
      weight_kg: parsedWeight,
      ...(analysis ? { scene_analysis: analysis } : {}),
    };
  }, [analysis, identityPhotos, parsedHeight, parsedWeight, ready, reference]);
  const requestKey = useMemo(() => requestBody ? JSON.stringify(requestBody) : "", [requestBody]);
  const quoteIsCurrent = Boolean(quote && requestKey && quotedRequestKey === requestKey);

  useEffect(() => {
    const imageUrl = reference?.url || "";
    setAnalysis(null);
    setAnalysisError("");
    if (!imageUrl) {
      setAnalyzing(false);
      return;
    }
    let active = true;
    setAnalyzing(true);
    void pinterestRepeatApi.analyze(imageUrl)
      .then((result) => {
        if (!active) return;
        setAnalysis(result.analysis);
        setAnalysisError("");
      })
      .catch((cause) => {
        if (!active) return;
        setAnalysis(null);
        setAnalysisError(cause instanceof Error ? cause.message : "AI-анализ сцены недоступен");
      })
      .finally(() => {
        if (active) setAnalyzing(false);
      });
    return () => {
      active = false;
    };
  }, [reference?.url]);

  useEffect(() => {
    submissionRef.current = null;
    if (!requestBody || !requestKey) {
      setQuote(null);
      setQuotedRequestKey("");
      setQuoting(false);
      return;
    }
    let active = true;
    setQuoting(true);
    setQuote(null);
    setQuotedRequestKey("");
    const timer = window.setTimeout(() => {
      void pinterestRepeatApi.quote(requestBody)
        .then((result) => {
          if (!active) return;
          setQuote(result);
          setQuotedRequestKey(requestKey);
          setError("");
        })
        .catch((cause) => {
          if (!active) return;
          setQuote(null);
          setQuotedRequestKey("");
          setError(cause instanceof Error ? cause.message : "Не удалось рассчитать стоимость");
        })
        .finally(() => {
          if (active) setQuoting(false);
        });
    }, 180);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [requestBody, requestKey]);

  const uploadReference = async (file: File | undefined) => {
    if (!file || uploadingReference) return;
    if (!isImageFile(file)) {
      setError("Выберите фотографию");
      return;
    }
    setUploadingReference(true);
    setError("");
    try {
      const result = await api.upload(file);
      setReference({ url: result.url, name: file.name });
      setPinterestUrl("");
      setSourceUrl("");
      haptic("light");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить референс");
    } finally {
      setUploadingReference(false);
    }
  };

  const resolvePinterest = async () => {
    if (!pinterestUrl.trim() || resolving) return;
    setResolving(true);
    setError("");
    try {
      const result = await pinterestRepeatApi.resolve(pinterestUrl.trim());
      setReference({ url: result.reference_url, name: "Pinterest" });
      setSourceUrl(result.source_url);
      haptic("light");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось получить фото из Pinterest");
    } finally {
      setResolving(false);
    }
  };

  const addIdentityPhotos = async (files: File[]) => {
    if (!files.length || uploadingIdentity) return;
    const remaining = Math.max(0, 5 - identityPhotos.length);
    const images = files.filter(isImageFile).slice(0, remaining);
    if (!images.length) {
      setError(identityPhotos.length >= 5 ? "Можно добавить не больше 5 фото" : "Выберите фотографии");
      return;
    }
    setUploadingIdentity(true);
    setError("");
    try {
      const uploaded: UploadedPhoto[] = [];
      for (const file of images) {
        const result = await api.upload(file);
        uploaded.push({ url: result.url, name: file.name });
      }
      setIdentityPhotos((current) => [...current, ...uploaded].slice(0, 5));
      haptic("light");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить ваши фото");
    } finally {
      setUploadingIdentity(false);
    }
  };

  const removeReference = () => {
    setReference(null);
    setSourceUrl("");
    setQuote(null);
    setQuotedRequestKey("");
  };

  const run = async () => {
    if (!requestBody || !requestKey || !quoteIsCurrent || running || analyzing) return;
    setRunning(true);
    setError("");
    haptic("medium");
    let submission = submissionRef.current;
    if (!submission || submission.requestKey !== requestKey) {
      submission = { requestKey, idempotencyKey: createIdempotencyKey() };
      submissionRef.current = submission;
    }
    try {
      const result = await pinterestRepeatApi.run(requestBody, submission.idempotencyKey);
      window.location.assign(`/mini-app/?route=history&generation=${encodeURIComponent(result.id)}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось запустить генерацию");
      setRunning(false);
    }
  };

  const primaryIdentity = identityPhotos[0] || null;
  const extraIdentityCount = Math.max(0, identityPhotos.length - 1);

  return (
    <StandaloneShell
      kicker="ПОВТОР ПО РЕФЕРЕНСУ"
      title="Повтори фото с Pinterest"
      copy="Понравилось фото? Сделаем тебя в нём — сохраним сцену, позу, свет и композицию."
    >
      <style jsx global>{`
        .pin-repeat{display:grid;gap:14px}.pin-tip{padding:14px 15px;border-radius:18px;background:#f1cf58;color:#211800;font-size:13px;font-weight:800;line-height:1.35}.pin-tip small{display:block;margin-top:4px;font-size:11px;font-weight:650;opacity:.72}.pin-pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}.pin-slot{display:grid;gap:8px}.pin-slot-head{display:flex;align-items:center;justify-content:space-between;gap:6px;min-width:0}.pin-slot-label{font-size:11px;font-weight:950;letter-spacing:.08em;color:#f2edf6}.pin-slot-pill{padding:4px 6px;border-radius:999px;background:rgba(176,79,255,.17);color:#dcb4ff;font-size:8px;font-weight:900;letter-spacing:.04em;white-space:nowrap}.pin-slot-pill.person{background:rgba(67,137,255,.16);color:#a9c9ff}.pin-media{position:relative;overflow:hidden;aspect-ratio:3/4;display:grid;place-items:center;border:1px solid rgba(255,255,255,.1);border-radius:18px;background:#0a080d;cursor:pointer}.pin-media.empty{border-style:dashed;border-color:rgba(198,121,255,.35);background:rgba(142,61,213,.06)}.pin-media input{display:none}.pin-media img{width:100%;height:100%;display:block;object-fit:cover}.pin-media-add{display:grid;gap:6px;place-items:center;padding:10px;text-align:center;color:#eee3f6;font-size:12px;font-weight:850}.pin-media-add b{font-size:25px;line-height:1}.pin-media-add small{font-size:9px;color:var(--muted);font-weight:600}.pin-remove{position:absolute;z-index:2;top:7px;right:7px;width:29px;height:29px;border:1px solid rgba(255,255,255,.18);border-radius:50%;background:rgba(6,5,8,.8);color:#fff;font-size:17px}.pin-more{position:absolute;left:8px;bottom:8px;padding:5px 8px;border-radius:999px;background:rgba(7,6,10,.78);color:#fff;font-size:10px;font-weight:850}.pin-section-label{margin-top:2px;color:#a8a0ad;font-size:10px;font-weight:900;letter-spacing:.08em}.pin-url-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px}.pin-input,.pin-number{width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.11);border-radius:15px;background:#0a080d;color:#fff;padding:12px 13px;font:inherit}.pin-input:focus,.pin-number:focus{outline:none;border-color:rgba(202,114,255,.55);box-shadow:0 0 0 3px rgba(174,76,255,.11)}.pin-url-button{border:1px solid rgba(194,113,255,.3);border-radius:15px;background:#17101f;color:#f2ddff;padding:0 13px;font-weight:850}.pin-url-button:disabled{opacity:.45}.pin-helper{margin:-1px 0 0;color:var(--muted);font-size:10px;line-height:1.42}.pin-source{display:flex;align-items:center;gap:9px;padding:11px 12px;border:1px solid rgba(255,255,255,.08);border-radius:15px;background:#0c0a0f;min-width:0}.pin-source-icon{flex:0 0 auto;width:24px;height:24px;display:grid;place-items:center;border-radius:8px;background:#df2040;color:#fff;font-size:12px;font-weight:950}.pin-source-copy{min-width:0;display:grid;gap:2px}.pin-source-copy b{font-size:9px;letter-spacing:.07em;color:#aaa1b0}.pin-source-copy span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px;color:#d6cfda}.pin-status{display:grid;gap:8px}.pin-status-line{display:flex;align-items:flex-start;gap:7px;color:#a7e6b9;font-size:11px;line-height:1.35}.pin-status-line:before{content:"";flex:0 0 auto;width:7px;height:7px;margin-top:4px;border-radius:50%;background:#50cb77}.pin-thumbs{display:flex;gap:7px;overflow-x:auto;padding-bottom:1px}.pin-thumb{position:relative;flex:0 0 48px;width:48px;height:48px;overflow:hidden;border:1px solid rgba(255,255,255,.1);border-radius:12px;background:#0a080d}.pin-thumb img{width:100%;height:100%;object-fit:cover}.pin-thumb button{position:absolute;right:2px;top:2px;width:18px;height:18px;border:0;border-radius:50%;background:rgba(0,0,0,.72);color:#fff;font-size:12px;line-height:1}.pin-thumb-add{flex:0 0 48px;width:48px;height:48px;display:grid;place-items:center;border:1px dashed rgba(194,113,255,.35);border-radius:12px;background:rgba(144,63,225,.05);color:#dfc0f7;font-size:20px;cursor:pointer}.pin-thumb-add input{display:none}.pin-count{color:var(--muted);font-size:10px}.pin-fields{display:grid;grid-template-columns:1fr 1fr;gap:9px}.pin-field{display:grid;gap:6px}.pin-field label{font-size:10px;font-weight:900;letter-spacing:.06em;color:#d9d1df}.pin-field-wrap{position:relative}.pin-field-wrap span{position:absolute;right:12px;top:50%;transform:translateY(-50%);color:#777080;font-size:10px;pointer-events:none}.pin-number{padding-right:38px}.pin-proportion-help{margin:0;color:var(--muted);font-size:10px;line-height:1.42}.pin-error{padding:11px 12px;border-radius:14px;background:rgba(255,80,120,.1);color:#ffc6d3;font-size:12px}.pin-summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 13px;border-radius:16px;background:#141019}.pin-summary span{color:var(--muted);font-size:11px}.pin-summary strong{font-size:16px}.pin-run{width:100%;min-height:53px;border:0;border-radius:17px;background:linear-gradient(135deg,#a84dff,#d66cff);color:#fff;font-weight:900;font-size:15px;box-shadow:0 14px 34px rgba(172,68,255,.24)}.pin-run:disabled{opacity:.42;box-shadow:none}.pin-footnote{margin:0;text-align:center;color:var(--muted);font-size:10px;line-height:1.4}@media(max-width:360px){.pin-pair{gap:7px}.pin-slot-pill{font-size:7px;padding:4px}.pin-media-add{font-size:11px}}@media(min-width:720px){.pin-repeat{max-width:620px}.pin-media{aspect-ratio:4/5}.pin-thumb{flex-basis:58px;width:58px;height:58px}.pin-thumb-add{flex-basis:58px;width:58px;height:58px}}
      `}</style>

      <div className="pin-repeat">
        <div className="pin-tip">
          Как получить идеальное фото?
          <small>Исходные фото сильно влияют на результат — используйте чёткие снимки без сильных фильтров.</small>
        </div>

        <div className="pin-pair">
          <section className="pin-slot" aria-label="Референс">
            <div className="pin-slot-head">
              <span className="pin-slot-label">РЕФЕРЕНС</span>
              <span className="pin-slot-pill">ОТКУДА</span>
            </div>
            {reference ? (
              <div className="pin-media">
                <img src={reference.url} alt="Референс сцены" />
                <button className="pin-remove" type="button" aria-label="Удалить референс" onClick={removeReference}>×</button>
              </div>
            ) : (
              <label className="pin-media empty">
                <input type="file" accept="image/*,.heic,.heif" onChange={(event) => void uploadReference(event.target.files?.[0])} />
                <span className="pin-media-add"><b>+</b>{uploadingReference ? "Загружаем…" : "Загрузить"}<small>фото-референс</small></span>
              </label>
            )}
          </section>

          <section className="pin-slot" aria-label="Ваши ракурсы">
            <div className="pin-slot-head">
              <span className="pin-slot-label">ТЫ</span>
              <span className="pin-slot-pill person">КОГО ВСТАВЛЯЕМ</span>
            </div>
            <label className={`pin-media ${primaryIdentity ? "" : "empty"}`}>
              <input type="file" accept="image/*,.heic,.heif" multiple onChange={(event) => void addIdentityPhotos(Array.from(event.target.files || []))} />
              {primaryIdentity ? (
                <>
                  <img src={primaryIdentity.url} alt="Ваш ракурс 1" />
                  {extraIdentityCount > 0 ? <span className="pin-more">+{extraIdentityCount} ракурса</span> : null}
                </>
              ) : (
                <span className="pin-media-add"><b>+</b>{uploadingIdentity ? "Загружаем…" : "Загрузить"}<small>1–5 ваших фото</small></span>
              )}
            </label>
          </section>
        </div>

        <div className="pin-section-label">ИЛИ ВСТАВЬ ССЫЛКУ</div>
        <div className="pin-url-row">
          <input className="pin-input" type="url" inputMode="url" placeholder="ссылка на пин с Pinterest" value={pinterestUrl} onChange={(event) => setPinterestUrl(event.target.value)} />
          <button className="pin-url-button" type="button" disabled={!pinterestUrl.trim() || resolving} onClick={() => void resolvePinterest()}>{resolving ? "…" : "Загрузить"}</button>
        </div>
        <p className="pin-helper">Вставь ссылку на пин (pinterest.com/pin/... или pin.it/...) — сами вытащим картинку и используем её как сцену.</p>

        {sourceUrl ? (
          <div className="pin-source">
            <span className="pin-source-icon">P</span>
            <span className="pin-source-copy"><b>ИСТОЧНИК</b><span>{sourceUrl}</span></span>
          </div>
        ) : null}

        {resolving ? <div className="pin-helper">Загружаем референс из Pinterest…</div> : null}
        {analyzing ? <div className="pin-helper">Разбираем сцену, позу, свет и эмоцию…</div> : null}

        {identityPhotos.length > 0 ? (
          <>
            <div className="pin-thumbs" aria-label="Ваши загруженные ракурсы">
              {identityPhotos.map((photo, index) => (
                <div className="pin-thumb" key={`${photo.url}-${index}`}>
                  <img src={photo.url} alt={`Ваш ракурс ${index + 1}`} />
                  <button type="button" aria-label={`Удалить ракурс ${index + 1}`} onClick={() => setIdentityPhotos((current) => current.filter((_, currentIndex) => currentIndex !== index))}>×</button>
                </div>
              ))}
              {identityPhotos.length < 5 ? (
                <label className="pin-thumb-add" aria-label="Добавить свои фото">
                  <input type="file" accept="image/*,.heic,.heif" multiple onChange={(event) => void addIdentityPhotos(Array.from(event.target.files || []))} />
                  <span>{uploadingIdentity ? "…" : "+"}</span>
                </label>
              ) : null}
            </div>
            <div className="pin-count">1–5 ракурсов одного человека · сейчас {identityPhotos.length}/5</div>
          </>
        ) : null}

        {analysis ? (
          <div className="pin-status">
            <div className="pin-status-line">сцена, свет и поза считаны с референса</div>
            <div className="pin-status-line">эмоция: {analysis.expression} · взгляд: {analysis.gaze}</div>
            <div className="pin-status-line">камера: {analysis.camera}</div>
          </div>
        ) : null}
        {reference && analysisError && !analyzing ? (
          <div className="pin-helper">AI-разбор недоступен — повторим сцену напрямую по референсу.</div>
        ) : null}

        <div className="pin-fields">
          <div className="pin-field">
            <label htmlFor="pin-height">РОСТ</label>
            <div className="pin-field-wrap"><input id="pin-height" aria-label="Рост" className="pin-number" type="number" min={120} max={230} step={1} value={heightCm} onChange={(event) => setHeightCm(event.target.value)} /><span>см</span></div>
          </div>
          <div className="pin-field">
            <label htmlFor="pin-weight">ВЕС</label>
            <div className="pin-field-wrap"><input id="pin-weight" aria-label="Вес" className="pin-number" type="number" min={30} max={250} step={1} value={weightKg} onChange={(event) => setWeightKg(event.target.value)} /><span>кг</span></div>
          </div>
        </div>
        <p className="pin-proportion-help">Рост и вес нужны, чтобы руки, шея и пропорции тела совпали с тобой. Основную форму тела модель берёт с твоих фото.</p>

        {error ? <div className="pin-error" role="alert">{error}</div> : null}

        <div className="pin-summary">
          <span>Стоимость · формат наследуется с референса</span>
          <strong>{quoting || (requestBody && !quoteIsCurrent) ? "Считаем…" : quoteIsCurrent && quote ? (quote.admin_free ? "Бесплатно" : `${money(quote.effective_cost_rox)} ROX`) : "—"}</strong>
        </div>
        <button className="pin-run" type="button" disabled={!requestBody || !quoteIsCurrent || quoting || running || analyzing || uploadingReference || uploadingIdentity || resolving} onClick={() => void run()}>{running ? "Создаём…" : analyzing ? "Разбираем референс…" : "Создать →"}</button>
        <p className="pin-footnote">После запуска задача появится в истории. Можно закрыть Mini App — генерация продолжится на сервере.</p>
      </div>
    </StandaloneShell>
  );
}
