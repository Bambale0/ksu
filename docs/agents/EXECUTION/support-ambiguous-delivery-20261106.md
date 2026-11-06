# Support delivery ambiguity audit — 2026-11-06

## Pre-edit evidence and scope

Automatic review of 8ab925f3 identified that an outbound Telegram timeout is retried although Telegram may already have accepted the reply. Source inspection also found the same uncertainty at the expired sending-lease boundary. Telegram sendMessage provides no application idempotency key and the worker has no authoritative reconciliation receipt after a lost response. AGENTS requires a duplicate-prevention strategy for mutating external operations.

The existing SupportOutbox status is String(24), without an enum/check constraint; admin message serialization already exposes it directly. No schema migration is needed. Customer replies remain durably visible in the support conversation independently of Telegram delivery.

Regression plan: the real worker with an isolated fake transport records acceptance before timeout/network/server/unknown failure; expired in-flight work must not send again, while a leased-but-not-started row remains safely reclaimable. Explicit Telegram rate-limit rejection must still retry. Simultaneous workers must start only one transport call. All fixtures use the isolated database and synthetic identities, and cleanup only their own rows.

Prepared design: distinguish claimed (leased, transport not started) from sending (durable intent committed before the external call). Count actual attempts at sending start. Timeout or otherwise ambiguous outcomes become delivery_unknown and are excluded from automatic delivery and contact recovery. Expired sending intent also becomes unknown; expired claimed work is safely reclaimed. Definitive rejection retains existing retry/terminal behavior. The admin UI explains unknown delivery and asks the operator to confirm receipt before an explicit repeat. This trades automatic recovery of uncertain outcomes for duplicate prevention; it does not claim exactly-once transport or invent a successful delivery receipt.

Root owns admin_delivery.py, workers/admin_support.py, the new regression module and the two old worker-fixture adaptations required by the new claim boundary. The UI agent owns status labels. No production messages, replay, database writes or credential changes are performed during verification.

## Reproduction

The unchanged worker produced seven failing regressions and two passing controls in 8.16s (isolated log test-run-20261106T071558Z-3746937.log). Timeout, lost network response, server failure and response-decode uncertainty were all scheduled for retry. The real worker deadline also retried. A canceled accepted send was actually sent a second time after lease expiry. The unused-claim case showed the missing distinction between claimed and sending. Concurrent workers and definitive 429 retry controls passed before the fix.

## Late-receipt review follow-up

The first corrected worker and complete relevant compatibility set passed 55 tests in 23.76s (log test-run-20261106T071844Z-3753591.log). Root review found a concrete stale ORM risk: while the external call awaits a response, another worker can mark an expired sending intent unknown; the original session still sees last_error=None, so assigning None on success may not clear the newer persisted ambiguity reason. Add a held-call/expired-lease/late-receipt regression before correcting the finalization read. A known successful message receipt should resolve the unknown state without another external send.

The late-receipt case failed exactly as predicted: status=sent and a known external message ID, but last_error still contained send_lease_expired (one failure in 4.81s, log test-run-20261106T072047Z-3758965.log). Finalization now refreshes and locks the persisted row before applying a known successful receipt, so a real success clears the intervening ambiguity reason. Error outcomes already assign explicit status/error values and retain their existing classification.

## Final verification and freeze

The late-receipt regression is now green together with the complete delivery/notification/profile compatibility set: **56 passed in 24.60s**, job job_367937acc19a, log test-run-20261106T072204Z-3761225.log. The ten new cases cover accepted-but-unknown transport outcomes, the actual finite deadline, canceled send/expired lease, reclaiming an unused claim, concurrent workers, explicit rate-limit retry and a late authoritative receipt. The two pre-existing worker fixtures now represent a committed claimed lease rather than an already-started send; their success/retry/call-count/API assertions are unchanged. Concurrent-state review by the support agent found no blocker. No real Telegram request or production replay was performed. Exactly-once delivery is not claimed: uncertain outcomes require operator reconciliation, while a known successful receipt resolves the persisted state without another external call.
