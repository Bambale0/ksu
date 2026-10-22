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
- Audit committed remotely as 55975fd1e9a271f417b6922f62f4e1be0b86d441 before production changes.
- RED/GREEN: new image HTTP contract initially 8 failures; Grok HTTP contract 9 failures; service/route coverage 10 failures; later GPT exposed-resolution, admin migration, URL-result and worker-interruption regressions reproduced before each correction.
- Implemented eight KSU IDs with original primary providers. Immutable wire snapshots use provider model IDs (GPT text/edit share gpt-image-2; Grok maps to grok-imagine-video-1.5). All image circuits isolated from video; image bytes are encoded consistently with MIME.
- READ ONLY production audit: stored routes revision 4 has historical Nexus/Kie image defaults, deliberate Kie/Nexus Seedream and shorter Nexus/Neironych Seedance routes. Targeted interpretation of the complete previous registry upgrades only the four historical defaults and adds Grok; unrelated choices and saved jobs remain. Admin opt-outs remain available after saving the expanded registry. No production data/runtime route writes performed.
- Capability preservation: fixed GPT ratios map 1K/2K/4K to size pixels. Auto plus explicit GPT resolution, Nano auto/unsupported ratios or reference counts, and unsupported Grok controls skip before paid POST. These restrictions are explicit provider limitations; no guessed square, size downgrade, reference truncation or duration clamping.
- Live GPT edit unexpectedly returned data[].url despite response_format=b64_json. The original operation was recovered using the SAME body/key, never a replacement key; the actual new adapter then replayed that same original result and downloaded it through bounded public HTTPS with no API credentials. Internal URLs are rejected by regression tests.
- Separate Standards and Spec reviewers found interrupted Grok replay, fixed GPT size mapping, targeted runtime expansion and legacy relative Grok reference gaps; regressions reproduced each, fixes reviewed again. Both final reviews report no remaining blockers.
- Full local regression and exact-final-head CI results are recorded below / in the PR; no merge or production rollout is claimed.


## Live API evidence — 2026-10-22, started 12:48 UTC

Eight unique operations (seven provider model IDs plus GPT edit), synthetic prompts/media only. One minimal generation per case; no new key after an uncertain result. Every result was downloaded. Images verified with Pillow; videos verified with ffprobe. Artifacts remain in a private temporary task directory; no API key, private URL, base64 or customer content is committed.

| Provider model / mode | Request ID | Result |
|---|---|---|
| gpt-image-2 edit | `421fcc3b-6706-43fa-8ad7-e7079eec9e1d` | succeeded; PNG, 1024x1024; 698523 bytes |
| gpt-image-2 | `6575e458-c865-4e12-9bce-3843e30cbf8d` | succeeded; PNG, 1024x1024; 892113 bytes |
| grok-imagine-video-1.5 | `4fa6ebf4-5de3-4a58-b29b-53c272133876` | done; MP4/H.264, 848x480, 1.041667 seconds; 136174 bytes |
| nano-banana-2-lite | `287dd60e-e0c4-44c3-ab6a-2f8a5af9ec0f` | succeeded; JPEG, 1024x1024; 443639 bytes |
| nano-banana-2 | `02530aab-a87f-4c24-99c1-a9833ec07629` | succeeded; JPEG, 1024x1024; 459532 bytes |
| nano-banana-pro | `2346f7fe-290b-4b5a-8e48-f9c137edfd50` | succeeded; JPEG, 1024x1024; 551602 bytes |
| seedance-2.0 | `17b55180-b38a-4b54-8537-f1969a108d56` | done; MP4/H.264, 864x496, 4.096000 seconds; 581837 bytes |
| seedance-2.5 | `5a61ddb0-36c4-43cc-bae6-82aa6e833b82` | done; MP4/H.264, 854x480, 4.064000 seconds; 1321587 bytes |

Guide SHA256: `113ffb9b4793aa577526c0cceac34af6d98022938b6349199635f606ab7116b4`.
Live checks prove the exercised minimal contracts and file availability, not every resolution/reference combination or future provider availability. The tests do not change customer wallets or generation records. Paid provider costs remain the provider's authoritative account usage.

## Final verification

