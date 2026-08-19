# KSU / ROXY

Production Telegram AI content platform: Telegram bot + ROXY Mini App + FastAPI backend + PostgreSQL/Redis workers + Kie generation pipeline + payments + privileged admin console.

**Documentation status:** synchronized with the production code baseline on **2026-08-20**. Start with [`docs/README.md`](docs/README.md).

## Current product

### User Mini App

- `/mini-app/` is the ROXY user product.
- Primary customer navigation: Create, Prompts, My ROX, Earn, Profile, with additional Studio/history/discovery surfaces mounted inside the same shell.
- Create opens a media-first chooser and then independent **Photo** or **Video** generation flows. Selecting Video no longer routes through the home screen.
- Model/product cards feed the existing dynamic builder. The backend `ui_schema` remains the source of truth for fields, scenarios, validation hints and billing duration.
- Quote: `POST /api/v1/generations/quote`.
- Create: `POST /api/v1/generations` with signed Telegram `initData`.
- Local media upload: `POST /api/v1/uploads/kie`; provider credentials never reach the browser.
- Product-owned media ingestion, result polling, history/reuse, wallet, profile, referrals, creator/partner flows, feed/trends and prompt tools are implemented in the same product shell.

### Generation catalog

Current backend families include Nano Banana, Seedream, GPT Image, WAN, Seedance, Kling, Veo, Grok and Gemini variants implemented in `ModelCatalog`.

WAN 2.7 includes both video generation/editing and a photo generation/editing product backed by Kie `wan/2-7-image`.

The runtime model catalog is authoritative:

```text
GET /api/v1/generations/models
```

Do not hardcode provider parameter matrices in clients. The Mini App consumes the returned model metadata and `ui_schema`.

### ROX and generation pricing

Public denomination:

```text
1 ROX = 1 RUB
```

Generation billing is server-side:

```text
flat image:       cost_rox = flat_price_rox
per-second video: cost_rox = unit_price_rox × billing_seconds
```

Current public pricing baseline:

| Product | Public price |
| --- | ---: |
| Nano Banana PRO | 25 ROX |
| WAN 2.7 photo | 20 ROX |
| GPT Image 2 | 20 ROX |
| Nano Banana 2 | 25 ROX |
| Nano Banana 2 Lite | 25 ROX |
| Seedream 4.5 | 20 ROX |
| Seedream 5 Pro | 20 ROX |
| Seedance 2.0 | 40 ROX/s |
| Seedance 2.5 | 60 ROX/s |
| Kling 3.0 | 30 ROX/s |
| Veo 3.1 | 35 ROX/s |
| Grok | 15 ROX/s |
| Grok Imagine 1.5 | 30 ROX/s |
| Gemini Omni | from 30 ROX/s |
| Kling Motion 2.6 720p / 1080p | 20 / 30 ROX/s |
| Kling Motion 3.0 720p / 1080p | 60 / 80 ROX/s |

Exact model IDs and live values come from the backend catalog and published pricing overrides. If a model has multiple variants, the server resolves the applicable model/parameter price tier before both quote and debit.

### Live admin pricing

`/admin-app/` is the separate privileged operations console. The Admin Tariffs contour can publish `generation_pricing` overrides.

Important guarantees:

- published generation pricing becomes effective in runtime without a client deploy;
- quote and actual wallet debit use the same pricing resolver;
- the most recent published pricing is restored from PostgreSQL after application restart;
- invalid model IDs, incompatible price modes and unsupported tier parameters are rejected;
- publish requires `pricing.manage`, explicit confirmation and fresh MFA step-up according to the admin security policy.

See `docs/ADMIN_CONSOLE.md`, `docs/ADMIN_RUNBOOK.md` and `docs/GENERATION_MINI_APP.md`.

### Promo slides / assets

The ROXY home promo carousel uses repository-owned user-supplied artwork. Runtime sources:

```text
app/web/mini_app/roxy-partner-referrals-slide-source.webp
app/web/mini_app/roxy-creator-rewards-slide-source.webp
```

Documentation mirrors are stored under `docs/assets/roxy-promo/`. The approved compositions must be preserved exactly: no generative redraw, restyling, re-typesetting or crop. The carousel uses contain-style rendering and no visual filter/transform processing.

## Generation reliability

