"use client";

import { useEffect, useMemo, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { haptic, initTelegram, notify, telegramHeaders } from "@/lib/telegram";
import type { TrendItem } from "@/lib/types";

type UploadResult = { url: string; name?: string };
type RunResult = {
  id: string;
  task_id?: string;
  status: string;
  cost_rox?: string;
  result_url?: string | null;
};

type UploadedRef = { url: string; name: string };

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      ...telegramHeaders(Boolean(init.body) && !isForm),
      ...(init.headers || {}),
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail ?? payload?.message ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload as T;
}

async function uploadImage(file: File): Promise<UploadedRef> {
  if (!file.type.startsWith("image/")) throw new Error(`${file.name}: нужен файл изображения`);
  const form = new FormData();
  form.append("file", file, file.name);
  const uploaded = await request<UploadResult>("/api/v1/uploads/kie", { method: "POST", body: form });
  return { url: uploaded.url, name: uploaded.name || file.name };
}

function serviceIdFromLocation(): string {
  if (typeof window === "undefined") return "";
  return new URL(window.location.href).searchParams.get("id") || "";
}

export default function PinterestFlowPage() {
  const [serviceId, setServiceId] = useState("");
  const [service, setService] = useState<TrendItem | null>(null);
  const [scene, setScene] = useState<UploadedRef | null>(null);
  const [identity, setIdentity] = useState<UploadedRef | null>(null);
  const [extras, setExtras] = useState<UploadedRef[]>([]);
  const [heightCm, setHeightCm] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [uploading, setUploading] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<RunResult | null>(null);

  useEffect(() => {
    initTelegram();
    const id = serviceIdFromLocation();
    setServiceId(id);
    if (!id) {
      setError("Pinterest Flow не выбран");
      return;
    }
    let active = true;
    request<TrendItem>(`/api/v1/services/pinterest/${encodeURIComponent(id)}`)
      .then((item) => active && setService(item))
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "Не удалось открыть Pinterest Flow"));
    return () => { active = false; };
  }, []);

  const height = Number(heightCm);
  const weight = Number(weightKg);
  const canRun = useMemo(
    () => Boolean(
      serviceId
      && scene
      && identity
      && height >= 120
      && height <= 230
      && weight >= 30
      && weight <= 250
      && confirmed
      && !uploading
      && !submitting,
    ),
    [confirmed, height, identity, scene, serviceId, submitting, uploading, weight],
  );

  const pickSingle = async (kind: "scene" | "identity", file?: File) => {
    if (!file) return;
    setUploading(kind);
    setError("");
    try {
      const uploaded = await uploadImage(file);
      if (kind === "scene") setScene(uploaded);
      else setIdentity(uploaded);
      notify("success");
      haptic("light");
    } catch (reason) {
      notify("error");
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить изображение");
    } finally {
      setUploading("");
    }
  };

  const pickExtras = async (files: File[]) => {
    const remaining = Math.max(0, 5 - extras.length);
    if (!remaining || !files.length) return;
    setUploading("extras");
    setError("");
    try {
      const next: UploadedRef[] = [];
      for (const file of files.slice(0, remaining)) next.push(await uploadImage(file));
      setExtras((current) => [...current, ...next].slice(0, 5));
      notify("success");
      haptic("light");
    } catch (reason) {
      notify("error");
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить дополнительные ракурсы");
    } finally {
      setUploading("");
    }
  };

  const run = async () => {
    if (!canRun || !scene || !identity) return;
    setSubmitting(true);
    setResult(null);
    setError("");
    try {
      const payload = await request<RunResult>(`/api/v1/services/pinterest/${encodeURIComponent(serviceId)}/run`, {
        method: "POST",
        body: JSON.stringify({
          reference_urls: [scene.url, identity.url, ...extras.map((item) => item.url)],
          height_cm: height,
          weight_kg: weight,
          confirmed: true,
        }),
      });
      setResult(payload);
      notify("success");
      haptic("medium");
    } catch (reason) {
      notify("error");
      setError(reason instanceof Error ? reason.message : "Не удалось запустить Pinterest Flow");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <StandaloneShell
      kicker="ROXY SERVICES · PINTEREST"
      title={service?.title || "Pinterest AI"}
      copy="Сцена остаётся сценой, а твои фото отвечают только за личность. ROXY не смешивает роли референсов."
    >
      <div className="pinterest-flow-stack">
        {service?.preview_url ? (
          <div className="pinterest-service-preview">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={service.preview_url} alt={service.title || "Pinterest reference"} />
            <span className="service-new-badge">НОВИНКА</span>
          </div>
        ) : null}

        <section className="pinterest-step">
          <div className="pinterest-step-head"><span>1</span><div><h2>Сцена из Pinterest</h2><p>Фото, композицию и атмосферу которого хочешь повторить.</p></div></div>
          <label className={`pinterest-upload ${scene ? "is-ready" : ""}`}>
            <input type="file" accept="image/*" onChange={(event) => void pickSingle("scene", event.target.files?.[0])} />
            <strong>{uploading === "scene" ? "Загружаю…" : scene ? "Сцена загружена" : "Загрузить сцену"}</strong>
            <small>{scene?.name || "Image 1 · scene reference"}</small>
          </label>
        </section>

        <section className="pinterest-step">
          <div className="pinterest-step-head"><span>2</span><div><h2>Ты — лицо и тело</h2><p>Основное фото, по которому ROXY сохранит твою внешность.</p></div></div>
          <label className={`pinterest-upload ${identity ? "is-ready" : ""}`}>
            <input type="file" accept="image/*" onChange={(event) => void pickSingle("identity", event.target.files?.[0])} />
            <strong>{uploading === "identity" ? "Загружаю…" : identity ? "Фото личности загружено" : "Загрузить своё фото"}</strong>
            <small>{identity?.name || "Image 2 · identity master"}</small>
          </label>
        </section>

        <section className="pinterest-step">
          <div className="pinterest-step-head"><span>+</span><div><h2>Дополнительные ракурсы</h2><p>Необязательно. До 5 фото того же человека для более стабильной внешности.</p></div></div>
          <label className="pinterest-upload pinterest-upload-secondary">
            <input
              type="file"
              accept="image/*"
              multiple
              disabled={extras.length >= 5 || Boolean(uploading)}
              onChange={(event) => void pickExtras(Array.from(event.target.files || []))}
            />
            <strong>{uploading === "extras" ? "Загружаю…" : extras.length >= 5 ? "Добавлено 5 из 5" : "Добавить ракурсы"}</strong>
            <small>{extras.length ? `${extras.length} из 5 добавлено` : "Images 3–7 · supporting identity"}</small>
          </label>
          {extras.length ? (
            <div className="pinterest-ref-chips">
              {extras.map((item, index) => (
                <button key={`${item.url}-${index}`} type="button" onClick={() => setExtras((current) => current.filter((_, i) => i !== index))}>
                  Ракурс {index + 1} ×
                </button>
              ))}
            </div>
          ) : null}
        </section>

        <section className="pinterest-step pinterest-body-step">
          <div className="pinterest-step-head"><span>3</span><div><h2>Рост и вес</h2><p>Нужны для реалистичных пропорций тела, а не для изменения внешности.</p></div></div>
          <div className="pinterest-measure-grid">
            <label><span>Рост, см</span><input inputMode="numeric" type="number" min={120} max={230} value={heightCm} onChange={(event) => setHeightCm(event.target.value)} placeholder="175" /></label>
            <label><span>Вес, кг</span><input inputMode="numeric" type="number" min={30} max={250} value={weightKg} onChange={(event) => setWeightKg(event.target.value)} placeholder="70" /></label>
          </div>
        </section>

        <label className="pinterest-consent">
          <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
          <span>Подтверждаю, что на identity-фото изображён я или у меня есть право использовать эти изображения.</span>
        </label>

        {error ? <div className="service-error" role="alert">{error}</div> : null}

        <button type="button" className="service-primary-button pinterest-run" disabled={!canRun} onClick={() => void run()}>
          <span>{submitting ? "Запускаю…" : "Сгенерировать"}</span>
          {service?.cost_rox ? <strong>{service.cost_rox} ROX</strong> : null}
        </button>

        {result ? (
          <div className="pinterest-success" role="status">
            <strong>Генерация запущена</strong>
            <p>Задача #{result.task_id || result.id} уже в очереди. Результат появится в истории и профиле.</p>
            <button type="button" onClick={() => window.location.assign("/mini-app/?route=history")}>Открыть историю</button>
          </div>
        ) : null}
      </div>
    </StandaloneShell>
  );
}
