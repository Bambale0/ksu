# KSU admin contour

## Architecture

```text
Telegram /admin + FSM ───────────────┐
                                     │
Browser /admin-app/control.html ─────┼──> AdminPolicy
                                     │       │
Signed /internal/admin/* ────────────┘       ├──> AdminCommandLedger
                                             │       │
                                             │       └── idempotency + redacted request/response evidence
                                             │
                                             └──> shared admin services
                                                    ├── users / wallet
                                                    ├── partners / withdrawals
                                                    ├── reporting / finance / exports
                                                    ├── payments
                                                    ├── generation operations
                                                    ├── pricing / tariff versions
                                                    ├── promos
                                                    ├── prompt + feed moderation / trends
                                                    ├── support
                                                    ├── CMS versions
                                                    ├── campaigns
                                                    ├── runtime
                                                    └── AI admin brief
                                                             │
                            ┌────────────────────────────────┴──────────────────────┐
                            │                                                       │
                     transactional DB writes                                durable side effects
                                                                                    │
                                                        ┌───────────────────────────┴──────────────────────────┐
                                                        │                                                      │
                                                SupportOutbox worker                              CampaignDelivery worker
```

## Security boundaries

### Browser admin

The browser uses the existing bearer admin session/MFA system. The shared control page keeps the bearer token only in JavaScript memory, requires Telegram initData at login/step-up, confirms the admin identity with `/api/v1/admin/auth/me`, and relies on backend `require_permission()` for every protected route.

`require_permission()` delegates to `AdminPolicy`, so browser RBAC and domain-service RBAC use the same policy facade. Sensitive browser routes additionally require a fresh existing MFA step-up.

### Telegram admin

Every `/admin` callback and every continuation of an admin FSM state re-resolves an active `AdminAccount` from the Telegram user. Revoking the admin account therefore blocks an already-open keyboard/FSM flow on the next interaction.

Handlers do not contain wallet/payment/campaign/support write logic. They collect input, render preview/confirmation, and call shared services.

### Internal admin API

`/internal/admin/*` is a separate FastAPI router outside `/api/v1`. Authentication requires:

- private-network/CIDR allowlist;
- exact-body HMAC-SHA256;
- timestamp skew validation;
- request correlation ID;
- explicit admin account/user UUID;
- idempotency key for every write;
- confirmation and step-up markers according to the domain action policy.

The route must also be absent from the public ingress. See `ops/nginx/internal-admin.conf.example` and `docs/ADMIN_RUNBOOK.md`.

## Domain invariants

### Admin command ledger

Privileged write commands reserve an append-only `admin_commands` row before the side effect. The idempotency identity binds:

- `idempotency_key`;
- admin account;
- action;
- target;
- canonical request hash.

Repeating the same command returns its stored result. Reusing the key for a different request is a conflict. Stored request/response payloads recursively redact secret-bearing fields.

### Wallet/payment safety

- Manual balance changes use `WalletService` and a command-derived wallet idempotency key.
- Payment reprocess delegates back to the authoritative payment reconciliation domain and never raw-credits a wallet.
- Operation replay creates a child generation with zero new charge and a durable generation outbox row.
- Operation refund discovers the original generation charge and refuses a second refund even when a different admin idempotency key is supplied.

### Versioned configuration/content

- Tariffs are immutable versions; publish supersedes the previous published version.
- CMS content is stored as immutable document versions; publishing changes status rather than rewriting an old published version.
- Runtime reload reads the latest published generation pricing into the current process.

### Durable operator delivery

Support replies are committed as `SupportMessage + SupportOutbox`. Notification campaigns are committed as campaign metadata plus unique `(campaign_id, user_id)` delivery rows. HTTP/Telegram request handlers never rely on direct delivery as their only side effect.

Workers claim rows with PostgreSQL `FOR UPDATE SKIP LOCKED`, leases, retry/backoff, terminal states, and restart recovery.

## Canonical transport modules

### Shared services

- `app/services/admin_policy.py`
- `app/services/admin_commands.py`
- `app/services/admin_users.py`
- `app/services/admin_reporting.py`
- `app/services/admin_exports.py`
- `app/services/admin_partners.py`
- `app/services/admin_payments.py`
- `app/services/admin_generation_operations.py`
- `app/services/admin_pricing.py`
- `app/services/admin_promos.py`
- `app/services/admin_content.py`
- `app/services/admin_support.py`
- `app/services/admin_cms.py`
- `app/services/admin_notifications.py`
- `app/services/admin_runtime.py`
- `app/services/admin_ai.py`

### Transport adapters

- Signed HTTP: `app/api/internal_admin.py`
- Browser shared control: `app/api/v1/admin_control.py`, `app/api/v1/admin_capabilities.py`
- Telegram: `app/bot/handlers/admin.py`, `app/bot/handlers/admin_extensions.py`
- Browser UI: `app/web/admin_app/control.html`, `control.js`, `control.css`

### Workers

- `app/workers/admin_support.py`
- `app/workers/admin_campaigns.py`

## Capability map

The implementation covers:

- summary, user lookup, block/unblock and manual credit/debit;
- partner analytics and withdrawal actions;
- finance reporting plus CSV/XLSX exports;
- versioned packages/image/video/partner/prompt pricing payloads;
- promo create/lookup/activation state;
- prompt moderation including deactivate;
- persisted subscription-required runtime toggle and pricing reload;
- broadcast preview/create/test/start/cancel with durable deliveries;
- read-only operational AI admin brief;
- payment recheck/reprocess;
- operation detail/timeline/replay/refund;
- support assignment/state/reply outbox;
- versioned CMS save/publish;
- admin trends and explicit feed moderation state;
- privileged generation preview.

See `docs/ADMIN_CAPABILITY_MATRIX.md` for the phase-1 capability inventory prepared before implementation.

## Adding a new privileged mutation

The required order is:

1. Define/extend the domain entity and allowed transitions.
2. Add an action policy and permission.
3. Implement a shared service use case.
4. Put destructive/retryable mutation behind `AdminCommandLedger` idempotency.
5. Record audit evidence where operator attribution matters.
6. Add durable outbox/delivery state if the action has an external side effect that can fail after commit.
7. Add tests for permission, validation, idempotency and failure/retry behavior.
8. Only then add Telegram, browser and/or signed HTTP adapters.

A privileged mutation implemented only in a handler, callback, JavaScript module or one transport is an architecture regression.
