# Required photo -> video trend workflows

Implementation for issue #561. Release/deployment evidence belongs to the PR; this document is not a claim that production has been deployed.

## Product contract

A curated template can be either the existing single-stage v1 recipe or a `schema_version=2`, `workflow_type=sequential_photo_video` recipe. V2 contains exactly two ordered steps: an image generation and a video generation using one selected output of that image step. Ordinary photo/video generation and v1 trends retain their existing behavior.

The customer sees the required sequence, semantic input labels and a locked video step. Example slot labels are "Ваше фото" and "Фото одежды"; labels, help, requiredness and order belong to the admin recipe, not to a hardcoded model list. The first step charges only after its displayed server quote is accepted. The ready, product-owned photo must be visible and selected before the customer separately confirms "Оживить это фото". There is no automatic paid second step. Preparing an image is an opportunity to check clothing, lettering and symbols, not a promise of exact generative output.

A provider-success callback alone is insufficient: the owned image asset must be ready. User input and provider preview URLs are not accepted as substitutes for that completed workflow photo. A failed video does not delete the successful photo. A new paid attempt is an explicit action, never a transport retry.

## Recipe and admin ownership

`admin_trends` remains the only template store, with existing categories, visibility, publication and admin audit/RBAC. V2 includes common title/description/preview/tags/order plus two server-owned step definitions with model, hidden prompt, parameters, instructions, typed inputs and an explicit output-image binding. Image slots are ordered or semantic according to the chosen model/prompt. Personalization accepts validated scalar text, number, canonical calendar date or configured select options. Values are inserted literally once; user placeholder-like text is never re-expanded.

Model choices, input limits and binding fields are checked against the real model catalog. In particular, do not infer that every I2V model accepts the same `first_frame` field: use the supported field advertised by that model. The video step may reference its bound photo as `@Image1`; an unbound additional index is rejected before billing.

Prices are NOT stored as a second workflow tariff. Each step uses the existing model/tier tariff, billing-access decision, server quote and final debit resolver. Admins continue managing prices through the existing authenticated pricing surface. Draft estimates use synthetic values only for validation and never persist those values as customer input.

Both saved steps are validated on publication. Metadata-only changes must retain the v2 structure; duplicating a template must copy both steps instead of reconstructing a v1 form. An editor that cannot represent v2 must refuse a destructive down-conversion. No automatic v1-to-v2 migration or mass rewrite of templates is performed.

## Durable execution and ownership

Migration `0044_trend_workflows` adds owner-scoped runs and step rows. A run pins the normalized recipe including display metadata. A step records generation identity, selected asset, command identity/hash, reserved legacy identity and attempt history. The existing `Generation`, wallet ledger, outbox, provider routing, reconciliation, refund, media ingest and notification systems remain authoritative for their own concerns.

State creation does not charge and does not increment template usage. The first accepted generation increments usage once, atomically with its step link, generation, debit and outbox. The second stage, a transport replay and a deliberate retry do not count as additional scenario starts.

Paid mutation locks the workflow and then the step in a consistent order. `GenerationService.create/create_many` retain their normal commit/wake defaults for all existing callers; the workflow owns one transaction using `commit=False, wake=False`, attaches the generation and trusted history metadata, commits once, then sends the Redis wake-up. PostgreSQL outbox remains the fallback if Redis is unavailable. Old reserved-ID state can be reconciled without starting a second paid task.

Client idempotency keys are scoped to the authenticated owner/run/step and checked against the submitted payload hash. Repeating the same command returns its prior operation; changed input with the same key conflicts. A new key alone is not permission to redo an already successful step. Deliberate redo/retry supplies `retry=true`, a new key and a fresh accepted quote. A stale price is rejected before the debit; the customer must review the new price. An uncertain network response is reconciled using the original command, not blindly retried with a new key.

Private generation history exposes only a safe `trend_workflow` pointer (`id`, `trend_id`, `step_id`). Both stages retain `action_type=trend`; hidden prompts/settings remain hidden in detail/history/recreate and derivative boundaries.

## Media boundary

The workflow stores `media_asset_id`, not a temporary provider URL. Quote/start checks that the selected image belongs to the completed photo step of the same owner/run, has a ready image MIME type, and has usable storage metadata. A missing local source file cannot unlock another paid video.

