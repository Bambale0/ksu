# KSU / ROXY

Production Telegram AI content platform: Telegram bot + ROXY Next.js Mini App + FastAPI backend + PostgreSQL/Redis workers + AI generation providers + payments + privileged admin operations.

**Documentation baseline:** **2026-08-27**. Start with [`docs/README.md`](docs/README.md) and [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md).

## Current product

### ROXY customer Mini App

`/mini-app/` is the customer product. Primary navigation is:

```text
Студия · Лента · Каталог · Создать · Партнёры · Профиль
```

Current product contracts:

- **Лента** — full-screen TikTok-style vertical feed with `Для вас` / `Подписки`, likes, comments, sharing, author navigation and Repeat/remix actions.
- A hidden public prompt can remain repeatable: Repeat restores prompt/settings on the server and does not reveal them to another user.
- Publication/referral/profile deep links use a Direct Mini App link only with a real BotFather short name. Otherwise the supported fallback is `t.me/<bot>?start=<payload>`; ROXY does not invent `/app`.
- **Каталог** is the discovery/capability surface. Model-family sheets show an explicit backend-supplied price for each model variant.
- **Создать** is schema-driven from `GET /api/v1/generations/models`; clients do not hardcode provider parameter matrices.
- Ordinary new Create starts clean. History/feed Repeat are explicit server-owned restore flows.
- Curated **Тренды** use hidden validated recipes and the normal generation/quote/billing/outbox path.
- Active admins can manage Trends inline next to **Готовые сценарии**: create, durable preview upload, edit, duplicate, hide and restore. Backend separately verifies `AdminAccount` + `social.moderate`.
- History, reusable references, profile publication, wallet, partner/referral and prompt tools live in the same product shell.

## Model catalog and pricing

Current backend families include maintained image, video and music products such as Nano Banana, Seedream, GPT Image, WAN, Seedance, Kling, Veo, Grok, Gemini and music/Suno variants.

Authoritative catalog:

```text
GET /api/v1/generations/models
```

Authoritative quote:

```text
POST /api/v1/generations/quote
```

Public denomination:

```text
1 ROX = 1 RUB
```

Generation billing is server-owned. Models may use flat, per-second or parameter-tier pricing. The latest published Admin Tariffs `generation_pricing` version is persisted in PostgreSQL and synchronized by API workers before model/quote/create pricing decisions. Displayed variant price, quote and wallet debit use the same pricing resolver. Music/Suno participates in this same pricing contour.

Do not treat a README price example as billing truth; use the live catalog + latest published tariff.

## Feed/publication contract

Publication state is stored on the generation domain; feed is not a second task system.

- `private` — unpublished;
- `profile` — profile-visible;
- `feed` — profile-visible and eligible for public discovery.

Cross-user interactions re-authorize the requested feed/profile surface server-side. Prompt visibility is independent from allowed Repeat. Share endpoints return a usable Telegram link even when no Direct Mini App short name is configured.

See [`docs/FEED_DOMAIN.md`](docs/FEED_DOMAIN.md).

## Curated Trends

Public trend recipes keep the model prompt/provider parameters server-side. Customers receive only safe presentation/model/price/reference metadata and cannot override the curated model or hidden prompt.

Admin management is available through both:

- inline ROXY Mini App controls for an active Telegram-authenticated admin;
- `/admin-app/trends.html` under the separate privileged admin session.

Both use the same `AdminTrend` store and validated recipe model. Preview uploads are persisted under ROXY ownership rather than depending on expiring provider URLs.

See [`docs/TRENDS.md`](docs/TRENDS.md).

## Generation reliability

- durable PostgreSQL transactional generation outbox;
- leased worker processing and recovery/reconciliation;
- Redis used for latency/coordination/resource controls, not as the durable generation ledger;
- monotonic terminal generation states and idempotent refunds;
- ambiguous provider submission states are reconciled rather than blindly duplicated;
- product-owned result/reference media paths preferred over temporary provider URLs;
- controlled hard timeouts/recovery for abandoned provider work.

## Payments and economy

- **1 ROX = 1 RUB**;
- welcome/referral/partner reward accounting is server-owned;
- internal spend balance and withdrawable partner earnings remain separate accounting domains;
- payment intent creation is idempotent;
- provider reconciliation/refund state is durable;
- supported payment code paths are documented for Crypto Pay, T-Bank and YooKassa.

