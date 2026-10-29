# Prompt Tools

Epic #42 ports the useful product contracts of the `banano_kling:tanyapi` image/prompt analyzers into KSU without copying the legacy synchronous handler implementation.

## Product surfaces

Three user tools share one durable domain:

- `image_analysis` — «Промпт по фото»: structured visual analysis for composition, subjects, style, lighting, colors, camera/angle, details and generation notes.
- `prompt_builder` — «Улучшить промпт»: returns semantically equivalent `prompt_ru` and `prompt_en` from user text and an optional image reference.
- `video_prompt` — «Промпт по видео»: RU/EN prompts, camera movement, timeline, style and negative prompt from up to four chronological video frames. Audio and unseen motion between frames are not analyzed.

Telegram exposes the tools from the main menu and through `/prompt_tools`, `/photo_prompt` and `/prompt`. Uploads and result interaction happen in `/mini-app/prompt-tools/`; historical links are retained. Telegram bot file URLs containing bot credentials are never forwarded to an external AI provider.

## Provider contract

New `image_analysis` and `video_prompt` tasks default to Neironych `qwen3.8-max` at
`POST /v1/chat/completions`, using the existing server-only partner key and API origin.
The verified Neironych Qwen contract accepts text and `image_url` blocks, including
inline JPEG frames. It rejects native `video_url`/`input_video`; KSU explicitly uses
frame analysis. Videos retain the bounded 30 MiB / 60-second media validation and
existing ffprobe/ffmpeg extraction. Very short clips may produce fewer than four frames.

Nexus `gpt-6-sol` is the default reserve. Cross-provider fallback is permitted only before
submission (for example, an open circuit), after a definite account/capability refusal,
or with Neironych's request-bound proof of non-acceptance. A generic gateway error,
timeout, invalid output or an uncertain accepted request never permits alternate spend.

Text `prompt_builder` remains Nexus GPT-5.5; its historical image-reference API remains
Nexus GPT-6 Sol. Existing tasks without a media routing snapshot retain the original
Nexus/Kie dispatch. Pinterest and generation routing are separate domains.

### Runtime provider selection

The protected web admin's **«Анализ фото и видео»** form edits the DB-backed
`prompt_tool_provider_routes` setting. It manages exactly `image_analysis` and
`video_prompt`; each route contains one or both verified provider/model pairs:

```json
{
  "revision": 1,
  "routes": {
    "image_analysis": [
      {"provider": "neironych", "model": "qwen3.8-max"},
      {"provider": "nexus", "model": "gpt-6-sol"}
    ],
    "video_prompt": [
      {"provider": "neironych", "model": "qwen3.8-max"},
      {"provider": "nexus", "model": "gpt-6-sol"}
    ]
  }
}
```

`GET /api/v1/admin/runtime` also returns the validated choices. The POST endpoint
`/api/v1/admin/runtime/prompt-tool-routes` requires runtime permission, fresh MFA
step-up, explicit confirmation, `Idempotency-Key` and `expected_revision`. The command
ledger records the actor and operation; stale saves cannot overwrite a newer policy.
Changing this setting affects future admission only. The customer catalog resolves the
same policy as admission, and a replayed customer request keeps its existing task.

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

The existing `INTERNAL_CREDIT_RUB` conversion is used for the RUB preview. Selecting a different analysis provider does not change customer ROX prices or wallet rules.

## Durable lifecycle

`PromptToolTask` stores the owner, tool, status, server-selected provider/model, private input metadata, structured result, user credit cost and optional provider-credit usage. New media tasks also freeze the configured route, revision and current route index. Public status responses never expose provider request bodies, reference URLs or credential fingerprints.

`PromptToolOutbox` provides a durable lease/retry queue. Task creation, outbox creation and wallet debit are committed together. The API requires `Idempotency-Key`; KSU deterministically derives the task UUID from `(user_id, idempotency_key)`, so the same request cannot create a second debit.

The dedicated `prompt-tool-worker`:

1. leases one outbox row with `FOR UPDATE SKIP LOCKED`;
2. calls the server-owned provider adapter;
3. stores structured result and completes the outbox atomically; or
4. retries with bounded exponential delay;
5. on terminal failure marks the task failed and credits the full user charge back with an idempotent wallet key.

