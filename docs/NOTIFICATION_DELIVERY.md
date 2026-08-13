# Durable transactional notification delivery

KSU keeps the in-app notification inbox authoritative and uses Telegram only as a delivery channel.

`NotificationService.create()` writes the inbox row and one Telegram outbox row in the caller's existing PostgreSQL transaction. Domain status transitions for generation, payment, partner withdrawal and admin support replies are bridged into the same unit of work. No Telegram network call runs inside provider/payment/admin transactions.

`notification_deliveries` stores channel, purpose, status, attempts, `available_at`, finite `lease_until`, `sent_at`, external message id and the final error. `(notification_id, channel)` is unique. Workers claim work with `FOR UPDATE SKIP LOCKED`, commit the lease before Telegram I/O and reclaim expired leases after a crash.

Delivery is durable **at-least-once**, not exactly-once: Telegram `sendMessage` has no idempotency key, so a process that sends successfully and crashes before committing `sent` can create one duplicate retry.

Immediately before sending, the worker re-reads current profile preferences. `notifications_enabled=false` suppresses Telegram push but never removes the inbox item. Marketing delivery additionally requires `marketing_notifications=true`; marketing campaigns are intentionally a separate future contour.

Transient API errors use exponential retry. Telegram `retry_after` is honored. Blocked/inactive recipients become terminal `undeliverable`; max attempts become `failed`.

Run with:

```text
python -m app.workers.notifications
```

or:

```text
docker compose -f docker-compose.yml -f docker-compose.notifications.yml up -d notification-worker
```
