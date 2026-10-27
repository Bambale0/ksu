# Two-step trend visual parity — 2026-10-27

## Audit baseline

- Baseline and deployed revision: `9143e6f8c2258030c1ae03e3a4b251cab32394c9`.
- Existing: versioned `sequential_photo_video` recipes, server-side Step 2 lock, owner-scoped generated-photo selection, separate quotes/consent, resume/retry, admin opt-in and browser coverage.
- Partial: the customer page already exposes adjacent Step 1/Step 2 navigation and a locked Step 2 card, but both are text-first. Clicking locked Step 2 scrolls to Step 1 and shows an inline alert.
- Missing: screenshot-matched media cards and an explicit modal that explains why Step 2 is unavailable before offering cancellation or navigation to Step 1.
- Reuse: public trend/workflow preview thumbnail, selected owned photo after Step 1, existing workflow state and focus target. No API, database, provider or financial changes.

## Acceptance

1. Only `sequential_photo_video` trends receive the new presentation; legacy and ordinary one-step trends are unchanged.
2. Mobile overview shows two equal portrait image cards side by side with camera/video glyphs and `ШАГ 1` / `ШАГ 2` labels.
3. Before Step 1 is ready, Step 2 is visibly dimmed and carries a centered `Сначала Шаг 1` chip while remaining clickable for explanation.
4. Clicking locked Step 2 opens a dark, high-depth modal with title `Сначала Шаг 1`, explanatory copy, and full-width `Отмена` and `Перейти к Шагу 1` actions.
5. Cancel, backdrop and Escape close the modal. `Перейти к Шагу 1` closes it, scrolls to and focuses the existing Step 1 form. Focus is placed inside the dialog and restored on dismissal.
6. Once an owned Step 1 photo is ready, Step 2 unlocks and no modal intercepts it. The existing quote/payment/provider flow is unchanged.
7. Cards and modal have no horizontal overflow at 320/375/390/430 px, respect safe-area bottom padding, 44 px touch targets, visible focus and reduced-motion preferences.

## Verification matrix

| Area | Decision |
|---|---|
| Unit/domain | N/A — no domain behavior changes. |
| Database/repository | Existing workflow suites; no persistence change. |
| Authorization | Existing owner-scoped workflow/media endpoints unchanged. |
| Migrations | N/A — no schema change. |
| Provider contract | N/A — no outbound payload change. |
| Idempotency/reconciliation | Existing step execution code untouched. |
| API integration | Existing workflow DTO fields only. |
| Frontend E2E | RED/GREEN Playwright assertions for exact locked-card/modal/cancel/go-to-Step-1/unlock behavior and legacy isolation. |
| Smoke/deployability | Typecheck, production build, focused Chromium plus iPhone/iPad WebKit and exact-head CI if released. |
| Observability/audit | N/A — presentation-only interaction; existing workflow telemetry retained. |
| No-hardcode/admin | Workflow enablement remains admin-controlled; copy is product UI text matching the supplied reference. |
| Performance | Reuse existing image URLs; no new request or polling path. |
| Rollback | Revert the frontend-only commit; workflow state and accepted generations remain compatible. |

## Plan

1. Add a browser regression that specifies the two media cards, dimmed lock chip and accessible modal behavior.
2. Implement the smallest presentation/state change in the existing trend route and CSS module.
3. Verify locked, cancelled, redirected and unlocked states; retain one-step regression.
4. Run focused Chromium/WebKit, typecheck/build, lint/diff, then independent Standards/Spec review.

## Guidance

- Repository `AGENTS.md`; local `.agents` is absent.
- `Bambale0/skills`: TDD and code-review; UI prototype guidance was inspected but not used because the user supplied a single approved visual rather than requesting alternatives.
- `Bambale0/claw`: frontend QA and frontend accessibility/state guidance.
- `wondelai/skills`: iOS HIG modal/safe-area/touch-target guidance and Refactoring UI hierarchy/depth guidance.
- `Bambale0/dev-agents-pack`: frontend and behavior-focused test instructions.
- `agentskills/agentskills` and `anthropics/skills`: catalogs inspected; no more specific production Mini App workflow was applicable.

## Verification result

- RED: the new reference-path browser test failed against the text-only overview and missing modal.
- GREEN: the complete workflow spec passes in Chromium (`32 passed`), including legacy one-step isolation, payment/idempotency, retry, owner-media and local/external workflow-cover paths.
- The visual paths pass in Chromium (`4 passed`) and mobile WebKit (`4 passed`): locked/unlocked states, background unlock, equal 4:5 cards, centered chip, dimming and no overflow at 320/375/390/430/768 px. Modal focus entry/loop, Cancel, Escape, backdrop, focus restoration and Step 1 navigation are asserted.
- Production static build succeeds for all 24 Mini App routes with TypeScript checking enabled.
- `git diff --check` passes. No API, persistence, provider, pricing or runtime-setting files changed.
- Independent Standards and Spec review found background-unlock/focus-restoration and missing Escape/backdrop/layout coverage. Both findings were fixed and the expanded Chromium/WebKit paths pass.
- GitHub review found cold thumbnail `202` recovery, Telegram-provided content safe-area, duplicate-trigger dialog semantics, signed owned-media URL safety, and external image covers misclassified by the workflow output media type. The cards cache-bust only the owned thumbnail endpoint before falling back, never mutate signed media query parameters, prefer the created workflow thumbnail, exclude only explicit video extensions from image-card fallback, and preserve extensionless external image covers, the modal consumes synchronized `--tg-safe-*` insets, both triggers expose the same dialog relationship, and focused browser regressions pass.
- The user explicitly authorized a full release on 2026-10-27. Release gates are exact-head PR CI, protected merge, successful production deployment, exact merge-SHA verification in Git and running images/containers, public release metadata, health/readiness/operational checks, and a non-charging live verification of the two-step trend route/assets.
