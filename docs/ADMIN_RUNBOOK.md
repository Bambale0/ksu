# Admin contour runbook

**Status:** synchronized with shipped runtime on 2026-08-20.

This runbook covers the shared KSU/ROXY admin domain, `/admin-app/`, signed internal admin API, privileged workers and live tariff operations.

## Required environment

Browser/Telegram admin security:

```text
ADMIN_SECURITY_KEY=<strong dedicated secret>
ADMIN_BOOTSTRAP_TELEGRAM_IDS=<temporary bootstrap allow-list>
ADMIN_REQUIRE_MFA=true
ADMIN_SESSION_TTL_MINUTES=...
ADMIN_IDLE_TIMEOUT_MINUTES=...
ADMIN_STEP_UP_MINUTES=...
```

Signed internal admin API:

```text
INTERNAL_ADMIN_HMAC_SECRET=<32+ char random secret>
INTERNAL_ADMIN_NETWORK_ALLOWLIST=<private trusted CIDRs>
INTERNAL_ADMIN_TIMESTAMP_SKEW_SECONDS=300
```

Do not expose `/internal/admin/*` on public Mini App ingress. CIDR validation is defense in depth, not a replacement for a private route/VPN/service mesh.

The exact HMAC payload remains:

```text
<unix_timestamp>\n
<request_id>\n
<METHOD>\n
<path>\n
<exact raw body bytes>
```

Writes use idempotency and, where policy requires, explicit confirmation and fresh step-up evidence.

## Deployment order

1. Back up PostgreSQL and record the current deploy SHA.
2. Deploy application images/code.
3. Run `alembic upgrade head`.
4. Verify admin secrets/private ingress and worker environment.
5. Start/restart API, bot and required workers.
6. Verify `/admin-app/` login, MFA and effective permissions.
7. Run signed internal API smoke checks if that surface is enabled.
8. Run pricing smoke checks below before allowing tariff changes.
9. Run customer quote/create smoke checks after any price/config release.

## Admin authentication smoke checks

- regular user cannot enter the admin panel;
- revoked admin cannot continue an existing privileged state;
- admin bearer token is memory-only in the browser;
- MFA enrollment/recovery code handling works;
- high-impact actions require fresh step-up and a separate final execute/publish action;
- permission-hidden buttons are not treated as authorization; backend rejection remains authoritative;
- session mutation requires the mutation permission (for privileged session revocation: `sessions.manage`).

## Generation pricing operations

The current pricing contour is versioned and server-authoritative. The active customer price may come from catalog defaults plus an authorized published `generation_pricing` override.

### Before changing a price

1. Identify the concrete backend `model_id` from `/api/v1/generations/models`.
2. Confirm its `price_mode` (`flat` or `per_second`).
3. For tiered models, confirm the server-supported tier parameter/value set. Do not invent arbitrary tier dimensions in the admin payload.
4. Record the currently published tariff/version and representative quotes for rollback evidence.
5. Confirm the operator has `pricing.manage` and a fresh MFA step-up can be completed.

### Publish procedure

1. Create/edit the next tariff version in Admin Tariffs.
2. Enter model overrides using public ROX units (`1 ROX = 1 RUB`).
3. Preview/validate the change.
4. Complete fresh MFA step-up.
5. Explicitly confirm and publish.
6. Confirm the version becomes the published tariff.
7. Request a fresh generation quote for every changed model/tier.
8. Run one controlled generation on a test wallet and confirm actual debit equals the quote.
9. Inspect the audit record for actor, command/request ID and published version.

Published generation pricing becomes active in the current API runtime. The latest published tariff is persisted in PostgreSQL and restored when the application starts/restarts.

### Tiered pricing verification

Current resolution-tier acceptance values:

```text
Kling Motion 2.6: 720p 20 ROX/s, 1080p 30 ROX/s
Kling Motion 3.0: 720p 60 ROX/s, 1080p 80 ROX/s
```

Quote both tiers explicitly. A base/default price alone is not sufficient evidence that parameter-aware pricing is working.

### Rollback a pricing mistake

Do not edit/delete historical tariff/audit rows. Publish a corrected version using the previous known-good values, then repeat quote/debit verification. If the runtime is unhealthy, disable operator pricing changes, restore the last known-good application revision and verify the persisted published tariff is loaded on startup.

### Current approved baseline

```text
Nano Banana PRO            25 ROX
WAN 2.7 photo              20 ROX
GPT Image 2                20 ROX
Nano Banana 2              25 ROX
Nano Banana 2 Lite         25 ROX
Seedream 4.5               20 ROX
Seedream 5 Pro             20 ROX
Seedance 2.0 480p          40 ROX/s
Seedance 2.0 720p          50 ROX/s
Seedance 2.0 1080p         60 ROX/s
Seedance 2.5 480p          50 ROX/s
Seedance 2.5 720p          60 ROX/s
Seedance 2.5 1080p         70 ROX/s
Seedance 2.5 4K            90 ROX/s, reserved until callable provider support is exposed
Kling 2.5 Turbo Pro 5s     40 ROX
Kling 2.5 Turbo Pro 10s    80 ROX
Kling AI Avatar Standard   100 ROX/s
Kling AI Avatar Pro        150 ROX/s
Kling 3.0                  30 ROX/s
Veo 3.1                    35 ROX/s
Grok                        15 ROX/s
Grok Imagine 1.5           30 ROX/s
Gemini Omni                from 30 ROX/s
Kling Motion 2.6 720p      20 ROX/s
Kling Motion 2.6 1080p     30 ROX/s
Kling Motion 3.0 720p      60 ROX/s
Kling Motion 3.0 1080p     80 ROX/s
```

The published live tariff overrides this baseline when intentionally changed.

## Signed API smoke checks

- valid allowlisted signed `GET /internal/admin/health` succeeds;
- changed body/signature or stale timestamp fails;
- same idempotency key + same mutation replays without a duplicate side effect;
- same key + different mutation conflicts.

## Durable support/campaign operations

Support and campaign workers own eventual Telegram delivery. Verify lease recovery by queueing work with a worker stopped, restarting it and confirming eventual delivery. Campaign recipient materialization must remain idempotent and users with marketing notifications disabled must be suppressed.

## Audit / incident response

- treat admin command/audit data as append-only evidence;
- correlate by request ID, idempotency key, actor, action and target;
- sensitive request/response representations remain redacted;
- rotate internal HMAC secrets and disable the private ingress immediately if compromised;
- revoke compromised admin sessions/accounts through the security contour;
- for pricing incidents, record affected model IDs, published tariff version, first/last affected generation and quote/debit evidence.

## Application rollback

1. Disable new privileged actions/private admin ingress as needed.
2. Stop incompatible operator workers when rolling back across worker schema changes.
3. Roll application image back to a known-good revision.
4. Keep additive admin tables/migrations in place unless a tested DB rollback is required; preserving audit/idempotency/outbox evidence is safer.
5. Never run Alembic downgrade while newer workers/code are still active.
6. Verify wallet/payment invariants, admin auth and generation quote/debit before reopening operations.

## Ownership rule

The shared backend admin service/policy/audit layer is the authoritative mutation path. Telegram handlers, signed internal HTTP and browser controls are adapters. New privileged writes — including pricing writes — must be implemented in the domain/policy layer first, never only in JavaScript or a transport handler.
