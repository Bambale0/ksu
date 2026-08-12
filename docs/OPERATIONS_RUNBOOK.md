# KSU production operations runbook

**Status:** matches runtime as of 2026-08-12.

This runbook covers the FastAPI app, Telegram Mini App, PostgreSQL/Redis, durable generation delivery, payment reconciliation, OWASP API4 resource controls and privileged admin API.

## 1. Topology

```text
Internet / Telegram
        |
        v
 HTTPS reverse proxy
        |
        v
 app :8000 --------------------> PostgreSQL
   |                              |-- business state
   |                              |-- generation_outbox
   |                              |-- payment lifecycle
   |
   +--> Redis ------------------> limits / FSM / wake signals
   |       |
   |       +--> generation-worker --> Kie.ai
   |
   +----------> payment-worker ----> payment providers
```

Compose services:

```text
postgres
redis
app
generation-worker
payment-worker
```

Only the HTTPS proxy should be internet-facing. PostgreSQL and Redis must remain private.

## 2. External endpoints

Telegram:

```text
POST /webhooks/telegram
```

Kie:

```text
POST /webhooks/kie
```

Payments:

```text
POST /webhooks/payments/cryptobot
POST /webhooks/payments/tbank
POST /webhooks/payments/yookassa
```

Mini App:

```text
GET /mini-app/
```

Kie callback URLs include the local `generation_id`; callback HMAC and authoritative `recordInfo` remain required.

## 3. Core production environment

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://api.example.com
DATABASE_URL=postgresql+asyncpg://ksu:<password>@postgres:5432/ksu
REDIS_URL=redis://redis:6379/0
BOT_TOKEN=...
TELEGRAM_WEBHOOK_URL=https://api.example.com
TELEGRAM_WEBHOOK_SECRET=<random-secret>

INTERNAL_CREDIT_RUB=10
ROX_PACKAGES_JSON={"starter":{"credits":"30","currency":"RUB"}}

ADMIN_SECURITY_KEY=<dedicated-random-secret-32+-chars>
ADMIN_REQUIRE_MFA=true
```

Provider credentials are listed in `.env.example`; never reuse them for `ADMIN_SECURITY_KEY`.

## 4. Generation reliability configuration

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

Generation + wallet debit + PostgreSQL transactional outbox commit together. Redis `wake:generations` is latency optimization only.

## 5. Payment lifecycle configuration

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

`payment-worker` reconciles unknown/pending provider state. Do not manually set payment success/refund state as an incident shortcut.

## 6. Anti-abuse / OWASP API4 controls

Production defaults are explicit and configurable:

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

Operational meaning:

- generation request rate is per authenticated user;
- active-generation cap covers `queued`, `retry`, `submitting`, `generating`;
- daily generation-credit ceiling is optional (`0` disables it);
- upload request rate and bytes/day are per authenticated user;
- Kie upload also keeps global MIME and `KIE_UPLOAD_MAX_BYTES` checks;
- payment creation has a per-user rate in addition to UUID idempotency;
- Kie has a global submission rate and availability circuit breaker;
- `429` responses carry `Retry-After`;
- if `ABUSE_FAIL_CLOSED=true`, inability to verify an expensive user/provider operation through Redis returns/delays with `503`/retry instead of allowing unmetered spend.

### Important Redis-outage distinction

PostgreSQL remains durable business state. If Redis goes down **after** a paid generation has been committed, the generation is not lost. However, with fail-closed protection, `generation-worker` can deliberately postpone a new Kie submission until the protection store recovers. This is expected safety behavior, not an outbox failure.

### Reverse-proxy body limit

Application upload checks happen after multipart reaches FastAPI. Configure an edge/proxy request-body limit consistent with the largest allowed upload so oversized bodies are rejected before application parsing. Application quotas do not replace this edge control.

## 7. Deployment

```bash
git clone <repository-url> ksu
cd ksu
cp .env.example .env
chmod 600 .env

