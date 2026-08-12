# KSU bot

Production-oriented Telegram AI content platform: Telegram bot + schema-driven Mini App + FastAPI backend + durable Kie generation pipeline + resilient payments + privileged admin API.

**Documentation status:** synchronized with this branch on 2026-08-12.

## Implemented runtime

### User product

- Telegram bot commands `/start`, `/balance`, `/profile`, `/support`.
- Telegram Mini App at `/mini-app/`.
- Telegram WebApp `initData` validation for authenticated REST actions.
- Dynamic model-specific generation screens driven by backend `ui_schema`.
- Per-model draft state, scenario validation, selected-settings summary and live server quote.
- Authenticated media upload proxy at `/api/v1/uploads/kie`; provider keys stay server-side.
- Internal-credit wallet/ledger, promo codes, referrals, support data and notifications.

### Generation

- Kie Market unified task API and `recordInfo` reconciliation.
- Kie callback HMAC verification.
- PostgreSQL transactional outbox: generation + wallet debit + `generation_outbox` commit atomically.
- `generation-worker` claims leased rows with `FOR UPDATE SKIP LOCKED`.
- Redis is a best-effort `wake:generations` channel only; losing Redis does not lose paid work.
- Recovery for missing outbox rows, expired leases, uncertain `submitting` state and stale `generating` Kie tasks.
- Idempotent generation refund on unrecoverable provider failure.
- Nano Banana, Seedream, GPT Image, Wan, Seedance, Kling Motion and Grok model families.
- Image flat billing and video per-second billing, calculated server-side.

### Payments

- Product rule: **1 internal credit = 10 RUB** by default.
- Server-side package catalog; client cannot choose arbitrary RUB/credit values.
- `POST /api/v1/payments` requires a UUID `Idempotency-Key`.
- Local `payment_requests` intent is committed before the provider side effect, so retry/double-click cannot intentionally create another local payment intent.
- `GET /api/v1/payments/{payment_id}` exposes authenticated local payment state for polling.
- Dedicated `payment-worker` periodically reconciles `creating`, `creation_unknown`, `pending` and `refund_review` payments.
- Crypto Pay: signed `invoice_paid` webhook plus `getInvoices` recovery by invoice ID/local payload.
- T-Bank: `/v2/Init`, signed notifications, `/v2/CheckOrder`, `/v2/GetState`, and full merchant refund through classic `/v2/Cancel`.
- YooKassa: payment creation with provider `Idempotence-Key`, authoritative payment re-fetch, cumulative `refunded_amount` reconciliation, and idempotent partial/full merchant refunds through `/v3/refunds`.
- Immutable `payment_reversals` accounting ledger.
- Provider refund/reversal withdraws the corresponding internal credits exactly once and proportionally reverses referral rewards.
- If refunded credits were already spent, accounting reversal may make the wallet negative; normal user spending still rejects insufficient balance.
- Crypto Pay invoice API has no merchant invoice-refund operation, so this backend does not invent one.
- T-Bank admin-initiated partial refunds are intentionally disabled until receipt/fiscalization data is modelled; full refunds are supported.

### Admin/security

- Separate privileged admin identities and opaque server-side sessions.
- Deny-by-default permissions, TOTP MFA, recovery codes, idle/absolute expiry and step-up reauthentication.
- Payment reconciliation/refund admin actions require fresh MFA step-up and the existing financial wallet-adjust permission, which is granted to owner/admin/finance roles.
- Audit trail, user restrictions, support/withdrawal/promo/referral/admin security operations.

> The repository currently ships the protected **admin API/security contour**, not a dedicated visual admin client. See `docs/ADMIN_SECURITY.md`.

## Stack

- Python 3.12
- FastAPI + aiogram 3
- PostgreSQL 17 + async SQLAlchemy 2
- Redis 7.4
- Alembic
- Docker Compose
- Vanilla HTML/CSS/JavaScript Telegram Mini App
- GitHub Actions CI

## Runtime topology

```text
Telegram / browser
        |
        v
 HTTPS reverse proxy
        |
        v
 FastAPI app :8000 --------------------> PostgreSQL
    |                                      |-- business state
    |                                      |-- generation_outbox
    |                                      |-- payment requests/reversals
    |
    +--> Redis wake/FSM --> generation-worker --> Kie.ai
    |
    +--------------------> payment-worker ------> payment providers

Kie callbacks ---------> /webhooks/kie
Payment providers -----> /webhooks/payments/*
```

Compose services:

- `postgres`
- `redis`
- `app`
- `generation-worker`
- `payment-worker`

## Documentation map

- `docs/API_REFERENCE.md` — route and authorization boundaries.
- `docs/OPERATIONS_RUNBOOK.md` — production deployment, workers, webhooks, incidents, backups and rollback.
- `docs/GENERATION_MINI_APP.md` — dynamic model-screen contract.
- `docs/ADMIN_SECURITY.md` — admin bootstrap, MFA, permissions, sessions and audit.

## Local development

```bash
cp .env.example .env
docker compose up --build
```

Useful endpoints:

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
GET  /api/v1/payments/{payment_id}
```

Swagger/ReDoc are disabled in production.

## Core configuration

Start from `.env.example`.

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://api.example.com
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
BOT_TOKEN=...
TELEGRAM_WEBHOOK_URL=https://api.example.com
TELEGRAM_WEBHOOK_SECRET=<random-secret>

INTERNAL_CREDIT_RUB=10
ROX_PACKAGES_JSON={"starter":{"credits":"30","currency":"RUB"}}

ADMIN_SECURITY_KEY=<dedicated-random-secret-32+-chars>
ADMIN_REQUIRE_MFA=true
```