Before a Neironych POST, KSU persists its exact JSON body, hash, origin, model, stable
task-based `Idempotency-Key`, client request ID and a private credential identity digest.
Recovery reuses that body without downloading media again or rebuilding prompts/frames.
Neironych's partner/key/fingerprint contract replays the stored response without another
upstream operation. `409 request_already_submitted`, transport failure and unknown gateway
outcomes remain on the same provider/key; recovery is bounded by
`GENERATION_SUBMISSION_UNKNOWN_TIMEOUT_SECONDS`. Expired or invalid results terminate via
the existing idempotent refund. Changed body/origin/model/credential identity fails closed.

Managed Nexus media calls have one HTTP attempt and a durable start marker because an
equivalent supplier replay protocol has not been verified. A crash or ambiguous outcome
after that boundary cannot create a second Nexus POST. Historical tasks keep their old
behavior. Provider retries cannot create another customer debit or terminal refund.

Each managed dispatch checks the current outbox attempt and unexpired lease, including
after video preparation. The default whole-operation deadline is 480 seconds; its lease
is at least 600 seconds and always at least the deadline plus 60 seconds. No database
row lock is held across external provider I/O. Safe provider transitions are committed
under that same fence before the alternate provider can be called.

Worker and provider logs record task/provider/model/revision/attempt/outcome/duration
and safe provider request identifiers. They exclude media, prompts, response bodies,
authorization values and credential fingerprints.

## Telegram result delivery

Successful `image_analysis` and `video_prompt` tasks enqueue a transactional `Notification` plus `NotificationDelivery` in the same database transaction that completes the prompt task. Telegram delivery therefore reuses the existing notification-worker lease/retry path instead of sending directly from the provider worker. The prompt task remains the source of truth and the Mini App polling contract is unchanged.

The chat message contains the primary user-facing `prompt_ru`, falling back to `prompt_en` only when needed. The prompt is rendered as a language-tagged Telegram `<pre><code>` block so current Telegram clients expose their native whole-block copy control. This is intentional: Bot API `CopyTextButton.text` is limited to 256 characters while production photo/video prompts are normally much longer.

Only the media-analysis tools push prompt results to chat:

- `image_analysis` → `prompt_tool_photo_succeeded`;
- `video_prompt` → `prompt_tool_video_succeeded`.

`prompt_builder` keeps its existing Mini App-only result behavior.

## API

Authenticated endpoints:

- `GET /api/v1/prompt-tools` — enabled state and current authoritative prices.
- `POST /api/v1/prompt-tools/image-analysis` — body: `image_url`, optional `instruction`; requires `Idempotency-Key`.
- `POST /api/v1/prompt-tools/prompt-builder` — body: `text`, optional `image_url`; requires `Idempotency-Key`.
- `POST /api/v1/prompt-tools/video-prompt` — body: `video_url`, optional `instruction` and target `duration_seconds`; requires `Idempotency-Key`.
- `GET /api/v1/prompt-tools/{task_id}` — owner-only status/result.

Clients cannot submit model, provider, price, provider settings or billing metadata.

## Input safety

Image URLs must be HTTPS and obvious loopback/local hosts are rejected. The browser uploads files through the existing authenticated `/api/v1/uploads/kie` path and submits the resulting remote URL. User text/instructions are bounded before provider execution.

## Deployment

The existing Prompt Tools migrations and `prompt-tool-worker` service remain in use. The Neironych-primary change adds no database migration, new secret or service.

The API and prompt worker must share `./static/uploads:/app/static/uploads`. Mini App photo/video uploads are stored as stable ROXY `/uploads/refs/...` URLs before provider execution; without the shared mount the API can accept an upload while the worker later fails the task because the stored reference is missing in its own container filesystem.

The worker retains the existing poll/max-attempt settings. Managed media work uses
`PROMPT_TOOL_MEDIA_TIMEOUT_SECONDS` (default 480) and
`PROMPT_TOOL_MEDIA_OUTBOX_LEASE_SECONDS` (default 600); its effective lease is never
shorter than the execution deadline plus 60 seconds. Provider/model routing is managed
in the authenticated runtime admin, not through an environment-only fallback flag.
