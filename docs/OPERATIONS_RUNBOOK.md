# KSU production operations runbook

**Status:** matches the repository runtime as of 2026-08-12.

This runbook covers production deployment and operation of the KSU backend, Telegram Mini App, durable generation outbox/worker, Kie.ai integration, payments and admin/security API.

Commands assume Docker Compose on Linux behind an external HTTPS reverse proxy/load balancer.

## 1. Production topology

```text
Internet / Telegram
        |
        v
 HTTPS reverse proxy
        |
        v
 app :8000
   |      \
   |       +--> PostgreSQL
   |       |      +--> business data
   |       |      +--> generation_outbox (durable work)
   |       |
   |       +--> Redis (FSM + best-effort generation wake signal)
   |       +--> Telegram API
   |       +--> Kie API / Kie upload API
   |       +--> Crypto Pay / T-Bank / YooKassa
   |
   +--> wake:generations
                  |
                  v
          generation-worker
             | DB lease / SKIP LOCKED
             v
             Kie Market
```

Compose services:

```text
postgres
redis
app
generation-worker
```

Production rules:

- only the HTTPS reverse proxy should be internet-facing;
- PostgreSQL and Redis must remain private;
- do not expose `.env` or the Docker socket;
- use persistent volumes and off-host PostgreSQL backups;
- keep system clocks synchronized;
- treat PostgreSQL as the durable source for money, generations and generation delivery state;
- treat Redis generation notifications as latency optimization only.

## 2. Required external setup

### Telegram

Obtain/configure:

- bot token from BotFather;
- public HTTPS origin;
- random `TELEGRAM_WEBHOOK_SECRET`;
- Main Mini App URL if the profile-level launch button is desired.

Mini App URL:

```text
https://api.example.com/mini-app/
```

Telegram webhook:

```text
https://api.example.com/webhooks/telegram
```

Authenticated REST endpoints validate `Telegram.WebApp.initData` server-side. Never replace that with trust in `initDataUnsafe`.

Official reference: https://core.telegram.org/bots/webapps

### Kie.ai

Obtain:

- API key;
- Webhook HMAC key from Kie Settings;
- access to the Kie Market models enabled by the server catalog.

Base callback path:

```text
https://api.example.com/webhooks/kie
```

For every submitted generation the worker actually sends a callback URL containing the local identity:

```text
https://api.example.com/webhooks/kie?generation_id=<local-generation-uuid>
```

That query value is not trusted as proof of success. The handler first verifies Kie webhook HMAC, then uses Kie `recordInfo` for authoritative provider state. The local ID exists so a callback can recover the Kie `taskId` if the worker died after `createTask` was accepted but before the task ID was committed locally.

Official references:

- https://docs.kie.ai/market/common/get-task-detail
- https://docs.kie.ai/common-api/webhook-verification
- https://docs.kie.ai/file-upload-api/upload-file-stream/

### CryptoBot / Crypto Pay

Webhook:

```text
https://api.example.com/webhooks/payments/cryptobot
```

The backend verifies `crypto-pay-api-signature` over the raw body before processing `invoice_paid`.

Official reference: https://help.send.tg/en/articles/10279948-crypto-pay-api

### T-Bank Internet Acquiring

Current backend behavior:

- creates payments with `/v2/Init`;
- sends `NotificationURL={PUBLIC_BASE_URL}/webhooks/payments/tbank`;
- validates notification `Token`, terminal, payment ID and amount;
- accepts `CONFIRMED` as success;
- maps `REJECTED`, `REVERSED`, `CANCELED` to local canceled state when the payment is not already succeeded;
- returns HTTP 200 with body exactly `OK` on successful notification handling.

Official references:

- https://developer.tbank.ru/eacq/api/init
- https://developer.tbank.ru/eacq/intro/developer/notification

### YooKassa

Configure `payment.succeeded` webhook:

```text
https://api.example.com/webhooks/payments/yookassa
```

The backend re-fetches the payment from YooKassa and validates metadata, local/external IDs, amount, currency and authoritative status before crediting the wallet.

Official references:

- https://yookassa.ru/developers/payment-acceptance/getting-started/quick-start
- https://yookassa.ru/developers/using-api/webhooks

## 3. Production `.env`

Start from `.env.example`; never reuse example secrets.

