# KSU #561 — Trend photo → video active execution

## Audit and scope

- Baseline: `main@e9037324a096ea3992cd5f63e8044811a4a5bf5a`; work branch `feat/trend-photo-video-561`.
- Approved source: `/root/agent-work/ksu-561-control/SPEC.md` (read in full before edits).
- Intended outcome: selected admin templates can require an explicit, resumable, owner-scoped image preparation step before a separate explicit video step; legacy v1 templates and freeform generation remain unchanged.
- Safety: no production checkout, live `.env`, production DB, Docker stack, paid provider call, customer message, commit, push, merge, deploy, or destructive migration.

## Required guidance evidence

- Local `.agents`: `AGENTS.md`, `README.md`, `SKILLS_INDEX.md`, `subagent-driven-development` plus its implementer/spec-reviewer/code-quality-reviewer prompts, `test-driven-development`, `frontend-ux-audit` and `references/full-audit-checklist.md`, `requesting-code-review`, and `code-review-and-quality` were read. No skill scripts are being executed blindly.
- `Bambale0/skills`: controller-refreshed task-relevant implement/TDD/code-review guidance; applied through the local execution/review flow.
- `Bambale0/claw`: controller-refreshed UX/UI and QA audit guidance; applied to customer/admin states and responsive/a11y checks.
- `wondelai/skills`: controller-refreshed design-everyday-things guidance; applied to explicit step affordances and error recovery.
- `Bambale0/dev-agents-pack`: controller-refreshed backend/frontend/test agent guidance; applied to existing seams and focused tests.
- `agentskills/agentskills`: current README confirms progressive disclosure and minimal selected skills; no KSU-specific workflow.
- `anthropics/skills`: controller-refreshed webapp-testing guidance; applied to browser-seam test planning. Public fetch for the named path was unavailable in this environment; no claim of applying unavailable text.
- `Bambale0/start`: baseline is not being changed; no additional ambiguous Start rule required beyond KSU AGENTS.

## Existing / partial / missing

- Existing: `admin_trends.payload` recipe normalization and v1 public/admin DTOs in `app/services/trends.py`; v1 routes in `app/api/v1/trends.py`; `GenerationService` quote/create and durable wallet/outbox lifecycle; `MediaAsset` and media ingest readiness; trend collections and counters; React Mini App under `frontend/mini-app`; static admin editor.
- Partial: Model capability validation and image-to-video adapters exist for freeform actions, but are not tied to a protected trend workflow. Admin editors are v1-shaped. Existing trend run commits generation independently.
- Missing: schema-versioned v2 recipe with explicit image/video steps and input bindings; workflow/run + step persistence; owner-scoped resumable API; atomic/idempotent step reservation with generation key; v1 bypass rejection; server-side ready-asset gate; step-aware user runner; v2-preserving admin editor; focused DB/API/UI regressions and docs.
- Prefactor first: keep v2-specific validation/orchestration in a focused trend workflow service/module; do not turn general generation into a generic workflow engine.

### Backend audit before implementation (2026-10-27)

- Exact baseline verified locally: `e9037324a096ea3992cd5f63e8044811a4a5bf5a` on `feat/trend-photo-video-561`.
- Reuse confirmed: `TrendService.normalize_recipe/validate_recipe/public_view/run`, `GenerationService.prepare_request/create`, `ModelCatalog.prepare`, `MediaAssetService.ready_assets_for_generations`, existing owner dependency, wallet debit idempotency, generation outbox, and media ingest.
- Confirmed limitation: `GenerationService.create()` commits the generation, wallet debit, outbox and progress row before returning. This slice therefore uses a durable workflow/step reservation and deterministic generation UUID as the recovery boundary; a crash after generation commit but before step update is recoverable by re-reading that generation, but a single database transaction spanning the existing service is not introduced.
- Missing for this slice: v2 normalization/validation, durable workflow/run-step rows and additive migration, protected workflow/quote/run/status endpoints, legacy v1 bypass rejection, and focused behavioral coverage.
- Security decisions: owner is always derived from signed `CurrentUserDep`; step 2 resolves the persisted step-1 generation and a ready image `MediaAsset` owned by that user; client URLs and completion claims are ignored/rejected; public DTOs are allowlisted and omit prompts, provider payloads, snapshots, wallet details and external media URLs.
- Observability decisions: logs identify workflow/run/step/generation/request/attempt/status/failure category only; no prompts, provider payloads or private media URLs. Usage increments at workflow creation under a trend row lock, never per step.
- Verification plan: unit validation/mapping, v1 bypass, owner isolation, ready-owned-asset gate, quote-before-debit, changed-body replay, duplicate command, usage count, migration parity, focused API tests and compile/lint checks. Frontend/admin UI, paid provider calls, production smoke and exact-head CI remain out of scope/controller-owned.
- Source-access note: controller-refreshed evidence for `Bambale0/skills`, `Bambale0/claw`, `wondelai/skills`, `Bambale0/dev-agents-pack`, `agentskills/agentskills` and `anthropics/skills` was recorded above. In this session, the public fetch for the named Bambale0 skill paths was unavailable; local KSU guidance and the controller-provided current evidence are used, while the accessible Agent Skills and Anthropic repositories were checked for progressive disclosure/webapp-testing conventions. No skill scripts were executed.

