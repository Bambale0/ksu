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
- Redis is a best-effort `wake:generations` channel for delivery latency; PostgreSQL remains durable work state.
- Recovery for missing outbox rows, expired leases, uncertain `submitting` state and stale `generating` Kie tasks.
- Idempotent generation refund on unrecoverable provider failure.
- Nano Banana, Seedream, GPT Image, Wan, Seedance, Kling Motion and Grok model families.
- Image flat billing and video per-second billing, calculated server-side.

### Payments

- Product rule: **1 internal credit = 10 RUB** by default.
- Server-side package catalog; client cannot choose arbitrary RUB/credit values.
- Payment creation requires UUID `Idempotency-Key`.
- Durable payment intents, provider reconciliation, immutable reversal accounting and proportional referral reversal.
- Dedicated `payment-worker` reconciles uncertain/pending provider states.
- Crypto Pay, T-Bank and YooKassa provider-specific recovery/refund behavior is documented in `docs/OPERATIONS_RUNBOOK.md`.

### Anti-abuse / resource consumption

The expensive product paths now have centralized OWASP API4-style resource controls:

- distributed Redis fixed-window counters implemented atomically with Lua;
- generation requests per user/minute;
- maximum simultaneous active generations per user;
- optional daily generation spend ceiling in internal credits;
- upload requests/minute and uploaded bytes/day per user;
- existing global Kie upload-size ceiling and MIME allowlist;
- payment-creation requests/minute layered on top of payment idempotency;
- global Kie submission rate;
- Kie availability circuit breaker based on recent transport/429/5xx failures;
- standardized HTTP `429`/`503` responses with `Retry-After`;
- expensive user mutations fail closed by default when the distributed protection store is unavailable.

Generation admission happens **before wallet debit**. Active-generation and daily-spend decisions are serialized with a PostgreSQL user-row lock, so concurrent requests for one user cannot race past the configured active-task cap.

When the Kie circuit/rate guard is closed to new provider calls, already-paid generation work remains in the durable PostgreSQL outbox and is delayed until `Retry-After`; protection throttling itself does not mark the task failed or issue a false refund.

### Admin/security

- Separate privileged admin identities and opaque server-side sessions.
- Deny-by-default permissions, TOTP MFA, recovery codes, idle/absolute expiry and step-up reauthentication.
- Payment reconciliation/refund admin actions require fresh MFA step-up and financial permissions.
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
    +--> Redis --------------------------> distributed limits / FSM / wake
    |          |                               |
    |          +--> generation-worker --------+--> Kie.ai
    |
    +--------------------> payment-worker --------> payment providers

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
- `docs/OPERATIONS_RUNBOOK.md` — production deployment, workers, webhooks, limits, incidents, backups and rollback.
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

`ADMIN_SECURITY_KEY` must be dedicated and must never reuse bot/provider credentials. Owner bootstrap/MFA procedure is in `docs/ADMIN_SECURITY.md`.

### Generation reliability

```dotenv
KIE_API_KEY=...
KIE_BASE_URL=https://api.kie.ai
KIE_UPLOAD_BASE_URL=https://kieai.redpandaai.co
KIE_UPLOAD_MAX_BYTES=104857600
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

### Payment lifecycle

```dotenv
PAYMENT_RECONCILE_INTERVAL_SECONDS=60
PAYMENT_RECONCILE_STALE_SECONDS=30
PAYMENT_RECONCILE_BATCH_SIZE=100

CRYPTOPAY_API_TOKEN=...
TBANK_TERMINAL_KEY=...
TBANK_PASSWORD=...
YOOKASSA_SHOP_ID=...
YOOKASSA_SECRET_KEY=...
PAYMENT_RETURN_URL=https://app.example.com/payment-result
```

### Resource-consumption controls

All operational limits are configurable without code changes:

```dotenv
ABUSE_PROTECTION_ENABLED=true
ABUSE_FAIL_CLOSED=true
GENERATION_RATE_LIMIT_PER_MINUTE=10
GENERATION_MAX_ACTIVE_PER_USER=3
GENERATION_DAILY_SPEND_LIMIT_CREDITS=0
UPLOAD_RATE_LIMIT_PER_MINUTE=12
UPLOAD_DAILY_BYTES_LIMIT=1073741824
PAYMENT_CREATE_RATE_LIMIT_PER_MINUTE=6
KIE_SUBMIT_RATE_LIMIT_PER_MINUTE=60
KIE_CIRCUIT_FAILURE_THRESHOLD=5
KIE_CIRCUIT_FAILURE_WINDOW_SECONDS=60
KIE_CIRCUIT_OPEN_SECONDS=60
```

`GENERATION_DAILY_SPEND_LIMIT_CREDITS=0` disables the separate daily-spend quota; wallet balance still applies. Other zero/disabled values are documented in `.env.example`.

When a user quota is exceeded the API returns `429` with a `Retry-After` header and a JSON `retry_after` value. If `ABUSE_FAIL_CLOSED=true` and Redis cannot verify an expensive user mutation, the API returns `503` rather than allowing unmetered provider spend.

A Redis outage after a generation has already been atomically committed does not lose the generation. However, while fail-closed provider protection cannot verify Kie submission limits, the generation worker may deliberately delay new external submissions until Redis recovers.

## Internal credit accounting

```text
rubles = internal_credits × INTERNAL_CREDIT_RUB
```

Legacy DB/API fields named `rox` remain for compatibility; product terminology is **credits**. Kie provider credits are unrelated to product credits.

Video billing:

```text
cost_credits = price_credits_per_second × billing_seconds
cost_rub = cost_credits × INTERNAL_CREDIT_RUB
```

## Migrations

```bash
alembic upgrade head
```

Current migration chain:

```text
0001_initial
0002_admin_security
0003_generation_outbox
0004_payment_lifecycle
```

Anti-abuse controls use existing PostgreSQL/Redis infrastructure and add no schema migration.

## CI

```text
pip install -e '.[dev]'
ruff check .
python -m compileall -q app tests
node --check app/web/mini_app/app.js
alembic upgrade head
pytest -q
```

CI uses real PostgreSQL and Redis containers; anti-abuse tests exercise real Redis Lua/TTL behavior.

## Known production limitations / next epics

1. **Observability is the next P0 epic:** metrics, traces, worker heartbeats and actionable production alerts.
2. **Provider media URLs are not product-owned durable storage.** Permanent object storage is still required.
3. **No dedicated visual admin client yet.**
4. **Payment chargeback files/settlement registries are not ingested automatically.** Webhook/API-visible refunds are handled; offline acquiring-register reconciliation remains an accounting extension.
5. Compose publishes app port 8000 for development; production must place it behind HTTPS and keep PostgreSQL/Redis private.
6. Proxy-level hard request-body limits remain part of production edge configuration; application upload limits do not replace a reverse-proxy body-size cap.

## External references checked

- OWASP API Security Top 10 2023 — API4 Unrestricted Resource Consumption.
- Redis distributed rate limiting guidance and atomic Lua-based counters.
- PostgreSQL `SKIP LOCKED` queue-style work claiming.
- Kie Market task detail/webhook/upload documentation.
- Crypto Pay API 1.5.2.
- T-Bank Internet Acquiring payment/refund contracts.
- YooKassa payment/refund/idempotency/webhook documentation.
- Telegram Mini Apps documentation.
- OWASP ASVS 5.0.0 / Authorization guidance.
