# Wallet and payment checkout

**Status:** synchronized with current runtime on 2026-08-20.

Wallet is a presentation layer over the durable payment lifecycle. It does not calculate package prices, create arbitrary amounts, verify settlement itself or persist payment success locally.

## User flow

```text
Wallet
  |
  +--> GET /api/v1/payments/card/packages
  |
  +--> choose configured package/currency
  |
  +--> POST checkout with Idempotency-Key
  |
  +--> render current-payment card
  |       |
  |       +--> explicit user click: Open payment
  |
  +--> payment status polling / provider reconciliation
  |
  +--> succeeded
          |
          +--> refresh /api/v1/me
          +--> refresh /api/v1/me/transactions
```

The client never invents settlement state or credits the balance optimistically.

The active customer checkout is the hosted `card` route backed by Lava Top. Other
payment providers remain reserve integrations and are not part of the current
Mini App purchase path until they are explicitly enabled again.

## Server recovery after reload

Wallet does not write current financial state to `localStorage` or `sessionStorage`.

On activation/reopen it requests recent server payments and resumes the newest recoverable non-terminal payment. Typical states include:

```text
creating
creation_unknown
pending
```

That server record becomes the current payment card and polling resumes. A full Mini App reload therefore recovers from durable server state rather than stale browser state.

## Idempotency

One checkout intent is bound to the requested provider/package/currency plus its UUID `Idempotency-Key` where that payment surface requires one.

Client protections include:

- no concurrent double-tap checkout POSTs;
- transient retries of the same local intent reuse the same idempotency key;
- changing the requested purchase invalidates the old client intent;
- terminal state clears the in-memory checkout intent;
- `409` is treated as an idempotency conflict, not proof of payment.

Server `PaymentRequest` remains the durable idempotency boundary.

## Provider uncertainty

An upstream create error can be ambiguous: the provider may have accepted the request even though ROXY did not receive a usable response.

The safe rule is:

```text
unknown external side effect != retry create blindly
```

ROXY persists `creation_unknown` / `PaymentRequest=unknown` and lets provider-specific reconciliation recover or review the original intent.

For the hosted `card` checkout, a later verified webhook carrying an unknown `contractId` triggers an authoritative `GET /api/v1/invoices/{id}` lookup. ROXY binds that contract only when provider id + amount + currency + buyer email identify **exactly one** unresolved local intent. Zero or multiple candidates remain unbound. Arbitrary custom `clientUtm` fields are not treated as a guaranteed merchant-correlation channel.

See `PRIMARY_CARD_CHECKOUT.md` for the full contract.

## Rate limiting

Payment creation is protected by Redis payment-creation limits. On `429`, the Mini App reads `Retry-After`, disables checkout for that interval and shows an explicit retry state.

The client must not implement rapid automatic POST retries. Polling GETs are presentation refreshes, not payment creation.

## CryptoBot / Crypto Pay

CryptoBot is a first-class wallet payment method rather than a client-side redirect hack.
It reuses the same server-owned ROX package catalog and top-up bonus rules as card checkout.
The user chooses a package, ROXY creates a `currency_type=fiat`, `fiat=RUB` Crypto Pay
invoice, and CryptoBot lets the user settle it with any asset enabled for the app.

```text
Wallet -> CryptoBot
  -> POST /api/v1/payments/crypto/checkout
  -> Crypto Pay createInvoice(payload=<local payment UUID>)
  -> open mini_app_invoice_url / bot_invoice_url
  -> invoice_paid webhook
  -> HMAC-SHA256 verification over the raw request body
  -> amount + fiat + invoice id verification
  -> idempotent wallet credit
```

`createInvoice` has no provider-side idempotency key. ROXY therefore commits the local
`Payment` + `PaymentRequest` before the external call. If the create response is lost,
the durable payment enters `creation_unknown`; reconciliation searches Crypto Pay invoices
by the local UUID stored in `payload` instead of blindly creating another invoice.

Configuration is server-only:

```text
CRYPTOPAY_API_TOKEN=<Crypto Pay app token>
CRYPTOPAY_BASE_URL=https://pay.crypt.bot
```

The webhook must be enabled for the Crypto Pay app in @CryptoBot and point to:

```text
<PUBLIC_BASE_URL>/webhooks/payments/cryptobot
```

No Crypto Pay token, signature key, or settlement decision is exposed to the Mini App.
The UI only shows CryptoBot when the server reports the provider as configured.

## Provider navigation

Telegram Mini App link APIs are used when available:

```text
openTelegramLink(url)   t.me / telegram.me links
openLink(url)           normal provider HTTPS links
```

KSU/ROXY enforces payment navigation through `payment-link-guard.js`:

- only HTTPS payment URLs are accepted;
- `openLink` / `openTelegramLink` are allowed only during direct click/keyboard activation;
- automatic opening after an asynchronous checkout request is blocked;
- the server current-payment card exposes an explicit **Open payment** action;
- returning to or reopening ROXY keeps the server payment state rather than browser financial state.

Outside Telegram the fallback remains a secure new browser tab/window with `noopener,noreferrer`.

## Payment states

Presentation labels map to server state only:

```text
creating              Создаём
creation_unknown      Проверяем
pending               Ожидает оплаты
succeeded             Оплачено
partially_refunded    Частичный возврат
refunded              Возвращено
refund_review         Проверка возврата
canceled              Отменено
expired               Истекло
failed                Ошибка
```

The Mini App never transitions these states itself.

## Balance refresh

When polling first observes `succeeded`, Wallet:

1. emits Telegram success haptic where supported;
2. fetches `/api/v1/me`;
3. fetches `/api/v1/me/transactions`;
4. updates the persistent header balance and Wallet balance/ledger.

Purchased ROX are never added optimistically.

## Recent payments

The recent-payment API is owner-scoped and newest-first. Wallet shows recent provider/package/amount/status rows beneath the active payment.

This bounded history is not a second accounting ledger. Wallet transactions remain authoritative for ROX movement.

## Empty/error states

Wallet distinguishes:

- payment packages not configured;
- no signed Telegram init data;
- provider create uncertainty under reconciliation;
- ambiguous hosted-card recovery requiring another webhook/reconciliation/operator review rather than an unsafe bind;
- rate-limited checkout with explicit retry interval;
- ordinary refresh failure, where last rendered server state is retained rather than fabricated.

## Security boundaries

- raw signed `Telegram.WebApp.initData` is the user authentication material;
- provider secrets never reach the Mini App;
- package amount/ROX are server-owned;
- payment ownership is checked on user routes;
- `Idempotency-Key` is not proof of settlement;
- webhook payload is not trusted as wallet-credit authority;
- provider status APIs + reconciliation are settlement truth;
- ambiguous payment correlation fails closed;
- browser storage is not financial truth;
- payment navigation accepts HTTPS only and requires direct activation in Telegram.

## Maintained implementation surfaces

```text
app/api/v1/payments.py
app/api/v1/card_payments.py
app/api/card_webhooks.py
app/services/card_payments.py
app/services/card_payment_recovery.py
app/providers/card_checkout.py
app/web/mini_app/payment-link-guard.js
app/web/mini_app/wallet.js
app/web/mini_app/primary-card-checkout.js
tests/test_wallet_checkout.py
tests/test_payment_link_guard.py
tests/test_primary_card_checkout.py
tests/test_card_payment_recovery.py
```

The partner cabinet/withdrawal product is already shipped and documented separately; it is not a future Wallet epic. Wallet remains the user entrypoint for balance, top-up, payment state and ledger.
