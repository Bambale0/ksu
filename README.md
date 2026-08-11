# KSU bot

Production-oriented Telegram AI content platform: Telegram bot + schema-driven Mini App + FastAPI backend + Kie.ai generation worker + internal credits/payments + privileged admin API.

**Documentation status:** synchronized with `main` on 2026-08-11.

## What is implemented now

### User product

- Telegram bot commands `/start`, `/balance`, `/profile`, `/support`.
- Telegram Mini App served by this backend at `/mini-app/`.
- Telegram WebApp `initData` validation on authenticated REST endpoints.
- Dynamic generation screens driven by backend `ui_schema`, not hardcoded per model in the browser.
- Isolated per-model drafts, scenario-specific fields, live selected-settings summary and server-side live quote.
- Local image/video/audio upload through the backend to Kie File Upload; the Kie API key never reaches the browser.
- Users, wallets, immutable wallet transaction ledger, promo codes, referrals, support tickets and notifications.

### Generation

- Kie.ai Market task integration through `/api/v1/jobs/createTask` and unified `/api/v1/jobs/recordInfo` reconciliation.
- Kie webhook HMAC verification through `X-Webhook-Timestamp` / `X-Webhook-Signature` when `KIE_WEBHOOK_HMAC_KEY` is configured.
- Redis generation queue + dedicated `generation-worker` process.
- Idempotent internal-credit refund when a provider task fails.
- Server-controlled model catalog for Nano Banana, Seedream, GPT Image, Wan, Seedance, Kling Motion Control and Grok Imagine variants.
- Flat billing for image tasks and per-second billing for every video model.
- Fixed product exchange rate: **1 internal credit = 10 RUB** by default.

### Payments

- CryptoBot / Crypto Pay: invoice creation + raw-body HMAC webhook verification.
- T-Bank Internet Acquiring: `/v2/Init`, signed `Token`, verified notifications and required `OK` acknowledgement.
- YooKassa: server-side payment creation with `Idempotence-Key`; incoming notification is rechecked against the authoritative YooKassa payment before wallet credit.
- Server-side credit package catalog; clients submit only `package_id` and provider.
- Successful payment credits the wallet idempotently and accrues 30% / 5% referral rewards according to configuration.

### Admin/security

- Separate privileged admin identity and session domain; normal Telegram user authorization is not an admin bearer session.
- Roles: `owner`, `admin`, `support`, `finance`, `moderator`, `auditor`.
- Deny-by-default permissions with explicit allow/deny overrides.
- TOTP MFA, one-time recovery codes, opaque server-side sessions, idle/absolute expiry and step-up reauthentication for sensitive operations.
- Admin operations for users, wallet adjustments, generations, payments visibility, support, withdrawals, promos, referrals, admin accounts/sessions and audit/security visibility.
- HMAC-protected audit trail with secret/credential redaction.
- User restrictions are enforced in both REST/Mini App authorization and Telegram bot middleware.

> The repository currently ships the **admin API/security contour**, but not a dedicated visual admin web client. See `docs/ADMIN_SECURITY.md`.

## Stack

- Python 3.12
- FastAPI
- aiogram 3
- PostgreSQL 17 + async SQLAlchemy 2
- Redis 7.4
- Alembic
- Docker / Docker Compose
- Vanilla HTML/CSS/JavaScript Telegram Mini App
- GitHub Actions CI

## Runtime topology

```text
Telegram / browser
        |
        v
 reverse proxy / TLS
        |
        v
 FastAPI app :8000 --------------------> PostgreSQL
    |       |                           Redis
    |       |
    |       +--> Telegram webhooks
    |       +--> Kie/payment webhooks
    |       +--> /mini-app static assets
    |       +--> /api/v1/*
    |
    +--> Redis queue --> generation-worker --> Kie.ai

Payment providers --> /webhooks/payments/* --> wallet/referrals
Kie callbacks -----> /webhooks/kie ----------> generation reconciliation
```

Docker Compose services:

- `postgres`
- `redis`
- `app`
- `generation-worker`

## Documentation map

- `docs/OPERATIONS_RUNBOOK.md` — production deployment, provider setup, smoke checks, backup/restore, incident and rollback procedures.
- `docs/GENERATION_MINI_APP.md` — dynamic model-screen contract, state rules, uploads, quoting and model scenarios.
- `docs/ADMIN_SECURITY.md` — privileged admin bootstrap, MFA, permissions, sessions, audit and security operations.

## Local development

```bash
cp .env.example .env
docker compose up --build
```

The app container runs `alembic upgrade head` before starting Uvicorn. For controlled production releases, follow the explicit migration/deploy sequence in `docs/OPERATIONS_RUNBOOK.md` instead of relying on startup migration alone.

Local API: `http://localhost:8000`

Useful surfaces:

