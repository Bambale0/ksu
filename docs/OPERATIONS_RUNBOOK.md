# KSU / ROXY production operations runbook

**Status:** synchronized with shipped runtime on 2026-08-20.  
**Runtime baseline:** `main` after generation recovery hardening `fa787db146f713b8f6568f037dd2d1ca17c2c68c`.

This runbook covers the FastAPI app, Telegram Mini App, PostgreSQL/Redis, durable generation delivery, product-owned media ingestion, payment reconciliation, creator partnership worker, abuse protection, observability and privileged admin surfaces.

## 1. Topology

```text
Internet / Telegram
        |
        v
 HTTPS reverse proxy
        |
        v
 app :8000 --------------------------> PostgreSQL
   |                                  |-- business state / wallets
   |                                  |-- generation_outbox
   |                                  |-- media_assets / media_ingest_jobs
   |                                  |-- payment lifecycle
   |                                  |-- admin / feed / partner state
   |
   +--> Redis -----------------------> rate limits / FSM / wake signals / worker telemetry
   |       |
   |       +--> generation-worker ------> Kie.ai
   |       +--> media-worker -----------> private S3-compatible bucket
   |
   +----------> payment-worker ---------> payment providers
   +----------> creator-partnership-worker
```

Current compose services:

```text
postgres
redis
app
generation-worker
media-worker
payment-worker
creator-partnership-worker
```

Only the HTTPS proxy should be internet-facing. PostgreSQL and Redis remain private. Product media storage must remain private; user access uses short-lived presigned capabilities after ownership checks.

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

Primary hosted card checkout uses its configured provider callback route documented in `PRIMARY_CARD_CHECKOUT.md` / `WALLET_PAYMENTS.md`.

Product surfaces:

```text
GET /mini-app/
GET /admin-app/
```

Kie callback URLs may include the local `generation_id` for recovery correlation. HMAC validation remains required when configured, and authoritative provider status lookup is the final task-state source rather than callback payload fields alone.

## 3. Core production environment

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://api.example.com
DATABASE_URL=postgresql+asyncpg://ksu:<password>@postgres:5432/ksu
REDIS_URL=redis://redis:6379/0
BOT_TOKEN=...
TELEGRAM_WEBHOOK_URL=https://api.example.com
TELEGRAM_WEBHOOK_SECRET=<random-secret>

# Public economy: 1 ROX = 1 RUB.
INTERNAL_CREDIT_RUB=1
START_BALANCE_ROX=50
INVITE_BONUS_ROX=30
PROMPT_REPEAT_BONUS_ROX=5
ROX_PACKAGES_JSON={}

ADMIN_SECURITY_KEY=<dedicated-random-secret-32+-chars>
ADMIN_REQUIRE_MFA=true
```

Provider/storage credentials are listed in `.env.example`. The example file must contain placeholders only; never commit a live provider/payment credential. Do not reuse provider secrets as `ADMIN_SECURITY_KEY`.

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
GENERATION_HARD_TIMEOUT_SECONDS=7200
GENERATION_RECONCILE_INTERVAL_SECONDS=60
GENERATION_RECONCILE_STALE_SECONDS=60
GENERATION_RECOVERY_BATCH_SIZE=50
```

Generation + wallet debit + PostgreSQL transactional outbox commit together. Redis `wake:generations` is a latency optimization only.

Recovery rules:

- terminal `succeeded` / `failed` states are monotonic;
- permanent validation/auth rejection fails/refunds immediately;
- explicit provider `429` is retryable;
- timeout, transport, 5xx and malformed-success outcomes are treated as uncertain because a billable task may already exist;
- uncertain submissions remain `submitting` and are **not** blindly resubmitted;
- callback/reconciliation may bind the provider task ID later;
- unresolved uncertain submissions fail/refund once after `GENERATION_SUBMISSION_UNKNOWN_TIMEOUT_SECONDS`;
- active provider work exceeding `GENERATION_HARD_TIMEOUT_SECONDS` fails/refunds once;
- a provider success without usable result media is not finalized as a charged empty success.

Do not manually retry `createTask` for an uncertain generation. Doing so can create two paid provider tasks for one local debit.

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

For AWS S3, prefer workload/IAM credentials and leave `S3_ENDPOINT_URL` empty. For S3-compatible services, use the provider HTTPS endpoint and required addressing style.

Required deployment controls:

- keep the bucket private;
- scope runtime IAM to the product bucket/prefix;
- configure browser CORS for exact Telegram/web origins that need downloads;
- configure lifecycle cleanup for incomplete multipart uploads;
- monitor media-worker heartbeat and oldest ingest age.

Detailed storage guidance is in `docs/MEDIA_STORAGE.md`.

## 6. Payment lifecycle configuration

