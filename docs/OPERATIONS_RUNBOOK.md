# KSU / ROXY production operations runbook

**Status:** synchronized with the current ROXY runtime and migration chain as of 2026-08-20.

This is the maintained operational source of truth for deployment, health checks, generation recovery, media durability, PostgreSQL backups, payment reconciliation, referral admission controls and incident response. Historical epic notes must not override this file.

## 1. Runtime topology

```text
Internet / Telegram
        |
        v
 HTTPS reverse proxy
        |
        v
 app :8000 --------------------------> PostgreSQL
   |                                  |-- users / wallets / payments
   |                                  |-- generation_outbox
   |                                  |-- media_assets / media_ingest_jobs
   |                                  |-- feed / partner / admin state
   |                                  |-- referral_events
   |
   +--> Redis -----------------------> rate limits / FSM / wake signals / telemetry
   |       |
   |       +--> generation-worker ------> Kie.ai
   |       +--> media-worker -----------> private S3-compatible bucket
   |
   +----------> payment-worker ---------> payment providers
   +----------> creator-partnership-worker

 backup-worker ----------------------> PostgreSQL
       |
       +-----------------------------> private db_backups volume
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
backup-worker
```

Only the HTTPS proxy should be public. PostgreSQL, Redis, the backup volume and product media storage remain private.

### Public callback routes

Telegram and provider callbacks currently include:

```text
POST /webhooks/telegram
POST /webhooks/kie
POST /webhooks/payments/cryptobot
POST /webhooks/payments/tbank
POST /webhooks/payments/yookassa
```

The primary hosted-card checkout callback uses the dedicated route documented in `PRIMARY_CARD_CHECKOUT.md` and `WALLET_PAYMENTS.md`. Callback authentication/signature validation remains mandatory where configured, and provider callback payloads are reconciled against authoritative provider/local state rather than trusted as the sole source of truth.

## 2. Production deployment

Preferred release path is the production GitHub workflow. It resolves an exact `main` SHA, requires the release checks to be green, creates and validates a pre-migration PostgreSQL custom-format dump, runs Alembic, recreates runtime services including `backup-worker`, and verifies health/release metadata.

The pre-deploy archive must be non-empty, parse through `pg_restore --list`, and receive a SHA-256 sidecar before migration proceeds.

Manual recovery deployment:

```bash
git fetch origin main
git checkout main
git reset --hard origin/main
cp .env.example .env   # only for first-time setup; fill secrets separately
chmod 600 .env

docker compose up -d postgres redis
docker compose build app generation-worker media-worker prompt-tool-worker payment-worker creator-partnership-worker
docker compose run --rm app alembic upgrade head
docker compose up -d app generation-worker media-worker prompt-tool-worker payment-worker creator-partnership-worker backup-worker
```

Never deploy from a feature branch. Never hard-code a historical Alembic revision as the deployment target.

Current migration chain reaches:

```text
0001_initial
...
0023_roxy_one_ruble_denomination
0024_creator_partnership
0025_partner_wallet_transfers
0026_referral_antifraud
```

Always use:

```bash
alembic upgrade head
```

## 3. Core environment

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://api.example.com
DATABASE_URL=postgresql+asyncpg://ksu:<password>@postgres:5432/ksu
REDIS_URL=redis://redis:6379/0
BOT_TOKEN=...
TELEGRAM_WEBHOOK_URL=https://api.example.com
TELEGRAM_WEBHOOK_SECRET=<random-secret>

DB_BACKUP_INTERVAL_SECONDS=10800
DB_BACKUP_RETENTION_COUNT=16
DB_BACKUP_ON_START=true

# Public economy: 1 ROX = 1 RUB.
INTERNAL_CREDIT_RUB=1
START_BALANCE_ROX=50
INVITE_BONUS_ROX=30
PROMPT_REPEAT_BONUS_ROX=5
REFERRAL_FIRST_PERCENT=30
REFERRAL_SECOND_PERCENT=5
PARTNER_MIN_WITHDRAWAL_RUB=3000

