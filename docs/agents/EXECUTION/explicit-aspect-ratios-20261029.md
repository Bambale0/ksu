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
| Frontend/bot E2E | Create/reuse/special workflows/bot choice with existing project seams; Chromium/mobile CI |
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
- Implementation and verification pending; no completed-code/deployment claim.
