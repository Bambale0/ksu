# KSU bot

Production-oriented backend baseline for a Telegram content product.

## Stack

- Python 3.12
- FastAPI (HTTP API + Telegram/provider webhooks)
- aiogram 3 (Telegram bot + Redis FSM)
- PostgreSQL + async SQLAlchemy 2
- Redis (FSM + generation queue)
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
- Kie.ai generation provider + Redis generation worker
- Kie callback HMAC verification and provider status reconciliation
- CryptoBot / Crypto Pay payments with signed webhooks
- T-Bank Internet Acquiring `/v2/Init` payments with Token verification
- YooKassa payments with Idempotence-Key and authoritative webhook recheck
- server-side ROX package catalog: the client never supplies payment amount or ROX reward
- support tickets/messages
- notifications and partner withdrawal data models
- health/readiness probes

## Local start

```bash
cp .env.example .env
docker compose up --build
```

API: `http://localhost:8000`

- `GET /health/live`
- `GET /health/ready`
- `POST /webhooks/telegram`
- `POST /webhooks/kie`
- `POST /webhooks/payments/cryptobot`
- `POST /webhooks/payments/tbank`
- `POST /webhooks/payments/yookassa`
- `GET /api/v1/payments/packages`
- `POST /api/v1/payments`
- `/docs` in non-production environments

## Kie.ai

Configure the API key and one server-controlled Kie model for every enabled product flow:

```dotenv
PUBLIC_BASE_URL=https://api.example.com
KIE_API_KEY=...
KIE_WEBHOOK_HMAC_KEY=...
KIE_TEXT_TO_IMAGE_MODEL=...
KIE_IMAGE_TO_IMAGE_MODEL=...
KIE_TEXT_TO_VIDEO_MODEL=...
KIE_IMAGE_TO_VIDEO_MODEL=...
```

Generation requests are persisted and charged first, then pushed to Redis. The `generation-worker` service consumes the queue and submits tasks to Kie `/api/v1/jobs/createTask`. Kie callbacks are verified and reconciled through `/api/v1/jobs/recordInfo`. Failed provider jobs receive an idempotent ROX refund.

The model is not accepted from the client. This prevents a user from selecting an unexpectedly expensive Kie model while paying the ROX price of a cheaper generation kind. Model choice remains server configuration until a model-aware pricing catalog is added.

## ROX packages

Prices are server-side configuration. `POST /api/v1/payments` accepts only a `package_id` and provider, never an amount supplied by the browser or Telegram client.

Configure packages as JSON:

```dotenv
ROX_PACKAGES_JSON={"starter":{"amount":"299.00","currency":"RUB","rox":"350"}}
```

The values above are only a configuration example; set the real product prices before deployment.

## CryptoBot / Crypto Pay

```dotenv
CRYPTOPAY_API_TOKEN=...
CRYPTOPAY_BASE_URL=https://pay.crypt.bot
```

Set the Crypto Pay webhook URL in the CryptoBot app settings to:

```text
https://api.example.com/webhooks/payments/cryptobot
```

The backend validates `crypto-pay-api-signature` against the raw request body before crediting ROX.

## T-Bank

```dotenv
TBANK_TERMINAL_KEY=...
TBANK_PASSWORD=...
TBANK_BASE_URL=https://securepay.tinkoff.ru
PAYMENT_RETURN_URL=https://example.com/payment-result
```

The backend uses `/v2/Init`, sends `NotificationURL`, validates the SHA-256 `Token` on notifications, verifies local order/payment/amount values and returns the required plain-text `OK` response.

## YooKassa

```dotenv
YOOKASSA_SHOP_ID=...
YOOKASSA_SECRET_KEY=...
YOOKASSA_BASE_URL=https://api.yookassa.ru
PAYMENT_RETURN_URL=https://example.com/payment-result
```

Configure `payment.succeeded` notifications to:

```text
https://api.example.com/webhooks/payments/yookassa
```

Creating a payment uses the local payment UUID as `Idempotence-Key` and metadata. Incoming notifications are not trusted by themselves: the backend requests the payment from YooKassa again and only credits ROX after the authoritative status, metadata, amount and currency match.

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

CI runs validation on every pull request and on pushes to `main`, with real PostgreSQL and Redis service containers.

## Telegram webhook

When `BOT_TOKEN` and `TELEGRAM_WEBHOOK_URL` are configured, application startup registers:

`{TELEGRAM_WEBHOOK_URL}/webhooks/telegram`

If `TELEGRAM_WEBHOOK_SECRET` is set, incoming Telegram webhook requests must contain the matching `X-Telegram-Bot-Api-Secret-Token` header.
