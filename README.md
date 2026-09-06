# ROXY AI Platform

> **Production AI content platform** · FastAPI · PostgreSQL · Redis · Telegram Mini App · async workers · payments · object storage · CI/CD
>
> Repository codename: `ksu`.

ROXY is a production-grade platform for AI image and video generation. It combines a Telegram bot, a customer Mini App, a FastAPI backend, durable background workers, billing, creator/referral mechanics, a privileged admin console, and production operations in one system.

This repository is one of the main portfolio projects in this GitHub profile because it demonstrates not only AI API integration, but also backend architecture, reliability, security, payments, observability, and deployment.

## Engineering highlights

- **FastAPI + aiogram 3** application with signed Telegram `initData` authentication.
- **PostgreSQL + async SQLAlchemy + Alembic** for durable business state.
- **Redis** for FSM/cache/wake-up/operational coordination.
- PostgreSQL **transactional outbox** for reliable generation submission.
- Dedicated **generation, media and payment workers** with leased jobs and idempotent processing.
- Multi-provider AI catalog: Nano Banana, Seedream, GPT Image, WAN, Seedance, Kling, Veo, Grok and Gemini families.
- Server-side quote/debit pipeline so the client never becomes the pricing source of truth.
- Product-owned **S3-compatible media storage** instead of relying on temporary provider URLs.
- Protected admin application with **RBAC, TOTP MFA, step-up confirmation and audit trail**.
- Prometheus metrics, operational health checks and optional OpenTelemetry tracing.
- Automated PostgreSQL backups with validation, checksums and pre-migration backup gates.
- GitHub Actions release flow with exact-SHA deployment and production verification.

## Product surfaces

### Customer Mini App

The customer product is served from `/mini-app/` and provides:

- photo and video generation;
- dynamic model-specific forms driven by backend `ui_schema`;
- uploads and reference-based generation;
- generation history and reuse;
- wallet and payments;
- public feed and trends;
- prompt marketplace/tools;
- referrals, creator and partner flows;
- profile and account surfaces.

### Telegram bot

Telegram acts as a native product channel and entry point while the generation/business logic remains in the backend rather than being tied to chat handlers.

### Admin console

A separate privileged interface covers user, generation, payment, withdrawal, referral, promo, pricing and security operations. High-impact actions are protected by explicit permissions and MFA policies.

## Architecture

```text
Telegram / Mini App
        |
        v
 HTTPS reverse proxy
        |
        v
 FastAPI application
    |        |          |
    |        |          +--> Admin API / Admin App
    |        |
    |        +--> Redis -----------------------+
    |                                          |
    v                                          v
PostgreSQL                              background workers
  |                                     |-- generation-worker --> AI providers
  |                                     |-- media-worker ------> object storage
  |                                     +-- payment-worker ----> payment providers
  |
  +-- users / wallet / generations / outbox
  +-- pricing / payments / referrals
  +-- audit / admin / operational state

backup-worker --> validated PostgreSQL archives
```

## Reliability model

External AI generation is asynchronous and failure-prone by nature, so the project treats provider calls as durable jobs rather than request/response-only operations.

Key guarantees include:

- durable submission state in PostgreSQL;
- leased worker rows and safe concurrent processing;
- callback verification;
- recovery of stale generation states;
- idempotent refunds and payment reconciliation;
- deterministic media ingest keys so retries converge safely;
- exact-SHA production deploys;
- health and revision verification after deployment.

## API examples

```text
GET    /health/live
GET    /health/ready
GET    /health/operational
GET    /metrics
GET    /api/v1/generations/models
POST   /api/v1/generations/quote
POST   /api/v1/generations
GET    /api/v1/generations/{generation_id}
POST   /api/v1/uploads/kie
GET    /api/v1/payments/packages
POST   /api/v1/payments
```

The backend model catalog is authoritative. Client applications consume model metadata and UI schemas instead of hardcoding provider parameter matrices.

## Runtime configuration contracts

Production configuration is environment-driven. Important runtime contracts include:

- `KIE_UPLOAD_BASE_URL` — server-side KIE upload endpoint/base configuration; provider credentials remain server-side.
- `ADMIN_SECURITY_KEY` — dedicated secret material for the privileged admin security contour.
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` — optional OpenTelemetry trace exporter endpoint.

Real values belong in deployment secrets and are never committed to the repository.

## Observability

- `GET /metrics` exposes Prometheus metrics.
- `GET /health/operational` reports operational worker/readiness state.
- OpenTelemetry traces can be exported through `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`.
- Production alert rules live in [`ops/prometheus-alerts.yml`](ops/prometheus-alerts.yml).
- Detailed metric and worker-heartbeat contracts are documented in [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md).

## Stack

| Area | Technology |
| --- | --- |
| Backend | Python 3.12, FastAPI, aiogram 3 |
| Database | PostgreSQL 17, async SQLAlchemy 2, Alembic |
| Runtime coordination | Redis 7 |
| Storage | private S3-compatible object storage |
| Frontend | Telegram Mini App, HTML/CSS/JavaScript |
| Observability | Prometheus, optional OpenTelemetry |
| Delivery | Docker, GitHub Actions, exact-SHA production deploy |
| Testing | pytest + focused contract/regression suites |

## Local development

```bash
cp .env.example .env
docker compose up --build
```

Core verification:

```bash
alembic upgrade head
ruff check .
python -m compileall -q app tests
pytest -q
```

## Documentation

The root README is intentionally a portfolio-level overview. Detailed engineering and operational documentation lives in `docs/`:

- [`docs/README.md`](docs/README.md)
- [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)
- [`docs/OPERATIONS_RUNBOOK.md`](docs/OPERATIONS_RUNBOOK.md)
- [`docs/GENERATION_MINI_APP.md`](docs/GENERATION_MINI_APP.md)
- [`docs/ADMIN_SECURITY.md`](docs/ADMIN_SECURITY.md)
- [`docs/ADMIN_RUNBOOK.md`](docs/ADMIN_RUNBOOK.md)
- [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md)
- [`docs/DATABASE_BACKUPS.md`](docs/DATABASE_BACKUPS.md)
- [`docs/GITHUB_PRODUCTION_DEPLOY.md`](docs/GITHUB_PRODUCTION_DEPLOY.md)

## Portfolio note

The interesting part of ROXY is not a single model integration. The project demonstrates how to turn unreliable external AI APIs into a production product with durable jobs, accounting, media ownership, security controls, operational visibility, backups and repeatable releases.
