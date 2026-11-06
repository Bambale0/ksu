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

| Category | Required evidence / status |
| --- | --- |
| Unit/domain | Canonical support behavior, valid/invalid lifecycle, activity, content validation; pending |
| Database/repository | Isolated PostgreSQL ticket/message/notice/outbox atomicity and ordering; pending |
| Authorization | Owner isolation, support permissions, configured recipient selection, deactivation, no private-text leak; pending |
| Migration | N/A unless audit proves schema changes necessary; existing tables reused |
| External contract | Fake Telegram delivery success/forbidden/transient outcomes; no live test send |
| Idempotency/retry/reconciliation | Same reply key one message/outbox; bounded eligible recovery and no generic/full duplication; pending |
| API | Real main/control/customer endpoints and backwards compatibility; pending |
| Frontend/bot E2E | Main/admin conversation open/reply/reopen/paging/refresh/race and existing entity controls; pending; bot routing remains unchanged |
| Smoke/deployability | Source lint/build plus exact-head required CI; production baseline health read-only |
| Observability/audit | Safe correlated delivery state + admin action audit; pending |
| No-hardcode | Existing recipient/config sources, no embedded personal or business values; review pending |
| Performance/query shape | Bounded paging, stable ordering, avoid accidental N+1; pending |
| Rollback/recovery | No destructive changes or historical replay, previous-image rollback; review pending |

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
- Implementation and tests pending.

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
