# Telegram generation UUID and waiting status

Ordinary image/video requests admitted by `GenerationService.create_many` (including its single-request wrapper) enqueue a Telegram progress notification in the same database transaction as the generation and wallet debit. Customer admission remains Mini-App-only; this feature does not register the retired customer text menus or modify the separate admin test-task protocol.

## Customer behaviour

One Telegram message shows the full local `Generation.id`, a copy-UUID button, the model title, observed stage and elapsed time. An indeterminate spinner changes on refresh; there are no invented percentages or provider completion estimates. States are queued, sending, generating, checking an uncertain result, and terminal success/failure. The full UUID also appears in the separate final result/error message.

`_submission_uncertain` is rendered as checking the result, not a promise that a provider polling endpoint exists. This presentation does not retry a generation, switch providers, change billing, or shorten the existing recovery deadlines. Final media is still sent by the existing durable result-delivery path.

## Configuration and recipient policy

- `TELEGRAM_GENERATION_PROGRESS_ENABLED=true` enables enqueueing and refreshes.
- `TELEGRAM_GENERATION_PROGRESS_INTERVAL_SECONDS=15` sets the per-task refresh cadence (5..300 seconds). Queue load and Telegram `Retry-After` may delay a refresh.
- Existing active-user and notification-preference checks apply. The bot cannot message an unreachable Telegram chat; the usual reachability-recovery path remains in charge.

Apply configuration consistently to API and notification worker. Disabling stops new enqueueing; the updated worker changes existing anchors to a neutral status and completes their progress delivery. Do not roll back the worker code while active progress rows remain: first disable, allow the updated worker to drain due rows, then revert if needed.

## Persistence and safety

The progress notification uses `uuid5(generation.id, "generation_progress")`, making repeated enqueueing idempotent. Its `NotificationDelivery.external_message_id` stores the Telegram anchor, while existing row locks and leases serialize workers. A normal refresh defers without consuming the error retry budget. `Retry-After` is honored; unchanged edits count as a successful tick. Deleted/uneditable anchors stop refreshing instead of creating replacement spam. Progress rows are read/internal and excluded from the customer notification API.

The worker validates notification/generation ownership and never mutates generation/provider parameters. The progress `sent` status is independent of `Generation.telegram_notification_status`, so a completed status message cannot suppress final media. A concurrent provider completion may race with one already-started edit; the following tick observes the terminal state and finalizes the anchor. Progress does not include raw prompts, media URLs, provider request IDs or exceptions.

As with ordinary Telegram outbox sends, a process crash after Telegram accepts the first send but before its ID is committed is an ambiguous at-least-once window. Telegram offers no idempotency key for `sendMessage`; do not claim absolute exactly-once delivery. Once the ID is persisted, normal restart/lease recovery edits the same anchor. No synthetic production generation or customer message is needed for regression verification.

## Verification

`tests/test_generation_progress_notifications.py` exercises the actual notification worker with a fake Telegram boundary and isolated PostgreSQL: UUID/copy, message reuse across sessions, honest uncertain state, repeated ticks, 429, deleted/unchanged messages, recipient policy, concurrent workers, provider completion during an edit, admission transaction/idempotency, API filtering, escaping/time and disablement. Existing notification/media, generation, pricing, authorization and full backend CI remain mandatory. Exact-head CI and deployed user-journey evidence are separate release claims.
