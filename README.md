# KSU bot

Production-oriented Telegram AI content platform: Telegram bot + schema-driven Mini App + FastAPI backend + durable Kie.ai generation worker + internal credits/payments + privileged admin API.

**Documentation status:** synchronized with this branch on 2026-08-12.

## What is implemented now

### User product

- Telegram bot commands `/start`, `/balance`, `/profile`, `/support`.
- Telegram Mini App served at `/mini-app/`.
- Telegram WebApp `initData` validation on authenticated REST endpoints.
- Dynamic generation screens driven by backend `ui_schema`.
- Isolated per-model drafts, scenario-specific fields, selected-settings summary and live server-side quote.
- Local image/video/audio upload through `/api/v1/uploads/kie`; the Kie API key never reaches the browser.
- Users, wallets, immutable wallet transaction ledger, promo codes, referrals, support tickets and notifications.

### Generation

- Kie.ai Market task integration through `/api/v1/jobs/createTask` and unified `/api/v1/jobs/recordInfo` reconciliation.
- Kie webhook HMAC verification when `KIE_WEBHOOK_HMAC_KEY` is configured.
- **Transactional outbox for generation submission:** generation row, wallet debit and `generation_outbox` row commit in one PostgreSQL transaction.
- PostgreSQL leased work claims using `FOR UPDATE SKIP LOCKED`; expired leases are reclaimable by another worker.
- Redis is a best-effort low-latency wake-up channel only; losing Redis wake-up does not lose paid generation work.
- Dedicated `generation-worker` polls the durable outbox and periodically performs recovery/reconciliation.
- Existing `queued/retry` rows without outbox records are repaired automatically.
- Kie callback URL carries the local `generation_id`, allowing recovery if Kie accepted `createTask` before the worker persisted `taskId`.
- Stale `generating` tasks are reconciled through Kie `recordInfo` if a callback is delayed/lost.
- Provider failure/unknown-submission timeout produces an idempotent internal-credit refund.
- Server-controlled model catalog for Nano Banana, Seedream, GPT Image, Wan, Seedance, Kling Motion Control and Grok Imagine variants.
- Flat billing for image tasks and per-second billing for video tasks.
- Fixed product exchange rate: **1 internal credit = 10 RUB** by default.

### Payments

- CryptoBot / Crypto Pay: invoice creation + raw-body HMAC webhook verification.
- T-Bank Internet Acquiring: `/v2/Init`, signed `Token`, verified notifications and `OK` acknowledgement.
- YooKassa: `Idempotence-Key`; incoming notification is rechecked against the authoritative provider payment before wallet credit.
- Server-side credit package catalog; clients submit only `package_id` and provider.
- Successful payment credits the wallet idempotently and accrues configured 30% / 5% referral rewards.

### Admin/security

- Separate privileged admin identity/session domain.
- Roles: `owner`, `admin`, `support`, `finance`, `moderator`, `auditor`.
- Deny-by-default permissions with explicit allow/deny overrides.
- TOTP MFA, one-time recovery codes, opaque server-side sessions, idle/absolute expiry and step-up reauthentication.
- Admin operations for users, wallet adjustments, generations, payment visibility, support, withdrawals, promos, referrals, admin accounts/sessions and audit/security visibility.
- HMAC-protected audit trail with secret/credential redaction.
- User restrictions are enforced in REST/Mini App authorization and Telegram bot middleware.

> The repository ships the **admin API/security contour**, but not a dedicated visual admin web client. See `docs/ADMIN_SECURITY.md`.

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
 FastAPI app :8000 --------------------------> PostgreSQL
    |                                             |
    |                                             +--> generation_outbox
    |                                             +--> wallet/generation state
    |
    +--> best-effort Redis wake --------------------+
                                                   |
                                                   v
                                         generation-worker
                                           | claim lease
                                           | SKIP LOCKED
                                           v
                                              Kie.ai

