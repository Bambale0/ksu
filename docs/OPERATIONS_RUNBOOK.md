# KSU production operations runbook

**Status:** matches the repository runtime as of 2026-08-12.

This runbook covers deployment and operation of the KSU backend, Telegram Mini App, durable generation worker, payment reconciliation/refunds and admin/security API.

Commands assume Docker Compose on Linux behind an HTTPS reverse proxy/load balancer.

## 1. Production topology

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
   |                              |-- payment_requests/reversals
   |
   +--> Redis ------------------> generation-worker --> Kie
   |
   +---------------------------> payment-worker ------> providers
```

Compose services:

```text
postgres
redis
app
generation-worker
payment-worker
```

Production rules:

- expose only the HTTPS reverse proxy;
- keep PostgreSQL/Redis private;
- keep `.env` and Docker socket private;
- maintain off-host PostgreSQL backups;
- synchronize system clocks;
- PostgreSQL is authoritative for money, generation delivery and payment lifecycle;
- Redis generation wake signals are latency optimization, not durable paid-work state.

## 2. External setup

### Telegram

Configure bot token, public HTTPS origin, random `TELEGRAM_WEBHOOK_SECRET`, and optionally BotFather Main Mini App URL.

```text
Mini App: https://api.example.com/mini-app/
Webhook:  https://api.example.com/webhooks/telegram
```

Authenticated REST calls validate `Telegram.WebApp.initData` server-side.

Official reference: https://core.telegram.org/bots/webapps

### Kie.ai

Configure API key and Webhook HMAC key.

```text
https://api.example.com/webhooks/kie
```

The worker adds `?generation_id=<local-uuid>` to callback URLs for crash recovery. Callback HMAC is checked and provider state is then reconciled through Kie `recordInfo`.

Official references:

- https://docs.kie.ai/market/common/get-task-detail
- https://docs.kie.ai/common-api/webhook-verification
- https://docs.kie.ai/file-upload-api/upload-file-stream/

### Crypto Pay

Configure:

```text
https://api.example.com/webhooks/payments/cryptobot
```

The backend validates `crypto-pay-api-signature` over the raw body. `payment-worker` can recover invoice state through `getInvoices` using external invoice ID or local UUID stored in `payload`.

Crypto Pay invoice API has no merchant refund method; do not simulate one by locally changing payment status.

Official reference: https://help.send.tg/en/articles/10279948-crypto-pay-api

### T-Bank Internet Acquiring

Current integration uses:

```text
/v2/Init
/v2/CheckOrder
/v2/GetState
/v2/Cancel
```

Notification URL:

```text
https://api.example.com/webhooks/payments/tbank
```

Successful notification handling returns HTTP 200 body exactly:

```text
OK
```

Full admin refund is implemented through classic `/v2/Cancel` without `Amount`. Admin partial T-Bank refunds are disabled because online-cash-register setups can require a refund `Receipt`, which KSU does not yet model.

Official references:

- https://developer.tbank.ru/eacq/api/init
- https://developer.tbank.ru/eacq/api/check-order
- https://developer.tbank.ru/eacq/api/get-state
- https://developer.tbank.ru/eacq/api/cancel
- https://developer.tbank.ru/eacq/scenarios/cancel_confirm/
- https://developer.tbank.ru/eacq/intro/developer/notification

### YooKassa

Configure payment/refund notifications to the same endpoint:

```text
https://api.example.com/webhooks/payments/yookassa
```

At minimum subscribe to:

```text
payment.succeeded
refund.succeeded
```

The webhook body is not trusted as final accounting truth. The backend re-fetches the payment from YooKassa and uses its authoritative status plus cumulative `refunded_amount`.

Merchant refund API uses `/v3/refunds` with UUID `Idempotence-Key`.

Official references:

- https://yookassa.ru/developers/using-api/interaction-format
- https://yookassa.ru/developers/payment-acceptance/after-the-payment/refund
- https://yookassa.ru/developers/using-api/webhooks

## 3. Production `.env`

Start from `.env.example`.

### Core

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://api.example.com
DATABASE_URL=postgresql+asyncpg://ksu:<strong-password>@postgres:5432/ksu
REDIS_URL=redis://redis:6379/0
BOT_TOKEN=...
TELEGRAM_WEBHOOK_URL=https://api.example.com
TELEGRAM_WEBHOOK_SECRET=<random-secret>
```

### Credits/packages

```dotenv
INTERNAL_CREDIT_RUB=10
START_BALANCE_ROX=0
REFERRAL_FIRST_PERCENT=30
REFERRAL_SECOND_PERCENT=5
ROX_PACKAGES_JSON={"starter":{"credits":"30","currency":"RUB"}}
```

With `INTERNAL_CREDIT_RUB=10`, 30 credits must equal 300 RUB.

### Generation

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
CRYPTOPAY_BASE_URL=https://pay.crypt.bot

TBANK_TERMINAL_KEY=...
TBANK_PASSWORD=...
TBANK_BASE_URL=https://securepay.tinkoff.ru