## Frozen v2 recipe and public workflow contract

The implementation uses the smallest typed shape compatible with current catalog/pricing seams. Mutable labels, prompts, models, parameters, slot labels/help/order/requiredness, bindings, previews, and prices are supplied by the admin payload and validated server-side; only structural keys and step ordering are code constants.

```json
{
  "schema_version": 2,
  "workflow_type": "sequential_photo_video",
  "preview_url": "https://...",
  "steps": [
    {"id":"prepare_photo","kind":"image","title":"...","instructions":"...","model_id":"...","prompt":"...","parameters":{},"inputs":[{"id":"person_photo","label":"Ваше фото","help":"...","type":"image","required":true,"order":0}],"price":{}},
    {"id":"animate_photo","kind":"video","title":"...","instructions":"...","model_id":"...","prompt":"...","parameters":{},"inputs":[],"bindings":[{"from":"prepare_photo.output_image","to":"first_frame"}],"price":{}}
  ]
}
```

Public DTOs expose `workflow_type`, a safe preview, ordered step metadata, input labels/help/requiredness, current status, quote, generation/media IDs and safe media URLs only. They never expose prompts, provider payloads, recipe snapshots, external provider URLs, wallet internals, or init data.

Planned endpoints (exact paths are finalized in contract tests before UI integration): `GET /trends/{id}` safe recipe; `POST /trends/{id}/workflow` create/resume owner run; `GET /trends/workflows/{run_id}` owner read; `POST /trends/workflows/{run_id}/steps/{step_id}/quote`; `POST /trends/workflows/{run_id}/steps/{step_id}/run` with an owner-scoped command key and request hash. Legacy `POST /trends/{id}/run` rejects v2 before quote/debit. Step 2 never accepts client URLs or a completion claim.

## Verification matrix

- Unit/domain: planned v2 recipe validation, slot order/binding and state transitions.
- Database/repository: planned additive migration, owner/run/step uniqueness, immutable snapshot, ready asset ownership.
- Authorization: planned owner-scoped reads/mutations and admin permission parity.
- Migrations: additive only; rollback is application flag/disable, no destructive down migration while runs exist.
- Provider/external contract: reuse model catalog/capability and existing image-to-video adapter; no paid calls.
- Idempotency/retry/reconciliation: planned command key + payload hash, duplicate/parallel request tests, unknown result read/reconcile.
- API integration: planned safe DTO, v1 bypass, quote/run/status tests.
- Frontend/Mini App E2E: planned runner locked/loading/ready/error/resume and explicit step-2 CTA tests; no live provider.
- Smoke/deployability: local isolated backend checks, frontend typecheck/build, release contract checks; exact-head CI remains controller-owned/pending.
- Observability/audit: workflow/step/generation/request/status/failure category without prompts/PII/private URLs.
- No-hardcode/admin configurability: v2 recipe values are admin payload + catalog/pricing validation; no business price/model values in UI.
- Performance/query shape: owner-scoped indexed reads and no unbounded workflow loads.
- Rollback/recovery: preserve v1 and paid snapshots; disable new v2 starts without deleting runs.

## Numbered implementation steps and progress log

1. Audit, frozen contract, and focused tests: **completed for backend slice**.
2. Backend schema/service/API/migration with TDD: **implemented; review handoff**.
3. Customer React runner and category metadata: pending.
4. Admin v2 editor and preservation tests: pending.
5. Integrated verification, independent spec/quality/security review, docs/rollout notes: pending.

### Backend implementation handoff (2026-10-27)

