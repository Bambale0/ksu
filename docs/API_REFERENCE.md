# KSU API reference

**Status:** current backend on 2026-08-12.

This is an operational route/auth map. `/docs` and `/redoc` are available only outside production.

## Authentication classes

### Public

No product identity required. Examples: health probes, generation model catalog/quote and credit package catalog.

### Telegram user

```http
X-Telegram-Init-Data: <Telegram.WebApp.initData>
```

The backend validates signed Telegram WebApp data with `BOT_TOKEN`, resolves the user and rejects inactive users. `initDataUnsafe` is never an authentication source.

### Admin

```http
Authorization: Bearer <opaque-admin-session-token>
```

Admin login/enrollment/step-up also requires fresh Telegram `initData`. Sensitive financial mutations require fresh MFA step-up.

## Resource-consumption response contract

Expensive user/provider operations are protected by distributed Redis limits plus database admission checks.

Quota/circuit response:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 27
Content-Type: application/json

{
  "detail": "Generation rate limit exceeded",
  "code": "resource_limit_exceeded",
  "retry_after": 27
}
```

If `ABUSE_FAIL_CLOSED=true` and Redis cannot verify an expensive operation:

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 5

{
  "detail": "Resource protection store is unavailable",
  "code": "protection_backend_unavailable",
  "retry_after": 5
}
```

Clients should respect `Retry-After`; do not immediately retry in a tight loop.

## Health and Mini App

```text
GET /health/live
GET /health/ready
GET /health/operational
GET /mini-app/
```

`/health/operational` verifies generation, media, prompt-tool and payment worker heartbeats. `/mini-app/` itself is static/public; authenticated actions use Telegram `initData`.

## User/profile

```text
GET /api/v1/me
GET /api/v1/me/transactions
```

**Auth:** Telegram user.

## Generations

```text
GET    /api/v1/generations/models                   public
POST   /api/v1/generations/quote                    public
POST   /api/v1/generations                          Telegram user
GET    /api/v1/generations                          Telegram user
GET    /api/v1/generations/{generation_id}          Telegram user
GET    /api/v1/generations/{generation_id}/recreate Telegram user
DELETE /api/v1/generations/{generation_id}/history Telegram user
POST   /api/v1/generations/{generation_id}/history/restore Telegram user
POST   /api/v1/uploads/kie                          Telegram user
```

Generation creation atomically commits generation + wallet debit + PostgreSQL transactional outbox. Redis wake-up is not durable generation state.

Before any debit, `POST /api/v1/generations` enforces:

- per-user generation request rate;
- configured maximum active generations (`queued/retry/submitting/generating`);
- optional UTC daily credit-spend ceiling.

The active/daily admission decision locks the product user row until the generation/wallet/outbox transaction commits, preventing concurrent requests from racing through the active-task cap.

`generation-worker` additionally applies a global Kie submission rate and Kie availability circuit breaker. When throttled/open, the outbox item is released with delay instead of being marked failed/refunded.

### Generation result storage

Kie result URLs are temporary provider sources. On successful Kie completion, the same PostgreSQL transaction that marks the generation succeeded also creates one `MediaAsset` + durable `MediaIngestJob` per provider result URL.

`media-worker` copies these results into the configured private S3-compatible bucket. Generation detail/history then prefer short-lived product-owned presigned URLs. Until an owned asset is ready, the provider URL remains a compatibility fallback.

Generation detail/history adds:

```json
{
  "result_storage": "owned | provider",
  "media": [
    {
      "id": "uuid",
      "url": "short-lived-presigned-view-url",
      "download_url": "/api/v1/media/<uuid>/download",
      "content_type": "image/png",
      "size_bytes": 12345,
      "ordinal": 0
    }
  ]
}
```

Presigned URLs are temporary capabilities and must not be stored as permanent media identifiers.

## Media assets

```text
GET /api/v1/media/{asset_id}
GET /api/v1/media/{asset_id}/download
```

**Auth:** Telegram user owning the asset.

`GET /api/v1/media/{asset_id}` returns non-secret metadata and readiness state. Foreign/missing assets return 404 to avoid cross-user enumeration.

`GET /api/v1/media/{asset_id}/download` requires a ready owned asset and returns a redirect to a short-lived presigned S3 `GetObject` URL with attachment `Content-Disposition`. A pending/failed asset returns 409; missing storage configuration returns 503.

The underlying bucket stays private; this route does not proxy the object bytes through FastAPI.

## Uploads

### `POST /api/v1/uploads/kie`

**Auth:** Telegram user.

In addition to MIME allowlist and `KIE_UPLOAD_MAX_BYTES`, the endpoint enforces:

- uploads per user/minute;
- uploaded bytes per user/day.

If Starlette does not expose multipart size metadata, the server measures the already-spooled file so chunked clients do not bypass byte accounting. Production reverse proxy must still enforce its own request-body ceiling before application parsing.

## Wallet and payments

The Wallet Mini App treats backend package/payment state as authoritative. The client never submits arbitrary RUB or credit amounts and never marks a payment successful locally.

### `GET /api/v1/payments/packages`

**Auth:** public.

Returns the server-defined package catalog and `internal_credit_rub` conversion rate. Example shape:

```json
{
  "internal_credit_rub": "10",
  "packages": {
    "starter": {
      "amount": "300.00",
      "currency": "RUB",
      "credits": "30.00",
      "rox": "30.00"
    }
  }
}
```

