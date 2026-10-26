# Neironych balance low-funds Telegram alert (2026-10-26)

## User request and actual gap

Notify the configured KSU owner/admin on Telegram when **Neironych partner cash balance <= 1000.00 RUB**. This is the external provider account's balance, **not** ROX, not user's wallet, and not approved credit limit. There is presently no recurring Neironych balance monitor or reliable partner-key read endpoint in Neironych. The existing Neironych `GET /api/v1/billing/partners/{id}/balance` needs a master admin token and MUST NOT be integrated into KSU.

Prerequisite separate provider PR: [Bambale0/ooo#133](https://github.com/Bambale0/ooo/pull/133) adds a partner-authenticated read-only `GET /api/v1/billing/self/balance`. Production KSU must not be activated until this endpoint exists in production.

## Reuse, scope and decisions

- Reuse `app/workers/notifications.py`'s single poll loop and durable `NotificationService.create`/Telegram outbox (including retry/lease/reachability), no new scheduler, sidecar, migration, bypass, bot token, direct Telegram POST or admin token.
- Recipient: current **active owner** account linked to the configured `ADMIN_BOOTSTRAP_TELEGRAM_IDS` (production presently one ID matching one owner). No IDs in source, and no broadcast of sensitive balance to other admin accounts.
- Source: `settings.neironych_api_key` (partner key already used for generation), `GET` `/api/v1/billing/self/balance`. Strict `Decimal` RUB, compare `balance_rub` inclusive at 1000.00; do not inflate with `credit_limit_rub`. HTTPS endpoint, timeouts, no raw body or credentials in logs. No paid generation calls.
- Every 300 seconds by default (configurable via `NEIRONYCH_BALANCE_ALERT_POLL_SECONDS`). Default threshold 1000 RUB (configurable via `NEIRONYCH_BALANCE_ALERT_THRESHOLD_RUB`). No configuration in frontend; product-visible UI or customer notifications unchanged.
- Persist alert state using the **latest per-recipient notification** of kinds `neironych_balance_low` or `neironych_balance_recovered`. One low warning per episode; one recovery after a recheck > threshold; next drop re-arms warning. PostgreSQL transaction advisory lock prevents duplicates across worker overlaps/restarts. Existing outbox deliveries are durable and retried. Important: *at-least-once Telegram*, not guaranteed exactly-once in the send/commit crash window.
- Operational kind bypasses users' optional marketing/notification preferences; disabled accounts receive nothing. No other user sees the provider's cash balance.
- Failure handling: absent key, malformed response/NaN, 401/403, 5xx, timeout and absent admin recipient produce safe diagnostic log (error type/code only), **never** false low/recovered signals; next polling cycle retries. Existing notification worker must keep processing customer deliveries.
- If balance is first observed above threshold, no recovery message. On <= threshold, queue immediately on next poll, even on initial run. Strict no-false-positives from credit limit or unavailable provider.
- Audit: structured monitor events (status, count, safe balance), existing NotificationDelivery state; zero new schema, no key leakage.

## Verification matrix

| Boundary | Evidence expected |
| --- | --- |
| Domain | <=1000, >1000, negative, Decimal precision, NaN rejection |
| HTTP | provider MockTransport, partner key Bearer only, no paid POST, no token logged, HTTP/status failure |
| DB/outbox | active configured owner only, idempotent repeat/restart, recovery re-arm, Notification and NotificationDelivery atomic |
| Security | no admin credential or other admin fanout, inactive owner excluded, notification preference bypass only for operational kinds |
| Worker | due polling even under idle notifications, bounded fetch failures do not stop queue |
| Migration | N/A; uses current Notification and Delivery schema |
| Pricing | no user ROX/wallet, paid generation or provider routes changed |
| Performance | bounded GET every 300s per worker; advisory transaction and indexed recipient queries |
| Release | exact-head CI, review, merge-main 6 gates, upstream dependency deployed first, exact-image deployment and health |
| Rollback | disable via config? Stop monitor by unsetting partner key is NOT suitable because generation needs it. Revert change/redeploy; already queued alerts remain durable. |

Skill use: user's `Bambale0/.agents` agents-global-router, observability-and-instrumentation, api-integration and python-testing-patterns; KSU primary `Bambale0/skills` implement/tdd/code-review, `Bambale0/claw` safety, `Bambale0/dev-agents-pack` release-manager; `agentskills/agentskills` format; `anthropics/skills` no KSU-specific balance guide; `wondelai/skills` release-it. No executable skill script run.
