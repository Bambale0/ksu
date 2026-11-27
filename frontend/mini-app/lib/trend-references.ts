import type { TrendReferenceInput, TrendReferenceSchema, TrendReferenceSlot } from "./types";

export function referenceTitle(slot: TrendReferenceSlot): string {
  return `${slot.kind === "image" ? "Image" : "Video"}${slot.id.split("_")[1]} · ${slot.label}`;
}

export function referenceInputs(schema: TrendReferenceSchema, values: Record<string, string>): TrendReferenceInput[] {
  return schema.slots.filter(slot => slot.source === "user" && values[slot.id]).map(slot => ({
    slot_id: slot.id, kind: slot.kind, url: values[slot.id],
  }));
}

export function namedReferencesReady(schema: TrendReferenceSchema, values: Record<string, string>): boolean {
  const gaps: Record<string, boolean> = {};
  return schema.slots.every(slot => {
    const present = slot.source === "admin" || Boolean(values[slot.id]);
    if (slot.required && !present) return false;
    if (gaps[slot.kind] && present) return false;
    if (!present) gaps[slot.kind] = true;
    return true;
  });
}

export function extractReferenceSlots(prompt: string): TrendReferenceSlot[] {
  const counts: Record<"image" | "video", number> = { image: 0, video: 0 };
  for (const match of prompt.matchAll(/(?<![\w@])@?(image|video)_?([1-9][0-9]*)(?!\w)/gi)) {
    const kind = match[1].toLowerCase() as "image" | "video";
    counts[kind] = Math.max(counts[kind], Number(match[2]));
  }
  if (counts.image + counts.video > 16) throw new Error("Слишком много референсов в промпте. Проверьте номера.");
  return (["image", "video"] as const).flatMap(kind => Array.from({ length: counts[kind] }, (_, i) => ({
    id: `${kind}_${i + 1}`, label: `${kind === "image" ? "Фото" : "Видео"} ${i + 1}`, description: "",
    kind, source: "user" as const, required: true, order: kind === "image" ? i : counts.image + i,
  })));
}
