# Separate workflow step previews — 2026-10-28

## Baseline and scope

- Baseline: `origin/main` at `b2f05a36fd2b2067c4312bd7f5d94b5e8bd93b03`.
- User outcome: an administrator can upload an image for the Step 1 card and an image or video for the Step 2 card of a `sequential_photo_video` trend. The Step 2 video requirement was clarified by the user on 2026-10-29; its implementation and release evidence are tracked in the [follow-up audit](iphone-new-trend-502-20261029.md).
- Reuse: the existing permanent upload endpoint, v2 recipe snapshot, public step presentation and two-card workflow overview.
- Excluded: provider payloads, prompts, pricing, billing, step execution, generated media, permissions and legacy v1 trends.

## Contract

1. Each v2 workflow step may carry an optional HTTP(S) `preview_url`.
2. The admin editor accepts images for Step 1 and images or videos for Step 2, and persists each uploaded URL on its matching step. Step 2 videos render as inline video in the editor and the customer overview; existing image previews remain supported.
3. The public trend and owner workflow DTO expose the safe step preview without exposing prompts or provider parameters.
4. Before Step 1 completes, each overview card prefers its own step preview. A ready owned Step 1 result still replaces the Step 1 preview.
5. Existing workflows without step previews keep the workflow-level thumbnail/preview fallback.
6. Unsafe URL schemes are rejected at server normalization. Step previews are display-only and never enter provider parameters or replace the Step 1 result binding. Unavailable Step 2 video preserves the existing image/thumbnail fallback and step-lock behavior.

## Verification matrix

| Area | Evidence |
| --- | --- |
| Domain/API | RED/GREEN normalization and public-presentation tests for two safe URLs and unsafe URL rejection. |
| Admin UI | Playwright uploads two files and asserts the write payload stores distinct step URLs. |
| Customer UI | Playwright asserts Step 1 and Step 2 cards render their separate configured images. |
| Compatibility | Full workflow/admin Chromium specs cover v1 isolation, editing, duplication, lock/unlock, recovery and payment consent. |
| Mobile | Focused WebKit tests use an ASCII artifact directory to avoid the Windows/OneDrive video-artifact path defect. |
| Build | Next static production build with TypeScript checking. |
| Database/migration | N/A; fields live in the existing versioned JSON recipe and immutable run snapshot. |
| Provider/billing | N/A; execution parameters and pricing are unchanged. |
| Rollback | Revert the step field/UI changes; old workflow-level preview fallback remains compatible. |

## Initial verification (2026-10-28)

- Backend focused: `3 passed`; adjacent workflow/personalization suite: `42 passed`, plus the temp-path case `1 passed`.
- Chromium: full `trend-admin-v2` + `trend-workflow` suites, `39 passed`.
- Mobile WebKit: focused admin upload and customer-card paths, `2 passed`.
- Next.js production build: 24 static routes built and TypeScript passed.
- No paid generation, production data mutation, merge or deployment was performed.

## Guidance

- Repository `.agents` was absent; local TDD and verification fallback guidance was applied.
- `Bambale0/skills` and `Bambale0/claw`: no more specific current GitHub search result for this bounded feature.
- `wondelai/skills`: clean-code/TDD guidance for behavior-first tests and small readable changes.
- `Bambale0/dev-agents-pack`: frontend state/accessibility and behavior-focused deterministic tests.
- `agentskills/agentskills`: skill format/catalog only; no product-specific guidance.
- `anthropics/skills`: webapp-testing guidance for rendered browser verification.
- `Bambale0/start`: no more specific current guidance; the Start-derived repository baseline remains unchanged.