YOOKASSA_SHOP_ID=...
YOOKASSA_SECRET_KEY=...
YOOKASSA_BASE_URL=https://api.yookassa.ru

PAYMENT_RETURN_URL=https://app.example.com/payment-result
```

`payment-worker` periodically reconciles stale local states:

```text
creating
creation_unknown
pending
refund_review
```

Provider/API failures during reconciliation are logged and retried later; they do not create a second local payment intent.

### Admin security

```dotenv
ADMIN_SECURITY_KEY=<dedicated-random-secret-32+-chars>
ADMIN_BOOTSTRAP_TELEGRAM_IDS=<temporary-initial-owner-id>
ADMIN_REQUIRE_MFA=true
ADMIN_SESSION_TTL_MINUTES=480
ADMIN_IDLE_TIMEOUT_MINUTES=30
ADMIN_STEP_UP_MINUTES=10
```

See `docs/ADMIN_SECURITY.md`.

## 4. Deployment

### First install / update

```bash
git clone <repository-url> ksu
cd ksu
cp .env.example .env
chmod 600 .env
```

Start dependencies:

```bash
docker compose up -d postgres redis
docker compose ps
```

Build and migrate:

```bash
docker compose build app generation-worker payment-worker
docker compose run --rm app alembic upgrade head
```

Current migration chain:

```text
0001_initial
0002_admin_security
0003_generation_outbox
0004_payment_lifecycle
```

Start runtime:

```bash
docker compose up -d app generation-worker payment-worker
docker compose ps
docker compose logs --tail=200 app generation-worker payment-worker
```

## 5. Reverse proxy requirements

The proxy must:

- terminate valid HTTPS;
- preserve provider signature/token headers;
- preserve raw Crypto Pay request body;
- allow upload body sizes consistent with `KIE_UPLOAD_MAX_BYTES`;
- use upload/provider callback timeouts appropriate for the service;
- prevent direct public access to PostgreSQL/Redis.

## 6. Post-deploy smoke checks

```bash
BASE=https://api.example.com
curl -fsS "$BASE/health/live"
curl -fsS "$BASE/health/ready"
curl -fsSI "$BASE/mini-app/"
curl -fsS "$BASE/api/v1/generations/models"
curl -fsS "$BASE/api/v1/payments/packages"
```

### Generation smoke

From Telegram:

1. open Mini App;
2. switch models/scenarios and verify controls;
3. upload small valid media;
4. verify quote/selected settings;
5. run one budgeted test generation;
6. confirm generation reaches terminal result/refund behavior.

### Payment smoke

Use a dedicated low-value package.

Client creation must include a UUID key:

```http
Idempotency-Key: <uuid>
```

Retry the same request with the same key and confirm the same local payment ID is returned rather than another provider intent.

After payment:

```text
GET /api/v1/payments/{payment_id}
```

should eventually show `succeeded`; wallet credit must occur once.

## 7. Generation reliability operations

Normal local flow:

```text
queued -> outbox pending -> leased processing -> submitting -> generating -> succeeded
```

Inspect outbox:

```sql
SELECT status, count(*) FROM generation_outbox GROUP BY status;

SELECT id, generation_id, status, attempts, available_at, lease_until, last_error
FROM generation_outbox
WHERE status IN ('pending','processing')
ORDER BY created_at ASC
LIMIT 100;
```

Redis loss should increase latency only. Paid generation state remains in PostgreSQL.

## 8. Payment lifecycle operations

### Creation idempotency

`payment_requests` is the durable local creation-intent registry.

```sql
SELECT user_id, request_key, provider, package_id, payment_id, status, last_error, created_at
FROM payment_requests
ORDER BY created_at DESC
LIMIT 100;
```

If provider creation returns a transport error after the request may have been accepted, local payment becomes:

```text
creation_unknown
```

Do **not** issue a new key automatically. `payment-worker` attempts provider-specific recovery.

### Provider recovery

Crypto Pay:

```text
external_id known -> getInvoices(invoice_ids=...)
external_id missing -> scan recent invoices for local payload UUID
```

T-Bank:

```text
external_id missing -> CheckOrder(OrderId=<local payment uuid>)
external_id known   -> GetState(PaymentId=...)
```

YooKassa:

```text
external_id missing -> repeat create payment with same provider Idempotence-Key
external_id known   -> GET authoritative payment
```

### Refund/reversal accounting

Inspect reversal ledger:

```sql
SELECT payment_id, provider, amount, credits, reason, provider_event_id, created_at
FROM payment_reversals
ORDER BY created_at DESC
LIMIT 100;
```

Referral reductions:

```sql
SELECT reward_id, payment_reversal_id, amount, created_at
FROM referral_reward_reversals
ORDER BY created_at DESC
LIMIT 100;
```

A provider-confirmed refund can legitimately make a user's credit balance negative if bought credits were already spent. That is accounting debt, not a reason to ignore the provider refund.

### Admin refund/reconcile

Requires privileged admin session, financial permission and fresh MFA step-up:

```text
POST /api/v1/admin/payments/{id}/reconcile
POST /api/v1/admin/payments/{id}/refund
```

Refund request:

```json
{
  "amount":"300.00",
  "request_id":"<uuid-v4>",
  "reason":"Customer refund"
}
```

Support matrix:

```text
YooKassa  partial/full  yes
T-Bank    full only     yes
Crypto Pay refund       no provider API
```

Never manually edit wallet/payment status as a substitute for provider refund/reconciliation.

## 9. Backup/restore

PostgreSQL contains money, outbox and payment lifecycle state. Back up before migrations and on the business RPO schedule.

```bash
mkdir -p backups
docker compose exec -T postgres \
  pg_dump -U ksu -d ksu -Fc > "backups/ksu-$(date +%Y%m%d-%H%M%S).dump"