- RED: `APP_ENV=test KSU_ALLOW_TEST_DATABASE=1 /tmp/ksu-561-venv/bin/python -m pytest -q tests/test_trend_workflows.py` first failed with the expected missing-feature failures (`model_id is required` / missing v2 order validation) after the initial system-Python dependency error was isolated.
- GREEN: the same focused workflow file passed **8 tests**; adjacent legacy trend service tests passed **65 tests total** with no paid/provider calls.
- Added: `app/services/trend_workflows.py`, `app/db/trend_workflow_models.py`, `alembic/versions/0044_trend_workflows.py`, v2 dispatch/bypass in `app/services/trends.py`, owner-scoped routes in `app/api/v1/trends.py`, Alembic model registration, and `tests/test_trend_workflows.py`.
- Covered: exact two-step image→video validation, typed ordered slots, consecutive `@ImageN`, real binding target, v1 bypass before `GenerationService.create`, ready-owned-image step-2 gate, same-key replay, changed-body replay, and once-only usage increment in focused tests.
- Static checks: targeted Ruff passed; `compileall` passed. Full backend suite, live PostgreSQL migration parity, exact-head CI, independent spec/quality/security review, frontend/admin work, paid calls and deployment were intentionally not run/changed and remain controller-owned.
- Known implementation limitation for review: the existing `GenerationService.create()` commits independently. The deterministic generation UUID and persisted step reservation provide recovery/idempotency, but do not create one new cross-service transaction. Worker-side status synchronization and full DB/API concurrency tests require the mandated review/isolated database pass.

## Risks / follow-ups

- Exact `ModelCatalog` field names and generation transaction seam must be confirmed from current code before implementation; no invented provider payloads.
- Exact-head GitHub CI, merge, deployment, and production smoke are controller-owned and must not be claimed here.


## Independent controller verification — backend BLOCKED pending fixes

The controller ran a separate, real PostgreSQL smoke at the public TrendService/TrendWorkflowService seams against `ksu561_controller` on task-only port 32788, with separate Redis DB 14. No live database, customers, provider calls or paid requests were used.

- New migration applies and `alembic check` reports **No new upgrade operations detected**.
- Focused new + adjacent suite: **115 passed in 9.88s**. This does NOT prove the workflow happy path.
- **P1 confirmed:** a saved valid v2 template with a required image slot cannot be read through `TrendService.get_public`: it returns `LookupError: Trend not found`. `public_trend_view` quotes using empty required inputs, so the catalog path rejects its own recipe.
- **P1 confirmed:** submitting the actual required photo via `reference_urls` with no unrelated text values fails `Required workflow input is missing: person_photo`. Image slot validation incorrectly demands a second value in the text-values dictionary.
- **P1 confirmed:** after supplying that redundant value to reach the next boundary, a real `run_step` fails PostgreSQL `trend_workflow_steps_generation_id_fkey`: it flushes the reference before the Generation row exists. No generation or wallet transaction was created, and the synthetic balance remained 1000.00.

Reproducer: `/root/agent-work/ksu-561-control/controller_backend_smoke.py`; results: `controller_backend_smoke_result.json` and `.log`. Controller regression requirements, including replay after a later retry, quote drift inside debit, expired provider URLs and immutable attempt history, are in `/root/agent-work/ksu-561-control/controller-review-cases.md`. Read these before accepting the backend or starting UI integration.

Required next action: add true PostgreSQL/API regression tests reproducing these three failures, repair the root causes, then re-run the full owner/quote/debit/outbox/media/idempotency path. Do not weaken or replace the existing positive assertions merely to make the suite green. A same-object mock cannot validate transaction/FK ordering or concurrency. Backend acceptance remains blocked until the independently reproduced happy path works.

## Fix pass — controller blockers (2026-10-27)

- Read `/root/agent-work/ksu-561-control/controller-review-cases.md` and `controller_backend_smoke_result.json`. The three reported failures were reproduced first in the focused test additions: public quote with required image slot, image-only request without a text value, and generation-link FK ordering. Focused RED evidence was **4 failed / 8 passed** before the corresponding fixes; after implementation `tests/test_trend_workflows.py` passed **21/21**.
- Public v2 reads now quote with safe synthetic HTTP(S) image placeholders. `_step_request` treats image inputs as typed media rather than text values; `image_inputs[{slot_id,url}]` is supported, ordered legacy `reference_urls` remains compatible, and step 2 rejects client media URLs.
- Step 2 validates `ModelCapabilityResolver` image-to-video operation/input capability, explicit binding targets, typed slot options and ordered `@ImageN` tags. Optional image slots cannot precede required slots or silently shift references.
- Workflow steps now persist a non-FK generation reservation before calling the existing committing `GenerationService`, then attach the FK only after the generation exists. Terminal failures allow an explicit new command key; prior command keys/hashes and generation IDs are retained in `attempt_history`, and old-key replay is rejected safely. Same-key replay remains idempotent.
- Step 2 provider input persists a durable `ksu-media://<asset-id>` marker, not `MediaAsset.source_url`. `GenerationProviderService` resolves it immediately before submission through `MediaAssetService.provider_source_url`, which creates a fresh absolute signed/presigned URL and fails closed when storage is unavailable. Public workflow media is an owner-safe allowlist with no provider URL.
- Workflow run/run-step routes require bounded `Idempotency-Key`; missing keys fail HTTP 400 before service work. Quote cost is passed into the existing GenerationService debit boundary and a changed effective price fails before debit. Lifecycle logs/Prometheus events include only event, workflow/step/generation/request/attempt/status/failure category.
- Additive migration `0044_trend_workflows` includes reservation/history columns and downgrade refuses when either workflow table contains rows. Admin metadata-only updates preserve v2 payload structure and explicit schema-1 downconversion is rejected.
- Real isolated PostgreSQL/Redis smoke (task-only `127.0.0.1:32788`, Redis DB14, no provider) passed: public v2 read returned `sequential_photo_video` with 2 steps; image-only step created one Generation and one wallet transaction; same-key replay reused the generation; public status was `running` with no media URL. Balance changed from 1000.00 to 975.00 for that synthetic paid image generation.
- Migration verification: `alembic upgrade head` from 0043 to 0044 passed; `alembic check` reported **No new upgrade operations detected**. Focused/adjacent tests passed **99/100**; the one failure was the pre-existing persistent task-DB collision on fixed fixture external id `kie/media-task` in `tests/test_media_storage.py`, not a workflow failure. Full backend suite and PostgreSQL concurrency/late-callback/provider-ingest end-to-end tests were not run in this pass.
- Remaining limitation: the existing `GenerationService.create()` commits generation, wallet, outbox and progress independently of the final workflow FK update. The durable reservation and deterministic generation UUID make crash recovery deterministic, but this is not one cross-service transaction. Exact-head CI and independent controller review remain pending; no commit/push/deploy was made.


