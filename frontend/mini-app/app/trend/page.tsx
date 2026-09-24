"use client";

import { useEffect, useMemo, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { api } from "@/lib/api";
import { copyToClipboard, haptic, notify, openTelegramShare } from "@/lib/telegram";
import { trendUsageLabel } from "@/lib/trend-usage";
import type { TrendItem, TrendQualityOption, TrendUserField } from "@/lib/types";
import styles from "./trend.module.css";

const TREND_USER_NUMBER_RE = /^-?\d+(?:[.,]\d+)?$/;

function trendId(): string {
  if (typeof window === "undefined") return "";
  return new URL(window.location.href).searchParams.get("id") || "";
}

function money(value?: string | null): string {
  if (!value) return "—";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) : value;
}

function userFieldValid(field: TrendUserField, value: string): boolean {
  const clean = value.trim();
  if (!clean) return field.required === false;
  if (field.type === "number") return TREND_USER_NUMBER_RE.test(clean);
  return clean.length <= Math.max(1, Math.min(160, field.max_length || 160));
}

function previewIsVideo(trend: TrendItem): boolean {
  if (trend.media_type === "video") return true;
  return /\.(mp4|webm|mov|m4v)(?:[?#]|$)/i.test(trend.preview_url || "");
}

function defaultQualityValue(trend: TrendItem): string {
  const options = trend.quality_options || [];
  return options.find((option) => option.default)?.value || options[0]?.value || "";
}

function optionPriceLabel(option: TrendQualityOption): string {
  const value = option.admin_free ? option.retail_cost_rox || option.cost_rox : option.cost_rox;
  return value ? `${money(value)} ROX` : "";
}

type ReferenceKind = "image" | "video" | "audio";
type ReferenceRequirement = { min: number; max: number };

function referenceRequirement(trend: TrendItem | null, kind: ReferenceKind): ReferenceRequirement {
  const typed = trend?.reference_requirements?.[kind];
  if (typed) {
    const min = Math.max(0, Number(typed.min || 0));
    return { min, max: Math.max(min, Number(typed.max ?? min)) };
  }
  if (kind === "image") {
    const min = Math.max(0, Number(trend?.reference_requirements?.min || 0));
    return { min, max: Math.max(min, Number(trend?.reference_requirements?.max ?? min)) };
  }
  return { min: 0, max: 0 };
}

function requirementPart(kind: ReferenceKind, requirement: ReferenceRequirement): string {
  if (!requirement.max) return "";
  const label = kind === "image" ? "фото" : kind === "video" ? "видео" : "аудио";
  return requirement.min === requirement.max
    ? `${requirement.min} ${label}`
    : `${requirement.min}–${requirement.max} ${label}`;
}

export default function TrendPage() {
  const [trend, setTrend] = useState<TrendItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [copying, setCopying] = useState(false);
  const [references, setReferences] = useState<Array<{ url: string; name: string; kind: "image" | "video" | "audio" }>>([]);
  const [userValues, setUserValues] = useState<Record<string, string>>({});
  const [selectedQuality, setSelectedQuality] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const id = trendId();
    if (!id) {
      setError("Тренд не выбран");
      setLoading(false);
      return;
    }
    void api.trend(id)
      .then((item) => {
        setTrend(item);
        setUserValues(Object.fromEntries((item.user_fields || []).slice(0, 6).map((field) => [field.key, ""])));
        setSelectedQuality(defaultQualityValue(item));
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Не удалось открыть тренд"))
      .finally(() => setLoading(false));
  }, []);

  const imageRequirement = referenceRequirement(trend, "image");
  const videoRequirement = referenceRequirement(trend, "video");
  const audioRequirement = referenceRequirement(trend, "audio");
  const requirements: Record<ReferenceKind, ReferenceRequirement> = {
    image: imageRequirement,
    video: videoRequirement,
    audio: audioRequirement,
  };
  const userFields = (trend?.user_fields || []).slice(0, 6);
  const qualityOptions = trend?.quality_options || [];
  const chosenQuality = qualityOptions.find((option) => option.value === selectedQuality) || qualityOptions.find((option) => option.default) || qualityOptions[0] || null;
  const displayedCost = chosenQuality?.cost_rox || trend?.cost_rox;
  const displayedRetailCost = chosenQuality?.retail_cost_rox || trend?.retail_cost_rox;
  const adminFree = Boolean(chosenQuality?.admin_free ?? trend?.admin_free);
  const userFieldsReady = userFields.every((field) => userFieldValid(field, userValues[field.key] || ""));
  const referenceCount = (kind: ReferenceKind) => references.filter((item) => item.kind === kind).length;
  const referencesReady = (Object.keys(requirements) as ReferenceKind[]).every((kind) => {
    const count = referenceCount(kind);
    const requirement = requirements[kind];
    return count >= requirement.min && count <= requirement.max;
  });
  const ready = referencesReady && userFieldsReady;
  const referenceCopy = useMemo(() => {
    if (!trend) return "";
    const parts = (["image", "video", "audio"] as ReferenceKind[])
      .map((kind) => requirementPart(kind, referenceRequirement(trend, kind)))
      .filter(Boolean);
    if (!parts.length) return "Референсы не нужны — сценарий можно запустить сразу.";
    return `Добавьте ${parts.join(" + ")}. Генерация начнётся только после нажатия кнопки.`;
  }, [trend]);

  const addFiles = async (files: File[], kind: ReferenceKind) => {
    if (!trend || !files.length) return;
    const requirement = requirements[kind];
    const currentCount = referenceCount(kind);
    const available = Math.max(0, requirement.max - currentCount);
    if (!available) {
      setError(`Лимит для этого типа референса: ${requirement.max}`);
      return;
    }
    setUploading(true);
    setError("");
    try {
      const next: Array<{ url: string; name: string; kind: ReferenceKind }> = [];
      for (const file of files.filter((item) => item.type.startsWith(`${kind}/`)).slice(0, available)) {
        const uploaded = await api.upload(file);
        next.push({ url: uploaded.url, name: file.name, kind });
      }
      setReferences((current) => [...current, ...next]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить референс");
    } finally {
      setUploading(false);
    }
  };

  const share = async () => {
    if (!trend || sharing) return;
    setSharing(true);
    setError("");
    haptic("light");
    try {
      const result = await api.shareTrend(trend.id);
      openTelegramShare(result.share_url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось поделиться трендом");
    } finally {
      setSharing(false);
    }
  };

  const copyLink = async () => {
    if (!trend || copying) return;
    setCopying(true);
    setError("");
    try {
      const result = await api.shareTrend(trend.id);
      const copied = await copyToClipboard(result.copy_link || result.link);
      if (!copied) throw new Error("Не удалось скопировать ссылку тренда");
      notify("success");
      haptic("light");
    } catch (reason) {
      notify("error");
      setError(reason instanceof Error ? reason.message : "Не удалось скопировать ссылку тренда");
    } finally {
      setCopying(false);
    }
  };

  const run = async () => {
    if (!trend || !ready || running) return;
    setRunning(true);
    setError("");
    try {
      const multimodal = videoRequirement.max > 0 || audioRequirement.max > 0;
      const result = await api.runTrend(
        trend.id,
        multimodal
          ? {
              image_reference_urls: references.filter((item) => item.kind === "image").map((item) => item.url),
              video_reference_urls: references.filter((item) => item.kind === "video").map((item) => item.url),
              audio_reference_urls: references.filter((item) => item.kind === "audio").map((item) => item.url),
            }
          : references.filter((item) => item.kind === "image").map((item) => item.url),
        userValues,
        chosenQuality ? { resolution: chosenQuality.value } : {},
      );
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
              <span>{trendUsageLabel(trend.usage_count)}</span>
              <span>{trend.model?.title || "ROXY model"}</span>
              <span>{adminFree ? "Бесплатно" : `${money(displayedCost)} ROX`}</span>
              {trend.billing_seconds ? <span>{trend.billing_seconds} сек</span> : null}
              {chosenQuality ? <span>{chosenQuality.label || chosenQuality.value}</span> : null}
            </div>
            {qualityOptions.length > 1 ? (
              <section className={styles.quality} aria-label="Качество видео">
                <div className={styles.qualityHead}>
                  <strong>Качество видео</strong>
                  {adminFree && displayedRetailCost ? <span>обычно {money(displayedRetailCost)} ROX</span> : null}
                </div>
                <div className={styles.qualityOptions} role="radiogroup" aria-label="Качество видео">
                  {qualityOptions.map((option) => {
                    const active = option.value === chosenQuality?.value;
                    const price = optionPriceLabel(option);
                    return (
                      <button
                        key={option.value}
                        type="button"
                        className={active ? "active" : ""}
                        role="radio"
                        aria-checked={active}
                        onClick={() => {
                          haptic("light");
                          setSelectedQuality(option.value);
                        }}
                      >
                        <span>{option.label || option.value}</span>
                        {price ? <small>{price}</small> : null}
                      </button>
                    );
                  })}
                </div>
              </section>
            ) : null}
            <p className="muted">{referenceCopy}</p>

            {(Object.keys(requirements) as ReferenceKind[]).some((kind) => requirements[kind].max > 0) ? (
              <>
                {(Object.keys(requirements) as ReferenceKind[]).map((kind) => {
                  const requirement = requirements[kind];
                  if (!requirement.max) return null;
                  const count = referenceCount(kind);
                  const title = kind === "image" ? "Фото" : kind === "video" ? "Видео" : "Аудио";
                  return (
                    <label className="upload-control" key={kind}>
                      <span>
                        {uploading
                          ? "Загружаю…"
                          : count
                            ? `${title}: добавлено ${count}/${requirement.max}`
                            : `Добавить ${title.toLowerCase()}`}
                      </span>
                      <input
                        type="file"
                        accept={`${kind}/*`}
                        multiple={requirement.max > 1}
                        disabled={uploading || count >= requirement.max}
                        onChange={(event) => {
                          const files = Array.from(event.target.files || []);
                          event.target.value = "";
                          void addFiles(files, kind);
                        }}
                      />
                    </label>
                  );
                })}
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

            {userFields.length ? (
              <div className="trend-user-fields">
                <strong>Персонализируйте шаблон</strong>
                <p className="muted">Заполните только свои данные. Скрытый промпт останется скрытым.</p>
                {userFields.map((field) => {
                  const value = userValues[field.key] || "";
                  const valid = userFieldValid(field, value);
                  return <label key={field.key} className="trend-user-field">
                    <span>{field.label}{field.required === false ? "" : " *"}</span>
                    <div className="trend-user-field-input">
                      <input
                        type={field.type === "date" ? "date" : "text"}
                        inputMode={field.type === "number" ? "decimal" : "text"}
                        value={value}
                        maxLength={field.type === "date" ? undefined : Math.max(1, Math.min(160, field.max_length || 160))}
                        placeholder={field.placeholder || ""}
                        aria-invalid={Boolean(value) && !valid}
                        disabled={running}
                        onChange={(event) => {
                          let nextValue = event.target.value;
                          if (field.type === "number") nextValue = nextValue.replace(/[^0-9.,-]/g, "").slice(0, 160);
                          setUserValues((current) => ({ ...current, [field.key]: nextValue }));
                        }}
                      />
                      {field.suffix ? <span>{field.suffix}</span> : null}
                    </div>
                    {value && !valid ? <small className="action-error">Проверьте значение поля «{field.label}»</small> : null}
                  </label>;
                })}
              </div>
            ) : null}

            {error ? <div className="action-error" role="alert">{error}</div> : null}
            <button className="primary wide" type="button" disabled={!ready || uploading || running} onClick={() => void run()}>
              {running ? "Запускаю…" : adminFree ? "Сгенерировать бесплатно" : `Сгенерировать · ${money(displayedCost)} ROX`}
            </button>
            <button className="secondary wide" type="button" disabled={sharing} onClick={() => void share()}>
              {sharing ? "Открываю Telegram…" : "Поделиться трендом"}
            </button>
            <button className="secondary wide" type="button" disabled={copying} onClick={() => void copyLink()}>
              {copying ? "Копирую…" : "Скопировать ссылку тренда"}
            </button>
          </div>
        </div>
      ) : error ? <div className="action-error" role="alert">{error}</div> : <div className="panel"><p className="muted">Загрузка…</p></div>}
    </StandaloneShell>
  );
}
