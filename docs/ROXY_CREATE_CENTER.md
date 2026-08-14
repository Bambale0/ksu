# ROXY Create Center

The primary `Создать` route is media-first. Users choose the output class before choosing a provider/model.

## Product flow

1. `Фото`
2. `Видео`
3. `Музыка` — visible as a disabled next-stage entry until the dedicated music-domain epic (#128) is implemented.
4. After Photo/Video selection, ROXY opens the existing schema-driven builder with a compatible model.
5. The model catalog, dynamic fields, references, presets, server quote and generation lifecycle remain authoritative.

The Create Center does **not** implement its own pricing or generation POST request. It only selects a compatible model and hands control to the existing builder.

## Embedded AI prompt helper

The builder receives an additive AI helper panel. It uses the existing paid `prompt_builder` task lifecycle and pricing:

- improve the current prompt;
- optionally upload a photo reference;
- build a prompt from the photo reference;
- use server-owned purpose context for image vs video prompts;
- return Russian and English production-ready prompt variants;
- explicitly apply one variant back to the active schema-driven `prompt` field.

The helper uses the normal `Idempotency-Key`, wallet debit/refund and outbox processing contracts. It never edits the generation price or bypasses the generation quote.

## Prompt purpose

`POST /api/v1/prompt-tools/prompt-builder` accepts:

```json
{
  "text": "user idea",
  "image_url": null,
  "purpose": "video"
}
```

Allowed purposes are `general`, `image`, and `video`. The API converts `image` / `video` into bounded server-owned context before creating the existing `prompt_builder` task. Public clients still cannot choose the model, provider or price.

For video, the instruction asks the prompt model to describe temporal action, camera/object movement, scene dynamics, continuity and final state. For images, it emphasizes composition, camera/angle, lighting, materials, palette and style.

## Music boundary

Music is intentionally not faked through the current image/video model catalog. The current model contract supports image/video and the separate #128 epic adds provider/model, pricing, queue, storage, history and audio-player semantics before the Music card becomes active.