```

Restore tests must run in a separate database before relying on backups.

Redis persists FSM/wake data but losing Redis must not lose paid generation/payment records.

## 10. Release procedure

1. require green CI;
2. inspect migrations;
3. back up PostgreSQL;
4. pull approved commit/tag;
5. update `.env` if required;
6. build app + both workers;
7. run `alembic upgrade head` explicitly;
8. recreate app/workers;
9. run smoke checks;
10. watch logs and provider dashboards.

```bash
git fetch --all --prune
git checkout <approved-commit-or-tag>
docker compose build app generation-worker payment-worker
docker compose run --rm app alembic upgrade head
docker compose up -d app generation-worker payment-worker
docker compose logs --tail=200 app generation-worker payment-worker
```

## 11. Rollback

If schema change is backward-compatible, roll application images/commit back without downgrading DB.

Do not automatically run `alembic downgrade` after a failed production release. Stop writes and choose a reviewed forward fix or restore if a migration is incompatible.

## 12. Incident playbooks

### Health fails

- inspect `docker compose ps`;
- inspect app/worker logs;
- inspect PostgreSQL/Redis connectivity;
- verify proxy upstream and recent migrations.

### Generation stuck queued

- verify `generation-worker`;
- inspect `generation_outbox` row/lease;
- Redis is secondary;
- do not create another billable generation as repair.

### Generation stuck submitting

- inspect Kie callback/logs;
- do not blindly resubmit uncertain provider requests;
- allow callback recovery/timeout refund.

### Payment stuck `creation_unknown`

- verify `payment-worker` is running;
- inspect provider connectivity/credentials;
- use admin reconcile if needed;
- reuse original payment ID/request key, not a new payment intent.

### Payment stuck `pending`

- inspect provider dashboard and `payment-worker` logs;
- compare local external ID with provider state;
- run authorized admin reconcile;
- never manually mark `succeeded`.

### T-Bank `refund_review`

- inspect provider state/dashboard and original operation;
- this state is intentionally used when a partial refund/reversal cannot be converted to a safe local amount from the currently observed provider payload;
- do not guess the amount;
- resolve through authoritative provider/accounting data.

### YooKassa refund occurred outside KSU

- `refund.succeeded` should trigger provider re-fetch;
- if webhook was lost, `payment-worker` reconciliation reads cumulative `refunded_amount`;
- confirm `payment_reversals` reaches provider cumulative refund amount exactly once.

### Crypto Pay invoice paid but balance not credited

- verify webhook signature delivery;
- inspect `payment-worker` recovery via `getInvoices`;
- remember Crypto Pay can disable webhooks after exhausted retries, so inspect app settings after prolonged incident.

### Refund caused negative credit balance

This can be correct if the user spent credits before the external refund. Do not manually erase the debt. Escalate only if provider reversal amount itself is wrong.

### Admin security incident

Follow `docs/ADMIN_SECURITY.md`, revoke affected sessions/accounts and preserve audit logs.

## 13. Monitoring priorities

Minimum alerts:

- readiness failure/restart loop;
- generation outbox backlog/oldest age/expired leases;
- generation failure/refund spike;
- `payment-worker` restart/reconciliation error rate;
- count/age of `creation_unknown`, `pending`, `refund_review` payments;
- payment reversal volume and negative-wallet events;
- payment webhook 4xx/5xx rate;
- repeated admin auth failures;
- PostgreSQL storage/connection pressure;
- Redis availability/memory pressure.

Never put bearer tokens, Telegram `initData`, provider credentials, MFA secrets or recovery codes into logs/alerts.

## 14. CI/release gate

GitHub Actions validates:

```text
install dependencies
ruff check .
python compileall
node --check app/web/mini_app/app.js
alembic upgrade head on PostgreSQL
pytest on PostgreSQL + Redis
```

## 15. Current operational gaps

- permanent product-owned media/object storage is not implemented;
- anti-abuse/resource limits are the next P0 epic;
- full observability/metrics/tracing is still pending;
- T-Bank partial merchant refunds are intentionally withheld until refund Receipt/fiscal data is modelled;
- Crypto Pay invoice refund is unavailable in provider API;
- acquiring settlement/chargeback register ingestion is not automated;
- no dedicated visual admin client is bundled;
- Compose does not yet define an app healthcheck;
- `mypy` is not a required CI gate.
