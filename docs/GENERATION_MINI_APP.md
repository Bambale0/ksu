# Dynamic generation Mini App

**Status:** matches the shipped Mini App/model contract as of 2026-08-11.

The current Mini App is the user-facing generation screen served by FastAPI at:

```text
/mini-app/
```

It is intentionally **schema-driven**. The browser does not maintain one hardcoded form for every Kie model. The backend model catalog is the source of truth for what fields are rendered and how billing is calculated.

## 1. Main flow

```text
Open from Telegram
    ↓
GET /api/v1/generations/models
    ↓
choose family → model → input scenario
    ↓
render model ui_schema
    ↓
change settings / upload references
    ↓
validate current state
    ↓
POST /api/v1/generations/quote
    ↓
show selected settings + current server price
    ↓
POST /api/v1/generations
```

The final create endpoint validates and prices the request again. A quote displayed in the browser is not a trusted price token.

## 2. API surfaces

### Model catalog

```http
GET /api/v1/generations/models
```

This endpoint is currently public and returns:

```json
{
  "schema_version": 1,
  "internal_credit_rub": "10",
  "models": []
}
```

Each model contains the server model metadata plus:

```json
{
  "ui_schema": {
    "version": 1,
    "groups": [],
    "fields": [],
    "defaults": {},
    "summary_fields": [],
    "scenario": {},
    "billing_seconds": {}
  }
}
```

`scenario` and `billing_seconds` are present only when needed.

### Quote

```http
POST /api/v1/generations/quote
Content-Type: application/json
```

Example:

```json
{
  "model_id": "wan-2.7-t2v",
  "prompt": "Cinematic city at night",
  "parameters": {
    "duration": 6,
    "resolution": "1080p",
    "ratio": "16:9"
  }
}
```

Response includes:

```text
unit_price_credits
unit_price_rub
billing_seconds
cost_credits
cost_rub
internal_credit_rub
```

Quote currently does not require Telegram user authorization.

### Create generation

```http
POST /api/v1/generations
X-Telegram-Init-Data: <Telegram.WebApp.initData>
Content-Type: application/json
```

The create endpoint requires authenticated Telegram Mini App context, recalculates model validation and billing, debits the wallet, persists the generation and enqueues it for the worker.

### Upload local media

```http
POST /api/v1/uploads/kie
X-Telegram-Init-Data: <Telegram.WebApp.initData>
Content-Type: multipart/form-data
```

This endpoint:

- accepts image/video/audio MIME prefixes;
- enforces global `KIE_UPLOAD_MAX_BYTES` when file size is known;
- streams the file to the Kie upload API;
- returns provider URL/name/MIME/size;
- never exposes `KIE_API_KEY` to the browser.

Official Kie file upload documentation: https://docs.kie.ai/file-upload-api/upload-file-stream/

Provider-hosted upload URLs are temporary assets. Do not design long-term history/storage around them without copying results to product-owned storage.

## 3. `ui_schema` field contract

A field contains values such as:

```json
{
  "name": "duration",
  "label": "Длительность",
  "control": "number",
  "group": "output",
  "required": true,
  "min": 1,
  "max": 30,
  "step": 1,
  "suffix": "с"
}
```

Current control types:

```text
text
textarea
number
toggle
combobox
file
files
json
```

Current groups:

```text
prompt      → Описание
references  → Референсы
output      → Результат
advanced    → Дополнительно
```

`advanced` is marked collapsible in the schema.

### Important current limitation: suggestions are not strict enums

`combobox.suggestions` are UI suggestions. The current generic backend model validation primarily checks:

- known/required fields;
- video duration bounds;
- family/model-specific structural rules;
- server pricing.

It does **not** currently enforce every `suggestions` value as a strict provider enum. The Mini App uses a datalist-like combobox and can therefore submit a manually typed value. Kie may reject provider-invalid values later.

Do not document UI suggestions as a complete server-enforced enum contract until explicit enum validation is added to `ModelCatalog`.