### Core

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://api.example.com
DATABASE_URL=postgresql+asyncpg://ksu:<strong-password>@postgres:5432/ksu
REDIS_URL=redis://redis:6379/0
```

### Telegram

```dotenv
BOT_TOKEN=...
TELEGRAM_WEBHOOK_URL=https://api.example.com
TELEGRAM_WEBHOOK_SECRET=<random-secret>
```

### Internal credits

```dotenv
INTERNAL_CREDIT_RUB=10
START_BALANCE_ROX=0
REFERRAL_FIRST_PERCENT=30
REFERRAL_SECOND_PERCENT=5
ROX_PACKAGES_JSON={"starter":{"credits":"30","currency":"RUB"}}
```

At the default exchange rate, 30 credits must equal 300 RUB. Mismatched amount/credits package configuration is rejected.

### Generation / Kie

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

`GENERATION_PRICING_JSON` uses internal credits. Video values are credits per second; image values are flat per task.

Example:

```dotenv
GENERATION_PRICING_JSON={"wan-2.7-t2v":{"per_second":"8.5"},"gpt-image-2-t2i":{"flat":"18"}}
```

Reliability settings:

- `GENERATION_WORKER_POLL_SECONDS`: maximum normal latency before a worker polls PostgreSQL if no Redis wake is received;
- `GENERATION_OUTBOX_LEASE_SECONDS`: ownership lease for one claimed outbox row;
- `GENERATION_SUBMISSION_MAX_ATTEMPTS`: bound for retryable local submission attempts;
- `GENERATION_SUBMISSION_UNKNOWN_TIMEOUT_SECONDS`: recovery window when provider acceptance may have occurred but no task ID was persisted;
- `GENERATION_RECONCILE_INTERVAL_SECONDS`: periodic recovery pass cadence;
- `GENERATION_RECONCILE_STALE_SECONDS`: age before a generating Kie task is polled as callback fallback;
- `GENERATION_RECOVERY_BATCH_SIZE`: maximum rows handled per recovery scan.

### Payments

```dotenv
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

### Admin security

```dotenv
ADMIN_SECURITY_KEY=<dedicated-random-secret-32+-chars>
ADMIN_BOOTSTRAP_TELEGRAM_IDS=<temporary-initial-owner-id>
ADMIN_REQUIRE_MFA=true
ADMIN_SESSION_TTL_MINUTES=480
ADMIN_IDLE_TIMEOUT_MINUTES=30
ADMIN_STEP_UP_MINUTES=10
ADMIN_LOGIN_RATE_LIMIT_PER_MINUTE=5
ADMIN_REQUEST_RATE_LIMIT_PER_MINUTE=120
ADMIN_LOGIN_MAX_FAILURES=5
ADMIN_LOGIN_LOCK_MINUTES=15
```

Read `docs/ADMIN_SECURITY.md` before bootstrapping owner access.

## 4. First deployment

### Prepare

```bash
git clone <repository-url> ksu
cd ksu
cp .env.example .env
chmod 600 .env
```

Populate production values.

### Start stateful dependencies

```bash
docker compose up -d postgres redis
docker compose ps
```

Both should become healthy.

### Build and migrate

```bash
docker compose build app generation-worker
docker compose run --rm app alembic upgrade head
```

The migration chain currently includes:

```text
0001_initial
0002_admin_security
0003_generation_outbox
```

### Start application processes

```bash
docker compose up -d app generation-worker
docker compose ps
docker compose logs --tail=200 app generation-worker
```

## 5. Reverse proxy / TLS requirements

Production should restrict published port 8000 so only the reverse proxy can access it.

The proxy must:

- terminate valid HTTPS;
- preserve request bodies and required headers;
- allow POST bodies up to the configured media ceiling;
- preserve `X-Telegram-Bot-Api-Secret-Token`;
- preserve `X-Webhook-Timestamp` / `X-Webhook-Signature`;
- preserve `crypto-pay-api-signature`;
- allow payment-provider POST callbacks;
- use upstream timeouts suitable for upload and provider callbacks.

## 6. Post-deploy smoke checklist

```bash
BASE=https://api.example.com
```

### Health

```bash
curl -fsS "$BASE/health/live"
curl -fsS "$BASE/health/ready"
```

Both must return HTTP 200.

### Mini App

```bash
curl -fsSI "$BASE/mini-app/"
```

Expected HTTP 200.

### Model schema

```bash
curl -fsS "$BASE/api/v1/generations/models"
```

Verify non-empty models, `schema_version`, `ui_schema` and expected families.

### Quote

```bash
curl -fsS -X POST "$BASE/api/v1/generations/quote" \
  -H 'Content-Type: application/json' \
  -d '{"model_id":"gpt-image-2-t2i","prompt":"smoke test","parameters":{"aspect_ratio":"1:1"}}'
```

