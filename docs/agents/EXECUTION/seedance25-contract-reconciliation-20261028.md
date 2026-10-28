# Seedance 2.5 contract and accepted-job reconciliation — 2026-10-28

## Fresh audit

- Baseline: `main` `530fbc4a70a2615cf9ffd2ba5ef7d547019c85b8`.
- Current provider route policy is intentionally untouched. Production revision 6 is reported as common `neironych -> nexus` for Seedance 2.5 and one scoped `nexus -> neironych` override.
- Exists/reuse: typed Neironych video normalizer; immutable request snapshot and idempotency key; one paid POST followed by polling; durable Generation/outbox; structured provider error codes and redaction; mocked contract/reliability tests.
- Partial: edit exists but accepts legacy `duration=-1` / `aspect_ratio=adaptive`; `generate_audio=false` is incorrectly treated as provider incompatibility; accepted jobs are refunded and terminalized solely on KSU hard lifetime; user errors contain only an opaque provider code.
- Missing: extend and draft payload normalization; a durable reconciliation marker for accepted jobs beyond the local lifetime; allowlisted safe user explanations for Neironych 400/402.
- Official contract evidence checked 2026-10-28: [ArgoLink Seedance 2.5 model page](https://argolink.io/en/models/seedance-2.5) and [ArgoLink Seedance 2.5 API guide](https://argolink.io/en/blog/how-to-use-seedance-2-5-api). `POST /v1/videos/generations`, model `seedance-2.5`; edit/extend use `omni_reference_task_type`; draft preview uses `draft:true` at 480p; final draft request contains only `draft_task.id`; silent output uses `generate_audio:false`. Jobs are asynchronous and may run well beyond typical latency, so a local deadline is not terminal provider evidence.

## Acceptance criteria and implementation plan

1. Neironych Seedance 2.5 keeps boolean `generate_audio=false` in the frozen wire body; no fallback is scheduled merely for silence.
2. Edit omits duration and aspect ratio, requires a source video and permits documented image references. Extend requires a source video, preserves 4-30 second duration and omits aspect ratio. Draft preview is forced to 480p; a final draft render accepts only a bounded `draft_task.id` object.
3. A generation with a persisted provider task ID remains non-terminal after KSU's hard lifetime, keeps its debit, is marked for reconciliation and remains pollable. Unknown pre-acceptance submissions retain their existing separate policy.
4. Neironych 400/402 terminal messages use an allowlist keyed by status/code; provider text, prompt, media URL, credentials and response body are never copied to the public Generation error.
5. No provider route, price, schema, migration, paid request, production config or deployment change.

Plan: add RED provider-contract/error/reliability regressions; implement the narrow normalizer/error/reconciliation changes; run focused then full backend checks; review against this spec and repository standards; push a PR and require exact-head CI.

## Verification matrix

- Unit/domain: contract normalization and safe error mapping — required.
- Database/repository: accepted Generation remains generating, marker persists, wallet unchanged — required.
- Authorization: N/A; no authorization surface changes.
- Migration: N/A; existing JSON metadata and status are reused.
- Provider/external contract: mocked exact bodies only; no paid POST — required.
- Idempotency/retry/reconciliation: immutable snapshot retained; accepted task is polled, never resubmitted or fallback-routed — required.
- API integration: public generation error contains allowlisted reason only — required through service/API serialization coverage where practical.
- Frontend/Mini App/bot E2E: N/A; no control or layout change.
- Smoke/deployability: compile/lint/full backend CI — required; deploy explicitly excluded.
- Observability/audit: reconciliation marker, timestamp and safe error category retained — required.
- No-hardcode/admin: provider routes remain the existing revisioned control plane; fixed protocol enums/error allowlist are code-owned contract — required.
- Performance/query shape: no new query; existing bounded recovery batch — N/A beyond regression.
- Rollback/recovery: revert PR; accepted jobs remain recoverable because no terminal/refund mutation occurs.

## Guidance

- Local project `.agents` is absent and `.gitignore` excludes it; the repository has no `.gitmodules` entry to initialize. Used the available current `C:/Users/happy/.agents` api-integration, test-driven-development and verification-before-completion skills.
- `Bambale0/skills`: implement, TDD and code-review; narrow vertical slices and exact-head checks.
- `Bambale0/claw`: backend-integration and kie-seedance; durable local/remote IDs, async polling, idempotent completion, mocked provider calls.
- `wondelai/skills`: Release It stability/retry guidance; a timeout without terminal provider evidence is not permission to duplicate a paid mutation.
- `Bambale0/dev-agents-pack`: api-integrator and test instructions; verified fields, bounded failures, safe metadata and mocked contract tests.
- `agentskills/agentskills`: progressive disclosure only; no provider-specific workflow.
- `anthropics/skills`: catalog inspected; no applicable Seedance/backend lifecycle skill.
- Shared `Bambale0/start` baseline is already embedded in repository `AGENTS.md`; no ambiguity or baseline change.

## Progress and verification

- RED: the new public-reason import failed because no safe mapper existed; after that slice, provider contract tests failed on the old edit geometry, rejected `generate_audio=false`, absent extend support and absent draft normalization.
- GREEN: `APP_ENV=test KSU_ALLOW_TEST_DATABASE=1 .venv/Scripts/python -m pytest tests/test_neironych_documented_contract.py tests/test_neironych_submission_protocol.py tests/test_seedance_admin_full_wizard.py tests/test_seedance25_parity.py -q` — **86 passed**. All HTTP/provider calls are mocked; no paid request was made.
- Static checks: focused Ruff passed; `python -m compileall -q app tests` passed; `git diff --check` passed.
- DB-backed provider and worker regressions are present but cannot run on this Windows host: Docker/PostgreSQL are unavailable. An attempted focused DB run was stopped after repeated connection failures. Exact-head Linux CI with the repository PostgreSQL service remains a hard PR gate.
- No route/config/price/migration/deploy change. The accepted task retains provider, external ID and route index; the hard-lifetime transition only adds reconciliation metadata and keeps the debit pending an authoritative terminal provider result.
