# Retired Telegram support FSM — canonical persistence audit, 2026-11-06

## Evidence and reachability before edits

Review thread PRRT_kwDOT1THts60bxXz identifies a real bypass in app/bot/handlers/support.py. With no direct support URL, the legacy state handler inserts SupportTicket and SupportMessage itself, without SupportConversationService.add_customer_message, activity ordering, operator notifications or the customer message quota. It clears FSM and sends success before DatabaseSessionMiddleware commits, so a later commit failure can leave a false acknowledgement and no retained input state.

Independent source inspection confirms the current production dispatcher includes only admin, admin_extensions, seedance_test, nexus_test and launcher. It does not register support.router; tests/test_app_only_bot_contract.py explicitly preserves that boundary. The retired handler is therefore not the established production incident entry point. Repair its behavior without enabling the router.

The current webhook already calls dispatcher.feed_update(..., redis=request.app.state.redis), and other Telegram handlers receive redis: Redis by dependency injection. Use that existing injection path rather than creating another client or importing the API layer into the bot.

## Approved narrow change

Move the existing per-customer quota invocation into SupportConversationService with the same AbuseProtectionService implementation, configured support_message_rate_limit_per_minute, abuse:support:user:{internal UUID} key, 60-second window and global fail-open/fail-closed switches. Retain the API helper as a thin delegate. Update only the old quota fixture's settings injection to the canonical settings object; keep its behavioral assertions unchanged.

The bot must validate empty text before admission, consume the common quota before support persistence, then create the ticket and call canonical message persistence. Complete the existing UserService profile transaction first, matching the API authentication boundary and avoiding a profile write lock across recipient-policy reads. Commit ticket/message/notification together before clearing FSM or acknowledging success. On quota rejection, retain the waiting state and give a retry response. On persistence/commit error, roll back and propagate without clearing FSM or success acknowledgement. Keep the existing non-text placeholder and default topic behavior.

## RED and verification plan

Use real isolated PostgreSQL, Redis, memory FSM and the aiogram HandlerObject dependency adapter under DatabaseSessionMiddleware, with a synthetic message.answer boundary. Exercise canonical notification delivery records, activity timestamp, durable visibility at success acknowledgement, enqueue failure and commit failure rollback, shared API-to-bot and bot-to-API quota, unavailable Redis fail-closed, and whitespace rejection without quota consumption. No production dispatcher registration, real Telegram message or provider call is involved.

Owned source: app/bot/handlers/support.py, app/services/support.py, app/api/v1/support.py. Tests: new tests/test_support_legacy_fsm.py and fixture-only configuration adaptation in tests/test_support_rate_limit.py. Existing support, rate-limit and retired-router contract suites provide compatibility coverage. No schema, production mutation, commit or push is included.

## Approved message receipt follow-up before implementation

The webhook currently has no global update deduplication. Moving the commit before FSM clearing makes a post-commit Redis-clear failure retryable; without a durable receipt that same Telegram message could create a second ticket and operator notice. Root approved a handler-local deterministic SupportTicket UUID derived from a fixed namespace plus bot/chat/message identity, using the existing primary key rather than a schema or global webhook change.

An existing same-owner receipt is acknowledged without spending new quota or appending messages/notices, including when the ticket has since closed. For first delivery, consume the existing admission policy, perform INSERT ON CONFLICT DO NOTHING and let only the insertion winner call canonical message persistence. A concurrent loser reloads the committed winning receipt. Two simultaneous first attempts can spend two quota admissions; this is not an exactly-once quota contract. Sequential replay must spend none even when the allowance is exhausted.

Add real concurrent absent-read barriers, post-commit FSM-clear and acknowledgement failures followed by same-message replay, and closed-ticket replay. Keep the receipt ownership check mandatory and do not reopen or bump activity for an already persisted Telegram message.

## RED evidence before product changes

All 13 focused cases failed on the original handler in 9.44s: job_f8f69246b0b1, test-run-20261106T085032Z-3886389.log. The failures showed persisted ticket/message without any operator notice/delivery, success acknowledgement before any committed support row, lost FSM on commit failure, bypassed API/bot quota, no fail-closed admission, duplicate tickets for the same concurrent message, and loss of the conversation when clear/ack failed before the old middleware commit. No fixture or signature failure masked those behaviors.

The rate-limit fixture now targets the canonical settings object. An AST comparison verified that every existing Assert node in tests/test_support_rate_limit.py is unchanged.

## Final evidence and source freeze

| Check | Result | Evidence |
| --- | --- | --- |
| Original handler behavior RED | 13 failed in 9.44s | job_f8f69246b0b1; test-run-20261106T085032Z-3886389.log |
| New handler cases plus existing quota/delivery/profile/router compatibility | 53 passed in 22.26s | job_2ff343f2a8b8; test-run-20261106T085231Z-3889600.log |
| Existing quota assertions | Every Assert AST node unchanged | Compared before/after fixture configuration relocation |
| Ruff, AST and scoped diff check | All passed for five Python files | Exit 0 |

The combined result includes 13 new handler cases, 11 existing quota cases, 20 support-delivery regressions, 5 profile/support cases and 4 Mini-App-only dispatcher contract checks. New tests exercise the actual handler via aiogram signature-based DI and DatabaseSessionMiddleware against isolated PostgreSQL/Redis, with memory FSM and a mocked answer boundary. No live Telegram call was made.

Verified behavior:
- Canonical message insertion updates activity and queues exactly one notice/delivery for the explicitly selected operator.
- Support rows are committed before success is observed; enqueue or commit failure leaves zero durable ticket/message/notice/delivery rows and retains waiting FSM/topic.
- API and bot use the same configured quota and internal-user key. Limit/backend rejection retains FSM with a retry response; blank text consumes no quota.
- A bot/chat/message receipt survives post-commit clear or acknowledgement failure. Sequential replay with an exhausted quota creates no new support row or notification and spends no new admission.
- Concurrent absent reads and duplicate delivery converge on one primary-key insertion and one message/notice. Concurrent first attempts may consume separate admission attempts as documented; exactly-once quota is not claimed.
- Replaying an already closed ticket neither reopens it nor changes its activity.
- The profile/auth transaction completes before support work; ticket/message/notice then commit atomically. The rollback assertions concern support rows, not deletion of previously registered users.
- The retired production router remains unregistered. This is a dormant-path correctness repair, not a newly established explanation for the original production incident.

Root independently read all three product diffs, the fixture change and the entire new test file, personally obtained GREEN53, and signed off quota/DI, transaction order, rollback, receipt ownership and concurrent insertion behavior. Source and tests are frozen; root owns the combined publication and exact-head CI/release.

Exact owned paths:
- app/bot/handlers/support.py
- app/services/support.py
- app/api/v1/support.py
- tests/test_support_legacy_fsm.py (new)
- tests/test_support_rate_limit.py (fixture-only configuration relocation; behavioral assertions unchanged)
- docs/agents/EXECUTION/support-legacy-fsm-20261106.md (new)

No schema migration, production mutation, router activation, live message, historical replay, commit or push was performed. Prepared postdeploy baseline, image/health/static/recipient/quota/outbox checks, aggregate MFA/payment checks and bounded read-only Telegram/provider probes are retained and have not been run.
