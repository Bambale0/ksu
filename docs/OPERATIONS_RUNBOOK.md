# KSU production operations runbook

**Status:** matches the repository runtime as of 2026-08-11.

This runbook covers production deployment and operation of the current KSU backend, Telegram generation Mini App, Kie generation worker, payment integrations and admin/security API.

It is intentionally operational: commands below assume Docker Compose on a Linux host with an external HTTPS reverse proxy/load balancer.

## 1. Production topology

```text
Internet / Telegram
        |
        v
 HTTPS reverse proxy
        |
        v
 app :8000
   |       \
   |        +--> PostgreSQL
   |        +--> Redis
   |        +--> Telegram API
   |        +--> Kie API / Kie upload API
   |        +--> Crypto Pay / T-Bank / YooKassa
   |
   +--> Redis queue --> generation-worker --> Kie Market
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
- do not expose `.env` or Docker socket;
- use persistent volumes and off-host PostgreSQL backups;
- use a dedicated domain/origin for the service, for example `https://api.example.com`;
- keep system clocks synchronized because Telegram/Kie signatures and payment flows rely on timestamps or signed data.

## 2. Required external setup

Before first deployment obtain/configure:

### Telegram

- bot token from BotFather;
- public HTTPS origin;
- random `TELEGRAM_WEBHOOK_SECRET`;
- Main Mini App URL in BotFather if the profile-level launch button is desired.

Mini App URL:

```text
https://api.example.com/mini-app/
```

The backend also places this URL in the bot's **Create content** WebApp button when `PUBLIC_BASE_URL` is configured.

Telegram requires server-side validation of `Telegram.WebApp.initData`; this project does that on authenticated REST endpoints. Do not replace it with trust in `initDataUnsafe`.

Official reference: https://core.telegram.org/bots/webapps

### Kie.ai

Obtain:

- API key;
- Webhook HMAC key from Kie Settings;
- access to Kie Market models used by the server catalog.

Enable Kie Webhook HMAC verification in production and set the same key in `KIE_WEBHOOK_HMAC_KEY`.

Current callback path:

```text
https://api.example.com/webhooks/kie
```

The worker supplies this URL as `callBackUrl` for Kie Market tasks. The callback handler verifies HMAC and then queries `/api/v1/jobs/recordInfo` for authoritative task state.

Official references:

- https://docs.kie.ai/market/common/get-task-detail
- https://docs.kie.ai/common-api/webhook-verification
- https://docs.kie.ai/file-upload-api/upload-file-stream/

### CryptoBot / Crypto Pay

Create a Crypto Pay application and set its webhook URL to:

```text
https://api.example.com/webhooks/payments/cryptobot
```

Production base URL:

```text
https://pay.crypt.bot
```

The backend validates `crypto-pay-api-signature` over the raw request body before processing `invoice_paid`.

Operational note: Crypto Pay API 1.5.2 documents extended webhook retries and automatic webhook disabling after all retries fail. Monitor webhook delivery after incidents.

Official reference: https://help.send.tg/en/articles/10279948-crypto-pay-api

### T-Bank Internet Acquiring

Obtain terminal key/password and ensure the terminal accepts HTTPS notifications.

Current backend behavior:

- creates payments with `/v2/Init`;
- sends `NotificationURL={PUBLIC_BASE_URL}/webhooks/payments/tbank`;
- validates notification `Token`, terminal, payment ID and amount;
- accepts `CONFIRMED` as success;
- maps `REJECTED`, `REVERSED`, `CANCELED` to local canceled state;
- responds to a successfully processed notification with HTTP 200 and body exactly `OK`.

Official references:

- https://developer.tbank.ru/eacq/api/init
- https://developer.tbank.ru/eacq/intro/developer/notification

### YooKassa

Obtain shop ID and secret key and configure a `payment.succeeded` webhook to:

```text
https://api.example.com/webhooks/payments/yookassa
```

The backend does not trust the incoming webhook object as final truth. It retrieves the payment from YooKassa again and checks metadata, local/external IDs, amount, currency and authoritative status before wallet credit.

Official references:

- https://yookassa.ru/developers/payment-acceptance/getting-started/quick-start
- https://yookassa.ru/developers/using-api/webhooks

## 3. Production `.env`

Start from `.env.example`; never use example secrets verbatim.