Provider input stores an internal asset marker. Kie, Nexus and Neironych resolve that marker to a usable private source at their actual submission boundary; the marker is never an outbound provider URL. Neironych resolves before freezing its first immutable request body. Its uncertain retry reuses the original frozen body/idempotency identity; it does not silently mint a different request.

Customer `media` and `media_options` use the existing short-lived signed PRIVATE view URLs. The `/media/{id}/public` route remains publication-gated and must return404 for an unpublished workflow photo. Refreshing the owner run supplies a fresh view link. No intermediary image is published or copied into public static storage merely to make animation work.

## API

All routes require normal authenticated customer identity. Owner mismatch uses the existing safe not-found behavior. Hidden/edited live templates do not alter already pinned owner runs.

| Method | Route | Contract |
| --- | --- | --- |
| GET | `/api/v1/trends/{trend_id}` | Safe public template/steps and estimates; no prompts/provider recipe |
| GET | `/api/v1/trends/{trend_id}/workflow` | Latest owned run, or404; supports existing hidden-template continuation |
| POST | `/api/v1/trends/{trend_id}/workflow` | Create/idempotently recover empty run; `Idempotency-Key`, body `{}`; no debit |
| GET | `/api/v1/trends/workflows/{run_id}` | Owned immutable presentation, steps/status, ready media and safe attempt history |
| POST | `/api/v1/trends/workflows/{run_id}/steps/{step_id}/quote` | Validate current customer inputs and resolve effective server price |
| POST | `/api/v1/trends/workflows/{run_id}/steps/{step_id}/run` | `Idempotency-Key` plus accepted `quoted_cost_rox`; atomically admit the step |

Photo inputs use `image_inputs: [{slot_id, url}]` and `values: {field_id: scalar}`. Do not combine semantic image inputs with the legacy positional `reference_urls` representation. Video uses `media_asset_id` and its explicitly declared values, never a client-selected source URL. Allowed customer settings remain limited to the server contract; hidden model/prompt/binding are not overridable.

A run DTO is self-contained: `title`, `description`, preview metadata, `workflow_type`, ordered steps, safe `model` and `settings_summary`. Canonical customer continuation is `/mini-app/trend/?id=<trend_id>&workflow=<run_id>`. Shared links refer to the public TEMPLATE, never the owner's private workflow. The old `/trends/{id}/run` rejects a v2 recipe before generation/billing.

## Verification and observability

Meaningful checks include actual PostgreSQL transactions and owner-scoped HTTP, not only fake sessions: direct-stage2 rejection; double submission with equal/different keys; quote drift rollback; crash/legacy reservation recovery; exactly one debit/outbox; source ownership/readiness; private image bytes viewable while public route is404; hidden-template resume; no prompt leak; semantic input/date/literal-text validation; adapter payloads without internal markers; ordinary-v1 regressions. Browser checks exercise the actual built React app with mocked external APIs, including mobile layout, quote stability, media-ingest polling, explicit paid consent, preview selection and reload.

Lifecycle logs/metrics carry safe workflow/step/generation identifiers and phase/error categories. Do not log hidden prompts, credentials, full private media URLs or customer input. Test artifacts use synthetic media and accounts. Local/browser fixtures do not certify paid provider generation quality or physical Telegram iOS/Android behavior.

## Rollout and rollback

Apply the additive migration only during an explicitly authorized release after a database backup. Ship backend/workers before enabling newly published v2 templates. Start with selected admin-created templates; do not convert the whole catalog. Verify exact merge SHA, deployment revision, worker/readiness health and a permitted smoke. No actual paid generation is part of ordinary mocked QA.

To stop new starts, hide affected v2 templates using existing admin controls. Keep the workflow-aware backend/workers running so already accepted jobs can finish and owned runs remain readable. Do not roll workers back to code that cannot interpret their queued media markers. Do not drop0044 tables or remove durable media while runs exist: the migration downgrade explicitly refuses non-empty workflow state. A code rollback to a pre-workflow release requires drained in-flight workflow jobs and a deliberate continuity plan; hiding cards alone does not make old workers compatible.