- Focused initial provider/regression matrix: 218 passed before the final review corrections. Expanded new regression file contains 52 cases; full-suite verification below supersedes this intermediate count.
- Full backend/product regression before the final JPEG-preservation slice: **1886 passed**, one existing SQLAlchemy trend-category reassignment warning, in 57.57s. The final adapter/regression subset passed 93 tests, including 52 new cases. Repeated partial runs used separate task databases; the final full run used a fresh isolated migrated database and CI-equivalent Settings defaults.
- Ruff repository-wide, Python compileall and git diff whitespace checks passed.
- Isolated PostgreSQL 17 created for this task and migrated to existing Alembic head; no application migration added. Dedicated Redis 7.4 used for full regression.
- The first full-suite attempt inherited workstation package configuration and stopped at a pre-existing pricing fixture mismatch; rerun exports verified Settings defaults and isolated test URLs, with production credentials disabled. A stale batch-route expectation then reproduced the intended default-route change and was updated.
- Final image-quality review added explicit byte preservation for valid original JPEGs and quality=95 only when converting another format to JPEG. High-quality JPEG fixtures reproduce four recompression failures on the prior committed implementation; PNG conversion and original JPEG retention pass after the correction.
- Exact final source SHA, complete local/backend results and exact job/step CI evidence are recorded in the PR to avoid a circular commit-SHA ledger update. No merge/deploy is part of this delivery.


## Authorized merge and production release recovery — 2026-10-22

- User authorized merge and then requested completion through production. PR #551 merged as `e4920860e46f986ed254d093b5ebabe10d3f067f`; its tree `ef520af54ff5c3392e49477857046e7b6f682e85` exactly matches the verified feature head `6e22d676612d48f8003cd52351dacd6b694a24e0`.
- Final feature-head CI passed **1890 tests**, lint/compile, migration parity, frontend build/typecheck and all required PR workflows. Eight unique real API operations above succeeded. Earlier statements that merge/deploy were outside scope describe the initial implementation delivery; later user authorization extends the release scope.
- On merged main, Batch Generation, ROXY Release Gate, ROXY E2E and Mini App Playwright E2E workflows succeeded. The initial CI run stalled downloading Ubuntu FFmpeg packages; its cancelled run recovered to a terminal state and attempt 2 now advances normally, using the identical main SHA.
- Confirmed GitHub status inconsistency: Admin Console workflow `39793836489` / check suite `107849837201` reports in_progress, while its only job `119876155893` and every step completed successfully at 14:13:35 UTC. Re-running the job/full workflow returns 403 already running; both cancel and force-cancel return 409 not in progress. This prevents the unchanged deployment workflow's six-workflow release gate from succeeding. Official GitHub troubleshooting documents this out-of-sync state: https://docs.github.com/en/actions/how-tos/troubleshoot-workflows#canceling-workflows.
- Read-only pre-release smoke: public live/ready/operational health and Mini App release metadata returned HTTP 200; actual application image and release marker remain `9bfc98c0eba2b21cfb33ecd6c60d74e341bdd2df`. Production is healthy but this feature is not yet deployed.
- Recovery plan: publish this evidence-only documentation change; review the two-file diff; require exact-head PR checks before merge; require all six fresh checks on the exact new main SHA; allow the existing production workflow to deploy; verify its real deploy step, all application/worker image IDs, public release marker, health and SELECT-only effective routes. Do not alter workflows, fabricate check results, bypass a release gate, mutate stored admin routes or repeat paid API operations.
- Verification matrix for recovery: documentation accuracy and preservation required; behavioral/unit, DB, authorization, provider, idempotency, API and browser coverage use the normal exact-SHA CI because production code is unchanged. No new migration, setting, secret, permission, logging or runtime policy. Smoke/deployability and rollback evidence remain required. Existing image `ksu-app:9bfc98c0eba2b21cfb33ecd6c60d74e341bdd2df` and accepted-job compatibility provide the rollback basis; no destructive downgrade.
- Guidance refreshed remotely: Bambale0/skills diagnosing-bugs (inspect job/status evidence before intervention); Bambale0/claw AGENTS (minimal safe changes and no secrets; no clone because KSU remote-first takes precedence); Bambale0/dev-agents-pack release-manager (immutable release/rollback/smoke evidence); wondelai/skills release-it (dependency health and immutable deployment). agentskills/agentskills and anthropics/skills README catalogs have no additional applicable production-recovery procedure. Local .agents AGENTS/README/index and verification-before-completion require fresh completion evidence. All sources available; no fallback. Start baseline unchanged and unambiguous.
- This recovery PR intentionally changes only CONTEXT.md and this execution ledger. Final checks, merge/deploy SHAs and production results will be recorded in its PR body, avoiding a circular source-SHA update.
