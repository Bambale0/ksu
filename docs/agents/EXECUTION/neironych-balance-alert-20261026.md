# Neironych balance low-funds Telegram alert (2026-10-26)

## User request and actual gap

Notify the configured KSU owner/admin on Telegram when **Neironych partner cash balance <= 1000.00 RUB**. This is the external provider account's balance, **not** ROX, not user's wallet, and not approved credit limit. There is presently no recurring Neironych balance monitor or reliable partner-key read endpoint in Neironych. The existing Neironych `GET /api/v1/billing/partners/{id}/balance` needs a master admin token and MUST NOT be integrated into KSU.

Prerequisite separate provider PR: [Bambale0/ooo#133](https://github.com/Bambale0/ooo/pull/133) adds a partner-authenticated read-only `GET /v1/balance`. Read-only GitHub inspection confirms it merged as `b057bb4c0a0c49b45db5124ea1e2c4fe2c3f52f5`; its final route and tests agree with KSU. This is not production availability evidence. Production KSU must not be activated until the authenticated endpoint works in production.

## Reuse, scope and decisions

- Reuse `app/workers/notifications.py`'s single poll loop and durable `NotificationService.create`/Telegram outbox (including retry/lease/reachability), no new scheduler, sidecar, migration, bypass, bot token, direct Telegram POST or admin token.
- Recipient: current **active owner** account linked to the configured `ADMIN_BOOTSTRAP_TELEGRAM_IDS` (production presently one ID matching one owner). No IDs in source, and no broadcast of sensitive balance to other admin accounts.
- Source: `settings.neironych_api_key` (partner key already used for generation), partner-authenticated `GET /v1/balance`. Strict `Decimal` RUB, compare `balance_rub` inclusive at the configured threshold; do not inflate with `credit_limit_rub`. HTTPS endpoint, timeouts, no raw body or credentials in logs. No paid generation calls.
- Every 300 seconds by default (bounded through `NEIRONYCH_BALANCE_ALERT_POLL_SECONDS`). The enabled flag and threshold are stored in the existing audited `AdminRuntimeSetting` control plane, exposed in the protected web admin with optimistic revision, explicit confirmation, fresh MFA step-up and idempotent command handling. `NEIRONYCH_BALANCE_ALERT_THRESHOLD_RUB=1000.00` is only the bootstrap fallback when no admin policy exists, so first deployment remains safe without manual SQL.
- Persist alert state using the **latest per-recipient notification** of kinds `neironych_balance_low` or `neironych_balance_recovered`. One low warning per episode; one recovery after a recheck > threshold; next drop re-arms warning. PostgreSQL transaction advisory lock prevents duplicates across worker overlaps/restarts. Existing outbox deliveries are durable and retried. Important: *at-least-once Telegram*, not guaranteed exactly-once in the send/commit crash window.
- Operational kind bypasses users' optional marketing/notification preferences; disabled accounts receive nothing. No other user sees the provider's cash balance.
- Whole-poll wall-clock deadline: 10 seconds around lock acquisition, HTTP, policy read and transaction. Unlike the per-I/O HTTP timeout this also bounds slow responses and contended locks. Each poll has a correlation ID and duration metric in structured logs.
- The provider response is streamed through a 16 KiB declared/accumulated byte cap before JSON parsing; oversized or malformed payloads fail closed without starving Telegram delivery.
- `Accept-Encoding: identity` is enforced and raw bytes are capped before decoding. The balance-state advisory lock covers the final freshness check through Telegram send/commit, authorization-suppressed lows re-arm after access restoration, and shared logs contain state/revision/IDs rather than exact provider money.
- A queued low/recovered retry is suppressed as `balance_episode_superseded` when a newer committed observation exists for that recipient. Owner revocation is rechecked both on delivery and every inbox read/count, including the account profile badge.
- Failure handling: absent key, malformed response/NaN, 401/403, 5xx, timeout and absent admin recipient produce safe diagnostic log (error type/code only), **never** false low/recovered signals; next polling cycle retries. Existing notification worker must keep processing customer deliveries.
- If balance is first observed above threshold, no recovery message. On <= threshold, queue immediately on next poll, even on initial run. Strict no-false-positives from credit limit or unavailable provider.
- Audit: structured monitor events (status, count, safe balance), existing NotificationDelivery state; zero new schema, no key leakage.

## Verification matrix

| Boundary | Evidence expected |
| --- | --- |
| Domain | <=1000, >1000, negative, Decimal precision, NaN rejection |
| HTTP | provider MockTransport, partner key Bearer only, no paid POST, no token logged, HTTP/status failure |
| DB/outbox | active configured owner only, idempotent repeat/restart, recovery re-arm, Notification and NotificationDelivery atomic |
| Security | no admin credential or other admin fanout, inactive owner excluded, notification preference bypass only for operational kinds; policy write requires runtime permission + MFA step-up + confirmation |
| Worker | due polling even under idle notifications, bounded fetch failures do not stop queue |
| Migration | N/A; uses current Notification and Delivery schema |
| Admin/config | DB-backed enabled/threshold policy, exact decimal validation, optimistic revision and replay-safe audited write; env fallback is 1000 RUB |
| Pricing | no user ROX/wallet, paid generation or provider routes changed |
| Performance | bounded GET every 300s per worker; advisory transaction and indexed recipient queries |
| Release | exact-head CI, review, merge-main 6 gates, upstream dependency deployed first, exact-image deployment and health |
| Rollback | Disable in the protected admin policy; do not unset the generation partner key. Existing current alerts remain durable; superseded or unauthorized notices are suppressed. Code rollback requires a separately controlled deployment; no schema rollback. |

Skill use: user's `Bambale0/.agents` agents-global-router, observability-and-instrumentation, api-integration and python-testing-patterns; KSU primary `Bambale0/skills` implement/tdd/code-review, `Bambale0/claw` safety, `Bambale0/dev-agents-pack` release-manager; `agentskills/agentskills` format; `anthropics/skills` no KSU-specific balance guide; `wondelai/skills` release-it. No executable skill script run.

## Verification evidence

- Current admin-control slice: added deterministic service/API/browser regressions for DB policy, disable behavior, exact threshold, permission, MFA step-up, confirmation, optimistic revision, idempotent replay and the real form submission. On the Windows handoff host, Node syntax checks and `git diff --check` pass. PostgreSQL tests, Ruff, full compile and browser execution must run on Linux CI because this host has no Docker/PostgreSQL and its default Python is 3.7; do not treat the earlier 15-test result below as verification of the newer admin-control commit.
- Neironych provider [Bambale0/ooo#133](https://github.com/Bambale0/ooo/pull/133): 65 isolated ASGI/documentation/security tests pass on the final public /v1/balance route; Ruff pass.
- KSU isolated PostgreSQL 17 with Alembic migrations: `tests/test_neironych_balance_alerts.py` **15 passed**, including exact Decimal boundary, malformed response fail-closed, owner-only routing, one-shot dedupe and recovered re-arm, successful owner Telegram delivery despite muted preferences, and concurrency guard via Postgres advisory lock. Ruff, compileall and `alembic check` passed. No production database written and no live provider/paid generation used in tests.
- Recipient in production verified read-only: precisely one configured bootstrap Telegram owner matches an active owner account. The broader admin account population must not receive these alerts.

## Continuation review and verification (2026-10-26)

- Audit baseline/head: `ef06c605bc0adec7f55f63337eec99bdef0734f9`, PR base `55e0763fb512474b5c62d2229f465bcc27fb3e1e`. CI run `40340590839` succeeded: Ruff, compile, migrations, ORM parity, focused contracts and **1981 passed** full backend regression. This evidence applies to that head only.
- Independent read-only review found no missing cash/owner/policy behavior. Reliability review found no total poll deadline and stale delayed balance notices; security review found a revoked-owner profile badge inconsistency. Regressions cover the deadline, current-episode check, shared sensitive-kind scope, badge filter, correlation ID and duration logs.
- Cloud Python 3.12 isolated verification before the final observability addition: Ruff, compileall and whitespace checks passed; **24 passed, 10 deselected** focused non-DB service/worker tests. Exact-final-head CI remains required.
- Guidance used: `Bambale0/.agents` observability, API integration and Python testing; project `AGENTS.md`; `Bambale0/skills` implement/TDD/review; `Bambale0/claw` backend/release safety; `Bambale0/dev-agents-pack` backend/Telegram/API/test/review; `wondelai/skills` clean code. No skill scripts changed.


## Authorized release continuation

The user explicitly authorized merge/deployment and live exact-SHA verification,
superseding the earlier no-merge/no-deploy task boundary. No unrelated production
writes or paid generation are authorized. The live balance read never prints keys.

Upstream prerequisite evidence (read-only): deploy run 40303655959 succeeded for
`b057bb4c0a0c49b45db5124ea1e2c4fe2c3f52f5`; the live provider app APP_REVISION
matches. An authenticated GET /v1/balance from KSU returned HTTP 200,
Cache-Control: no-store, partner identity and finite Decimal cash/available fields.
The upstream auth dependency was inspected: its path performs SELECT only.
Thus prerequisite availability is verified before KSU activation.

Standards-review follow-up at `c200549493ea65684214ad1c4633e096a9d0c3f4`:
the per-poll request_id_var/duration logs are present. The provider HTTP read now
propagates X-Request-ID, and enqueue logs include the created notification_id so
operators can join the correlated poll to NotificationDelivery. A MockTransport
regression verifies propagation. No new schema/config migration is required.
Final exact-head CI and independent Spec/Standards results are recorded in PR #560.

Current guidance refreshed remotely: Bambale0/skills current engineering
implement/TDD/code-review; Bambale0/claw and Bambale0/dev-agents-pack PR review
checklists; wondelai/skills release-it timeouts/stability; agentskills/agentskills
progressive disclosure (no KSU-specific implementation guide); anthropics/skills
webapp-testing; user-linked Bambale0/.agents fix-review/review-swarm/observability.
Branch-local .agents instructions/index are absent; .clinerules receiving-code-review
and verification-before-completion used as fallback. No skill scripts executed.
