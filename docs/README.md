# KSU / ROXY documentation index

**Documentation baseline:** **2026-08-27**  
**Runtime baseline:** current `main`; production acceptance is always tied to an exact tested/deployed SHA.

This directory documents the production ROXY Telegram AI platform. When prose and runtime disagree, the order of authority is:

1. backend validation and durable database state;
2. latest published admin configuration/tariff in PostgreSQL;
3. live server catalog/quote/API responses;
4. exact-SHA CI/deploy evidence;
5. this documentation.

Runtime-affecting changes must update maintained documentation in the same PR.

## Current product / runtime snapshot

- User product: `/mini-app/`.
- Primary navigation: **Студия · Лента · Каталог · Создать · Партнёры · Профиль**.
- `Лента` is the full-screen TikTok-style public discovery surface, not the historical grid feed.
- Foreign-user Repeat is server-owned and may remain available when the public prompt is hidden; hidden prompt text is not disclosed to the repeating client.
- Publication/profile/referral links use Direct Mini App `startapp` only with a real configured BotFather short name; otherwise they fall back to `t.me/<bot>?start=<payload>`.
- `Каталог` is discovery/product capability navigation. Generation model variants expose explicit backend-supplied prices.
- Create uses the backend `ui_schema`, quote and create pipeline; ordinary new Create is fresh-by-default while history/feed actions explicitly restore source settings server-side.
- Generation pricing is server-authoritative. The latest published Admin Tariffs `generation_pricing` version is persisted in PostgreSQL and synchronized by API workers before model/quote/create pricing decisions. Image, video and music/Suno participate in the same operator pricing contour.
- Privileged operations console: `/admin-app/` with separate admin session, RBAC, MFA/step-up and audit.
- Active admins additionally get Tanya-style inline Trend management inside **Тренды → Готовые сценарии**: create, durable preview upload, edit, duplicate, hide and restore. Backend always re-authorizes `social.moderate`.
- Public denomination: **1 ROX = 1 RUB**.
- Generation execution uses a durable PostgreSQL outbox plus recovery/reconciliation. Product-owned result/reference media paths are preferred over temporary provider URLs.
- Production deployment targets an exact tested `main` SHA and validates `/mini-app/release.json` after health checks.
- Mandatory Mini App acceptance now includes the existing 300 scenario matrix plus 150 system-risk scenarios across five viewport classes (**450 named matrix scenarios**) and separate iPhone/iPad WebKit responsive audits.

## Documentation map

### Current status / audit

- `CURRENT_STATE.md` — compact cross-domain current state.
- `SYSTEM_AUDIT_2026-08-27.md` — 450-scenario system audit scope/evidence.
- `ROXY_RELEASE_ACCEPTANCE.md` — production release acceptance.

### Product / Mini App

- `ROXY_BRAND.md` — brand/ROX/promo artwork rules.
- `ROXY_DESIGN_SYSTEM.md` — Mini App visual system.
- `MINI_APP_SHELL.md` — shell/navigation/Telegram WebApp behavior.
- `STUDIO_SHELL.md` — studio workspace shell.
- `ROXY_CREATE_CENTER.md`, `GENERATION_MINI_APP.md` — schema-driven create, quote and generation behavior.
- `POST_GENERATION_ACTIONS.md`, `RESULTS_HISTORY.md` — repeat/remix/history/reuse contracts.
- `FEED_DOMAIN.md`, `HISTORY_SOCIAL.md` — TikTok-style feed/social/publication domain.
- `TRENDS.md` — public curated Trends and inline admin management.
- `TRENDING_MODEL_CATALOG.md`, `MODEL_IDENTITY_AND_ADMIN_FREE.md` — customer model presentation and provider identity rules.
- `KLING_25_AVATAR_CONTRACT.md` — Kling 2.5/Avatar provider/UI/billing contract.
- `ROXY_PROFILE_CABINET.md` — profile cabinet.
- `PARTNER_CABINET.md`, `ROXY_CREATOR_PARTNERSHIP.md` — partner/referral surfaces.
- `PROMPT_TOOLS.md`, `ROXY_MUSIC_GENERATION.md` — extra creative tools.
- `WALLET_PAYMENTS.md`, `PRIMARY_CARD_CHECKOUT.md` — wallet and checkout.

### Economy / pricing

- `ROXY_ECONOMY_IMPLEMENTATION.md`, `ROXY_ECONOMY_REFERENCE.md` — current ROX economy.
- `PRICING.md`, `GENERATION_MINI_APP.md` — price modes/current runtime contract.
- `ADMIN_CONSOLE.md`, `ADMIN_RUNBOOK.md` — published pricing and operator procedures.

Live `/api/v1/generations/models` and `/api/v1/generations/quote` override any example values in prose.

### Admin / security

- `ADMIN_CONSOLE.md` — privileged console plus inline Trend admin boundary.
- `ADMIN_CONTOUR.md` — admin domain.
- `ADMIN_CAPABILITY_MATRIX.md` — permissions.
- `ADMIN_SECURITY.md` — sessions/MFA/step-up/audit/bootstrap.
- `ADMIN_RUNBOOK.md` — operator procedures.

### API / operations

- `API_REFERENCE.md` — current route/auth boundaries.
- `OPERATIONS_RUNBOOK.md` — deployment/workers/incidents.
- `GITHUB_PRODUCTION_DEPLOY.md` — exact-SHA deployment.
- `DATABASE_BACKUPS.md` — PostgreSQL backup/restore/off-host responsibility.
- `OBSERVABILITY.md` — metrics/logging/tracing/alerts.
- `MEDIA_STORAGE.md` — durable media.
- `NOTIFICATION_DELIVERY.md` — durable notification delivery.
- `REPOSITORY_HYGIENE.md` — repository lifecycle.

## Release test authority

The required browser gate is `.github/workflows/miniapp-playwright.yml`:

```text
Run 450-scenario Mini App audit        Chromium
Run iPhone/iPad WebKit responsive audit
```

The Chromium invocation also executes focused Playwright specs outside the two 300+150 matrices, so its raw test count is intentionally greater than 450. Do not equate the raw runner count with the named matrix count.

Other mandatory gates include CI/backend regression, ROXY browser E2E, Admin Console, Batch Generation and ROXY Release Gate.

## Historical parity material

`parity-*.md` files and old epic notes are implementation history, not current navigation/pricing/feed/trend authority. Use the maintained documents above and exact-SHA release evidence for current behavior.
