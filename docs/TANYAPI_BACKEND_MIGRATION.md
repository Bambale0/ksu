# ROXY backend migration from `banano_kling:tanyapi`

**Status:** runtime migration substantially complete; production cutover evidence remains open.  
**Current baseline:** `main` after PR #188 (`ad46cef525057ed88c006871617c11d123557fd4`), 2026-08-20.

## Decision

ROXY keeps the current KSU Mini App and customer-facing ROXY brand, while selected production-proven backend behavior from `Bambale0/banano_kling:tanyapi` is ported behind ROXY's own contracts.

The donor is an operational reference, not a shared runtime. ROXY does **not** point at Tanya/NEUROMIX production data or credentials. ROXY keeps isolated PostgreSQL, Redis, media storage, bot token, domains and provider/payment credentials.

The migration is no longer a broad source-copy exercise. Proven mechanisms are clean-ported only where they improve the current ROXY architecture; current provider contracts override stale Tanya payloads when the upstream API has changed.

## Product boundary

Telegram is transport only. There is no parallel customer text-bot menu.

Customer UX lives in the Mini App:

- onboarding;
- generation setup and references;
- balance/top-up;
- history;
- feed/catalog;
- profile;
- referrals/partner program;
- support.

The Telegram bot accepts `/start`, preserves referral attribution and deep-link intent, removes the legacy persistent reply keyboard and returns the Mini App launcher. Any other customer message is redirected to the same product entrypoint.

## Migration principles

1. Preserve the current ROXY Mini App URLs and API contract where practical.
2. Port proven backend behavior behind compatibility facades instead of rewriting the frontend around donor-specific routes.
3. Keep current provider/model IDs stable internally; rebrand only customer-visible names/copy/metadata.
4. Never share Tanya production DB, Redis namespace, media root or secrets with ROXY.
5. Keep ROX billing and approved/published ROXY tariffs as the public economy.
6. Every migrated subsystem needs regression coverage before old KSU/Tanya staging implementations are retired.
7. Roll out by subsystem so production can be recovered without reverting unrelated product work.
8. Current upstream provider schemas are authoritative over historical Tanya payloads.
9. Runtime/config changes update maintained docs and `.env.example` in the same PR.

## Donor → ROXY mapping

| Donor (`banano_kling:tanyapi`) | ROXY target | Current state |
| --- | --- | --- |
| `bot/miniapp.py` | `app/api/v1/*` | Mini App remains the customer contract; Telegram stays launcher/transport only |
| generation handlers/services | `app/services/generations.py`, outbox/recovery workers/providers | Durable submission/recovery, exactly-once refund boundary and current provider adapters shipped |
| upload/reference storage | upload/reference + media services | Image/video/audio uploads, reusable references and product-owned result ingest shipped |
| `data/price.json` + pricing services | ROXY tariff/admin services | ROXY pricing is server-authoritative; Admin Tariffs can publish validated runtime overrides |
| payment services | payment APIs/workers/provider adapters | Durable intents, reconciliation and conservative lost-create-response recovery shipped |
| partner/referral services | referral/partner/feed attribution services | Two-level partner accounting plus registration-time anti-fraud and feed/remix attribution shipped |
| production media topology | ROXY media delivery | Private product-owned S3-compatible storage; no cross-product storage sharing |
| production workflows | `.github/workflows/*` | Exact-SHA release gates, fail-closed SSH config, pre-migration DB archive and backup-worker shipped |

## Phase status

### Phase 0 — customer shell — complete

- [x] make Telegram an app-only launcher;
- [x] remove production registration of customer text-menu routers;
- [x] preserve `/start` referral attribution/deep-link intent;
- [x] move onboarding UX into Mini App;
- [x] add contracts preventing text-menu regression.

### Phase 1 — generation + references — runtime complete

- [x] align donor/provider behavior with the ROXY model catalog rather than copying the donor frontend;
- [x] preserve current `/api/v1/uploads` and generation API contracts;
- [x] support image/video/audio upload and reusable references;
- [x] use durable PostgreSQL generation outbox/recovery instead of Redis-only work state;
- [x] make terminal generation states monotonic and refunds idempotent/exactly-once;
- [x] classify provider submission failures into permanent/retryable/uncertain and avoid blind duplicate paid tasks;
- [x] reconcile callbacks/provider status and hard-timeout unrecoverable work;
- [x] ingest successful provider media into product-owned storage;
- [x] preserve ROXY dynamic model controls and server quote/debit contract;
- [x] implement current Seedance 2.5 callable contract;
- [x] implement current Kling 2.5 Turbo Pro T2V/I2V and Kling AI Avatar Standard/Pro from current Kie contracts rather than old Tanya payloads;
- [x] CI/Batch/full-regression gates cover generation, model UI and provider normalization contracts.

Maintained current-provider documents include `SEEDANCE_25_CONTRACT.md`, `KLING_25_AVATAR_CONTRACT.md`, `GENERATION_MINI_APP.md` and `ROXY_RELEASE_ACCEPTANCE.md`.