```text
GET  /health/live
GET  /health/ready
GET  /mini-app/
GET  /api/v1/generations/models
POST /api/v1/generations/quote
POST /api/v1/generations
POST /api/v1/uploads/kie
GET  /api/v1/payments/packages
POST /api/v1/payments
```

OpenAPI Swagger/ReDoc are enabled only outside production.

## Core environment configuration

Start from `.env.example`.

### Application and Telegram

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://api.example.com
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...

BOT_TOKEN=...
TELEGRAM_WEBHOOK_URL=https://api.example.com
TELEGRAM_WEBHOOK_SECRET=<random-secret>
```

`PUBLIC_BASE_URL` is the public HTTPS origin used for the Mini App and provider callbacks. `TELEGRAM_WEBHOOK_URL` is the origin used during `Bot.set_webhook`; in a normal deployment they are the same origin.

When both `BOT_TOKEN` and `TELEGRAM_WEBHOOK_URL` are set, application startup registers:

```text
{TELEGRAM_WEBHOOK_URL}/webhooks/telegram
```

Incoming Telegram updates must include `X-Telegram-Bot-Api-Secret-Token` when `TELEGRAM_WEBHOOK_SECRET` is configured.

The bot's **Create content** button opens:

```text
{PUBLIC_BASE_URL}/mini-app/
```

Also configure the Main Mini App URL in BotFather if you want the app launch button on the bot profile.

## Internal credits

The product's internal currency is intentionally separate from Kie provider credits.

```dotenv
INTERNAL_CREDIT_RUB=10
```

Rule:

```text
rubles = internal_credits × INTERNAL_CREDIT_RUB
```

With the current default:

```text
1 credit  = 10 RUB
30 credits = 300 RUB
```

Legacy database/API compatibility fields named `rox` remain in parts of the codebase, but public product terminology is **credits**.

Kie `creditsConsumed` is provider-side usage data and is not automatically treated as the user's product balance.

## Kie.ai

```dotenv
KIE_API_KEY=...
KIE_BASE_URL=https://api.kie.ai
KIE_UPLOAD_BASE_URL=https://kieai.redpandaai.co
KIE_UPLOAD_MAX_BYTES=104857600
KIE_WEBHOOK_HMAC_KEY=...
```

Production flow:

1. Client requests a server model from `GET /api/v1/generations/models`.
2. Client asks the server for a quote.
3. On generation creation the backend validates the same request again, debits the wallet and stores the generation.
4. The generation ID is pushed to Redis `queue:generations`.
5. `generation-worker` submits the Kie task with `callBackUrl={PUBLIC_BASE_URL}/webhooks/kie`.
6. Kie callback is HMAC-verified when the HMAC key is configured.
7. Backend calls Kie `recordInfo` and applies the authoritative state/result.
8. Provider failure triggers an idempotent generation refund.

In production, enable Webhook HMAC in the Kie settings page and configure the same key as `KIE_WEBHOOK_HMAC_KEY`.

Media uploads use:

```text
POST /api/v1/uploads/kie
```

This endpoint requires valid Telegram Mini App authorization, accepts image/video/audio MIME types, applies the global `KIE_UPLOAD_MAX_BYTES` limit, and streams the file to Kie. Model-specific UI limits may be stricter than the global upload ceiling.

Kie-hosted uploaded/generated URLs are provider-managed temporary assets. If durable storage is required, copy successful outputs to product-owned object storage instead of treating provider URLs as permanent storage.

## Dynamic generation Mini App

The browser does not contain a separate hardcoded form for each Kie model.

```text
GET /api/v1/generations/models
```

returns `schema_version` and, for every model, a `ui_schema` containing groups, fields, control types, defaults, required flags, model-specific scenarios, summary fields and optional explicit billing-seconds configuration.

Current important behaviors:

- model-specific drafts are isolated and persisted locally as a convenience;
- stale/unknown fields are removed when a draft is restored against a newer schema;
- switching a scenario clears mutually incompatible fields from state, not only from the DOM;
- selected-settings chips are rendered from the current state;
- quote is refreshed after relevant changes with a short debounce;
- the Create button and Telegram bottom button are disabled while validation/upload/quote is incomplete;
- local file uploads require Telegram `initData`; a normal HTTP/HTTPS remote URL may also be supplied where a file field is shown.

See `docs/GENERATION_MINI_APP.md` for the contract and model scenario details.

## Generation billing

Image model:

```text
cost_credits = flat_price
```

Video model:

```text
cost_credits = price_credits_per_second × billing_seconds
cost_rub = cost_credits × INTERNAL_CREDIT_RUB
```

Prices are server-controlled. Optional overrides:

```dotenv
GENERATION_PRICING_JSON={"wan-2.7-t2v":{"per_second":"8.50"},"gpt-image-2-t2i":{"flat":"18"},"kling-motion-3.0":{"per_second":"15"}}
```

The create endpoint recalculates price independently; a client cannot submit its own trusted cost.

For operations without a usable provider `duration` input, `ui_schema.billing_seconds` supplies a separate product billing value. Grok upscale may reuse the source task's stored billed duration when that source belongs to this backend.

## Credit packages and payments

Packages are server-side:

```dotenv
ROX_PACKAGES_JSON={"starter":{"credits":"30","currency":"RUB"}}
```

At `INTERNAL_CREDIT_RUB=10`, this creates a 300 RUB package. If both `amount` and `credits` are supplied, the backend rejects mismatched exchange rates.

### CryptoBot / Crypto Pay

```dotenv
CRYPTOPAY_API_TOKEN=...
CRYPTOPAY_BASE_URL=https://pay.crypt.bot
```

Webhook:

```text
POST {PUBLIC_BASE_URL}/webhooks/payments/cryptobot
```

The backend verifies `crypto-pay-api-signature` against the **raw** request body using the Crypto Pay token-derived HMAC secret before processing `invoice_paid`.

### T-Bank

```dotenv
TBANK_TERMINAL_KEY=...
TBANK_PASSWORD=...
TBANK_BASE_URL=https://securepay.tinkoff.ru
PAYMENT_RETURN_URL=https://example.com/payment-result
```

The backend calls `/v2/Init`; `NotificationURL` is generated from `PUBLIC_BASE_URL`. Notifications are signature/terminal/payment/amount checked and the handler returns exactly plain-text `OK` on successful processing.

### YooKassa

```dotenv
YOOKASSA_SHOP_ID=...
YOOKASSA_SECRET_KEY=...
YOOKASSA_BASE_URL=https://api.yookassa.ru
PAYMENT_RETURN_URL=https://example.com/payment-result
```

Configure `payment.succeeded` notifications to:

```text
POST {PUBLIC_BASE_URL}/webhooks/payments/yookassa
```

Payment creation uses the local UUID as `Idempotence-Key` and in metadata. The webhook payload alone is not trusted: the backend retrieves the provider payment again and verifies metadata, ID, amount, currency and authoritative state before crediting the wallet.

## Admin/security

Required production variables include:

```dotenv
ADMIN_SECURITY_KEY=<dedicated random secret, 32+ chars>
ADMIN_BOOTSTRAP_TELEGRAM_IDS=<temporary initial owner Telegram ID>
ADMIN_REQUIRE_MFA=true
```

Do not reuse a provider credential as `ADMIN_SECURITY_KEY`.

After first owner enrollment, remove `ADMIN_BOOTSTRAP_TELEGRAM_IDS` and manage additional admins through the owner-only API. Full procedure: `docs/ADMIN_SECURITY.md`.

## Database migrations

Current migration chain includes the product schema and admin/security schema.

```bash
alembic upgrade head
```

For production, back up PostgreSQL before migrations and use the runbook deploy sequence.

## CI and local validation

GitHub Actions currently runs on every pull request and pushes to `main`:

```text
pip install -e '.[dev]'
ruff check .
python -m compileall -q app tests
node --check app/web/mini_app/app.js
alembic upgrade head
pytest -q
```

CI uses real PostgreSQL and Redis service containers.

`mypy` is installed in the dev extra but is **not currently a required CI gate**.

## Known production limitations

These are deliberate documentation of the current code, not claims of completed work:

1. **No transactional outbox yet for generation enqueue.** Generation/wallet DB state is committed before `Redis.rpush`. A process failure in that narrow gap can leave a paid generation in `queued` state without a queue message. Do not assume Redis restart alone repairs this case. Add transactional outbox/reconciliation before treating enqueue as exactly-once durable.
2. **Provider URLs are not product-owned durable media storage.** Uploaded/generated Kie assets should be copied to owned object storage if permanent retention is required.
3. **No dedicated visual admin client is bundled yet.** The protected admin API/security domain is implemented; a separate UI can be built against it.
4. **Compose exposes app port 8000 directly for development.** Production should place it behind HTTPS/reverse proxy and keep PostgreSQL/Redis private.
5. **Application startup also runs migrations in the Compose command.** Production deployments should still execute migrations explicitly before replacing the app/worker, as described in the runbook.

## External references checked for this documentation

- Kie.ai Market task creation/detail, file upload and webhook HMAC verification documentation.
- Telegram Mini Apps documentation (`initData`, dynamic theme, Bottom/Main button behavior).
- Crypto Pay API webhook signature documentation.
- T-Bank Internet Acquiring Init and notification documentation.
- YooKassa payment creation/webhook documentation.
- OWASP ASVS 5.0.0 and Authorization guidance for the privileged admin contour.
