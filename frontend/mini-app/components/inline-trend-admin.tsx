"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "@/lib/api";
import type { TrendUserField, UiField } from "@/lib/types";
import { inferTemplateFieldType } from "@/lib/trend-user-fields";
import {
  trendAdminApi,
  type TrendAdminImageStep,
  type TrendAdminInput,
  type TrendAdminItem,
  type TrendAdminModel,
  type TrendAdminPayload,
  type TrendAdminV1Payload,
  type TrendAdminV2Payload,
  type TrendAdminVideoStep,
} from "@/lib/trend-admin-api";

const REFERENCE_FIELDS = new Set([
  "image_input",
  "image_urls",
  "input_urls",
  "reference_image_urls",
  "image_url",
  "first_frame_url",
  "first_frame",
]);
const SINGLE_REFERENCE_FIELDS = new Set(["image_url", "first_frame_url", "first_frame"]);
const BINDABLE_IMAGE_FIELDS = new Set([
  "first_frame_url",
  "first_frame",
  "reference_image",
  "reference_image_urls",
  "image_input",
  "image_urls",
  "input_urls",
]);
const I2V_OPERATIONS = new Set(["image_to_video", "text_or_image_to_video", "multimodal_video", "reference_to_video"]);
const TEMPLATE_FIELD_PRESETS = ["Возраст", "Имя", "Надпись", "Дата", "Число"] as const;
const WORKFLOW_TYPE = "sequential_photo_video" as const;

function normalizedAdminField(label: string): TrendUserField {
  const clean = label.replace(/[{}]/g, "").trim().slice(0, 48);
  return {
    key: clean,
    label: clean,
    type: inferTemplateFieldType(clean),
    required: true,
    max_length: 160,
  };
}

function previewIsVideo(url: string): boolean {
  return /\.(mp4|webm|mov|m4v)(?:[?#]|$)/i.test(url);
}

function modelAcceptsReferences(model?: TrendAdminModel | null): boolean {
  return Boolean(model?.known_fields?.some((field) => REFERENCE_FIELDS.has(field)));
}

function recipeParameters(value: string): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(value || "{}");
    if (parsed && !Array.isArray(parsed) && typeof parsed === "object") return parsed as Record<string, unknown>;
  } catch { /* Report one actionable error for malformed recipe JSON. */ }
  throw new Error("Дополнительные параметры должны быть корректным JSON-объектом");
}

function audioReferenceUrls(parameters: Record<string, unknown>): string[] {
  return Array.isArray(parameters.reference_audio_urls)
    ? parameters.reference_audio_urls.filter((url): url is string => typeof url === "string" && Boolean(url.trim()))
    : [];
}

function referenceCapacity(model?: TrendAdminModel | null): number {
  const advertised = Number(model?.reference_capacity);
  if (Number.isFinite(advertised) && advertised >= 0) return advertised;
  return model?.known_fields?.some((field) => SINGLE_REFERENCE_FIELDS.has(field)) ? 1 : 8;
}

type DraftBase = {
  title: string;
  description: string;
  previewUrl: string;
  sortOrder: number;
  tags: string;
  isActive: boolean;
};

type LegacyDraft = DraftBase & {
  mode: "legacy";
  modelId: string;
  prompt: string;
  userFields: TrendUserField[];
  inputMode: "none" | "image";
  minReferences: number;
  maxReferences: number;
  billingSeconds: string;
  parameters: string;
};

type WorkflowStepDraft = {
  title: string;
  instructions: string;
  previewUrl: string;
  modelId: string;
  prompt: string;
  parameters: Record<string, unknown>;
  inputs: TrendAdminInput[];
  bindingTarget?: string;
};

type WorkflowDraft = DraftBase & {
  mode: "workflow";
  sourcePayload: TrendAdminV2Payload;
  photo: WorkflowStepDraft;
  video: WorkflowStepDraft;
};

type Draft = LegacyDraft | WorkflowDraft;

function emptyDraft(modelId = ""): LegacyDraft {
  return {
    mode: "legacy",
    title: "",
    description: "",
    previewUrl: "",
    modelId,
    prompt: "",
    userFields: [],
    inputMode: "none",
    minReferences: 0,
    maxReferences: 0,
    billingSeconds: "",
    sortOrder: 0,
    tags: "trend",
    parameters: "{}",
    isActive: true,
  };
}

function modelUsesProviderDuration(model?: TrendAdminModel | null): boolean {
  return Boolean(
    model?.media_type === "video"
      && model.known_fields?.includes("duration")
      && model.required_fields?.includes("duration"),
  );
}

function isWorkflowPayload(payload: TrendAdminPayload): payload is TrendAdminV2Payload {
  return payload.schema_version === 2
    && payload.workflow_type === WORKFLOW_TYPE
    && Array.isArray(payload.steps)
    && payload.steps.length === 2
    && payload.steps[0]?.kind === "image"
    && payload.steps[1]?.kind === "video";
}

function cloneParameters(value: Record<string, unknown> | undefined): Record<string, unknown> {
  return value ? structuredClone(value) : {};
}

function workflowInput(input: TrendAdminInput, order: number): TrendAdminInput {
  return {
    id: input.id,
    label: input.label,
    help: input.help,
    type: input.type,
    required: input.required,
    order,
    ...(input.options ? { options: [...input.options] } : {}),
  };
}

function workflowBindingTarget(model: TrendAdminModel | undefined, current?: string): string {
  const known = new Set(model?.known_fields || []);
  const candidates = ["first_frame_url", "first_frame", "reference_image", "reference_image_urls", "image_input", "image_urls", "input_urls"]
    .filter((field) => known.has(field) && BINDABLE_IMAGE_FIELDS.has(field));
  if (current && candidates.includes(current)) return current;
  return candidates[0] || "";
}

function workflowModelSupportsI2V(model: TrendAdminModel | undefined): boolean {
  if (!model || model.media_type !== "video") return false;
  const capabilities = model.capabilities;
  const declared = Array.isArray(capabilities)
    ? capabilities
    : capabilities && typeof capabilities === "object"
      ? Object.entries(capabilities).filter(([, enabled]) => enabled).map(([key]) => key)
      : [];
  if (declared.includes("image_to_video") || declared.includes("i2v")) return true;
  return I2V_OPERATIONS.has(model.operation) && Boolean(model.known_fields?.some((field) => BINDABLE_IMAGE_FIELDS.has(field)));
}

function workflowParameterDefaults(model: TrendAdminModel | undefined): Record<string, unknown> {
  return cloneParameters(model?.ui_schema?.defaults);
}

