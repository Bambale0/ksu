# KSU production operations runbook

**Status:** matches runtime as of 2026-08-12.

This runbook covers the FastAPI app, Telegram Mini App, PostgreSQL/Redis, durable generation delivery, product-owned media ingestion, payment reconciliation, OWASP API4 resource controls, observability and privileged admin API.

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
   |                              |-- media_assets / media_ingest_jobs
   |                              |-- payment lifecycle
   |
   +--> Redis ------------------> limits / FSM / wake signals / worker telemetry
   |       |
   |       +--> generation-worker --> Kie.ai
   |       +--> media-worker -------> private S3-compatible bucket
   |
   +----------> payment-worker ----> payment providers
```

Compose services:

```text
postgres
redis
app
generation-worker
media-worker
payment-worker
```

Only the HTTPS proxy should be internet-facing. PostgreSQL and Redis must remain private. The media bucket must also remain private; users receive short-lived presigned read capabilities only after ownership checks.

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

Provider and storage credentials are listed in `.env.example`; never reuse them for `ADMIN_SECURITY_KEY`.

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

## 5. Durable media storage configuration

Kie result URLs are temporary ingestion sources. Successful generation state + `media_assets` + `media_ingest_jobs` commit together in PostgreSQL, and `media-worker` performs the external copy later.

```dotenv
S3_BUCKET=ksu-production-media
S3_REGION=us-east-1
S3_ENDPOINT_URL=
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=
S3_SESSION_TOKEN=
S3_ADDRESSING_STYLE=auto
S3_MULTIPART_THRESHOLD_BYTES=8388608
S3_MULTIPART_CHUNK_BYTES=8388608
S3_MAX_CONCURRENCY=4

MEDIA_WORKER_POLL_SECONDS=5
MEDIA_INGEST_LEASE_SECONDS=600
MEDIA_INGEST_MAX_ATTEMPTS=5
MEDIA_INGEST_MAX_BYTES=1073741824
MEDIA_INGEST_CONNECT_TIMEOUT_SECONDS=10
MEDIA_INGEST_READ_TIMEOUT_SECONDS=180
MEDIA_INGEST_MAX_REDIRECTS=5
MEDIA_PRESIGN_TTL_SECONDS=900
MEDIA_LEGACY_RECONCILE_SECONDS=60
```

For AWS S3, prefer workload/IAM credentials and leave `S3_ENDPOINT_URL` empty. For S3-compatible services, use the provider's HTTPS endpoint and required addressing style.

Required deployment controls:

- keep the bucket private;
- scope runtime IAM to the product bucket/prefix;
- configure browser CORS for exact Telegram/web origins that need downloads;
- configure lifecycle `AbortIncompleteMultipartUpload` cleanup for `generations/`;
- monitor media-worker heartbeat and oldest ingest age.

Detailed bucket/CORS/lifecycle examples are in `docs/MEDIA_STORAGE.md`.

## 6. Payment lifecycle configuration

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

## 7. Anti-abuse / OWASP API4 controls

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

Media ingestion also remains durable in PostgreSQL. Redis heartbeat loss can make `/health/operational` degraded, but it does not delete `media_ingest_jobs`.

### Reverse-proxy body limit

Application upload checks happen after multipart reaches FastAPI. Configure an edge/proxy request-body limit consistent with the largest allowed upload so oversized bodies are rejected before application parsing. Application quotas do not replace this edge control.

## 8. Deployment

```bash
git clone <repository-url> ksu
cd ksu
cp .env.example .env
chmod 600 .env

docker compose up -d postgres redis
docker compose build app generation-worker media-worker payment-worker
docker compose run --rm app alembic upgrade head
docker compose up -d app generation-worker media-worker payment-worker
```

Current migration chain:

```text
0001_initial
0002_admin_security
0003_generation_outbox
0004_payment_lifecycle
0005_generation_history_state
0006_durable_media_storage
```

Anti-abuse and observability use current PostgreSQL/Redis infrastructure and add no separate migration.

## 9. Smoke checks

```bash
BASE=https://api.example.com
curl -fsS "$BASE/health/live"
curl -fsS "$BASE/health/ready"
curl -fsS "$BASE/health/operational"
curl -fsSI "$BASE/mini-app/"
curl -fsS "$BASE/api/v1/generations/models"
curl -fsS "$BASE/api/v1/payments/packages"
```

Then use Telegram to verify one model quote, one small upload, one budgeted generation and one low-value test payment. For a successful generation, wait for `result_storage=owned` and verify the owned media opens/downloads before declaring the storage deployment healthy.

### Limit smoke test

In staging only, temporarily lower one limit, exceed it and verify:

```text
HTTP 429
Retry-After: <seconds>
{"code":"resource_limit_exceeded", ...}
```

Temporarily point staging at an unavailable limiter Redis and verify expensive mutation returns `503 protection_backend_unavailable` when fail-closed is enabled.

## 10. Generation incident checks

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

## 11. Media incident checks

Queue summary:

```sql
SELECT status, count(*)
FROM media_ingest_jobs
GROUP BY status;
```

Old/problem work:

```sql
SELECT
  j.asset_id,
  a.generation_id,
  a.user_id,
  a.status AS asset_status,
  j.status AS job_status,
  j.attempts,
  j.available_at,
  j.lease_until,
  j.last_error