`ADMIN_SECURITY_KEY` must be a dedicated secret and must never reuse bot/provider credentials. Owner bootstrap/MFA procedure is documented in `docs/ADMIN_SECURITY.md`.

### Generation reliability

```dotenv
KIE_API_KEY=...
KIE_BASE_URL=https://api.kie.ai
KIE_UPLOAD_BASE_URL=https://kieai.redpandaai.co
KIE_WEBHOOK_HMAC_KEY=...
GENERATION_PRICING_JSON={}

GENERATION_WORKER_POLL_SECONDS=5
GENERATION_OUTBOX_LEASE_SECONDS=90
GENERATION_SUBMISSION_MAX_ATTEMPTS=5
GENERATION_SUBMISSION_UNKNOWN_TIMEOUT_SECONDS=900
GENERATION_RECONCILE_INTERVAL_SECONDS=60
GENERATION_RECONCILE_STALE_SECONDS=60
GENERATION_RECOVERY_BATCH_SIZE=50
```

There remains an unavoidable external-provider ambiguity if Kie accepted `createTask` but neither its response task ID nor callback is ever observed. The backend avoids blind duplicate submission and refunds the user after the configured timeout.

### Payment lifecycle

```dotenv
PAYMENT_RECONCILE_INTERVAL_SECONDS=60
PAYMENT_RECONCILE_STALE_SECONDS=30
PAYMENT_RECONCILE_BATCH_SIZE=100

CRYPTOPAY_API_TOKEN=...
CRYPTOPAY_BASE_URL=https://pay.crypt.bot

TBANK_TERMINAL_KEY=...
TBANK_PASSWORD=...
TBANK_BASE_URL=https://securepay.tinkoff.ru

YOOKASSA_SHOP_ID=...
YOOKASSA_SECRET_KEY=...
YOOKASSA_BASE_URL=https://api.yookassa.ru
PAYMENT_RETURN_URL=https://app.example.com/payment-result
```

User payment creation contract:

```http
POST /api/v1/payments
X-Telegram-Init-Data: <signed Telegram initData>
Idempotency-Key: <UUID>
Content-Type: application/json

{"provider":"yookassa","package_id":"starter"}
```

Reuse the same key for retrying the **same** payment intent. Reusing it with another provider/package returns a conflict.

Admin financial lifecycle:

```text
POST /api/v1/admin/payments/{payment_id}/reconcile
POST /api/v1/admin/payments/{payment_id}/refund
```

Both require an authenticated privileged session and fresh MFA step-up. Refund request body contains `amount`, UUID `request_id`, and `reason`.

Supported merchant refund initiation:

- YooKassa — partial and full;
- T-Bank — full original-payment refund only;
- Crypto Pay — unsupported because the invoice API does not expose refund.

Provider-initiated/manual YooKassa refunds are still reconciled because authoritative payment state contains cumulative `refunded_amount`.

## Internal credit accounting

```text
rubles = internal_credits × INTERNAL_CREDIT_RUB
```

Legacy DB/API fields named `rox` remain for compatibility, but product terminology is **credits**. Kie provider credits are unrelated to product credits.

Generation video billing:

```text
cost_credits = price_credits_per_second × billing_seconds
cost_rub = cost_credits × INTERNAL_CREDIT_RUB
```

## Migrations

```bash
alembic upgrade head
```

Current chain includes:

```text
0001_initial
0002_admin_security
0003_generation_outbox
0004_payment_lifecycle
```

## CI

Current GitHub Actions gate:

```text
pip install -e '.[dev]'
ruff check .
python -m compileall -q app tests
node --check app/web/mini_app/app.js
alembic upgrade head
pytest -q
```

CI uses real PostgreSQL and Redis containers. `mypy` is installed in dev dependencies but is not yet a required CI gate.

## Known production limitations / next epics

1. **Provider media URLs are not product-owned durable storage.** Permanent object storage is still required.
2. **No dedicated visual admin client yet.**
3. **Anti-abuse/resource-consumption controls are the next P0 epic:** generation concurrency/rate/upload/spend limits and provider circuit breakers.
4. **Observability is still incomplete:** metrics, traces and production alerts remain a separate P0 epic.
5. **Payment chargeback files/settlement registries are not ingested automatically.** Webhook/API-visible refunds are handled; reconciliation of offline acquiring registers/chargebacks remains an accounting integration extension.
6. Compose still publishes app port 8000 for development; production must place it behind HTTPS and keep PostgreSQL/Redis private.

## External references checked

- PostgreSQL `SKIP LOCKED` queue-style work claiming.
- Kie Market task detail/webhook HMAC documentation.
- Crypto Pay API 1.5.2 (`getInvoices`, webhook signature and supported methods).
- T-Bank Internet Acquiring `/v2/Init`, `/v2/GetState`, `/v2/CheckOrder`, `/v2/Cancel`, notifications and refund scenarios.
- YooKassa payment/refund/idempotency/webhook documentation.
- Telegram Mini Apps documentation.
- OWASP ASVS 5.0.0 / Authorization guidance.
