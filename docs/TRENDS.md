# Curated Trends

**Status:** current runtime contract on **2026-08-27**.

ROXY reuses the existing `AdminTrend` store for curated image/video scenarios. There is no parallel trend task or billing system: a trend is a validated, versioned recipe that ultimately creates a normal `Generation` through the standard generation service.

## Source of truth

`AdminTrend.payload` is a validated recipe rather than arbitrary JSON. Canonical shape:

```json
{
  "schema_version": 1,
  "description": "Short public description",
  "media_type": "image",
  "preview_url": "https://product-owned.example/trend.jpg",
  "model_id": "nano-banana-2",
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

Recipes are normalized/validated against the current generation catalog and `GenerationService` contract before persistence. Hiding a trend is a soft deactivation.

## Public customer API

Authenticated product endpoints:

```text
GET  /api/v1/trends
GET  /api/v1/trends/{trend_id}
POST /api/v1/trends/{trend_id}/run
```

The run request accepts customer references only. The browser cannot override the curated model, hidden prompt, provider parameters, billing duration, quality or pricing. Those fields are loaded server-side from the curated recipe.

The public trend DTO exposes presentation data, safe model identity, current server price, reference requirements and usage metadata. It returns `prompt_hidden=true` / `prompt_actions_allowed=false`; the hidden curated prompt/provider parameters are never serialized to the customer.

## One-tap generation

`TrendService.run()` merges validated customer reference URLs into the curated recipe and calls the normal `GenerationService.create()` path. Trend jobs therefore reuse:

- model capability validation;
- server-authoritative flat/per-second/tiered pricing;
- admission/rate controls;
- wallet debit idempotency;
- durable PostgreSQL generation outbox;
- provider worker/reconciliation/recovery;
- media ingestion and refund behavior.

Trend generation rows use `action_type=trend`.

## Hidden-recipe boundary

The owner generation/history API deliberately does not reveal the curated recipe for `action_type=trend`. Generic recreate is rejected for those jobs; repeating a trend goes through the Trends catalog again. This prevents history/recreate endpoints from becoming an alternate route to the hidden prompt.

## Mini App customer flow

The current Trends surface lives inside the ROXY Mini App catalog under **Тренды → Готовые сценарии**. It is not a separate legacy `/trends.html` customer application.

Customers can:

- browse image/video curated scenarios;
- see public copy, preview, model and authoritative current price;
- open a trend runner;
- upload only the references required by the recipe;
- submit only allowed reference input to the trend-run endpoint;
- receive the result through the normal generation/history delivery system.

The customer UI never persists Telegram auth or hidden trend recipe fields in browser storage.

## Inline admin flow (Tanya-style parity)

An active admin sees `＋ Добавить` / `Управлять трендами` directly beside **Готовые сценарии** in the same customer Mini App. This reproduces the practical `banano_kling:tanyapi` workflow without copying its legacy auth/generation architecture.

Supported actions:

- create a trend;
- upload image/video preview from device;
- select a live model;
- configure hidden prompt, input/ref requirements, duration, priority, tags and advanced model parameters;
- edit or duplicate;
- hide and restore.

Preview uploads use the existing `/api/v1/uploads/kie` compatibility endpoint, which now persists reusable input under ROXY ownership. The historical route name does not mean the browser stores a temporary Kie provider URL.

### Inline admin endpoints

```text
GET    /api/v1/trends/manage
POST   /api/v1/trends/manage
PATCH  /api/v1/trends/manage/{trend_id}
DELETE /api/v1/trends/manage/{trend_id}
POST   /api/v1/trends/manage/{trend_id}/activate
```

These endpoints use signed Telegram Mini App authentication, then separately resolve an active `AdminAccount` and authorize `social.moderate`. `me.is_admin` controls presentation only; it is not the mutation security boundary.

Writes go through `TrendService.validate_recipe` and `AdminCommandLedger` for validation, auditability and idempotency.

## Standalone Admin Console

`/admin-app/trends.html` remains available for privileged operators using the separate admin-session/MFA boundary. It and the inline manager operate on the same `AdminTrend` rows. Do not add a second trend table or parallel recipe format.

## Compatibility and rollout

Legacy `AdminTrend` rows are not blindly trusted. Public listing skips rows that cannot be normalized against the current recipe/model contract. Operators should recreate/update incompatible records through one of the validated admin paths.

No new trend-specific Alembic table is required because the existing curated store is reused.

## Acceptance

Trend changes must preserve:

- public hidden-prompt boundary;
- server-owned model/price/recipe selection;
- durable preview storage;
- admin permission checks on every write;
- ordinary-user absence of admin controls;
- normal generation billing/outbox/recovery semantics;
- Mini App Chromium and mobile WebKit release gates.
