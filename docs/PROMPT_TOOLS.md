# Prompt Tools

Epic #42 ports the useful product contracts of the `banano_kling:tanyapi` image/prompt analyzers into KSU without copying the legacy synchronous handler implementation.

## Product surfaces

Two user tools share one durable domain:

- `image_analysis` — «Промпт по фото»: structured visual analysis for composition, subjects, style, lighting, colors, camera/angle, details and generation notes.
- `prompt_builder` — «Улучшить промпт»: returns semantically equivalent `prompt_ru` and `prompt_en` from user text and an optional image reference.

Telegram exposes the tools from the main menu and through `/prompt_tools`, `/photo_prompt` and `/prompt`. The actual image upload and result interaction happen in `/mini-app/prompt-tools.html` so Telegram bot file URLs containing bot credentials are never forwarded to an external AI provider.

## Provider contract

KSU uses the configured Kie API key on the server only.

- image analysis: Gemini 2.5 Pro chat-completions endpoint with a strict JSON response schema;
- prompt builder: GPT-5.5 Responses endpoint with mixed text/image input and JSON-only output instructions.

The system prompts deliberately do not copy the old uncensored legacy image-analyzer instruction. The tools describe observable visual properties, do not attempt real-person identification from images and do not infer sensitive personal attributes.

## Pricing

Prompt по описанию and Prompt по фото have fixed public product prices:

```json
{
  "prompt_builder": "1.00",
  "image_analysis": "1.00"
}
```

These two prices are not overridden by the latest published `TariffVersion.payload.prompt_costs`; this keeps customer-facing billing stable even when model/provider routing changes. Prompt по видео keeps the tariff/default pricing path:

```json
{
  "prompt_costs": {
    "video_prompt": "30.00"
  }
}
```

The video value above is an example/default. If a tool has no resolved positive price it is returned as `enabled=false` and task creation fails closed with HTTP 503.

The normal internal-credit conversion is used for the RUB preview, so the existing rule `1 internal credit = 10 RUB` remains authoritative.

## Durable lifecycle

`PromptToolTask` stores the owner, tool, status, server-selected provider/model, sanitized input metadata, structured result, user credit cost and optional Kie provider-credit usage.

`PromptToolOutbox` provides a durable lease/retry queue. Task creation, outbox creation and wallet debit are committed together. The API requires `Idempotency-Key`; KSU deterministically derives the task UUID from `(user_id, idempotency_key)`, so the same request cannot create a second debit.

The dedicated `prompt-tools-worker`:

1. leases one outbox row with `FOR UPDATE SKIP LOCKED`;
2. calls the server-owned provider adapter;
3. stores structured result and completes the outbox atomically; or
4. retries with bounded exponential delay;
5. on terminal failure marks the task failed and credits the full user charge back with an idempotent wallet key.

Provider-side chat calls do not currently expose a KSU-controlled idempotency key. A worker crash after the external provider accepted a request but before the DB result commit may therefore repeat provider consumption on recovery; the user is never charged twice. This is an explicit provider-boundary compromise.

## API

Authenticated endpoints:

- `GET /api/v1/prompt-tools` — enabled state and current authoritative prices.
- `POST /api/v1/prompt-tools/image-analysis` — body: `image_url`, optional `instruction`; requires `Idempotency-Key`.
- `POST /api/v1/prompt-tools/prompt-builder` — body: `text`, optional `image_url`; requires `Idempotency-Key`.
- `GET /api/v1/prompt-tools/{task_id}` — owner-only status/result.

Clients cannot submit model, provider, price, provider settings or billing metadata.

## Input safety

Image URLs must be HTTPS and obvious loopback/local hosts are rejected. The browser uploads files through the existing authenticated `/api/v1/uploads/kie` path and submits the resulting remote URL. User text/instructions are bounded before provider execution.

## Deployment

Apply Alembic migration `0017_prompt_tools`, then deploy the API/bot and start the `prompt-tools-worker` service included in `docker-compose.notifications.yml`.

The worker reuses the existing generation-worker poll/lease/max-attempt configuration until a dedicated operational tuning need appears; this avoids another set of environment variables before real workload data exists.