```dotenv
PAYMENT_RECONCILE_INTERVAL_SECONDS=60
PAYMENT_RECONCILE_STALE_SECONDS=30
PAYMENT_RECONCILE_BATCH_SIZE=100

CARD_API_KEY=...
CARD_API_BASE_URL=https://gate.lava.top
CARD_WEBHOOK_KEY=...
CARD_OFFER_ID=...
CARD_PACKAGES_JSON={}
CARD_PAYMENT_ROUTE_BY_CURRENCY_JSON={}

CRYPTOPAY_API_TOKEN=...
TBANK_TERMINAL_KEY=...
TBANK_PASSWORD=...
YOOKASSA_SHOP_ID=...
YOOKASSA_SECRET_KEY=...
PAYMENT_RETURN_URL=https://app.example.com/payment-result
```

`payment-worker` reconciles unknown/pending provider state. Never manually mark payment success/refund as an incident shortcut. Amount, currency and provider identity must be bound to the original durable local payment intent.

## 7. Creator partnership worker

```dotenv
CREATOR_PARTNERSHIP_GRANT_INTERVAL_SECONDS=3600
```

Creator/influencer grants are spend-only ROX and are separate from withdrawable referral earnings. The worker is idempotent per agreement/period; do not manually duplicate a grant when troubleshooting delayed worker execution.

## 8. Anti-abuse / OWASP API4 controls

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
- daily generation spend ceiling is expressed in public ROX after migration `0023`; `0` disables it;
- upload request rate and bytes/day are per authenticated user;
- Kie upload keeps MIME and `KIE_UPLOAD_MAX_BYTES` checks;
- payment creation has a per-user rate in addition to UUID idempotency;
- Kie has a global submission rate and availability circuit breaker;
- `429` responses carry `Retry-After`;
- with `ABUSE_FAIL_CLOSED=true`, inability to verify an expensive operation through Redis returns/delays rather than allowing unmetered spend.

### Redis-outage distinction

PostgreSQL remains durable business state. If Redis fails **after** a paid generation is committed, the generation is not lost. With fail-closed protection, `generation-worker` can deliberately postpone a new Kie submission until the protection store recovers. This is expected safety behavior.

Media ingestion also remains durable in PostgreSQL. Redis heartbeat loss can make `/health/operational` degraded but does not delete media jobs.

### Reverse-proxy body limit

Application upload checks happen after multipart reaches FastAPI. Configure an edge/proxy request-body limit consistent with the largest allowed upload so oversized bodies are rejected before application parsing.

## 9. Deployment

```bash
git clone <repository-url> ksu
cd ksu
cp .env.example .env
chmod 600 .env

docker compose up -d postgres redis
docker compose build app generation-worker media-worker payment-worker creator-partnership-worker
docker compose run --rm app alembic upgrade head
docker compose up -d app generation-worker media-worker payment-worker creator-partnership-worker
```

The production workflow under `.github/workflows/` is preferred for real releases because it resolves an exact `main` SHA, requires green release workflows and performs health/release verification. See `docs/GITHUB_PRODUCTION_DEPLOY.md`.

Current Alembic chain reaches:

```text
0001_initial
...
0020_batch_generation
0021_batch_generation_items
0022_batch_generation_commands
0023_roxy_one_ruble_denomination
0024_creator_partnership
0025_partner_wallet_transfers
```

Always run `alembic upgrade head`; do not hard-code `0025` as a deployment target because later migrations may be added.

## 10. Smoke checks

```bash
BASE=https://api.example.com
curl -fsS "$BASE/health/live"
curl -fsS "$BASE/health/ready"
curl -fsS "$BASE/health/operational"
curl -fsSI "$BASE/mini-app/"
curl -fsS "$BASE/api/v1/generations/models"
curl -fsS "$BASE/api/v1/payments/packages"
```

Then use Telegram to verify one model quote, one small upload, one budgeted generation and one low-value test payment. For a successful generation, wait for product-owned media state and verify the owned media opens/downloads before declaring storage healthy.

### Limit smoke test

In staging only, temporarily lower one limit, exceed it and verify:

```text
HTTP 429
Retry-After: <seconds>
{"code":"resource_limit_exceeded", ...}
```

Temporarily point staging at an unavailable limiter Redis and verify expensive mutation returns the expected protection-backend failure when fail-closed is enabled.

## 11. Generation incident checks

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

Generation state overview:

```sql
SELECT id, status, provider, external_id, created_at, updated_at, error
FROM generations
WHERE status IN ('queued','retry','submitting','generating')
ORDER BY created_at ASC
LIMIT 100;
```

If a generation is delayed:

