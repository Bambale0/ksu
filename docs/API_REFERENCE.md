# KSU API reference

**Status:** route/auth reference for the current backend on 2026-08-12.

This is an operational route map, not a generated OpenAPI dump. In non-production environments the backend exposes `/docs` and `/redoc`; in production those UIs are disabled.

## Authentication classes

### Public

No product user identity is required. Current examples include health probes, model catalog, generation quote and credit package catalog. Provider/Telegram webhook endpoints authenticate by provider-specific mechanisms rather than product-user sessions.

### Telegram user

Authenticated REST calls use:

```http
X-Telegram-Init-Data: <Telegram.WebApp.initData>
```

The backend validates signed Telegram WebApp data using `BOT_TOKEN`, resolves/creates the product user, and rejects inactive users. Do not trust `initDataUnsafe` as authentication.

### Admin

Admin API uses:

```http
Authorization: Bearer <opaque-admin-session-token>
```

Admin login/enrollment/step-up also uses fresh `X-Telegram-Init-Data`. Admin sessions are separate from normal product-user authentication. See `ADMIN_SECURITY.md`.

## Health

### `GET /health/live`

Public process liveness probe.

### `GET /health/ready`

Public readiness probe that checks PostgreSQL and Redis connectivity.

## Static Mini App

### `GET /mini-app/`

Serves the bundled generation Mini App (`app/web/mini_app`). The page is static/public; authenticated actions inside it use Telegram `initData`.

## User/profile

### `GET /api/v1/me`

**Auth:** Telegram user. Returns basic product user identity and current wallet balance. Some legacy response naming still uses `balance_rox`; product terminology is internal credits.

### `GET /api/v1/me/transactions`

**Auth:** Telegram user. Returns recent wallet ledger transactions.

## Generation

### `GET /api/v1/generations/models`

**Auth:** public. Returns `schema_version`, `internal_credit_rub`, server model catalog, Kie mapping/billing metadata and `ui_schema`. The Mini App treats this endpoint as the runtime screen contract.

### `POST /api/v1/generations/quote`

**Auth:** public.

```json
{
  "model_id": "...",
  "prompt": "...",
  "input_url": null,
  "billing_seconds": null,
  "parameters": {}
}
```

The server validates model fields/rules and calculates credit/RUB pricing from server configuration.

### `POST /api/v1/generations`

**Auth:** Telegram user.

Creates a paid generation with durable local delivery semantics:

1. validates the model request and recalculates price;
2. creates the generation row;
3. debits the wallet idempotently;
4. creates one `generation_outbox` row;
5. commits generation + wallet + outbox atomically in PostgreSQL;
6. emits a best-effort Redis wake signal;
7. returns HTTP 202.

Redis is not authoritative generation state. If the wake-up is lost or Redis is unavailable after the PostgreSQL commit, `generation-worker` still polls and claims the outbox row.

The worker uses leased PostgreSQL claims with `FOR UPDATE SKIP LOCKED`. Expired processing leases are reclaimable, so a worker crash before provider submission does not lose the job.

The Kie callback URL contains the local `generation_id`. If Kie accepted `createTask` but the worker died before persisting the returned provider `taskId`, a signed Kie callback can bind that task back to the original local generation. An uncertain `submitting` generation is not blindly resubmitted; if it cannot be recovered before the configured timeout, the user is refunded idempotently.

Stale `generating` rows with a Kie task ID are periodically reconciled through `/api/v1/jobs/recordInfo` as a callback fallback.

## Uploads

### `POST /api/v1/uploads/kie`

**Auth:** Telegram user. `multipart/form-data` with one `file`.

Allowed MIME prefixes:

```text
image/
video/
audio/
```

The global size ceiling comes from `KIE_UPLOAD_MAX_BYTES` when size metadata is available. Model/UI-specific limits can be stricter.

## Payment packages

### `GET /api/v1/payments/packages`

**Auth:** public. Returns server-defined packages and `internal_credit_rub`. The client cannot define payment amount or credit quantity.

## Payment creation

### `POST /api/v1/payments`

**Auth:** Telegram user.

```json
{
  "provider": "cryptobot | tbank | yookassa",
  "package_id": "starter"
}
```

Returns local payment ID/status/provider/amount/currency/credits and provider payment URL.

## Promo codes

### `POST /api/v1/promocodes/redeem`

**Auth:** Telegram user.

```json
{"code":"PROMO"}
```

Promo redemption is validated server-side and wallet credit uses the product ledger.

## Referrals

### `GET /api/v1/referrals/stats`

**Auth:** Telegram user. Returns referral stats, configured level percentages and `ref_<telegram_id>` payload. Payment completion accrues configured first/second-line rewards idempotently.

## Support

### `POST /api/v1/support/tickets`

**Auth:** Telegram user. Creates a support ticket and its first user message.

### `GET /api/v1/support/tickets`

**Auth:** Telegram user. Lists that user's support tickets. Admin reply/status operations are under the privileged admin API.

## Webhooks

Webhook routes are omitted from production OpenAPI (`include_in_schema=False`).

### `POST /webhooks/telegram`

Checks `X-Telegram-Bot-Api-Secret-Token` when `TELEGRAM_WEBHOOK_SECRET` is configured.

### `POST /webhooks/kie`

Checks `X-Webhook-Timestamp` and `X-Webhook-Signature` using Kie HMAC when configured, can recover the local generation from the callback query `generation_id`, then reconciles provider state through Kie `recordInfo`.

### `POST /webhooks/payments/cryptobot`

Checks `crypto-pay-api-signature` against the raw body. Only `invoice_paid` is treated as completion.

### `POST /webhooks/payments/tbank`

Checks token, terminal, local/external IDs and amount. Successful handling returns plain-text `OK`.

### `POST /webhooks/payments/yookassa`

Re-fetches the payment from YooKassa and verifies authoritative metadata/ID/amount/currency/status before completing the local payment.

## Admin API

Prefix: `/api/v1/admin`.

Admin endpoints require separate opaque bearer-session authentication and explicit permission dependencies. Sensitive actions additionally require a fresh step-up window.

Main groups:

```text
/admin/auth/*
/admin/dashboard
/admin/users/*
/admin/generations/*
/admin/payments
/admin/support/*
/admin/withdrawals/*
/admin/promocodes/*
/admin/referrals/*
/admin/roles
/admin/admins/*
/admin/audit
/admin/security/*
```

See `ADMIN_SECURITY.md` for exact auth/session/role behavior.

## Pricing and trust boundaries

The browser is never authoritative for model/provider slug, generation cost, package price, credit amount, payment success, admin authorization or Kie callback success. Server-side components re-evaluate these from configuration or provider-authoritative data.

## HTTP error conventions

Typical classes:

```text
400 invalid application/provider input
401 missing/invalid user/admin authentication
403 authenticated but forbidden / invalid webhook signature
404 resource/package/payment not found
409 state/mismatch conflict
413 upload too large
415 unsupported upload media type
422 request/model validation error
429 admin rate limit/lock condition
502 upstream provider creation/upload failure
503 required service/configuration unavailable
```

Do not build client logic around exact human error strings when a status/state field is available.

## Versioning note

REST uses `/api/v1`; generation UI also carries `schema_version` / `ui_schema.version`. Incompatible dynamic-form changes should bump/document the UI schema contract instead of silently changing semantics.
