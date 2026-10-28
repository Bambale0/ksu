"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { StandaloneShell } from "@/components/standalone-shell";
import { api } from "@/lib/api";
import { copyToClipboard, haptic, notify, openTelegramShare } from "@/lib/telegram";
import { trendUsageLabel } from "@/lib/trend-usage";
import type {
  TrendItem,
  TrendQualityOption,
  TrendUserField,
  TrendWorkflowInput,
  TrendWorkflowMedia,
  TrendWorkflowQuote,
  TrendWorkflowRun,
  TrendWorkflowStep,
} from "@/lib/types";
import styles from "./trend.module.css";

const TREND_USER_NUMBER_RE = /^-?\d+(?:[.,]\d+)?$/;

function trendId(): string {
  if (typeof window === "undefined") return "";
  return new URL(window.location.href).searchParams.get("id") || "";
}

function workflowRunId(): string {
  if (typeof window === "undefined") return "";
  return new URL(window.location.href).searchParams.get("workflow") || "";
}

function workflowCommandKey(trendIdValue: string): string {
  const storageKey = `roxy:trend-workflow:${trendIdValue}`;
  try {
    const current = window.sessionStorage.getItem(storageKey);
    if (current) return current;
    const next = `workflow:${trendIdValue}:${crypto.randomUUID()}`;
    window.sessionStorage.setItem(storageKey, next);
    return next;
  } catch {
    return `workflow:${trendIdValue}`;
  }
}

function freshCommandKey(stepId: string): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return `workflow-step:${stepId}:${crypto.randomUUID()}`;
  return `workflow-step:${stepId}:${Date.now()}`;
}

type PendingOperationMetadata = { key: string; acceptedQuotePrice?: string; retry?: boolean };

function pendingCommandStorageKey(workflowId: string, stepId: string): string {
  return `roxy:trend-operation:${workflowId}:${stepId}`;
}

