# Named trend references — 2026-11-27

## Fresh audit before production changes

1. Baseline: `9949ca8a70ba9653f0b0318f1924d02535e35344`, default and production branch main; successful deploy 45817847774. Open PR 671 touches the inline trend editor; do not absorb its unrelated scope. Local execution is necessary for requested test-first and browser verification.
2. Exists: v1 per-recipe image ranges, Seedance video requirements, user fields, server preflight, hidden recipes, authenticated audited admin writes. Product-owned verified Kling video/audio, model capacity validation and normal billing/outbox lifecycle.
3. Partial: v2 already has named image inputs and semantic mapping. Preserve its independent sequential workflow and immutable snapshots.
4. Missing: v1 explicit strict/range named slots, admin-confirmed prompt discovery, per-slot uploader and durable preset images.
5. Reuse: AdminTrend JSON, user-field validation, model capacities, upload/probe/storage, TemplateVideoService and existing run orchestration.
6. Prefactoring: isolate named-reference normalization/assembly in a domain module; avoid changing generic GenerationService contracts.
7. Risks: optional gaps can shift provider numbering; reject gaps per media kind. Never trust a submitted media kind or admin URL. Avoid private URL/prompt disclosure. Validate owned uploads before generation.
8. Migration: additive product-owned template image metadata, nullable uploader attribution. No backfill or rewrite of existing trends. New schema is opt-in in AdminTrend payload.
9. Public seams: TrendService normalization/run and HTTP input boundary, upload authorization, browser admin/customer journeys. User explicitly requested TDD, backend checks before debit/provider and UI smoke; these are the selected seams.
10. Admin decisions: per-trend mode/slot names/help/type/order/source/required flags. No global reference limit change. Preset video remains bounded by existing supported provider capability.
11. Observability: reuse audited admin commands, upload actor/entity events and safe trend rejection logging. Never log URLs, prompts or personal field values.
12. Acceptance: four named images in order; strict count and required values; typed video; preset admin image/video cannot be overridden; admin can edit existing trends and confirm extracted Image1/@image_1 references; ordinary legacy/free generation remains unchanged.
13. Rollout: all six exact-head CI gates, two-axis review, merge and exact-main immutable deployment. Keep additive metadata/media on rollback; disable new named trends before old code rollback (old code cannot enforce the new contract). No production data writes or paid smoke without a concrete reviewed scenario.
14. Plan: (1) ledger + domain count RED/GREEN; (2) typed/owned run validation and preset lifetime RED/GREEN; (3) public/API privacy; (4) admin/customer UI browser RED/GREEN; (5) regressions/type/build/migration; (6) independent review, PR, CI, release evidence.

## Guidance inspected

- `.agents/` and `.clinerules` absent in this clean checkout (including ignored local guidance).
- Bambale0/skills current engineering implement, TDD and code-review: vertical slices at public seams and two-axis review.
- Bambale0/claw backend-integration: service boundary, validation, reuse billing/idempotency and public docs.
- wondelai/skills ux-heuristics: clear field labels, visible upload state and actionable error prevention.
- Bambale0/dev-agents-pack backend-python: explicit contracts and behavior regressions.
- agentskills/agentskills specification inspected: skill authoring only, no applicable runtime engineering guidance.
- anthropics/skills webapp-testing: inspect rendered UI, test browser flows and capture evidence using existing project Playwright infrastructure.
- Start baseline not changed or ambiguous. Companion project-specific prerequisites are not imported as KSU authority.

## Verification matrix / progress

### First vertical slices

- RED on unchanged main: two named-reference service tests failed (strict schema ignored, incomplete set admitted). GREEN after opt-in normalization/run mapping.
- RED: owned verified media regression admitted foreign URLs; GREEN after owned metadata lookup before generation. RED: audio disguised as video admitted; GREEN after explicit video stream requirement.
- RED browser: named fields absent and existing admin trend had no discovery confirmation. GREEN Chromium: 25/25 named/customer/instruction/v1+v2 admin scenarios, typecheck and static build pass. Screenshot of four named slots inspected at 393px.
- Focused backend: 280 passed, 3 integration cases deselected locally because PostgreSQL/ffmpeg are absent; two upload authorization/invalid-byte tests pass. New preset lifetime integration will run in CI against PostgreSQL. Ruff and compileall pass.
- WebKit on Windows cannot record video reliably in this Unicode OneDrive path. The first run failed before page creation (Screencast.startVideo). ASCII output alone still stalled recording. With recording disabled in an ignored local-only config, the new named-slot journey passes in mobile WebKit (1/1); repository CI retains original video evidence settings and includes the new file in Linux WebKit coverage.
- No production recipes, users, wallets or provider calls changed. No migration has run on production.

- Unit/domain: pending RED/GREEN.
- Database/repository: additive metadata + CI integration pending.
- Authorization: existing admin policy, typed owned media checks; tests pending.
- Migrations: additive upgrade and ORM parity pending CI.
- Provider contract: preserve current image/video field mappings; tests pending.
- Idempotency/retry: reuse generation/admin lifecycle, no new submission path; regressions pending.
- API: typed slot request and privacy tests pending.
- Browser: named uploader, replacement/removal, required fields, admin edit/confirm pending.
- Smoke/deployability: pending exact-SHA six gates and deployment.
- Audit: existing safe rejection logging/upload and admin audit, validation pending.
- Configurability: per-trend schema and authenticated visual editor pending.
- Performance: at most existing recipe slot budget; no network on normalization, bounded media lookups on run.
- Rollback: additive schema retained; new named recipes must be disabled before old-code rollback.
