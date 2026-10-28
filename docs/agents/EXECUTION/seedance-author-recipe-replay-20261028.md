# Seedance author-recipe replay parity

## Audit baseline

- Baseline: `origin/main` / production `530fbc4a70a2615cf9ffd2ba5ef7d547019c85b8`.
- Worktree: `fix/seedance-author-reference-priority-20261028`.
- Existing: `FeedRemixService` owns hidden prompt reuse, reference ownership validation, quote/launch parity, lineage and remix audit rows. `ReferenceResolver` canonicalizes persisted Seedance image/video aliases. Mini App `/remix` uploads typed owned references and quotes before launch. Provider adapters already freeze canonical `reference_image_urls` / `reference_video_urls` and preserve idempotency.
- Partial: source reference counts are exposed as requirements, but every author reference is replaced with viewer-owned media. The source's original video provenance is not represented in the draft.
- Missing: server-side restoration of the author's original Seedance video reference, an identity-vs-motion role prompt, public boolean provenance, and video-first/photo-fallback composer copy.
- Reuse: APIX's verified pattern: never use the rendered output MP4; restore original input video server-side; expose only `source_has_video_reference`; use viewer-owned photos for identity; keep mixed photo+video provider mode as reference.

## Outcome and acceptance criteria

1. `prepare` for a public Seedance 2.5 source returns `source_has_video_reference` without exposing author media URLs.
2. When author video exists, the viewer supplies owned image references only. Quote and launch restore the author video and build an explicit role prompt where `@Video1` controls motion/scene and `@Image1..N` control identity.
3. When no author video exists, no rendered output video is submitted; viewer-owned photos replace the author's image-role inputs and the author's prompt/settings remain server-owned.
4. Viewer-supplied video/audio references are rejected for the Seedance author-recipe path. Foreign/missing references still fail before quote/debit/provider work.
5. Non-Seedance feed repeats retain current replace-all-reference behavior.
6. Quote and launch use the same composition. Pricing, routes, duration/resolution, idempotency, lineage and publication permissions are unchanged.
7. Mini App describes the restored motion source without exposing its URL and requests only the typed viewer photos required by the source recipe.

## Architecture, security and data decisions

- Business logic remains in `FeedRemixService`; routes stay thin.
- No migration or mutable runtime setting: reference-role selection is a provider/product contract derived from immutable generation input provenance.
- Author URLs never enter public DTOs. Public state is a boolean plus counts.
- A public/profile-visible source is re-authorized server-side on every prepare/quote/launch. Viewer media continues through `ReferenceService.resolve_owned`.
- The original source result MP4 is never considered an input recipe.
- Logs contain source generation ID, model and counts only; no prompt or media URL.

## Verification matrix

| Area | Plan |
| --- | --- |
| Unit/domain | Role-prompt literal contract and source recipe selection. |
| DB/repository | Real `FeedRemixService.prepare/launch` tests with public source and owned/foreign references. |
| Authorization | Existing surface visibility and owned-reference checks; regressions for foreign video/image injection. |
| Migrations | N/A: no schema change. |
| Provider contract | Canonical mixed image/video parameters and Neironych/KIE frozen payload tests; no paid HTTP. |
| Idempotency/retry | Existing generation creation/outbox paths unchanged; quote/launch composition parity test. |
| API | Prepare DTO and quote/launch 422 behavior. |
| Mini App/E2E | Playwright route mocks for author-video and photo-only source recipes. |
| Smoke/deployability | TypeScript/build, focused backend, full CI exact head before release. |
| Observability | Safe count-only composition log. |
| No-hardcode/admin | N/A: deterministic provider contract, no mutable business value. |
| Performance | No new query; source parameters are already loaded. |
| Rollback | Revert service/UI/tests; no data migration or persisted rewrite. |

## Implementation plan and progress

1. [done] RED backend/API tests for video-first and photo fallback.
2. [done] Minimal server-side source-recipe resolver and role prompt.
3. [done] Provider frozen-payload coverage for supported mixed viewer-image + author-video requests.
4. [done] Mini App DTO/copy, image-only picker and E2E parity coverage.
5. [done locally] Focused checks and two-axis review.
6. [in progress] User authorized full release on 2026-10-28: publish a reviewable PR, require exact-head CI, merge only with all protected gates green, then verify the merged SHA in the production deploy/runtime and public Mini App path without a paid generation.

## Implementation and verification evidence

- `FeedRemixService.prepare` exposes only `source_has_video_reference`; original author input URLs remain private.
- Quote and launch share `_composition`: Seedance 2.5 strips author identity images, restores original author video inputs, injects the exact required number of viewer-owned photos, and wraps the prompt with explicit `@Video1` motion / `@ImageN` identity roles. Mixed refs use the model's supported reference-mode inference; the unsupported internal `omni_reference_task_type` field is never sent through KSU preflight.
- Photo fallback keeps the author prompt/settings and viewer photo while never reading `Generation.result_url` into provider parameters.
- New author-recipe generations receive an internal `_private_author_recipe_replay` marker in the same transaction as wallet/outbox/remix-audit persistence and are woken only after commit. History, recreate and action-context surfaces use that marker to redact the wrapped hidden prompt and author video URL; marked replays expose only publish after completion. Historical unmarked Seedance remixes retain their existing behavior.
- Prepare, quote and launch reject a derivative remix as a new source, including direct API calls after publication, so private wrapped recipes cannot be recursively replayed or disclosed.
- Role-prefix space is reserved in `prompt_max_length` and checked against both KSU's 30,000-character limit and Neironych's 40,000-byte UTF-8 limit. Hidden oversized sources fail during prepare; visible prompts can still open the composer and be shortened before quote.
- Pure backend/provider suite: 63 passed across replay, history/privacy, action restrictions, KSU/Neironych routing, prompt-limit and composer tests.
- Lint: targeted Ruff passed. Targeted MyPy exposed repository-wide pre-existing strict errors when following imports; no new Ruff failure. The new service module is typed and covered by runtime contract tests.
- Mini App: `pnpm run typecheck` and `ROXY_E2E=1 pnpm run build` passed.
- Browser: headless installed Chrome at 390x844 with mocked prepare responses passed both author-video and no-video branches; the page showed the matching copy and accepted `image/*` only.
- Independent Standards and Spec reviews found and drove fixes for the unsupported task-type field, derivative-history prompt/video disclosure, contradictory top copy and role-prefix prompt budget. Focused checks passed after the fixes.
- PostgreSQL integration tests were authored in `tests/test_feed_remix_own_references.py`. This Windows host has no Docker/PostgreSQL binaries, so they remain an exact-head Linux CI gate; the test guard prevented any accidental live-database access.
- Release authorization now covers PR, merge and production deployment for this feature. Paid provider generation remains out of scope; production verification must use immutable release/runtime evidence and read-only public smoke.

## Guidance

- Applied: `Bambale0/skills` implement, TDD and code-review; `Bambale0/claw` backend-integration and kie-seedance; `wondelai/skills` working-with-legacy-code; `Bambale0/dev-agents-pack` backend-python; `anthropics/skills` webapp-testing.
- Release continuation applied current `Bambale0/claw` release-hardening, `wondelai/skills` release-it, and `Bambale0/dev-agents-pack` release-manager guidance: exact-head gates, immutable deploy evidence, health/public smoke, preserved backup and revert-based rollback. `agentskills/agentskills` has no current application-release skill.
- `agentskills/agentskills`: no current task-specific backend/Seedance skill found.
- Repository-local `.agents`: absent in this checkout; versioned KSU `AGENTS.md` and existing Seedance execution ledgers are the local authority.