## 4. State model

The browser state contains:

```text
models
modelById
selectedFamily
selectedModelId
drafts
quote
quoteError
uploading/submitting state
```

Drafts are isolated by `model_id`.

A model draft contains:

```json
{
  "values": {},
  "touched": {},
  "files": {},
  "scenario": null,
  "billing_seconds": null
}
```

### Per-model isolation

Switching from a video model to an image model does not carry video-only settings into the image request.

When a stored draft is restored, `sanitizeDraft` keeps only fields that still exist in the current backend `ui_schema`. This prevents stale fields from an older model/schema from silently remaining in submitted parameters.

### Local persistence

The current Mini App stores generation drafts in browser `localStorage` under a versioned KSU key and also remembers the selected model.

This is convenience persistence, not secure storage.

Operational/privacy implications:

- do not store admin bearer tokens there;
- draft reference URLs/file metadata can remain on the device/browser profile;
- on shared devices, use the reset action or clear site storage if media references are sensitive;
- failure/unavailability of local storage does not prevent the form from working.

Telegram added DeviceStorage/SecureStorage APIs in newer clients, but the current shipped generation screen still uses normal browser `localStorage` for non-secret draft convenience.

Official Telegram Mini Apps reference: https://core.telegram.org/bots/webapps

## 5. Scenario-driven screens

Scenarios are used when one Kie model has mutually incompatible input modes.

The scenario contract supports:

```text
id
title
visible_fields
clear_fields
required_fields
required_any
```

When scenario changes, `clear_fields` are deleted from draft values/file metadata/touched state. They are not merely hidden in CSS.

### Seedance 2.x / 2.5

Current scenarios:

```text
text
first_frame
first_last
references
```

Behavior:

- `text`: clears frame and multimodal references;
- `first_frame`: requires first frame and clears multimodal refs/last frame;
- `first_last`: requires both first and last frames and clears multimodal refs;
- `references`: requires at least one image/video/audio reference and clears frame mode fields.

The backend also rejects mixing frame mode and multimodal reference mode for current Seedance models.

The current contract reflects the provider distinction between frame-driven and multimodal-reference input modes. Always verify new Seedance versions against Kie before changing these rules.

### Wan 2.7 image-to-video

Current scenarios:

```text
first_frame
first_last
continuation
```

Behavior:

- first frame requires `first_frame_url`;
- first + last requires both frame URLs;
- continuation requires `first_clip_url`;
- switching modes clears incompatible frame/clip fields.

The backend additionally requires at least `first_frame_url` or `first_clip_url` for `wan-2.7-i2v`.

### Kling Motion Control 2.6 / 3.0

Current UI contract tightens file controls to:

```text
input_urls: max 1 image, UI max 10 MB
video_urls: max 1 video, UI max 100 MB
billing_seconds: 3..30
```

Backend validation requires exactly one image URL and exactly one motion-video URL. Video billing duration is represented separately because the provider request schema does not use a normal generation `duration` field for this operation.

When a local video is selected, the browser reads its metadata duration and clamps the initial billing duration to the schema min/max.

## 6. Billing behavior

Image model:

```text
price_mode = flat
cost_credits = unit_price_credits
```

Video model:

```text
price_mode = per_second
cost_credits = unit_price_credits × billing_seconds
```

RUB display:

```text
cost_rub = cost_credits × INTERNAL_CREDIT_RUB
```

With the current product default:

```text
1 credit = 10 RUB
```

### Where billing seconds come from

Normal video models use their configured duration field.

For models without a normal duration input, `ui_schema.billing_seconds` adds a separate billing field.

Current examples:

- Kling Motion Control: reference-video billing duration;
- Grok video extend: billed extension length;
- Grok video upscale: backend can reuse source billed duration when source task belongs to this backend.

The create endpoint always recalculates cost from server model/pricing configuration.

## 7. Selected-settings summary

