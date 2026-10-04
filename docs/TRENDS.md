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

The run request accepts only customer-owned inputs that the public trend contract explicitly exposes:

```json
{
  "reference_urls": ["https://..."],
  "user_values": {"Имя": "Игорь"},
  "resolution": "720p",
  "aspect_ratio": "9:16"
}
```

The browser cannot choose or override the model, hidden prompt, provider route/settings, duration, price or arbitrary recipe fields. Resolution is restricted to server-published quality options. Aspect ratio is restricted to fixed values from the selected model's authoritative UI contract; `auto` and `adaptive` are not offered by the Trend launcher. When a model exposes fixed aspect ratios, `aspect_ratio` is mandatory at run time and a missing or unsupported value is rejected with HTTP 422 before generation/billing. User reference URLs must be HTTP(S); browser-local `blob:` and `data:` URLs are rejected.

The public trend DTO exposes only presentation data, safe model identity, authoritative current price, reference requirements, user-field schema, `aspect_ratio_options`, optional quality options, usage counter and the flags `prompt_hidden=true` / `prompt_actions_allowed=false`. It never serializes the curated prompt or provider parameters.

## One-tap generation

`TrendService.run()` merges only the validated user image reference URLs into the curated recipe and calls the normal `GenerationService.create()` path. Video previews are presentation-only: they are never sent as generation inputs and do not add a video-reference surcharge, regardless of whether their duration metadata is verified.

Video references are not supported in trends. Recipes containing video-input parameters (including legacy aliases) or Seedance `@VideoN` tags are rejected before generation or billing. For Seedance templates, the highest `@ImageN` automatically defines the minimum number of user image uploads, and validation uses distinct placeholder URLs for every required image. Existing reference-integrity checks still reject missing or out-of-range references. Ordinary generation outside Trends retains video-reference support.

Therefore trend jobs reuse KSU's existing:

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

Telegram supports `/trends` and the compatibility alias `/prompts`. The carousel shows image/video previews, public copy, model, authoritative price and reference requirements. The repeat action opens the canonical `/mini-app/trend/?id=<uuid>` launcher, so Telegram cannot bypass required reference, personalization, quality or aspect-ratio choices.

The Mini App Trends runner:

- lists and filters image/video trends;
- uploads only the required user reference images through the existing Kie upload endpoint;
- requires an explicit fixed aspect-ratio choice whenever the model exposes fixed ratios;
- submits only validated customer inputs (`reference_urls`, optional user fields/quality, and the required fixed aspect ratio) to the trend run endpoint;
- polls the normal generation detail endpoint for the result;
- never stores Telegram initData or reference URLs in browser storage;
- builds dynamic content with DOM/textContent APIs rather than HTML injection.

## Compatibility and rollout

Existing legacy `admin_trends` rows are not migrated automatically. Public listing skips active rows that cannot be normalized against the current recipe contract. Operators should recreate or update such entries through the validated admin path before relying on them in production.

Legacy trends with video inputs or `@VideoN` tags need an admin recipe/prompt update before they can be listed or run. Their display videos can remain uploaded; removing or re-uploading the preview is not necessary. Hidden creative prompts are never rewritten automatically.

No Alembic migration is required for this epic because the existing `admin_trends` table is reused.


## Template categories

Template categories are stored relationally:

- `trend_collections` owns category metadata, ordering, visibility and hashtag aliases;
- `trend_collection_assignments` links one `admin_trends` row to one category and records whether that move was automatic;
- no assignment means the trend appears in the live `Тренды` root;
- an explicit manual assignment, including a manual move to `Тренды`, is authoritative over hashtag routing.

Migration `0036_trend_collections` copies the previous
`admin_runtime_settings.trend_collections_v1` JSON state into these tables.
The legacy setting is retained as a pre-migration fallback, while runtime reads and writes
use the relational tables only. If migration 0036 is downgraded, the current relational
category state is serialized back into that legacy setting before the tables are removed.
Category mutation remains admin-only.
