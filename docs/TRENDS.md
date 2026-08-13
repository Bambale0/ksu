# Curated Trends

Epic #41 ports the product contract of the `banano_kling:tanyapi` Trends surface into KSU without copying the legacy generation or billing implementation.

## Source of truth

`admin_trends` remains the single curated-trend store. No second trend table is introduced. `AdminTrend.payload` is now treated as a validated versioned recipe rather than arbitrary JSON.

A canonical payload has this shape:

```json
{
  "schema_version": 1,
  "description": "Short public description",
  "media_type": "image",
  "preview_url": "https://cdn.example/trend.jpg",
  "model_id": "nano-banana-pro",
  "prompt": "private curated prompt",
  "parameters": {
    "aspect_ratio": "1:1",
    "resolution": "1K"
  },
  "billing_seconds": null,
  "input_mode": "image",
  "min_references": 1,
  "max_references": 4,
  "tags": ["portrait"],
  "sort_order": 10,
  "usage_count": 0
}
```

Creation goes through the existing privileged admin content service. The recipe is normalized and validated against `ModelCatalog` and `GenerationService.prepare_request()` before persistence. Deactivation remains a soft delete.

## Public API

Authenticated product endpoints:

- `GET /api/v1/trends`
- `GET /api/v1/trends/{trend_id}`
- `POST /api/v1/trends/{trend_id}/run`

The run request accepts only:

```json
{"reference_urls": ["https://..."]}
```

The browser cannot choose or override the model, prompt, provider settings, duration, price, aspect ratio, quality or other recipe fields. They are loaded server-side from the curated record. User reference URLs must be HTTP(S); browser-local `blob:` and `data:` URLs are rejected.

The public trend DTO exposes only presentation data, the safe model identity, authoritative current price, reference requirements, usage counter and the flags `prompt_hidden=true` / `prompt_actions_allowed=false`. It never serializes the curated prompt or provider parameters.

## One-tap generation

`TrendService.run()` merges only the validated user reference URLs into the curated recipe and calls the normal `GenerationService.create()` path. Therefore trend jobs reuse KSU's existing:

- model capability validation;
- server-authoritative pricing and per-second billing;
- abuse/admission controls;
- wallet debit idempotency;
- durable generation outbox;
- worker/recovery/refund behavior.

Trend generation rows are marked `action_type=trend`.

## Hidden-recipe boundary

The normal owner history/detail endpoint deliberately returns an empty prompt and empty public settings for `action_type=trend`. `GET /api/v1/generations/{id}/recreate` returns HTTP 409 for those jobs. Repeating the job must go through the Trends catalog again.

This prevents the generic history/recreate API from becoming an alternate route to the hidden curated recipe.

## Telegram and Mini App

Telegram supports `/trends` and the compatibility alias `/prompts`. The carousel shows image/video previews, public copy, model, authoritative price and reference requirements. The repeat action opens `/mini-app/trends.html?trend=<uuid>`.

The Mini App Trends runner:

- lists and filters image/video trends;
- uploads only the required user reference images through the existing Kie upload endpoint;
- submits only `reference_urls` to the trend run endpoint;
- polls the normal generation detail endpoint for the result;
- never stores Telegram initData or reference URLs in browser storage;
- builds dynamic content with DOM/textContent APIs rather than HTML injection.

## Compatibility and rollout

Existing legacy `admin_trends` rows are not migrated automatically. Public listing skips active rows that cannot be normalized against the current recipe contract. Operators should recreate or update such entries through the validated admin path before relying on them in production.

No Alembic migration is required for this epic because the existing `admin_trends` table is reused.