ADMIN_SECURITY_KEY=<dedicated-random-secret-32+-chars>
ADMIN_REQUIRE_MFA=true
```

`.env.example` must contain placeholders only for secrets. Never commit live provider/payment credentials.

## 4. Referral admission anti-fraud

New-user referral attachment is a server-side admission boundary, not a client-side trust decision.

```dotenv
REFERRAL_ANTIFRAUD_MAX_PER_HOUR=30
REFERRAL_ANTIFRAUD_MAX_PER_DAY=120
REFERRAL_ANTIFRAUD_BURST_WINDOW_SECONDS=10
REFERRAL_ANTIFRAUD_BURST_MAX=6
REFERRAL_ANTIFRAUD_BURST_AUTOBAN=true
```

Rules:

- existing users are never rebound to a new inviter;
- self-referral is rejected and recorded;
- missing or inactive inviters are rejected and recorded;
- inviter admission is serialized under a PostgreSQL row lock;
- hourly/day limits reject only the new attachment and do **not** deactivate the inviter;
- the burst threshold blocks the attempt that would reach the configured threshold;
- with autoban enabled, a burst violation also sets the inviter inactive;
- the referral relation and invite bonus are created only after admission passes;
- invite bonus remains idempotent through `invite-bonus:<visitor-id>`;
- every admission outcome is auditable in `referral_events`.

Default burst semantics therefore block the sixth qualifying attempt inside 10 seconds when `REFERRAL_ANTIFRAUD_BURST_MAX=6`.

### Referral incident checks

Recent anti-fraud decisions:

```sql
SELECT
  created_at,
  visitor_telegram_id,
  inviter_telegram_id,
  reason,
  attached,
  metadata
