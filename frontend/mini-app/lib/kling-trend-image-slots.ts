/** Ordered customer image slots for a one-stage Kling 4.0 trend.
 * Provider references are matched by prompt order, not by preview URL.
 */
export type LegacyImageDraft = {
  prompt: string;
  inputMode: "none" | "image";
  minReferences: number;
  maxReferences: number;
};

export function klingTrendImageSlots(prompt: string): number[] {
  return [...new Set(Array.from(
    prompt.matchAll(/@image_?([1-9][0-9]*)(?!\w)/gi),
    (match) => Number(match[1]),
  ))].sort((a, b) => a - b);
}

export function klingTrendPromptError(prompt: string, capacity: number): string {
  const slots = klingTrendImageSlots(prompt);
  if (/@video_?[1-9][0-9]*(?!\w)/i.test(prompt)) {
    return "Видео из промпта нельзя использовать как превью. Для видеореференса выберите подходящий шаблон.";
  }
  if (slots.some((slot, index) => slot !== index + 1)) {
    return "Укажите номера фотографий по порядку, начиная с @image_1.";
  }
  if (slots.length > capacity) {
    return `Эта модель поддерживает не более ${capacity} фото. Уберите лишние ссылки из промпта.`;
  }
  return "";
}

export function syncKlingTrendImages<T extends LegacyImageDraft>(
  draft: T, prompt: string, modelId: string, capacity: number,
): T {
  const next = { ...draft, prompt };
  if (modelId !== "kling-4.0" || klingTrendPromptError(prompt, capacity)) return next;
  const count = klingTrendImageSlots(prompt).length;
  if (!count) return next;
  return {
    ...next,
    inputMode: "image",
    minReferences: Math.min(capacity, Math.max(count, next.minReferences)),
    maxReferences: Math.min(capacity, Math.max(count, next.minReferences, next.maxReferences)),
  } as T;
}