- Kie Market unified task API + `recordInfo` reconciliation.
- Kie callback HMAC verification.
- PostgreSQL **transactional outbox** for durable generation submission.
- `generation-worker` uses leased rows and `FOR UPDATE SKIP LOCKED`.
- Redis wake-up is latency optimization; PostgreSQL is durable work state.
- Recovery for stale submission/generation states and idempotent refunds on unrecoverable provider failure.
- Successful results create durable media ingest work; `media-worker` copies bounded HTTPS sources into private product-owned S3-compatible storage.
- Deterministic storage keys make retries converge safely.

## Payments and economy

- **1 ROX = 1 RUB**.
- 50 ROX welcome bonus.
- 30 ROX inviter bonus.
- 5 ROX paid prompt-repeat reward to the original author; no self-reward.
- Referral top-up rewards: 30% level 1, 5% level 2.
- Minimum partner withdrawal: 3,000 ROX.
- Internal spend ROX and withdrawable partner earnings remain separate accounting domains.
- Payment intents are idempotent and provider reconciliation is durable.
- Supported provider integrations include Crypto Pay, T-Bank and YooKassa code paths documented in the payment/runbook docs.

## Admin/security

The repository ships a protected visual admin application at `/admin-app/` plus the privileged API/security contour:

- separate admin identities/sessions;
- deny-by-default RBAC;
- TOTP MFA and recovery codes;
- fresh step-up for high-impact actions;
- audit trail;
- user/support/generation/payment/withdrawal/promo/referral/security operations;
- live tariff publishing and rollback workflow.

The admin bearer token is held in memory by the client and is not persisted to browser storage.

## Stack

- Python 3.12
- FastAPI + aiogram 3
- PostgreSQL 17 + async SQLAlchemy 2
- Redis 7.4
- Alembic
- private S3-compatible object storage
- vanilla HTML/CSS/JavaScript Telegram Mini Apps
- Prometheus + optional OpenTelemetry
- GitHub Actions CI / production deploy workflow

## Runtime topology

```text
Telegram / browser
        |
        v
 HTTPS reverse proxy
        |
        v
 FastAPI app :8000 --------------------> PostgreSQL
    |                                      |-- business state
    |                                      |-- generation outbox
    |                                      |-- published tariffs/admin audit
    |                                      |-- media/payment/history state
    |
    +--> Redis --------------------------> limits / FSM / wake / telemetry
    |          |
    |          +--> generation-worker --------> Kie.ai
    |          +--> media-worker -------------> private object storage
    |          +--> payment-worker -----------> payment providers
    |
    +--> /mini-app/   ROXY customer UI
    +--> /admin-app/  privileged operator UI
```

## Local development

```bash
cp .env.example .env
docker compose up --build
```

Useful endpoints:

```text
GET    /health/live
GET    /health/ready
GET    /health/operational
GET    /metrics
GET    /mini-app/
GET    /admin-app/
GET    /api/v1/generations/models
POST   /api/v1/generations/quote
POST   /api/v1/generations
GET    /api/v1/generations
GET    /api/v1/generations/{generation_id}
POST   /api/v1/uploads/kie
GET    /api/v1/payments/packages
POST   /api/v1/payments
```

Swagger/ReDoc are disabled in production.

## Core production configuration

Start from `.env.example`. Key groups:

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://api.example.com
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
BOT_TOKEN=...
TELEGRAM_WEBHOOK_SECRET=...

INTERNAL_CREDIT_RUB=1
KIE_API_KEY=...
KIE_UPLOAD_BASE_URL=...
KIE_WEBHOOK_HMAC_KEY=...
GENERATION_PRICING_JSON={}

ADMIN_SECURITY_KEY=<dedicated-random-secret-32+-chars>
ADMIN_REQUIRE_MFA=true
```

`KIE_UPLOAD_BASE_URL` controls the configured Kie upload base used by the server-side upload integration; it is not exposed as a provider credential to the Mini App.

A published admin tariff can override generation pricing at runtime; `GENERATION_PRICING_JSON` is therefore not the only production pricing source. See the admin runbook before changing pricing manually in environment configuration.

## Migrations / CI

```bash
alembic upgrade head
ruff check .
python -m compileall -q app tests
pytest -q
```

CI also syntax-checks Mini App/Admin JavaScript and executes focused ROXY/admin/generation contracts before full regression.

## Documentation

Canonical documentation and operations references:

- `docs/README.md`
- `docs/API_REFERENCE.md`
- `docs/OPERATIONS_RUNBOOK.md`
- `docs/GENERATION_MINI_APP.md`
- `docs/ADMIN_SECURITY.md`
- `docs/ADMIN_RUNBOOK.md`
- `docs/ROXY_RELEASE_ACCEPTANCE.md`

Historical `parity-*` files are implementation records, not current pricing/model/navigation authority.