docker compose up -d postgres redis
docker compose build app generation-worker payment-worker
docker compose run --rm app alembic upgrade head
docker compose up -d app generation-worker payment-worker
```

Current migration chain:

```text
0001_initial
0002_admin_security
0003_generation_outbox
0004_payment_lifecycle
```

Anti-abuse uses current PostgreSQL/Redis infrastructure and adds no migration.

## 8. Smoke checks

```bash
BASE=https://api.example.com
curl -fsS "$BASE/health/live"
curl -fsS "$BASE/health/ready"
curl -fsSI "$BASE/mini-app/"
curl -fsS "$BASE/api/v1/generations/models"
curl -fsS "$BASE/api/v1/payments/packages"
```

Then use Telegram to verify one model quote, one small upload, one budgeted generation and one low-value test payment.

### Limit smoke test

In staging only, temporarily lower one limit, exceed it and verify:

```text
HTTP 429
Retry-After: <seconds>
{"code":"resource_limit_exceeded", ...}
```

Temporarily point staging at an unavailable limiter Redis and verify expensive mutation returns `503 protection_backend_unavailable` when fail-closed is enabled.

## 9. Generation incident checks

Outbox summary:

```sql
SELECT status, count(*)
FROM generation_outbox
GROUP BY status;
```

Old work:

```sql
SELECT generation_id, status, attempts, available_at, lease_until, last_error
FROM generation_outbox
WHERE status IN ('pending','processing')
ORDER BY created_at ASC
LIMIT 100;
```

If a generation is delayed with an error mentioning resource/circuit protection:

1. check Redis health;
2. check Kie provider health/429/5xx rate;
3. inspect circuit TTL before forcing anything;
4. do not manually mark the generation failed or create another paid task;
5. let the durable outbox retry after the protection delay.

## 10. Redis anti-abuse keys

Current key families:

```text
abuse:generation:user:<user_uuid>
abuse:upload:req:<user_uuid>
abuse:upload:bytes:<user_uuid>:<utc-date>
abuse:payment:user:<user_uuid>
abuse:provider-submit:kie
abuse:circuit:kie:failures
abuse:circuit:kie:open
```

Do not routinely delete these in production to “fix” throttling. Confirm the underlying traffic/provider incident first.

## 11. Payment incident checks

Creation-intent state:

```sql
SELECT user_id, request_key, provider, package_id, payment_id, status, last_error, created_at
FROM payment_requests
ORDER BY created_at DESC
LIMIT 100;
```

Reversal state:

```sql
SELECT payment_id, provider, amount, credits, reason, provider_event_id, created_at
FROM payment_reversals
ORDER BY created_at DESC
LIMIT 100;
```

Payment `creation_unknown` should be reconciled through the original local intent; never mint a new idempotency key automatically.

## 12. Backup and restore

PostgreSQL contains wallets, payments and durable generation work:

```bash
mkdir -p backups
docker compose exec -T postgres \
  pg_dump -U ksu -d ksu -Fc > "backups/ksu-$(date +%Y%m%d-%H%M%S).dump"
```

Keep off-host copies and regularly restore into a separate test database.

Redis loss affects FSM, protection state and latency, but not committed PostgreSQL wallet/payment/outbox records.

## 13. Release procedure

1. require green CI;
2. inspect migrations/config changes;
3. back up PostgreSQL;
4. build images;
5. run migration explicitly;
6. recreate app and both workers;
7. run health/product/limit smoke checks;
8. watch logs and provider dashboards.

```bash
docker compose build app generation-worker payment-worker
docker compose run --rm app alembic upgrade head
docker compose up -d app generation-worker payment-worker
docker compose logs --tail=200 app generation-worker payment-worker
```

Do not automatically run `alembic downgrade` after a failed production release; use a reviewed forward fix or controlled restore when necessary.

## 14. Monitoring priorities

Until the Observability epic lands, minimally alert on:

- `/health/ready` failures;
- app/generation-worker/payment-worker restart loops;
- generation outbox oldest pending age;
- generation refund/failure spikes;
- Redis availability;
- repeated `resource_limit_exceeded` / `protection_backend_unavailable` events;
- Kie 429/5xx and open circuit events;
- payment reconciliation errors and webhook 4xx/5xx;
- admin auth failures;
- PostgreSQL connections/storage.

Never log bearer tokens, Telegram `initData`, provider secrets, MFA secrets or recovery codes.

## 15. CI gate

GitHub Actions validates:

```text
install dependencies
ruff check .
python compileall
node --check app/web/mini_app/app.js
alembic upgrade head on PostgreSQL
pytest on PostgreSQL + Redis
```

Anti-abuse tests use real Redis for Lua counters/TTL/circuit behavior and PostgreSQL for generation admission.

## 16. Current gaps / next epic

- full metrics/traces/worker heartbeats/alerts are the next P0 Observability epic;
- permanent product-owned media storage is not implemented;
- no visual admin client is bundled yet;
- acquiring settlement/chargeback register ingestion is not automated;
- T-Bank partial merchant refund remains intentionally disabled until receipt/fiscal data is modelled;
- `mypy` is not yet a CI gate.

Official external guidance used by this runbook includes OWASP API Security API4 Unrestricted Resource Consumption, Redis distributed rate limiting, Kie task/webhook/upload documentation, Telegram Mini Apps, Crypto Pay, T-Bank and YooKassa provider documentation.
