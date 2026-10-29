# KSU iPhone Add Trend interaction incident — 2026-10-29

## Scope and baseline

- User report: on iPhone, the Add Trend button does not respond; the attached complaint also describes lost taps and scrolling in the web content while Telegram's native close/navigation still work.
- Exact main baseline: `0889745f77f5a09099006cbd5880500059e52745` (tree `abc7aa4f7121ca1ad10910bc0d5193e7cbeeb7e7`).
- Isolated branch: `fix/iphone-add-trend-20261029`.
- This investigation changes only the Mini App preview resource lifecycle, stable trend-manager preview geometry, and regression coverage. No pricing, provider routing, permissions, template recipes, API schemas, financial data, customer messages or paid generations.
- Diagnosis and a reviewable branch are authorized by the incident request. This record does not assert permission to merge/deploy this new incident patch.

## Evidence before changes

1. The outer `Управлять трендами` button synchronously calls `setOpen(true)`. It is a semantic button, rendered through a portal into the ready-scenarios section.
2. The open manager renders every managed trend. Every ordinary video preview immediately has a remote `src`, `autoPlay`, `loop` and `preload="metadata"`, regardless of clipping/scroll position.
3. Opening the editor leaves the entire management list and its media elements mounted behind the form. Actual playback depends on browser/WebView policy; merely seeing autoplay attributes does not establish that every video plays simultaneously on iOS.
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
- Baseline regression head `28290ab8fc4d8492cb8072db4f7aa2edbd4007a8`, draft PR #572: completed [Mini App run 40833892496](https://github.com/Bambale0/ksu/actions/runs/40833892496), job `123314081851`, proves two intended failures in both Chromium and mobile WebKit. The distant 300th card already has a video `src`; three manager video sources remain mounted under the create form instead of zero. Chromium: 916 passed / 3 failed; mobile WebKit: 239 passed / 3 failed; separate personalized-keyboard WebKit: 11 passed. The third failure is an initial test-fixture mistake: upload HTTP 503 is intentionally translated by the existing API layer to a safe service-unavailable message. Correct the test expectation, not application behavior. Five other baseline workflows passed.
- Local baseline and initial patch typechecks passed. A local static build compiled but its nested TypeScript CLI returned empty captured stdout in this runtime; no application build guard was bypassed. Hosted baseline CI and ROXY E2E successfully built the unchanged application.
- Independent review found a related inherited media-lifecycle gap: the reusable preview only removes `src` when a visited video leaves the viewport. The [HTML Standard](https://html.spec.whatwg.org/multipage/media.html#location-of-the-media-resource) specifies that removing this attribute does not invoke media-load/reset. To avoid accumulating visited resources, the shared component must own source assignment and explicit pause/remove-source/load cleanup in one effect. A single owner also prevents cleanup from deleting a replacement URL during a same-card refresh. This expands the patch to the existing shared media component, with no API/configuration change.
- Before that shared-component change, regression coverage was strengthened with real MP4 metadata, currentSrc/paused checks after scrolling and unmount, and same-card URL replacement. Native file-picker activation remains a real tap; programmatic scroll assertions do not certify a physical iPhone swipe or hardware memory-pressure recovery.
- Independent Standards review found no remaining source-lifecycle blocker after the single-owner effect. Separate Spec review identified a layout risk: intrinsic portrait media geometry could change row height when unloading/unmounting previews. The patch keeps the existing minimum-height card slot and absolutely fills it with media, so media metadata cannot change list geometry. The same regression now uses a generated 32x96 H.264 portrait fixture and empty descriptions; it checks first-card height after unloading, total list height, and scroll/preview geometry while the form is open as well as after return. The Spec reviewer agreed with this minimal geometry fix.
- Local final source typecheck and test syntax check passed. Independent Standards and Spec reviews of source head `c79d8e3ef5137646bbd3d077eb0bd104fcbaa0fd` found no remaining P0-P2 findings. Both media-lifecycle and portrait-layout review findings are resolved. Full baseline-to-head whitespace review found one trailing blank line in this audit, removed by the documentation follow-up.
- Live diagnostics yielded no completed production telemetry; no production host/container/release/count or affected-device error is claimed from those calls. No permission policy was altered or bypassed.
- Implementation and independent review are complete. Completion/release remain gated on the exact final-head CI, whose final run URLs and results are maintained in [PR #572](https://github.com/Bambale0/ksu/pull/572). The physical-device cause and production rollout remain unverified; neither is inferred from browser regression success.
- Runtime follow-up on `953393df7aec0ffce0003f0c7c10e7bafdcfd231`: five workflows passed (including 2126 backend/product tests and seven ROXY E2E journeys), but [Mini App run 40835715521](https://github.com/Bambale0/ksu/actions/runs/40835715521) finished with Chromium 918 passed / 2 failed and mobile WebKit 241 passed / 2 failed. Only the two new media-state journeys failed: Chromium saw zero H.264 dimensions; WebKit decoded the video and replaced its URL successfully, but retained the old currentSrc string after offscreen/unmount cleanup while paused. The three other new interaction journeys passed in both engines. A separate diagnostic-only branch reproduced the same four failures in [run 40837065586](https://github.com/Bambale0/ksu/actions/runs/40837065586); it does not replace required PR gates. Further diagnostics must distinguish actual media-state retention from a stale URL field before changing production cleanup or its regression oracle.
- [Diagnostic run 40837740912](https://github.com/Bambale0/ksu/actions/runs/40837740912), source/test head `b1b5f763c487dbe23dec4514bd0c44c611932955`, established both fixture/oracle issues. Bundled Chromium reports no support for the fixture's `avc1.42C00A` codec and supports VP8; WebKit supports both. Use equivalent 32x96 portrait VP8/WebM for Chromium and H.264/MP4 for WebKit, with matching URLs, MIME and byte ranges. Correct the synthetic PNG IDAT CRC and require actual `naturalWidth > 0` after upload.
- In the same diagnostic, both browsers successfully decoded the chosen video and, after offscreen cleanup and unmount, reported `src=null`, `paused=true`, `readyState=0`, `networkState=0`, empty buffered ranges, zero video dimensions and `error=null`; only the historical `currentSrc` string remained. [Playwright v1.56.1 pins WebKit revision db897909](https://github.com/microsoft/playwright/blob/v1.56.1/browser_patches/webkit/UPSTREAM_CONFIG.sh). That revision's [load/reset implementation](https://github.com/WebKit/WebKit/blob/db897909f7c31d9b38793374c66427b6a4cb3dd3/Source/WebCore/html/HTMLMediaElement.cpp) replaces the player and returns from the no-source branch without clearing `m_currentSrc`, consistent with the [HTML resource selection algorithm](https://html.spec.whatwg.org/multipage/media.html#concept-media-load-algorithm). Replace the incorrect empty-URL oracle with the complete observed reset state, including connection state, while preserving positive metadata, URL replacement, offscreen request bounds and geometry assertions. Keep `currentSrc` in failure diagnostics. This proves reset at the DOM/player API seam, not instantaneous release of all GPU/OS memory. Production implementation remains unchanged.
- Independent Standards/Spec review of refined test blob `e61d851f7b12799765399c1e3e29fee4d91af949` passed: the reset assertion atomically requires all observed empty-player fields and the correct connection state, retains loaded-media preconditions and replacement-URL checks, and rethrows diagnostic failures. The production components remain byte-identical to `953393df7aec0ffce0003f0c7c10e7bafdcfd231`. Focused browser verification precedes the final six exact-head PR gates.
- Focused GREEN: [diagnostic run 40838160519](https://github.com/Bambale0/ksu/actions/runs/40838160519), head `a0580426b75e4f089ce4462b4c482fa14caf4b9c`, completed with all ten cases passing (five Chromium, five mobile WebKit; 41.1 seconds). This covers the complete 300-card journey through editing and return, source replacement/unmount, create/upload/close, pending/failed loading, and same-file upload retry. The reviewed test blob and equivalent portrait fixtures are promoted to PR #572; the diagnostic workflow stays on its separate branch. Final required workflow results are recorded in the PR for its exact delivery head.