Expected `cost_credits` and `cost_rub`.

### Telegram

From a real Telegram client:

1. open the bot;
2. press **Create content**;
3. confirm Mini App loads;
4. switch model/family and confirm controls update;
5. verify selected-settings summary;
6. upload a small media file to a supported model;
7. run a paid production generation only with an explicit test budget.

## 7. Durable generation worker verification

### Normal lifecycle

```text
queued
  -> outbox pending
  -> outbox processing (leased)
  -> submitting
  -> generating
  -> succeeded

provider failure / unrecoverable submission
  -> failed
  -> idempotent credit refund
```

The generation row, wallet debit and outbox row are committed in one PostgreSQL transaction.

Redis key:

```text
wake:generations
```

is only a wake-up channel. It is safe for a wake signal to be lost because the worker polls the database after a finite timeout.

### Verify worker

```bash
docker compose logs -f generation-worker
```

Database checks during an incident can inspect:

```sql
SELECT status, count(*)
FROM generation_outbox
GROUP BY status;
```

and old outstanding work:

```sql
SELECT id, generation_id, status, attempts, available_at, lease_until, last_error
FROM generation_outbox
WHERE status IN ('pending', 'processing')
ORDER BY created_at ASC
LIMIT 100;
```

### Worker crash behavior

If a worker dies after claiming an outbox row but before provider submission, the lease expires and another worker may reclaim the row.

If the worker dies after Kie accepted `createTask` but before the returned `taskId` is persisted, the backend does **not** blindly resubmit the request. The signed Kie callback can bind its task ID via the callback URL's local `generation_id`. If no callback recovers it before `GENERATION_SUBMISSION_UNKNOWN_TIMEOUT_SECONDS`, the local generation is failed and credits are refunded idempotently.

This avoids double-charging the user and avoids deliberately duplicating provider jobs. It cannot mathematically eliminate the cross-system ambiguity where Kie accepted work but neither its HTTP response nor callback is ever observed.

### Lost/delayed callback behavior

`generation-worker` periodically scans stale `generating` rows with a Kie `external_id` and queries Kie `recordInfo`. Temporary reconciliation failure is logged and does not itself fail/refund the generation.

## 8. Payment smoke and rules

Never test production payment webhooks by bypassing signature checks.

### Crypto Pay

- create a low-value configured package through the normal API/UI;
- pay the invoice normally;
- verify wallet credit occurs once;
- duplicate webhook delivery must not produce a second credit.

### T-Bank

- successful notification must receive body exactly `OK`;
- inspect provider dashboard if notifications retry;
- verify RUB-to-kopeck amount conversion.

### YooKassa

- ensure `payment.succeeded` webhook is registered;
- webhook handling requires outbound access to `api.yookassa.ru` for authoritative re-fetch;
- do not introduce/manual-use an unsafe local "mark succeeded" shortcut.

## 9. Backup procedure

PostgreSQL contains durable business and generation-delivery state. Back it up before migrations and on the business RPO schedule.

```bash
mkdir -p backups
docker compose exec -T postgres \
  pg_dump -U ksu -d ksu -Fc > "backups/ksu-$(date +%Y%m%d-%H%M%S).dump"
```

Keep off-host backups.

Redis contains FSM and best-effort generation wake signals. A Redis data loss can affect active conversational state/latency, but **must not lose a paid generation**, because `generation_outbox` is in PostgreSQL.

## 10. Restore test

Restore into a separate test database:

```bash
docker compose exec -T postgres createdb -U ksu ksu_restore_test || true
cat backups/<backup>.dump | \
  docker compose exec -T postgres pg_restore -U ksu -d ksu_restore_test --clean --if-exists
```

Validate data/schema, then:

```bash
docker compose exec -T postgres dropdb -U ksu ksu_restore_test
```

A production restore is an incident change: stop writes, preserve failed state, restore into a controlled target, validate, then reopen traffic.

## 11. Normal release procedure

1. confirm target CI is green;
2. inspect migrations;
3. take PostgreSQL backup;
4. pull approved commit/tag;
5. update `.env` if required;
6. build images;
7. run migrations explicitly;
8. recreate app and worker;
9. run smoke checklist;
10. watch application/worker logs and provider dashboards.

```bash
git fetch --all --prune
git checkout <approved-commit-or-tag>
docker compose build app generation-worker
docker compose run --rm app alembic upgrade head
docker compose up -d app generation-worker
docker compose ps
docker compose logs --tail=200 app generation-worker
```