FROM media_ingest_jobs j
JOIN media_assets a ON a.id = j.asset_id
WHERE j.status IN ('pending','processing','failed')
ORDER BY j.created_at ASC
LIMIT 100;
```

If storage is intentionally not configured, jobs stay pending without consuming the permanent retry budget. Once `S3_BUCKET` and credentials are configured, the same durable rows resume.

For repeated media failures:

1. verify `media-worker` heartbeat;
2. verify bucket/region/custom endpoint and credentials;
3. check provider URL HTTP state and whether it expired;
4. inspect SSRF/MIME/size rejection messages before widening any limits;
5. never mark a generation failed/refund it solely because durable copying failed;
6. do not manually rewrite object keys unless performing a reviewed data repair.

## 12. Redis anti-abuse keys

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

## 13. Payment incident checks

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

## 14. Backup and restore

PostgreSQL contains wallets, payments, durable generation work and durable media metadata/queue state:

```bash
mkdir -p backups
docker compose exec -T postgres \
  pg_dump -U ksu -d ksu -Fc > "backups/ksu-$(date +%Y%m%d-%H%M%S).dump"
```

Keep off-host copies and regularly restore into a separate test database.

The S3 bucket is a separate durability domain. Configure versioning/replication/backup according to the chosen provider and product retention requirements. A PostgreSQL restore does not restore deleted object bytes by itself.

Redis loss affects FSM, protection state and latency, but not committed PostgreSQL wallet/payment/outbox/media rows.

## 15. Release procedure

1. require green CI;
2. inspect migrations/config changes;
3. back up PostgreSQL;
4. verify bucket policy/CORS/lifecycle before enabling media-worker in production;
5. build images;
6. run migration explicitly;
7. recreate app and all three workers;
8. run health/product/media/limit smoke checks;
9. watch logs, Prometheus and provider dashboards.

```bash
docker compose build app generation-worker media-worker payment-worker
docker compose run --rm app alembic upgrade head
docker compose up -d app generation-worker media-worker payment-worker
docker compose logs --tail=200 app generation-worker media-worker payment-worker
```

Do not automatically run `alembic downgrade` after a failed production release; use a reviewed forward fix or controlled restore when necessary.

## 16. Monitoring priorities

Use `/metrics`, `/health/operational` and `ops/prometheus-alerts.yml` as the baseline. Prioritize:

- API readiness and 5xx ratio;
- generation/media/payment worker heartbeats;
- generation outbox oldest pending age;
- media ingest oldest pending age and failed asset count;
- generation refund/failure spikes;
- Redis availability;
- repeated `resource_limit_exceeded` / `protection_backend_unavailable` events;
- Kie 429/5xx and open circuit events;
- payment reconciliation errors and webhook 4xx/5xx;
- admin auth failures;
- PostgreSQL connections/storage;
- S3 capacity/quota/provider errors and incomplete multipart cleanup.

Never log bearer tokens, Telegram `initData`, provider/S3 secrets, MFA secrets, recovery codes or full presigned query strings.

## 17. CI gate

GitHub Actions validates:

```text
install dependencies
ruff check .
python compileall
node --check app/web/mini_app/app.js
alembic upgrade head on PostgreSQL
pytest on PostgreSQL + Redis
```

Anti-abuse tests use real Redis for Lua counters/TTL/circuit behavior and PostgreSQL for generation admission. Durable-media tests exercise PostgreSQL idempotency/ownership and S3 signing without requiring production object-storage credentials.

## 18. Current gaps / next epic

- full Mini App product shell/navigation is the next P1 epic;
- no visual admin client is bundled yet;
- acquiring settlement/chargeback register ingestion is not automated;
- T-Bank partial merchant refund remains intentionally disabled until receipt/fiscal data is modelled;
- `mypy` is not yet a CI gate.

Official external guidance used by this runbook includes OWASP API Security API4 Unrestricted Resource Consumption, Redis distributed rate limiting, PostgreSQL queue-style `SKIP LOCKED`, Kie task/webhook/upload documentation, AWS S3/Boto3 presigned URL/managed transfer/lifecycle guidance, Telegram Mini Apps, Crypto Pay, T-Bank and YooKassa provider documentation.