## Independent controller verification — fix-pass 2 must not be accepted yet

Fresh task-only database `ksu561_controller_v2` applied the revised migration 0044. Actual service-level PostgreSQL test with synthetic users/owned image bytes and zero provider calls now confirms public v2 read, photo create/debit/outbox, durable photo readiness and video create/debit work. Source media is stored as a stable internal asset marker, not provider source_url. This repairs the first three independently reproduced blockers.

**Additional confirmed blockers (real DB / source evidence):**
1. **Crash-after-debit recovery is still broken.** The controller injected a failure immediately after the real GenerationService.create commit and before workflow FK assignment. Repeating the SAME idempotency key returns at run_step's initial replay guard before inspecting reserved_generation_id. Public GET also ignores that reservation. Result: 1 generation + 1 debit persisted, balance 9975.00, but workflow public generation_id is null/status queued forever. Fix same-key/GET reconciliation before the early return, or preferably make workflow link + attempt + generation/debit/outbox one transaction. Test this exact crash seam with real PostgreSQL, not a fake create result.
2. **Missing explicit quote is accepted and charged.** Calling run_step without quoted_cost_rox created a generation and a 25.00 debit. The request schema permits null and GenerationService comparison is optional. Require the accepted price/quote context for workflow run requests (while quote endpoint may omit it) and compare the effective cost in the actual creation transaction. Preserve backwards compatibility of ordinary generation.
3. **Provider routing gap:** repository search finds `_resolve_workflow_media_input` called ONLY in `GenerationProviderService.submit_kie`. Nexus and Neironych call `_input_for` directly and have no resolver hook; internal `ksu-media://...` therefore reaches their own payload/validation path. Add fresh owned-asset resolution to ALL configured submission adapters including fallback/retry, with adapter-level tests and zero live provider calls. A Kie-only smoke does not verify the user's Seedance routing.
4. **Successful-photo redo unsupported in source:** existing_generation=succeeded with step status queued/ready returns existing for a new key. The spec requires an explicit paid redo after preview, while preserving earlier photo and selected asset/attempt. Define an explicit retry/redo intent, serialize by workflow when it could race step2, and reject incompatible in-flight redo clearly rather than silently returning the previous operation.
5. Current workflow media DTO exposes only authenticated download_url, not a renderable signed view URL or all ready media choices. User UI must display the real selected photo and select among outputs without leaking unsigned/private URLs; provide safe media URLs/array using existing ownership serializer or explicit authenticated media fetch.

Reproducer and exact outputs: `/root/agent-work/ksu-561-control/controller_backend_deep_smoke.py`, `controller_backend_deep_smoke_result.json`, `.log`. Controller guarantees no paid providers, no production reads/writes, only synthetic test DB/media. The source-level redo/provider findings still require final public seam regressions. Before the next review, read `/root/agent-work/ksu-561-control/controller-review-cases.md` to cover concurrency, optional-slot indexing, stale quote, late callbacks, owner isolation, old-key replay and template edit/hide recovery. Do not call the backend complete while these are unresolved.


### Controller design clarification and adapter requirement

Do NOT add a second pricing system or editable arbitrary step-price JSON to satisfy a review wording issue: the approved design explicitly reuses existing admin-managed model tariffs and server quote/debit. Per-step displayed prices are derived from each step's selected model + validated parameters. The existing price-admin surface is the authoritative control plane. This is intentional, not a missing feature.

