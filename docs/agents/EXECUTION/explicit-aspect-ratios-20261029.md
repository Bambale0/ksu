# Explicit aspect ratios and Neironych primaries — 2026-10-29

## Audit and authorized scope
Baseline main/running release: `e39b6485960d068365e4091fa30614201dbaa684`.
Baseline tree: `77fadc9657a7960d8dcd13eee295da70189b8bcf`.
The user requested removal of aspect-ratio Auto and Neironych primary everywhere it is already integrated; previous merge/deploy authorization remains active.

Four real Lite jobs had a Neironych-first route, then skipped it for unsupported Auto or reference counts. Runtime revision 7 already corrected the Lite account override. This change addresses new admission and visible controls, then reorders the remaining supported runtime overrides. It does not add a provider for unsupported models.

## Existing / partial / missing
Existing: model catalogs and public schemas, normal/batch admission, immutable route/body/idempotency snapshots, template structural preflight, trends/workflows, action contexts, Pinterest and AI Reference, quote guards, admin routing control plane and exact-SHA CI/deploy.
Partial: explicit ratio selectors already exist in ordinary trends but automatic defaults are restored in normal forms and snapshots; special requests synthesize Auto.
Missing: one consistent public no-Auto boundary and safe user selection through each new-admission path.
Reuse the current schema and service seams. No architectural prefactor or new external dependency is required.

## Contracts and safety
Neironych Lite accepts 1K, 1:1 / 16:9 / 9:16 / 4:3 / 3:4 and up to 3 refs. Its absent ratio defaults to 1:1. Do not silently change Auto to square, drop refs, or relax the gateway validator based on a different upstream's broader contract.
This task concerns aspect_ratio Auto only. CSS/transport automation, audio_setting Auto, duration=-1/0 and legitimate source-driven adaptive/omitted ratio modes are not equivalent.
Legacy templates/action contexts remain readable. Already admitted generations keep their body, route, provider, external ID and stable key.
New invalid input must fail before financial debit/outbox/provider mutation with a useful Russian error. Parameter overrides remain narrow; hidden prompts/references are not exposed.

## Configuration, authorization and observability
Use existing AdminRuntimeService with an existing verified owner, runtime.manage, confirmation, revision fencing, idempotency and AdminCommand audit. No direct SQL writes, forged sessions or MFA state.
Move Neironych to the front only where it is already an allowed provider, both globally and in every existing account scope. Preserve each remaining provider's relative order and all unsupported routes.
Existing logs, request IDs, route revisions, provider attempts, audit records and API/worker health provide verification. Never print credentials or customer prompts.

## Acceptance criteria
1. Final public schemas and user-facing selectors contain no aspect_ratio Auto.
2. Stale Auto defaults ask for explicit selection; no silent square conversion.
3. Quote/create/batch/trend/workflow/repeat/special flows carry the chosen ratio consistently.
4. Invalid new Auto input fails before debit, outbox or provider POST.
5. Structural template reads and provider-required source-driven modes still work.
6. All already supported Neironych routes and account overrides start with Neironych after activation.
7. Other model settings, reference semantics, prices and existing jobs are preserved.
8. Exact-head CI, independent review, exact-main deploy and live readback/health pass.

## Implementation slices
1. Commit this audit and CONTEXT pointer.
2. Add failing regressions at public schema, runtime admission and stale-context boundaries.
3. Implement the smallest backend policy and explicit overrides for special flows; preserve template preflight.
4. Add schema-driven frontend selection/restoration and browser regressions; retain mobile accessibility.
5. Run relevant isolated checks, full existing CI and independent standards/spec review.
6. Merge the verified exact head, verify exact-main CI/deployment.
7. Apply one CAS/audited runtime route update and verify API+worker policy and health.

## Verification matrix
| Category | Planned evidence |
|---|---|
| Unit/domain | Final schema, explicit/stale ratio and request construction tests |
| DB/repository | Isolated quote/create/batch/context/trend integration tests |
| Authorization | Existing ownership/admin controls, narrow override DTO tests |
| Migration | N/A: no schema/data migration |
| Provider contract | Current documented ratios/refs and existing adapter tests; no paid calls |
| Idempotency/reconciliation | Existing frozen jobs and fallback contracts retained; config CAS/ledger readback |
| API | Schema, quote/run error and selected ratio propagation |
| Frontend/bot E2E | Create/reuse/special workflows with existing project seams; Chromium/mobile CI. Dormant text-generation handler is not registered and is N/A. |
| Smoke/deployability | Existing six CI gates, exact-main deployment and live readiness/operational health |
| Audit/observability | Runtime revision, actor/request/audit completion and saved route evidence |
| No-hardcode/admin | Routes remain validated runtime settings; controls reuse current model schema |
| Performance | No generation polling or broad DB reads added; bounded DTO/schema work |
| Rollback | Revert code PR; restore only changed routing leaves using current revision |

## Environment and guidance
The local scratch Python lacks backend test dependencies/DB/browser binaries. Existing hosted CI provides isolated PostgreSQL17/Redis7.4 and Playwright. Local frontend dependencies may be copied into the separate verified snapshot for typecheck/build. Never run tests against production DATABASE_URL.
Mandatory guidance refs were refreshed and unchanged: Bambale0/skills eca5310, claw 10e261e, wondelai/skills c172996, dev-agents-pack 9ae0af4, agentskills 69ef37e, anthropics ca45fc4. Applied implement/TDD/code-review, backend integration/release hardening/frontend QA, release-it, API integration/release management and webapp-testing. agentskills is a format catalog with no task-specific workflow. Start baseline unchanged.