1. check Redis and generation-worker heartbeat;
2. check Kie 429/5xx/provider health;
3. inspect whether the local state is `submitting` with no `external_id` before doing anything;
4. for uncertain submission, **do not create another provider task manually**;
5. allow callback/reconciliation and the configured unknown-submission timeout to decide the outcome;
6. for old `generating` work, compare provider status and `GENERATION_HARD_TIMEOUT_SECONDS`;
7. never manually credit a refund when the idempotent generation refund path can perform it.

## 12. Media incident checks

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

If storage is intentionally not configured, durable jobs can remain pending until configuration is restored.

For repeated media failures:

1. verify media-worker heartbeat;
2. verify bucket/region/custom endpoint and credentials;
3. check provider URL HTTP state and whether it expired;
4. inspect SSRF/MIME/size rejection messages before widening any limits;
5. never mark a generation failed/refund it solely because durable copying failed;
6. do not manually rewrite object keys without a reviewed repair plan.

## 13. Redis anti-abuse keys

Current key families include:

```text
abuse:generation:user:<user_uuid>
abuse:upload:req:<user_uuid>
abuse:upload:bytes:<user_uuid>:<utc-date>
abuse:payment:user:<user_uuid>
abuse:provider-submit:kie
abuse:circuit:kie:failures
abuse:circuit:kie:open
```

Do not routinely delete these in production to bypass throttling. Confirm the underlying traffic/provider incident first.

## 14. Payment incident checks

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

`creation_unknown` must be reconciled through the original local intent; never mint a new idempotency key automatically just because the provider create response was lost.

## 15. Backup and restore

PostgreSQL contains wallets, payments, durable generation work, media metadata/queue state, partner/admin/feed state:

```bash
mkdir -p backups
docker compose exec -T postgres \
  pg_dump -U ksu -d ksu -Fc > "backups/ksu-$(date +%Y%m%d-%H%M%S).dump"
```

Validate backups and keep off-host copies. Regularly restore into a separate test database.

The media bucket is a separate durability domain. Configure versioning/replication/backup according to the storage provider and product retention requirements. A PostgreSQL restore does not restore deleted object bytes.

Redis loss affects FSM, protection state and latency, not committed PostgreSQL wallet/payment/outbox/media rows.

## 16. Release procedure

1. require green CI / required workflows for the exact release SHA;
2. inspect migrations and configuration changes;
3. confirm maintained docs and `.env.example` match the runtime change;
4. back up PostgreSQL;
5. verify storage policy/CORS/lifecycle when media behavior changed;
6. build images;
7. run migration explicitly;
8. recreate app and current workers;
9. run health/product/media/payment/recovery smoke checks;
10. watch logs, metrics and provider dashboards.

```bash
docker compose build app generation-worker media-worker payment-worker creator-partnership-worker
docker compose run --rm app alembic upgrade head
docker compose up -d app generation-worker media-worker payment-worker creator-partnership-worker
docker compose logs --tail=200 app generation-worker media-worker payment-worker creator-partnership-worker
```

Do not automatically run `alembic downgrade` after a failed production release; use a reviewed forward fix or controlled restore when necessary.

## 17. Monitoring priorities

Use `/metrics`, `/health/operational` and `ops/prometheus-alerts.yml` as the baseline. Prioritize:

- API readiness and 5xx ratio;
- generation/media/payment/creator worker heartbeats where published;
- generation outbox oldest pending age;
- generations stuck in `submitting` / `generating`;
- media ingest oldest pending age and failed asset count;
- generation refund/failure spikes;
- Redis availability;
- repeated resource/protection errors;
- Kie 429/5xx and open circuit events;
- payment reconciliation errors and webhook 4xx/5xx;
- admin auth failures;
- PostgreSQL connections/storage;
- S3 capacity/quota/provider errors and incomplete multipart cleanup.

Never log bearer tokens, Telegram `initData`, provider/S3/payment secrets, MFA secrets, recovery codes or full presigned query strings.

## 18. CI gate

GitHub Actions validates the repository with Ruff, Python compile checks, Mini App/Admin JavaScript syntax checks, Alembic migration on PostgreSQL and the full regression suite. Focused generation tests protect outbox recovery, terminal monotonicity, uncertain submissions, stale Kie HMAC callbacks and refund exactly-once behavior.

Release-specific workflow requirements are documented in `docs/GITHUB_PRODUCTION_DEPLOY.md` and `docs/ROXY_RELEASE_ACCEPTANCE.md`.

## 19. Known intentionally constrained behavior

- T-Bank partial merchant refund remains guarded/review-oriented until receipt/fiscal semantics are safely modelled.
- `mypy` is not currently an enforced CI gate unless the workflow is explicitly changed.
- Provider/API capabilities are exposed only when they have a real mapped and tested backend contract; historical parity documents do not authorize a model or operation by themselves.

For current product/runtime truth, follow `docs/README.md`, `docs/CURRENT_STATE.md`, this runbook and the tested server contracts. Historical `parity-*` files are implementation records only.
