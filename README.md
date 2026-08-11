# KSU bot

Production-oriented backend baseline for a Telegram content product.

## Stack

- Python 3.12
- FastAPI (HTTP API + Telegram webhook)
- aiogram 3 (Telegram bot + Redis FSM)
- PostgreSQL + async SQLAlchemy 2
- Redis (FSM, distributed locks, cache-ready infrastructure)
- Alembic migrations
- Docker Compose
- GitHub Actions CI with PostgreSQL and Redis service containers

## Implemented product foundations

- Telegram `/start`, `/balance`, `/profile`, `/support`
- Telegram WebApp `initData` authentication for REST endpoints
- users/profiles and ROX wallets
- immutable wallet ledger with idempotency keys and row-level locking
- promo code redemption
- two-level referrals (30% / 5% configuration)
- generation job records and Redis enqueueing
- support tickets/messages
- notifications, payments and partner withdrawal data models
- health/readiness probes

The actual AI provider and payment gateway adapters are deliberately left behind service boundaries because the provider/payment specification is not yet defined.

## Local start

```bash
cp .env.example .env
# set BOT_TOKEN and TELEGRAM_WEBHOOK_URL when Telegram webhook is needed
docker compose up --build
```

API: `http://localhost:8000`

- `GET /health/live`
- `GET /health/ready`
- `POST /webhooks/telegram`
- `/docs` in non-production environments

## Migrations

```bash
alembic upgrade head
```

## Tests and lint

```bash
python -m pip install -e '.[dev]'
ruff check .
mypy app
pytest -q
```

## Telegram webhook

When `BOT_TOKEN` and `TELEGRAM_WEBHOOK_URL` are configured, application startup registers:

`{TELEGRAM_WEBHOOK_URL}/webhooks/telegram`

If `TELEGRAM_WEBHOOK_SECRET` is set, incoming Telegram webhook requests must contain the matching `X-Telegram-Bot-Api-Secret-Token` header.
