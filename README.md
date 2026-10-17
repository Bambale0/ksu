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

### Public referral and share entry

New public referral, trend, post, profile and remix links use Telegram bot `?start=` links. After Start, a trend/post link previews that single public resource in the chat; its button opens the same resource in the Mini App. The original sharer payload is preserved, while referral attribution remains registration-only.

Public image cards use an existing lightweight JPEG preview when available. Public video cards use their existing poster as a photo, while the button opens the original video in the exact Mini App resource. Missing posters keep the original media-type fallback; audio remains audio. Preview selection never generates or downloads new media during /start. A rejected media request falls back to the same resource button; uncertain transport failures are not retried as another message.

Previously shared `?startapp=` links remain supported and still open the Mini App directly; already distributed Telegram URLs cannot be rewritten by this server change. Explicit Mini App/private repeat/task links retain their existing behavior. Private, removed or unavailable resources must not expose media through bot previews. Blurred posts show the resource button without unblurred media.

Receiving a private bot message, including `/start`, already re-enables eligible transactional notifications that were deferred because Telegram could not reach the chat. This change does not backfill historical notifications or perform refunds.

## Photo/video prompts: Nexus GPT primary, Neironych Qwen 3.8 fallback

The ROXY tools **Prompt по фото** (image_analysis) and **Prompt по видео**
(video_prompt) stay on Nexus GPT Vision (gpt-6-sol) as primary. The fallback
is exclusively Neironych Qwen 3.8 Max (model qwen3.8-max) via
POST https://api.xn--e1aikcel5c5a.online/v1/chat/completions.
The text-only prompt builder remains on its existing Nexus route.
This replaces the prior draft Grok 4.5 video-only fallback. Kie is never an
automatic fallback for these tools, but older already-recorded Kie jobs
remain supported.

Set PROMPT_TOOL_QWEN_FALLBACK_ENABLED=true and NEIRONYCH_API_KEY only after
review and a successful authorized image/video Qwen vision paid smoke.
The default is false; deploy does not silently turn on paid routing.
Fallback occurs only when Nexus explicitly returns 502/503/504 or its
prompt circuit is open; never on content rejection/other 4xx,
unexpected model output, or uncertain network timeouts.

For a photo prompt Qwen receives the same public HTTPS reference URL that
Nexus would use and the existing photo prompt schema. For a video prompt
the existing safe ROXY downloader verifies the source (30 MB maximum),
real duration is probed and four chronological JPEG frames are sent
as data:image/jpeg;base64 blocks using image_url in multimodal Chat
Completions. Direct raw-video input is not assumed. Frame analysis cannot
infer audio or every motion detail in unseen frames. Both tools retain the
same ROXY result shapes, customer prices and wallet idempotency.

The outbox atomically pins provider=neironych and model=qwen3.8-max before
any fallback POST, preserving the exact task ID after worker restarts and
rejecting stale claims. Each tool has a task-stable provider Idempotency-Key
and a 600-second media prompt lease (both photo/video) to avoid early
duplicate claims. The supplier is credited/charged independently of user
ROX; monitor real spend, errors, successes and task refunds.
Neironych HTTP 400/401/402/403/404/413/422 are permanent for this task:
no repeated paid supplier submissions, immediate task failure/refund.
429/5xx use the existing bounded outbox retry with the SAME provider and key.

After rollout monitor prompt_tool_qwen_fallback logs (without customer media),
Nexus and Neironych prompt circuit status, supplier spend, queue attempts,
progress/latency and customer ROX refunds.
Rollback: disable PROMPT_TOOL_QWEN_FALLBACK_ENABLED and restart prompt-tool
workers. Already-pinned Neironych tasks will keep their supplier for safe
idempotent completion; switching them manually back to Nexus is unsafe.