### Phase 2 — payments + wallet — runtime complete

- [x] keep public economy at `1 ROX = 1 RUB`;
- [x] keep quote and actual debit on one server-side pricing resolver;
- [x] support published Admin Tariffs with permission/confirmation/MFA protections;
- [x] use durable idempotent payment intents/reconciliation;
- [x] retain current Crypto Pay, T-Bank, YooKassa and primary hosted-card contours;
- [x] prevent blind second hosted-card invoice creation after an uncertain create response;
- [x] recover a lost hosted-card contract id only after authoritative provider lookup and unique amount/currency/email correlation;
- [x] keep wallet credit idempotent under duplicate callbacks/reconciliation;
- [x] payment/economy/admin regression gates are required before merge.

See `WALLET_PAYMENTS.md`, `PRIMARY_CARD_CHECKOUT.md`, `ROXY_ECONOMY_IMPLEMENTATION.md`, `ADMIN_RUNBOOK.md` and `ROXY_RELEASE_ACCEPTANCE.md`.

### Phase 3 — referral / partner / feed attribution — runtime complete

- [x] preserve immutable inviter attribution for new users;
- [x] keep spend-wallet invitation bonus separate from withdrawable referral earnings;
- [x] preserve 30% / 5% referral accounting and partner withdrawal flows;
- [x] serialize registration-time referral admission under PostgreSQL locking;
- [x] reject/audit self, missing, inactive and configured abuse-limit referrals before relation/bonus creation;
- [x] preserve exactly-once prompt-repeat/source-author reward semantics;
- [x] preserve source/remix attribution in feed/profile flows;
- [x] keep feed prompt/reference privacy and trend action restrictions server-side;
- [x] regression tests cover referral admission, concurrency, partner accounting and feed/remix attribution.

See `PARTNER_CABINET.md`, `ROXY_ECONOMY_IMPLEMENTATION.md`, `FEED_DOMAIN.md` and `ROXY_RELEASE_ACCEPTANCE.md`.

### Phase 4 — production cutover — implementation complete, evidence partially open

Implemented in repository/runtime contract:

- [x] isolated ROXY PostgreSQL / Redis / media configuration;
- [x] provider/payment credentials remain separate from donor production;
- [x] production workflow deploys an exact current `main` SHA only after CI + Batch Generation + Admin Console are green;
- [x] production deployment is fail-closed when required SSH secrets are absent;
- [x] deployment creates a custom-format pre-migration PostgreSQL archive and requires non-empty + `pg_restore --list` + SHA-256 before Alembic;
- [x] periodic `backup-worker` creates validated/checksummed PostgreSQL archives in a private volume and retries failed attempts promptly;
- [x] operations docs explicitly require encrypted off-host durability and isolated restore drills;
- [x] Mini App release metadata is checked against the intended production SHA by the deploy workflow.

Still requires real production evidence before this migration epic can be closed:

- [ ] verify a successful `Deploy Production` run for the current cutover SHA and record the deployed SHA;
- [ ] verify the first/current periodic production backup plus checksum/catalog validation;
- [ ] verify the configured encrypted off-host backup copy/snapshot is fresh;
- [ ] execute and record an isolated PostgreSQL restore drill from a production backup;
- [ ] execute production smoke covering auth/onboarding, upload/reference, representative image + T2V/I2V/Avatar generation, callback/reconciliation, owned-media delivery, charge/refund, payment top-up, referral attribution and Admin Tariff quote/debit;
- [ ] verify rollback/recovery procedure operationally without automatic Alembic downgrade;
- [ ] only after the evidence above, close migration epic #177 and retire any remaining migration-only compatibility artifacts that are no longer used.

## Cutover evidence checklist

Record evidence in the release/epic discussion without copying secrets or customer data.

```text
main SHA:
Deploy Production run:
production release.json SHA:
health/live:
health/ready:
health/operational:
predeploy backup verified:
periodic latest.dump verified:
off-host copy freshness:
restore drill database/result:
generation smoke models/results:
payment smoke provider/result:
refund/recovery smoke:
referral smoke:
admin tariff publish/quote/debit/rollback:
operator/date:
```

A GitHub merge or green CI run is **not** sufficient evidence that production received the release.

## Explicit non-goals

- Do not copy the Tanya/NEUROMIX frontend.
- Do not reuse Tanya production users, balances, referrals, media or payment records.
- Do not rename stable current internal provider identifiers just for branding.
- Do not keep customer functionality duplicated in Telegram text handlers.
- Do not port historical provider fields when current upstream callable schemas no longer expose them.
- Do not treat a same-host Docker backup volume as off-host disaster recovery.

## Current authority rule

For Phases 0–3, current ROXY runtime/docs on `main` are authoritative; `tanyapi` is now historical behavioral reference only.

For Phase 4, repository implementation is present, but **production cutover is not considered proven until the production deploy, backup/restore and smoke evidence above is recorded**.
