# KSU / ROXY documentation index

**Documentation baseline:** 2026-08-22  
**Runtime baseline:** current `main`; use Git history/release SHA rather than a hard-coded historical commit in this index.

This directory documents the production ROXY Telegram AI platform. When prose and runtime disagree, the order of authority is:

1. backend validation and durable database state;
2. published admin tariff/configuration;
3. live server catalog/quote responses;
4. this documentation.

Runtime-affecting changes must update the relevant maintained documentation and configuration examples in the same PR before merge. Follow-up documentation-only PRs are reserved for repairing already-existing drift.

## Current product / runtime snapshot

- User product: `/mini-app/`.
- Privileged operations console: `/admin-app/`.
- Public denomination: **1 ROX = 1 RUB**.
- Create is split into independent **Photo** and **Video** flows; both end in the same server-driven schema builder and server quote/create pipeline.
- Successful generations expose server-computed post-generation actions in Telegram and deep-link into explicit derivative Mini App flows; ordinary Create remains fresh-by-default.
- The public Photo/Video model picker is intentionally limited to the maintained Tanya-style trending catalog; historical provider versions stay internal for history/recovery only and cannot be quoted/created as new work.
- Generation pricing is server-authoritative; published Admin Tariffs can override generation pricing and are restored from PostgreSQL after restart.
- Generation tasks snapshot the exact upstream provider model at creation. Customer titles/grouping never decide provider routing.
- Active `AdminAccount` users have zero customer-wallet ROX cost for AI generation/tool actions; retail price metadata and all resource/provider safety gates remain intact.
- Generation execution uses a durable PostgreSQL outbox plus recovery/reconciliation. Terminal states are monotonic and ambiguous provider submissions are not blindly duplicated.
- Product-owned result media is ingested to private S3-compatible storage.
- Current Kling coverage includes Kie-native Kling 2.5 Turbo Pro T2V/I2V plus Kling AI Avatar Standard/Pro with provider-contract allowlists and dynamic UI schemas.
- Registration-time referral admission is serialized/audited in PostgreSQL with hour/day/burst abuse controls.
- Production deployment targets an exact tested `main` SHA, validates a pre-migration PostgreSQL archive and explicitly starts the periodic `backup-worker`.
- Periodic PostgreSQL archives are custom-format, parsed with `pg_restore --list`, checksummed and retained in a private Docker volume; encrypted off-host durability remains an explicit operations responsibility.
- Home promo artwork uses repository-owned supplied assets; artwork must render without crop, filters or generative redraw.

## Documentation map

### Product / Mini App

- `ROXY_BRAND.md` — brand, ROX rules and promo artwork contract.
- `ROXY_DESIGN_SYSTEM.md` — customer Mini App design tokens, components and visual rules.
- `MINI_APP_SHELL.md` — shell/navigation/Telegram WebApp behavior.
- `STUDIO_SHELL.md` — generation workspace shell.
- `ROXY_CREATE_CENTER.md` — current Photo/Video create entry flow.
- `GENERATION_MINI_APP.md` — dynamic generation schema, quote/create, pricing and recovery behavior.
- `POST_GENERATION_ACTIONS.md` — Remix/Repeat/Edit/Animate/Publish semantics, lineage, privacy, Telegram deep links and troubleshooting.
- `TRENDING_MODEL_CATALOG.md` — current Tanya-derived Photo/Video product set, hidden legacy compatibility and release acceptance.
- `MODEL_IDENTITY_AND_ADMIN_FREE.md` — exact provider-model snapshotting, customer model presentation/grouping and zero-wallet-cost admin contract.
- `KLING_25_AVATAR_CONTRACT.md` — current Kie Kling 2.5 Turbo Pro T2V/I2V and Kling AI Avatar Standard/Pro provider/UI/billing contract.
- `RESULTS_HISTORY.md` — result/history/reuse semantics.
- `ROXY_PROFILE_CABINET.md` — profile cabinet.
- `WALLET_PAYMENTS.md` and `PRIMARY_CARD_CHECKOUT.md` — wallet and checkout.
- `PARTNER_CABINET.md`, `ROXY_CREATOR_PARTNERSHIP.md` — partner surfaces.
- `FEED_DOMAIN.md`, `HISTORY_SOCIAL.md`, `TRENDS.md` — discovery/social/trends.
- `PROMPT_TOOLS.md`, `ROXY_MUSIC_GENERATION.md` — extra creative tools.

### Economy / pricing

- `ROXY_ECONOMY_IMPLEMENTATION.md` — ROX denomination and current economy.
- `ROXY_ECONOMY_REFERENCE.md` — compact economy reference.
- `PRICING.md` — compact current generation tariff reference.
- `GENERATION_MINI_APP.md` — generation price modes and public tariff matrix.
- `MODEL_IDENTITY_AND_ADMIN_FREE.md` — active-admin zero customer cost while preserving retail/operator accounting.
- `ADMIN_CONSOLE.md` / `ADMIN_RUNBOOK.md` — changing and publishing runtime tariffs.

### Admin / security

- `ADMIN_CONSOLE.md` — visual admin application.
- `ADMIN_CONTOUR.md` — admin domain and privilege boundaries.
- `ADMIN_CAPABILITY_MATRIX.md` — permissions/capabilities.
- `ADMIN_SECURITY.md` — sessions, MFA, step-up, audit and bootstrap.
- `ADMIN_RUNBOOK.md` — operator procedures, including pricing publish/rollback.

### API / operations

- `API_REFERENCE.md` — HTTP route/auth boundaries.
- `OPERATIONS_RUNBOOK.md` — production deployment, workers, incidents and release operations.
- `GITHUB_PRODUCTION_DEPLOY.md` — exact-SHA GitHub production deployment flow.
- `DATABASE_BACKUPS.md` — periodic PostgreSQL backups, verification, restore drills and off-host durability boundary.
- `REPOSITORY_HYGIENE.md` — merged-branch pruning, legacy-code cleanup and safe branch lifecycle.
- `OBSERVABILITY.md` — metrics/logging/tracing/alerts.
- `MEDIA_STORAGE.md` — durable product-owned media.
- `NOTIFICATION_DELIVERY.md` — durable notification delivery.

### Release / acceptance

- `ROXY_RELEASE_ACCEPTANCE.md` — production acceptance gate.
- `TRENDING_MODEL_CATALOG.md` — focused current-model allowlist and legacy-removal acceptance requirements.
- `MODEL_IDENTITY_AND_ADMIN_FREE.md` — focused model-identity/admin-free release acceptance requirements.
- `POST_GENERATION_ACTIONS.md` — derivative action release checklist including Playwright, privacy, lineage and Seedance regression coverage.
- `ROXY_TELEGRAM_ACCEPTANCE.md` — Telegram/mobile acceptance.
- `ONBOARDING.md` and `ROXY_BOT_LAUNCHER.md` — launch/onboarding contracts.

### Historical parity material

`parity-*.md` files are implementation history/checklists. They are not a source of truth for current pricing, model availability, recovery semantics, backup policy or current Mini App navigation. Use the maintained domain documents above for current behavior.

## Promo slide assets

Documentation mirrors of the current runtime slide binaries live in:

```text
docs/assets/roxy-promo/partner-referrals-runtime.png
docs/assets/roxy-promo/creator-rewards-runtime.png
```

The runtime files remain:

```text
app/web/mini_app/roxy-partner-referrals-slide-source.png
app/web/mini_app/roxy-creator-rewards-slide-source.png
```

The originals are user-supplied artwork. Do not recreate, restyle, re-typeset, crop or replace them with generated approximations. Asset replacement must preserve the exact approved composition and copy.