function draftFrom(item: TrendAdminItem, models: TrendAdminModel[], duplicate = false): Draft {
  const rawPayload = item.payload;
  if (isWorkflowPayload(rawPayload)) {
    const payload = rawPayload;
    const [photo, video] = payload.steps;
    return {
      mode: "workflow",
      title: duplicate ? `${item.title} — копия` : item.title,
      description: String(payload.description || ""),
      previewUrl: String(payload.preview_url || ""),
      sortOrder: Number(payload.sort_order || 0),
      tags: Array.isArray(payload.tags) ? payload.tags.join(", ") : "trend",
      isActive: duplicate ? true : item.is_active !== false,
      sourcePayload: payload,
      photo: {
        title: photo.title,
        instructions: photo.instructions || "",
        previewUrl: String(photo.preview_url || ""),
        modelId: photo.model_id,
        prompt: photo.prompt,
        parameters: cloneParameters(photo.parameters),
        inputs: photo.inputs.map((input, order) => workflowInput(input, order)),
      },
      video: {
        title: video.title,
        instructions: video.instructions || "",
        previewUrl: String(video.preview_url || ""),
        modelId: video.model_id,
        prompt: video.prompt,
        parameters: cloneParameters(video.parameters),
        inputs: video.inputs.map((input, order) => workflowInput(input, order)),
        bindingTarget: video.bindings[0]?.to || workflowBindingTarget(models.find((model) => model.id === video.model_id)),
      },
    };
  }
  const payload = rawPayload as TrendAdminV1Payload;
  return {
    mode: "legacy",
    title: duplicate ? `${item.title} — копия` : item.title,
    description: String(payload.description || ""),
    previewUrl: String(payload.preview_url || ""),
    modelId: String(payload.model_id || ""),
    prompt: String(payload.prompt || ""),
    userFields: Array.isArray(payload.user_fields) ? payload.user_fields.slice(0, 6) : [],
    inputMode: payload.input_mode === "image" ? "image" : "none",
    minReferences: Number(payload.min_references || 0),
    maxReferences: Number(payload.max_references || 0),
    billingSeconds: payload.billing_seconds ? String(payload.billing_seconds) : "",
    sortOrder: Number(payload.sort_order || 0),
    tags: Array.isArray(payload.tags) ? payload.tags.join(", ") : "trend",
    parameters: JSON.stringify(payload.parameters || {}, null, 2),
    isActive: duplicate ? true : item.is_active !== false,
  };
}

function emptyWorkflowDraft(models: TrendAdminModel[]): WorkflowDraft {
  const photoModel = models.find((model) => model.media_type === "image");
  const videoModel = models.find((model) => workflowModelSupportsI2V(model));
  const photoInput: TrendAdminInput = {
    id: "person_photo",
    label: "Ваше фото",
    help: "Загрузите чёткое фото.",
    type: "image",
    required: true,
    order: 0,
  };
  return {
    mode: "workflow",
    title: "",
    description: "",
    previewUrl: "",
    sortOrder: 0,
    tags: "trend",
    isActive: true,
    sourcePayload: {
      schema_version: 2,
      workflow_type: WORKFLOW_TYPE,
      preview_url: "",
      steps: [
        {
          id: "prepare_photo",
          kind: "image",
          title: "Подготовить фото",
          instructions: "",
          model_id: photoModel?.id || "",
          prompt: "",
          parameters: workflowParameterDefaults(photoModel),
          inputs: [photoInput],
        },
        {
          id: "animate_photo",
          kind: "video",
          title: "Оживить фото",
          instructions: "",
          model_id: videoModel?.id || "",
          prompt: "",
          parameters: workflowParameterDefaults(videoModel),
          inputs: [],
          bindings: [{ from: "prepare_photo.output_image", to: workflowBindingTarget(videoModel) }],
        },
      ],
    },
    photo: {
      title: "Подготовить фото",
      instructions: "",
      previewUrl: "",
      modelId: photoModel?.id || "",
      prompt: "",
      parameters: workflowParameterDefaults(photoModel),
      inputs: [photoInput],
    },
    video: {
      title: "Оживить фото",
      instructions: "",
      previewUrl: "",
      modelId: videoModel?.id || "",
      prompt: "",
      parameters: workflowParameterDefaults(videoModel),
      inputs: [],
      bindingTarget: workflowBindingTarget(videoModel),
    },
  };
}

function modelParameterFields(model: TrendAdminModel | undefined): UiField[] {
  return (model?.ui_schema?.fields || []).filter((field) => (
    field.name !== "prompt"
    && !REFERENCE_FIELDS.has(field.name)
    && !field.name.endsWith("_urls")
  ));
}

function ModelParameterControls({
  model,
  parameters,
  onChange,
}: {
  model?: TrendAdminModel;
  parameters: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
}) {
  const fields = modelParameterFields(model);
  if (!fields.length) return <small>Для выбранной модели нет дополнительных управляемых параметров.</small>;
  return <div className="inline-trend-parameter-grid">
    {fields.map((field) => {
      const value = parameters[field.name];
      const label = `${field.label || field.name}${field.required ? " *" : ""}`;
      if (field.control === "toggle") {
        return <label className="inline-trend-checkbox" key={field.name}>
          <input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(field.name, event.target.checked)} />
          <span>{label}</span>
        </label>;
      }
      if (field.suggestions?.length) {
        return <label key={field.name}><span>{label}</span><select value={value == null ? "" : String(value)} onChange={(event) => onChange(field.name, event.target.value)}>
          {!field.required ? <option value="">Авто</option> : null}
          {field.suggestions.map((option) => <option value={String(option)} key={String(option)}>{String(option)}</option>)}
        </select></label>;
      }
      if (field.control === "json") {
        const jsonValue = value == null ? "" : JSON.stringify(value, null, 2);
        return <label key={field.name}><span>{label}</span><textarea rows={3} value={jsonValue} onChange={(event) => {
          try {
            onChange(field.name, event.target.value.trim() ? JSON.parse(event.target.value) : {});
          } catch {
            // Keep malformed JSON local to this control; backend validation remains authoritative.
          }
        }} /></label>;
      }
      return <label key={field.name}><span>{label}</span><input
        type={field.control === "number" ? "number" : "text"}
        min={field.min}
        max={field.max}
        step={field.step}
        value={value == null ? "" : String(value)}
        placeholder={field.placeholder || ""}
        onChange={(event) => onChange(field.name, field.control === "number" ? (event.target.value ? Number(event.target.value) : null) : event.target.value)}
      /></label>;
    })}
  </div>;
}

function WorkflowInputEditor({
  inputs,
  onChange,
}: {
  inputs: TrendAdminInput[];
  onChange: (inputs: TrendAdminInput[]) => void;
}) {
  const update = (index: number, patch: Partial<TrendAdminInput>) => {
    onChange(inputs.map((input, current) => current === index ? { ...input, ...patch } : input));
  };
  return <div className="inline-trend-workflow-inputs" role="group" aria-label="Входные слоты фото">
    <div className="inline-trend-section-heading"><strong>Входные слоты</strong><small>Слоты становятся полями формы пользователя. Порядок сохраняется на сервере.</small></div>
    {inputs.map((input, index) => <div className="inline-trend-workflow-input" key={`${input.id}-${index}`}>
      <div className="inline-trend-two-cols">
        <label><span>ID слота</span><input value={input.id} pattern="[a-zA-Z][a-zA-Z0-9_-]{0,63}" onChange={(event) => update(index, { id: event.target.value })} /></label>
        <label><span>Порядок</span><input value={index} readOnly aria-label={`Порядок слота ${index + 1}`} /></label>
      </div>
      <label><span>Метка</span><input value={input.label} maxLength={120} onChange={(event) => update(index, { label: event.target.value })} /></label>
      <label><span>Подсказка</span><textarea rows={2} maxLength={500} value={input.help} onChange={(event) => update(index, { help: event.target.value })} /></label>
      <div className="inline-trend-two-cols">
        <label><span>Содержимое поля</span><select value={input.type} onChange={(event) => update(index, { type: event.target.value as TrendAdminInput["type"], options: event.target.value === "select" ? (input.options || [""]) : undefined })}>
          {(["image", "text", "number", "date", "select"] as const).map((type) => <option value={type} key={type}>{{ image: "Фотография", text: "Текст", number: "Число", date: "Дата", select: "Выбор из списка" }[type]}</option>)}
        </select></label>
        <label className="inline-trend-checkbox"><input type="checkbox" checked={input.required} onChange={(event) => update(index, { required: event.target.checked })} /><span>Обязательное</span></label>
      </div>
      {input.type === "select" ? <label><span>Варианты через запятую</span><input value={(input.options || []).join(", ")} onChange={(event) => update(index, { options: event.target.value.split(",").map((option) => option.trim()).filter(Boolean) })} /></label> : null}
      <button className="inline-trend-secondary" type="button" onClick={() => onChange(inputs.filter((_, current) => current !== index))}>Удалить слот</button>
    </div>)}
    <button className="inline-trend-secondary" type="button" onClick={() => onChange([...inputs, { id: `input_${inputs.length + 1}`, label: "Новый вход", help: "Опишите входные данные.", type: "text", required: false, order: inputs.length }])}>＋ Добавить слот</button>
  </div>;
}

