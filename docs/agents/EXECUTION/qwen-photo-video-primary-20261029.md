# Neironych Qwen primary for photo/video prompt analysis — 2026-10-29

## Request, baseline and scope

The user asks KSU/ROXY to use Neironych as primary for photo and video prompt analysis with `qwen3.8-max`. The clarified scope is the two customer tools `image_analysis` and `video_prompt`. The source video is analyzed through chronological frames without audio: the deployed Neironych contract explicitly rejects native-video blocks. Text `prompt_builder`, its legacy image-reference API, Pinterest, generation models, prices and already accepted jobs keep their existing contracts.

Remote main and deployed baseline: `e39b6485960d068365e4091fa30614201dbaa684`, tree `77fadc9657a7960d8dcd13eee295da70189b8bcf`. AGENTS blob `35fa07c0ed7812285fef0ad55328399b8f4a0f5d`. The local checkout contains the completed #574 work and must not be reset or cleaned. The new product tree is based on current remote main. There are no repository-local `.agents` instructions/index files.

Overlapping work: [PR #542](https://github.com/Bambale0/ksu/pull/542), branch `fix/ksu-video-prompt-nexus-503-fallback-20261010`, head `49a3af3d332f5a061e17f473ee407083b681c82c`. Its adapter and useful tests can be reused; its Nexus-primary admission, environment-only fallback flag and unverified replay assumptions do not satisfy this request. Preserve its history and update its scope instead of publishing a competing implementation.

## Fresh audit

1. **Exists:** `PromptToolService` validates input, atomically persists task/outbox and one wallet debit, derives task identity from user/idempotency key, and publishes owner-scoped status. Processor dispatches the saved provider. Completion/refund are fenced by outbox attempts and transactional notifications are retained.
2. **Partial:** saved model is metadata rather than an adapter argument; Nexus/Kie clients use their own constants. Existing media tasks use a 90-second general lease despite longer media/provider work. PR #542 adds a Qwen adapter, 600-second media leases and fenced fallback persistence, but pinned primary dispatch still needs a current-claim check.
3. **Missing:** Qwen-primary admission/catalog, an audited runtime selection for these tools, verified provider-side chat idempotency/error classification, and current real photo/video provider proof.
4. **Reuse:** `AdminRuntimeSetting`, `AdminRuntimeService`, fresh step-up dependency, confirmation and command ledger; provider HTTP and parser conventions; safe bounded video downloader, ffprobe and JPEG extraction; public DTOs, wallet and notification seams.
5. **Prefactor:** add a small prompt-tool policy module independent of generation routing; keep adapter HTTP payloads out of the application service. Do not change the shared `NEXUS_VISION_MODEL` used by Pinterest and prompt building.
6. **Risks:** two provider charges after an ambiguous timeout, concurrent stale worker submissions, changing an accepted model on retries, copying unverified native-video fields, leaking media/auth into logs, stale admin writes and inaccurate catalog metadata.
7. **Integration/schema:** reuse configured Neironych partner key and origin. No new key, database table, migration, pricing change, unrelated environment edit or production SQL. Provider model IDs remain closed to verified vision contracts.
8. **Test seams:** task admission/catalog and real PostgreSQL wallet/outbox; provider `httpx.MockTransport`; real JPEG/video extraction; authenticated admin endpoint and browser UI; existing full CI/E2E; deployed release markers and bounded synthetic media smoke.
9. **Configuration:** separate versioned `prompt_tool_provider_routes` runtime policy with validated provider/model choices. Default new photo/video work uses Neironych/Qwen; an authenticated admin can change future admission without a redeploy. Existing task snapshots remain authoritative.
10. **Observability:** task ID, tool, configured revision, actual provider/model, attempt, failure category and duration. No raw media, model responses, authorization headers or personal identifiers in new logs. Keep existing structured request context.
11. **Rollout/rollback:** review/test the exact PR head, merge through existing gates, verify all six main workflows and exact production image/release markers. Runtime policy rollback affects new tasks; accepted jobs stay on their saved supplier. Do not declare live vision verified from mock tests or an accessible catalog.

## External contract evidence and limitations

- QwenCloud's [model update notice](https://docs.qwencloud.com/changelog/model-updates/qwen3.8-max-upgrade) confirms `qwen3.8-max` and its September snapshot mapping. This is upstream model evidence, not evidence of Neironych's deployed transport or billing behavior.
- Existing KSU PR #542 supplies reusable prompt/parser and frame-mode concepts. Independently read provider source at `Bambale0/ooo@f87409831f5e006b66096ba3df29836f6bf10507`: chat admission, registry, partner-scoped unique idempotency reservation, body fingerprint, response replay and receipt validation. Its contract rejects native-video blocks before reservation. Completed exact-body/key requests replay the stored response; expired replay results fail terminally without a new provider operation.
- Provider [deployment 40767557213](https://github.com/Bambale0/ooo/actions/runs/40767557213), job `123095679419`, completed its actual deploy step and logged `DEPLOY_VERIFIED f87409831f5e006b66096ba3df29836f6bf10507` at `2026-10-28T20:57:23.5040559Z`. This source/deployment evidence supports replay handling, but does not replace a current multimodal inference check.
- Fresh free GET preflight from the existing KSU application container completed at `2026-10-29T15:36:57Z`: `/v1/models`, `/api/v1/catalog/pricing` and authenticated `/v1/balance` all returned 200; `qwen3.8-max` is available and the configured partner account has funds. No secret, customer media, paid inference or customer-wallet mutation was involved. Direct requests from the local executor remained unavailable; the authorized existing server integration supplied this evidence.
- Real inference completed at `2026-10-29T15:50:10Z` using the exact reviewed adapter (`SHA256 06dcb9b09ac36b10ff79e534850dd95f93885f8d369f2ca53a4b2037002a996c`) through the existing configured account. A synthetic 128px PNG and four real JPEG frames from a six-second synthetic MP4 both returned HTTP 200 with `model=qwen3.8-max`, valid RU/EN results and the expected visible colors. Video audio notes were empty. Each exact-body/key replay returned identical response bytes and the same provider generation, attempt, charge and ledger entry: two operations, four POSTs, two charges totaling **2.53 RUB** (photo 0.84, video 1.69). Per-generation settlement/trace supplied the financial evidence; aggregate balance delta was only contextual.
- Live smoke limitations: the photo URL itself encodes its color, so its check proves transport/schema and basic color consistency, not broad vision quality. Video replaced only the isolated candidate module's byte loader with locally generated bytes; ffprobe, JPEG extraction, payload, HTTP and parsing were real. This probe did not create KSU customer tasks or touch customer wallets/notifications. The worker, media-ingestion and application journeys are covered separately by CI. Read-only runtime inspection also confirmed no stored `prompt_tool_provider_routes` override before release.
- Generic gateway 502/503/504, malformed output and transport timeouts do not independently prove that a paid request was not accepted. They must not cause a new alternate-provider POST. If replay cannot be proven safe, persist the submission boundary and fail/reconcile without a second paid submission.
- Local backend dependencies are unavailable and package installation failed at the configured network boundary. Use the existing isolated GitHub CI PostgreSQL/Redis runtime; do not run tests against production.

## Acceptance criteria

1. New `image_analysis` and `video_prompt` tasks and catalog entries select Neironych `qwen3.8-max` under the default policy.
2. Policy is server-owned, validated, revisioned, auditable and editable in the existing runtime admin. Permission, step-up, confirmation, idempotency and stale-write protection are preserved.
3. Photo input and bounded chronological video frames reach the documented provider endpoint with the saved model; results retain the current RU/EN and media-specific schemas.
4. Text building, Pinterest, generation routing, tariffs and accepted Nexus/Kie jobs are unchanged. Idempotent request replays retain the original task/provider even after a policy change.
5. A stale claim cannot submit. Before a potentially paid request, saved provider/model and submission identity are authoritative. Ambiguous outcomes never cross providers or silently create a new paid attempt.
6. Safe configured fallback, if supported, is limited to verified non-acceptance/pre-submission conditions and is persisted under the current fence before calling its provider.
7. One customer debit, one terminal refund when appropriate and one successful result notification survive retry/reclaim. No raw secret/media data is added to logs or public DTOs.
8. Exact PR/main CI, separate Standards and Spec reviews and real deployment/media evidence are recorded honestly; incomplete external verification remains a release limitation.

## Verification matrix

| Category | Required verification |
| --- | --- |
| Unit/domain | route/model validation, default selection, error classification and response schema |
| Database/integration | admission snapshot, replay after policy change, atomic debit/refund, fenced reclaim and provider transition |
| Authorization | runtime permission, fresh step-up, confirmation, owner-only task access, rejected client provider selection |
| Migrations | N/A: reuse task JSON and existing runtime setting/command tables; ORM parity still required |
| Provider contract | exact model/endpoint/auth/media envelope, finite timeouts, no unsafe automatic replay, real media extraction |
| Idempotency/retry | stable task identity, fenced dispatch, unknown outcome handling, single refund and notification |
| API | photo/video admission/catalog/public DTO and admin policy lifecycle |
| UI/E2E | runtime route control and existing photo/video result/poll/reopen/copy journeys |
| Smoke/deployability | all exact-head/main gates, exact deployed revision and bounded synthetic photo/video provider proof |
| Observability | task/provider/model/revision/attempt/duration without secret or media payloads |
| No hardcode | typed DB runtime policy, closed supported model choices, future-task rollback without source changes |
| Performance | finite whole-operation deadline, bounded video bytes/duration/frames and response bytes; no per-task unbounded queries |
| Recovery | old supplier dispatch, frozen accepted route, no alternate spend after unknown completion |

## Implementation plan and progress

1. Record fresh audit and complete independent contract/guidance review. **Recorded before production edits.**
2. **RED verified:** isolated [run 40902036431](https://github.com/Bambale0/ksu/actions/runs/40902036431), exact diagnostic head `eca734ff0d21edbae844c3be3368bb25f07ee190`, used unchanged main product code. Three media admission/catalog regressions failed on Nexus/GPT selection; two text-builder guards passed. Dependency setup, migrations and test collection succeeded.
3. **Implemented:** typed runtime policy, frozen task routes/model/revision, private exact Qwen request snapshots before POST, same-key/body recovery and strictly limited fallback. Managed Nexus submissions have one-attempt durable markers; legacy jobs retain their existing dispatch.
4. **Implemented:** existing runtime admin permission/confirmation/step-up/idempotency/revision contracts; focused DB/API and browser tests. Video UI explains key-frame analysis without audio. The adapter clears unsupported audio observations even if the supplier invents them.
5. **Focused GREEN and source review complete:** [run 40904195426](https://github.com/Bambale0/ksu/actions/runs/40904195426), exact diagnostic head `c8a05bc7e315a8a29c00ff6e0b348e616e68c909`, passed **182 tests in 16.54 seconds**, plus Ruff, compile, migrations and ORM parity. This includes 22 managed-task cases, six existing lifecycle cases, adapter/media, runtime policy/admin and prior prompt contracts. The preceding implementation run stopped at one Ruff membership-style error, corrected before this successful runtime run. Independent Standards/Spec review has no open P0–P2. Four findings were fixed and reread: local protection failures retry on the same route, completion retains a current fence through commit, production logging keeps safe outcome fields, and HTTP410 is terminal before body processing. Local syntax/whitespace and Mini App typecheck also pass.
6. **Real provider smoke passed:** exact candidate photo/video calls and same-key replay were verified through partner-scoped generation/trace GETs. Normal merge/deploy remains gated by all six checks on the final PR SHA and resulting main SHA; record final workflow and production evidence in the PR/release report without claiming a deployment from source review alone.

## Guidance

Remote task-specific guidance refreshed from `Bambale0/skills` (implement/TDD/code review), `Bambale0/claw` (backend/release review), `wondelai/skills` (Release It integration stability), `Bambale0/dev-agents-pack` (backend/API/release review), `agentskills/agentskills` (catalog/progressive disclosure; no KSU-specific provider implementation), `anthropics/skills` (webapp testing). `Bambale0/.agents` provides applicable API integration, observability and tests guidance. Embedded Start baseline is unchanged and unambiguous. No skill scripts were executed.

The diagnostic workflow exists only on the diagnostic branch and is excluded from the 22-file product PR. On product head `bfe25b05f8ad2ed4ee758fa7053f7918426df275`, full backend CI passed **2237 tests**, ROXY E2E passed seven journeys, and Admin Console, Batch Generation and ROXY Release Gate passed. The subsequent Mini App run exposed two test-fixture selector failures: Playwright includes option text in the wrapping label of a select, so an exact short label did not match. Isolated [run 40906597318](https://github.com/Bambale0/ksu/actions/runs/40906597318) confirmed both original failures at that locator, then passed **both corrected cases in 3.3 seconds** using explicit field names plus separate visible-label assertions. All route/model/revision/idempotency/MFA/cancel/stale-write assertions remain. Product code and the live-tested adapter are unchanged by this fixture correction.

All six gates must still pass on the final PR SHA and resulting main SHA, followed by actual KSU deployment verification; no production-primary switch is claimed from this pre-release document. Runtime rollback must retain a compatible worker for already accepted Qwen tasks; reverting to the old worker image is not a substitute for changing future admission policy.

## Release-gate follow-up: existing WebKit preview recovery

The full gate on `4aea7046c6facd68dbcbac63f581832afcfc9c31` passed all five other workflows and **928 Chromium tests**, including both admin-route cases and all four photo/video tool cases. Its WebKit audit passed 248 cases but failed `broken step previews fall back to the workflow thumbnail`; the first image retained its failed step URL instead of the workflow thumbnail. Eleven keyboard cases passed; the later upload-deadline step did not run. This is a real failed release gate, not permission to merge after a partial browser pass.

Fresh audit before any corrective product edit:

- **Existing:** `WorkflowStagePreview` in `app/trend/page.tsx` has an ordered source list, image/video error handling, three bounded thumbnail retries and timer cleanup. It also resets state in a passive effect keyed by the source list. The failing image is an ordinary eager image, so lazy/offscreen loading is not an evidenced explanation.
- **Baseline:** the page and test are unchanged from deployed main `e39b648`: blobs `f86156a5b538f0ec812676ba838a383f36b7a730` and `e52e2c65e6550ff7b10e99ec9f70a0fee0eb431d`. The Qwen change does not itself explain the failure.
- **Uncertain:** a fast image error may advance the source before the passive reset overwrites it. Establish request/error/reset/render ordering in an isolated WebKit diagnostic; do not call it a random failure or weaken the fallback assertions without evidence.
- **Reuse/scope:** retain the existing source ordering, bounded retry policy, signed-URL behavior, video component and functional test. If lifecycle evidence requires a fix, confine it to preview state ownership and its regressions; no provider, billing, API/schema, styling or new feature changes.
- **Verification/acceptance:** failed step images recover to a decoded workflow thumbnail even when failure is immediate; a genuinely changed source set gets fresh state; obsolete timers/events cannot damage the replacement. Preserve valid video previews and user interactions. Then pass focused WebKit verification, independent review and all six exact final PR/main gates before normal deployment.
- **Diagnostic isolation:** event instrumentation belongs only to the diagnostic branch and must not enter the product tree. No production test suite, customer task or provider inference is needed for this investigation.


### Bounded original-test follow-up

Instrumented diagnostic run 40909994845 at f6ea85be9e316b6c902f8c191a2855865d5dc898 passed all 12 WebKit repeats. All 24 image instances recorded reset before native error and React error, then fallback source index 1 and decoded 24x32 thumbnail. The suspected reset-after-error race was not reproduced; no preview production fix is justified by this evidence. Instrumentation and single-worker isolation can affect timing.

The next diagnostic restores the exact product tree c11a15f9b96d456c139bd8c8a60fb4225c7292f0: original page blob f86156a5b538f0ec812676ba838a383f36b7a730 and test blob e52e2c65e6550ff7b10e99ec9f70a0fee0eb431d. Only this audit and the diagnostic workflow differ. The unchanged target runs 30 times in WebKit 1.56.1 with two workers and --retries=0. Any failure stops the release sequence for investigation. If all pass, allow one controlled full Mini App workflow rerun on unchanged PR head 4aea7046c6facd68dbcbac63f581832afcfc9c31, followed by all mandatory exact merged-main gates. This does not establish a root cause or claim the original failure is fixed.
