import type { TrendAdminInput } from "./trend-admin-api";

// The recipe schema accepts at most sixteen inputs across all types.
const MAX_INPUTS = 16;

function photoNumbers(prompt: string): number[] {
  return [...new Set(Array.from(prompt.matchAll(/@Image(\d+)/gi), (match) => Number(match[1])))].sort((a, b) => a - b);
}

function scalarKeys(prompt: string): string[] {
  return [...new Set(Array.from(prompt.matchAll(/\{\{([^{}]+)\}\}/g), (match) => match[1].trim()))];
}

export function workflowInputReferenced(prompt: string, inputs: TrendAdminInput[], index: number): boolean {
  const input = inputs[index];
  return input.type === "image"
    ? photoNumbers(prompt).includes(inputs.slice(0, index + 1).filter((field) => field.type === "image").length)
    : scalarKeys(prompt).includes(input.id);
}

export function workflowPromptError(prompt: string, capacity: number, kind: "image" | "video"): string {
  const numbers = photoNumbers(prompt);
  if (!numbers.length) return "";
  if (kind === "video" && (numbers.length !== 1 || numbers[0] !== 1)) {
    return "Шаг 2 использует только готовое фото первого шага. В промпте видео можно указать только @Image1.";
  }
  if (numbers.some((number, index) => number !== index + 1)) {
    return "Укажите фотографии по порядку: @Image1, @Image2, @Image3 — без пропусков.";
  }
  if (numbers.length > Math.min(capacity, MAX_INPUTS)) {
    return `Выбранная модель поддерживает не более ${Math.min(capacity, MAX_INPUTS)} фото. Уберите лишние ссылки из промпта или выберите другую модель.`;
  }
  return "";
}

export function syncWorkflowPromptInputs(prompt: string, current: TrendAdminInput[], capacity: number): TrendAdminInput[] {
  // Never delete/reorder configured fields or infer business-specific meanings.
  const inputs = current.map((input) => ({ ...input }));
  if (!workflowPromptError(prompt, capacity, "image")) {
    const count = photoNumbers(prompt).length;
    let photos = inputs.filter((input) => input.type === "image").length;
    while (photos < count && inputs.length < MAX_INPUTS) {
      photos += 1;
      let id = `photo_${photos}`;
      while (inputs.some((input) => input.id === id)) id += "_";
      inputs.push({
        id, label: photos === 1 ? "Ваше фото" : `Фото ${photos}`,
        help: `Загрузите фотографию для @Image${photos}.`,
        type: "image", required: photos === 1, order: inputs.length,
      });
    }
  }
  for (const id of scalarKeys(prompt)) {
    if (!/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(id)) continue;
    if (inputs.length >= MAX_INPUTS || inputs.some((input) => input.id === id)) continue;
    inputs.push({ id, label: id, help: `Укажите значение поля «${id}».`, type: "text", required: true, order: inputs.length });
  }
  return inputs.map((input, order) => ({ ...input, order }));
}

export function workflowInputError(inputs: TrendAdminInput[], prompt: string, capacity: number): string {
  const images = inputs.filter((input) => input.type === "image");
  if (scalarKeys(prompt).some((id) => !/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(id))) {
    return "Для ключа поля используйте латинские буквы, цифры и подчёркивание; начните с буквы.";
  }
  if (images.length > capacity) return `Выбранная модель поддерживает не более ${capacity} фото. Удалите лишние поля фото или выберите другую модель.`;
  if (photoNumbers(prompt).some((number) => number > images.length)
    || scalarKeys(prompt).some((id) => !inputs.some((input) => input.type !== "image" && input.id === id))) {
    return "Для всех ссылок в промпте нужны поля пользователя. В одном шаге можно добавить не более 16 полей.";
  }
  if (photoNumbers(prompt).length) {
    const numbers = photoNumbers(prompt);
    if (images.some((image, index) => image.required && !numbers.includes(index + 1))) {
      return "Укажите в промпте ссылку для каждого обязательного фото.";
    }
    let optionalSeen = false;
    for (const image of images) {
      if (!image.required) optionalSeen = true;
      else if (optionalSeen) return "Разместите обязательные фото перед необязательными.";
    }
  }
  return "";
}

export function klingTrendRequiredImages(prompt: string): number {
  const matches = Array.from(prompt.matchAll(/@image_([1-9][0-9]*)(?!\\w)/gi));
  if (!matches.length) return 0;
  const values = matches.map((match) => Number(match[1])).filter((value) => Number.isSafeInteger(value));
  return values.length ? Math.max(...values) : 0;
}

export function trendSaveError(cause: unknown): string {
  const message = cause instanceof Error ? cause.message : "";
  if (/Undeclared reference @image[_ ]?([1-9][0-9]*)/i.test(message)) {
    const number = message.match(/@image[_ ]?([1-9][0-9]*)/i)?.[1];
    return `Для промпта требуется фото №${number || "2"}. Укажите правильное количество изображений в шаблоне.`;
  }
  if (/HTTP 50[234]|Bad Gateway|gateway timeout|service unavailable/i.test(message)) {
    return "Не удалось подтвердить сохранение: временная ошибка связи с сервером. Проверьте список трендов и повторите попытку, если записи нет.";
  }
  if (message.includes("@ImageN") || message.includes("ordered image input slots")) {
    return "Проверьте поля фото и номера @Image в промптах обоих шагов. В шаге видео используется только @Image1.";
  }
  return message || "Не удалось сохранить тренд";
}
