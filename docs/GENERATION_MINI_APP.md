# ROXY dynamic generation Mini App

**Status:** synchronized with shipped runtime on 2026-08-20.

The ROXY generation experience is served inside `/mini-app/`. It is media-first and schema-driven: the customer chooses **Photo** or **Video**, then a product/model, and the existing backend-driven builder renders the concrete controls.

## Customer flow

```text
Create
  ↓
Photo | Video
  ↓
media-specific product/model screen
  ↓
model / operation / scenario selection
  ↓
server ui_schema builder
  ↓
upload references + set parameters
  ↓
POST /api/v1/generations/quote
  ↓
review authoritative ROX price
  ↓
POST /api/v1/generations
  ↓
worker → provider → result/history
```

Photo and Video are independent child flows. Opening Video must not route to Home. Back navigation from the builder returns to the selected media flow where ROXY owns the navigation context.

`app/web/mini_app/roxy-generation-flow-v3.js` provides the product-oriented media flow. `app/web/mini_app/app.js` remains the generic schema builder and submission client.

## Runtime sources of truth

The frontend must not maintain a second provider schema or pricing engine.

```http
GET /api/v1/generations/models
POST /api/v1/generations/quote
POST /api/v1/generations
POST /api/v1/uploads/kie
```

`GET /api/v1/generations/models` returns current models, media type, operation, price mode, public price and `ui_schema`. The create endpoint validates and prices again; a browser quote is not a trusted price token.

Authenticated create/upload calls use raw signed `Telegram.WebApp.initData` in `X-Telegram-Init-Data`. `initDataUnsafe` is never an authentication source.

## Product grouping

ROXY groups compatible backend variants into user-facing products where useful. Examples include Nano Banana, Seedream, GPT Image, WAN and Grok groups. Grouping is presentation only: the concrete backend `model_id` still controls validation, provider payload and billing.

WAN 2.7 is exposed in both media families:

- video: text/image/video-oriented Wan 2.7 variants;
- photo: `wan-2.7-image` / related image variants, backed by Kie `wan/2-7-image`.

Model availability must be derived from the runtime catalog, not hardcoded as an entitlement in the UI.

## `ui_schema` and schema state

Each model contract carries a `schema_version`. The client stores non-secret convenience drafts in `localStorage`, keyed per model/schema context, and sanitizes stale fields against the latest schema before reusing them. A schema version change therefore invalidates assumptions from an older client draft instead of making stale fields provider input.

The backend `ui_schema` can define:

- groups and fields;
- defaults;
- summary fields;
- model scenarios;
- required/visible/clear fields for scenarios;
- explicit `billing_seconds` for models whose provider payload does not expose a normal duration field.

Supported generic controls include text, textarea, number, toggle, combobox, file, files and JSON controls. Where a field contains suggestions, **suggestions are not strict enums** unless the backend validation contract explicitly says so. Critical provider constraints must also be validated server-side; hiding a field in the UI is not a security or billing boundary.

Drafts are isolated per model and stored only as non-secret convenience state. Stale fields are sanitized against the latest model schema before use.

## Scenarios and media inputs

Scenario-driven models clear incompatible state when switching modes. Current examples include Seedance frame/reference modes, Wan 2.7 first/last frame or continuation modes, and Kling Motion image+motion-video input.

Uploads go through `/api/v1/uploads/kie`; the provider API key remains server-side. Generated result URLs are temporary provider ingest sources until product-owned media ingestion completes.

## ROX denomination

Public accounting is:

```text
1 ROX = 1 RUB
```

Legacy code/database field names may still contain `credits`/`rox`, but all current customer-facing generation prices below are public ROX.

## Price modes

Flat image/product price:

```text
cost_rox = flat_price_rox
```

Per-second video price:

```text
cost_rox = resolved_unit_price_rox × billing_seconds
```

For parameter-aware models the server first resolves the applicable price tier, then calculates both quote and debit from that same result.

## Current public pricing baseline

| Product | Price |
| --- | ---: |
| Nano Banana PRO | 25 ROX |
| WAN 2.7 photo | 20 ROX |
| GPT Image 2 | 20 ROX |
| Nano Banana 2 | 25 ROX |
| Nano Banana 2 Lite | 25 ROX |
| Seedream 4.5 | 20 ROX |
| Seedream 5 Pro | 20 ROX |
| Seedance 2.0 | 40 ROX/s |
| Seedance 2.5 | 60 ROX/s |
| Kling 3.0 | 30 ROX/s |
| Veo 3.1 | 35 ROX/s |
| Grok | 15 ROX/s |
| Grok Imagine 1.5 | 30 ROX/s |
| Gemini Omni | from 30 ROX/s |
| Kling Motion 2.6 — 720p | 20 ROX/s |
| Kling Motion 2.6 — 1080p | 30 ROX/s |
| Kling Motion 3.0 — 720p | 60 ROX/s |
| Kling Motion 3.0 — 1080p | 80 ROX/s |

The table is the approved baseline, not a client-side constant. The live backend catalog and published admin tariff override are authoritative at request time.

“Kling 03 • Omni” is not represented as a fabricated provider model ID. Add it only after a real provider/catalog endpoint is mapped and tested.

## Live Admin Tariffs

Generation pricing can be changed through the privileged admin pricing contour.

Contract:

1. operator has `pricing.manage`;
2. change is validated against known model IDs, price mode and supported parameter tiers;
3. explicit confirmation + fresh MFA step-up are required for publish;
4. published `generation_pricing` becomes the runtime override immediately;
5. quote and actual wallet debit use the same resolver;
6. the latest published tariff is restored from PostgreSQL on application startup/restart.

This prevents a visual admin price from diverging from the money actually debited.

See `ADMIN_CONSOLE.md` and `ADMIN_RUNBOOK.md` for operator procedure.

## Quote freshness

The Mini App invalidates its cached quote whenever relevant model/scenario/parameter state changes. Create remains disabled while upload/submit is active, validation fails, or no fresh successful quote exists. The server still recalculates on create.

## Results and history

Generation work is durably queued in PostgreSQL. The frontend polls generation detail and displays results; successful provider media is ingested into product-owned storage. Reuse/recreate creates a new draft and receives a new server quote before any new debit.

## Adding a model safely

1. Verify the real provider/Kie model slug and current schema.
2. Add/update the backend model specification and structural validation.
3. Define `ui_schema` fields/scenarios only for supported provider inputs.
4. Define the correct `flat` or `per_second` pricing mode and any supported tier resolver.
5. Ensure the product appears in the correct Photo/Video group without duplicating billing logic in JavaScript.
6. Add regression tests for prepare/quote/create and UI schema.
7. Verify Admin Tariffs validation for the model.
8. Run full CI and inspect `/api/v1/generations/models` after deploy.
9. Update this document and the release acceptance checklist.

## CI contract

CI syntax-checks every Mini App JavaScript file and executes focused generation/ROXY contracts before the full Python regression suite. Pricing tests must verify both default prices and server-side overrides, including parameter tiers where applicable.
