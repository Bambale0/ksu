# KSU API reference

**Status:** current backend contract on **2026-08-27**.

This is the maintained operational route/auth map. `/docs` and `/redoc` are disabled in production.

## Authentication classes

### Public

No product identity required. Examples: health probes and read-only model/package metadata where the route is explicitly public.

### Telegram user

```http
X-Telegram-Init-Data: <Telegram.WebApp.initData>
```

The backend validates signed Telegram WebApp data with `BOT_TOKEN`, resolves the product user and rejects inactive users. `initDataUnsafe` is presentation data only and is never an authentication source.

Telegram start/deep-link payload may additionally arrive through the supported start-param header/launch contract; payload never substitutes for signed user authentication.

### Privileged Admin Console

```http
Authorization: Bearer <opaque-admin-session-token>
```

Admin login/enrollment/step-up starts from fresh signed Telegram data and then uses the separate server-created admin session. Sensitive operations require the appropriate permission plus confirmation/fresh MFA step-up.

### Inline Trend admin

`/api/v1/trends/manage*` deliberately uses the customer Mini App Telegram-auth channel, then separately resolves an active linked `AdminAccount` and authorizes `social.moderate` on the server. `me.is_admin` only controls UI visibility.

## Health / release

```text
GET /health/live
GET /health/ready
GET /health/operational
GET /metrics
GET /mini-app/
GET /mini-app/release.json
GET /admin-app/
```

Production deployment validates operational health and requires `/mini-app/release.json` to match the exact GitHub deploy SHA.

## User/profile/history/references

```text
GET    /api/v1/me
GET    /api/v1/me/transactions
GET    /api/v1/generations
GET    /api/v1/generations/{generation_id}
GET    /api/v1/generations/{generation_id}/recreate
DELETE /api/v1/generations/{generation_id}/history
POST   /api/v1/generations/{generation_id}/history/restore
GET    /api/v1/references
POST   /api/v1/references/touch
DELETE /api/v1/references/{reference_id}
POST   /api/v1/uploads/kie
```

**Auth:** Telegram user unless the individual read-only route documents otherwise.

`/uploads/kie` is a compatibility route name. Current reusable uploads are persisted under ROXY/product ownership before being used as durable references; clients must not interpret the route name as permission to store temporary provider URLs as product truth.

## Generation catalog / quote / create

```text
GET  /api/v1/generations/models
POST /api/v1/generations/quote
POST /api/v1/generations
```

The catalog returns model identity, family/presentation metadata, supported fields/scenarios, `ui_schema` and public pricing metadata. The customer UI must derive model controls and variant price display from this response.

Pricing contract:

- the latest published Admin Tariffs `generation_pricing` version in PostgreSQL is the canonical operator override;
- API workers synchronize the current version before catalog/quote/create pricing decisions;
- flat, per-second and supported parameter tiers use the shared server resolver;
- image/video/music/Suno products participate in the same pricing contour;
- quote and actual debit must agree.

Generation creation atomically commits generation state + wallet debit + PostgreSQL outbox. Redis is coordination/latency state, not the durable work ledger.

Before debit the backend enforces resource/admission limits. Worker submission additionally respects provider/global rate and circuit state. Ambiguous provider acceptance is reconciled rather than blindly resubmitted.

## Feed / publication / social

```text
GET    /api/v1/feed
GET    /api/v1/profiles/{user_id}/feed
POST   /api/v1/feed/{generation_id}/like
DELETE /api/v1/feed/{generation_id}/like
GET    /api/v1/feed/{generation_id}/comments
POST   /api/v1/feed/{generation_id}/comments
POST   /api/v1/feed/{generation_id}/share
POST   /api/v1/feed/{generation_id}/remix
```

Publication/profile action routes live in the generation/feed domain and are surface-authorized server-side.

Current contract:

- a public feed DTO may hide `prompt` while still allowing a legitimate cross-user Repeat/remix action;
- server restores protected source prompt/settings internally;
- client never supplies the trusted source prompt for repeat/remix;
- feed/profile surface access is revalidated for like/share/comment/repeat actions.