The **Вы выбрали** summary is generated from current application state, not by scraping visible DOM labels after the fact.

It uses `ui_schema.summary_fields` and currently:

- excludes prompt text from chips;
- excludes raw JSON controls;
- displays toggle values as Да/Нет;
- displays file names/counts from stored file metadata;
- includes explicit billing seconds where used;
- includes the current scenario in the summary model heading.

When any setting changes:

```text
state quote cleared
→ summary rerendered
→ validation rerun
→ create controls disabled until quote is fresh
→ quote scheduled
```

## 8. Quote freshness and concurrency

The Mini App debounces quote refresh by approximately 350 ms.

A monotonically increasing request sequence prevents an older/slower quote response from overwriting a newer request state.

Create controls require all of these:

```text
not submitting
not uploading
no client validation errors
fresh successful server quote exists
```

The Telegram main/bottom button mirrors the same readiness and current credit cost.

## 9. Telegram integration

The Mini App calls:

```text
Telegram.WebApp.ready()
Telegram.WebApp.expand()
```

and uses available theme/background, haptic feedback and main/bottom button APIs.

Authenticated requests use only raw:

```text
Telegram.WebApp.initData
```

sent as:

```text
X-Telegram-Init-Data
```

The backend validates the signed data using the configured bot token. `initDataUnsafe` must never replace server validation.

Telegram's current documentation also emphasizes real-time theme changes and mobile-first/safe-area design; future UI work should continue to follow those contracts.

Official reference: https://core.telegram.org/bots/webapps

## 10. Model families currently exposed by the backend catalog

Do not duplicate the full provider parameter matrix in frontend source or hand-maintained docs; `GET /api/v1/generations/models` is the runtime source of truth.

Current families include:

- Nano Banana;
- Seedream;
- GPT Image;
- Wan;
- Seedance;
- Kling Motion Control;
- Grok Imagine.

The server catalog currently includes text/image/video/edit/reference/upscale/extend variants where implemented.

Kie Market uses a common task creation interface and a unified task details endpoint. Production should prefer callbacks and use `recordInfo` for reconciliation.

Official Kie references:

- https://docs.kie.ai/market/gpt/gpt-image-2-text-to-image
- https://docs.kie.ai/market/common/get-task-detail
- https://docs.kie.ai/common-api/webhook-verification

## 11. How to add or change a model safely

When Kie adds/changes a model:

1. Verify the current Kie model page and exact model slug.
2. Update `ModelCatalog` known/required fields and duration/billing rules.
3. Add/update `FIELD_DEFINITIONS` and model-specific UI override only when generic behavior is insufficient.
4. Add scenario rules if input modes are mutually exclusive.
5. Add server-side structural validation for critical provider constraints; do not rely only on UI hiding.
6. Update pricing default/override expectations.
7. Add regression tests in `tests/test_model_ui.py` and model catalog tests.
8. Run CI, including `node --check`.
9. Verify the runtime `/models` schema and quote response after deploy.
10. Update this document only for stable cross-model behavior; avoid copying a provider parameter list that will immediately drift.

## 12. CI contract for the Mini App

Current CI checks:

```text
node --check app/web/mini_app/app.js
pytest tests including dynamic UI contract assertions
```

Tests currently assert, among other things:

- every known model field has a UI control;
- scenario fields belong to the same model;
- Wan/Seedance scenario requirements are represented;
- per-second models can supply billing duration;
- Kling Motion UI upload limits are present;
- Mini App static assets are packaged.

## 13. Current limitations / follow-ups

- combobox suggestions are not strict backend enums yet;
- local drafts use `localStorage`, including provider media URLs/file metadata;
- provider media is not copied to permanent product object storage;
- there are no automated browser/E2E tests yet; JavaScript syntax + Python contract tests are the current frontend CI gate;
- model contract drift still requires active verification against Kie documentation when provider schemas change;
- generation enqueue is not protected by a transactional outbox; see `docs/OPERATIONS_RUNBOOK.md`.