For the provider bridge, Neironych already freezes immutable request bytes in `_freeze_new_submission` BEFORE paid POST and uses the same bytes on uncertain retry. Resolve a workflow asset into a fresh signed URL BEFORE the first snapshot is frozen; never regenerate the URL inside an already-frozen uncertain retry, as that would violate provider idempotency. Nexus needs equivalent source resolution before normalization/create. Add tests that exercise all three adapters and prove the internal marker never reaches outbound HTTP, while Neironych reuses the identical original byte body on uncertain replay. Do not claim a helper unit test proves this full execution path.

The controller full backend suite is running against another fresh isolated database (`ksu561_full_first`/Redis DB12); its result will be in `control/controller-full-first-tests.log` and `.exit`. No schema/fixture collisions with the agent DB. This run does not replace missing new feature DB/concurrency regressions.


### Controller adapter probe — confirmed P1, not merely inspection risk

`controller_provider_bridge_probe.py` exercised the actual Nexus and Neironych `submit` methods on real test PostgreSQL generation rows for Seedance 2.5 with a ready owned photo marker. Only external provider clients/reference probes were replaced with local fakes (zero real network/provider calls). Results: Nexus raised `NexusGenerationContractError: Nexus reference must be an absolute URL or product-owned media URL`; Neironych finalized the test task failed with `reference_images: нужен HTTPS URL.` Neither fake client was reached. Both actual adapters must resolve the internal marker before provider normalization/freeze; Kie-only resolution is insufficient. Results in control/controller_provider_bridge_probe_result.json.

Controller full suite on a fresh task-only database completed: **2021 passed, 1 warning in 79.58s** (existing SQLAlchemy row-count warning in trend category deletion test). This is a regression baseline, not acceptance of new workflow recovery/provider paths.

A small backwards-compatible `GenerationService.create/create_many` transaction-owner option (default unchanged), propagated through the two existing audit wrappers, is a reasonable solution to the observed commit/link window: create + debit + outbox flush without internal commit, attach the step/attempt link, commit once under the workflow lock, then Redis wake. This is not a billing rewrite. If preserving reservation reconciliation instead, test actual crash points, same-key concurrent responses and owner GET, not only the success path.

## Critical fix handoff — crash recovery and mandatory quote (2026-10-27)

- Scope for this pass: backend Python/tests/ledger only, prioritizing the controller's P1 crash-after-debit and missing-quote findings. Frontend, admin UI, provider-adapter completion and unrelated suites were not expanded.
- RED evidence: `test_workflow_generation_joins_existing_transaction_before_linking` failed before the fix because the workflow did not pass transaction ownership to `GenerationService.create` (`KeyError: commit`).
- GREEN implementation: `GenerationService.create_many/create` now accept `commit` and `wake` flags, defaulting to the previous behavior. The workflow calls `commit=False, wake=False`, links the durable workflow step FK after generation/debit/outbox flush, then commits once. The two existing generation audit wrappers propagate both flags, so the transaction boundary is preserved through their validation seams.
- Real PostgreSQL regressions: `test_postgres_crash_recovery_links_reserved_paid_generation_before_replay` seeds an already-debited reserved generation, replays the same key, and verifies deterministic step/public linkage with exactly one generation and one wallet transaction; `test_postgres_missing_workflow_quote_does_not_create_or_debit` verifies no generation, debit, or balance change without `quoted_cost_rox`.
- Exact verification: `source /root/agent-work/ksu-561-control/TEST_ENV.sh && python -m pytest -q tests/test_trend_workflows.py` → **32 passed in 4.25s**. Targeted Ruff → **All checks passed**; targeted compileall → **passed**; `git diff --check` → **passed**.
- Existing same-key reservation reconciliation and public GET reconciliation remain in place for reservations created by an older process/version. New workflow crashes before final commit roll back generation/debit and reservation together, so replay safely creates the one paid attempt.
- Not run in this handoff: full backend suite, adapter-path tests for Nexus/Neironych/Kie, true concurrent multi-session race tests, provider/media ingest integration, exact-head CI, frontend/admin E2E, commit/push/deploy. These are verification limits, not completion claims.


### Controller private-media browser boundary regression

The current workflow DTO calls `MediaAssetService.public_view(..., server_route=True)` for current media, media_options and previous-attempt media. This returns `/media/{id}/public`, but these photos are intentionally PRIVATE. A real ASGI GET returned **404** for the DTO URL. The same asset serialized with the existing default `MediaAssetService.public_view(asset)` yields a signed private view URL; ASGI GET returned **200 image/png, 82 bytes**. Fix all three workflow serializers to use the existing private signed view, not the publication-only route; do not publish photos or weaken the public endpoint. Add a regression that actually opens the DTO media URL. Evidence: `control/controller_private_media_probe_result.json`.

