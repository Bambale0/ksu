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
