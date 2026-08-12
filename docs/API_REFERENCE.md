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

## Health and Mini App

```text
GET /health/live
GET /health/ready
GET /mini-app/
```

`/mini-app/` itself is static/public; authenticated actions use Telegram `initData`.

## User/profile

```text
GET /api/v1/me
GET /api/v1/me/transactions
```

**Auth:** Telegram user.

## Generations

```text
GET  /api/v1/generations/models       public
POST /api/v1/generations/quote        public
POST /api/v1/generations              Telegram user
POST /api/v1/uploads/kie              Telegram user
```

Generation creation atomically commits generation + wallet debit + PostgreSQL `generation_outbox`. Redis is only a wake signal; `generation-worker` polls/leases durable outbox work and Kie callbacks/status reconciliation close the provider lifecycle.

## Payment packages

### `GET /api/v1/payments/packages`

**Auth:** public.

Returns server-defined packages and `internal_credit_rub`. Client cannot submit arbitrary amount/credits.

## Payment creation

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

Semantics:

1. validates server package/provider;
2. creates local Payment + `payment_requests` idempotency record;
3. commits local intent before crossing provider boundary;
4. creates provider payment;
5. saves external ID/payment URL or leaves `creation_unknown` if response outcome is uncertain.

Retrying the **same** provider/package with the same key returns the existing local payment. Reusing the key for a different intent returns HTTP 409.

### `GET /api/v1/payments/{payment_id}`

**Auth:** Telegram user owning the payment.

Returns current local status/payment URL. Intended for payment UI polling and recovery after provider redirect.

Important local states include:

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

A dedicated `payment-worker` periodically reconciles nonterminal/unknown payments against provider-authoritative state.

## Provider reconciliation

### Crypto Pay

- creation recovery uses `getInvoices` and local UUID stored in invoice `payload`;
- signed `invoice_paid` webhook completes payment;
- statuses `active/paid/expired` map to local lifecycle;
- Crypto Pay invoice API exposes no merchant refund method, so local admin refund initiation is unsupported.

### T-Bank

- creation: `/v2/Init`;
- missing external ID recovery: `/v2/CheckOrder` by local `OrderId`;
- state recovery: `/v2/GetState`;
- signed notifications are processed through the same state mapper;
- `CONFIRMED` credits once;
- full `REFUNDED/REVERSED` creates an idempotent local reversal;
- `PARTIAL_REFUNDED/PARTIAL_REVERSED` enters `refund_review` unless a provider-authoritative partial amount is available through a supported operation;
- admin full refund uses classic `/v2/Cancel` without `Amount`.

Admin-initiated T-Bank partial refunds are intentionally disabled because an online-cash-register integration can require a refund `Receipt`, which is not currently stored by KSU.

### YooKassa

- creation uses local payment UUID as provider `Idempotence-Key` and metadata;
- unknown creation can safely repeat the same create request/idempotency key;
- webhook is treated as a signal, then payment is re-fetched from YooKassa;
- cumulative provider `refunded_amount` drives partial/full local reversal, including refunds performed outside KSU;
- admin refund uses `/v3/refunds` with UUID `Idempotence-Key`;
- `refund.succeeded` triggers authoritative payment re-fetch before accounting changes.

## Refund/reversal accounting

Provider-confirmed refund/reversal creates immutable `payment_reversals` rows.

For a cumulative refunded share:

```text
reversed_credits = original_credits × refunded_amount / original_payment_amount
```

The final full reversal is clamped to exactly the original credit amount to avoid rounding drift.

Effects are idempotent:

- internal credits are debited once;
- referral rewards are reversed proportionally through immutable `referral_reward_reversals`;
- payment becomes `partially_refunded` or `refunded`.

If purchased credits were already spent, an external refund may produce a negative internal balance. This is deliberate accounting debt. Normal user spending still blocks insufficient balance.

## Admin payment lifecycle

### `POST /api/v1/admin/payments/{payment_id}/reconcile`

**Auth:** privileged admin + financial wallet-adjust permission + fresh MFA step-up.

Queries the configured provider and applies authoritative local state.

### `POST /api/v1/admin/payments/{payment_id}/refund`

**Auth:** same high-risk financial controls.

Body:

```json
{
  "amount": "300.00",
  "request_id": "uuid-v4",
  "reason": "Customer refund"
}
```

Supported initiation:

```text
YooKassa: partial + full
T-Bank:   full original payment only
Crypto Pay: unsupported
```

Every action is admin-audited.

## Promo/referral/support

```text
POST /api/v1/promocodes/redeem       Telegram user
GET  /api/v1/referrals/stats         Telegram user
POST /api/v1/support/tickets         Telegram user
GET  /api/v1/support/tickets         Telegram user
```

## Webhooks

Provider/Telegram webhooks are omitted from production OpenAPI.

```text
POST /webhooks/telegram
POST /webhooks/kie
POST /webhooks/payments/cryptobot
POST /webhooks/payments/tbank
POST /webhooks/payments/yookassa
```

Trust boundaries:

- Telegram: webhook secret header when configured;
- Kie: HMAC signature, then authoritative `recordInfo`;
- Crypto Pay: HMAC over raw body;
- T-Bank: signed `Token`, terminal/payment identity and state checks; successful acknowledgement is plain `OK`;
- YooKassa: incoming event triggers authenticated provider API re-fetch before payment/refund accounting.

## Other admin API groups

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

## Trust rules

Browser/client is never authoritative for:

- generation model/provider slug or cost;
- package amount/credit quantity;
- payment success/refund state;
- provider callback success;
- admin authorization.

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
429 admin rate limit/lock
502 upstream provider operation failure
503 service/config unavailable
```
