# iPhone New Trend / Step 2 video preview — follow-up audit

## Baseline and user-visible evidence

- Remote main and local source baseline: `33e006149a05ae88d26b5b9c8ab2cf5f475cd5ff`, tree `3009c1f519a919d9b2c182fe71ba8341eb77e295`; refreshed on 2026-10-29. No subsequent main change was found.
- Previous media-lifecycle fix was delivered by [PR #572](https://github.com/Bambale0/ksu/pull/572) and test-only [PR #573](https://github.com/Bambale0/ksu/pull/573). [Deploy 40874337932](https://github.com/Bambale0/ksu/actions/runs/40874337932) verified this SHA, immutable service images and host-local health/release checks. That is not physical-iPhone verification.
- The user reports that “Новый тренд” still does not respond and clarifies that the button freezes. The supplied iPhone Telegram screenshot shows the trend manager, “Новый тренд” and “Обновить”, a literal `HTTP 502` alert, and “Трендов пока нет. Создайте первый.” There are no visible trend previews in this state. No screenshot or private Telegram data is committed.
- Whether the whole WebView or only the create action stops responding is not yet established. The screenshot alone does not identify the failed endpoint, request time, client release, or underlying gateway exception.

## Existing implementation and competing hypotheses

- `InlineTrendAdmin.beginCreate` synchronously creates a local draft, clears its error and sets `formOpen=true`. It has no request, loading guard or nonempty-model guard. Empty models alone do not prove failure to open the form.
- `trendAdminApi.list` joins `GET /api/v1/trends/manage` and `GET /api/v1/generations/models` with `Promise.all`. Either rejection discards the combined result. A non-JSON 502 is displayed as `HTTP 502`.
- Initial failure leaves items/models empty. The current manager also renders a confirmed-empty message after failed loading; creation then has no model choices until a successful list refresh.
- Existing global generation click guards do not match the New Trend button. Manager/form are sibling overlays at z-index 140/150 outside the main app subtree. No confirmed event-interception or stacking defect was found in the initial source audit.
- Existing failure coverage first populates models from a successful response and only taps New after another successful response. It does not exercise a cold HTML 502, failure of public model enrichment, or opening the form while the initial request is pending/failing.
- Hypotheses to distinguish: a cold-load render exception; late request state replacing an open form; public-catalog failure discarding otherwise valid managed data; actual gateway/service failure; client/version or physical WebView behavior absent from hosted WebKit. Do not label an adjacent error-state improvement as a proven fix for the reported freeze.

## Scope and acceptance criteria

1. Characterize the unchanged deployed frontend with a real touch activation under initial HTML 502 for each endpoint independently. Require visible editable form, close/reopen, no page errors, and no unintended writes. Also exercise an outstanding list request settling after the form opens.
2. Inspect current production/runtime evidence through supported read-only tooling, including request/client errors if accessible. Preserve access boundaries; do not read secrets, restart services or infer the public origin from another project.
3. Patch only a cause established by reproduction or runtime evidence. Preserve authorization, server model/recipe authority, billing and all existing media lifecycle regressions.
4. A failed load must not be presented as proof of an empty catalog. If data loading is changed, define recovery explicitly and preserve draft input during retry; do not invent fallback business models.
5. Obtain separate Standards and Spec reviews, relevant focused browser/API verification and all six exact-head/main CI gates for any delivered fix. Retain the prior authorized release process and verify actual production SHA before claiming delivery.

## Verification matrix and implementation plan

| Category | Initial decision |
| --- | --- |
| Unit/domain and DB integration | No change proposed until a concrete cause is found; use the relevant existing backend suites if the cause crosses this boundary. |
| Authorization and provider contracts | Preserve Telegram/admin checks and server-authoritative model lists; no real generation, charge or provider request for browser tests. |
| Migrations/configuration/admin settings | None proposed. Do not invent catalog defaults or change service settings based only on the screenshot. |
| Retry/idempotency/API | Mock only HTTP boundaries in browser diagnostics; distinguish managed-list and public-model failures, pending completion and recovery. |
| Frontend E2E | Touch Chromium and mobile WebKit against the exact baseline. Capture dialog/render/error evidence; preserve all five existing media/interaction cases. |
| Smoke/deployability | Existing exact-SHA gates and deploy workflow remain authoritative for a future release. Current local browser executables and Docker are unavailable; hosted diagnostics are required. |
| Observability | Inspect existing client-logs and request/runtime logs when accessible. Do not log private prompts/media, auth headers or credentials. |
| Performance | No resource/performance fix proposed without a reproduced invariant. |
| Rollback/recovery | Keep any confirmed fix narrow and reversible; no data migration is currently planned. |

Sequence: record this audit before changes; add diagnostic cases on the unchanged production code; inspect their outcomes together with production evidence; select the minimal confirmed fix or record the remaining reproduction/access gap; review and verify any fix before delivery. A passing characterization does not reproduce or resolve the physical-device complaint.

## Guidance refreshed

- KSU `AGENTS.md` blob `35fa07c0ed7812285fef0ad55328399b8f4a0f5d` is unchanged. Repository-local `.agents` remains absent; preserve the embedded Start-derived baseline, whose rules are unambiguous and unchanged.
- `Bambale0/.agents@e4a2e491647fb9d88a61e50f1f05f5059235f09f`: systematic-debugging, frontend-ux-audit.
- `Bambale0/skills@eca5310a73bf9fb6107bd9a587605945de31c562`: diagnosing-bugs, TDD/tests/mocking and separate code reviews.
- `Bambale0/claw@10e261e9e4ad0435795d738c47c3442623fbf0a1`: frontend-qa and release-hardening.
- `wondelai/skills@c172996495bed0fcd26896a9416b2093fd7073f0`: working-with-legacy-code and release-it/deployment-strategies.
- `Bambale0/dev-agents-pack@9ae0af4aff26179456037ea9bc15beb2c44662bf`: debugger/frontend and devops/release-manager.
- `anthropics/skills@ca45fc496a3436251f191354091d557da31c15b5`: webapp-testing.
- `agentskills/agentskills@69ef37e9424c0a7ea9dd2293b559e43ec8176379`: catalog inspected; no task-specific iPhone/media/deployment guidance.
- All source heads were refreshed remotely and remain unchanged. No external skill scripts were executed.

## Progress

- 2026-10-29: fresh source/screenshot audit recorded before implementation. Independent frontend trace agrees that 502 alone does not suppress the synchronous create action; cold-failure browser coverage and current production telemetry remain outstanding.
- Additional user evidence: two screenshots clarify “Когда шаг 2 видео” / “Не добавляется, не показывает” and show the iOS photo picker. This establishes a separate concrete video-preview requirement within the same trend-creation journey. The earlier HTTP 502 is still a distinct, unproven cause of any nonresponsive click.

## Clarified Step 2 video requirement, recorded before product edits

The original [step-preview specification](trend-step-previews-20261028.md) deliberately allowed only images for both workflow cards. The user's new evidence requires Step 2 to accept a video preview as well as an image. This is the controlling requirement for the follow-up; Step 1 continues to accept images.

Confirmed barriers on the deployed source:

1. Step 2's file input advertises only `image/*`, excluding videos from the native picker.
2. `uploadWorkflowStepPreview` rejects every non-image, including a video manually supplied to the input.
3. The editor renders Step 2's URL through `<img>`.
4. The customer workflow overview likewise sends Step 2's URL to `WorkflowStageImage`, which always renders `<img>` and eventually falls back from a video URL to a shared image.

Existing server contracts already support the requested preview: `/uploads/kie` accepts image/video media, workflow normalization accepts a safe HTTP(S) step `preview_url`, and public/owned step presentation preserves it. This preview remains display-only; it is not a video generation input, model parameter or replacement for the Step 1 result binding.

Implementation/acceptance plan:

1. Add failing browser cases on the unchanged deployed source: real touch/file chooser includes video for Step 2; a supported tiny clip decodes in the editor, survives save/edit; a configured Step 2 video renders and decodes on the customer card. Preserve Step 1 image behavior, locks and no-generation assertions. Keep the three cold-502 characterization cases separate in purpose.
2. Extend the existing Step 2 picker/type guard to image or video and update its labels. Render video URLs with media lifecycle cleanup; preserve legacy image previews and per-step draft ownership.
3. Extend the existing workflow-card media renderer to videos while retaining its image/thumbnail/error fallback and locked-step behavior. Reuse the visibility-aware media component where appropriate; do not reintroduce eager offscreen players.
4. Verify safe video URLs survive server normalization and public presentation without modifying generation/billing contracts. No schema, migration, provider routing or business configuration change is planned.
5. Require focused RED/GREEN evidence, independent Standards/Spec review, existing workflow/media regressions and all exact-head/main gates before the already authorized release process. Report physical-iPhone and HTTP-502 limits separately from the delivered video-preview behavior.
