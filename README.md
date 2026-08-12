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
- Live generation result polling, result gallery and owned cursor-paginated history.
- Safe recreation/variant draft from historical generations with a fresh server quote before charging again.
- Reversible soft-hide history state without deleting financially significant generation/accounting rows.
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

The expensive product paths have centralized OWASP API4-style resource controls:

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

### Observability

- Structured JSON logging with `request_id`, `trace_id` and `span_id` correlation.
- Bounded `X-Request-ID` propagation with UUID fallback.
- Prometheus endpoint at `/metrics`, optionally protected by `METRICS_BEARER_TOKEN`.
- Worker heartbeat health at `/health/operational` for `generation-worker` and `payment-worker`.
- Generation/outbox/payment snapshot gauges, worker health, provider circuit state and bounded Redis cross-process counters.
- Optional OpenTelemetry FastAPI/HTTPX tracing through OTLP HTTP.
- Production alert rules in `ops/prometheus-alerts.yml`.

Operational contract and alert semantics: `docs/OBSERVABILITY.md`.

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
- Prometheus client + optional OpenTelemetry OTLP tracing
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
    |                                      |-- history presentation state
    |
    +--> Redis --------------------------> distributed limits / FSM / wake / worker telemetry
    |          |                               |
    |          +--> generation-worker --------+--> Kie.ai
    |
    +--------------------> payment-worker --------> payment providers

Kie callbacks ---------> /webhooks/kie
Payment providers -----> /webhooks/payments/*
Monitoring ------------> /metrics
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
- `docs/RESULTS_HISTORY.md` — generation result polling, history, reuse and soft-hide semantics.
- `docs/OBSERVABILITY.md` — metrics, worker heartbeats, traces, logs and alerts.
- `docs/ADMIN_SECURITY.md` — admin bootstrap, MFA, permissions, sessions and audit.

## Local development

```bash
cp .env.example .env
docker compose up --build
```

Useful endpoints:

```text
GET    /health/live
GET    /health/ready
GET    /health/operational
GET    /metrics
GET    /mini-app/
GET    /api/v1/generations/models
POST   /api/v1/generations/quote
POST   /api/v1/generations
GET    /api/v1/generations
GET    /api/v1/generations/{generation_id}
GET    /api/v1/generations/{generation_id}/recreate
DELETE /api/v1/generations/{generation_id}/history
POST   /api/v1/generations/{generation_id}/history/restore
POST   /api/v1/uploads/kie
GET    /api/v1/payments/packages
POST   /api/v1/payments
GET    /api/v1/payments/{payment_id}
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

`GENERATION_DAILY_SPEND_LIMIT_CREDITS=0` disables the separate daily-spend quota; wallet balance still applies.

### Observability

```dotenv
LOG_LEVEL=INFO
JSON_LOGS=true
METRICS_ENABLED=true
METRICS_BEARER_TOKEN=<random-monitoring-secret>
WORKER_HEARTBEAT_TTL_SECONDS=180
WORKER_STALE_AFTER_SECONDS=120

OTEL_ENABLED=false
OTEL_SERVICE_NAME=ksu
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces
OTEL_TRACE_SAMPLE_RATIO=0.10
```

Keep `/metrics` on a monitoring/private network where possible even when bearer authentication is configured. `/health/operational` is an alerting endpoint for worker availability; orchestration readiness should remain bound to `/health/ready`.

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
0005_generation_history_state
```

Anti-abuse and observability controls use existing PostgreSQL/Redis infrastructure and add no separate schema migration.

## CI

```text
pip install -e '.[dev]'
ruff check .
python -m compileall -q app tests
node --check app/web/mini_app/app.js
alembic upgrade head
pytest -q
```

CI uses real PostgreSQL and Redis containers.

## Known production limitations / next epics

1. **Provider media URLs are not product-owned durable storage.** Permanent S3-compatible object storage is the next product/infrastructure epic.
2. **No dedicated visual admin client yet.**
3. **Payment chargeback files/settlement registries are not ingested automatically.** Webhook/API-visible refunds are handled; offline acquiring-register reconciliation remains an accounting extension.
4. Compose publishes app port 8000 for development; production must place it behind HTTPS and keep PostgreSQL/Redis private.
5. Proxy-level hard request-body limits remain part of production edge configuration; application upload limits do not replace a reverse-proxy body-size cap.

## External references checked

- OWASP API Security Top 10 2023 — API4 Unrestricted Resource Consumption.
- Redis distributed rate limiting guidance and atomic Lua-based counters.
- PostgreSQL `SKIP LOCKED` queue-style work claiming.
- Kie Market task detail/webhook/upload documentation.
- Crypto Pay API.
- T-Bank Internet Acquiring payment/refund contracts.
- YooKassa payment/refund/idempotency/webhook documentation.
- Telegram Mini Apps documentation.
- Prometheus Python client documentation.
- OpenTelemetry Python SDK, OTLP HTTP exporter and FastAPI/HTTPX instrumentation documentation.
- OWASP ASVS 5.0.0 / Authorization guidance.
