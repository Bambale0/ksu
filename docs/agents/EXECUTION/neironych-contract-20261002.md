# Neironych contract remediation and release

Baseline: `68baa83e16acad9f6bc6cc338a3498dd3b5ecc52`.
Official guide checked 2026-10-02: `https://api.xn--e1aikcel5c5a.online/guide?lang=ru`.
Guide digest: `49ad6c449facad9b2d96de9101027673dcc04554272bc6609be203c91fc50a34`.

## Scope and preserved behavior

Routes remain Neironych -> Kie for exact Seedance 2.0/2.5 and Neironych -> Nexus for Nano Pro.
Other models, public prices, wallet charge/refund identities and private-media authorization stay unchanged.
No Alembic revision/schema change. Existing provider-bound requests continue at their original provider.

## Implemented contract boundaries

- Strict integer Seedance seconds; edit accepts -1/omitted duration and adaptive/omitted ratio; Seedance 2.5 frames require adaptive/omitted ratio. Invalid seed, watermark=true, n>1, fractional seconds and credential-bearing reference URLs are rejected.
- Nano Pro UI offers documented fixed ratios; Nano 2 and the Nexus adapter retain auto support. Legacy Nano Pro auto requests may use Nexus before any Neironych paid submission. No silent auto-to-square rewrite.
- Error parsing retains structured code, X-Request-Id/body request_id and numeric/date Retry-After. Correlation metadata lives in `_provider_response`, not image `external_id` (which would trigger video polling). Full private provider error bodies are not copied into operational metadata.
- Definite account/rate/capability refusals may take the configured single fallback. Input/policy/idempotency-conflict errors do not bypass to another provider. Generic provider_rejected_request is conservatively rejected because its cause may be input/moderation. Unknown 403 is not treated as partner inactivity.
- Unknown sync image outcomes and request_already_submitted never trigger another paid POST. New video jobs save the exact JSON bytes, method, origin, model, key and digest in private `_neironych_submission` before POST; retry does not rebuild those bytes with a future normalizer. Admin tasks use the same wire snapshot.
- Legacy unknown video submissions without a saved wire body fail closed into existing bounded reconciliation/refund handling; no guessed replacement body/key. Already bound legacy IDs keep polling normally.
- `NEIRONYCH_POLL_SECONDS` defaults to 10 (minimum 10); other providers retain their cadence. Outbox/recovery share an atomic next-poll reservation. Retry-After is not shortened by polling/backoff.
- Seedance inputs are inspected before paid submission: real JPEG/PNG headers/geometry; ffprobe duration/container/dimensions/fps and aggregate video/audio duration. MP4/MOV and WAV/MP3 rules are model-specific. Local-file trust requires the KSU origin; external references use bounded public-HTTPS validation with no Bearer header. ffprobe network protocols are disabled.
- `NEIRONYCH_REFERENCE_VALIDATION_TIMEOUT_SECONDS` defaults to 60; transient reference-read failures are bounded pre-submit retries. Input URLs/order are not rewritten on replay.
- Structured logs redact signed query strings, local signed-view tokens, Telegram token paths and Bearer values. Nexus logs prompt length instead of prompt text. SQLAlchemy hides bound parameters to keep private request snapshots out of exception diagnostics.

## Verification evidence

Baseline new contract test: 20 failed / 2 passed. Core fixes: 60 passed.
Protocol/recovery/media/route suite: 98 passed, including one debit/final refund and unchanged replay body/key.
Full backend on a second new isolated PostgreSQL database after final review: 1435 passed, one existing SQLAlchemy warning in trend-category reassignment. Additional late-pending/refund guard regression passes.
Repository Ruff and compileall passed; isolated Alembic upgrade/check passed with no new schema revision.
Additional final-review guards and exact-head CI/deploy verification are recorded in CONTEXT.md and PR checks.

## Safety and rollback

No new paid provider generation was used for these tests. HTTP/provider behavior is mocked; media uses synthetic files.
A 503 is not necessarily an outage, and a successful reference GET does not prove model-compatible bytes.
External provider availability and visual quality cannot be guaranteed by contract tests.
Rollback changes future-job routes through the existing audited Runtime admin setting; keep the Neironych adapter available for accepted IDs. Do not edit a submitted wire snapshot or change its idempotency key.

## Guidance

KSU and local .agents instructions; local debugger; Bambale0/skills diagnosing-bugs; claw and dev-agents-pack api-integrator; wondelai release-it. AgentSkills/Anthropic catalogs were inspected with no additional applicable provider-specific workflow. Shared Start baseline unchanged.