function readPendingOperation(workflowId: string, stepId: string): PendingOperationMetadata | null {
  try {
    const raw = window.sessionStorage.getItem(pendingCommandStorageKey(workflowId, stepId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PendingOperationMetadata;
    if (!parsed || typeof parsed.key !== "string" || !parsed.key) return null;
    return {
      key: parsed.key,
      ...(typeof parsed.acceptedQuotePrice === "string" ? { acceptedQuotePrice: parsed.acceptedQuotePrice } : {}),
      retry: parsed.retry === true,
    };
  } catch {
    return null;
  }
}

function rememberPendingOperation(workflowId: string, stepId: string, key: string, acceptedQuotePrice?: string, retry = false): boolean {
  try {
    const payload: PendingOperationMetadata = { key, retry };
    if (acceptedQuotePrice) payload.acceptedQuotePrice = acceptedQuotePrice;
    const storageKey = pendingCommandStorageKey(workflowId, stepId);
    const serialized = JSON.stringify(payload);
    window.sessionStorage.setItem(storageKey, serialized);
    return window.sessionStorage.getItem(storageKey) === serialized;
  } catch {
    return false;
  }
}

function operationAccepted(step: TrendWorkflowStep | undefined, key: string): boolean {
  if (!step || !key) return false;
  if (step.command_id === key && step.generation_id) return true;
  return Boolean(step.attempt_history?.some((attempt) => attempt.command_id === key && attempt.generation_id));
}

function WorkflowLockIcon() {
  return <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>;
}

function WorkflowCameraIcon() {
  return <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M4 7.5h3l1.3-2h7.4l1.3 2h3a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9.5a2 2 0 0 1 2-2Z" /><circle cx="12" cy="13.5" r="4" /></svg>;
}

function WorkflowVideoIcon() {
  return <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><rect x="2.5" y="5.5" width="13.5" height="13" rx="2.5" /><path d="m16 10 5-3v10l-5-3" /></svg>;
}

function workflowPreviewRetryUrl(url: string, attempt: number): string {
  return attempt ? `${url}${url.includes("?") ? "&" : "?"}retry=${attempt}` : url;
}

function workflowPreviewCanCacheBust(url: string): boolean {
  return /\/api\/v1\/trends\/[^/?]+\/preview-thumbnail(?:[?#]|$)/.test(url);
}

function WorkflowStageImage({ primaryUrl, fallbackUrl, alt }: { primaryUrl: string; fallbackUrl: string; alt: string }) {
  const [attempt, setAttempt] = useState(0);
  const [usingFallback, setUsingFallback] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const retryTimer = useRef<number | null>(null);

  useEffect(() => {
    setAttempt(0);
    setUsingFallback(false);
    setUnavailable(false);
    return () => {
      if (retryTimer.current !== null) window.clearTimeout(retryTimer.current);
      retryTimer.current = null;
    };
  }, [fallbackUrl, primaryUrl]);

  const source = usingFallback ? fallbackUrl : primaryUrl;
  const canRetryPrimary = !usingFallback && workflowPreviewCanCacheBust(primaryUrl);
  if (!source || unavailable) return <span className={styles.workflowStageFallback} aria-hidden="true" />;
  return <img
    src={canRetryPrimary ? workflowPreviewRetryUrl(source, attempt) : source}
    alt={alt}
    onError={() => {
      if (retryTimer.current !== null) return;
      if (canRetryPrimary && attempt < 3) {
        retryTimer.current = window.setTimeout(() => {
          retryTimer.current = null;
          setAttempt((current) => current + 1);
        }, 600);
      } else if (!usingFallback && fallbackUrl && fallbackUrl !== primaryUrl) {
        setUsingFallback(true);
      } else {
        setUnavailable(true);
      }
    }}
  />;
}


function safeError(reason: unknown, fallback: string): string {
  return reason instanceof Error && reason.message ? reason.message : fallback;
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

function previewUrlHasVideoExtension(url: string): boolean {
  return /\.(mp4|webm|mov|m4v)(?:[?#]|$)/i.test(url);
}

function previewIsVideo(trend: TrendItem): boolean {
  const previewUrl = trend.preview_url || "";
  if (previewUrlHasVideoExtension(previewUrl)) return true;
  if (/\.(avif|bmp|gif|heic|heif|jpe?g|png|svg|webp)(?:[?#]|$)/i.test(previewUrl)) return false;
  return trend.media_type === "video";
}

function defaultQualityValue(trend: TrendItem): string {
  const options = trend.quality_options || [];
  return options.find((option) => option.default)?.value || options[0]?.value || "";
}

function optionPriceLabel(option: TrendQualityOption): string {
  const value = option.admin_free ? option.retail_cost_rox || option.cost_rox : option.cost_rox;
  return value ? `${money(value)} ROX` : "";
}

type WorkflowImageValue = { url: string; name: string; previewUrl: string };
type WorkflowUploadState = { status: "idle" | "uploading" | "error"; name?: string; message?: string };

const WORKFLOW_ACTIVE_STATUSES = new Set(["running", "queued", "reconciling", "awaiting_media"]);

function workflowNeedsRetryConsent(status: string): boolean {
  return status === "failed" || status === "ready";
}

function workflowStatusLabel(status: string): string {
  switch (status) {
    case "pending": return "ожидает действий";
    case "queued": return "в очереди";
    case "running": return "выполняется";
    case "ready": return "готово";
    case "awaiting_media": return "сохраняем результат";
    case "reconciling": return "проверяем результат";
    case "failed": return "не получилось";
    default: return status || "ожидает действий";
  }
}

function workflowMediaUrl(media?: TrendWorkflowMedia | null): string {
  return typeof media?.url === "string" ? media.url : "";
}

function workflowSettingsLabel(settings?: Record<string, string | number | null>): string {
  if (!settings) return "";
  const labels: Record<string, string> = { duration: "Длительность", resolution: "Разрешение", aspect_ratio: "Соотношение сторон" };
  return Object.entries(settings)
    .filter(([, value]) => value !== null && value !== undefined && String(value).trim())
    .map(([key, value]) => `${labels[key] || key}: ${value}`)
    .join(" · ");
}

function workflowInputValueIsValid(input: TrendWorkflowInput, value: string): boolean {
  const clean = value.trim();
  if (!clean) return !input.required;
  if (input.type === "number") return /^-?\d+(?:[.,]\d+)?$/.test(clean);
  if (input.type === "date") {
    const parsed = new Date(`${clean}T00:00:00Z`);
    return /^\d{4}-\d{2}-\d{2}$/.test(clean) && !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === clean;
  }
  if (input.type === "select") return Boolean(input.options?.includes(clean));
  return clean.length <= 160;
}

function WorkflowInputSlot({
  input,
  value,
  onChange,
  disabled,
}: {
  input: TrendWorkflowInput;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  const label = `${input.label}${input.required ? " *" : ""}`;
  const invalid = Boolean(value) && !workflowInputValueIsValid(input, value);
  if (input.type === "select") {
    return (
      <label className={styles.workflowField}>
        <span>{label}</span>
        <select aria-label={input.label} value={value} disabled={disabled} aria-invalid={invalid} onChange={(event) => onChange(event.target.value)}>
          <option value="">Выберите вариант</option>
          {(input.options || []).map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
        <small>{input.help}</small>
      </label>
    );
  }
  return (
    <label className={styles.workflowField}>
      <span>{label}</span>
      <input
        aria-label={input.label}
        maxLength={input.type === "date" ? undefined : 160}
        type={input.type === "date" ? "date" : "text"}
        inputMode={input.type === "number" ? "decimal" : undefined}
        value={value}
        disabled={disabled}
        aria-invalid={invalid}
        onChange={(event) => onChange(event.target.value)}
      />
      <small>{input.help}</small>
      {invalid ? <em>Проверьте значение поля</em> : null}
    </label>
  );
}

function TrendWorkflowRunner({
  trend,
  initialWorkflow,
  onShare,
  onCopy,
  sharing,
  copying,
}: {
  trend: TrendItem | null;
  initialWorkflow: TrendWorkflowRun;
  onShare: () => void;
  onCopy: () => void;
  sharing: boolean;
  copying: boolean;
}) {
  const [workflow, setWorkflow] = useState(initialWorkflow);
  const [values, setValues] = useState<Record<string, string>>({});
  const [videoValues, setVideoValues] = useState<Record<string, string>>({});
  const [previewReady, setPreviewReady] = useState("");
  const [quoteRevision, setQuoteRevision] = useState(0);
  const [images, setImages] = useState<Record<string, WorkflowImageValue>>({});
  const [uploads, setUploads] = useState<Record<string, WorkflowUploadState>>({});
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [quotes, setQuotes] = useState<Record<string, TrendWorkflowQuote | null>>({});
  const [quoteLoading, setQuoteLoading] = useState<Record<string, boolean>>({});
  const [quoteErrors, setQuoteErrors] = useState<Record<string, string>>({});
  const [retryConsent, setRetryConsent] = useState<Record<string, boolean>>({});
  const [retryPreviousPrices, setRetryPreviousPrices] = useState<Record<string, string>>({});
  const [runningStep, setRunningStep] = useState("");
  const [error, setError] = useState("");
  const [reconciling, setReconciling] = useState(false);
  const [lockedStepDialogOpen, setLockedStepDialogOpen] = useState(false);
  const lockedStepTrigger = useRef<HTMLButtonElement | null>(null);
  const lockedStepCancel = useRef<HTMLButtonElement | null>(null);
  const lockedStepDialog = useRef<HTMLElement | null>(null);
  const videoStageCard = useRef<HTMLButtonElement | null>(null);
  const inputVersions = useRef<Record<string, number>>({});
  const quoteVersions = useRef<Record<string, number>>({});
  const commandKeys = useRef<Record<string, string>>({});
  const pendingCommands = useRef<Record<string, { key: string; body: Record<string, unknown> }>>({});
  const [uncertainStep, setUncertainStep] = useState("");
  const pendingOperations = useRef<Record<string, PendingOperationMetadata>>({});
  const [recoveryConsent, setRecoveryConsent] = useState(false);
  const acceptedQuotePrices = useRef<Record<string, string>>({});
  const seenRetryStates = useRef<Record<string, string>>({});
  const mounted = useRef(true);
  const imagesRef = useRef(images);
  imagesRef.current = images;
  useEffect(() => () => {
    mounted.current = false;
    for (const image of Object.values(imagesRef.current)) URL.revokeObjectURL(image.previewUrl);
  }, []);
  const runningRef = useRef(false);
  const pollingRef = useRef(false);
  const workflowRef = useRef(workflow);
  workflowRef.current = workflow;

  useEffect(() => {
    let unresolved = "";
    for (const step of workflow.steps) {
      const stored = readPendingOperation(workflow.id, step.id);
      if (!stored) continue;
      if (stored.acceptedQuotePrice) acceptedQuotePrices.current[step.id] = stored.acceptedQuotePrice;
      if (operationAccepted(step, stored.key)) {
        delete pendingCommands.current[step.id];
        delete pendingOperations.current[step.id];
        delete commandKeys.current[step.id];
        // If an earlier in-flight request won, show its actual selected source.
        if (step.kind === "video" && step.command_id === stored.key) {
          const photo = workflow.steps.find((candidate) => candidate.kind === "image");
          if (photo?.media_asset_id) setSelectedAssetId(photo.media_asset_id);
        }
      } else {
        pendingOperations.current[step.id] = stored;
        commandKeys.current[step.id] = stored.key;
        unresolved ||= step.id;
      }
    }
    setUncertainStep(unresolved);
  }, [workflow]);

  const invalidateQuote = (stepId: string) => {
    quoteVersions.current[stepId] = (quoteVersions.current[stepId] || 0) + 1;
    setQuotes((current) => ({ ...current, [stepId]: null }));
    setQuoteErrors((current) => {
      if (!current[stepId]) return current;
      const next = { ...current };
      delete next[stepId];
      return next;
    });
  };
  const photoStep = workflow.steps.find((step) => step.kind === "image") || workflow.steps[0];
  const videoStep = workflow.steps.find((step) => step.kind === "video") || workflow.steps[1];
  const photoInputs = useMemo(() => (photoStep?.inputs || []).slice().sort((a, b) => a.order - b.order), [photoStep?.inputs]);
  const photoImageInputs = useMemo(() => photoInputs.filter((input) => input.type === "image"), [photoInputs]);
  const photoValueInputs = useMemo(() => photoInputs.filter((input) => input.type !== "image"), [photoInputs]);
  const videoValueInputs = useMemo(() => (videoStep?.inputs || []).filter((input) => input.type !== "image").sort((a, b) => a.order - b.order), [videoStep?.inputs]);
  const photoStatus = photoStep?.status || "pending";
  const videoStatus = videoStep?.status || "pending";
  const photoReady = photoStatus === "ready" && Boolean(photoStep?.media_asset_id) && Boolean(workflowMediaUrl(photoStep?.media));
  const videoUnlocked = photoReady;
  const mediaOptions = useMemo(() => (photoStep?.media_options || []).filter((media) => Boolean(media.id && workflowMediaUrl(media))), [photoStep?.media_options]);
  const selectedMedia = mediaOptions.find((media) => media.id === selectedAssetId) || photoStep?.media;
  const selectedMediaUrl = workflowMediaUrl(selectedMedia);
  const workflowThumbnailUrl = trend?.preview_thumbnail_url || workflow.preview_thumbnail_url || "";
  const workflowCoverFallbackUrl = (trend?.preview_url && !previewUrlHasVideoExtension(trend.preview_url) ? trend.preview_url : "") || selectedMediaUrl;
  const photoOverviewUrl = photoReady && selectedMediaUrl
    ? selectedMediaUrl
    : (photoStep?.preview_url || workflowThumbnailUrl || workflowCoverFallbackUrl);
  const videoOverviewUrl = videoStep?.preview_url || workflowThumbnailUrl || workflowCoverFallbackUrl || photoOverviewUrl;
  const selectionVersion = `${selectedAssetId}:${selectedMediaUrl}`;
  const photoReadOnly = Boolean(videoStep?.generation_id);
  const inputsLocked = Boolean(runningStep || (uncertainStep && pendingCommands.current[uncertainStep])) || WORKFLOW_ACTIVE_STATUSES.has(photoStatus);
  const workflowUncertain = workflow.status === "reconciling" || workflow.steps.some((step) => Boolean(step.reconcile_required));
  const stepIsUncertain = (stepId: string): boolean => workflowUncertain || uncertainStep === stepId || Boolean(pendingCommands.current[stepId]);

  useEffect(() => {
    if (!selectedAssetId && photoStep?.media_asset_id) setSelectedAssetId(photoStep.media_asset_id);
    if (selectedAssetId && mediaOptions.length && !mediaOptions.some((media) => media.id === selectedAssetId)) {
      setSelectedAssetId(photoStep?.media_asset_id || mediaOptions[0]?.id || "");
    }
  }, [mediaOptions, photoStep?.media_asset_id, selectedAssetId]);

  const imageInputPayload = useMemo(() => photoImageInputs
    .filter((input) => images[input.id]?.url)
    .map((input) => ({ slot_id: input.id, url: images[input.id].url })), [images, photoImageInputs]);

  const valuesPayload = useMemo(() => Object.fromEntries(photoValueInputs
    .filter((input) => values[input.id] !== undefined && values[input.id] !== "")
    .map((input) => [input.id, input.type === "number" ? Number(values[input.id].replace(",", ".")) : values[input.id]])), [photoValueInputs, values]);

  const photoValid = photoImageInputs.every((input) => Boolean(images[input.id]) || !input.required)
    && photoValueInputs.every((input) => workflowInputValueIsValid(input, values[input.id] || ""));
  const videoValid = videoUnlocked && Boolean(selectedAssetId) && previewReady === selectionVersion
    && videoValueInputs.every((input) => workflowInputValueIsValid(input, videoValues[input.id] || ""));
  const videoValuesPayload = useMemo(() => Object.fromEntries(videoValueInputs
    .filter((input) => videoValues[input.id] !== undefined && videoValues[input.id] !== "")
    .map((input) => [input.id, videoValues[input.id]])), [videoValueInputs, videoValues]);
  const quoteBodies = useMemo(() => ({
    [photoStep.id]: { image_inputs: imageInputPayload, values: valuesPayload },
    [videoStep.id]: { media_asset_id: selectedAssetId, values: videoValuesPayload },
  }), [imageInputPayload, photoStep.id, selectedAssetId, valuesPayload, videoStep.id, videoValuesPayload]);
  // A polling response may replace step objects, but identical user input must
  // not re-trigger pricing merely because quote state or object identity changed.
  const photoQuoteKey = JSON.stringify(quoteBodies[photoStep.id]);
  const videoQuoteKey = JSON.stringify(quoteBodies[videoStep.id]);

  useEffect(() => {
    const step = photoStep;
    if (!step || !photoValid) {
      setQuotes((current) => ({ ...current, [step?.id || "prepare_photo"]: null }));
      return;
    }
    const version = (quoteVersions.current[step.id] || 0) + 1;
    quoteVersions.current[step.id] = version;
    setQuoteLoading((current) => ({ ...current, [step.id]: true }));
    setQuotes((current) => ({ ...current, [step.id]: null }));
    setQuoteErrors((current) => ({ ...current, [step.id]: "" }));
    void api.quoteTrendWorkflowStep(workflow.id, step.id, quoteBodies[step.id]).then((quote) => {
      if (quoteVersions.current[step.id] === version) setQuotes((current) => ({ ...current, [step.id]: quote }));
    }).catch((reason) => {
      if (quoteVersions.current[step.id] === version) setQuoteErrors((current) => ({ ...current, [step.id]: safeError(reason, "Не удалось обновить стоимость фото") }));
    }).finally(() => {
      if (quoteVersions.current[step.id] === version) setQuoteLoading((current) => ({ ...current, [step.id]: false }));
    });
    return () => { if (quoteVersions.current[step.id] === version) quoteVersions.current[step.id] += 1; };
  }, [photoStep.id, photoValid, photoQuoteKey, workflow.id, quoteRevision]);

  useEffect(() => {
    if (!videoStep || !videoValid) {
      setQuotes((current) => ({ ...current, [videoStep?.id || "animate_photo"]: null }));
      return;
    }
    const version = (quoteVersions.current[videoStep.id] || 0) + 1;
    quoteVersions.current[videoStep.id] = version;
    setQuoteLoading((current) => ({ ...current, [videoStep.id]: true }));
    setQuotes((current) => ({ ...current, [videoStep.id]: null }));
    setQuoteErrors((current) => ({ ...current, [videoStep.id]: "" }));
    void api.quoteTrendWorkflowStep(workflow.id, videoStep.id, quoteBodies[videoStep.id]).then((quote) => {
      if (quoteVersions.current[videoStep.id] === version) setQuotes((current) => ({ ...current, [videoStep.id]: quote }));
    }).catch((reason) => {
      if (quoteVersions.current[videoStep.id] === version) setQuoteErrors((current) => ({ ...current, [videoStep.id]: safeError(reason, "Не удалось обновить стоимость видео") }));
    }).finally(() => {
      if (quoteVersions.current[videoStep.id] === version) setQuoteLoading((current) => ({ ...current, [videoStep.id]: false }));
    });
    return () => { if (quoteVersions.current[videoStep.id] === version) quoteVersions.current[videoStep.id] += 1; };
  }, [videoQuoteKey, videoStep.id, videoValid, workflow.id, quoteRevision]);

  useEffect(() => {
    const retryable = [
      { step: photoStep, status: photoStatus, bodyKey: photoQuoteKey },
      { step: videoStep, status: videoStatus, bodyKey: videoQuoteKey },
    ];
    for (const { step, status, bodyKey } of retryable) {
      if (!step || !workflowNeedsRetryConsent(status)) continue;
      // A later failed attempt can have the same status and inputs. Consent
      // belongs to one accepted attempt, never to the whole recipe forever.
      const marker = JSON.stringify([step.command_id, step.generation_id, step.attempts, status, bodyKey]);
      if (seenRetryStates.current[step.id] === marker) continue;
      seenRetryStates.current[step.id] = marker;
      setRetryConsent((current) => ({ ...current, [step.id]: false }));
      const previousPrice = acceptedQuotePrices.current[step.id];
      if (previousPrice) setRetryPreviousPrices((current) => ({ ...current, [step.id]: previousPrice }));
      invalidateQuote(step.id);
      setQuoteRevision((current) => current + 1);
    }
  }, [photoQuoteKey, photoStatus, photoStep.command_id, photoStep.generation_id, photoStep.attempts,
    videoQuoteKey, videoStatus, videoStep.command_id, videoStep.generation_id, videoStep.attempts]);

  const refreshWorkflow = async () => {
    const next = await api.trendWorkflow(workflow.id);
    setWorkflow(next);
    return next;
  };

  const pollActive = workflow.steps.some((step) => WORKFLOW_ACTIVE_STATUSES.has(step.status)) || workflow.status === "reconciling";

  useEffect(() => {
    if (!pollActive) return;
    let disposed = false;
    let timer: number | undefined;
    let attempts = 0;
    const poll = async () => {
      if (disposed) return;
      if (pollingRef.current || document.hidden) { timer = window.setTimeout(() => void poll(), 3000); return; }
      pollingRef.current = true;
      attempts += 1;
      try {
        const next = await api.trendWorkflow(workflowRef.current.id);
        if (!disposed) setWorkflow(next);
        if (!disposed && (next.steps.some((step) => WORKFLOW_ACTIVE_STATUSES.has(step.status)) || next.status === "reconciling")) timer = window.setTimeout(() => void poll(), Math.min(10_000, 1200 + attempts * 150));
      } catch (reason) {
        if (!disposed) setError(safeError(reason, "Не удалось обновить состояние работы"));
        if (!disposed) timer = window.setTimeout(() => void poll(), 1800);
      } finally {
        pollingRef.current = false;
      }
    };
    void poll();
    return () => { disposed = true; if (timer) window.clearTimeout(timer); };
  }, [pollActive, workflow.id]);

  const uploadImage = async (input: TrendWorkflowInput, file: File) => {
    const version = (inputVersions.current[input.id] || 0) + 1;
    inputVersions.current[input.id] = version;
    const previewUrl = URL.createObjectURL(file);
    setUploads((current) => ({ ...current, [input.id]: { status: "uploading", name: file.name } }));
    setError("");
    try {
      const uploaded = await api.upload(file);
      if (!mounted.current || inputVersions.current[input.id] !== version) { URL.revokeObjectURL(previewUrl); return; }
      invalidateQuote(photoStep.id);
      setImages((current) => {
        const previous = current[input.id];
        if (previous?.previewUrl) URL.revokeObjectURL(previous.previewUrl);
        return { ...current, [input.id]: { url: uploaded.url, name: file.name, previewUrl } };
      });
      setUploads((current) => ({ ...current, [input.id]: { status: "idle", name: file.name } }));
    } catch (reason) {
      URL.revokeObjectURL(previewUrl);
      if (mounted.current && inputVersions.current[input.id] === version) {
        setUploads((current) => ({ ...current, [input.id]: { status: "error", name: file.name, message: safeError(reason, "Не удалось загрузить фото") } }));
        setError(safeError(reason, "Не удалось загрузить фото. Попробуйте ещё раз."));
      }
    }
  };

  const removeImage = (inputId: string) => {
    inputVersions.current[inputId] = (inputVersions.current[inputId] || 0) + 1;
    invalidateQuote(photoStep.id);
    setImages((current) => { if (current[inputId]?.previewUrl) URL.revokeObjectURL(current[inputId].previewUrl); const next = { ...current }; delete next[inputId]; return next; });
    setUploads((current) => ({ ...current, [inputId]: { status: "idle" } }));
  };

  const reconcileAfterAmbiguousRun = async (stepId: string) => {
    setReconciling(true);
    const key = pendingOperations.current[stepId]?.key || pendingCommands.current[stepId]?.key || readPendingOperation(workflow.id, stepId)?.key;
    try {
      if (!key) {
        await refreshWorkflow();
        setError("");
        return;
      }
      for (let attempt = 0; attempt < 3; attempt += 1) {
        if (attempt) await new Promise<void>((resolve) => window.setTimeout(resolve, 250));
        const next = await refreshWorkflow();
        if (operationAccepted(next.steps.find((step) => step.id === stepId), key)) {
          delete pendingCommands.current[stepId];
          delete pendingOperations.current[stepId];
          delete commandKeys.current[stepId];
          setUncertainStep("");
          setError("");
          return;
        }
      }
      setError("Запуск пока не подтверждён. Проверьте статус или восстановите тот же запуск — второй заказ не создаётся.");
    } catch {
      setError("Не удалось проверить запуск. Проверьте соединение и нажмите «Проверить статус».");
    } finally { setReconciling(false); }
  };

  const runStep = async (step: TrendWorkflowStep, quote: TrendWorkflowQuote | null, retry: boolean, recover = false) => {
    const existing = pendingCommands.current[step.id];
    const metadata = pendingOperations.current[step.id];
    if (runningRef.current || runningStep || reconciling || workflowUncertain) return;
    if (stepIsUncertain(step.id) && !existing && !recover) return;
    if (!existing && (!quote || quoteLoading[step.id])) return;
    if (recover && (!metadata || !recoveryConsent || !(step.kind === "image" ? photoValid : videoValid))) return;
    const effectiveRetry = metadata ? metadata.retry === true : retry;
    const body: Record<string, unknown> = existing?.body || {
      ...quoteBodies[step.id], quoted_cost_rox: quote!.cost_rox, ...(effectiveRetry ? { retry: true } : {}),
    };
    const key = existing?.key || metadata?.key || (retry ? freshCommandKey(step.id) : commandKeys.current[step.id] || freshCommandKey(step.id));
    const acceptedPrice = String(body.quoted_cost_rox || quote?.cost_rox || acceptedQuotePrices.current[step.id] || "");
    if (!rememberPendingOperation(workflow.id, step.id, key, acceptedPrice, effectiveRetry)) {
      setError("Не удалось сохранить состояние запуска. Освободите хранилище приложения или откройте ROXY заново. Запуск не оплачен.");
      return;
    }
    acceptedQuotePrices.current[step.id] = acceptedPrice;
    commandKeys.current[step.id] = key;
    pendingOperations.current[step.id] = { key, acceptedQuotePrice: acceptedPrice, retry: effectiveRetry };
    pendingCommands.current[step.id] = { key, body };
    runningRef.current = true;
    setRunningStep(step.id);
    setError("");
    try {
      const next = await api.runTrendWorkflowStep(workflow.id, step.id, key, body);
      setWorkflow(next);
      if (operationAccepted(next.steps.find((candidate) => candidate.id === step.id), key)) {
        delete pendingCommands.current[step.id];
        delete pendingOperations.current[step.id];
        delete commandKeys.current[step.id];
        setUncertainStep("");
      } else {
        setUncertainStep(step.id);
        void reconcileAfterAmbiguousRun(step.id);
      }
    } catch (reason) {
      const status = Number((reason as { status?: number })?.status);
      setUncertainStep(step.id);
      if ([401, 403, 404, 409, 422, 429].includes(status)) {
        // A delayed original may still be in flight. Permit correction, but
        // retain its identity until an owner-scoped receipt proves acceptance.
        delete pendingCommands.current[step.id];
        setRecoveryConsent(false);
        invalidateQuote(step.id);
        setQuoteRevision((current) => current + 1);
        setError(status === 422 ? "Проверьте поля и актуальную стоимость перед восстановлением запуска." : safeError(reason, "Не удалось запустить шаг"));
      } else {
        setError("Проверяю результат запуска. Новый платный запрос не отправляется.");
      }
      void reconcileAfterAmbiguousRun(step.id);
    } finally { runningRef.current = false; setRunningStep(""); }
  };

  const startAnother = async () => {
    if (runningRef.current) return;
    runningRef.current = true;
    try {
      const next = await api.createTrendWorkflow(workflow.trend_id, freshCommandKey("workflow"));
      window.location.assign(`/mini-app/trend/?id=${encodeURIComponent(workflow.trend_id)}&workflow=${encodeURIComponent(next.id)}`);
    } catch (reason) { setError(safeError(reason, "Не удалось открыть новый сценарий")); }
    finally { runningRef.current = false; }
  };

  const focusPhoto = () => {
    const target = document.querySelector<HTMLElement>('[data-step="prepare_photo"]');
    target?.focus({ preventScroll: false });
    target?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  };

  const openLockedStepDialog = (trigger: HTMLButtonElement) => {
    lockedStepTrigger.current = trigger;
    setLockedStepDialogOpen(true);
  };

  const dismissLockedStepDialog = () => {
    setLockedStepDialogOpen(false);
    window.requestAnimationFrame(() => {
      const trigger = lockedStepTrigger.current;
      if (trigger && document.contains(trigger)) trigger.focus();
      else videoStageCard.current?.focus();
    });
  };

  const continueToPhotoStep = () => {
    setLockedStepDialogOpen(false);
    window.requestAnimationFrame(focusPhoto);
  };

  useEffect(() => {
    if (!lockedStepDialogOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusFrame = window.requestAnimationFrame(() => lockedStepCancel.current?.focus());
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setLockedStepDialogOpen(false);
        window.requestAnimationFrame(() => {
          const trigger = lockedStepTrigger.current;
          if (trigger && document.contains(trigger)) trigger.focus();
          else videoStageCard.current?.focus();
        });
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(lockedStepDialog.current?.querySelectorAll<HTMLElement>("button:not([disabled])") || []);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [lockedStepDialogOpen]);

  useEffect(() => {
    if (!videoUnlocked || !lockedStepDialogOpen) return;
    setLockedStepDialogOpen(false);
    window.requestAnimationFrame(() => videoStageCard.current?.focus());
  }, [lockedStepDialogOpen, videoUnlocked]);

  const renderQuote = (step: TrendWorkflowStep, action: string) => {
    const quote = quotes[step.id];
    if (!quote) return quoteLoading[step.id] ? "Считаю стоимость…" : action;
    if (quote.admin_free) return `${action} · Бесплатно (админский доступ)`;
    return `${action} · ${money(quote.cost_rox)} ROX`;
  };

  const refreshQuote = (stepId: string) => {
    setError("");
    invalidateQuote(stepId);
    setQuoteRevision((current) => current + 1);
  };

  const retryConsentCopy = (step: TrendWorkflowStep): string => {
    const quote = quotes[step.id];
    return quote?.admin_free ? "Подтверждаю повторный запуск бесплатно" : `Подтверждаю новую оплату: ${money(quote?.cost_rox)} ROX`;
  };

  const uncertainWorkflowStep = workflow.steps.find((step) => step.id === uncertainStep);
  const uncertainCommand = uncertainStep ? pendingCommands.current[uncertainStep] : undefined;
  const recoveryQuote = quotes[uncertainStep];
  const recoveryValid = uncertainWorkflowStep?.kind === "image" ? photoValid : videoValid;
  const recoveryQuoteKey = JSON.stringify([uncertainStep, quoteBodies[uncertainStep], recoveryQuote?.cost_rox]);
  useEffect(() => setRecoveryConsent(false), [recoveryQuoteKey]);

  return (
    <div className={styles.workflow}>
      <button className={styles.workflowShare} type="button" disabled={sharing} onClick={onShare}>
        <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12" /><path d="m7 8 5-5 5 5" /><path d="M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6" /></svg>
        {sharing ? "Открываю Telegram…" : "Поделиться"}
      </button>
      <nav className={styles.workflowOverview} aria-label="Этапы сценария">
        <button className={styles.workflowStageCard} type="button" aria-label="Шаг 1. Подготовить фото" onClick={focusPhoto}>
          <WorkflowStageImage primaryUrl={photoOverviewUrl} fallbackUrl={workflowCoverFallbackUrl} alt="Шаг 1: Подготовить фото" />
          <span className={styles.workflowStageScrim} aria-hidden="true" />
          <span className={styles.workflowStageIcon}><WorkflowCameraIcon /></span>
          <strong className={styles.workflowStageLabel}>ШАГ 1</strong>
        </button>
        <button
          ref={videoStageCard}
          className={`${styles.workflowStageCard} ${!videoUnlocked ? styles.workflowStageCardLocked : ""}`}
          type="button"
          aria-label={`Шаг 2. Оживить фото${videoUnlocked ? "" : ". Сначала Шаг 1"}`}
          aria-haspopup={!videoUnlocked ? "dialog" : undefined}
          aria-expanded={!videoUnlocked ? lockedStepDialogOpen : undefined}
          aria-controls={!videoUnlocked ? "workflow-lock-dialog" : undefined}
          onClick={(event) => {
            if (!videoUnlocked) {
              openLockedStepDialog(event.currentTarget);
              return;
            }
            document.querySelector<HTMLElement>('[data-step="animate_photo"]')?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
          }}
        >
          <WorkflowStageImage primaryUrl={videoOverviewUrl} fallbackUrl={workflowCoverFallbackUrl} alt="Шаг 2: Оживить фото" />
          <span className={styles.workflowStageScrim} aria-hidden="true" />
          <span className={styles.workflowStageIcon}><WorkflowVideoIcon /></span>
          {!videoUnlocked ? <span className={styles.workflowLockedChip}>Сначала Шаг 1</span> : null}
          <strong className={styles.workflowStageLabel}>ШАГ 2</strong>
        </button>
      </nav>
      <div className={styles.workflowGrid}>
        <section className={`${styles.workflowCard} ${styles.workflowCardActive}`} data-step="prepare_photo" tabIndex={-1} aria-labelledby="prepare-photo-title">
          <div className={styles.workflowCardHead}><span className={styles.stepBadge}>1</span><div><h2 id="prepare-photo-title">{photoStep.title || "Подготовить фото"}</h2><p>{photoStep.instructions}</p></div></div>
          <div className={styles.workflowStatus} aria-live="polite">Состояние: {workflowStatusLabel(photoStatus)}{photoStep.generation_id ? <span> · задача {photoStep.generation_id}</span> : null}</div>
          {workflowSettingsLabel(photoStep.settings_summary) ? <small className={styles.workflowSettings}>Настройки: {workflowSettingsLabel(photoStep.settings_summary)}</small> : null}
          <div className={styles.workflowInputs}>
            {photoInputs.map((input) => input.type === "image" ? (
              <div className={styles.workflowField} data-slot-id={input.id} key={input.id}>
                <span>{input.label}{input.required ? " *" : ""}</span><small>{input.help}</small>
                {images[input.id] ? <div className={styles.workflowUploadPreview}><img src={images[input.id].previewUrl} alt={`Предпросмотр: ${input.label}`} /><button className="secondary" type="button" disabled={inputsLocked || photoReadOnly} onClick={() => removeImage(input.id)}>Удалить фото</button></div> : null}
                <label className="upload-control"><span>{uploads[input.id]?.status === "uploading" ? "Загружаю…" : images[input.id] ? "Заменить фото" : "Выбрать фото"}</span><input type="file" accept="image/*" disabled={uploads[input.id]?.status === "uploading" || inputsLocked || photoReadOnly} onChange={(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; if (file) void uploadImage(input, file); }} /></label>
                {uploads[input.id]?.status === "error" ? <div className="action-error" role="alert">{uploads[input.id].message || "Не удалось загрузить фото"}. Выберите файл ещё раз.</div> : null}
              </div>
            ) : <WorkflowInputSlot key={input.id} input={input} value={values[input.id] || ""} disabled={inputsLocked || photoReadOnly} onChange={(value) => { invalidateQuote(photoStep.id); setValues((current) => ({ ...current, [input.id]: value })); }} />)}
          </div>
          {photoStep.attempt_history?.length ? <div className={styles.workflowHistory}><span>Предыдущих попыток: {photoStep.attempt_history.length}</span><div className={styles.workflowHistoryMedia}>{photoStep.attempt_history.map((attempt, index) => workflowMediaUrl(attempt.media) ? <img key={`${attempt.generation_id}-${attempt.attempt}`} src={workflowMediaUrl(attempt.media)} alt={`Предыдущий вариант фото ${index + 1}`} /> : null)}</div></div> : null}
          {photoStatus === "failed" ? <div className="action-error" role="alert">Фото не готово. Проверьте входные данные и запустите повторно.</div> : null}
          {quoteErrors[photoStep.id] ? <><div className="action-error" role="alert">{quoteErrors[photoStep.id]}</div><button className="secondary wide" type="button" disabled={quoteLoading[photoStep.id]} onClick={() => refreshQuote(photoStep.id)}>Обновить стоимость</button></> : null}
          {workflowNeedsRetryConsent(photoStatus) && quotes[photoStep.id] ? <label className={styles.retryConsent}><input type="checkbox" checked={Boolean(retryConsent[photoStep.id])} onChange={(event) => setRetryConsent((current) => ({ ...current, [photoStep.id]: event.target.checked }))} />{retryConsentCopy(photoStep)}{retryPreviousPrices[photoStep.id] && retryPreviousPrices[photoStep.id] !== quotes[photoStep.id]?.cost_rox ? <small>Цена изменилась: было {money(retryPreviousPrices[photoStep.id])} ROX, сейчас {money(quotes[photoStep.id]?.cost_rox)} ROX.</small> : null}</label> : null}
          <button className="primary wide" type="button" disabled={!photoValid || (!quotes[photoStep.id] && !pendingCommands.current[photoStep.id]) || stepIsUncertain(photoStep.id) || Boolean(quoteLoading[photoStep.id]) || Boolean(runningStep) || reconciling || photoReadOnly || WORKFLOW_ACTIVE_STATUSES.has(photoStatus) || (workflowNeedsRetryConsent(photoStatus) && !retryConsent[photoStep.id]) || Boolean(Object.values(uploads).some((item) => item.status === "uploading"))} onClick={() => void runStep(photoStep, quotes[photoStep.id] || null, workflowNeedsRetryConsent(photoStatus))}>{runningStep === photoStep.id ? "Запускаю…" : renderQuote(photoStep, photoStatus === "failed" ? "Повторить фото" : photoStatus === "ready" ? "Переделать фото" : "Создать фото")}</button>
        </section>

        {videoUnlocked ? (
          <section className={`${styles.workflowCard} ${styles.workflowCardReady}`} data-step="animate_photo" aria-labelledby="animate-photo-title">
            <div className={styles.workflowCardHead}><span className={styles.stepBadge}>2</span><div><h2 id="animate-photo-title">{videoStep.title || "Оживить фото"}</h2><p>{videoStep.instructions}</p></div></div>
            <div className={styles.workflowStatus} aria-live="polite">Состояние: {workflowStatusLabel(videoStatus)}{videoStep.generation_id ? <span> · задача {videoStep.generation_id}</span> : null}</div>
            {workflowSettingsLabel(videoStep.settings_summary) ? <small className={styles.workflowSettings}>Настройки: {workflowSettingsLabel(videoStep.settings_summary)}</small> : null}
            <div className={styles.selectedMedia}><img key={selectionVersion} src={selectedMediaUrl} alt="Готовое фото для оживления" onLoad={() => setPreviewReady(selectionVersion)} onError={() => { setPreviewReady(""); setError("Фото пока не удалось открыть. Проверьте статус перед оплатой видео."); }} /><strong>{previewReady === selectionVersion ? "Выбранное фото для видео" : "Загружаю выбранное фото…"}</strong></div>
            {mediaOptions.length > 1 ? <div className={styles.mediaChoices} role="radiogroup" aria-label="Выберите готовое фото">{mediaOptions.map((media, index) => <button key={media.id} type="button" role="radio" aria-checked={selectedAssetId === media.id} className={selectedAssetId === media.id ? styles.mediaChoiceActive : ""} disabled={Boolean(runningStep || uncertainStep) || WORKFLOW_ACTIVE_STATUSES.has(videoStatus) || videoStatus === "ready"} onClick={() => { if (selectedAssetId !== media.id) { invalidateQuote(videoStep.id); setSelectedAssetId(media.id || ""); } }}><img src={workflowMediaUrl(media)} alt={`Вариант фото ${index + 1}`} /><span>{selectedAssetId === media.id ? "Выбрано" : `Вариант ${index + 1}`}</span></button>)}</div> : null}
            {videoValueInputs.map((input) => <WorkflowInputSlot key={input.id} input={input} value={videoValues[input.id] || ""} disabled={Boolean(runningStep || (uncertainStep && pendingCommands.current[uncertainStep])) || WORKFLOW_ACTIVE_STATUSES.has(videoStatus)} onChange={(value) => { invalidateQuote(videoStep.id); setVideoValues((current) => ({ ...current, [input.id]: value })); }} />)}
            {videoStatus === "failed" ? <div className="action-error" role="alert">Видео не получилось. Фото сохранено — можно повторить.</div> : null}
            {quoteErrors[videoStep.id] ? <><div className="action-error" role="alert">{quoteErrors[videoStep.id]}</div><button className="secondary wide" type="button" disabled={quoteLoading[videoStep.id]} onClick={() => refreshQuote(videoStep.id)}>Обновить стоимость</button></> : null}
            {workflowNeedsRetryConsent(videoStatus) && quotes[videoStep.id] ? <label className={styles.retryConsent}><input type="checkbox" checked={Boolean(retryConsent[videoStep.id])} onChange={(event) => setRetryConsent((current) => ({ ...current, [videoStep.id]: event.target.checked }))} />{retryConsentCopy(videoStep)}{retryPreviousPrices[videoStep.id] && retryPreviousPrices[videoStep.id] !== quotes[videoStep.id]?.cost_rox ? <small>Цена изменилась: было {money(retryPreviousPrices[videoStep.id])} ROX, сейчас {money(quotes[videoStep.id]?.cost_rox)} ROX.</small> : null}</label> : null}
            <button className="primary wide" type="button" disabled={!videoValid || (!quotes[videoStep.id] && !pendingCommands.current[videoStep.id]) || stepIsUncertain(videoStep.id) || Boolean(quoteLoading[videoStep.id]) || Boolean(runningStep) || reconciling || WORKFLOW_ACTIVE_STATUSES.has(videoStatus) || videoStatus === "ready" || (workflowNeedsRetryConsent(videoStatus) && !retryConsent[videoStep.id])} onClick={() => void runStep(videoStep, quotes[videoStep.id] || null, workflowNeedsRetryConsent(videoStatus))}>{runningStep === videoStep.id ? "Запускаю…" : videoStatus === "ready" ? "Видео готово" : renderQuote(videoStep, videoStatus === "failed" ? "Повторить видео" : "Оживить это фото")}</button>
            {videoStatus === "ready" && workflowMediaUrl(videoStep.media) ? <video className={styles.workflowResult} src={workflowMediaUrl(videoStep.media)} controls playsInline preload="metadata" /> : null}
          </section>
        ) : (
          <button className={`${styles.workflowCard} ${styles.workflowCardLocked}`} type="button" aria-haspopup="dialog" aria-expanded={lockedStepDialogOpen} aria-controls="workflow-lock-dialog" onClick={(event) => openLockedStepDialog(event.currentTarget)} aria-label="Оживить фото. Сначала создайте фото"><div className={styles.workflowCardHead}><span className={styles.stepBadge}>2</span><div><h2>Оживить фото</h2><p>Сначала создайте фото</p></div><span className={styles.lockIcon} aria-hidden="true"><WorkflowLockIcon /></span></div><p className={styles.lockCopy}>После готового фото здесь появится выбор результата и отдельная стоимость видео.</p></button>
        )}
      </div>
      <button className="secondary wide" type="button" disabled={reconciling || Boolean(runningStep)} onClick={() => void reconcileAfterAmbiguousRun(uncertainStep || videoStep.id)}>Проверить статус</button>
      {uncertainCommand && uncertainWorkflowStep ? <button className="secondary wide" type="button" disabled={reconciling || Boolean(runningStep)} onClick={() => void runStep(uncertainWorkflowStep, null, false)}>Повторить тот же запрос</button> : null}
      {uncertainWorkflowStep && !uncertainCommand ? <section className={styles.workflowCard} aria-label="Восстановление запуска">
        <p>Ответ на запуск потерян. При необходимости загрузите фото и заполните данные заново. Будет восстановлен тот же заказ: уже принятая операция повторно не оплачивается.</p>
        {acceptedQuotePrices.current[uncertainStep] && recoveryQuote && acceptedQuotePrices.current[uncertainStep] !== recoveryQuote.cost_rox ? <p>Цена изменилась: было {money(acceptedQuotePrices.current[uncertainStep])} ROX, сейчас {money(recoveryQuote.cost_rox)} ROX.</p> : null}
        <label className={styles.retryConsent}><input type="checkbox" checked={recoveryConsent} disabled={!recoveryQuote || quoteLoading[uncertainStep]} onChange={(event) => setRecoveryConsent(event.target.checked)} />Подтверждаю восстановление запуска: {recoveryQuote?.admin_free ? "бесплатно" : `${money(recoveryQuote?.cost_rox)} ROX`}</label>
        <button className="secondary wide" type="button" disabled={!recoveryValid || !recoveryQuote || !recoveryConsent || Boolean(quoteLoading[uncertainStep]) || reconciling || Boolean(runningStep) || workflowUncertain || WORKFLOW_ACTIVE_STATUSES.has(uncertainWorkflowStep.status)} onClick={() => void runStep(uncertainWorkflowStep, recoveryQuote || null, false, true)}>{renderQuote(uncertainWorkflowStep, "Восстановить тот же запуск")}</button>
      </section> : null}
      {videoStatus === "ready" ? <button className="secondary wide" type="button" onClick={() => void startAnother()}>Создать ещё раз</button> : null}
      {reconciling ? <p className={styles.workflowNotice} aria-live="polite">Проверяю результат запуска…</p> : null}
      {error ? <div className="action-error" role="alert">{error}</div> : null}
      <button className="secondary wide" type="button" disabled={copying} onClick={onCopy}>{copying ? "Копирую…" : "Скопировать ссылку тренда"}</button>
      {lockedStepDialogOpen ? (
        <div className={styles.workflowLockOverlay} onMouseDown={(event) => { if (event.target === event.currentTarget) dismissLockedStepDialog(); }}>
          <section id="workflow-lock-dialog" ref={lockedStepDialog} className={styles.workflowLockDialog} role="dialog" aria-modal="true" aria-labelledby="workflow-lock-title" aria-describedby="workflow-lock-copy">
            <h2 id="workflow-lock-title">Сначала Шаг 1</h2>
            <p id="workflow-lock-copy">В этот шаблон загружается фото, которое вы создадите на Шаге 1. Если загрузить сюда обычное фото, видео получится не таким, как на обложке.</p>
            <div className={styles.workflowLockActions}>
              <button ref={lockedStepCancel} type="button" onClick={dismissLockedStepDialog}>Отмена</button>
              <button type="button" onClick={continueToPhotoStep}>Перейти к Шагу 1</button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}

export default function TrendPage() {
  const [trend, setTrend] = useState<TrendItem | null>(null);
  const [workflow, setWorkflow] = useState<TrendWorkflowRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [workflowRecovery, setWorkflowRecovery] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [copying, setCopying] = useState(false);
  const [references, setReferences] = useState<Array<{ url: string; name: string }>>([]);
  const [videoReferences, setVideoReferences] = useState<Array<{ url: string; name: string }>>([]);
  const [userValues, setUserValues] = useState<Record<string, string>>({});
  const [selectedQuality, setSelectedQuality] = useState("");
  const [selectedAspectRatio, setSelectedAspectRatio] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const id = trendId();
    const runId = workflowRunId();
    if (!id) {
      setError("Тренд не выбран");
      setLoading(false);
      return;
    }
    let cancelled = false;
    const load = async () => {
      try {
        if (runId) {
          const snapshot = await api.trendWorkflow(runId);
          if (cancelled) return;
          setWorkflow(snapshot);
          setTrend({
            id: snapshot.trend_id,
            title: snapshot.title || "Тренд",
            description: snapshot.description,
            media_type: "video",
            preview_url: snapshot.preview_url,
            preview_thumbnail_url: snapshot.preview_thumbnail_url,
            workflow_type: snapshot.workflow_type,
            schema_version: snapshot.recipe_version,
          });
          setLoading(false);
          return;
        }
        const latest = await api.latestTrendWorkflow(id);
        if (latest?.workflow_type === "sequential_photo_video" && Array.isArray(latest.steps) && latest.steps.length === 2) {
          if (cancelled) return;
          setWorkflow(latest);
          setTrend({ id: latest.trend_id, title: latest.title || "Тренд", description: latest.description, media_type: "video", preview_url: latest.preview_url, preview_thumbnail_url: latest.preview_thumbnail_url, workflow_type: latest.workflow_type, schema_version: latest.recipe_version });
          window.history.replaceState(null, "", `/mini-app/trend/?id=${encodeURIComponent(latest.trend_id)}&workflow=${encodeURIComponent(latest.id)}`);
          return;
        }
        const item = await api.trend(id);
        if (cancelled) return;
        setTrend(item);
        setUserValues(Object.fromEntries((item.user_fields || []).slice(0, 6).map((field) => [field.key, ""])));
        setSelectedQuality(defaultQualityValue(item));
        setSelectedAspectRatio("");
        if (item.workflow_type === "sequential_photo_video" || item.schema_version === 2) {
          if (latest) throw new Error("Не удалось прочитать состояние сценария. Обновите страницу.");
          setWorkflowRecovery(true);
          const commandKey = workflowCommandKey(id);
          try {
            const created = await api.createTrendWorkflow(id, commandKey);
            if (cancelled) return;
            setWorkflow(created);
            setWorkflowRecovery(false);
            window.history.replaceState(null, "", `/mini-app/trend/?id=${encodeURIComponent(created.trend_id)}&workflow=${encodeURIComponent(created.id)}`);
          } catch (creationReason) {
            if (cancelled) return;
            const recovered = await api.latestTrendWorkflow(id);
            if (recovered?.workflow_type === "sequential_photo_video" && recovered.steps?.length === 2) {
              setWorkflow(recovered);
              setWorkflowRecovery(false);
              window.history.replaceState(null, "", `/mini-app/trend/?id=${encodeURIComponent(recovered.trend_id)}&workflow=${encodeURIComponent(recovered.id)}`);
            } else {
              setError(safeError(creationReason, "Не удалось подтвердить создание сценария. Проверьте статус и повторите попытку."));
            }
          }
        }
      } catch (reason) {
        if (!cancelled) setError(safeError(reason, "Не удалось открыть тренд"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, []);

  const retryWorkflowRecovery = async () => {
    const id = trend?.id;
    if (!id || running) return;
    setRunning(true);
    setError("");
    try {
      const recovered = await api.latestTrendWorkflow(id);
      if (recovered?.workflow_type === "sequential_photo_video" && recovered.steps?.length === 2) {
        setWorkflow(recovered);
        setWorkflowRecovery(false);
        window.history.replaceState(null, "", `/mini-app/trend/?id=${encodeURIComponent(recovered.trend_id)}&workflow=${encodeURIComponent(recovered.id)}`);
        return;
      }
      const created = await api.createTrendWorkflow(id, workflowCommandKey(id));
      setWorkflow(created);
      setWorkflowRecovery(false);
      window.history.replaceState(null, "", `/mini-app/trend/?id=${encodeURIComponent(created.trend_id)}&workflow=${encodeURIComponent(created.id)}`);
    } catch (reason) {
      setError(safeError(reason, "Не удалось подтвердить сценарий. Повторите проверку позже."));
    } finally {
      setRunning(false);
    }
  };

  const minimum = Number(trend?.reference_requirements?.image?.min ?? trend?.reference_requirements?.min ?? 0);
  const maximum = Math.max(minimum, Number(trend?.reference_requirements?.image?.max ?? trend?.reference_requirements?.max ?? minimum));
  const videoCount = Number(trend?.reference_requirements?.video?.min || 0);
  const userFields = (trend?.user_fields || []).slice(0, 6);
  const qualityOptions = trend?.quality_options || [];
  const aspectRatioOptions = trend?.aspect_ratio_options || [];
  const chosenQuality = qualityOptions.find((option) => option.value === selectedQuality) || qualityOptions.find((option) => option.default) || qualityOptions[0] || null;
  const displayedCost = chosenQuality?.cost_rox || trend?.cost_rox;
  const displayedRetailCost = chosenQuality?.retail_cost_rox || trend?.retail_cost_rox;
  const adminFree = Boolean(chosenQuality?.admin_free ?? trend?.admin_free);
  const userFieldsReady = userFields.every((field) => userFieldValid(field, userValues[field.key] || ""));
  const aspectRatioReady = !aspectRatioOptions.length || Boolean(selectedAspectRatio);
  const ready = references.length >= minimum && (!maximum || references.length <= maximum) && videoReferences.length === videoCount && userFieldsReady && aspectRatioReady;
  const referenceCopy = useMemo(() => {
    if (!trend) return "";
    if (videoCount) return minimum
      ? `Добавьте ${minimum} фото и ${videoCount} видео. Запуск — после нажатия кнопки.`
      : `Добавьте ${videoCount} видео. Запуск — после нажатия кнопки.`;
    if (!minimum) return "Референсы не нужны — сценарий можно запустить сразу.";
    if (minimum === maximum) return `Добавьте ${minimum} ${minimum === 1 ? "изображение" : "изображения"}. Генерация начнётся только после нажатия кнопки.`;
    return `Добавьте от ${minimum} до ${maximum} изображений. Генерация начнётся только после нажатия кнопки.`;
  }, [maximum, minimum, videoCount, trend]);

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

  const addVideoFiles = async (files: File[]) => {
    if (uploading || running) return;
    const available = Math.max(0, videoCount - videoReferences.length);
    if (!available) return;
    setUploading(true);
    setError("");
    try {
      const next: Array<{ url: string; name: string }> = [];
      for (const file of files.filter((item) => item.type.startsWith("video/")).slice(0, available)) {
        const uploaded = await api.upload(file);
        if (uploaded.reference?.kind !== "video" || uploaded.probe_status !== "ready") {
          throw new Error("Не удалось проверить видео. Загрузите MP4 или MOV.");
        }
        next.push({ url: uploaded.url, name: file.name });
      }
      setVideoReferences((current) => [...current, ...next].slice(0, videoCount));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить видео");
    } finally {
      setUploading(false);
    }
  };

  const share = async () => {
    const id = trend?.id || workflow?.trend_id;
    if (!id || sharing) return;
    setSharing(true);
    setError("");
    haptic("light");
    try {
      const result = await api.shareTrend(id);
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
      const result = await api.runTrend(
        trend.id,
        references.map((item) => item.url),
        userValues,
        {
          ...(chosenQuality ? { resolution: chosenQuality.value } : {}),
          videoReferenceUrls: videoReferences.map((item) => item.url),
          ...(selectedAspectRatio ? { aspectRatio: selectedAspectRatio } : {}),
        },
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
      title={trend?.title || workflow?.title || (loading ? "Загружаю сценарий" : "Тренд")}
      copy={trend?.description || workflow?.description || "Готовый сценарий ROXY с описанием и настройками."}
    >
      {workflow?.workflow_type === "sequential_photo_video" ? (
        <TrendWorkflowRunner trend={trend} initialWorkflow={workflow} onShare={() => void share()} onCopy={() => void copyLink()} sharing={sharing} copying={copying} />
      ) : workflowRecovery && trend?.workflow_type === "sequential_photo_video" ? (
        <div className={styles.workflowRecovery} role="alert">
          <strong>Восстанавливаю сценарий</strong>
          <p>Создание сценария уже могло завершиться. Проверим owner-состояние перед новой попыткой.</p>
          <button className="secondary wide" type="button" disabled={running} onClick={() => void retryWorkflowRecovery()}>{running ? "Проверяю…" : "Проверить сценарий"}</button>
        </div>
      ) : trend ? (
        <div className="tool-grid">
          {trend.description?.trim() ? (
            <aside className={styles.instructions} role="note" aria-label="Инструкция к тренду">
              <strong>Перед запуском</strong>
              <p>{trend.description}</p>
            </aside>
          ) : null}
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
            {aspectRatioOptions.length ? (
              <section className={styles.quality} aria-label="Формат кадра">
                <div className={styles.qualityHead}>
                  <strong>Формат кадра *</strong>
                  <span>{selectedAspectRatio ? "Выбран" : "Обязательно"}</span>
                </div>
                <div className={styles.aspectOptions} role="radiogroup" aria-label="Формат кадра">
                  {aspectRatioOptions.map((option) => {
                    const active = option === selectedAspectRatio;
                    return (
                      <button
                        key={option}
                        type="button"
                        role="radio"
                        aria-checked={active}
                        onClick={() => {
                          haptic("light");
                          setSelectedAspectRatio(option);
                        }}
                      >
                        <span>{option}</span>
                      </button>
                    );
                  })}
                </div>
              </section>
            ) : null}
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

            {videoCount > 0 ? <div className="trend-video-references">
              <label className="upload-control">
                <span>{uploading ? "Загружаю…" : `Добавить видео · ${videoReferences.length}/${videoCount}`}</span>
                <input type="file" accept="video/mp4,video/quicktime" multiple={videoCount > 1}
                  aria-label="Видеореференсы тренда"
                  disabled={uploading || running || videoReferences.length >= videoCount}
                  onChange={(event) => {
                    const files = Array.from(event.currentTarget.files || []);
                    event.currentTarget.value = "";
                    void addVideoFiles(files);
                  }} />
              </label>
              <div className="tool-file-list">
                {videoReferences.map((item, index) => <div className="tool-file-chip" key={item.url}>
                  <span>{item.name}</span>
                  <button type="button" aria-label={`Удалить видео ${index + 1}`} disabled={running || uploading}
                    onClick={() => setVideoReferences((current) => current.filter((_, i) => i !== index))}>×</button>
                </div>)}
              </div>
            </div> : null}

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
