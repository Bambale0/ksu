# ROXY Music Generation

## Product boundary

Music is a first-class third media type in ROXY alongside image and video.

The public model id is `suno-v5.5`, family `suno`, media type `audio`, operation `text_to_music`.

Music deliberately does **not** pretend to be a normal `/api/v1/jobs/createTask` image/video model. It has its own Kie/Suno request and status contract while reusing the product-owned parts of the generation platform:

- the `Generation` ledger;
- ROX wallet admission/debit/refund;
- PostgreSQL generation outbox;
- provider circuit/rate protection;
- callback + polling recovery;
- user History / recreate flow;
- product-owned S3 media storage.

## Provider contract

Submission uses the Kie Suno endpoint:

- `POST /api/v1/generate`

Status reconciliation uses:

- `GET /api/v1/generate/record-info?taskId=...`

The normalized terminal contract is the same one consumed by `GenerationProviderService`:

- provider success -> `Generation.status = succeeded`;
- provider failure -> `Generation.status = failed` + idempotent ROX refund;
- non-terminal provider status -> `generating`.

The callback still enters ROXY through `/webhooks/kie?generation_id=<uuid>`. The callback body is treated as a signal; ROXY fetches authoritative task state before settling the generation.

## Public request fields

The V5.5 product surface exposes:

- `prompt`;
- `customMode`;
- `instrumental`;
- `style`;
- `title`;
- `negativeTags`;
- `vocalGender` (`m` / `f`);
- `styleWeight` (`0..1`);
- `weirdnessConstraint` (`0..1`);
- `audioWeight` (`0..1`);
- `personaId`;
- `personaModel`;
- `duration` (V5_5 only).

The requirements are conditional rather than represented by a single static `required_fields` list:

- Simple Mode (`customMode=false`): `prompt` is required; current Generate Music docs allow up to 3000 characters; other custom fields are stripped before submission.
- Custom + instrumental: `style` and `title` are required; `prompt` may be omitted.
- Custom + vocal: `style`, `prompt`, and `title` are required.
- V5_5 custom prompt: up to 5000 characters.
- V5_5 style: up to 1000 characters.
- title: up to 80 characters.
- `duration` is accepted only while the configured provider model is `V5_5`.

The server is authoritative for these constraints even if the browser is bypassed.

## Pricing

Music has its own public ROX price:

```env
MUSIC_GENERATION_MODEL=V5_5
MUSIC_GENERATION_PRICE_ROX=100
```

The default is intentionally configurable. Provider-credit pricing is not exposed to the browser and is not used to redefine the public ROXY economy.

`1 ROX = 1 RUB` remains unchanged.

Quote and create use the same server setting, so the browser cannot choose a cheaper amount.

## Durable execution

Creation performs, in one database transaction:

1. input validation;
2. abuse / active-job / spend admission;
3. `Generation` row creation;
4. durable generation outbox creation;
5. ROX wallet debit.

Redis is only a wake-up signal. PostgreSQL remains authoritative if Redis is unavailable.

The existing generation worker dispatches rows marked `_provider_api=suno_music` to the Suno API. Submission failures and terminal provider failures use the existing idempotent `generation:<id>:refund` wallet key.

## Audio storage

Kie URLs are temporary provider sources, not the long-term product library.

On successful music generation ROXY creates `MediaAsset` rows and special `audio_pending` `MediaIngestJob` rows in the same transaction as the terminal generation state. The normal media worker additionally claims these audio jobs.

Audio ingest:

- follows only validated public HTTPS redirects;
- reuses the existing SSRF guard;
- enforces `MEDIA_INGEST_MAX_BYTES`;
- accepts audio MIME types and known audio extensions;
- uploads to the private product bucket;
- switches History to short-lived product-owned presigned URLs after ingest.

The audio queue uses distinct `audio_pending` / `audio_processing` states so the legacy image/video queue does not claim the same job.

Supported file extensions at ingest are currently `.mp3`, `.wav`, `.ogg`, `.m4a`, `.flac`, `.aac`, `.opus`.

## Mini App UX

The existing `Создать -> Фото / Видео / Музыка` selector enables Music when an audio model is present in the server catalog.

The `roxy-music` product layer:

- opens the Suno builder directly;
- labels the family as Music;
- hides the image/video prompt helper for audio jobs;
- converts generated audio result elements into native `<audio controls>` players;
- keeps the same polling, History and recreate flows used by other generation media.

### UI lifecycle / performance contract

Music no longer keeps `MutationObserver` instances over builder/result/history subtrees. Repeated whole-subtree patching was a release-blocking hot path because generation/history DOM can change frequently.

The product layer now refreshes from explicit lifecycle signals:

- model-select `change`;
- canonical `roxy:route-changed` and Studio route events;
- generation/history update events when emitted by product modules;
- user actions that explicitly change generation/history surfaces;
- media `load` / `error` capture events for asynchronously rendered result media;
- Telegram `activated`.

A `requestAnimationFrame` coalescer prevents duplicate work inside one frame. There is no `MutationObserver` or `{subtree: true}` observer in `roxy-music.js`.

This keeps Music progressive enhancement without turning arbitrary DOM mutations into application state.

## Failure and recovery semantics

- No provider task id + explicit submission exception -> terminal failure and refund.
- Worker interrupted after uncertain submission -> existing unknown-submission timeout applies.
- Callback missed -> stale generation reconciliation polls Kie.
- Provider terminal failure -> one idempotent refund.
- S3 unavailable -> generation remains succeeded; audio ingest waits without exhausting retry budget.
- Audio download failure -> bounded retries; provider URL remains available until owned ingest succeeds or the media job fails.

## Operations checklist

Before production release:

1. set `KIE_API_KEY`;
2. keep `KIE_WEBHOOK_HMAC_KEY` configured where Kie callback signing is enabled;
3. confirm `PUBLIC_BASE_URL` resolves to the callback-capable service;
4. configure S3-compatible storage;
5. explicitly approve `MUSIC_GENERATION_PRICE_ROX` for the current commercial tariff;
6. verify `media-worker` heartbeat and audio ingest events;
7. perform one vocal and one instrumental generation from Telegram Mini App;
8. verify provider URL changes to owned storage in History;
9. verify a forced provider failure refunds ROX exactly once;
10. verify builder/result/history Music UI updates without broad mutation-observer activity in performance tooling.
