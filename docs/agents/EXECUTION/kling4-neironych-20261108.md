# Kling 4 Neironych primary — 2026-11-08
## Audit and acceptance
KSU baseline 39b3410ee11de0a2a1da9c0af8e2669279fc921b; upstream 0f69d2a99a50aa94498afa74c95b96f03ce93e47, both inspected remotely.
Exists: immutable upstream deployment/CI, draft Kling contract, four reviewed prices, provider capabilities, native videos and idempotent accounting. KSU has complete Kie reference/keyframe contracts, Neironych durable submission/poll/download machinery and audited DB-backed routing.
Partial: upstream live smoke/enable gate. Missing: KSU native Kling mapping and registered route. Reuse existing adapters/state machine; no prefactor or migration.
Outcome: upstream Kling is smoke-proven and published first; new compatible KSU kling-4.0 requests use Neironych first, Kie fallback. Keyframe model remains Kie. Named elements/voices/original-audio controls and unrepresentable auto geometry fall back before paid submission; never drop these controls. Prompt @image_N/@video_N maps exactly to upstream @Image N/@Video N; original inputs stay intact.
Risks: distinct provider capabilities, prompt role indices, ambiguous paid POST, preserved frozen routes/in-flight jobs, procurement vs unchanged retail.
No-hardcode: admin route options expose both orders and single-provider choices; production choice saved through existing AdminRuntimeService with revision/idempotency/audit. No prices, limits, secrets or unrelated providers changed.
Observability: existing provider attempts, immutable request body, external ID and fallback reasons; no secrets/private payload logging.
Acceptance: live upstream content/usage; published catalog; normalization and HTTP-wire tests; pre-spend capability fallback preserving originals; configured-route create/freeze/submit/poll tests; all six exact-head CI gates, separate review, immutable KSU deploy and safe live smoke.
## Verification matrix / plan
1. Unit/provider contract: RED then GREEN mappings, aliases, ordered duplicate URLs, explicit ratios/durations, invalid controls and HTTP endpoint/body.
2. DB/repository/API: configured routes + real generation creation + immutable submission + fallback; existing ledger/outbox tests for concurrency/idempotency/refunds.
3. Authorization/admin: use existing server permission/revision/idempotency control plane; regression test route validation. No new permission surface.
4. Migrations: N/A, no schema changes. Frontend E2E: unchanged controls, existing CI coverage; backend keeps both public Kling models unchanged.
5. Smoke: one bounded 3-second upstream text task; content/usage confirmation before gate enablement; KSU compatible request/delivery smoke after deployment. Avoid duplicate submission on uncertain responses.
6. Performance: N/A new query shape; existing async provider client/queue. Rollback: audited route back to Kie; frozen accepted tasks keep original provider.
## Guidance evidence
Local .agents verification-before-completion; Bambale0/skills implement; Bambale0/claw backend-integration; wondelai/skills release-it (timeouts, deep health, immutable deploy); dev-agents-pack api-integrator; anthropics webapp-testing (existing browser CI); agentskills format README has no integration-specific workflow. All current source trees refreshed; no external skill scripts executed.
## Progress
- Audit recorded; upstream draft/contract/pricing and live KSU partner credential verified read-only. Bounded paid upstream smoke started; status not yet asserted.

- Upstream bounded smoke 1 (forest) and independent smoke 2 (blue cube): both HTTP 202/accepted, then provider failed with content_policy_violation / nsfw_content_detected. No content/usage confirmed; process exit 0 is not a successful generation. No automatic paid retries or policy fallback. Upstream model remains draft; gates unchanged.
- RED: 9 intended tests failed before implementation; old-route compatibility regression independently failed before its fix.
- GREEN: 115 focused unit/provider/SQLAlchemy integration/Kling regressions on a fresh isolated PostgreSQL database; all migrations applied only there. Ruff passed on all changed Python files. Earlier 68 pure contracts passed. One intermediate rerun reused a test DB and hit fixed-ID uniqueness in preexisting tests; final verification used a fresh database. New test IDs are unique.
- Separate source review: verified role mapping boundaries/order, no deduplication, preserved input snapshots, unsupported-control pre-spend fallback, default Kie route and old provider-route migration preservation. No schema, retail-price, secret, public-model or keyframe changes.
- Exact-head GitHub CI pending PR. Production rollout is blocked by real upstream content-policy failures, regardless of CI results. KSU prepared code remains unmerged, with Kie-first default. Re-run a bounded independent acceptance only after upstream issue is resolved, then enable through existing catalog gates, verify partner native delivery/accounting and set KSU primary via audited admin routing.
