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

Personalization types are inferred from the primary label on both save and read, using whole words rather than substrings. Parenthesized explanations and examples after a colon or “пример”/“например”/“example” do not determine the type. Literal text labels such as “Надпись” or “Цвет” remain text; otherwise explicit date words take priority over numeric words. The phrase “время года” describes a season rather than a numeric year, while mixed labels such as “Возраст в это время года” retain numeric validation. “Погода”, season choices and captions with a Birthday example use text inputs. Unknown labels conservatively remain text. Both admin editors share one frontend classifier; a reviewed catalog corpus verifies parity with the server.

Normalization repairs old inferred types on read without editing recipes or migrating data. Numeric inputs retain their existing decimal validation. Date inputs must be real calendar dates in canonical `YYYY-MM-DD` form; invalid dates return the existing safe HTTP 422 field error before generation or billing. User text is inserted literally in one pass: backslashes are preserved, and a user-supplied `{{…}}` string is not expanded as another field.

The [catalog-wide input audit](agents/EXECUTION/trend-input-audit-20261021.md) records the read-only snapshot, all reviewed labels, affected counts and verification scope.

## One-tap generation

`TrendService.run()` merges only the validated user image reference URLs into the curated recipe and calls the normal `GenerationService.create()` path. Video previews are presentation-only: they are never sent as generation inputs and do not add a video-reference surcharge, regardless of whether their duration metadata is verified.

Video references are not supported in trends. Recipes containing video-input parameters (including legacy aliases) or Seedance `@VideoN` tags are rejected before generation or billing. For Seedance templates, the highest `@ImageN` automatically defines the minimum number of user image uploads, and validation uses distinct placeholder URLs for every required image. Existing reference-integrity checks still reject missing or out-of-range references. Ordinary generation outside Trends retains video-reference support.

For models advertising `reference_audio_urls`, the Mini App template editor has an **Аудиореференсы для модели** section. An administrator can upload an audio file, listen to it, and remove it without editing JSON. Use `@Audio1`, `@Audio2`, etc. in the hidden Seedance prompt to explain how the model should use each reference; check the numbering after removing an entry. The audio is fixed in the server-owned recipe and reused on customer runs alongside their image references. It is not a user-editable input or a soundtrack applied after generation.

Audio uploads use the dedicated authenticated admin endpoint `/api/v1/uploads/template-audio`. The editor attaches a returned URL only when the server reports audio with a ready probe and a positive measured duration. Model-specific size/count/duration limits remain enforced by the normal server validation before saving or billing. Failed or unverified uploads leave the recipe unchanged and can be retried. Saving, model changes and JSON editing are disabled while an upload is pending; a late response cannot overwrite a newly opened draft. Editing and duplication retain existing audio settings.

Previously saved external or unregistered audio URLs are not repaired automatically. Remove the old entry and upload the file in this section to register its measured duration. The legacy web admin JSON editor remains compatible with `parameters.reference_audio_urls` containing already registered ROXY audio URLs. Migration 0043 separates template audio metadata from personal reference memory (see lifecycle section below).

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

### Template audio lifetime (PR #549 repair)

`POST /api/v1/uploads/template-audio` requires the existing inline-admin
`social.moderate` permission. It preserves size/rate limits, filename-based MIME
classification and media probing, and rejects files without an audio stream or
with a video stream. Blank, `application/octet-stream` and `binary/octet-stream`
MIME values are classified by the server. The client attaches only verified audio.

Audio metadata lives in `template_audio_references`, outside personal reference
limits and deletion. `uploaded_by` is nullable attribution, with `ON DELETE SET
NULL`. New uploads use an independent storage namespace. Migration 0043 copies
verified metadata for existing templates, including hidden templates and audio
previously marked deleted by personal pruning. Missing/unverified media is not
fabricated. Saving a legacy verified URL promotes it transactionally. Editing,
duplicating, hiding and republishing preserve the shared asset by URL.

Removing audio in the editor only changes the draft; saving removes that recipe
reference. To dispose of an unused upload, an authorized administrator can call
`DELETE /api/v1/trends/audio/{reference_id}` using the ID returned by upload.
Disposal refuses audio referenced by **any** template (including hidden copies),
generation history, preset or active personal reference. Saves and disposal serialize with a transaction
lock; metadata reads lock the asset until their transaction completes. Disposal
is repeatable: it tombstones metadata first, then removes local bytes only when
no personal reference shares the URL. A failed unlink can be retried with the
same endpoint; retained tombstones prevent accidental resurrection. Historical
personal files are retained, not deleted by this endpoint. Abandoned drafts are
not automatically purged; explicit disposal is conservative and has no TTL.

Rollout: apply additive migration before starting the new backend/frontend.
Code rollback must retain the new table and files; old code cannot validate new
independent audio. Disable new audio uploads before rolling back, and restore
metadata compatibility before serving templates with the old version. Do not
run the schema downgrade against templates using independent audio.