Kie callbacks --------> /webhooks/kie ----------> recordInfo reconciliation
Payment providers ----> /webhooks/payments/* ---> wallet/referrals
```

Docker Compose services:

- `postgres`
- `redis`
- `app`
- `generation-worker`

## Documentation map

- `docs/API_REFERENCE.md` — authentication boundaries and current route map.
- `docs/OPERATIONS_RUNBOOK.md` — production deployment, provider setup, smoke checks, backup/restore, incidents and rollback.
- `docs/GENERATION_MINI_APP.md` — dynamic model-screen contract, state rules, uploads, quote and model scenarios.
- `docs/ADMIN_SECURITY.md` — privileged admin bootstrap, MFA, permissions, sessions and audit.

## Local development

```bash
cp .env.example .env
docker compose up --build
```

The Compose app command runs `alembic upgrade head` before Uvicorn. Controlled production releases should still run migrations explicitly according to `docs/OPERATIONS_RUNBOOK.md`.

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

Swagger/ReDoc are enabled only outside production.

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

The bot's Create content button opens `{PUBLIC_BASE_URL}/mini-app/`. Configure the Main Mini App URL in BotFather as well if a profile-level launch button is desired.

## Internal credits

```dotenv
INTERNAL_CREDIT_RUB=10
```

```text
rubles = internal_credits × INTERNAL_CREDIT_RUB
```

Legacy storage/API compatibility fields named `rox` remain in parts of the codebase, but product terminology is **credits**. Kie `creditsConsumed` is provider-side usage and is not the user's internal-credit balance.

## Kie.ai and durable generation flow

```dotenv
KIE_API_KEY=...
KIE_BASE_URL=https://api.kie.ai
KIE_UPLOAD_BASE_URL=https://kieai.redpandaai.co
KIE_UPLOAD_MAX_BYTES=104857600
KIE_WEBHOOK_HMAC_KEY=...

GENERATION_WORKER_POLL_SECONDS=5
GENERATION_OUTBOX_LEASE_SECONDS=90
GENERATION_SUBMISSION_MAX_ATTEMPTS=5
GENERATION_SUBMISSION_UNKNOWN_TIMEOUT_SECONDS=900
GENERATION_RECONCILE_INTERVAL_SECONDS=60
GENERATION_RECONCILE_STALE_SECONDS=60
GENERATION_RECOVERY_BATCH_SIZE=50
```

Production flow:

1. Client selects a server model and obtains a server-side quote.
2. `POST /api/v1/generations` revalidates the model and price.
3. Generation row + wallet debit + `generation_outbox` row commit atomically in PostgreSQL.
4. The app sends a best-effort Redis wake signal. Failure is logged but does not fail the committed request.
5. `generation-worker` claims an outbox row with a lease and `FOR UPDATE SKIP LOCKED`.
6. Worker submits Kie `createTask` with `callBackUrl={PUBLIC_BASE_URL}/webhooks/kie?generation_id=<local-id>`.
7. The returned Kie `taskId` is persisted and the outbox row is completed.
8. Kie callback is HMAC-verified and then reconciled through `recordInfo`.
9. A periodic recovery pass also checks stale `generating` tasks through `recordInfo`.
10. Provider failure or unrecoverable unknown submission refunds the internal credits idempotently.

The worker never treats Redis as durable generation state. If Redis is unavailable, DB polling continues at `GENERATION_WORKER_POLL_SECONDS`.

### Uncertain provider submission

There is an unavoidable provider boundary: the process can die after Kie accepted `createTask` but before the HTTP response/task ID is durably stored. To avoid duplicate provider spend, the worker does **not** blindly resubmit a local generation already in `submitting` state. The callback can bind its signed Kie `taskId` back to the local `generation_id`. If no callback recovers the task within `GENERATION_SUBMISSION_UNKNOWN_TIMEOUT_SECONDS`, the user receives an idempotent refund and the local generation is failed.

### Media uploads

`POST /api/v1/uploads/kie` requires Telegram Mini App authorization and accepts image/video/audio MIME types within the configured global size ceiling. Provider URLs are temporary; copy successful results to product-owned object storage when durable media retention is implemented.

## Dynamic generation Mini App

`GET /api/v1/generations/models` returns `schema_version` and a `ui_schema` for every model. The browser uses it as the runtime form contract.

Important behavior:

- per-model drafts are isolated and persisted locally as a convenience;
- stale/unknown fields are removed when a saved draft meets a newer schema;
- scenario switching clears incompatible values from state, not only the DOM;
- selected-settings summary comes from current state;
- quote refreshes after relevant changes;
- create buttons remain disabled while validation/upload/quote is incomplete.

See `docs/GENERATION_MINI_APP.md`.

## Generation billing

Image:

```text
cost_credits = flat_price
```

Video:

```text
cost_credits = price_credits_per_second × billing_seconds
cost_rub = cost_credits × INTERNAL_CREDIT_RUB
```

Optional server-side price overrides:

```dotenv
GENERATION_PRICING_JSON={"wan-2.7-t2v":{"per_second":"8.50"},"gpt-image-2-t2i":{"flat":"18"},"kling-motion-3.0":{"per_second":"15"}}
```

The create endpoint recalculates price independently; clients cannot submit a trusted cost.

## Credit packages and payments

```dotenv
ROX_PACKAGES_JSON={"starter":{"credits":"30","currency":"RUB"}}
```

At `INTERNAL_CREDIT_RUB=10`, 30 credits cost 300 RUB. If both `amount` and `credits` are configured, mismatched exchange rates are rejected.

### CryptoBot / Crypto Pay

```dotenv
CRYPTOPAY_API_TOKEN=...
CRYPTOPAY_BASE_URL=https://pay.crypt.bot
```

Webhook: `POST {PUBLIC_BASE_URL}/webhooks/payments/cryptobot`.

### T-Bank

```dotenv
TBANK_TERMINAL_KEY=...
TBANK_PASSWORD=...
TBANK_BASE_URL=https://securepay.tinkoff.ru
PAYMENT_RETURN_URL=https://example.com/payment-result
```

The backend uses `/v2/Init`, validates notifications and returns plain-text `OK` on successful handling.

### YooKassa

```dotenv
YOOKASSA_SHOP_ID=...
YOOKASSA_SECRET_KEY=...
YOOKASSA_BASE_URL=https://api.yookassa.ru
PAYMENT_RETURN_URL=https://example.com/payment-result
```

Configure `payment.succeeded` to `POST {PUBLIC_BASE_URL}/webhooks/payments/yookassa`. Incoming notifications are re-fetched from YooKassa before local wallet credit.

## Admin/security

```dotenv
ADMIN_SECURITY_KEY=<dedicated random secret, 32+ chars>
ADMIN_BOOTSTRAP_TELEGRAM_IDS=<temporary initial owner Telegram ID>
ADMIN_REQUIRE_MFA=true
```

After first owner enrollment, remove `ADMIN_BOOTSTRAP_TELEGRAM_IDS`. Full procedure: `docs/ADMIN_SECURITY.md`.

## Database migrations

Current migration chain includes product schema, admin/security schema and generation outbox:

```bash
alembic upgrade head
```

## CI and local validation

```text
pip install -e '.[dev]'
ruff check .
python -m compileall -q app tests
node --check app/web/mini_app/app.js
alembic upgrade head
pytest -q
```

CI uses real PostgreSQL and Redis service containers. `mypy` is installed in the dev extra but is not currently a required CI gate.

## Known production limitations

1. **Provider URLs are not product-owned durable media storage.** Copy Kie outputs to owned object storage for permanent retention.
2. **No dedicated visual admin client is bundled yet.** The protected admin API/security domain is implemented.
3. **Compose exposes app port 8000 directly for development.** Production should place it behind HTTPS/reverse proxy and keep PostgreSQL/Redis private.
4. **Application startup also runs migrations in the Compose command.** Production deployments should execute migrations explicitly before replacing app/worker.
5. **Kie createTask has a cross-system ambiguity window.** The transactional outbox prevents local paid-work loss, and callback binding prevents blind duplicate submission, but if Kie accepted a request and neither its task ID response nor callback is observed, the backend refunds the user after the configured unknown-submission timeout. Provider-side spend may still have occurred in that rare case.

## External references checked for this architecture

- PostgreSQL row locking / `SKIP LOCKED` for queue-like consumers.
- Kie.ai Market task detail and webhook HMAC documentation.
- Redis finite blocking timeout semantics for best-effort worker wake-up.
- Telegram Mini Apps documentation.
- Crypto Pay, T-Bank and YooKassa provider documentation.
- OWASP ASVS 5.0.0 and Authorization guidance for privileged admin controls.