A separate read-only customer/admin UX adviser (no implementation files touched) is preparing `control/frontend-design-readonly.md` for the upcoming frontend/admin writer. It uses actual subagents and the pinned .agents frontend-ux-audit skill. Read it when present; do not wait on it to fix backend bugs.


### Controller correction completed — private-media URL, real HTTP regression

With no backend implementation writer active (fresh worker completed; spec reviewer is read-only), the controller made the three narrowly scoped workflow serializer calls use the PRIVATE signed URL (`server_route=False`), leaving the public publication guard intact. Added `tests/test_trend_workflow_private_media.py`: real PostgreSQL workflow + ready private image bytes + actual media ASGI routes. RED: 1 failed (DTO URL returned 404). GREEN: 1 passed; current media and every media option return the PNG bytes, while `/public` still returns 404. Ruff passed. Logs: control/private-media-regression-red.log and -green.log. Please retain this regression and change; no provider calls or production writes occurred.


## Controller stage adjudication and handoff

The core backend slice is accepted for customer/admin UI implementation, NOT as completion of the whole epic. The latest spec review correctly reports no remaining Critical core issue. Its media-404 finding has since been repaired and verified by the controller with the committed-tree test `test_trend_workflow_private_media.py` (not yet Git-committed). The redo flag is now explicitly `retry=true` plus a new command key and fresh quote; a new key alone is intentionally not paid consent. The absence of the not-yet-implemented customer/admin UI is a NEXT SLICE, not a reason to prohibit that slice from starting. No independent per-step price store will be added.

Real PostgreSQL concurrency verification now passes simultaneous create and simultaneous run, both equal and different command keys: one workflow, one generation, one debit, one outbox, and exactly one quoted charge. Evidence: control/controller_workflow_concurrency_result.json. The counter currently increments at workflow creation; the frontend integration must not count mere catalog opens as paid generation launches, and final telemetry/counter refinement remains to check.

Controller stopped only this task's backend coordinator process after the completed core slice to avoid repeating full-epic reviews before UI exists. All work is retained. A fresh bounded frontend/admin sequence follows, with one implementation writer and independent reviews. Production processes, checkout, credentials and data remain untouched.


## Controller: UI recovery/history contract implemented and verified

Added immutable run presentation metadata and safe model/settings summaries, latest-owner workflow GET (including hidden-template continuation), trusted generation-history workflow pointer, first-accepted-generation-only usage count, consistent workflow -> step row locking, and correct @Image1 validation for the video bound image. No customer recipe settings/prompts exposed.

TDD at actual PostgreSQL/HTTP seams: 5 intended failures +1 passing negative @Image2 case, then **40 passed** across resume/private-media/existing workflow regressions. Targeted Ruff passed. The narrow mocked tests now include the Generation.parameters and workflow.trend_id attributes used for history links; the former count-on-state-open expectation was corrected to the approved count-on-first-generation behavior and covered with real PostgreSQL tests. Logs: control/workflow-resume-red.log and workflow-resume-green.log. Frozen UI handoff: control/backend-ui-contract-ready.md.


### Controller personalization regression correction

Real feature-boundary tests reproduced 10 failures: required personal fields hid an otherwise valid workflow from the catalog; repeated substitutions re-expanded customer placeholders; invalid dates, NaN/Infinity, whitespace, overlong and object values were accepted. Public estimates now use synthetic valid placeholders (never persisted/sent as customer input), workflow values reuse the existing v1 field validator through a small public wrapper, and substitutions are single-pass/literal. Named fields without explicit prompt tokens are not silently ignored. New test file: tests/test_trend_workflow_personalization.py. RED10failures; full focused regression result in control/workflow-personalization-green.log. Ruff passed.


## Controller customer UI pre-review: unstable quote dependencies

The completed customer page currently rebuilds `photoInputs`, `photoImageInputs`, `photoValueInputs` arrays on EVERY render, uses those unstable arrays as useMemo dependencies for imageInputPayload/valuesPayload, then uses the resulting new quoteBodies object in effects that set quoteLoading/quotes state. With valid inputs, the effect can immediately repeat on its own state updates and spam the quote API. Memoize the derived slot arrays from stable step.inputs and use stable serialized request identity (or scalar dependency keys) for quote effects. Add a browser assertion that valid unchanged input triggers a bounded number of quote calls, and changing a field invalidates the old response. This is an important correctness/performance issue, not cosmetic.

`awaiting_media` is omitted from WORKFLOW_ACTIVE_STATUSES, so polling stops after provider success but before durable file ready, leaving Step2 locked indefinitely. It must remain a polling state. Also use the backend's160-character field length limit and real-calendar date validation; do not let frontend advertise500 when backend rejects160.

