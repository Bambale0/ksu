# Neironych fallback coverage — 2026-10-22

## Audit and scope
- Baseline: main@9bfc98c0eba2b21cfb33ecd6c60d74e341bdd2df. Six product workflows and production deploy succeeded at this exact SHA. No overlapping generation-routing PR; #542 changes prompt-tool text fallback only.
- Request: make Neironych a fallback for every matching image/video model and perform real API calls (user clarified "api"). Seven provider models correspond to eight KSU catalog IDs: Nano Pro, Nano 2, Nano 2 Lite, GPT Image 2 text/edit, Seedance 2.0/2.5, Grok Imagine Video 1.5.
- Exists: immutable provider route snapshots, audited admin runtime route controls, Nexus-primary routes, Neironych Nano Pro and Seedance adapters, outbox/background execution, response metadata, uncertain-submission guards, media ingestion and billing/refund seams.
- Missing: Nano 2/Lite and GPT Image 2 contracts/client/service handling; Grok video normalization/dispatch; registry coverage and contract/regression/live evidence. Partial: image circuit namespace currently covers only Nano Pro.
- Reuse: existing Neironych HTTP clients, wire-body snapshot/digest, video polling/download, synchronous image response parsing, provider error classifier, outbox and admin controls. No broad prefactor or schema migration required.
- Official evidence: current provider GET /v1/models returned 15 IDs. Guide https://api.xn--e1aikcel5c5a.online/guide?lang=ru fetched directly over HTTPS because web reader cannot access it. Image edits use images[].image_url; GPT uses size, Nano fixed aspect_ratio; Lite only 1k; Grok ID grok-imagine-video-1.5, duration 1–15, reference_images max 7 and only 480p/720p with references. Never invent capability from name alone.
- Risks: public ratio/reference limits differ by provider. Known unsupported combinations must skip before POST without changing semantics; invalid/policy inputs must fail closed. Unknown synchronous outcomes must not create a second paid job. Returned images can be PNG/JPEG; actual output must be encoded consistently with storage MIME. Existing accepted jobs retain their saved body/key/provider.
- Integration impact: new adapters only for matching models. No new model/version substitution, pricing, wallet, authorization, schema, deployment secret or config key. Grok keeps Kie primary; existing Nexus primary stays. Defaults add Neironych; admin opt-out choices remain available.
- Observability: reuse safe provider response/request IDs, fallback attempt history and image circuit; live evidence contains only synthetic prompts, IDs, statuses, latency and media shape/hash. Never save key, signed URLs, customer media or full base64 in Git.
- Local execution: existing checkout is used for incremental adapter contract/database tests and real API/media validation, which connector browsing cannot execute. No clone.

## Acceptance and public test seams
1. Every matching KSU model has a Neironych fallback, preserving existing primary provider and admin configurability.
2. Adapter HTTP requests match current provider docs; GPT text/edit and Nano references correctly select endpoints; Grok uses exact provider ID and canonical fields.
3. Unsupported provider capabilities skip before paid submission; no policy bypass, duplicate POST, reference truncation, clamped duration or auto-to-square change.
4. Existing persisted provider/bodies/IDs remain valid. Billing/refund identity and accepted-job reconciliation remain unchanged.
5. All synchronous images use separate image protection and correct MIME/encoding.
6. Regression tests cover HTTP contracts, route controls, fallback/rejection/uncertain states and media ingestion through existing service seams.
7. One minimal real call per matching provider model plus GPT edit path; async calls must be polled and downloaded before claiming successful generation. Record failures honestly; do not retry with new keys after unknown outcomes.
8. Exact PR/head SHA must pass repository CI and a separate Standards/Spec review before completion. No merge or deployment is inferred.

## Verification matrix
- Unit/domain: image/video normalization and route options.
- Database/repository: service fallback, snapshot/replay and result ingestion on isolated PostgreSQL.
- Authorization: existing owner/wallet controls unchanged; regression CI.
- Migrations: N/A, no schema change.
- Provider contract: mocked HTTP and bounded authorized live synthetic generation.
- Idempotency/retry/reconciliation: saved wire bodies, provider-scoped keys, no re-POST on unknown image outcome.
- API integration: existing admission/worker/service seams and CI; no public API change.
- Frontend/Mini App/bot E2E: existing exact-head CI; no UI change.
- Smoke/deployability: local compile/lint and exact-head product CI.
- Observability/audit: safe response metadata and persisted fallback history.
- No-hardcode/admin: existing audited generation_provider_routes control plane; model protocol limits are technical contract constants.
- Performance/query shape: no extra runtime query per generation; bounded provider requests, reuse polling reservation.
- Rollback/recovery: admin routes disable fallback for future jobs; code revert only after accepted jobs drain. No destructive data action.

## Plan
1. Commit audit/pointer before production changes.
2. RED/GREEN at image HTTP seam, then image service/snapshot/circuit and route seam.
3. RED/GREEN at Grok HTTP/service seam, then extend routing/admin compatibility.
4. Run focused provider/billing/recovery tests and review.
5. Execute bounded real API calls with saved keys and synthetic inputs, poll/download/inspect output.
6. Update evidence, publish reviewable PR, review Standards/Spec, inspect exact-final-head CI.

## Guidance
- Local .agents AGENTS/README/index and api-integration: progressive discovery, existing contracts, idempotent composition.
- Bambale0/skills: engineering/implement, tdd, code-review; existing KSU service/HTTP seams are authorized by repository test expectations. Preserve narrow vertical slices.
- Bambale0/claw: AGENTS engineering evidence, secrets and validation guidance; its clone requirement conflicts with higher-priority KSU remote-first instructions and is not applied.
- Bambale0/dev-agents-pack: api-integrator — verify payloads/errors/timeouts, no expensive loops.
- wondelai/skills: release-it — bounded calls, circuit isolation, safe retries; no system-wide resilience score claimed by this adapter task.
- agentskills/agentskills README: progressive skill discovery; no provider-specific skill.
- anthropics/skills README: no relevant provider-specific skill; no browser/UI implementation.
- All mandatory sources accessible; no fallback used. Start baseline unchanged and unambiguous.

## Progress
- Audit completed; implementation and live generation not yet started.