## Progress
- Audit recorded before production-code edits.
- Isolated source snapshot verified to match the exact remote baseline tree.
- Implemented public schema filtering and new-admission validation, copied legacy-context sanitization, structural template preflight, workflow ratio overrides, and authenticated options/explicit overrides for AI Reference, Pinterest and feed repeats.
- Frontend uses shared literal-Auto filtering and empty restored-choice markers, schema-driven selectors and quote invalidation in Create, batch, action contexts, trend workflows and special flows. The existing server catalog remains the source of choices.
- Isolated remote runner uses a separate checkout, temporary PostgreSQL17/Redis7.4 containers and an explicit test-only environment. No production `.env`, database, provider keys or paid calls enter test execution.
- Behavioral RED on unchanged application code: 53 failed / 7 passed. Initial focused implementation: 214 passed / 1 failed; the failure revealed an existing technical Seedance adaptive mode missing from the narrower UI enum and was fixed without adding Auto back.
- First full backend regression: 2,195 passed / 8 failed in 81.54 seconds. Seven failures were old UI expectations or success fixtures requiring an explicit ratio under the new contract; their original billing, routing, field-filtering and reference-preservation assertions remain. The eighth was the already identified adaptive regression.
- Independent backend and frontend reviews found source-driven Kling frame selectors, a no-ratio feed override, inherited-ratio initialization, stale Create quotes and an old-Auto derivative API null/empty bypass. All are addressed with narrow fixes and regressions before merge. Feed review regressions reproduced 2 failures / 1 pass before the follow-up implementation.
- Additional behavioral RED: the derivative boundary failed five rejected-input cases while its two valid cases passed; fresh/stored Kling contexts and actual workflow-ratio reload produced three expected failures. After fixes, the two new contract modules passed all 95 tests in 3.98 seconds.
- A repeated full run exposed fixed test IDs left in the temporary database and two inactive model IDs in a new test. The runner database was recreated and migrated; the compatibility test now exercises active Seedance 2.0/2.5 admission. No application behavior or database constraint was relaxed.
- Independent review of the seven updated legacy test files confirmed that all original billing, permission, provider-route, frozen-job, complete-reference and declared-field assertions remain intact.
- Exact initial candidate `02ae4238ab0b92c87815ed3acc9689bc5a285c08` full isolated run: 2,220 passed / 3 failed in 86.40 seconds. The remaining failures were static frontend-source assertions for the replaced inline defaults/fields expressions and the strengthened ratio membership guard. Those assertions now follow the shared schema helper and still require backend-driven fields, clean fresh drafts and model-owned choices; the local release architecture check passes.
- Hosted build/static export, TypeScript, Ruff, migrations and ORM parity passed on that candidate. ROXY browser evidence showed Nano Banana 2 Lite correctly waiting for the explicit ratio while the old test helper filled only the prompt. The helper now selects an available required ratio and asserts the exact value in the real create request; success/visibility checks remain unchanged.
- Legacy failed-batch recovery now accepts a narrow optional ratio through existing quote/retry endpoints, exposes current options and freezes the choice only in new retry generations. Historical recipes and successful siblings remain unchanged. The old no-body command fingerprint is preserved; different explicit choices conflict under the same key.
- Batch retry keeps the same request body/key across uncertain responses, refresh and reload. A deterministic two-session RED exposed a receipt lookup race before the batch lock; rechecking the same command under the acquired owner-scoped lock fixes it before active-state validation or billing. Final focused batch suite: 14 passed in 4.29 seconds, including single-charge concurrency and historical replay. Independent backend/frontend reviews found no remaining blockers in this slice.
- Full isolated backend regression on `305ecb0fd8f1e4e2d6ea82c5d598d0208b20146d`: 2,236 passed in 87.43 seconds, with one existing collection-delete warning. Ruff and the release architecture check passed. Hosted CI, Admin Console, Batch Generation, ROXY E2E and ROXY Release Gate also passed on that head.
- Browser execution reproduced two locator-only failures in new tests: the generic alert also selected Next's route announcer, and a wrapped select's accessible name included its options. The final follow-up scopes those assertions to the form and exact field label; all product assertions remain intact.
- Both complete focused browser files passed in Chromium and mobile WebKit after those selector fixes: 36 passed in 44.9 seconds using the existing Playwright 1.56.1 container with networking disabled. This covers explicit selection before upload/quote, legacy repeat and batch recovery, uncertain-response replay, special flows and source-driven compatibility. The host-only WebKit attempt lacked system libraries; no host packages or product dependencies were changed.
- Final exact-head CI and production receipts are tracked in [PR #575](https://github.com/Bambale0/ksu/pull/575); production activation is not claimed by these candidate results.
- Ruff passed on the initial integrated backend. Frontend TypeScript and three pure contract tests passed locally; Next compilation succeeded, but local Node child-process stdout capture prevented its TypeScript configuration phase. Hosted exact-head build and browser CI remain required.
- No database migration or new dependency. Exact-head CI, final independent review, merge/deployment and the remaining runtime route activation are pending; no completed release is claimed.
