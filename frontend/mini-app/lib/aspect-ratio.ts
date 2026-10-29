import type { UiField, UiSchema } from "./types";

export type AspectRatioOptions = {
  aspect_ratio_options?: string[];
  aspect_ratio_required?: boolean;
  default_aspect_ratio?: string | null;
};

export function isAutomaticAspectRatio(value: unknown): boolean {
  return typeof value === "string" && value.trim().toLowerCase() === "auto";
}

export function explicitAspectRatioOptions(options?: Array<string | number>): string[] {
  return (options || []).filter((value) => !isAutomaticAspectRatio(value)).map(String);
}

// An empty value records that an old automatic choice needs user input. Deleting
// it would allow a model's explicit default to silently replace the old choice.
export function normalizeAspectRatioValues(values?: Record<string, unknown>): Record<string, unknown> {
  const next = { ...values };
  if (isAutomaticAspectRatio(next.aspect_ratio)) next.aspect_ratio = "";
  return next;
}

export function normalizeAspectRatioFields(schema?: UiSchema): UiField[] {
  return (schema?.fields || []).map((field) => field.name === "aspect_ratio" ? {
    ...field,
    suggestions: explicitAspectRatioOptions(field.suggestions),
    required: Boolean(field.required || isAutomaticAspectRatio(schema?.defaults?.aspect_ratio)),
  } : field);
}

export function aspectRatioError(field: UiField, value: unknown): string {
  if (field.name !== "aspect_ratio") return "";
  if (isAutomaticAspectRatio(value) || value === "" || (field.required && value == null)) {
    return "Выберите соотношение сторон";
  }
  // Other values keep their existing server-side validation. In particular,
  // restored source-driven modes may be valid without being public suggestions.
  return "";
}

export function selectedAspectRatio(options: AspectRatioOptions): string {
  const value = options.default_aspect_ratio;
  return value && explicitAspectRatioOptions(options.aspect_ratio_options).includes(value) ? value : "";
}

export function isAspectRatioReady(options: AspectRatioOptions, value: string): boolean {
  return (!options.aspect_ratio_required && !value)
    || explicitAspectRatioOptions(options.aspect_ratio_options).includes(value);
}
