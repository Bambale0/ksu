# KSU bot

Production-oriented backend for a Telegram AI content product.

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
- users/profiles and internal-credit wallets
- immutable wallet ledger with idempotency keys and row-level locking
- fixed internal exchange rate: **1 internal credit = 10 RUB**
- promo code redemption
- two-level referrals (30% / 5% configuration)
- Kie.ai generation provider + Redis generation worker
- schema-driven Kie model catalog for Nano Banana, Seedream, GPT Image, Wan, Seedance, Kling Motion and Grok
- flat image billing + per-second video billing calculated only on the server
- Kie callback HMAC verification and provider status reconciliation
- CryptoBot / Crypto Pay payments with signed webhooks
- T-Bank Internet Acquiring `/v2/Init` payments with Token verification
- YooKassa payments with Idempotence-Key and authoritative webhook recheck
- server-side internal-credit package catalog
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
- `GET /api/v1/generations/models`
- `POST /api/v1/generations/quote`
- `POST /api/v1/generations`
- `GET /api/v1/payments/packages`
- `POST /api/v1/payments`
- `/docs` in non-production environments

## Internal credits

The product's internal currency is separate from Kie provider credits.

```dotenv
INTERNAL_CREDIT_RUB=10
```

The backend treats this as a hard exchange rule:

```text
1 internal credit = 10 RUB
rubles = internal_credits × 10
```

Generation quotes return both internal-credit and RUB values. Existing database fields named `rox` remain as a compatibility/storage detail, while public API responses expose `credits` as the preferred field.

Kie `creditsConsumed` is provider-side usage information and is not automatically treated as the product's internal credit balance.

## Kie.ai model catalog

The API uses Kie Market's unified task API. A client selects the local `model_id`; the backend maps it to a server-controlled Kie model slug and forwards model-specific input parameters.

Enabled families include:

- Nano Banana: base, Edit, Pro, 2, 2 Lite
- Seedream: 3.0, 4.0, 4.5, 5.0 Lite, 5.0 Pro, including edit/image-to-image and layer decomposition where supported
- GPT Image: 1.5 and 2, text-to-image and image-to-image
- Wan 2.7: image, image Pro, text-to-video, image-to-video, first/last frame, video continuation, video edit and reference-to-video
- Seedance: 1.5 Pro, 2.0, 2.0 Fast, 2.0 Mini and 2.5 with multimodal references
- Kling Motion Control: 2.6 and 3.0
- Grok Imagine: text/image generation, text/image-to-video, Video 1.5 Preview, upscale and extend

Configure Kie:

```dotenv
PUBLIC_BASE_URL=https://api.example.com
KIE_API_KEY=...
KIE_WEBHOOK_HMAC_KEY=...
```

Generation requests are persisted and charged first, then pushed to Redis. The `generation-worker` consumes the queue and submits tasks to Kie `/api/v1/jobs/createTask`. Kie callbacks are verified and reconciled through `/api/v1/jobs/recordInfo`. Failed provider jobs receive an idempotent internal-credit refund.

### Catalog

```http
GET /api/v1/generations/models
```

Each model entry exposes capabilities, billing mode, unit price in internal credits, RUB equivalent, video duration limits and capability notes.

### Quote

```http
POST /api/v1/generations/quote
Content-Type: application/json

{
  "model_id": "wan-2.7-t2v",
  "prompt": "Cinematic city at night",
  "parameters": {
    "duration": 6,
    "resolution": "1080p",
    "ratio": "16:9"
  }
}
```

For image models the quote uses a flat server-side credit rate. For every video model:

```text
cost_credits = unit_price_credits_per_second × billing_seconds
cost_rub = cost_credits × 10
```

The actual generation endpoint runs the same calculation again before wallet debit. A browser, mini app, or Telegram client cannot submit its own cost.

For models whose provider request does not contain a usable output duration, pass `billing_seconds`. Grok Upscale can reuse the source duration automatically when the source Kie task belongs to this backend.

### Generation pricing

Default product prices live in the model catalog and can be overridden without code changes:

```dotenv
GENERATION_PRICING_JSON={"wan-2.7-t2v":{"per_second":"8.50"},"gpt-image-2-t2i":{"flat":"18"},"kling-motion-3.0":{"per_second":"15"}}
```

`per_second` values are **internal credits per second**. `flat` values are internal credits per image task. At the fixed exchange rate, `8.50` credits/sec equals `85 RUB/sec`.

## Internal-credit packages

`POST /api/v1/payments` accepts only `package_id` and provider. Package pricing is server-side.

Preferred configuration specifies credits and derives RUB automatically:

```dotenv
ROX_PACKAGES_JSON={"starter":{"credits":"30","currency":"RUB"}}
```

This produces a 300 RUB payment. Legacy `rox` remains accepted as an alias for `credits`.

You may specify both amount and credits, but they must satisfy the exchange rule exactly:

```dotenv
ROX_PACKAGES_JSON={"starter":{"amount":"300","credits":"30","currency":"RUB"}}
```

A configuration such as 299 RUB for 30 credits is rejected.

## CryptoBot / Crypto Pay

```dotenv
CRYPTOPAY_API_TOKEN=...
CRYPTOPAY_BASE_URL=https://pay.crypt.bot
```

Set the Crypto Pay webhook URL to:

```text
https://api.example.com/webhooks/payments/cryptobot
```

The backend validates `crypto-pay-api-signature` against the raw request body before crediting the wallet.

## T-Bank

```dotenv
TBANK_TERMINAL_KEY=...
TBANK_PASSWORD=...
TBANK_BASE_URL=https://securepay.tinkoff.ru
PAYMENT_RETURN_URL=https://example.com/payment-result
```

The backend uses `/v2/Init`, sends `NotificationURL`, validates the SHA-256 `Token`, verifies order/payment/amount values and returns the required plain-text `OK` response.

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

Creating a payment uses the local payment UUID as `Idempotence-Key` and metadata. Incoming notifications are rechecked against YooKassa before wallet credit.

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

CI runs validation on every pull request and push to `main`, with real PostgreSQL and Redis service containers.

## Telegram webhook

When `BOT_TOKEN` and `TELEGRAM_WEBHOOK_URL` are configured, startup registers:

`{TELEGRAM_WEBHOOK_URL}/webhooks/telegram`

If `TELEGRAM_WEBHOOK_SECRET` is set, incoming Telegram webhook requests must contain the matching `X-Telegram-Bot-Api-Secret-Token` header.