Share endpoints return a usable publication link. Link generation uses a Direct Mini App short name only when explicitly configured; otherwise it returns a `t.me/<bot>?start=<payload>` fallback. It must never synthesize `/app`.

See `FEED_DOMAIN.md` and `POST_GENERATION_ACTIONS.md`.

## Curated Trends

### Customer

```text
GET  /api/v1/trends
GET  /api/v1/trends/{trend_id}
POST /api/v1/trends/{trend_id}/run
```

Public DTOs never expose the curated prompt/provider parameters. A trend run accepts only permitted customer reference input; model/prompt/settings/price are server-owned.

### Inline admin in ROXY

```text
GET    /api/v1/trends/manage
POST   /api/v1/trends/manage
PATCH  /api/v1/trends/manage/{trend_id}
DELETE /api/v1/trends/manage/{trend_id}
POST   /api/v1/trends/manage/{trend_id}/activate
```

**Auth:** signed Telegram user + active linked `AdminAccount` + server-side `social.moderate` authorization.

Writes use validated recipes and `AdminCommandLedger` idempotency/audit semantics.

### Privileged Admin Console

The separate `/api/v1/admin/trends*` / admin-content paths use the privileged Admin Console auth/session boundary. Both admin surfaces mutate the same curated Trend store.

## Referrals / partner links

```text
GET /api/v1/referrals/stats
GET /api/v1/referrals/invitations
GET /api/v1/referrals/rewards
```

**Auth:** Telegram user.

`referral_link` and profile/publication links follow the shared Telegram link contract: real Direct Mini App short name when configured; otherwise bot `/start` payload fallback.

## Wallet / payments

Package/checkout and payment-history routes are server-authoritative. The browser never invents an amount or marks a payment paid locally.

Representative routes:

```text
GET  /api/v1/payments/packages
GET  /api/v1/payments/card/packages
POST /api/v1/payments
POST /api/v1/payments/card/checkout
GET  /api/v1/payments
GET  /api/v1/payments/{payment_id}
```

Mutating payment intents require the route's Telegram auth/idempotency contract. Provider reconciliation remains server/worker owned.

Important payment states include creating/unknown/pending/succeeded/refund/expired/failed families. On uncertain provider creation, clients preserve the same intent/idempotency key and reload server state instead of generating a second invoice.

## Media assets

```text
GET /api/v1/media/{asset_id}
GET /api/v1/media/{asset_id}/download
```

Owned media is private and user/surface authorized. View/download URLs are short-lived capabilities; they are not permanent database identifiers.

## Prompt tools / promo / support

Representative Telegram-user endpoints include:

```text
GET  /api/v1/prompt-tools
POST /api/v1/promocodes/redeem
POST /api/v1/support/tickets
GET  /api/v1/support/tickets
```

Resource-consuming tools share the server's rate/admission protections.

## Admin API groups

Representative privileged groups:

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
/api/v1/admin/tariffs*
/api/v1/admin/trends*
/api/v1/admin/roles
/api/v1/admin/admins/*
/api/v1/admin/audit
/api/v1/admin/security/*
```

See `ADMIN_CONSOLE.md`, `ADMIN_SECURITY.md` and `ADMIN_CAPABILITY_MATRIX.md`.

## Webhooks

```text
POST /webhooks/telegram
POST /webhooks/kie
POST /webhooks/payments/cryptobot
POST /webhooks/payments/tbank
POST /webhooks/payments/yookassa
```

Webhook authenticity uses provider/Telegram signature/secret contracts. User rate-limit/auth mechanisms are not substitutes for webhook verification.

## Resource-protection response contract

Resource/admission limits may return:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: <seconds>
```

If configured fail-closed protection state cannot be verified, protected expensive operations may return `503` with `Retry-After`. Clients must respect the retry window and not tight-loop.

## Common HTTP classes

```text
400 invalid request/idempotency/header
401 invalid Telegram/admin authentication
403 permission/webhook/signature boundary
404 resource not found or intentionally non-enumerable
409 idempotency/state/unsupported-operation conflict
413 upload too large
415 unsupported media type
422 model/recipe/parameter validation
429 quota/rate/admission limit
502 upstream provider operation failure
503 service/config/protection-store unavailable
```

When a route returns `Retry-After`, honor it.
