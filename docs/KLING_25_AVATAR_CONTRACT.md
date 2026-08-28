# Kling 2.5 Turbo Pro + Kling AI Avatar current contract

**Provider contract verified:** 2026-08-20 against the current Kie Market callable forms and API documentation.

ROXY implements these as current Kie models, not as a payload copy from the historical Tanya integration.

## Runtime model mapping

| ROXY model | Kie model | Billing baseline |
| --- | --- | ---: |
| `kling-2.5-turbo-pro-t2v` | `kling/v2-5-turbo-text-to-video-pro` | 40 ROX / 5s, 80 ROX / 10s |
| `kling-2.5-turbo-pro-i2v` | `kling/v2-5-turbo-image-to-video-pro` | 40 ROX / 5s, 80 ROX / 10s |
| `kling-avatar-standard` | `kling/ai-avatar-standard` | 100 ROX/s |
| `kling-avatar-pro` | `kling/ai-avatar-pro` | 150 ROX/s |

These are ROXY product tariffs, not claims about Kie wholesale pricing. Published Admin Tariffs remain authoritative and can override the baseline without a client deploy.

## Kling 2.5 Turbo Pro — Text to Video

Provider input allowlist:

```text
prompt            required string
duration          "5" | "10"
aspect_ratio      16:9 | 9:16 | 1:1
negative_prompt   optional string
cfg_scale         optional finite number
nsfw_checker      optional boolean
```

ROXY defaults:

```text
duration=5
aspect_ratio=16:9
cfg_scale=0.5
nsfw_checker=true
```

The backend rejects any other public parameter before wallet debit/provider submission.

## Kling 2.5 Turbo Pro — Image to Video

Provider input allowlist:

```text
prompt            required string
image_url         required HTTPS URL
tail_image_url    optional HTTPS URL
duration          "5" | "10"
negative_prompt   optional string
cfg_scale         optional finite number
nsfw_checker      optional boolean
```

Current callable Kie UI accepts JPEG/PNG for both first/tail frames with a 10 MB maximum per image. The current Kie callable form exposes `tail_image_url`; ROXY therefore supports it as an optional last-frame input rather than importing a historical Tanya-only field.

`aspect_ratio` is intentionally not exposed on this I2V route because it is not part of the current callable I2V input schema.

## Kling AI Avatar Standard / Pro

Both current Avatar routes use exactly this provider input shape:

```text
image_url   required HTTPS URL
audio_url   required HTTPS URL
prompt      string; empty guidance is allowed and is still sent
```

Current Kie upload limits/capabilities used by the dynamic UI:

- avatar image: JPEG/PNG, max 10 MB;
- audio: MPEG, WAV/X-WAV, AAC, MP4 or OGG, max 100 MB;
- audio duration: max 5 minutes / 300 seconds;
- Standard: up to 720p;
- Pro: up to 1080p / 48 fps.

Kie describes prompt guidance as optional for expression/emotion/motion control. ROXY always sends the `prompt` field and allows an empty string.

### Avatar billing

The provider payload has **no `duration` field**. ROXY therefore uses the existing top-level `billing_seconds` value for quote/debit and requires 1–300 seconds. It must represent the real source-audio duration.

`billing_seconds` is stored only as internal generation metadata (`_billing_seconds`) and is stripped before Kie submission. ROXY never invents a provider `duration` parameter for Avatar.

## Safety / validation boundary

For all four models:

- the public parameter allowlist is enforced before wallet debit;
- internal `_...` generation metadata never reaches Kie;
- Kie provider normalization repeats the contract at submission time for defense in depth;
- provider contract failures follow the normal generation failure/refund path;
- quote and debit use the same server-side tariff resolver;
- result callbacks/reconciliation use the existing monotonic generation recovery contract;
- result media is ingested into product-owned storage through the existing media pipeline.

## Dynamic Mini App contract

The model catalog drives the Mini App fields:

- T2V duration is a 5/10 selector, not an arbitrary number;
- T2V aspect ratio is limited to 16:9 / 9:16 / 1:1;
- I2V exposes first frame plus optional last frame, each with the 10 MB product/provider limit;
- both Kling 2.5 routes expose CFG, negative prompt and NSFW check;
- Avatar exposes image + audio + optional guidance prompt;
- Avatar displays a separate required `Длительность аудио` billing field capped at 300 seconds;
- Avatar audio upload copy reflects the current 100 MB Kie callable limit.

Any future widening of these fields must be verified against the then-current callable provider schema and accompanied by contract tests and documentation updates in the same PR.
