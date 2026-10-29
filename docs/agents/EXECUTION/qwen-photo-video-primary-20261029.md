# Neironych Qwen primary for photo/video prompt analysis — 2026-10-29

## Request, baseline and scope

The user asks KSU/ROXY to use Neironych as primary for photo and video prompt analysis with `qwen3.8-max`. The clarified scope is the two customer tools `image_analysis` and `video_prompt`. The source video continues to be analyzed through chronological frames unless Neironych's own native-video contract is positively verified. Text `prompt_builder`, its legacy image-reference API, Pinterest, generation models, prices and already accepted jobs keep their existing contracts.

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
- Existing KSU PR #542 records `POST /v1/chat/completions`, HTTPS image blocks and four chronological JPEG data-URI frames, plus a historical public catalog check. Current direct guide/catalog requests from this executor were unavailable; do not treat historical observations as a fresh live test.
- The provider implementation is available separately in `Bambale0/ooo`; inspect its current chat route/registry/ledger to distinguish definite non-acceptance from uncertain completion. A transmitted `Idempotency-Key` alone does not establish supplier replay safety.
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
2. Add behavior-first regressions demonstrating that unchanged main/PR #542 do not admit Qwen-primary media tasks.
3. Reuse the Qwen adapter and implement typed runtime policy, actual snapshot dispatch and narrowly proven safe failure handling.
4. Add runtime admin control and authorization/revision tests; preserve existing UI and task contracts.
5. Run focused RED/GREEN verification in isolated CI, resolve independent Standards/Spec findings, then all exact-head checks.
6. Complete provider smoke within authorized access, publish through normal merge/deploy gates and record exact release evidence or the remaining blocker.

## Guidance

Remote task-specific guidance refreshed from `Bambale0/skills` (implement/TDD/code review), `Bambale0/claw` (backend/release review), `wondelai/skills` (Release It integration stability), `Bambale0/dev-agents-pack` (backend/API/release review), `agentskills/agentskills` (catalog/progressive disclosure; no KSU-specific provider implementation), `anthropics/skills` (webapp testing). `Bambale0/.agents` provides applicable API integration, observability and tests guidance. Embedded Start baseline is unchanged and unambiguous. No skill scripts were executed.

Initial independent source audit and architecture review passed with the explicit provider-contract gate. Exact implementation review, CI and production verification are still pending.