### Core

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://api.example.com
DATABASE_URL=postgresql+asyncpg://ksu:<strong-password>@postgres:5432/ksu
REDIS_URL=redis://redis:6379/0
```

`PUBLIC_BASE_URL` must be the externally reachable HTTPS origin. It is used for:

- Mini App WebApp button;
- Kie callback URL;
- T-Bank NotificationURL;
- fallback payment return URL if `PAYMENT_RETURN_URL` is empty.

### Telegram

```dotenv
BOT_TOKEN=...
TELEGRAM_WEBHOOK_URL=https://api.example.com
TELEGRAM_WEBHOOK_SECRET=<random-secret>
```

`TELEGRAM_WEBHOOK_URL` is an origin, not the full `/webhooks/telegram` path. The application appends that path during startup.

### Internal credits

```dotenv
INTERNAL_CREDIT_RUB=10
START_BALANCE_ROX=0
REFERRAL_FIRST_PERCENT=30
REFERRAL_SECOND_PERCENT=5
ROX_PACKAGES_JSON={"starter":{"credits":"30","currency":"RUB"}}
```

With `INTERNAL_CREDIT_RUB=10`, `30` credits must cost `300 RUB`. The backend rejects mismatched package amount/credits pairs.

### Generation / Kie

```dotenv
KIE_API_KEY=...
KIE_BASE_URL=https://api.kie.ai
KIE_UPLOAD_BASE_URL=https://kieai.redpandaai.co
KIE_UPLOAD_MAX_BYTES=104857600
KIE_WEBHOOK_HMAC_KEY=...
GENERATION_PRICING_JSON={}
```

`GENERATION_PRICING_JSON` overrides product prices. Video values are internal credits **per second**; image values are flat internal credits per task.

Example:

```dotenv
GENERATION_PRICING_JSON={"wan-2.7-t2v":{"per_second":"8.5"},"gpt-image-2-t2i":{"flat":"18"}}
```

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

For YooKassa, either `PAYMENT_RETURN_URL` or `PUBLIC_BASE_URL` must be configured.

### Admin security

```dotenv
ADMIN_SECURITY_KEY=<dedicated random secret, at least 32 chars>
ADMIN_BOOTSTRAP_TELEGRAM_IDS=<temporary initial owner ID>
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

### 4.1 Prepare files

```bash
git clone <repository-url> ksu
cd ksu
cp .env.example .env
chmod 600 .env
```

Populate `.env` with production values.

### 4.2 Start stateful dependencies

```bash
docker compose up -d postgres redis
```

Check:

```bash
docker compose ps
```

Both services should become healthy.

### 4.3 Apply migrations explicitly

For production, migrate before replacing app/worker:

```bash
docker compose build app generation-worker
docker compose run --rm app alembic upgrade head
```

The Compose `app` command also runs `alembic upgrade head`, but the explicit production migration step gives a clear failure boundary and avoids relying on container start order.

### 4.4 Start application processes

```bash
docker compose up -d app generation-worker
```

### 4.5 Inspect startup

```bash
docker compose ps
docker compose logs --tail=200 app generation-worker
```

If `BOT_TOKEN` + `TELEGRAM_WEBHOOK_URL` are valid, app startup calls Telegram `setWebhook` automatically.

## 5. Reverse proxy / TLS requirements

The current Compose file publishes `8000:8000`; treat that as development-friendly wiring. In production restrict host/network access so only the reverse proxy can reach port 8000.

Required proxy behavior:

- terminate valid HTTPS;
- preserve normal request bodies and headers;
- allow POST bodies large enough for the configured upload ceiling;
- do not strip `X-Telegram-Bot-Api-Secret-Token`;
- do not strip `X-Webhook-Timestamp` / `X-Webhook-Signature`;
- preserve `crypto-pay-api-signature`;
- allow payment provider POSTs;
- set sensible upstream timeouts for file upload and provider callback processing.

Do not put secrets in query strings.

## 6. Post-deploy smoke checklist

Set:

```bash
BASE=https://api.example.com
```

### Liveness

```bash
curl -fsS "$BASE/health/live"
```

Expected: HTTP 200.

### Readiness

```bash
curl -fsS "$BASE/health/ready"
```

Expected: HTTP 200 with PostgreSQL and Redis ready.

### Mini App asset

```bash
curl -fsSI "$BASE/mini-app/"
```

Expected: HTTP 200.

### Model schema

```bash
curl -fsS "$BASE/api/v1/generations/models"
```

Verify:

- non-empty `models`;
- `schema_version` present;
- every model contains `ui_schema`;
- expected families appear.

### Quote

Use a currently enabled model ID from the catalog rather than assuming a stale ID:

```bash
curl -fsS -X POST "$BASE/api/v1/generations/quote" \
  -H 'Content-Type: application/json' \
  -d '{"model_id":"gpt-image-2-t2i","prompt":"smoke test","parameters":{"aspect_ratio":"1:1"}}'
```

Expected: quote with `cost_credits` and `cost_rub`.

### Telegram

From a real Telegram client:

1. Open the bot.
2. Press **Create content**.
3. Confirm Mini App loads without leaving Telegram.
4. Change model/family and verify fields update.
5. Confirm selected-settings summary matches visible values.
6. For an authenticated upload field, upload a small test image.
7. Do not run a paid generation in production unless an explicit test budget is intended.

## 7. Generation worker verification

Watch:

```bash
docker compose logs -f generation-worker
```

The worker consumes Redis list:

```text
queue:generations
```

Expected lifecycle:

```text
queued -> submitting -> generating -> succeeded
                                  \-> failed -> idempotent refund
```

Kie callback handling performs a `recordInfo` reconciliation before applying provider result.

### Known queue durability limitation

Current creation order is:

```text
DB generation + wallet debit
COMMIT
Redis RPUSH
```

There is no transactional outbox yet. A process crash after DB commit but before Redis enqueue can leave a paid generation stuck in `queued` with no queue message.

Incident guidance:

- do not debit the user again;
- do not assume restarting Redis/worker repairs a missing enqueue;
- verify whether a Kie external task exists before any repair;
- if no provider task exists, repair/requeue only through a reviewed maintenance action that preserves the existing generation ID and charge idempotency;
- prioritize implementation of a transactional outbox/reconciliation job before high-volume production.

## 8. Payment smoke and production rules

Never test production payment webhooks by manually posting a fake `succeeded` body and then bypassing signature checks.

### Crypto Pay

- create a low-value allowed package through the normal API/UI;
- pay the provider invoice normally;
- verify the webhook arrives and wallet credit occurs once;
- resend/duplicate delivery must not produce a second credit.

The provider signs the raw body. Reverse proxies/body parsers must not transform the body before FastAPI receives it.

### T-Bank

- successful notification must receive body `OK` exactly;
- check provider dashboard if notifications are retrying;
- verify local amount in RUB became provider amount in kopecks correctly.

### YooKassa

- ensure `payment.succeeded` webhook is registered;
- the backend re-fetches payment state from YooKassa, so outbound access to `api.yookassa.ru` is required even while handling inbound webhook;
- do not introduce a future admin button that blindly sets local payment status to succeeded.

## 9. Backup procedure

At minimum back up PostgreSQL before migrations and on a schedule appropriate for business RPO.

Example logical backup:

```bash
mkdir -p backups
docker compose exec -T postgres \
  pg_dump -U ksu -d ksu -Fc > "backups/ksu-$(date +%Y%m%d-%H%M%S).dump"
```

Also back up off-host; the same server/volume is not a disaster-recovery backup.

Redis contains FSM and generation queue state. AOF is enabled in Compose, but PostgreSQL remains the primary source for durable business records. Preserve Redis persistence/volume during normal upgrades.

## 10. Restore test procedure

Test restores regularly into a separate database, not directly over production.

Example:

```bash
docker compose exec -T postgres createdb -U ksu ksu_restore_test || true
cat backups/<backup>.dump | \
  docker compose exec -T postgres pg_restore -U ksu -d ksu_restore_test --clean --if-exists
```

Validate schema/data, then remove the test database:

```bash
docker compose exec -T postgres dropdb -U ksu ksu_restore_test
```

A real production restore should be treated as an incident change: stop app/worker writes, preserve the failed database, restore into a controlled target, validate, then reopen traffic.

## 11. Normal release procedure

1. Confirm target commit/PR CI is green.
2. Read migration diff if migrations changed.
3. Take PostgreSQL backup.
4. Pull/checkout target commit.
5. Update `.env` only if required by the release.
6. Build images.
7. Run migrations explicitly.
8. Start/recreate `app` and `generation-worker`.
9. Run smoke checklist.
10. Watch app/worker logs and provider webhook dashboards.

Commands:

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

If the database migration is backward-compatible:

```bash
git checkout <previous-known-good-commit>
docker compose build app generation-worker
docker compose up -d app generation-worker
```

Run all smoke checks.

### Migration rollback warning

Do **not** automatically run `alembic downgrade` in production just because an app release failed. A downgrade can destroy data or be incompatible with writes already made by the new version.

If a migration is not backward-compatible:

1. stop writes/app/worker;
2. assess migration and written data;
3. either deploy a forward fix or restore the pre-deploy backup;
4. validate before reopening traffic.

Forward fixes are generally safer after production data has been written.

## 13. Incident playbooks

### `/health/live` fails

- inspect `docker compose ps`;
- inspect app logs;
- check reverse proxy upstream;
- restart only after identifying whether crash loop is configuration/migration related.

### `/health/ready` fails

- check PostgreSQL health/connectivity;
- check Redis health/connectivity;
- inspect connection strings/DNS/network;
- do not route full traffic until ready succeeds.

### Mini App loads but authenticated API calls return 401

- confirm it was opened from Telegram, not a normal browser tab;
- confirm `BOT_TOKEN` matches the bot that launched the Mini App;
- verify frontend sends `X-Telegram-Init-Data`;
- verify server clock;
- do not bypass validation with `initDataUnsafe`.

### Media upload fails

- check `KIE_API_KEY` and outbound connectivity;
- check `KIE_UPLOAD_BASE_URL`;
- compare file size with global `KIE_UPLOAD_MAX_BYTES` and model-specific UI limit;
- check reverse proxy request-body limit;
- remember Kie upload URLs are temporary provider assets.

### Generation stuck in `queued`

- verify worker is running;
- inspect worker logs;
- inspect Redis availability;
- consider the documented DB-commit/Redis-enqueue gap;
- do not create a second billable generation as a repair without reconciling the original.

### Generation stuck in `generating`

- inspect stored Kie `external_id`;
- use the existing admin reconcile endpoint if authorized;
- verify Kie `recordInfo` availability;
- check callback/HMAC configuration.

### Kie callbacks return 403

- verify Kie Settings webhook HMAC is enabled;
- verify `KIE_WEBHOOK_HMAC_KEY` matches exactly;
- check proxy preserves `X-Webhook-Timestamp` and `X-Webhook-Signature`;
- check server time.

### Crypto Pay webhook failures

- verify webhook URL and HTTPS;
- verify token belongs to that Crypto Pay application;
- ensure proxy does not alter raw body;
- inspect Crypto Pay dashboard because repeated failures can eventually disable webhook delivery.

### T-Bank retries notifications

- verify endpoint returns HTTP 200 body exactly `OK`;
- inspect token/terminal/amount mismatch logs;
- verify public HTTPS URL and proxy timeout;
- compare with T-Bank notification archive/dashboard.

### YooKassa webhook arrives but balance is not credited

- inspect authoritative provider re-fetch failure;
- verify shop ID/secret and outbound API access;
- compare payment metadata `payment_id`, external ID, amount and currency;
- do not manually set local succeeded state before resolving mismatch.

### Admin credential/session incident

Follow `docs/ADMIN_SECURITY.md`.

At minimum:

- disable/revoke affected admin sessions/accounts;
- preserve audit logs;
- rotate compromised provider-specific credentials;
- treat `ADMIN_SECURITY_KEY` rotation specially because it affects session token verification, audit HMAC verification and encrypted MFA secrets.

## 14. Monitoring priorities

Minimum useful alerts:

- `/health/ready` failure;
- app/worker restart loop;
- generation failures/refund spike;
- `queued` generations older than an operational threshold;
- payment webhook 4xx/5xx rate;
- repeated admin auth failures/lockouts;
- active admins without MFA;
- large wallet adjustments;
- withdrawal status changes;
- PostgreSQL storage/connection exhaustion;
- Redis memory/persistence issues.

Do not include raw bearer tokens, Telegram `initData`, payment credentials, MFA secrets or recovery codes in logs/alerts.

## 15. CI/release gate

Current GitHub Actions gate:

```text
install dependencies
ruff check .
python compileall
node --check app/web/mini_app/app.js
alembic upgrade head on real PostgreSQL
pytest on PostgreSQL + Redis
```

A green CI run verifies the tested code/migration path, but it does not replace production smoke tests or provider sandbox/live configuration checks.

## 16. Current known operational gaps

Track these explicitly:

- generation DB commit and Redis enqueue are not transactional;
- there is no product-owned permanent object storage for generated/uploaded media;
- no dedicated visual admin client is bundled;
- payment state does not currently have a generic admin/provider reconciliation button; this is intentional to avoid unsafe manual success overrides, but operational reconciliation tooling may be added later;
- Compose does not define an app healthcheck, so orchestration uses process start rather than application readiness for `generation-worker` dependency;
- `mypy` is not currently enforced by CI.

Do not hide these gaps in operational documentation; they determine incident behavior and release risk.
