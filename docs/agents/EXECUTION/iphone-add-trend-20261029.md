# KSU iPhone Add Trend interaction incident — 2026-10-29

## Scope and baseline

- User report: on iPhone, the Add Trend button does not respond; the attached complaint also describes lost taps and scrolling in the web content while Telegram's native close/navigation still work.
- Exact main baseline: `0889745f77f5a09099006cbd5880500059e52745` (tree `abc7aa4f7121ca1ad10910bc0d5193e7cbeeb7e7`).
- Isolated branch: `fix/iphone-add-trend-20261029`.
- This investigation changes only the Mini App trend manager's media resource lifecycle and its regression coverage. No pricing, provider routing, permissions, template recipes, API schemas, financial data, customer messages or paid generations.
- Diagnosis and a reviewable branch are authorized by the incident request. This record does not assert permission to merge/deploy this new incident patch.

## Evidence before changes

1. The outer `Управлять трендами` button synchronously calls `setOpen(true)`. It is a semantic button, rendered through a portal into the ready-scenarios section.
2. The open manager renders every managed trend. Every ordinary video preview immediately has a remote `src`, `autoPlay`, `loop` and `preload="metadata"`, regardless of clipping/scroll position.
3. Opening the editor leaves the entire management list and its playing videos mounted behind the form.
4. Public trend surfaces already use `TrendPreviewMedia`, which observes visibility and attaches video URLs only near the viewport. This is an existing reusable seam.
5. The manager and form are Page-level siblings, not descendants of the transformed main application shell. No unconditional touch-cancel handler was found in the direct button path.
6. A delayed synthetic click in the category handoff is a separate fragile path; it does not explain the ordinary outer Add button by itself.
7. A real iPhone freeze is not yet reproduced. Eager offscreen media activation is a confirmed code defect; its causal contribution to this particular device incident remains a hypothesis until runtime/device evidence is available.

## Competing hypotheses

- Most supported by code: mass video initialization and playback overload the mobile web content process when the manager opens, and remain active while editing.
- Alternative: modal sizing/focus/scroll geometry after the keyboard or file picker. Verify actual tap/open/close/reopen behavior in mobile WebKit; do not add speculative CSS fixes.
- Edge case: collection handoff timing or a stale detached portal mount. Preserve existing behavior and investigate only if a regression journey identifies this path.

## Existing / partial / missing / reuse

- Exists: authenticated admin APIs, ordinary and two-step editors, upload lifecycle guards, browser mocks, client error telemetry and a visibility-aware preview component.
- Partial: preview lifecycle is bounded on public surfaces but bypassed by this admin surface.
- Missing: a realistic large-video-catalog regression and explicit suspension of manager media while the editor covers it.
- Reuse: `TrendPreviewMedia`, existing manager/dialog semantics, current API fixtures and Playwright Chromium/mobile WebKit CI.
- No prefactor, new dependency, schema migration or server query is required.

## Acceptance criteria and plan

1. Add a browser regression using actual touch activation and a large synthetic video catalog. Baseline must fail the offscreen-media invariant; do not manufacture or claim a physical-device crash.
2. Opening the manager must not activate every video source or request offscreen media.
3. Creating/editing a trend must leave the form, upload, close and reopen interactions usable. Covered manager previews must not keep loading/playing.
4. Scrolling to a distant trend must still expose and edit that exact trend; closing/reopening should retain normal navigation behavior.
5. Pending/failed loading and failed upload must show existing errors without trapping the user.
6. Apply the smallest change at the admin media seam, then run typecheck/build, focused browser cases in Chromium and WebKit, existing adjacent editor/preview cases, independent review and exact-head CI.
7. Record results and limits below as they occur. No broad redesign or unrelated performance rewrite.

## Verification matrix

| Category | Decision |
| --- | --- |
| Unit/domain | No business/domain change; behavior covered at browser seam. |
| DB/repository integration | N/A: no data or backend implementation change. |
| Authorization | Existing admin guard/API unchanged; preserve non-admin absence in regression where relevant. |
| Migrations | N/A: no schema change. |
| Provider/external contract | N/A: no provider call or payload change; video requests mocked in tests. |
| Idempotency/retry/reconciliation | Existing upload/save contracts unchanged; exercise retry/close behavior without real writes. |
| API integration | Mock only HTTP boundaries; assert existing upload and manager interactions. Existing backend CI remains required. |
| Frontend E2E | New large-catalog touch/media lifecycle regression plus existing admin editor suites, Chromium and mobile WebKit. |
| Smoke/deployability | Typecheck/static export and exact-head CI. Production claims require a separately proven deploy SHA. |
| Observability/audit | Preserve client-error reporting; collect page errors and request evidence in tests, no private media/prompts logged. |
| No-hardcode/admin | No business configuration or new catalog limits. Visibility comes from browser geometry, not a hardcoded number of trends. |
| Performance | Assert offscreen media remain inactive, and manager media are suspended beneath the editor. |
| Rollback/recovery | Revert the frontend commit; persisted recipes/media remain unchanged and compatible. |

## Guidance inspected

- Local versioned `AGENTS.md`, README, CONTEXT, current frontend components/tests/workflows. Repository-local `.agents` is absent in the inspected tree and existing checkout.
- `Bambale0/.agents@e4a2e491647fb9d88a61e50f1f05f5059235f09f`: AGENTS, README, SKILLS_INDEX; systematic-debugging and frontend-ux-audit (Safari/WebView, tap, modal scroll, file picker, reopen).
- `Bambale0/skills@eca5310a73bf9fb6107bd9a587605945de31c562`: diagnosing-bugs, tdd plus tests/mocking, code-review (public behavior, red/green, separate Standards/Spec).
- `Bambale0/claw@10e261e9e4ad0435795d738c47c3442623fbf0a1`: frontend-qa (working interactions and failure states).
- `wondelai/skills@c172996495bed0fcd26896a9416b2093fd7073f0`: working-with-legacy-code (characterize the narrow seam).
- `Bambale0/dev-agents-pack@9ae0af4aff26179456037ea9bc15beb2c44662bf`: debugger and frontend instructions (evidence and minimal fix).
- `anthropics/skills@ca45fc496a3436251f191354091d557da31c15b5`: webapp-testing (inspect rendered DOM, capture actual outcomes).
- `agentskills/agentskills@69ef37e9424c0a7ea9dd2293b559e43ec8176379`: README/catalog; no task-specific iPhone/media guidance.
- All mandatory remote guidance sources were accessible. Start-derived baseline is unchanged and unambiguous. No external skill scripts executed.

## Progress

- 2026-10-29: audit recorded before production-code changes. Current code and independent review agree on eager all-video activation; physical iPhone causality remains unproven.
- Local source snapshot is hash-verified against the exact remote commit. The normal local Git HTTPS proxy is unavailable; connector retrieval was used without altering network policy.
- Local browser executables are absent. Browser regressions will use the repository's existing isolated Playwright CI unless a permitted existing local runtime is found. This is not a passing-test claim.

