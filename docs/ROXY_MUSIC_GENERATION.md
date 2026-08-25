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
- `styleWeight` (`0..1`, UI default `0.7`);
- `weirdnessConstraint` (`0..1`, UI default `0.3`);
- `audioWeight` (`0..1`, UI default `0.6`);
- `personaId`;
- `personaModel`;
- `duration` (V5_5 only).

The requirements are conditional rather than represented by a single static `required_fields` list:

- Simple Mode (`customMode=false`): `prompt` is required; the public builder keeps this short and validates up to 500 characters; other custom fields are stripped before submission.
- Custom + instrumental: `style` is required; `prompt` may be omitted.
- Custom + vocal: `style` and `prompt` are required.
- `title` is optional in the product UI and is sent only when filled.
- V5_5 custom prompt / lyrics: up to 5000 characters.
- V5_5 style: up to 1000 characters.
- title: up to 80 characters.
- `duration` is accepted only while the configured provider model is `V5_5`.

The server is authoritative for these constraints even if the browser is bypassed.

## Pricing

Music has its own public ROX price:

```env
MUSIC_GENERATION_MODEL=V5_5
MUSIC_GENERATION_PRICE_ROX=25
```

The default product tariff is **25 ROX**. Provider-credit pricing is not exposed to the browser and is not used to redefine the public ROXY economy.

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

The existing `Создать -> Фото / Видео / Музыка` selector now enables Music when an audio model is present in the server catalog.

The `suno-v5.5` product layer:

- opens as a dedicated audio builder inside the shared Create surface;
- exposes the same concepts as the approved mockup: prompt, optional title, simple/custom mode, vocal/instrumental choice, voice, lyrics, advanced style controls and excluded tags;
- defaults the advanced controls to `styleWeight=0.7`, `weirdnessConstraint=0.3`, `audioWeight=0.6`;
- shows the server-owned 25 ROX quote before launch;
- converts generated audio result elements into native `<audio controls>` players;
- keeps the same polling, History and `Повторить / изменить` flows used by other generation media.

This keeps one Create and History experience without forcing the Suno provider contract into the image/video ModelCatalog.

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
5. explicitly approve `MUSIC_GENERATION_PRICE_ROX=25` or the intended production override for the current commercial tariff;
6. verify `media-worker` heartbeat and audio ingest events;
7. perform one vocal and one instrumental generation from Telegram Mini App;
8. verify provider URL changes to owned storage in History;
9. verify a forced provider failure refunds ROX exactly once.
