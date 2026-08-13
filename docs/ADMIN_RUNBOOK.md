# Admin contour runbook

This runbook covers the shared KSU admin domain, signed internal API, Telegram admin UI, browser control UI, and durable operator workers.

## Required environment

### Browser / Telegram admin security

- `ADMIN_SECURITY_KEY`: strong application secret used by the existing admin session/MFA security layer.
- `ADMIN_BOOTSTRAP_TELEGRAM_IDS`: explicit Telegram IDs allowed to bootstrap the first owner.
- `ADMIN_REQUIRE_MFA=true`: keep enabled in production.
- `ADMIN_SESSION_TTL_MINUTES`, `ADMIN_IDLE_TIMEOUT_MINUTES`, `ADMIN_STEP_UP_MINUTES`: privileged session lifetime and fresh-MFA window.

### Signed internal admin API

- `INTERNAL_ADMIN_HMAC_SECRET`: random secret at least 32 characters long.
- `INTERNAL_ADMIN_NETWORK_ALLOWLIST`: comma-separated trusted IPv4/IPv6 CIDRs. Production must never use a public catch-all CIDR.
- `INTERNAL_ADMIN_TIMESTAMP_SKEW_SECONDS`: accepted request clock skew; default `300`.

The internal signature is lowercase hex HMAC-SHA256 with this exact byte payload:

```text
<unix_timestamp>\n
<request_id>\n
<METHOD>\n
<path>\n
<exact raw body bytes>
```

Required signed-request headers:

- `X-Admin-Timestamp`
- `X-Request-Id`
- `X-Admin-Signature` (`<hex>` or `sha256=<hex>`)
- `X-Admin-User-Id` for authenticated admin routes; accepts the admin account UUID or its user UUID.

Every internal write also requires:

- `Idempotency-Key`
- `X-Admin-Confirm: confirmed` for actions whose policy requires manual confirmation
- `X-Admin-Step-Up: confirmed` only for trusted server-to-server callers after their own fresh-MFA/step-up control has been satisfied

Do not expose `/internal/admin/*` through the public Telegram/Mini App ingress. Route it only through a private listener, private reverse-proxy location, VPN, service mesh, or equivalent network boundary. Application CIDR checking is defense in depth, not a substitute for ingress isolation.

### Durable operator workers

Support replies and broadcast campaigns require `BOT_TOKEN` plus:

- `SUPPORT_OUTBOX_WORKER_POLL_SECONDS`
- `SUPPORT_OUTBOX_LEASE_SECONDS`
- `SUPPORT_OUTBOX_MAX_ATTEMPTS`
- `SUPPORT_OUTBOX_BATCH_SIZE`
- `CAMPAIGN_WORKER_POLL_SECONDS`
- `CAMPAIGN_DELIVERY_LEASE_SECONDS`
- `CAMPAIGN_DELIVERY_MAX_ATTEMPTS`
- `CAMPAIGN_DELIVERY_BATCH_SIZE`

`docker-compose.notifications.yml` starts the existing notification worker plus `admin-support-worker` and `admin-campaign-worker`.

## Rollout order

1. Back up PostgreSQL and verify the currently deployed application revision.
2. Deploy code/images without routing operator traffic to the new internal API yet.
3. Run `alembic upgrade head`. The admin contour migrations are additive and create command ledger, tariff/CMS/campaign/support-outbox, runtime/trend, and moderation tables.
4. Configure `INTERNAL_ADMIN_HMAC_SECRET` and a narrow `INTERNAL_ADMIN_NETWORK_ALLOWLIST` on the API service and trusted internal caller.
5. Start/restart the API and bot processes.
6. Start `admin-support-worker` and `admin-campaign-worker` together with the existing notification worker.
7. Enable the private reverse-proxy/service-mesh route for `/internal/admin/*`; keep the path absent from public ingress.
8. Open `/admin-app/` from Telegram, verify MFA, then open `/admin-app/control.html` through the `Control` link.
9. Run the smoke checks below before enabling real operator workflows.

## Smoke checks

### Database and process checks

- `alembic current` reports the expected head.
- API health remains healthy.
- Support and campaign workers remain running and can acquire PostgreSQL leases.
- No worker is crash-looping because `BOT_TOKEN` is absent.

