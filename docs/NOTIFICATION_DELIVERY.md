# Durable transactional notification delivery

KSU keeps the in-app notification inbox authoritative and uses Telegram as the background delivery channel.

`NotificationService.create()` writes the inbox row and one Telegram outbox row in the caller's existing PostgreSQL transaction. Domain status transitions for generation, payment, partner withdrawal and admin support replies are bridged into the same unit of work. No Telegram network call runs inside provider/payment/admin transactions.

`notification_deliveries` stores channel, purpose, status, attempts, `available_at`, finite `lease_until`, `sent_at`, external message id and the final error. `(notification_id, channel)` is unique. Workers claim work with `FOR UPDATE SKIP LOCKED`, commit the lease before Telegram I/O and reclaim expired leases after a crash.

## Generation completion delivery

Successful and failed generation notifications use the generation UUID as the notification UUID. That gives the delivery worker a stable domain reference and avoids unsafe "latest generation" lookups when several jobs finish concurrently.

The `generations` row mirrors Telegram delivery state for operations/support:

- `telegram_notification_status` — `not_scheduled`, `pending`, `sending`, retry/terminal state or `sent`;
- `telegram_notification_sent_at` — timestamp of the committed successful Telegram delivery;
- `telegram_message_id` — Telegram message id when known.

On provider callback or reconciliation success the normal generation transaction stores the result and queues the notification. The independent notification worker can therefore deliver the result even when the user already closed the Mini App.

For a successful generation the worker tries to send the first generated asset as native Telegram photo/video/audio and adds a compact caption containing status, model, result count and charged ROX. The message can include:

- `📥 Скачать оригинал` — the generated result URL when one exists;
- `🚀 Открыть в ROXY` — a private-chat Web App button to `/mini-app/?route=history&generation=<generation_id>`.

If Telegram cannot fetch/decode the provider media URL under Bot API media limits, delivery degrades to a normal text message with the same result/open buttons instead of losing the completion notification.

Failure notifications contain a short user-facing reason category and explicitly state the ROX refund when the failed generation was charged. Raw provider exception text is not exposed as customer copy.

The generation row plus the unique outbox delivery suppress ordinary duplicate callbacks/re-enqueues. Delivery is still durable **at-least-once**, not mathematically exactly-once: Telegram does not expose an idempotency key for message sends, so a process that sends successfully and crashes before committing `sent` can create one duplicate retry. This crash window must remain documented rather than hidden behind a false exactly-once guarantee.

Immediately before sending, the worker re-reads current profile preferences. `notifications_enabled=false` suppresses Telegram push but never removes the inbox item. Marketing delivery additionally requires `marketing_notifications=true`.

Transient API errors use exponential retry. Telegram `retry_after` is honored. Blocked/inactive recipients become terminal `undeliverable`; max attempts become `failed`.

Run with:

```text
python -m app.workers.notifications
```

or via the normal Compose stack, where `notification-worker` is already a separate service from the API/Mini App process.