## 12. Rollback procedure

### Application-only rollback

If migrations are backward-compatible:

```bash
git checkout <previous-known-good-commit>
docker compose build app generation-worker
docker compose up -d app generation-worker
```

### Migration warning

Do not automatically run `alembic downgrade` after a failed release. If a migration is not backward-compatible, stop writes and choose a reviewed forward fix or pre-deploy restore.

## 13. Incident playbooks

### `/health/live` fails

- inspect `docker compose ps`;
- inspect app logs;
- inspect reverse-proxy upstream;
- identify config/migration crash loops before restart.

### `/health/ready` fails

- check PostgreSQL/Redis health and connectivity;
- inspect URLs/DNS/network;
- do not route full traffic until readiness recovers.

### Mini App authenticated calls return 401

- confirm app was opened through Telegram;
- confirm `BOT_TOKEN` matches the launching bot;
- verify `X-Telegram-Init-Data` is sent;
- verify system clock;
- never bypass with `initDataUnsafe`.

### Media upload fails

- verify `KIE_API_KEY` and outbound access;
- verify `KIE_UPLOAD_BASE_URL`;
- compare file size with global/model limits;
- inspect reverse-proxy body limit.

### Generation stuck `queued`

- verify `generation-worker` is running;
- inspect `generation_outbox` for the generation;
- if outbox is missing, recovery scan should create it automatically;
- inspect `available_at`, `lease_until`, attempts and last error;
- Redis availability is secondary: a Redis outage should increase latency, not lose the job;
- do not create a second billable generation as a repair.

### Outbox stuck `processing`

- compare `lease_until` with current UTC time;
- an expired lease should be reclaimable automatically;
- if leases continually expire, inspect worker crashes and provider submission latency;
- never manually mark payment/generation success merely to clear the row.

### Generation stuck `submitting`

- if no `external_id`, this is the provider ambiguity window;
- inspect recent worker logs and Kie callbacks;
- do not manually resubmit without proving no Kie task exists;
- allow callback recovery / configured timeout handling to decide refund.

### Generation stuck `generating`

- inspect Kie `external_id`;
- verify worker periodic reconciliation is running;
- use the authorized admin reconcile endpoint if necessary;
- verify Kie `recordInfo` and webhook/HMAC configuration.

### Kie callbacks return 403

- verify webhook HMAC configuration/key;
- verify proxy preserves Kie signature headers;
- check server time.

### Crypto Pay webhook failures

- verify HTTPS/webhook URL/token;
- ensure proxy does not alter raw body;
- inspect provider retry/dashboard state.

### T-Bank retries notifications

- endpoint must return HTTP 200 body exactly `OK`;
- inspect token/terminal/amount mismatch;
- verify public HTTPS/proxy timeout.

### YooKassa webhook arrives but balance is not credited

- inspect authoritative re-fetch errors;
- verify shop credentials/outbound API access;
- compare metadata, external ID, amount and currency;
- do not manually set succeeded before resolving mismatch.

### Admin incident

Follow `docs/ADMIN_SECURITY.md`. Revoke affected sessions/accounts and preserve audit logs.

## 14. Monitoring priorities

Minimum useful alerts:

- readiness failure;
- app/worker restart loop;
- `generation_outbox` pending/processing backlog and oldest age;
- expired/repeated outbox leases;
- generations stuck `submitting` near unknown timeout;
- generation failure/refund spike;
- Kie reconciliation error rate;
- payment webhook 4xx/5xx rate;
- repeated admin auth failures/lockouts;
- PostgreSQL storage/connection pressure;
- Redis availability/memory issues.

Never put bearer tokens, Telegram `initData`, payment credentials, MFA secrets or recovery codes into logs/alerts.

## 15. CI/release gate

Current GitHub Actions validates:

```text
install dependencies
ruff check .
python compileall
node --check app/web/mini_app/app.js
alembic upgrade head on PostgreSQL
pytest on PostgreSQL + Redis
```

A green CI run does not replace production provider configuration and smoke tests.

## 16. Current operational gaps

Track these explicitly:

- Kie `createTask` still has an unavoidable cross-system ambiguity if provider acceptance occurs but neither response task ID nor callback is ever observed; local timeout/refund protects the user but provider spend may still exist;
- there is no product-owned permanent object storage for generated/uploaded media;
- no dedicated visual admin client is bundled;
- full payment refund/chargeback reconciliation is a separate next epic;
- Compose does not define an app healthcheck;
- `mypy` is not currently enforced by CI.
