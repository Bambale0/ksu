# Support inbox and admin audit — 2026-11-06

## Scope and baseline

The user reports that support messages do not arrive and requests chats/replies plus a review of the whole admin surface and management of existing entities. The word "цветы" is treated as a likely typo for "чаты"; no flower-related product is introduced. Baseline main and running production image: `9590eb61ca209b3fcb2cb9a77ab74c3cf49840c7` (PR #580). Production source has unrelated untracked browser test artifacts, which must be preserved. No overlapping open support PR was found.

The scope is diagnosis, isolated implementation, regression and browser verification, independent review, and an exact-head CI-backed PR. No real customer/admin test messages, historical replay, balance changes, paid generations, production migration, or unrelated production writes are authorized by this audit. Any deployment claim requires separate exact-release evidence.

## Fresh audit before production-code changes

1. **Exists:** authenticated customer support ticket/message API; user conversation screen; separate main and control admin screens; RBAC/MFA/audit/command ledger; SupportOutbox and support worker; generic NotificationDelivery worker; support state/priority/assignment service; tests and CI.
2. **Partial:** main admin replies save a message but bypass SupportOutbox; activity timestamps do not move on message-only writes; primary support UI has fixed list limits and no live inbox refresh; closed tickets lose their status control; control UI has the durable path but is secondary.
3. **Missing:** durable inbound operator notice, one canonical reply delivery path, reliable recent conversation visibility, explicit admin delivery feedback, regression coverage of the real main admin HTTP entry point.
4. **Reuse:** existing schemas, SupportOutbox leases/retry, transactional notifications, AdminPolicy/AdminCommandLedger/AdminAuditService, real current admin recipient configuration, request IDs, existing browser fixtures and isolated PostgreSQL test setup.
5. **Prefactor:** a small shared support service boundary and backwards-compatible endpoint adapters; do not rewrite the whole admin or reactivate retired bot FSM blindly.
6. **Risks:** support text is private; notices must reach only authorized configured recipients and access must be checked server-side. Never broadcast to every historical AdminAccount row. Preserve ownership, confirmation, idempotency, closed-ticket rules, stale-dialog guards, and draft text on failure. Do not double-send generic and full Telegram replies.
7. **Migration/integration:** prefer additive response metadata and reuse existing tables; no schema migration planned. Retain direct Telegram contact and Mini-App-only bot architecture. Existing customer API shape remains compatible.
8. **Public seams:** customer HTTP create/reply; primary and control admin HTTP reply/list/detail/status; durable worker with fake Telegram transport; browser main admin conversation and entity management journeys.
9. **No hardcode/admin:** derive recipients from the existing configured policy and effective permissions; no personal identifiers, new business limits, prices, model/provider choices, or secrets in source. Reuse existing bounded list parameters and frontend polling conventions.
10. **Observability:** expose queued/sent/undeliverable/failed reply state; record safe IDs/action/outcome/attempt, never message bodies/tokens in logs; verify delivery through queue rows and worker outcomes.
11. **Acceptance:** new customer message persists and creates a durable operator notice; old conversations rise by actual activity; main/control replies share exactly one full-text durable delivery and retain inbox visibility; authorized lifecycle operations include reopening; long histories and large lists remain reachable; UI refreshes safely, preserves drafts, and cannot send to the wrong conversation after a race.
12. **Broad admin acceptance:** inventory every actual navigation area and management action; trace UI→API→validation→permissions→persistence→UI; reproduce and fix confirmed scoped defects, with evidence level recorded per area. Do not claim a source audit is executed browser verification.
13. **Rollout/recovery:** changes are prepared in an isolated branch/worktree; standard immutable-image release and previous SHA rollback if separately authorized. Existing support records remain readable without mutating/replaying them. Failed historical outbox rows are not bulk retried. Confirmed user contact can recover eligible new undeliverable replies only through bounded existing recovery semantics.
14. **Plan:** audit ledger → failing public-boundary tests → canonical inbound/outbound support slice → focused backend verification → main/control UI and browser regressions → broad admin coverage and minimal fixes → independent Standards/Spec review → exact-head project CI → concrete delivery report.

## Production evidence (read-only)

At inspection on 2026-11-06, main and all ten Python service images matched the baseline; support worker, other workers, PostgreSQL and Redis were running. Database queries ran in an explicit READ ONLY transaction and were rolled back.

- 23 tickets: 17 open and six in progress.
- 21 customer messages; newest persisted at 2026-11-05 20:18:27 UTC. The corresponding API response was HTTP 201.
- Three tickets have messages newer than their unchanged activity timestamp.
- Only six historical support_reply notifications; no incoming operator notifications.
- Six old failed SupportOutbox records (August), each with eight attempts. They are evidence, not permission to replay.
- The active dispatcher uses the Mini App launcher; legacy support FSM is not registered. Direct contact messages are a separate channel and cannot be assumed to be stored internally.

Hypotheses: (A) saved messages without an operator notice and fresh ordering is confirmed by code + runtime state; (B) messages typed into launcher/direct contact would not create an internal ticket, by current architecture; (C) fixed list/history limits can hide old or long chats, confirmed by code but not the current low production ticket count. Worker outage is not supported by observed process state.

## Verification matrix

| Category | Evidence / status |
| --- | --- |
| Unit/domain | Support 20, payment compatibility 79, session/refund compatibility 41 focused tests pass; download/storage 38 pass; list paging 20 pass |
| Database/repository | Real isolated PostgreSQL, canonical message/outbox atomicity, concurrent ticket ordering, refund row-lock/idempotency and stable list ties exercised |
| Authorization | Owner isolation, configured recipient selection, account deactivation, session MFA/reason, private-media signatures/expiry and paging RBAC pass; login/me capability parity and real signed/MFA session regressions pass (54 with security compatibility) |
| Migration | N/A: existing tables reused; no schema migration added. Core exact-head CI Alembic 1.20.1 parity passes |
| External contract | Fake Telegram transport covers success/forbidden/transient delivery; authoritative payment GET only in production; media byte download/browser contract exercised without real customer sends |
| Idempotency/retry/reconciliation | Same reply key produces one message/outbox; bounded recovery and generic/full-delivery exclusion; concurrent admin/worker refunds remain one credit; Telegram transport remains at-least-once after an ambiguous timeout |
| API | Real main/control/customer routes, unique route registration, compatibility, lookup-vs-list behavior and bounded pagination exercised |
| Frontend/bot E2E | 45 Chromium admin support/security/runtime/pagination cases and four media-download cases pass; bot launcher architecture unchanged; WebKit awaits final exact-head CI |
| Smoke/deployability | Core d7b117e5 full backend CI: 2450 passed; exact final head gates and release proof remain pending |
| Observability/audit | Safe delivery state, attempts and correlation IDs exposed; revoke reason and admin command audit retained; no body/token logging added |
| No-hardcode | Recipient configuration, policy supplements, existing business config and media signing reused; no personal IDs or new price/credit rules introduced |
| Performance/query shape | SQL limit/offset/count over matching filters, deterministic timestamp/UUID ordering, latest-message cursors; no new unbounded entity list |
| Rollback/recovery | No production data rewrite or historic reply replay; ordinary immutable-image rollback; historical paid mismatch remains an operator/domain-resolution case |

## Guidance inspected

- Repository AGENTS.md, README, CONTEXT, support/admin implementations, tests, workflows, compose; production-local .agents AGENTS/README/index.
- .agents frontend-ux-audit and full checklist, local revision e4a2e491647fb9d88a61e50f1f05f5059235f09f.
- Bambale0/skills diagnosing-bugs, tdd (including tests/mocking), code-review.
- Bambale0/claw QA_AUDIT_CHECKLIST and UX/UI audit: trace each control to persistence.
- wondelai/skills ux-heuristics and release-it: visibility, recovery, bounded retries and health.
- Bambale0/dev-agents-pack prompts/pr-review-checklist.
- anthropics/skills webapp-testing: rendered browser/network/console checks; inspect scripts before running under KSU rules.
- agentskills/agentskills README/catalog: no applicable product runtime skill; format/progressive-disclosure guidance only.
All mandatory sources were accessible and inspected remotely; no skills repositories were cloned. Shared baseline is unchanged and unambiguous.

## Progress

- Audit baseline, production evidence and ownership recorded before changing production code.
- Backend/support owner: support_audit. UI/admin inventory owner: admin_audit. Root: integration, runtime evidence, execution ledger and release/PR coordination. Independent reviewer: engineering_guidance.
- Implementation follows the regression-first slices below; the final exact-head CI/release state is recorded separately from local proofs.

## Expanded support-message triage and payment audit (2026-11-06)

The user explicitly reinforced: check the actual support messages and fix all confirmed issues. Read-only review found 21 incoming messages in 17 open tickets. Categories include missing payment credit, duplicate generation charges/no result, video download, missing history, input/age personalization and generative quality/refund requests. Private message text, user IDs and invoice IDs stay out of Git.

Runtime evidence:
- All succeeded payments for these ticket users have exactly the expected payment-ledger entry; no succeeded-without-credit case was found.
- One recent card payment remains pending because its frozen local amount is 543.50 RUB while the same authoritative Lava invoice is COMPLETED at 543.48 RUB for a 500-ROX package. This is a confirmed contract mismatch, not evidence of an unpaid invoice.
- Current generation rows for the ticket users are terminal; all succeeded rows have a result URL. Actual file availability and duplicate-charge/refund evidence require further targeted checks; do not equate a stored URL with delivery.
- Open PR #554 (head b17030090ec4ca0264bc56c8e61cd81cf48dc96d) already contains a reviewed fixed-offer/amountTotal integrity fix and deterministic retry termination. Inspect/adapt this existing work against current main instead of implementing a competing unreviewed money rule.
- Admin payment recheck/reprocess and legacy reconcile dispatch CardPaymentService or PaymentService, while the payment worker also supports Payment2328Service. Verify with failing service/API regressions before adding the missing 2328 dispatch.

Payment slice constraints and acceptance:
1. Validate authoritative identity, currency and exact amount; no new rounding tolerance, blind expected-amount rewrite, manual SQL credit, duplicate invoice or unapproved real payment/refund.
2. Preserve reviewed invoice-integrity behavior from #554, newer main changes, settled/refund-review guards, idempotency and safe audit evidence.
3. Provide a concrete guarded existing-admin/MFA path for a historic paid mismatch; do not forge sessions, confirmation or step-up evidence. Operator compensation/refund decisions are distinct from code repair.
4. Test fixed/dynamic offers, mismatched/conflicting/non-finite amounts, terminal vs transient lookup, concurrent replay and all supported admin payment providers in the isolated test environment.
5. No schema or price/configuration mutation planned. Record unresolved individual financial/quality cases honestly rather than automatically closing support tickets.

## Generation refund boundary audit before repair

Read-only per-generation ledger inspection of the duplicate-charge ticket shows one debit per operation; all seven failed operations already have automatic refunds and all nine successful operations are marked sent. Do not refund them again.

A separate source defect is confirmed: AdminGenerationOperationService.refund_operation detects only reference_type=generation_refund, whereas GenerationProviderService.fail_and_refund writes kind=generation_refund with reference_type=generation and the canonical generation:<id>:refund key. The admin path uses a different key and can miss the automatic refund. It also lacks the generation row lock used by the worker.

Root owns this minimal slice: first reproduce automatic→admin, admin→automatic, legacy-admin→automatic and concurrent attempts at real service seams in isolated PostgreSQL; then share detection of both persisted refund shapes, serialize on the same generation row, reuse the canonical refund effect, and retain AdminPolicy/MFA/confirmation/command audit. No production refund, wallet update, or historical transaction rewrite. Existing no-charge/free replay and repeated admin commands must remain no-ops. Test actual ledger balance and refund count, not only returned status.

## Session revocation boundary audit (before correction)

- Full admin inventory found two handlers for the same DELETE `/api/v1/admin/security/sessions/{session_id}`. Router registration selects the legacy account handler first, shadowing the audited handler with step-up MFA and an operator reason.
- Scope: remove only the duplicate weaker handler; preserve the existing canonical endpoint and its session lock/audit; require a nonblank reason after whitespace normalization; bring the main admin form into the same reason/MFA contract.
- Regression plan: actual composed router must have one route; stale MFA, missing/blank reason, and missing permission must not revoke; a fresh authorized session must revoke and retain the operator reason in session/audit. Test against isolated fixtures only, never revoke real sessions.

## Duplicate support reads audit (before correction)

- Route inventory found legacy GET support list/detail in `admin_capabilities.py` shadowed by `admin_operations.py`. They already delegate to the support service, but keep obsolete query signatures and an ambiguous OpenAPI contract.
- Scope: remove redundant handlers and route-only imports/dependencies; retain the canonical permission-checked main/control support service and externally unchanged paths. Verify unique composed GET routes and existing capability tests.
- Read-only runtime recipient validation: one configured operator, one matching account, one active account/user with effective support-read permission. No identifiers are published here.

## Concurrent message ordering follow-up (before correction)

- PostgreSQL `now()` in the default message timestamp reflects transaction start, which may precede a wait for the ticket lock. Thus a later serialized reply can receive an earlier timestamp and invert newest-message / needs-reply semantics.
- Use one wall-clock timestamp after the ticket lock for the new message and ticket activity in both customer and admin paths. Verify the delayed-transaction ordering with controlled concurrency in the isolated database.

## Review checkpoint

- Automatic/admin generation refunds: meaningful regression RED 5 failed / 1 passed; focused GREEN including prior financial safety 9 passed. Shared generation row lock and canonical refund key now coordinate both paths; legacy ledger shapes remain recognizable. Independent standards review: no blocker.
- Card invoice integrity: 19 failed / 1 passed RED, then 20 passed GREEN. Provider 2328 admin dispatch: 3 failed / 5 passed RED, then 8 passed GREEN. No balance changes were made in production.
- Support: 13 initial regressions RED then GREEN; 17 support regressions plus existing related compatibility tests passed (110 total), before adding the duplicate-route contract and concurrent-timestamp follow-up. Independent privacy/delivery review found no blocker; Telegram remains at-least-once across an ambiguous transport timeout.
- Session revocation: fixture-only failures were corrected without product edits; meaningful RED 6 failed / 1 passed reproduced the shadowed weaker route, stale-MFA acceptance and lost reason. Canonical handler now retains the legacy response boolean and normalizes the audit reason. Independent review: no blocker.
- Historical confirmed-paid invoice mismatch remains unresolved operationally. Existing recheck/reprocess rejects the mismatched invoice; raw wallet adjustment is unsafe. A new explicitly approved payment-domain acceptance would need fresh MFA, exact invoice/amount/currency/ROX evidence, atomic command/audit/credit, and defined later refund handling. Do not imply that the prevention fix settled this existing customer payment.

## Download authentication boundary audit (before correction)

- Two support complaints concern saving videos. The exact screen they used is not known, so their historical cause is not assumed.
- Current Downloads UI independently has a reproducible defect: a plain anchor targets the protected media download endpoint. Telegram authentication for that endpoint requires `X-Telegram-Init-Data`, which a browser anchor cannot send. Existing E2E checks only the href rather than a download.
- Scope: reproduce the real unauthenticated-navigation failure; repair Downloads using the established authenticated/signed-media contract; preserve media ownership, token expiry and private-media boundaries. Never put Telegram init data into a URL or remove endpoint authentication.
- Verification: a real click must initiate a successful download with the intended media rather than merely construct a URL; cover relevant auth/signature/ownership failure paths. No paid generation, real user message, provider mutation or historical file rewrite.

## Admin visibility boundary audit (before correction)

- Screenshot QA found that author CSS sets `display:grid` on login/shell containers but does not preserve the native `hidden` attribute. A successful login can leave an entire login panel visible above the intended mobile admin page; hidden step-up controls are affected by the same CSS cascade.
- Scope: restore `[hidden] { display: none !important; }` in the shared admin stylesheet; test actual visible state after login in both surfaces, including MFA controls. Do not change authentication or permission checks.

## Verified implementation checkpoint and remaining boundaries (2026-11-06)

- Core code is published in draft PR #581, commit d7b117e5eb9ccd2197fe3c536f6125c221756a6d. GitHub tree content was verified against all 45 isolated source blobs before publication.
- Final support regression set: 20 passed, including unique HTTP routes and the delayed-transaction timestamp race. Payment/provider dispatch compatibility: 79 passed. Session/refund/security compatibility: 41 passed. Independent reviews found no blocking issue in these slices.
- The core exact-head CI full backend/product suite passed 2450 tests. This result belongs to d7b117e5 and must not be represented as validation of the later download/pagination/capability commit.
- Download regression: former header-only endpoint navigation reproduced the failure. Signed local media capability now authorizes browser/native attachment download without leaking Telegram init data; wrong owner/key/asset/signature and expiry remain denied. The backend/storage suite passed 38 tests, actual browser download/native fallback suite passed four, and typecheck/build passed.
- Read-only rotated production access logs independently contain ten normalized media download requests returning HTTP 401 between 2026-11-04 21:39 UTC and 2026-11-05 18:46 UTC. They confirm the current endpoint problem but do not identify the exact path used in the older complaints.
- Backend list paging reproduced nine meaningful failures before repair, plus a separate same-created-at ordering regression. All 20 paging tests and 39 related existing compatibility/source checks now pass: eight list surfaces, filtered totals, stable ties, access denial, exact promo lookup compatibility and server-side trend search.
- UI paging/permission navigation has 45 passing Chromium cases, including the previous 21 support/security/runtime cases, plus 22 static source contracts. Dedicated trends and creator queues have request-sequence guards; generic main/control navigation retains its pre-existing late-response boundary. Do not claim all admin navigation races are fixed.
- Independent UI review exposed a final contract issue: login/me serialized only legacy role permissions, whereas AdminPolicy also grants role supplements. This is repaired through a common permission module. The five moved role/action/helper definitions are AST-identical to the baseline. Meaningful RED was 14 failed / four passed, followed by 54 passing auth/policy/security regression and compatibility tests. Real signed login/me, role supplements, explicit deny, wildcard/deny-all, inactive account and unverified MFA paths are exercised. Runtime wildcard authorization remains open-ended; only UI capability enumeration is finite when explicit exceptions exist. Seven creator-partnership runtime contract checks also pass after following the re-export. Independent standards/spec/security review signs off with no open blocker for the final prepared slices.

### Actual support-case outcomes

Read-only financial inspection covered 1533 generations belonging to open-ticket users: no nonterminal jobs, duplicate generation debits, missing full failure refunds, excess refunds, or succeeded payments without their ledger credit were found. A stored result URL is not proof of file availability. The specific duplicate-charge complainant had 16 terminal operations: nine successful/sent and seven failed/fully refunded; another refund would duplicate value.

One distinct payment is authoritatively COMPLETED at 543.48 RUB while the immutable local contract expects 543.50 RUB for 500 ROX. It remains pending and uncredited. The prevention fix rejects mismatched future invoices and fixes safe provider dispatch; it does not settle this historical payment. Current fixed Lava offers also need their business catalog/price configuration reconciled before this route can be considered operationally restored. No unsafe tolerance, raw wallet adjustment, price mutation or compensation was applied.

Age/photo-input and visual-quality complaints were correlated read-only within 24 hours of the three relevant ticket dates. The two age/video complaints map to five succeeded v1 generations but none stores a trend ID or workflow link; there are no matching v2 workflow records. The birthday upload complaint has no generation/workflow in that window. Current matching templates normalize, but neither their names nor normalization proves which historic template was used or reproduces output quality. The absence of persisted v1 trend linkage is an observability limitation, not permission to guess or alter a catalog record. No paid generation was launched, no support ticket was silently closed, and no customer reply was sent.

### Release evidence boundary

No production source/image/data changes have occurred during the isolated preparation. Read-only release readiness confirms clean tracked production source at 9590eb61, successful existing read/fetch authentication, and identical 44 migration sources; both repository and production database are at 0044_trend_workflows. The standard release migration command therefore has no pending schema work for this change. Final exact-head six-workflow CI and exact deployed-SHA health evidence remain required; any actual repository review or production-environment approval gate must be honored. No local/browser green result is a production delivery claim.

## Automated review follow-up audit, before corrections (2026-11-06)

Review of commit 2fa2e288 identifies four concrete remaining cases: customer-triggered operator notification spam; dependency on temporary bootstrap recipient IDs despite the owner-enrollment runbook clearing them; recoverable support replies beyond a single worker batch remaining terminal; and malformed provider catalog amounts entering creation_unknown before any invoice request.

The release is held for public-boundary regressions and small corrections. Recipient discovery must become durable and admin-managed without broadcasting to every historical admin. The customer create/reply API must share an atomic configured quota before persistence/enqueue. Invalid catalog values before remote creation must use terminal validation and release any promo reservation. No production configuration, payment, message or historic replay is performed by this review.

Root recovery slice: the current contact hook selects at most support_outbox_batch_size terminal blocked/chat-not-found rows and skips locked rows, but there is no continuation pass. Reproduce a backlog larger than the batch and a temporarily locked eligible row. Schedule every matching row atomically in SQL for this user, preserving status/error eligibility, other users, sent and leased rows. Keep actual delivery bounded by the existing worker batch/lease mechanism, prove repeat contact is a no-op and drain via the real worker with a synthetic Telegram transport. Reuse the schema; no migration or production replay.

Recovery RED reproduced both defects: only three of eight eligible replies were rearmed, and a locked eligible row was silently skipped (two failed tests). Before the product patch, the worker-drain fixture is isolated from unrelated existing suite rows by selecting timestamps earlier than their minimum and using an exact multiple of the configured batch; this preserves the assertions while avoiding consumption of foreign test data.

### Review correction evidence checkpoint

- Contact recovery: clean RED two failures (three of nine scheduled; temporarily locked row skipped), then GREEN three tests in 6.06s. One scoped SQL UPDATE schedules every eligible terminal blocked/chat-not-found reply, while the worker still claims bounded batches. The synthetic backlog is actually drained through the worker without duplicate sends, and sent/sending/foreign/non-recoverable rows remain unchanged. Ruff/AST/diff pass; independent review signs off.
- Customer API rate limiting: meaningful RED eight failures / three passes, including all 20 concurrent requests accepted at configured limit three. GREEN 22 tests includes 11 new real signed HTTP/Redis cases and existing profile/abuse compatibility. The existing atomic Lua quota is shared by create/reply, after input/ownership/status checks and before support persistence/enqueue. Existing fail-closed 503 and 429 Retry-After apply; normal operator writes and reads are unaffected. A typed environment setting documents default 10/minute and the existing zero-disable convention. Independent review signs off.
- Catalog prices: clean RED six failures / three passes, then GREEN 68 regression/compatibility checks. Malformed and non-finite supported-currency prices now raise the existing terminal validation exception before invoice creation. Idempotent replay and legacy promo release are tested; current partner attribution remains intact and unsupported-currency noise keeps its old semantics. Root independent review signs off.
- Durable operator recipients: use the existing AdminRuntimeSetting table for an explicit admin-ID mapping, with owner-only existing admin CRUD and fresh MFA. Initial import is a one-time compatibility seed from eligible configured bootstrap accounts; an explicit saved mapping, even empty, wins thereafter. No default broadcast to historical administrators and no new schema migration. Backend and UI regressions are in progress.


### Durable recipient and concurrency verification

The durable recipient API and UI now use an explicit persisted admin-account selection. Existing owner/MFA/audit controls protect changes; a configured but inactive or demoted operator remains visibly selected with effective delivery disabled. Creating a new subscription for an ineligible account is rejected. One-time bootstrap import does not replace an explicit empty selection and never selects every historical admin. Read-only production inspection before release found no saved recipient mapping, so the existing eligible bootstrap operator can be imported by the normal startup path.

Meaningful recipient regressions began with 11 failures / two passes, then 13 passes. Two additional real owner PATCH regressions reproduced HTTP 422 when deactivating or demoting an already subscribed account; validating eligibility only for a new subscription resolves those cases without weakening eligibility. Final combined backend verification passed **72 tests in 24.51s**, isolated log `test-run-20261106T062837Z-3668821.log`. It covers all 16 recipient cases, the prior support delivery suite, real signed customer quota requests, profile/bootstrap/security compatibility and concurrent private reads.

Concurrency review reproduced two PostgreSQL deadlocks rather than inferring them. First, simultaneous support submissions by operators held FK key-share locks on their own user rows while recipient authorization requested exclusive locks on both users. Second, simultaneous notification/profile reads upgraded support shared locks to exclusive balance-eligibility locks. Both eligibility queries now use shared row locks, which compose with key-share reads and still block active/role revocation. The separate signed inbox/profile regression plus existing balance/revocation cases passed **38 tests in 10.74s** before the combined pass. Independent reviewers inspected the recipient, quota, recovery, catalog and balance-lock changes; no unresolved finding remains in those local slices.

Recipient UI browser regressions reproduced six missing-feature failures and then passed **23 Chromium cases** including the existing 17 support cases. The main admins page shows configured/effective status and zero-recipient warnings; enable/disable crosses the existing MFA and Execute confirmation. A mobile 390x844 screenshot was inspected. The operator permission and fresh-MFA boundaries remain unchanged.

The previous published head 2fa2e288 completed backend CI with 2499 passing tests, but its Mini App E2E workflow failed two actual-download fallback cases in WebKit while Chromium passed 1008 and WebKit passed the other 341. This is an open release gate, not a successful full browser verification. The exact Playwright 1.56.1 environment is being used to distinguish transport, browser and product behavior. No test is skipped or reduced to a link-only assertion. A new complete backend run is also in progress after the Python source freeze; all six CI workflows and automatic review must be renewed for the next published head.


### Final prepared WebKit and complete-suite checkpoint

The two previous WebKit failures had two independently reproduced causes. A real HTTPS response with image/png and attachment disposition rendered inline in WebKit 1.56.1; the same bytes and filename downloaded with application/octet-stream. Separately, routed attachment responses did not produce a usable WebKit download event even after the MIME correction. The product change therefore sets the binary attachment MIME only for explicit downloads, including signed S3 ResponseContentType. Image/video previews and asset metadata retain their original MIME, and all existing ownership/signature/expiry/public gates remain unchanged.

HTTP regressions first produced **six failures / six passes** on the exact MIME contract, then **30 media/storage compatibility checks passed in 6.28s**. They verify signed and authenticated local downloads, unchanged preview MIME/bytes, video Range responses and real offline S3 SigV4 signing for both download entry points. The browser fixture now uses a real loopback HTTPS attachment with an ephemeral certificate, isolated test-only certificate trust and finally cleanup. **Eight actual download/native cases passed in 21.8s** across Chromium and WebKit in the exact Playwright 1.56.1 CI image. Both fallback cases verify download completion, URL, filename, bytes and absence of Telegram init-data headers; native-error invocation is explicit, and native cancellation performs no fallback. Root and independent engineering review sign off. Physical Telegram devices remain outside this automated verification.

The single full local Python run after the support freeze produced **2524 passing tests and 14 setup errors in 162.37s**. All 14 errors came from unchanged deployment-preflight fixtures because the application test image lacks the git executable; there were no product assertion failures. Those exact 14 cases then passed separately in 0.82s using the existing host git/venv with a clean environment and only temporary synthetic repositories, no installations or production changes. This is reported as two bounded runs, not a single complete green run. The later media slice is verified separately above. Final exact-head CI must still run the complete suite and all six required workflows before merge/release.

All prepared source is frozen after independent review. No production source, image, payment, support message or historical outbox row has been changed by preparation. Read-only baseline records the original one eligible operator, all ten application services at 9590eb61 and the six failed legacy support replies; post-release verification must compare these exact cohorts and confirm the intended new runtime configuration.


### Creator pagination follow-up after automatic review of c61c46bd

The c61c46bd exact-head CI full backend passed **2541 tests in 92.22s** and Alembic reported no new upgrade operations. Its independent ROXY E2E completed seven real API/DB/Redis/worker journeys; the remaining comprehensive browser gate is tracked separately. Automatic code review found one additional P2: creator applications and agreements still used created_at-only ordering beneath the newly paginated UI.

Source inspection located applications ordering in CreatorPartnershipService.list_applications and agreements ordering in the admin creator API. Two real HTTP regressions failed before correction, demonstrating incorrect tie order for six rows with identical timestamps and deliberately shuffled UUIDs. The product correction appends the corresponding descending primary-key ID to these two existing orderings. Filters, totals, limits, offsets and authorization remain unchanged.

The new regressions and complete relevant creator/paging compatibility set passed **37 tests in 13.86s**, isolated job `job_919dc9379a2c`, log `test-run-20261106T065041Z-3715162.log`. They traverse three pages, repeat a middle page, preserve status filtering and total counts, account for existing suite rows and clean up only their synthetic records. Ruff, AST and diff checks pass. Root and independent engineering review sign off with no open local blocker. Detailed pre-edit/RED/GREEN evidence is in the existing pagination audit. The corrected head must again receive all six exact-head CI results and automatic review before protected merge and production verification.


### Review completion after the 8ab925f3 CI checkpoint

All six CI workflows completed successfully on 8ab925f3. That checkpoint passed 2543 backend tests, 1014 Chromium cases, 349 WebKit cases, the 11 targeted keyboard checks and three upload-deadline checks; its ROXY E2E completed all seven journeys. These counts belong to that head and are not substituted for verification of the following corrections.

Automatic review then exposed four further interaction cases. Each was reproduced before correction and independently reviewed:

- Notification-only admin edits sent an unchanged overrides blob and revoked target sessions. The API now compares the final persisted value before declaring a privilege change, and the form omits the noneditable field. Five meaningful HTTP failures became 39 passing new/security/recipient compatibility tests; genuine permission, role and active-state changes still revoke sessions.
- A previously complete support-history cache could conceal a gap after more than one refreshed page of new messages. A disjoint latest window now restores its history cursor; ID-based merging and the actual message total close the gap without losing cached messages or drafts. The complete support/admin browser suite passed 54 cases, 27 each in Chromium and mobile WebKit. Both surfaces recover all 400 unique messages from a previously complete 150-message conversation plus 250 new messages.
- Concurrent initial bootstrap enrollment could discard the losing initializer's recipient snapshot. Only an actual absent-policy/INSERT-conflict initializer may now merge its original still-eligible candidates, under a configuration-row lock and while the winning setting remains a nonempty bootstrap import. Explicit owner saves, including unchanged selection and empty choice, take precedence. A real race failed before correction, then 42 regression/compatibility checks and 19 existing bootstrap/security checks passed. Later enrollment after a policy already exists remains owner-managed; bootstrap does not become ongoing routing authority.
- An ambiguously accepted Telegram send could be retried after timeout or worker death. The reply worker now distinguishes a reclaimable unused claim from a durably committed in-flight send. Timeout, uncertain transport outcomes and expired in-flight leases become delivery_unknown, with a readable operator explanation and no automatic resend. Definitive rate-limit rejection retains bounded retry. Seven meaningful failures became a 55-test green checkpoint. A separate held-response test then exposed a stale persisted error after a late successful receipt; a fresh locked finalization read fixes it. The complete final worker/notification/profile set passed 56 tests in 24.60s.

This final full-reply delivery policy supersedes the earlier at-least-once timeout note in this chronological ledger: uncertain support replies now require operator reconciliation. The reply remains available in the durable in-app conversation. A known successful Telegram receipt resolves the state without another send. No exactly-once transport guarantee is claimed. Existing generic notification delivery is outside this narrowly changed worker contract.

All four slices have independent engineering signoff; the concurrent send-state slice was additionally reviewed by the support agent. Ruff, AST/JS syntax and diff checks pass. Their source and audits are frozen for one publication, followed by all six workflows and automatic review on the new exact head. No production message, historical replay, financial exception or schema change has occurred during preparation.