### Signed API

1. Sign an empty body for `GET /internal/admin/health` from an allowlisted address. Expect HTTP 200 and the same request ID.
2. Change one byte of the body/signature payload. Expect HTTP 401.
3. Use an expired timestamp. Expect HTTP 401.
4. Send the same signed balance adjustment twice with the same `Idempotency-Key`. The second response must report replay and the wallet balance must change only once.
5. Reuse the same idempotency key with a different payload/action. Expect a conflict, never another side effect.

### Telegram admin

- A regular user sending `/admin` cannot enter the panel.
- A user whose admin account is revoked while an FSM is active cannot continue the state or callback flow.
- Admin user lookup works by Telegram ID and internal UUID.
- Balance and destructive actions show preview/confirmation before execution.
- `/admin_export` produces CSV/XLSX without provider secrets or withdrawal requisites.
- Broadcast preview shows the recipient count; starting the broadcast creates durable deliveries instead of sending every message in the callback handler.

### Browser control

- `/admin-app/control.html` requires Telegram initData and an active server-confirmed admin session/MFA.
- Browser storage does not contain the admin bearer token; it is memory-only.
- A forged request from a regular user is rejected by backend dependencies even if UI controls are manually exposed in devtools.
- Sensitive balance/payment/operation/withdrawal/campaign actions require fresh MFA step-up.
- CMS publishing creates a new version/published state rather than editing published content in place.
- Feed moderation persists explicit `visible` / `blurred` / `removed` state and moderator metadata.

### Durable support and campaigns

1. Reply to a support ticket. The HTTP/Telegram transaction must create `support_messages` + `support_outbox`; delivery is performed by the worker.
2. Temporarily stop the support worker, queue a reply, restart it, and verify eventual delivery.
3. Start a campaign twice with the same idempotency key. Recipient rows must be materialized only once.
4. Stop/restart the campaign worker mid-delivery and verify leased rows recover after lease expiration without duplicate `(campaign_id, user_id)` rows.
5. Users with marketing notifications disabled are suppressed by the campaign worker.

## Pricing rollout

Tariffs are immutable version records. Publishing supersedes the previous published version. `runtime/reload` reads the latest published tariff and applies generation price overrides to the current API process.

For multi-process or multi-host deployments, perform runtime reload/restart consistently on every API/bot process that calculates prices. Do not assume one process mutation changes another process's in-memory settings.

## Audit and incident handling

- Treat `admin_commands` as append-only application evidence. Do not delete rows during normal operations.
- Use `request_id`, `idempotency_key`, admin account ID, action, and target ID to correlate a privileged command.
- Stored command request/response representations recursively redact `token`, `secret`, `password`, `authorization`, `api_key`, `webhook`, `callback`, access/refresh tokens, and cookies.
- Rotate `INTERNAL_ADMIN_HMAC_SECRET` immediately if it may have leaked, update trusted callers atomically, and keep the private route disabled until both sides agree on the new key.
- Revoke an admin session/account through the existing security console if an operator identity is compromised.

## Rollback

The safest application rollback is code-first, schema-last:

1. Disable new operator actions and remove the private `/internal/admin/*` ingress route.
2. Stop `admin-support-worker` and `admin-campaign-worker` if rolling back to a revision that does not understand their tables.
3. Roll the API/bot image back to the previous known-good revision.
4. Leave additive admin tables/migrations in place unless a tested database rollback is explicitly required. Old code ignores the additional tables and keeping them preserves audit/idempotency/outbox evidence.
5. Do not run Alembic downgrade while support/campaign workers or new application code are still active.
6. If a downgrade is unavoidable, export `admin_commands`, pending `support_outbox`, campaign/delivery records, tariff versions, CMS versions, and moderation state first. A schema downgrade can destroy evidence or pending durable work.
7. After rollback, run legacy API/bot smoke tests and verify wallet/payment invariants before reopening operator access.

## Operational ownership

The authoritative write path is the shared admin service layer. Telegram, signed internal HTTP, and the shared browser control are transport adapters. New privileged mutations must be added to the domain service + policy + ledger/audit layer first; adding a write only to a handler or JavaScript control is not an acceptable production change.
