# Durable transactional notification delivery

KSU user notifications have two separate responsibilities:

1. the in-app notification inbox is the authoritative user-visible record;
2. Telegram push is a best-effort delivery channel for transactional events.

The Telegram Bot API call is never executed inside payment/provider/admin business transactions.

## Transaction boundary

`NotificationService.create()` writes both:

- `notifications` inbox row;
- one `notification_deliveries` Telegram outbox row.

Both belong to the caller's existing PostgreSQL transaction. If the business transaction rolls back, neither the inbox item nor delivery job survives.

Existing domain status changes are bridged at SQLAlchemy `before_flush` so the notification is created in the same unit of work as the authoritative transition. Current transactional producers include:

- generation `succeeded` / `failed`;
- payment `succeeded` and reversal-like payment status transitions;
- partner withdrawal `processing` / `paid` / `rejected` / `canceled`;
- new admin support reply;
- successful promo redemption through the explicit `NotificationService` path.

The bridge never sends network traffic and never changes the domain transition.

## Delivery outbox

Migration `0010_notification_delivery` adds one row per notification/channel with:

```text
id
notification_id
channel              telegram
purpose              transactional | marketing
status               pending | sending | retry | sent | suppressed | undeliverable | failed
attempts
available_at
lease_until
sent_at
external_message_id
last_error
created_at / updated_at
```

`(notification_id, channel)` is unique, preventing intentional duplicate enqueue for the same inbox notification.

Workers claim rows with PostgreSQL `FOR UPDATE SKIP LOCKED`, write a finite lease and commit before contacting Telegram. Expired `sending` leases become claimable again after a worker crash.

## Delivery guarantees

The worker provides durable **at-least-once** processing, not a false exactly-once guarantee.

Telegram Bot API does not expose an idempotency key for `sendMessage`. If a process successfully sends a message and crashes before committing `sent`, the expired lease may cause one duplicate retry. The database prevents normal duplicate jobs, but it cannot make an external non-idempotent API exactly-once.

This trade-off prefers not losing transactional notifications.

## User preferences

The inbox row is kept regardless of push preference.

Immediately before sending, the worker reads current `UserPreference`:

- `notifications_enabled=false` → delivery becomes `suppressed`;
- marketing delivery additionally requires `marketing_notifications=true`;
- inactive/missing user → `undeliverable`.

This means changing preferences after a notification is enqueued but before it is delivered is respected.

This epic does **not** add marketing broadcast. Marketing requires a separate permission, consent/audience, rate-limit and campaign lifecycle and must not reuse transactional semantics implicitly.

## Retry policy

Configurable settings:

```text
NOTIFICATION_WORKER_POLL_SECONDS=3
NOTIFICATION_DELIVERY_LEASE_SECONDS=90
NOTIFICATION_DELIVERY_MAX_ATTEMPTS=8
NOTIFICATION_RETRY_BASE_SECONDS=5
NOTIFICATION_RETRY_MAX_SECONDS=900
NOTIFICATION_DELIVERY_BATCH_SIZE=50
```

Transient Telegram/API errors use exponential backoff. Telegram `retry_after` is honored when supplied. `TelegramForbiddenError` is terminal `undeliverable`. Once max attempts are reached, the row becomes `failed` and keeps the final error for operations/debugging.

Messages are sent as plain text; notification title/body are not interpreted as HTML.

## Worker

Run directly:

```text
python -m app.workers.notifications
```

or add the provided Compose override to the normal stack:

```text
docker compose -f docker-compose.yml -f docker-compose.notifications.yml up -d notification-worker
```

The worker requires `BOT_TOKEN` plus the normal database configuration.

## Tests

`tests/test_notification_delivery.py` covers:

- unique enqueue per notification/channel;
- payment status transition creating inbox + outbox atomically;
- admin support reply producer;
- push suppression while retaining inbox state;
- successful Telegram delivery / external message id;
- retry terminal state after configured attempts.
