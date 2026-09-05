"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { api } from "@/lib/api";
import {
  pinterestRepeatApi,
  type PinterestRepeatQuote,
  type PinterestRepeatRequest,
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
  const [identityPhotos, setIdentityPhotos] = useState<UploadedPhoto[]>([]);
  const [heightCm, setHeightCm] = useState("165");
  const [weightKg, setWeightKg] = useState("55");
  const [expression, setExpression] = useState("");
  const [uploadingReference, setUploadingReference] = useState(false);
  const [uploadingIdentity, setUploadingIdentity] = useState(false);
  const [resolving, setResolving] = useState(false);
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
      expression: expression.trim() || undefined,
    };
  }, [expression, identityPhotos, parsedHeight, parsedWeight, ready, reference]);
  const requestKey = useMemo(() => requestBody ? JSON.stringify(requestBody) : "", [requestBody]);
  const quoteIsCurrent = Boolean(quote && requestKey && quotedRequestKey === requestKey);

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

  const run = async () => {
    if (!requestBody || !requestKey || !quoteIsCurrent || running) return;
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
      // Keep the key for this exact request: a retry after a lost/timeout response
      // must replay the same paid generation rather than creating a second one.
      setError(cause instanceof Error ? cause.message : "Не удалось запустить генерацию");
      setRunning(false);
    }
  };

  return (
    <StandaloneShell
      kicker="ПОВТОР ФОТО"
      title="Повтори фото с Pinterest"
      copy="Дайте референс и свои ракурсы — ROXY сохранит сцену, свет и позу, но заменит человека на вас."
    >
      <style jsx global>{`
        .pin-repeat{display:grid;gap:16px}.pin-repeat-panel{display:grid;gap:14px;padding:18px;border:1px solid rgba(255,255,255,.09);border-radius:25px;background:#0f0c14;box-shadow:inset 0 1px 0 rgba(255,255,255,.03)}.pin-repeat-title{display:flex;align-items:flex-start;gap:11px}.pin-repeat-step{flex:0 0 auto;width:29px;height:29px;display:grid;place-items:center;border-radius:10px;background:rgba(176,79,255,.18);color:#ebd4ff;font-size:13px;font-weight:900}.pin-repeat-title h2{margin:1px 0 4px;font-size:21px;line-height:1.08}.pin-repeat-title p{margin:0;color:var(--muted);font-size:13px;line-height:1.4}.pin-reference-preview{position:relative;overflow:hidden;min-height:260px;aspect-ratio:3/4;border-radius:20px;border:1px solid rgba(204,135,255,.26);background:#08070b}.pin-reference-preview img{width:100%;height:100%;display:block;object-fit:cover}.pin-reference-remove,.pin-photo-remove{position:absolute;top:8px;right:8px;width:32px;height:32px;border:1px solid rgba(255,255,255,.18);border-radius:50%;background:rgba(5,4,8,.78);color:#fff;font-size:19px}.pin-upload{min-height:150px;display:grid;place-items:center;padding:18px;border:1px dashed rgba(204,135,255,.4);border-radius:20px;background:rgba(144,63,225,.07);color:#ead5fb;text-align:center;font-weight:850;cursor:pointer}.pin-upload input{display:none}.pin-upload small{display:block;margin-top:7px;color:var(--muted);font-weight:500;line-height:1.35}.pin-or{display:flex;align-items:center;gap:10px;color:#756d7e;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}.pin-or:before,.pin-or:after{content:"";height:1px;flex:1;background:rgba(255,255,255,.08)}.pin-url-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:9px}.pin-input,.pin-number{width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.11);border-radius:16px;background:#08070b;color:#fff;padding:13px 14px;font:inherit}.pin-input:focus,.pin-number:focus{outline:none;border-color:rgba(202,114,255,.55);box-shadow:0 0 0 3px rgba(174,76,255,.11)}.pin-url-button{border:1px solid rgba(194,113,255,.3);border-radius:16px;background:#17101f;color:#f2ddff;padding:0 14px;font-weight:850}.pin-url-button:disabled{opacity:.45}.pin-photo-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.pin-photo{position:relative;overflow:hidden;aspect-ratio:1/1;border:1px solid rgba(255,255,255,.1);border-radius:16px;background:#08070b}.pin-photo img{width:100%;height:100%;object-fit:cover}.pin-photo-add{aspect-ratio:1/1;display:grid;place-items:center;border:1px dashed rgba(204,135,255,.34);border-radius:16px;background:rgba(144,63,225,.06);color:#e8ccff;font-size:28px;cursor:pointer}.pin-photo-add input{display:none}.pin-count{color:var(--muted);font-size:12px}.pin-fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}.pin-field{display:grid;gap:7px}.pin-field label{font-size:12px;font-weight:850;color:#d9d1df}.pin-field-wrap{position:relative}.pin-field-wrap span{position:absolute;right:13px;top:50%;transform:translateY(-50%);color:#777080;font-size:12px;pointer-events:none}.pin-number{padding-right:42px}.pin-expression{display:grid;gap:7px}.pin-expression label{font-size:12px;font-weight:850;color:#d9d1df}.pin-expression textarea{width:100%;box-sizing:border-box;min-height:92px;resize:vertical;border:1px solid rgba(255,255,255,.11);border-radius:16px;background:#08070b;color:#fff;padding:13px 14px;font:inherit;line-height:1.45}.pin-expression textarea:focus{outline:none;border-color:rgba(202,114,255,.55);box-shadow:0 0 0 3px rgba(174,76,255,.11)}.pin-hint{margin:0;color:var(--muted);font-size:11px;line-height:1.4}.pin-summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px;border-radius:17px;background:#141019}.pin-summary span{color:var(--muted);font-size:12px}.pin-summary strong{font-size:17px}.pin-error{padding:12px 13px;border-radius:14px;background:rgba(255,80,120,.1);color:#ffc6d3;font-size:13px}.pin-run{width:100%;min-height:55px;border:0;border-radius:18px;background:linear-gradient(135deg,#a84dff,#d66cff);color:#fff;font-weight:900;font-size:16px;box-shadow:0 14px 34px rgba(172,68,255,.24)}.pin-run:disabled{opacity:.42;box-shadow:none}.pin-footnote{margin:0;text-align:center;color:var(--muted);font-size:11px;line-height:1.4}@media(min-width:720px){.pin-photo-grid{grid-template-columns:repeat(5,minmax(0,1fr))}.pin-reference-preview{max-width:390px}.pin-repeat-panel.reference{grid-template-columns:minmax(0,390px) minmax(0,1fr);align-items:start}.pin-repeat-panel.reference>.pin-repeat-title{grid-column:1/-1}}
      `}</style>

      <div className="pin-repeat">
        <section className="pin-repeat-panel reference">
          <div className="pin-repeat-title">
            <span className="pin-repeat-step">1</span>
            <div><h2>Референс</h2><p>Дайте 1 фото — повторим сцену, свет, композицию и позу.</p></div>
          </div>

          {reference ? (
            <div className="pin-reference-preview">
              <img src={reference.url} alt="Референс сцены" />
              <button className="pin-reference-remove" type="button" aria-label="Удалить референс" onClick={() => { setReference(null); setQuote(null); setQuotedRequestKey(""); }}>×</button>
            </div>
          ) : (
            <label className="pin-upload">
              <input type="file" accept="image/*,.heic,.heif" onChange={(event) => void uploadReference(event.target.files?.[0])} />
              <span>{uploadingReference ? "Загружаем…" : "+ Загрузить фото"}<small>JPEG, PNG, WEBP, HEIC — один исходный кадр</small></span>
            </label>
          )}

          <div style={{ display: "grid", gap: 11 }}>
            <div className="pin-or">или ссылка Pinterest</div>
            <div className="pin-url-row">
              <input className="pin-input" type="url" inputMode="url" placeholder="https://pin.it/…" value={pinterestUrl} onChange={(event) => setPinterestUrl(event.target.value)} />
              <button className="pin-url-button" type="button" disabled={!pinterestUrl.trim() || resolving} onClick={() => void resolvePinterest()}>{resolving ? "…" : "Загрузить"}</button>
            </div>
            <p className="pin-hint">Ссылка используется только как источник референса. Личность с Pinterest в результат не переносится.</p>
          </div>
        </section>

        <section className="pin-repeat-panel">
          <div className="pin-repeat-title">
            <span className="pin-repeat-step">2</span>
            <div><h2>Ваши ракурсы</h2><p>Добавьте от 1 до 5 фото одного человека. Чем разнообразнее ракурсы, тем стабильнее внешность.</p></div>
          </div>
          <div className="pin-photo-grid">
            {identityPhotos.map((photo, index) => (
              <div className="pin-photo" key={`${photo.url}-${index}`}>
                <img src={photo.url} alt={`Ваш ракурс ${index + 1}`} />
                <button className="pin-photo-remove" type="button" aria-label={`Удалить ракурс ${index + 1}`} onClick={() => setIdentityPhotos((current) => current.filter((_, currentIndex) => currentIndex !== index))}>×</button>
              </div>
            ))}
            {identityPhotos.length < 5 ? (
              <label className="pin-photo-add" aria-label="Добавить свои фото">
                <input type="file" accept="image/*,.heic,.heif" multiple onChange={(event) => void addIdentityPhotos(Array.from(event.target.files || []))} />
                <span>{uploadingIdentity ? "…" : "+"}</span>
              </label>
            ) : null}
          </div>
          <div className="pin-count">{identityPhotos.length}/5 фото</div>
        </section>

        <section className="pin-repeat-panel">
          <div className="pin-repeat-title">
            <span className="pin-repeat-step">3</span>
            <div><h2>Пропорции и выражение</h2><p>Эти параметры помогают не менять вашу фигуру и настроение кадра.</p></div>
          </div>
          <div className="pin-fields">
            <div className="pin-field">
              <label htmlFor="pin-height">Рост</label>
              <div className="pin-field-wrap"><input id="pin-height" className="pin-number" type="number" min={120} max={230} step={1} value={heightCm} onChange={(event) => setHeightCm(event.target.value)} /><span>см</span></div>
            </div>
            <div className="pin-field">
              <label htmlFor="pin-weight">Вес</label>
              <div className="pin-field-wrap"><input id="pin-weight" className="pin-number" type="number" min={30} max={250} step={1} value={weightKg} onChange={(event) => setWeightKg(event.target.value)} /><span>кг</span></div>
            </div>
          </div>
          <p className="pin-hint">Рост и вес — мягкая подсказка модели. Основные пропорции берём с ваших фотографий.</p>
          <div className="pin-expression">
            <label htmlFor="pin-expression">Желаемое выражение лица</label>
            <textarea id="pin-expression" maxLength={240} placeholder="Например: спокойная уверенность" value={expression} onChange={(event) => setExpression(event.target.value)} />
          </div>
        </section>

        {error ? <div className="pin-error" role="alert">{error}</div> : null}

        <div className="pin-summary">
          <span>Стоимость</span>
          <strong>{quoting || (requestBody && !quoteIsCurrent) ? "Считаем…" : quoteIsCurrent && quote ? (quote.admin_free ? "Бесплатно" : `${money(quote.effective_cost_rox)} ROX`) : "—"}</strong>
        </div>
        <button className="pin-run" type="button" disabled={!requestBody || !quoteIsCurrent || quoting || running || uploadingReference || uploadingIdentity || resolving} onClick={() => void run()}>{running ? "Создаём…" : "Создать"}</button>
        <p className="pin-footnote">После запуска задача появится в истории. Можно закрыть Mini App — генерация продолжится на сервере.</p>
      </div>
    </StandaloneShell>
  );
}