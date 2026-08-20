# KSU / ROXY documentation index

**Documentation baseline:** 2026-08-20  
**Runtime baseline:** `main` after generation recovery hardening `fa787db146f713b8f6568f037dd2d1ca17c2c68c`.

This directory documents the production ROXY Telegram AI platform. When prose and runtime disagree, the order of authority is:

1. backend validation and database state;
2. published admin tariff/configuration;
3. `GET /api/v1/generations/models` and quote responses;
4. this documentation.

Runtime-affecting changes must update the relevant maintained documentation and configuration examples in the same PR before merge. Follow-up documentation-only PRs are reserved for repairing already-existing drift.

## Current product snapshot

- User product: `/mini-app/`.
- Privileged operations console: `/admin-app/`.
- Public denomination: **1 ROX = 1 RUB**.
- Create is split into independent **Photo** and **Video** flows; both end in the same server-driven schema builder and server quote/create pipeline.
- WAN 2.7 is available for both video and photo generation/editing (`wan/2-7-image` for the image product).
- Generation pricing is server-authoritative. Flat image prices and per-second video prices are resolved on the server. Parameter-aware tiers are supported where a model requires them (currently Kling Motion resolution tiers).
- Published Admin Tariffs `generation_pricing` overrides become live immediately and the latest published tariff is restored from PostgreSQL after restart.
- Pricing publish is privileged (`pricing.manage`) and keeps explicit confirmation + fresh MFA step-up requirements.
- Generation execution uses a durable PostgreSQL outbox plus recovery/reconciliation. Terminal success/failure states are monotonic, ambiguous Kie submissions are not blindly duplicated, and a configurable hard lifetime prevents indefinitely stuck paid work.
- Home promo artwork uses repository-owned slide assets; artwork must be rendered without crop, filters or generative redraw.

## Documentation map

### Product / Mini App

- `ROXY_BRAND.md` — brand, ROX rules and promo artwork contract.
- `MINI_APP_SHELL.md` — shell/navigation/Telegram WebApp behavior.
- `STUDIO_SHELL.md` — generation workspace shell.
- `ROXY_CREATE_CENTER.md` — current Photo/Video create entry flow.
- `GENERATION_MINI_APP.md` — dynamic generation schema, quote/create, pricing and recovery behavior.
- `RESULTS_HISTORY.md` — result/history/reuse semantics.
- `ROXY_PROFILE_CABINET.md` — profile cabinet.
- `WALLET_PAYMENTS.md` and `PRIMARY_CARD_CHECKOUT.md` — wallet and checkout.
- `PARTNER_CABINET.md`, `ROXY_CREATOR_PARTNERSHIP.md` — partner surfaces.
- `FEED_DOMAIN.md`, `HISTORY_SOCIAL.md`, `TRENDS.md` — discovery/social/trends.
- `PROMPT_TOOLS.md`, `ROXY_MUSIC_GENERATION.md` — extra creative tools.

### Economy / pricing

- `ROXY_ECONOMY_IMPLEMENTATION.md` — ROX denomination and current product economy.
- `ROXY_ECONOMY_REFERENCE.md` — compact economy reference.
- `GENERATION_MINI_APP.md` — generation price modes and current public tariff matrix.
- `ADMIN_CONSOLE.md` / `ADMIN_RUNBOOK.md` — changing and publishing runtime tariffs.

### Admin / security

- `ADMIN_CONSOLE.md` — visual admin application.
- `ADMIN_CONTOUR.md` — admin domain and privilege boundaries.
- `ADMIN_CAPABILITY_MATRIX.md` — permissions/capabilities.
- `ADMIN_SECURITY.md` — sessions, MFA, step-up, audit and bootstrap.
- `ADMIN_RUNBOOK.md` — operator procedures, including pricing publish/rollback.

### API / operations

- `API_REFERENCE.md` — HTTP route/auth boundaries.
- `OPERATIONS_RUNBOOK.md` — production deployment, workers, incidents, release checks and rollback.
- `GITHUB_PRODUCTION_DEPLOY.md` — GitHub production deployment flow.
- `REPOSITORY_HYGIENE.md` — merged-branch pruning, legacy-code cleanup and safe branch lifecycle.
- `OBSERVABILITY.md` — metrics/logging/tracing/alerts.
- `MEDIA_STORAGE.md` — durable product-owned media.
- `NOTIFICATION_DELIVERY.md` — durable notification delivery.

### Release / acceptance

- `ROXY_RELEASE_ACCEPTANCE.md` — production acceptance gate.
- `ROXY_TELEGRAM_ACCEPTANCE.md` — Telegram/mobile acceptance.
- `ONBOARDING.md` and `ROXY_BOT_LAUNCHER.md` — launch/onboarding contracts.

### Historical parity material

`parity-*.md` files are implementation history/checklists. They are not a source of truth for current pricing, model availability, recovery semantics or current Mini App navigation. For current behavior use this index and the domain documents above.

## Promo slide assets

Documentation mirrors of the current runtime slide binaries live in:

```text
docs/assets/roxy-promo/partner-referrals-runtime.webp
docs/assets/roxy-promo/creator-rewards-runtime.webp
```

The runtime files remain:

```text
app/web/mini_app/roxy-partner-referrals-slide-source.webp
app/web/mini_app/roxy-creator-rewards-slide-source.webp
```

The originals are user-supplied artwork. Do not recreate, restyle, re-typeset, crop or replace them with generated approximations. Asset replacement must preserve the exact approved composition and copy.