`amount` and `credits` are output-only for the user client. Checkout sends only the selected package identifier and provider.

### `GET /api/v1/payments?limit=20`

**Auth:** Telegram user.

Returns the authenticated user's newest payments only, newest first. This is also the Wallet recovery source after a Mini App reload/reopen: the client finds the newest nonterminal payment from server state instead of persisting financial truth in browser storage.

Each item includes:

```text
id
status
provider
package_id
amount
currency
credits / rox
payment_url
created_at
updated_at
```

Foreign-user payments are never returned.

### `POST /api/v1/payments`

**Auth:** Telegram user.

Required headers:

```http
X-Telegram-Init-Data: <signed Telegram data>
Idempotency-Key: <UUID>
Content-Type: application/json
```

Body:

```json
{
  "provider": "cryptobot | tbank | yookassa",
  "package_id": "starter"
}
```

Before external invoice creation the endpoint also applies a per-user payment-creation rate limit. Payment idempotency remains authoritative: retrying the same intent with the same UUID returns the same local payment; reusing the key for a different intent returns 409.

The client should keep one UUID for one package/provider checkout attempt across transient retries. A network/provider uncertainty is not a reason to generate another invoice.

### `GET /api/v1/payments/{payment_id}`

**Auth:** Telegram user owning the payment. Returns current local payment state/payment URL.

Important states:

```text
creating
creation_unknown
pending
succeeded
partially_refunded
refunded
refund_review
canceled
expired
failed
```

`payment-worker` periodically reconciles nonterminal/unknown provider state. Wallet polling is only a presentation refresh; it does not perform settlement logic itself.

### Mini App checkout behavior

Wallet uses the current Telegram Mini Apps link APIs when available:

- Telegram-hosted (`t.me` / `telegram.me`) provider links: `openTelegramLink`;
- normal HTTPS provider links: `openLink`;
- ordinary browser fallback: new secure browser tab/window.

On Mini App `activated`, Wallet refreshes payment history and current server status. After `succeeded`, it refreshes `/api/v1/me` and `/api/v1/me/transactions` before showing the new balance.

If payment creation returns an upstream `502`, the client preserves the current idempotency intent and immediately reloads `GET /api/v1/payments`; it does not create a second invoice. `429` responses must honor `Retry-After`.

## Provider reconciliation

### Crypto Pay

- creation recovery via `getInvoices` and local UUID stored in `payload`;
- signed `invoice_paid` webhook completes payment;
- no merchant invoice-refund operation is invented.

### T-Bank

- `/v2/Init`, `/v2/CheckOrder`, `/v2/GetState`;
- signed notification state mapping;
- full `REFUNDED/REVERSED` creates idempotent local reversal;
- partial reversal without safe authoritative amount enters `refund_review`;
- admin full refund uses `/v2/Cancel` without `Amount`.

### YooKassa

- create uses local payment UUID as provider `Idempotence-Key` and metadata;
- webhook is a signal, then payment is re-fetched;
- cumulative provider `refunded_amount` drives partial/full local reversal;
- admin refund uses `/v3/refunds` with UUID `Idempotence-Key`.

## Refund/reversal accounting

Provider-confirmed reversal creates immutable `payment_reversals`. Credits and referral rewards are reversed proportionally and idempotently. A refund may produce negative product-credit balance if purchased credits were already spent; normal user spending still rejects insufficient balance.

## Admin payment lifecycle

```text
POST /api/v1/admin/payments/{payment_id}/reconcile
POST /api/v1/admin/payments/{payment_id}/refund
```

**Auth:** privileged financial permission + fresh MFA step-up.

Refund initiation matrix:

```text
YooKassa: partial + full
T-Bank:   full original payment only
Crypto Pay: unsupported
```

## Promo/referral/support

```text
POST /api/v1/promocodes/redeem       Telegram user
GET  /api/v1/referrals/stats         Telegram user
POST /api/v1/support/tickets         Telegram user
GET  /api/v1/support/tickets         Telegram user
```

## Webhooks

```text
POST /webhooks/telegram
POST /webhooks/kie
POST /webhooks/payments/cryptobot
POST /webhooks/payments/tbank
POST /webhooks/payments/yookassa
```

Provider/Telegram webhook trust boundaries remain signature/secret/provider-authoritative checks; user-facing resource-limit counters are not substitutes for webhook authenticity.

## Admin API groups

```text
/api/v1/admin/auth/*
/api/v1/admin/dashboard
/api/v1/admin/users/*
/api/v1/admin/generations/*
/api/v1/admin/payments*
/api/v1/admin/support/*
/api/v1/admin/withdrawals/*
/api/v1/admin/promocodes/*
/api/v1/admin/referrals/*
/api/v1/admin/roles
/api/v1/admin/admins/*
/api/v1/admin/audit
/api/v1/admin/security/*
```

See `ADMIN_SECURITY.md`.

## Common HTTP classes

```text
400 invalid request/idempotency header
401 invalid user/admin authentication
403 forbidden or invalid webhook signature
404 resource not found
409 idempotency/state/unsupported-operation conflict
413 upload too large
415 unsupported media type
422 model/refund validation error
429 resource quota/circuit/admin rate limit
502 upstream provider operation failure
503 service/config/protection-store unavailable
```

For 429/anti-abuse 503, read and honor `Retry-After`.