FROM referral_events
ORDER BY created_at DESC
LIMIT 200;
```

Current inviter state:

```sql
SELECT id, telegram_id, is_active, created_at
FROM users
WHERE telegram_id = <inviter_telegram_id>;
```

Recent accepted relations:

```sql
SELECT inviter_id, invitee_id, created_at
FROM referral_relations
WHERE inviter_id = <inviter_user_uuid>
ORDER BY created_at DESC
LIMIT 200;
```

Do not reactivate an autobanned inviter or delete audit rows until traffic is reviewed. Hour/day-limit rejections are not bans and should not be treated as account-disable incidents.

## 5. Generation reliability

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

Generation + wallet debit + PostgreSQL outbox commit together. Redis wake-up is latency optimization only.

Recovery contract:

- terminal `succeeded` / `failed` states are monotonic;
- permanent validation/auth rejection fails/refunds immediately;
- explicit provider `429` is retryable;
- timeout, transport, 5xx, malformed success or missing provider task id are uncertain;
- uncertain submission remains `submitting` and is not blindly resubmitted;
- callback/reconciliation may bind the provider task later;
- unresolved uncertain submission fails/refunds once after the unknown-submission timeout;
- active provider work exceeding `GENERATION_HARD_TIMEOUT_SECONDS` fails/refunds once;
- provider success without usable result media is not finalized as a charged empty success.

Do not manually call provider `createTask` for an uncertain generation.

Generation state overview:

```sql
SELECT id, status, provider, external_id, created_at, updated_at, error
FROM generations
WHERE status IN ('queued','retry','submitting','generating')
ORDER BY created_at ASC
LIMIT 100;
```

Outbox overview:

```sql
SELECT status, count(*)
FROM generation_outbox
GROUP BY status;
```

## 6. Durable media storage

Successful generation state, `media_assets` and `media_ingest_jobs` commit durably in PostgreSQL. Provider result URLs are temporary ingestion sources.

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

Keep the bucket private and expose owned media through short-lived presigned capabilities after ownership checks. See `MEDIA_STORAGE.md`.

Queue check:

```sql
SELECT status, count(*)
FROM media_ingest_jobs
GROUP BY status;
```

A media-copy failure alone is not a reason to manually fail/refund a successfully generated provider result.

## 7. Payments

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

Failure log checks:

```bash
tail -n 200 logs/errors.log
docker logs --since 1h ksu-app-1 2>&1 | grep -E 'ERROR|CRITICAL|Traceback|status=5[0-9][0-9]'
docker logs --since 1h ksu-generation-worker-1 2>&1 | grep -E 'ERROR|CRITICAL|Traceback|status=5[0-9][0-9]'
docker logs --since 1h ksu-payment-worker-1 2>&1 | grep -E 'ERROR|CRITICAL|Traceback|status=5[0-9][0-9]'
```

Primary hosted-card recovery contract:

- invoice creation uses the current hosted-checkout create route;
- authoritative single-contract lookup is `GET /api/v1/invoices/{id}`;
- do not depend on arbitrary ROXY metadata being returned by the provider webhook;
- when a verified webhook references an unknown local contract, authoritative invoice data is fetched first;
- recovery requires authoritative contract id, amount, currency and buyer email;
- local binding is allowed only when exactly one unresolved card intent matches amount + currency + normalized email;
- zero/multiple candidates or identity mismatch fail closed with no ROX credit;
- successful binding completes the durable payment request and then uses ordinary authoritative reconciliation;
- `creation_unknown` must not trigger a blind second remote invoice.

Creation-intent check:

```sql
SELECT user_id, request_key, provider, package_id, payment_id, status, last_error, created_at
FROM payment_requests
ORDER BY created_at DESC
LIMIT 100;
```

Never manually mark a payment successful or credit the wallet as an incident shortcut.

## 8. Creator partnership

```dotenv
CREATOR_PARTNERSHIP_GRANT_INTERVAL_SECONDS=3600
```

Creator/influencer grants are spend-only ROX and remain separate from withdrawable referral earnings. The worker is idempotent per agreement/period.

## 9. API/resource abuse protection

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

With fail-closed enabled, inability to verify an expensive mutation through Redis blocks/delays it rather than allowing unmetered spend. Durable PostgreSQL business state remains authoritative.

Do not routinely delete anti-abuse Redis keys to bypass throttling.

## 10. Health and smoke checks

```bash
BASE=https://api.example.com
curl -fsS "$BASE/health/live"
curl -fsS "$BASE/health/ready"
curl -fsS "$BASE/health/operational"
curl -fsSI "$BASE/mini-app/"
curl -fsS "$BASE/api/v1/generations/models"
curl -fsS "$BASE/api/v1/payments/packages"
docker compose ps backup-worker
```

Then verify through Telegram/Mini App:

1. authentication and onboarding;
2. one model quote;
3. one small upload;
4. one budgeted generation;
5. product-owned media delivery;
6. one low-value test payment;
7. referral link registration in staging with an isolated test inviter.

For referral staging smoke, temporarily lower limits and verify rejected attempts do not create `referral_relations` or invite bonuses. Restore production values immediately after the test.

## 11. Backup and restore

PostgreSQL contains wallets, payments, generation/outbox state, media metadata/jobs, partner/admin/feed state and referral audit state.

ROXY has two database-backup layers on the application host:

1. the production deploy creates a pre-migration custom-format archive, requires it to be non-empty, validates it with `pg_restore --list`, and writes a SHA-256 sidecar before Alembic runs;
2. the long-running `backup-worker` creates verified/checksummed periodic archives in the private `db_backups` volume (default every 3 hours, newest 16 retained, backup on worker start enabled).

Verify the periodic latest archive:

```bash
docker compose exec -T backup-worker sh -c 'cd /backups && sha256sum -c latest.dump.sha256'
docker compose exec -T backup-worker pg_restore --list /backups/latest.dump >/dev/null
```

Local Docker-volume retention is **not** off-host disaster recovery. Production operations must copy/snapshot verified database backups to dedicated encrypted off-host storage. Never transmit dumps through Telegram/chat.

Regularly restore a verified archive into an isolated disposable database and run application-level integrity checks. A successful checksum/catalog listing is not a restore drill.

The media bucket is a separate durability domain; a PostgreSQL restore does not restore deleted object bytes.

Full procedures and incident handling: `DATABASE_BACKUPS.md`.

## 12. Release procedure

1. release only an exact `main` SHA;
2. require green CI, Batch Generation and Admin Console checks for that SHA/PR;
3. inspect migrations and config changes;
4. confirm maintained docs and `.env.example` changed with runtime behavior;
5. require the production workflow's pre-migration PostgreSQL archive to pass non-empty + `pg_restore --list` + checksum publication;
6. build application/worker images;
7. run `alembic upgrade head`;
8. recreate current runtime services including `backup-worker`;
9. verify `backup-worker` is running plus API/product/payment/generation/media/referral smoke checks;
10. verify Mini App release metadata resolves the expected SHA;
11. confirm periodic backup freshness/off-host durability operationally;
12. monitor logs, worker heartbeats and provider dashboards.

Do not automatically downgrade Alembic after a failed production release. Prefer a reviewed forward fix or controlled restore.

## 13. Monitoring priorities

Prioritize:

- API readiness / 5xx ratio;
- generation/media/payment/creator worker health;
- `backup-worker` running state, last verified backup age and repeated backup failures;
- off-host backup freshness and restore-drill evidence;
- generation outbox oldest pending age;
- generations stuck in `submitting` / `generating`;
- media ingest oldest pending age and failures;
- generation refund/failure spikes;
- payment reconciliation failures and `creation_unknown` age;
- referral rejection/burst spikes and newly inactive inviters;
- Redis availability;
- PostgreSQL capacity/locks;
- provider 429/5xx/circuit state.

## 14. Operational invariants

- PostgreSQL is the durable business source of truth.
- Redis is never the only copy of wallet/payment/generation/media/referral business state.
- Local database backups are verified before publication; off-host copies remain a separate required durability layer.
- Wallet credit/debit/refund paths remain idempotent.
- Provider callbacks are authenticated where configured and reconciled against authoritative state.
- No blind duplicate provider generation or payment create is permitted after an uncertain response.
- Referral attachment is immutable after user creation and admitted under server-side controls.
- Secrets never belong in `.env.example`, docs, logs or issue/PR bodies.
- Runtime-affecting PRs update maintained docs/config examples in the same PR.