export function InlineTrendAdmin() {
  const [isAdmin, setIsAdmin] = useState(false);
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [open, setOpen] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [items, setItems] = useState<TrendAdminItem[]>([]);
  const [models, setModels] = useState<TrendAdminModel[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft());
  const [customFieldName, setCustomFieldName] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const draftVersion = useRef(0);
  const formRef = useRef<HTMLFormElement | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    void api.me()
      .then((me) => { if (alive) setIsAdmin(Boolean(me.is_admin)); })
      .catch(() => { if (alive) setIsAdmin(false); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    const sync = () => {
      const title = Array.from(document.querySelectorAll<HTMLElement>(".section-title h2"))
        .find((node) => node.textContent?.trim() === "Готовые сценарии");
      if (!title) {
        setHost(null);
        return;
      }
      const parent = title.closest<HTMLElement>(".section-title");
      if (!parent) return;
      let mount = parent.querySelector<HTMLElement>("[data-inline-trend-admin-host]");
      if (!mount) {
        mount = document.createElement("div");
        mount.dataset.inlineTrendAdminHost = "true";
        parent.appendChild(mount);
      }
      setHost(mount);
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [isAdmin]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await trendAdminApi.list();
      setItems(result.items || []);
      setModels((result.models || []) as TrendAdminModel[]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить тренды");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      if (formOpen) {
        draftVersion.current += 1;
        setFormOpen(false);
        return;
      }
      setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [formOpen, open]);

  useEffect(() => {
    if (!formOpen) return;
    const firstInput = formRef.current?.querySelector<HTMLInputElement>("input:not([type=checkbox]), textarea, select");
    firstInput?.focus();
  }, [formOpen]);

  const selectedModel = useMemo(
    () => draft.mode === "legacy" ? models.find((model) => model.id === draft.modelId) || null : null,
    [draft, models],
  );
  const referenceAllowed = draft.mode === "legacy" && modelAcceptsReferences(selectedModel);
  const audioAllowed = draft.mode === "legacy" && Boolean(selectedModel?.known_fields?.includes("reference_audio_urls"));
  const audioReferences = useMemo(() => {
    if (draft.mode !== "legacy") return [];
    try { return audioReferenceUrls(recipeParameters(draft.parameters)); }
    catch { return []; }
  }, [draft]);
  const capacity = referenceCapacity(selectedModel);
  const workflowPhotoModels = models.filter((model) => model.media_type === "image");
  const workflowVideoModels = models.filter((model) => workflowModelSupportsI2V(model) || (draft.mode === "workflow" && model.id === draft.video.modelId));

  const beginCreate = () => {
    draftVersion.current += 1;
    setUploading(false);
    const modelId = models[0]?.id || "";
    setEditingId(null);
    setDraft(emptyDraft(modelId));
    setCustomFieldName("");
    setError("");
    setFormOpen(true);
  };

  const chooseDraftMode = (mode: "legacy" | "workflow") => {
    if (mode === draft.mode) return;
    draftVersion.current += 1;
    setError("");
    setDraft(mode === "workflow" ? emptyWorkflowDraft(models) : emptyDraft(models[0]?.id || ""));
  };

  const beginEdit = (item: TrendAdminItem, duplicate = false) => {
    draftVersion.current += 1;
    setUploading(false);
    setOpen(true);
    setEditingId(duplicate ? null : item.id);
    setDraft(draftFrom(item, models, duplicate));
    setCustomFieldName("");
    setError("");
    setFormOpen(true);
  };

  const chooseModel = (modelId: string) => {
    if (draft.mode !== "legacy") return;
    const next = models.find((model) => model.id === modelId);
    setDraft((current) => current.mode === "legacy" ? ({
      ...current,
      modelId,
      inputMode: modelAcceptsReferences(next) ? current.inputMode : "none",
      minReferences: modelAcceptsReferences(next) && current.inputMode === "image" ? Math.max(1, current.minReferences || 1) : 0,
      maxReferences: modelAcceptsReferences(next) && current.inputMode === "image" ? Math.min(referenceCapacity(next), Math.max(1, current.maxReferences || 1)) : 0,
    }) : current);
  };

  const chooseInputMode = (inputMode: "none" | "image") => {
    if (draft.mode !== "legacy") return;
    if (inputMode === "image" && !referenceAllowed) return;
    setDraft((current) => current.mode === "legacy" ? ({
      ...current,
      inputMode,
      minReferences: inputMode === "image" ? 1 : 0,
      maxReferences: inputMode === "image" ? Math.min(capacity, Math.max(1, current.maxReferences || capacity)) : 0,
    }) : current);
  };

  const addUserField = (label: string) => {
    if (draft.mode !== "legacy") return;
    const field = normalizedAdminField(label);
    if (!field.key) return;
    setDraft((current) => {
      if (current.mode !== "legacy") return current;
      if (
        current.userFields.length >= 6
        || current.userFields.some((item) => item.key.toLowerCase() === field.key.toLowerCase())
      ) return current;
      return { ...current, userFields: [...current.userFields, field] };
    });
    setCustomFieldName("");
  };

  const removeUserField = (key: string) => {
    if (draft.mode !== "legacy") return;
    setDraft((current) => current.mode === "legacy" ? ({
      ...current,
      userFields: current.userFields.filter((field) => field.key !== key),
    }) : current);
  };

  const uploadPreview = async (file?: File) => {
    if (!file) return;
    if (!file.type.startsWith("image/") && !file.type.startsWith("video/")) {
      setError("Выберите изображение или видео");
      return;
    }
    const version = draftVersion.current;
    setUploading(true);
    setError("");
    try {
      const uploaded = await api.upload(file);
      if (draftVersion.current !== version) return;
      setDraft((current) => ({ ...current, previewUrl: uploaded.url }));
    } catch (cause) {
      if (draftVersion.current !== version) return;
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить превью");
    } finally {
      if (draftVersion.current === version) setUploading(false);
    }
  };

  const uploadWorkflowStepPreview = async (step: "photo" | "video", file?: File) => {
    if (!file || uploading || draft.mode !== "workflow") return;
    if (!file.type.startsWith("image/")) {
      setError("Для шага выберите изображение");
      return;
    }
    const version = draftVersion.current;
    setUploading(true);
    setError("");
    try {
      const uploaded = await api.upload(file);
      if (draftVersion.current !== version) return;
      setDraft((current) => current.mode === "workflow" ? {
        ...current,
        [step]: { ...current[step], previewUrl: uploaded.url },
      } : current);
    } catch (cause) {
      if (draftVersion.current !== version) return;
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить фото шага");
    } finally {
      if (draftVersion.current === version) setUploading(false);
    }
  };

  const uploadAudio = async (file?: File) => {
    if (!file || uploading || !audioAllowed || draft.mode !== "legacy") return;
    const version = draftVersion.current;
    setError("");
    try {
      const parameters = recipeParameters(draft.parameters);
      setUploading(true);
      const uploaded = await api.upload(file, "template-audio");
      if (draftVersion.current !== version) return;
      if (
        uploaded.reference?.kind !== "audio" || uploaded.probe_status !== "ready"
        || !Number.isFinite(uploaded.duration_ms) || Number(uploaded.duration_ms) <= 0
      ) {
        throw new Error("Не удалось определить длительность аудио. Выберите другой файл или загрузите его повторно.");
      }
      parameters.reference_audio_urls = [...new Set([...audioReferenceUrls(parameters), uploaded.url])];
      setDraft((current) => ({ ...current, parameters: JSON.stringify(parameters, null, 2) }));
    } catch (cause) {
      if (draftVersion.current === version) setError(cause instanceof Error ? cause.message : "Не удалось загрузить аудио");
    } finally {
      if (draftVersion.current === version) setUploading(false);
    }
  };

  const removeAudio = (index: number) => {
    if (draft.mode !== "legacy") return;
    try {
      const parameters = recipeParameters(draft.parameters);
      const urls = audioReferenceUrls(parameters).filter((_, position) => position !== index);
      if (urls.length) parameters.reference_audio_urls = urls;
      else delete parameters.reference_audio_urls;
      setDraft((current) => ({ ...current, parameters: JSON.stringify(parameters, null, 2) }));
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось удалить аудио");
    }
  };

  const save = async () => {
    if (saving || uploading) return;
    if (!draft.title.trim() || !draft.previewUrl.trim()) {
      setError("Добавьте название, превью, модель и скрытый промпт");
      return;
    }
    let payload: TrendAdminPayload;
    if (draft.mode === "workflow") {
      const photoModel = models.find((model) => model.id === draft.photo.modelId);
      const videoModel = models.find((model) => model.id === draft.video.modelId);
      if (photoModel?.media_type !== "image" || !photoModel.id) {
        setError("Выберите доступную модель для шага фото");
        return;
      }
      if (!videoModel || !workflowModelSupportsI2V(videoModel)) {
        setError("Выберите видео-модель с подтверждённой поддержкой I2V и входного изображения");
        return;
      }
      const knownVideoFields = new Set(videoModel.known_fields || []);
      const validBindingTargets = [...knownVideoFields].filter((field) => BINDABLE_IMAGE_FIELDS.has(field));
      if (draft.video.bindingTarget && !validBindingTargets.includes(draft.video.bindingTarget)) {
        setError("Выбранное поле привязки изображения не поддерживается этой видео-моделью");
        return;
      }
      const bindingTarget = workflowBindingTarget(videoModel, draft.video.bindingTarget);
      if (!bindingTarget) {
        setError("Видео-модель не объявляет совместимое поле для привязки результата фото");
        return;
      }
      if (!draft.photo.title.trim() || !draft.video.title.trim() || !draft.photo.prompt.trim() || !draft.video.prompt.trim()) {
        setError("Заполните названия и скрытые промпты обоих шагов");
        return;
      }
      const inputs = draft.photo.inputs.map((input, order) => ({ ...input, order }));
      if (inputs.some((input) => !/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(input.id) || !input.label.trim() || !input.help.trim())) {
        setError("Проверьте ID, метки и подсказки входных слотов фото");
        return;
      }
      if (new Set(inputs.map((input) => input.id)).size !== inputs.length) {
        setError("ID входных слотов фото не должны повторяться");
        return;
      }
      if (inputs.some((input) => input.type === "select" && (!input.options?.length || input.options.some((option) => !option)))) {
        setError("Для слота выбора добавьте хотя бы один непустой вариант");
        return;
      }
      const existingPhoto = draft.sourcePayload.steps[0];
      const existingVideo = draft.sourcePayload.steps[1];
      const photoStep: TrendAdminImageStep = {
        ...existingPhoto,
        id: existingPhoto.id,
        kind: "image",
        title: draft.photo.title.trim(),
        instructions: draft.photo.instructions.trim(),
        preview_url: draft.photo.previewUrl.trim() || undefined,
        model_id: photoModel.id,
        prompt: draft.photo.prompt.trim(),
        parameters: cloneParameters(draft.photo.parameters),
        inputs,
      };
      const videoStep: TrendAdminVideoStep = {
        ...existingVideo,
        id: existingVideo.id,
        kind: "video",
        title: draft.video.title.trim(),
        instructions: draft.video.instructions.trim(),
        preview_url: draft.video.previewUrl.trim() || undefined,
        model_id: videoModel.id,
        prompt: draft.video.prompt.trim(),
        parameters: cloneParameters(draft.video.parameters),
        inputs: draft.video.inputs.map((input, order) => workflowInput(input, order)),
        bindings: [{ from: `${photoStep.id}.output_image`, to: bindingTarget }],
      };
      payload = {
        ...draft.sourcePayload,
        schema_version: 2,
        workflow_type: WORKFLOW_TYPE,
        description: draft.description.trim(),
        preview_url: draft.previewUrl.trim(),
        tags: draft.tags.split(",").map((tag) => tag.trim().toLowerCase()).filter(Boolean).slice(0, 20),
        sort_order: Number(draft.sortOrder || 0),
        usage_count: Number(items.find((item) => item.id === editingId)?.payload.usage_count || 0),
        steps: [photoStep, videoStep],
      };
    } else {
      if (!draft.modelId || !draft.prompt.trim()) {
        setError("Добавьте название, превью, модель и скрытый промпт");
        return;
      }
      let parameters: Record<string, unknown>;
      try {
        parameters = recipeParameters(draft.parameters);
      } catch {
        setError("Дополнительные параметры должны быть корректным JSON-объектом");
        return;
      }
      const model = selectedModel;
      if (!model?.media_type) {
        setError("Выберите доступную модель");
        return;
      }
      const billingSeconds = draft.billingSeconds.trim() ? Number(draft.billingSeconds) : null;
      if (billingSeconds !== null && (!Number.isFinite(billingSeconds) || billingSeconds <= 0)) {
        setError("Длительность должна быть положительным числом секунд");
        return;
      }
      const userFields = draft.userFields.map((field) => normalizedAdminField(field.label));
      if (userFields.some((field) => !field.key)) {
        setError("Укажите название поля шаблона");
        return;
      }
      if (new Set(userFields.map((field) => field.key.toLowerCase())).size !== userFields.length) {
        setError("Названия полей шаблона не должны повторяться");
        return;
      }
      const legacyPayload: TrendAdminV1Payload = {
        description: draft.description.trim(),
        preview_url: draft.previewUrl.trim(),
        media_type: model.media_type,
        model_id: model.id,
        prompt: draft.prompt.trim(),
        user_fields: userFields.length ? userFields : undefined,
        parameters,
        input_mode: draft.inputMode,
        min_references: draft.inputMode === "image" ? Math.max(1, draft.minReferences) : 0,
        max_references: draft.inputMode === "image" ? Math.min(capacity, Math.max(draft.minReferences, draft.maxReferences)) : 0,
        tags: draft.tags.split(",").map((tag) => tag.trim().toLowerCase()).filter(Boolean).slice(0, 20),
        sort_order: Number(draft.sortOrder || 0),
        usage_count: Number(items.find((item) => item.id === editingId)?.payload.usage_count || 0),
      };
      payload = legacyPayload;
      if (billingSeconds !== null) {
        payload.billing_seconds = billingSeconds;
        if (modelUsesProviderDuration(model) && (parameters.duration === undefined || parameters.duration === null || parameters.duration === "")) {
          parameters.duration = billingSeconds;
        }
      }
      payload = legacyPayload;
    }

    const version = draftVersion.current;
    setSaving(true);
    setError("");
    try {
      const body = { title: draft.title.trim(), payload, is_active: draft.isActive };
      if (editingId) await trendAdminApi.update(editingId, body);
      else await trendAdminApi.create(body);
      if (draftVersion.current !== version) return;
      setFormOpen(false);
      setEditingId(null);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось сохранить тренд");
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (item: TrendAdminItem) => {
    if (busyId) return;
    setBusyId(item.id);
    setError("");
    try {
      if (item.is_active) await trendAdminApi.hide(item.id);
      else await trendAdminApi.activate(item.id);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось изменить видимость тренда");
    } finally {
      setBusyId(null);
    }
  };

  if (!isAdmin) return null;

  return <>
    {host ? createPortal(
      <button className="inline-trend-add-button" type="button" onClick={() => setOpen(true)} aria-label="Управлять трендами">
        <span>＋</span> Добавить
      </button>,
      host,
    ) : null}

    {open ? <div className="inline-trend-admin-overlay" role="dialog" aria-modal="true" aria-label="Управление трендами">
      <div className="inline-trend-admin-panel">
        <header className="inline-trend-admin-head">
          <div><span className="kicker">Админ</span><h2>Тренды</h2><p>Добавляйте и обновляйте готовые сценарии прямо из ROXY.</p></div>
          <button className="inline-trend-icon-button" type="button" onClick={() => { setOpen(false); setFormOpen(false); }} aria-label="Закрыть">×</button>
        </header>

        <div className="inline-trend-admin-toolbar">
          <button className="inline-trend-primary" type="button" onClick={beginCreate}>＋ Новый тренд</button>
          <button className="inline-trend-secondary" type="button" onClick={() => void refresh()} disabled={loading}>Обновить</button>
        </div>

        {error && !formOpen ? <div className="inline-trend-error" role="alert">{error}</div> : null}
        {loading ? <div className="inline-trend-empty">Загружаю тренды…</div> : null}
        {!loading && !items.length ? <div className="inline-trend-empty">Трендов пока нет. Создайте первый.</div> : null}

        <div className="inline-trend-admin-list">
          {items.map((item) => {
            const payload = item.payload || ({} as TrendAdminPayload);
            const video = !isWorkflowPayload(payload) && previewIsVideo(String(payload.preview_url || ""));
            const modelId = isWorkflowPayload(payload) ? payload.steps[0].model_id : payload.model_id;
            const model = models.find((entry) => entry.id === modelId);
            return <article className={`inline-trend-admin-card${item.is_active ? "" : " is-hidden"}`} key={item.id}>
              <div className="inline-trend-admin-preview">
                {payload.preview_url ? video
                  ? <video src={payload.preview_url} muted playsInline loop autoPlay preload="metadata" />
                  : <img src={payload.preview_url} alt="" loading="lazy" />
                  : <span>Нет превью</span>}
              </div>
              <div className="inline-trend-admin-card-body">
                <div className="inline-trend-admin-card-title"><strong>{item.title}</strong><span className={item.is_active ? "is-active" : ""}>{item.is_active ? "Активен" : "Скрыт"}</span></div>
                <small>{isWorkflowPayload(payload) ? "Фото → Видео" : `${model?.title || modelId || "Модель"} · ${payload.media_type === "video" ? "Видео" : "Фото"}`}</small>
                {payload.description ? <p>{payload.description}</p> : null}
                <div className="inline-trend-admin-actions">
                  <button type="button" onClick={() => beginEdit(item)}>Редактировать</button>
                  <button type="button" onClick={() => beginEdit(item, true)}>Дублировать</button>
                  <button type="button" className={item.is_active ? "danger" : ""} onClick={() => void toggleActive(item)} disabled={busyId === item.id}>{busyId === item.id ? "…" : item.is_active ? "Скрыть" : "Вернуть"}</button>
                </div>
              </div>
            </article>;
          })}
        </div>
      </div>
    </div> : null}

    {open && formOpen ? <div className="inline-trend-form-overlay" role="dialog" aria-modal="true" aria-label={editingId ? "Редактировать тренд" : "Добавить тренд"}>
      <form ref={formRef} className="inline-trend-form" onSubmit={(event) => { event.preventDefault(); void save(); }}>
        <header className="inline-trend-form-head"><div><span className="kicker">{editingId ? "Редактирование" : "Новый тренд"}</span><h2>{editingId ? draft.title || "Тренд" : "Добавить тренд"}</h2></div><button type="button" onClick={() => { draftVersion.current += 1; setFormOpen(false); }} aria-label="Закрыть">×</button></header>

        {error ? <div className="inline-trend-error" role="alert">{error}</div> : null}

        <label><span>Название</span><input value={draft.title} maxLength={80} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} placeholder="Например, Киношный портрет" required /></label>
        <label><span>Описание</span><textarea value={draft.description} maxLength={240} rows={2} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} placeholder="Что получит пользователь" /></label>

        <label><span>Тип шаблона</span><select value={draft.mode === "workflow" ? WORKFLOW_TYPE : "legacy"} onChange={(event) => chooseDraftMode(event.target.value === WORKFLOW_TYPE ? "workflow" : "legacy")} aria-label="Тип шаблона">
          <option value="legacy">Обычный шаблон</option>
          <option value={WORKFLOW_TYPE}>Фото → Видео</option>
        </select><small>Обычный шаблон сохраняет прежний v1-рецепт; workflow использует два серверно-каталогизированных шага.</small></label>

        <div className="inline-trend-two-cols">
          {draft.mode === "legacy" ? <label><span>Модель</span><select value={draft.modelId} onChange={(event) => chooseModel(event.target.value)} disabled={uploading} required><option value="">Выберите модель</option>{["image", "video"].map((kind) => <optgroup label={kind === "image" ? "Фото" : "Видео"} key={kind}>{models.filter((model) => model.media_type === kind).map((model) => <option value={model.id} key={model.id}>{model.title || model.id}</option>)}</optgroup>)}</select></label> : <div />}
          <label><span>Приоритет</span><input type="number" min={-100000} max={100000} value={draft.sortOrder} onChange={(event) => setDraft((current) => ({ ...current, sortOrder: Number(event.target.value || 0) }))} /></label>
        </div>

        <label><span>Загрузить превью</span><input aria-label="Загрузить превью" type="file" accept="image/*,video/*" onChange={(event) => { const input = event.currentTarget; const file = input.files?.[0]; input.value = ""; void uploadPreview(file); }} disabled={uploading} /><small>{uploading ? "Сохраняю файл в ROXY…" : "Фото или видео. Файл сохраняется постоянно."}</small></label>
        {draft.previewUrl ? <div className="inline-trend-form-preview">{previewIsVideo(draft.previewUrl) ? <video src={draft.previewUrl} muted playsInline controls /> : <img src={draft.previewUrl} alt="Превью тренда" />}</div> : null}
        <label><span>URL превью</span><input type="url" value={draft.previewUrl} onChange={(event) => setDraft((current) => ({ ...current, previewUrl: event.target.value }))} placeholder="https://…" required /></label>

        {draft.mode === "workflow" ? <>
          <section className="inline-trend-workflow-step" aria-labelledby="photo-step-heading">
            <div className="inline-trend-section-heading"><strong id="photo-step-heading">Шаг 1 · Фото</strong><small>Модель и поля берутся из серверного каталога.</small></div>
            <label><span>Загрузить фото шага 1</span><input aria-label="Загрузить фото шага 1" type="file" accept="image/*" disabled={uploading || saving} onChange={(event) => { const input = event.currentTarget; const file = input.files?.[0]; input.value = ""; void uploadWorkflowStepPreview("photo", file); }} /><small>Изображение для карточки первого шага.</small></label>
            {draft.photo.previewUrl ? <div className="inline-trend-form-preview"><img src={draft.photo.previewUrl} alt="Фото карточки шага 1" /></div> : null}
            <label><span>URL фото шага 1</span><input aria-label="URL фото шага 1" type="url" value={draft.photo.previewUrl} onChange={(event) => setDraft((current) => current.mode === "workflow" ? { ...current, photo: { ...current.photo, previewUrl: event.target.value } } : current)} placeholder="https://…" /></label>
            <label><span>Название шага фото</span><input value={draft.photo.title} onChange={(event) => setDraft((current) => current.mode === "workflow" ? { ...current, photo: { ...current.photo, title: event.target.value } } : current)} required /></label>
            <label><span>Модель фото</span><select value={draft.photo.modelId} onChange={(event) => setDraft((current) => current.mode === "workflow" ? { ...current, photo: { ...current.photo, modelId: event.target.value, parameters: workflowParameterDefaults(models.find((model) => model.id === event.target.value)) } } : current)} required><option value="">Выберите фото-модель</option>{workflowPhotoModels.map((model) => <option value={model.id} key={model.id}>{model.title || model.id}{model.price_rox ? ` · ${model.price_rox} ROX` : ""}</option>)}</select><small>Цена только для просмотра; расчёт тарифа остаётся на сервере.</small></label>
            <label><span>Инструкции к фото</span><textarea rows={2} value={draft.photo.instructions} onChange={(event) => setDraft((current) => current.mode === "workflow" ? { ...current, photo: { ...current.photo, instructions: event.target.value } } : current)} /></label>
            <label><span>Промпт фото</span><textarea rows={4} maxLength={8000} value={draft.photo.prompt} onChange={(event) => setDraft((current) => current.mode === "workflow" ? { ...current, photo: { ...current.photo, prompt: event.target.value } } : current)} placeholder="Скрытая инструкция для модели" required /></label>
            <ModelParameterControls model={models.find((model) => model.id === draft.photo.modelId)} parameters={draft.photo.parameters} onChange={(name, value) => setDraft((current) => current.mode === "workflow" ? { ...current, photo: { ...current.photo, parameters: { ...current.photo.parameters, [name]: value } } } : current)} />
            <WorkflowInputEditor inputs={draft.photo.inputs} onChange={(inputs) => setDraft((current) => current.mode === "workflow" ? { ...current, photo: { ...current.photo, inputs } } : current)} />
          </section>

          <section className="inline-trend-workflow-step" aria-labelledby="video-step-heading">
            <div className="inline-trend-section-heading"><strong id="video-step-heading">Шаг 2 · Видео</strong><small>Выберите реальную image-to-video модель и её объявленное поле первого кадра.</small></div>
            <label><span>Загрузить фото шага 2</span><input aria-label="Загрузить фото шага 2" type="file" accept="image/*" disabled={uploading || saving} onChange={(event) => { const input = event.currentTarget; const file = input.files?.[0]; input.value = ""; void uploadWorkflowStepPreview("video", file); }} /><small>Изображение для карточки второго шага.</small></label>
            {draft.video.previewUrl ? <div className="inline-trend-form-preview"><img src={draft.video.previewUrl} alt="Фото карточки шага 2" /></div> : null}
            <label><span>URL фото шага 2</span><input aria-label="URL фото шага 2" type="url" value={draft.video.previewUrl} onChange={(event) => setDraft((current) => current.mode === "workflow" ? { ...current, video: { ...current.video, previewUrl: event.target.value } } : current)} placeholder="https://…" /></label>
            <label><span>Название шага видео</span><input value={draft.video.title} onChange={(event) => setDraft((current) => current.mode === "workflow" ? { ...current, video: { ...current.video, title: event.target.value } } : current)} required /></label>
            <label><span>Модель видео</span><select aria-label="Модель видео" aria-describedby="workflow-video-model-help" value={draft.video.modelId} onChange={(event) => setDraft((current) => current.mode === "workflow" ? { ...current, video: { ...current.video, modelId: event.target.value, parameters: workflowParameterDefaults(models.find((model) => model.id === event.target.value)), bindingTarget: workflowBindingTarget(models.find((model) => model.id === event.target.value)) } } : current)} required><option value="">Выберите I2V-модель</option>{workflowVideoModels.map((model) => <option value={model.id} key={model.id}>{model.title || model.id}{model.price_rox ? ` · ${model.price_rox} ROX` : ""}</option>)}</select><small id="workflow-video-model-help">В список попадают только модели с серверно подтверждённой I2V-возможностью.</small></label>
            <label><span>Инструкции к видео</span><textarea rows={2} value={draft.video.instructions} onChange={(event) => setDraft((current) => current.mode === "workflow" ? { ...current, video: { ...current.video, instructions: event.target.value } } : current)} /></label>
            <label><span>Промпт видео</span><textarea rows={4} maxLength={8000} value={draft.video.prompt} onChange={(event) => setDraft((current) => current.mode === "workflow" ? { ...current, video: { ...current.video, prompt: event.target.value } } : current)} placeholder="Скрытая инструкция для модели" required /></label>
            <ModelParameterControls model={models.find((model) => model.id === draft.video.modelId)} parameters={draft.video.parameters} onChange={(name, value) => setDraft((current) => current.mode === "workflow" ? { ...current, video: { ...current.video, parameters: { ...current.video.parameters, [name]: value } } } : current)} />
            <label><span>Поле изображения видео</span><select value={draft.video.bindingTarget || ""} onChange={(event) => setDraft((current) => current.mode === "workflow" ? { ...current, video: { ...current.video, bindingTarget: event.target.value } } : current)}><option value="">Выберите поле привязки</option>{(models.find((model) => model.id === draft.video.modelId)?.known_fields || []).filter((field) => BINDABLE_IMAGE_FIELDS.has(field)).map((field) => <option value={field} key={field}>{field}</option>)}</select><small>{draft.video.bindingTarget ? `Результат шага фото будет передан в ${draft.video.bindingTarget}.` : "Модель не объявила совместимое поле."}</small></label>
          </section>
        </> : <>
          <label><span>Скрытый промпт</span><textarea value={draft.prompt} maxLength={8000} rows={5} onChange={(event) => setDraft((current) => ({ ...current, prompt: event.target.value }))} placeholder="Инструкция для модели. Пользователь её не увидит." required /></label>
        {draft.modelId === "seedance-2.5" ? <small>
          Для видео, которое загрузит пользователь, укажите @Video1 в промпте
          (далее @Video2 и т. д.). Превью служит только образцом результата.
        </small> : null}


          {audioAllowed || audioReferences.length ? <div className="inline-trend-user-fields-admin" role="group" aria-label="Аудиореференсы шаблона">
          <strong>Аудиореференсы для модели</strong>
          <small>Загрузите звук один раз — он будет использоваться при каждом запуске шаблона. В скрытом промпте укажите @Audio1 и опишите, как использовать звук. После удаления проверьте номера аудиореференсов в промпте.</small>
          {audioAllowed ? <label><span>Добавить аудиореференс</span><input type="file" accept="audio/*" disabled={uploading || saving} onChange={(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; void uploadAudio(file); }} /></label> : <small>Выбранная модель не поддерживает эти аудиореференсы. Удалите их или выберите другую модель.</small>}
          {uploading ? <small role="status">Сохраняю файл в ROXY…</small> : null}
          {audioReferences.map((url, index) => <div key={`${index}:${url}`}>
            <strong>@Audio{index + 1}</strong>
            <audio src={url} controls preload="none" style={{ width: "100%" }} aria-label={`Прослушать аудиореференс ${index + 1}`} />
            <button type="button" className="inline-trend-secondary" disabled={uploading || saving} onClick={() => removeAudio(index)} aria-label={`Удалить аудиореференс ${index + 1}`}>Удалить</button>
          </div>)}
          {!audioReferences.length ? <small>Аудио пока не добавлено.</small> : null}
          </div> : null}

          <div className="inline-trend-user-fields-admin">
          <div>
            <strong>Поля шаблона</strong>
            <small>Выберите только то, что пользователь сможет поменять. При повторе он увидит пустые поля с этими названиями и введёт свои значения. Остальное ROXY соберёт автоматически.</small>
          </div>

          <div className="inline-trend-field-presets">
            {TEMPLATE_FIELD_PRESETS.map((preset) => {
              const active = draft.userFields.some((field) => field.key.toLowerCase() === preset.toLowerCase());
              return <button className="inline-trend-secondary" key={preset} type="button" disabled={active || draft.userFields.length >= 6} onClick={() => addUserField(preset)}>＋ {preset}</button>;
            })}
          </div>

          <div className="inline-trend-custom-field">
            <input
              value={customFieldName}
              onChange={(event) => setCustomFieldName(event.target.value.slice(0, 48))}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  addUserField(customFieldName);
                }
              }}
              placeholder="Другое поле, например: Цвет волос"
            />
            <button className="inline-trend-secondary" type="button" disabled={!customFieldName.trim() || draft.userFields.length >= 6} onClick={() => addUserField(customFieldName)}>Добавить</button>
          </div>

          {draft.userFields.length ? <div className="inline-trend-selected-fields">
            {draft.userFields.map((field) => <div className="inline-trend-selected-field" key={field.key}>
              <div><small>Название поля</small><strong>{field.label}</strong></div>
              <button className="inline-trend-secondary" type="button" aria-label={`Удалить поле ${field.label}`} onClick={() => removeUserField(field.key)}>Удалить</button>
            </div>)}
          </div> : <small>Если пользователь ничего менять не должен — оставьте блок пустым.</small>}
          </div>

          <div className="inline-trend-two-cols">
          <label><span>Что загружает пользователь</span><select value={draft.inputMode} onChange={(event) => chooseInputMode(event.target.value as "none" | "image")}><option value="none">Ничего</option><option value="image" disabled={!referenceAllowed}>Фото / референс</option></select><small>{referenceAllowed ? "Модель поддерживает референсы" : "У выбранной модели нет входного изображения"}</small></label>
          <label><span>Длительность, сек</span><input type="number" min={1} value={draft.billingSeconds} onChange={(event) => setDraft((current) => ({ ...current, billingSeconds: event.target.value }))} placeholder="Авто" /></label>
          </div>

          {draft.inputMode === "image" ? <div className="inline-trend-two-cols"><label><span>Минимум фото</span><input type="number" min={1} max={capacity} value={draft.minReferences} onChange={(event) => setDraft((current) => current.mode === "legacy" ? ({ ...current, minReferences: Math.min(capacity, Math.max(1, Number(event.target.value || 1))) }) : current)} /></label><label><span>Максимум фото</span><input type="number" min={draft.minReferences} max={capacity} value={draft.maxReferences} onChange={(event) => setDraft((current) => current.mode === "legacy" ? ({ ...current, maxReferences: Math.min(capacity, Math.max(current.minReferences, Number(event.target.value || current.minReferences))) }) : current)} /></label></div> : null}

          <details className="inline-trend-advanced"><summary>Дополнительные параметры модели</summary><label><span>JSON параметров</span><textarea rows={7} spellCheck={false} value={draft.parameters} disabled={uploading} onChange={(event) => setDraft((current) => ({ ...current, parameters: event.target.value }))} /></label></details>
        </>}

        <label><span>Теги</span><input value={draft.tags} onChange={(event) => setDraft((current) => ({ ...current, tags: event.target.value }))} placeholder="trend, portrait" /><small>Через запятую, максимум 20.</small></label>

        {editingId ? <label className="inline-trend-checkbox"><input type="checkbox" checked={draft.isActive} onChange={(event) => setDraft((current) => ({ ...current, isActive: event.target.checked }))} /><span>Показывать пользователям</span></label> : null}

        <div className="inline-trend-form-actions"><button className="inline-trend-secondary" type="button" onClick={() => setFormOpen(false)}>Отмена</button><button className="inline-trend-primary" type="submit" disabled={saving || uploading}>{saving ? "Сохраняю…" : editingId ? "Сохранить" : "Опубликовать тренд"}</button></div>
      </form>
    </div> : null}

    <style jsx global>{`
      [data-inline-trend-admin-host] { display:flex; align-items:center; margin-left:auto; }
      .inline-trend-add-button { border:1px solid rgba(198,120,255,.42); background:rgba(155,74,255,.16); color:#d99aff; border-radius:999px; padding:9px 13px; font:700 13px/1 inherit; box-shadow:0 0 24px rgba(173,83,255,.16); }
      .inline-trend-add-button span { font-size:17px; line-height:0; margin-right:3px; }
      .inline-trend-admin-overlay,.inline-trend-form-overlay { position:fixed; inset:0; z-index:140; background:rgba(2,1,5,.78); backdrop-filter:blur(12px); display:flex; justify-content:center; align-items:flex-end; }
      .inline-trend-form-overlay { z-index:150; }
      .inline-trend-admin-panel,.inline-trend-form { width:min(100%,720px); max-height:94dvh; overflow:auto; background:#0b0910; border:1px solid rgba(255,255,255,.1); border-radius:24px 24px 0 0; padding:18px 16px calc(24px + env(safe-area-inset-bottom)); box-shadow:0 -20px 80px rgba(0,0,0,.5); }
      .inline-trend-admin-head,.inline-trend-form-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
      .inline-trend-admin-head h2,.inline-trend-form-head h2 { margin:2px 0 4px; font-size:26px; }
      .inline-trend-admin-head p { margin:0; color:#aaa2b4; font-size:13px; }
      .inline-trend-icon-button,.inline-trend-form-head>button { width:38px; height:38px; border-radius:50%; border:1px solid rgba(255,255,255,.12); background:#17131d; color:#fff; font-size:24px; }
      .inline-trend-admin-toolbar,.inline-trend-form-actions { display:flex; gap:10px; margin:16px 0; }
      .inline-trend-primary,.inline-trend-secondary { min-height:42px; border-radius:13px; padding:0 15px; font-weight:800; }
      .inline-trend-primary { border:0; background:linear-gradient(135deg,#a84dff,#d66cff); color:#fff; box-shadow:0 10px 30px rgba(172,68,255,.22); }
      .inline-trend-secondary { border:1px solid rgba(255,255,255,.11); background:#17131d; color:#fff; }
      .inline-trend-admin-list { display:grid; gap:12px; }
      .inline-trend-admin-card { display:grid; grid-template-columns:104px minmax(0,1fr); overflow:hidden; border:1px solid rgba(255,255,255,.09); border-radius:18px; background:#110e16; }
      .inline-trend-admin-card.is-hidden { opacity:.62; }
      .inline-trend-admin-preview { min-height:120px; background:#050407; display:grid; place-items:center; color:#766e80; }
      .inline-trend-admin-preview img,.inline-trend-admin-preview video { width:100%; height:100%; min-height:120px; object-fit:cover; }
      .inline-trend-admin-card-body { min-width:0; padding:12px; }
      .inline-trend-admin-card-title { display:flex; gap:8px; justify-content:space-between; align-items:flex-start; }
      .inline-trend-admin-card-title strong { font-size:14px; }
      .inline-trend-admin-card-title span { flex:0 0 auto; border-radius:999px; padding:4px 7px; background:#28212f; color:#aaa2b4; font-size:10px; font-weight:800; }
      .inline-trend-admin-card-title span.is-active { background:rgba(75,214,132,.13); color:#79e6a7; }
      .inline-trend-admin-card-body>small { display:block; margin-top:4px; color:#8f8798; }
      .inline-trend-admin-card-body>p { margin:8px 0; color:#bdb6c6; font-size:12px; }
      .inline-trend-admin-actions { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }
      .inline-trend-admin-actions button { border:1px solid rgba(255,255,255,.1); background:#1b1721; color:#eee9f4; border-radius:9px; padding:7px 9px; font-size:11px; font-weight:700; }
      .inline-trend-admin-actions button.danger { color:#ff9aa9; }
      .inline-trend-empty { padding:26px; text-align:center; color:#91899a; }
      .inline-trend-error { margin:12px 0; border:1px solid rgba(255,95,116,.28); background:rgba(255,78,103,.09); color:#ffb0bc; border-radius:12px; padding:10px 12px; font-size:12px; }
      .inline-trend-form { display:grid; gap:13px; }
      .inline-trend-form label { display:grid; gap:7px; color:#dcd6e3; font-size:12px; font-weight:700; }
      .inline-trend-form label>small { color:#81798b; font-weight:500; }
      .inline-trend-form input:not([type=checkbox]),.inline-trend-form textarea,.inline-trend-form select { width:100%; border:1px solid rgba(255,255,255,.1); background:#15111b; color:#fff; border-radius:12px; padding:11px 12px; outline:none; font:inherit; }
      .inline-trend-form input:focus,.inline-trend-form textarea:focus,.inline-trend-form select:focus { border-color:rgba(203,105,255,.65); box-shadow:0 0 0 3px rgba(174,72,255,.09); }
      .inline-trend-two-cols { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
      .inline-trend-workflow-step { display:grid; gap:11px; border:1px solid rgba(203,105,255,.18); border-radius:16px; background:rgba(31,20,42,.42); padding:13px; }
      .inline-trend-section-heading { display:grid; gap:4px; }
      .inline-trend-section-heading small { color:#91889c; font-weight:500; }
      .inline-trend-parameter-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; border-top:1px solid rgba(255,255,255,.07); padding-top:10px; }
      .inline-trend-workflow-inputs { display:grid; gap:10px; border-top:1px solid rgba(255,255,255,.07); padding-top:10px; }
      .inline-trend-workflow-input { display:grid; gap:9px; border:1px solid rgba(255,255,255,.08); border-radius:13px; padding:10px; background:#120f18; }
      .inline-trend-user-fields-admin { display:grid; gap:10px; border:1px solid rgba(255,255,255,.08); border-radius:16px; background:#100d15; padding:12px; }
      .inline-trend-user-fields-admin>div:first-child { display:grid; gap:5px; }
      .inline-trend-user-fields-admin small { color:#81798b; font-weight:500; }
      .inline-trend-field-presets { display:flex; flex-wrap:wrap; gap:7px; }
      .inline-trend-field-presets .inline-trend-secondary { min-height:36px; padding:0 11px; font-size:11px; }
      .inline-trend-custom-field { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:8px; align-items:center; }
      .inline-trend-selected-fields { display:grid; gap:8px; }
      .inline-trend-selected-field { display:flex; align-items:center; justify-content:space-between; gap:10px; border:1px solid rgba(255,255,255,.08); border-radius:12px; background:#15111b; padding:10px; }
      .inline-trend-selected-field>div { min-width:0; display:grid; gap:2px; }
      .inline-trend-selected-field strong { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
      .inline-trend-form-preview { max-height:260px; overflow:hidden; border-radius:16px; background:#050407; }
      .inline-trend-form-preview img,.inline-trend-form-preview video { width:100%; max-height:260px; object-fit:contain; display:block; }
      .inline-trend-advanced { border:1px solid rgba(255,255,255,.08); border-radius:14px; padding:11px 12px; }
      .inline-trend-advanced summary { cursor:pointer; color:#bcb4c6; font-size:12px; font-weight:800; }
      .inline-trend-advanced label { margin-top:12px; }
      .inline-trend-checkbox { display:flex!important; grid-template-columns:none!important; align-items:center; gap:9px!important; }
      .inline-trend-checkbox input { width:18px; height:18px; accent-color:#b455ff; }
      .inline-trend-form-actions { justify-content:flex-end; margin-bottom:0; }
      @media (max-width:520px) { .inline-trend-two-cols,.inline-trend-custom-field,.inline-trend-parameter-grid { grid-template-columns:1fr; } .inline-trend-admin-card { grid-template-columns:88px minmax(0,1fr); } }
    `}</style>
  </>;
}
