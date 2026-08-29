# Wallet and payment checkout

**Status:** synchronized with current runtime on 2026-08-29.

Wallet is a presentation layer over the durable payment lifecycle. It does not calculate package prices, create arbitrary amounts, verify settlement itself or persist payment success locally.

## User flow

```text
Wallet
  |
  +--> GET /api/v1/payments/card/packages or /crypto/packages
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

The primary card checkout is backed by Lava Top. Cryptocurrency checkout is backed by
2328.io and uses the same server-owned ROX packages and top-up bonus rules.

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

For 2328.io, the local `Payment.id` is also sent unchanged as upstream `order_id`.
2328.io scopes `order_id` to the merchant project and treats it as the create-payment
idempotency key, so an ambiguous create can be queried or retried without creating a
second invoice.

## Provider uncertainty

An upstream create error can be ambiguous: the provider may have accepted the request even though ROXY did not receive a usable response.

The safe rule is:

```text
unknown external side effect != create a new order
```

ROXY persists `creation_unknown` / `PaymentRequest=unknown` and lets provider-specific reconciliation recover the original intent.

For 2328.io reconciliation, ROXY queries `/v1/payment/info` by the provider UUID when
known, otherwise by the immutable local `order_id`. A recovered provider object is bound
only when `order_id`, payment UUID, amount and currency agree with the local payment.

For the hosted `card` checkout, a later verified webhook carrying an unknown `contractId` triggers an authoritative `GET /api/v1/invoices/{id}` lookup. ROXY binds that contract only when provider id + amount + currency + buyer email identify **exactly one** unresolved local intent. Zero or multiple candidates remain unbound. Arbitrary custom `clientUtm` fields are not treated as a guaranteed merchant-correlation channel.

See `PRIMARY_CARD_CHECKOUT.md` for the full card contract.

## Rate limiting

Payment creation is protected by Redis payment-creation limits. On `429`, the Mini App reads `Retry-After`, disables checkout for that interval and shows an explicit retry state.

The client must not implement rapid automatic POST retries. Polling GETs are presentation refreshes, not payment creation.

## 2328.io cryptocurrency payments

The public Mini App route remains provider-neutral:

```text
Wallet -> Криптовалюта
  -> POST /api/v1/payments/crypto/checkout
  -> POST https://api.2328.io/api/v1/payment
       amount=<RUB package price>
       currency=RUB
       order_id=<local Payment UUID>
       url_callback=<PUBLIC_BASE_URL>/webhooks/payments/2328
  -> open result.url hosted checkout
  -> signed payment status webhook
  -> verify HMAC-SHA256 before any state mutation
  -> verify order_id + uuid + amount + currency
  -> paid / overpaid -> idempotent wallet credit
```

2328.io request signing is HMAC-SHA256 over Base64 of compact UTF-8 JSON. Every outgoing
request sends the project UUID in the `project` header and the hexadecimal signature in
`sign`. Incoming webhook signatures are carried in the JSON `sign` field; ROXY removes
that field, serializes the remaining object as compact UTF-8 JSON, Base64-encodes it and
compares the HMAC in constant time.

Settlement policy:

```text
pending / check / awaiting_confirmation / underpaid_check -> pending, no credit
paid / overpaid                                      -> succeeded, credit once
cancel                                               -> expired, no credit
underpaid / aml_lock                                 -> failed, no credit
```

Redirects, client polling and transaction hashes are never treated as proof of payment.
Webhook delivery is the fast path; periodic `/v1/payment/info` reconciliation is the
recovery path for a lost webhook.

Configuration is server-only:

```text
PAYMENT_2328_PROJECT_UUID=<project UUID from 2328.io>
PAYMENT_2328_API_KEY=<API key from 2328.io>
PAYMENT_2328_BASE_URL=https://api.2328.io/api
PUBLIC_BASE_URL=https://your-production-origin.example
```

The callback URL sent with every invoice is:

```text
<PUBLIC_BASE_URL>/webhooks/payments/2328
```

No 2328.io API key or settlement decision is exposed to the Mini App. The crypto option
is shown only when project UUID, API key and a public callback origin are all configured.
The low-level client also refuses to create an invoice without `url_callback`.

## CryptoBot cutover

CryptoBot is no longer available for creating new payments. The public cryptocurrency
checkout and the generic payment-create contract both create only `provider=2328`.

Existing non-terminal `provider=cryptobot` rows are intentionally retained as a temporary
read/reconcile-only compatibility path:

```text
existing CryptoBot invoice
  -> remains visible in payment history
  -> may reopen its already-created payment_url
  -> POST /api/v1/payments/crypto/<id>/reconcile
  -> legacy provider status lookup only
  -> existing idempotent wallet settlement
```

This prevents a user from losing an invoice opened immediately before the cutover while
ensuring no new CryptoBot invoice can be created. Keep the legacy CryptoPay token only
until all old non-terminal invoices are terminal. After that drain period, the legacy
CryptoBot provider/service/configuration can be removed in a separate cleanup.

## Provider navigation

Telegram Mini App link APIs are used when available:

```text
openTelegramLink(url)   t.me / telegram.me links
openLink(url)           normal provider HTTPS links
```

2328.io hosted checkout uses a normal HTTPS URL, so Telegram opens it through the guarded
`openLink` path. Outside Telegram the fallback remains a secure new browser tab/window
with `noopener,noreferrer`.

KSU/ROXY enforces payment navigation through `payment-link-guard.js`:

- only HTTPS payment URLs are accepted;
- link opening is allowed only during direct click/keyboard activation;
- automatic opening after an asynchronous checkout request is blocked where the guard is active;
- the server current-payment card exposes an explicit **Open payment** action;
- returning to or reopening ROXY keeps the server payment state rather than browser financial state.

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
failed                 Ошибка
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
- `Idempotency-Key` and redirects are not proof of settlement;
- 2328.io webhooks are HMAC-verified before any state mutation;
- success is deduplicated by the existing wallet-credit idempotency key;
- provider status APIs + reconciliation recover missed webhooks;
- ambiguous payment correlation fails closed;
- browser storage is not financial truth;
- payment navigation accepts HTTPS only and requires direct activation in Telegram.

## Maintained implementation surfaces

```text
app/api/v1/payments.py
app/api/payment_2328_webhooks.py
app/services/payment_2328.py
app/providers/payment_2328.py
app/core/config.py
app/services/payment_reconciliation.py
app/api/v1/card_payments.py
app/api/card_webhooks.py
app/services/card_payments.py
app/services/card_payment_recovery.py
app/providers/card_checkout.py
frontend/mini-app/app/payments/page.tsx
frontend/mini-app/components/wallet-parity.tsx
tests/test_2328_checkout.py
tests/test_2328_settlement.py
tests/test_wallet_checkout.py
```

The partner cabinet/withdrawal product is documented separately. Wallet remains the user entrypoint for balance, top-up, payment state and ledger.