See `docs/WALLET_PAYMENTS.md`, `docs/PRIMARY_CARD_CHECKOUT.md` and the operations runbook.

## Admin / security

`/admin-app/` is the separate privileged operations console:

- separate admin identities/sessions;
- deny-by-default RBAC;
- TOTP MFA/recovery and fresh step-up for sensitive actions;
- audit trail;
- users, generations, payments, support, partners, promos/referrals, pricing and security operations.

Inline Trend management in `/mini-app/` is a convenience surface only. `me.is_admin` controls visibility; every write is authorized again on the backend.

Published generation tariffs are money-adjacent audited configuration. See [`docs/ADMIN_CONSOLE.md`](docs/ADMIN_CONSOLE.md) and `docs/ADMIN_RUNBOOK.md`.

## Release and system audit

The Mini App release gate contains:

```text
300 existing isolated user scenarios
+150 additional system-risk scenarios across 5 viewport classes
=450 named matrix scenarios
```

The same Chromium Playwright invocation also runs focused specs, so the raw runner test count is greater than 450. A separate iPhone/iPad WebKit responsive audit remains mandatory.

The +150 risk matrix covers:

- cross-user feed Repeat/share/privacy/comments;
- inline Trend admin authorization and CRUD;
- dynamic backend/admin pricing presentation;
- generation/quote/history/reference restoration;
- referral/profile link fallback;
- publication, wallet/payment and navigation integrity.

See [`docs/SYSTEM_AUDIT_2026-08-27.md`](docs/SYSTEM_AUDIT_2026-08-27.md).

Other release gates include full backend CI/regression, ROXY real-browser E2E, Admin Console, Batch Generation and ROXY Release Gate.

## Exact-SHA production deployment

Production deploys an exact tested `main` SHA and verifies health plus:

```text
GET /mini-app/release.json
```

The returned release SHA must equal the GitHub deploy SHA. A merge without a successful exact-SHA production deploy is not considered a completed rollout.

## PostgreSQL backup operations

- pre-migration production archive before Alembic;
- archive validation through `pg_restore --list` plus checksum;
- periodic `backup-worker` with private Docker volume retention;
- deployment verifies backup worker startup;
- local retained dumps are not a substitute for encrypted off-host disaster recovery and restore drills.

See `docs/DATABASE_BACKUPS.md` and `docs/GITHUB_PRODUCTION_DEPLOY.md`.

## Stack

- Python 3.12
- FastAPI + aiogram 3
- PostgreSQL 17 + async SQLAlchemy 2
- Redis 7.4
- Alembic
- Next.js customer Mini App
- separate static Admin Console
- private S3-compatible object storage
- Prometheus + optional OpenTelemetry
- Playwright Chromium + mobile WebKit acceptance
- GitHub Actions exact-SHA production deploy

## Local development

```bash
cp .env.example .env
docker compose up --build
```

Core checks:

```bash
alembic upgrade head
ruff check .
python -m compileall -q app tests
pytest -q
npm run typecheck --prefix frontend/mini-app
npm run build --prefix frontend/mini-app
```

Useful endpoints:

```text
GET  /health/live
GET  /health/ready
GET  /health/operational
GET  /metrics
GET  /mini-app/
GET  /mini-app/release.json
GET  /admin-app/
GET  /api/v1/generations/models
POST /api/v1/generations/quote
POST /api/v1/generations
GET  /api/v1/trends
GET  /api/v1/feed
```

Swagger/ReDoc are disabled in production.

## Documentation

Canonical entry points:

- `docs/README.md`
- `docs/CURRENT_STATE.md`
- `docs/SYSTEM_AUDIT_2026-08-27.md`
- `docs/API_REFERENCE.md`
- `docs/FEED_DOMAIN.md`
- `docs/TRENDS.md`
- `docs/ADMIN_CONSOLE.md`
- `docs/OPERATIONS_RUNBOOK.md`
- `docs/GITHUB_PRODUCTION_DEPLOY.md`
- `docs/ROXY_RELEASE_ACCEPTANCE.md`

Historical `parity-*` files are implementation records, not current navigation/pricing/feed/trend authority.
