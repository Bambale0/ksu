# KSU API reference

**Status:** route/auth reference for the current backend on 2026-08-11.

This is an operational route map, not a generated OpenAPI dump. In non-production environments the backend exposes `/docs` and `/redoc`; in production those UIs are disabled.

## Authentication classes

### Public

No product user identity is required.

Current examples:

- health probes;
- model catalog;
- generation quote;
- credit package catalog;
- provider/Telegram webhook endpoints authenticate by provider-specific mechanisms rather than product user session.

### Telegram user

Authenticated REST calls use:

```http
X-Telegram-Init-Data: <Telegram.WebApp.initData>
```

The backend validates signed Telegram WebApp data using `BOT_TOKEN`, resolves/creates the product user, and rejects inactive users.

Do not send or trust `initDataUnsafe` as authentication.

### Admin

Admin API uses:

```http
Authorization: Bearer <opaque-admin-session-token>
```

Admin login/enrollment/step-up also uses fresh:

```http
X-Telegram-Init-Data: <Telegram.WebApp.initData>
```

Admin sessions are separate from normal product-user authentication. See `ADMIN_SECURITY.md`.

## Health

### `GET /health/live`

Public process liveness probe.

### `GET /health/ready`

Public readiness probe that checks PostgreSQL and Redis connectivity.

## Static Mini App

### `GET /mini-app/`

Serves the bundled generation Mini App (`app/web/mini_app`).

The page itself is static/public; authenticated actions inside it use Telegram `initData`.

## User/profile

### `GET /api/v1/me`

**Auth:** Telegram user.

Returns basic product user identity and current wallet balance. Some legacy response naming still uses `balance_rox`; product terminology is internal credits.

### `GET /api/v1/me/transactions`

**Auth:** Telegram user.

Returns recent wallet ledger transactions.

## Generation

### `GET /api/v1/generations/models`

**Auth:** public.

Returns:

- `schema_version`;
- `internal_credit_rub`;
- server model catalog;
- Kie model mapping metadata;
- billing metadata;
- `ui_schema` for the dynamic Mini App.

The Mini App treats this endpoint as the runtime screen contract.

### `POST /api/v1/generations/quote`

**Auth:** public.

Request shape:

```json
{
  "model_id": "...",
  "prompt": "...",
  "input_url": null,
  "billing_seconds": null,
  "parameters": {}
}
```

Server validates model/required fields/model-specific structural rules and computes price from server configuration.

Response includes credit/RUB unit and total pricing.

### `POST /api/v1/generations`

**Auth:** Telegram user.

Creates a paid generation:

1. validates model request;
2. recalculates price;
3. creates generation DB row;
4. debits wallet idempotently;
5. commits DB transaction;
6. enqueues generation ID in Redis;
7. returns HTTP 202.

Known limitation: DB commit and Redis enqueue are not yet transactional. See `OPERATIONS_RUNBOOK.md`.

## Uploads

### `POST /api/v1/uploads/kie`

**Auth:** Telegram user.

`multipart/form-data` with one `file`.

Allowed media MIME prefixes:

```text
image/
video/
audio/
```

Global size ceiling comes from `KIE_UPLOAD_MAX_BYTES` when size metadata is available. The endpoint streams the media to Kie File Upload and returns the provider URL/metadata.

Model/UI-specific limits can be stricter than the global endpoint ceiling.

## Payment packages

### `GET /api/v1/payments/packages`

**Auth:** public.

Returns server-defined packages and `internal_credit_rub`.

The client cannot define its own payment amount or credit quantity.

## Payment creation

### `POST /api/v1/payments`

**Auth:** Telegram user.

Request:

```json
{
  "provider": "cryptobot | tbank | yookassa",
  "package_id": "starter"
}
```

Response returns local payment ID/status/provider/amount/currency/credits and provider payment URL.

## Promo codes

### `POST /api/v1/promocodes/redeem`

**Auth:** Telegram user.

Request:

```json
{"code":"PROMO"}
```

Promo redemption is validated server-side and wallet credit uses the product ledger.

## Referrals

### `GET /api/v1/referrals/stats`

**Auth:** Telegram user.

Returns referral stats, configured level percentages and referral payload:

```text
ref_<telegram_id>
```

Payment completion accrues configured first/second-line rewards idempotently.

## Support

### `POST /api/v1/support/tickets`

**Auth:** Telegram user.

Creates a support ticket and first user message.

Request:

```json
{
  "topic": "...",
  "message": "..."
}
```

### `GET /api/v1/support/tickets`

**Auth:** Telegram user.

Lists that user's support tickets.

Admin support reply/status operations are under the privileged admin API.

## Webhooks

Webhook routes are intentionally omitted from production OpenAPI (`include_in_schema=False`).

### `POST /webhooks/telegram`

Authentication/integrity:

```http
X-Telegram-Bot-Api-Secret-Token
```

is checked when `TELEGRAM_WEBHOOK_SECRET` is configured.

### `POST /webhooks/kie`

Checks:

```http
X-Webhook-Timestamp
X-Webhook-Signature
```

using Kie HMAC when `KIE_WEBHOOK_HMAC_KEY` is configured, then reconciles through Kie `recordInfo`.

### `POST /webhooks/payments/cryptobot`

Checks `crypto-pay-api-signature` against the raw body. Only `invoice_paid` is treated as a completion event.

### `POST /webhooks/payments/tbank`

Checks token, terminal, local/external IDs and amount. Successful handler response is plain text:

```text
OK
```

### `POST /webhooks/payments/yookassa`

Re-fetches the payment from YooKassa and verifies authoritative metadata/ID/amount/currency/status before completing the local payment.

## Admin API

Prefix:

```text
/api/v1/admin
```

Admin endpoints require separate opaque bearer-session auth and explicit permission dependencies. Sensitive actions additionally require a fresh step-up window.

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

See `ADMIN_SECURITY.md` for current exact auth/session/role behavior and endpoint inventory.

## Pricing and trust boundaries

The browser is never authoritative for:

- model/provider slug;
- generation cost;
- package price;
- credit amount;
- payment success;
- admin authorization;
- Kie callback success.

Server-side components re-evaluate these from model/payment/admin configuration or provider-authoritative data.

## HTTP error conventions

Current API uses FastAPI JSON errors with `detail` for most application validation/auth errors.

Typical classes:

```text
400 invalid application/provider input
401 missing/invalid user/admin authentication
403 authenticated but forbidden / invalid webhook signature
404 resource/package/payment not found
409 state/mismatch/insufficient-state conflict
413 upload too large
415 unsupported upload media type
422 request/model validation error
429 admin rate limit/lock condition
502 upstream provider creation/upload failure
503 required service/configuration unavailable
```

Do not build client logic around exact human error strings when a status/state field can be used instead.

## Versioning note

The current REST prefix is `/api/v1`, while the generation UI contract also carries its own `schema_version` / `ui_schema.version`.

When making incompatible dynamic-form changes, bump/document the UI schema contract instead of silently changing semantics under the same version.