Backend UI contract is already implemented/tested: read control/backend-ui-contract-ready.md. Controller installed CI-pinned Playwright locally with task cache; actual customer/adjacent Chromium tests are running and recorded at control/customer-ui-first-browser.log. No frontend edits by the controller yet.


### Full regression cross-surface feedback

Controller fresh-schema integration run:2050passed/4failed (existing frontend source contracts in the unfinished admin/type changes). Migration parity passes. Detailed actual failures and preservation requirements are in control/admin-regression-feedback.md; do not remove tests to conceal v1 behavior changes. This is not a completed green release run.


## Final independent backend review corrections

Reviewer child01a17d2c-58ef-79e1-9484-b2c95c076ec8 used requesting-code-review/TDD. Controller reproduced five failures at real PostgreSQL/API and normalization seams: echoed v2 metadata lost steps; failed attempt admitted new payment without retry flag; selected second photo lost on reload; previous photo absent from attempt history. Separately, actual admin HTTP save reset usage8to0. Regression tests failed before correction.

Corrections: metadata PATCH preserves omitted steps with downconvert guard; explicit retry=true for failed attempts; chosen photo stored atomically with video admission; previous owned output/history media options preserved; locked fresh-row usage and stable incoming-command hash. Existing explicit-retry fixture now expresses retry=true and no conflicting next-step row. Admin integration command keys are unique per fixture while replay within the test retains the same key. **60 focused tests passed**; targeted Ruff passed. Logs:control/backend-review-regressions-red.log,admin-counter-red.log,backend-review-regressions-green.log. No paid calls or production writes.


### Admin contract verified against actual API

Controller discovered browser fixtures advertised ui_schema that real admin model responses lacked. Added the existing authoritative schema builder to both admin option surfaces; real authenticated HTTP regression failed before and passed after (duration/defaults/fields + privileged parity). No provider/model hardcode. Evidence:control/admin-live-schema-red.log and-green.log.


### Integrated browser regression fixes

Fresh static-export Chromium run on isolated3028:57passed/4failed. Two failures shared an actual v1 regression: new-template default was changed from the first server model to the first image model, hiding audio controls for a server-first Seedance model. Restored the existing server order; kept both original audio tests unchanged. Invalid-I2V UI correctly refused submission but its accessible label included help text; gave the selector a precise label plus described-by help. The lost-response fixture intentionally keeps the accepted task running, so its assertion now verifies the original task UUID/status and exactly one submitted command rather than incorrectly requiring a completed image. No validation/idempotency assertion was removed. Added both workflow/admin specs to the existing mobile-WebKit CI list without removing other tests.


## Continuation audit — 2026-10-27

Resumed the existing dirty worktree at backend HEAD `6e3eb9246fa756f34f7b0ad783e19004d28431c5`, draft PR #562; no writer was active. Preserved all prior backend, customer/admin UI and E2E work. Fresh isolated PostgreSQL migration, Alembic parity, Ruff, compileall and full backend run passed: **2061 tests**, one existing category-delete SQLAlchemy warning. The six final UI recovery review findings remain open and are assigned to a bounded native-subagent repair followed by separate Spec/Quality reviews, using the pinned `.agents` library. No production or paid provider operations.

Controller source inspection identified a remaining source-choice edge: after choosing a non-first photo for video, a later quote/retry omitting `media_asset_id` queries the first asset instead of the persisted photo-step selection. Add real PostgreSQL regressions for omitted selection and unavailable selected media, then retain the explicit choice or fail closed; do not silently animate another image. Controller owns this small backend seam; the UI agent owns only frontend/helper/E2E files.


### Continuation source-choice RED/GREEN

Added `test_video_retry_without_asset_uses_persisted_photo_or_fails_closed` with two real PostgreSQL variants. RED: wrong first-image marker and missing rejection for a failed selected asset, **2 failures**. Minimal fix makes `_ready_step1_asset` use the photo step's persisted `media_asset_id` only when the request omits its selection, preserving all owner/generation/readiness filters. GREEN: all workflow test files **63 passed in 9.78s**; targeted Ruff passed. Logs: `control/resume-source-choice-red.log` and `resume-source-choice-green.log`. Independent read-only native-subagent review is requested.

UI recovery repair is assigned to native child `01a17dbb-f6bf-7422-8c57-948ed2e1046c`, coordinator `01a17dba-3de4-7561-8c90-8fc9c82fb2be`; both use the pinned `.agents` library and preserve existing work. Only one UI implementation writer is active. Controller source-choice changes are isolated to backend/test/docs files.


### Independent source review follow-up

