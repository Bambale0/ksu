"use client";

import { useEffect, useMemo, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { api } from "@/lib/api";
import type { TrendItem } from "@/lib/types";

function trendId(): string {
  if (typeof window === "undefined") return "";
  return new URL(window.location.href).searchParams.get("id") || "";
}

function money(value?: string | null): string {
  if (!value) return "—";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) : value;
}

function previewIsVideo(trend: TrendItem): boolean {
  if (trend.media_type === "video") return true;
  return /\.(mp4|webm|mov|m4v)(?:[?#]|$)/i.test(trend.preview_url || "");
}

export default function TrendPage() {
  const [trend, setTrend] = useState<TrendItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);
  const [references, setReferences] = useState<Array<{ url: string; name: string }>>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const id = trendId();
    if (!id) {
      setError("Тренд не выбран");
      setLoading(false);
      return;
    }
    void api.trend(id)
      .then(setTrend)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Не удалось открыть тренд"))
      .finally(() => setLoading(false));
  }, []);

  const minimum = Number(trend?.reference_requirements?.min || 0);
  const maximum = Math.max(minimum, Number(trend?.reference_requirements?.max || minimum || 0));
  const ready = references.length >= minimum && (!maximum || references.length <= maximum);
  const referenceCopy = useMemo(() => {
    if (!trend) return "";
    if (!minimum) return "Референсы не нужны — сценарий можно запустить сразу.";
    if (minimum === maximum) return `Добавьте ${minimum} ${minimum === 1 ? "изображение" : "изображения"}. Генерация начнётся только после нажатия кнопки.`;
    return `Добавьте от ${minimum} до ${maximum} изображений. Генерация начнётся только после нажатия кнопки.`;
  }, [maximum, minimum, trend]);

  const addFiles = async (files: File[]) => {
    if (!trend || !files.length) return;
    const available = Math.max(0, maximum - references.length);
    if (!available) {
      setError(`Максимум ${maximum} референсов`);
      return;
    }
    setUploading(true);
    setError("");
    try {
      const next: Array<{ url: string; name: string }> = [];
      for (const file of files.filter((item) => item.type.startsWith("image/")).slice(0, available)) {
        const uploaded = await api.upload(file);
        next.push({ url: uploaded.url, name: file.name });
      }
      setReferences((current) => [...current, ...next].slice(0, maximum));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить референс");
    } finally {
      setUploading(false);
    }
  };

  const run = async () => {
    if (!trend || !ready || running) return;
    setRunning(true);
    setError("");
    try {
      const result = await api.runTrend(trend.id, references.map((item) => item.url));
      window.location.assign(`/mini-app/?route=history&generation=${encodeURIComponent(result.id)}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось запустить тренд");
      setRunning(false);
    }
  };

  return (
    <StandaloneShell
      kicker="Тренд"
      title={trend?.title || (loading ? "Загружаю сценарий" : "Тренд")}
      copy={trend?.description || "Готовый сценарий ROXY с описанием и настройками."}
    >
      {trend ? (
        <div className="tool-grid">
          {trend.preview_url ? previewIsVideo(trend)
            ? <video className="trend-preview" src={trend.preview_url} muted autoPlay loop playsInline controls preload="metadata" />
            : <img className="trend-preview" src={trend.preview_url} alt={trend.title} />
            : null}
          <div className="panel tool-panel">
            <div className="trend-meta">
              <span>{trend.model?.title || "ROXY model"}</span>
              <span>{trend.admin_free ? "Бесплатно" : `${money(trend.cost_rox)} ROX`}</span>
              {trend.billing_seconds ? <span>{trend.billing_seconds} сек</span> : null}
            </div>
            <p className="muted">{referenceCopy}</p>

            {minimum > 0 ? (
              <>
                <label className="upload-control">
                  <span>{uploading ? "Загружаю…" : references.length ? `Добавлено ${references.length}/${maximum}` : "Добавить референсы"}</span>
                  <input
                    type="file"
                    accept="image/*"
                    multiple={maximum > 1}
                    disabled={uploading || references.length >= maximum}
                    onChange={(event) => {
                      const files = Array.from(event.target.files || []);
                      event.target.value = "";
                      void addFiles(files);
                    }}
                  />
                </label>
                <div className="tool-file-list">
                  {references.map((item, index) => (
                    <div className="tool-file-chip" key={`${item.url}-${index}`}>
                      <span>{item.name || `Референс ${index + 1}`}</span>
                      <button type="button" aria-label={`Удалить референс ${index + 1}`} onClick={() => setReferences((current) => current.filter((_, i) => i !== index))}>×</button>
                    </div>
                  ))}
                </div>
              </>
            ) : null}

            {error ? <div className="action-error" role="alert">{error}</div> : null}
            <button className="primary wide" type="button" disabled={!ready || uploading || running} onClick={() => void run()}>
              {running ? "Запускаю…" : trend.admin_free ? "Сгенерировать бесплатно" : `Сгенерировать · ${money(trend.cost_rox)} ROX`}
            </button>
          </div>
        </div>
      ) : error ? <div className="action-error" role="alert">{error}</div> : <div className="panel"><p className="muted">Загрузка…</p></div>}
    </StandaloneShell>
  );
}
