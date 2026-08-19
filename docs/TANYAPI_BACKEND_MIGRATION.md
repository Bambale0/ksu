# ROXY backend migration from `banano_kling:tanyapi`

Status: active migration.

## Decision

ROXY keeps the current KSU Mini App and customer-facing ROXY brand, while the backend is progressively aligned with the production-proven backend from `Bambale0/banano_kling`, branch `tanyapi`.

The donor is used as the operational reference because it already runs production generation, uploads/references, provider callbacks, payments, partner flows, media delivery and production CI/CD. We do **not** point ROXY at Tanya/NEUROMIX production data or credentials. ROXY keeps isolated databases, Redis, media, bot token, provider/payment credentials and domains.

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

The Telegram bot accepts `/start`, preserves referral attribution and deep-link intent, removes the legacy persistent reply keyboard and returns a single Mini App launcher. Any other customer message is redirected to the same launcher.

## Migration principles

1. Preserve the current ROXY Mini App URLs and API contract where practical.
2. Port proven backend behavior behind compatibility facades instead of rewriting the frontend around donor-specific routes.
3. Keep provider/model IDs stable internally; rebrand only customer-visible names/copy/metadata.
4. Never share Tanya production DB, Redis namespace, media root or secrets with ROXY.
5. Keep ROX billing and the approved ROXY public tariffs as the public economy.
6. Every migrated subsystem needs regression tests before the old KSU implementation is retired.
7. Roll out by subsystem so production can be rolled back without a full-repository revert.

## Donor → ROXY mapping

| Donor (`banano_kling:tanyapi`) | ROXY target | Migration intent |
| --- | --- | --- |
| `bot/miniapp.py` | `app/api/v1/*` | Mini App auth, upload/reference and generation behavior |
| generation handlers/services | `app/services/generations.py`, workers/providers | provider submission, retries, callbacks, reference semantics |
| upload/reference storage | `app/api/v1/uploads.py`, media services | resilient upload flow and reference persistence |
| `data/price.json` + pricing services | ROXY tariff/admin services | operator-editable ROX tariffs |
| payment services | `app/api/v1/payments.py`, card/crypto services | idempotent top-ups and callbacks |
| partner/referral services | ROXY referral/partner services | attribution, partner accounting and payouts |
| production media topology | ROXY media delivery | separated origin/CDN, no cross-product storage |
| production workflows | `.github/workflows/*` | exact-SHA, fail-closed production delivery |

## Phases

### Phase 0 — customer shell

- [x] create migration branch;
- [x] make Telegram an app-only launcher;
- [x] remove production registration of text-menu routers;
- [x] preserve `/start` referral attribution;
- [x] move onboarding UI into Mini App;
- [x] add contract tests preventing text-menu regression.

### Phase 1 — generation + references

- [ ] inventory donor model/provider adapters against ROXY catalog;
- [ ] port donor reference/media semantics behind current `/api/v1/uploads` and generation APIs;
- [ ] port provider callback normalization/recovery where donor is stronger;
- [ ] preserve ROXY model controls, ROX pricing and current Mini App payloads;
- [ ] image, image-edit, T2V, I2V, V2V and Motion E2E tests.

### Phase 2 — payments + wallet

- [ ] compare T-Bank/CryptoBot callback/idempotency behavior;
- [ ] port proven payment failure/retry/refund paths;
- [ ] keep ROXY wallet and public tariff source of truth;
- [ ] verify admin price edits affect quote and charge atomically.

### Phase 3 — partner/feed/profile

- [ ] migrate proven referral attribution/accounting paths where stronger;
- [ ] preserve ROXY feed/profile contracts and current Mini App UI;
- [ ] validate share/remix/repeat attribution end-to-end.

### Phase 4 — operations cutover

- [ ] isolated ROXY Postgres/Redis/media roots;
- [ ] provider/payment secrets separated from donor production;
- [ ] exact-SHA production deployment and health checks;
- [ ] backup/restore and rollback drill;
- [ ] production smoke: auth, upload, generation, callback, charge/refund, admin tariff edit.

## Explicit non-goals

- Do not copy the Tanya/NEUROMIX frontend.
- Do not reuse Tanya production users, balances, referrals, media or payment records.
- Do not rename stable internal provider identifiers just for branding.
- Do not keep customer functionality duplicated in Telegram text handlers.

## Current cutover rule

Until a subsystem is checked off in this document, the current ROXY implementation remains authoritative for that subsystem. The donor code is the behavioral reference, not a reason to bypass regression gates.