Read-only native reviewer `01a17dbd-f461-7ed2-a01d-27fd57173343` identified two compatibility/readiness gaps: older workflow attempts stored selection only on the video step, and a configured optional S3 backend did not prove that an owned remote object still exists. Reproduced the older-selection cases (**2 failed / 2 passed**) and added fallback to the stored video-step source while retaining owner/generation filters. Added semantic remote-source probe regressions before implementation. Remote validation will use a bounded read-only metadata probe off the event loop; no real external storage/provider requests are part of tests.


## Continuation integrated candidate — 2026-10-27

The customer/admin UI is now implemented in the existing branch, not a new workstream. The final owner-only receipt contract exposes opaque `command_id` on current and historical attempts, with no request bodies/hashes. Real PostgreSQL concurrency demonstrates that re-entered inputs and a delayed original using the same key create exactly one generation/debit. Legacy source selection remains pinned and remote owned media gets a finite off-loop metadata preflight before charge/submission.

Fresh isolated backend verification on the integrated candidate: **2074 passed**, one pre-existing category-delete SQLAlchemy warning; migration0044, Alembic parity, full Ruff and compileall passed. Evidence is `control/verified-backend-{summary.json,tests.log}`. A test-only fake unresolved reservation was strengthened to include the real ORM command field and assert that a receipt without generation remains unresolved; no production invariant was weakened.

The initial native UI child `01a17dbb-f6bf-7422-8c57-948ed2e1046c` implemented six recovery fixes, editor same-file retry and targeted tests. Independent native Spec reviewer `01a17dc9-6355-7652-8ea1-ac7de9843d49` found gaps in ambiguous reload and repeated-failure consent. Controller completed the bounded repair after an additional CLI invocation failed with model capacity, preserving all prior work. No fictional sub-agent completion is claimed. The controller's four corrected-selector RED journeys all failed for the actual behavior, then **47 focused Chromium journeys passed**, with typecheck and 24-route static export. The first exploratory RED run had locator mistakes and is not counted as behavioral evidence.

Final review then reproduced two consecutive failed attempts with unchanged input retaining consent (both image and video) and a disabled private-video input after reload: **3 additional RED failures**. Retry state is now keyed by command/generation/attempt plus status/input, and key-only video recovery permits re-entry. The final candidate reruns the 50 focused Chromium journeys and attempts the workflow/admin mobile WebKit suite; exact final outcomes belong to PR #562 and the local `final-ui-*` artifacts to avoid modifying the tested SHA merely to update CI links.

Independent source/receipt reviewer `01a17dcf-d3a5-7c02-91a4-72fe45d47f16` approved the bounded backend follow-up with no remaining Critical/Important findings; it was closed after its report. The UI reviewer is rechecking its final consent finding against the new regression. Source-specific review limits and live final disposition are recorded in PR #562. All real agents were instructed to use the pinned `.agents` library. Mandatory companion guidance was refreshed through GitHub and applied; no Start baseline change.

Known out-of-scope observation from read-only UI review: existing `browser-auth-session.ts` stores browser-login initData; the workflow adds no such storage. Assess that pre-existing authentication/session design separately rather than silently changing login during this feature. Physical Telegram iOS/Android, real paid generation and production deployment remain unverified and were not performed.

No merge, production migration, deployment, provider spend or customer notification. Rollout requires the existing release permission/gates; hiding v2 templates does not make old workers compatible with already queued owned-media markers.


### Final local candidate verification

- Full isolated backend: **2074 passed / 1 pre-existing warning**, migration/parity/Ruff/compile green; no backend changes since that run.
- Current frontend: typecheck and static export of24routes green; **50 focused Chromium tests passed** (customer workflow25, editor5, audio/share/back/instruction regressions20), including all seven controller recovery/consent RED/GREEN regressions.
- Mobile WebKit launch was attempted but failed before application startup because host GTK/GStreamer/other libraries are missing; **no WebKit pass claimed** and no system packages were installed on the production host. The CI Playwright container supplies those dependencies and explicitly includes new workflow/editor tests.
- Final mocked visual smoke on320/390/768px: no horizontal overflow, no page exceptions and zero paid POSTs; inspected screenshots use synthetic media, not customer data.
- Native independent UI reviewer `01a17dc9-6355-7652-8ea1-ac7de9843d49` approved the final bounded Spec and Quality fix after the per-attempt consent correction. No remaining Critical/Important finding in that reviewed scope. Reviewer did not run tests; controller verification is reported separately. `control/final-ui-rereview.md` contains the actual result.
- Scoped credential-pattern scan of the26candidate files: zero matches; this is not a claim of a full secret audit. No .env/.agents/venv/build/test-report paths are included. `git diff --check` is clean.

Exact final commit/PR CI links and any broad-suite results are recorded in PR #562 without amending the verified source tree. Merge/deploy requires separate authorization and exact-SHA release checks.
