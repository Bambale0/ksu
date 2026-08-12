# Wallet and payment checkout

**Status:** Mini App payment UX contract introduced on 2026-08-12.

Wallet is a presentation layer over the existing durable payment lifecycle. It does not calculate package prices, create arbitrary amounts, verify settlement itself or persist payment success locally.

## User flow

```text
Wallet
  |
  +--> GET /api/v1/payments/packages
  |       |
  |       +--> choose server package
  |
  +--> choose provider
  |       cryptobot | tbank | yookassa
  |
  +--> POST /api/v1/payments
  |       Idempotency-Key: UUID
  |       {provider, package_id}
  |
  +--> open provider payment_url
  |
  +--> GET /api/v1/payments/{id} polling
  |
  +--> succeeded
          |
          +--> refresh /api/v1/me
          +--> refresh /api/v1/me/transactions
```

The client never sends RUB amount or credit amount when creating a payment.

## Server recovery after reload

Wallet does not write current payment state to `localStorage` or `sessionStorage`.

On every Wallet activation/reopen it requests:

```text
GET /api/v1/payments?limit=12
```

and selects the newest payment whose status is one of:

```text
creating
creation_unknown
pending
```

That server record becomes the current payment card and polling resumes. This makes a full Mini App reload/reopen recoverable without trusting stale browser state.

## Idempotency

One checkout intent is one tuple:

```text
package_id + provider + UUID Idempotency-Key
```

The UUID is generated when the user starts that checkout and reused for transient retries of the same tuple.

Client protections:

- `checkoutBusy` prevents double-tap concurrent POSTs;
- changing package/provider invalidates the in-memory intent and creates a new UUID only on the next deliberate checkout;
- network errors keep the same UUID;
- `409` means the key conflicts with a different intent and is discarded before the next user retry;
- terminal payment states clear the intent.

Server `PaymentRequest` remains the authoritative idempotency boundary.

## Provider uncertainty

If `POST /api/v1/payments` returns upstream `502`, external creation may be uncertain. Wallet does **not** create another invoice.

It immediately reloads:

```text
GET /api/v1/payments?limit=12
```

and lets `payment-worker` reconciliation resolve `creation_unknown` / provider state.

## Rate limiting

Payment creation is protected by the existing Redis payment-creation limit. On `429`, Wallet reads `Retry-After`, disables checkout for that interval and shows a retry message.

The client must not implement rapid automatic POST retries. Polling GETs are separate presentation refreshes.

## Provider navigation

Current Telegram Mini Apps APIs are used when available:

```text
openTelegramLink(url)   t.me / telegram.me links
openLink(url)           normal provider HTTPS links
```

Outside Telegram the fallback is a secure new browser tab/window with `noopener,noreferrer`.

A payment URL is also retained on the server Payment payload and exposed back to the owning user, so the current-payment card can offer **Open payment** again after returning to KSU.

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

The UI does not add purchased credits optimistically.

## Recent payments

`GET /api/v1/payments` is owner-scoped and newest-first. Wallet shows recent provider/package/amount/status rows beneath the active payment.

This endpoint is intentionally a simple bounded recent-history API rather than a second accounting ledger. Wallet transactions remain the authoritative credit movement history.

## Empty/error states

Wallet distinguishes:

- package catalog empty: payment packages are not configured;
- no Telegram signed init data: checkout unavailable in ordinary browser preview;
- payment provider upstream uncertainty: existing intent is being reconciled;
- rate-limited checkout: explicit retry interval;
- ordinary network refresh failure: keep last rendered server state rather than fabricate a new state.

## Files

```text
app/api/v1/payments.py             user recent-payment API + existing checkout/status routes
app/web/mini_app/index.html        Wallet checkout/status/history surfaces
app/web/mini_app/wallet.js         server-driven checkout/recovery/polling controller
app/web/mini_app/wallet.css        Telegram-first Wallet payment presentation
tests/test_wallet_checkout.py      backend ownership + client contract tests
```

## Security boundaries

- raw signed `Telegram.WebApp.initData` is the user authentication material;
- provider secrets never reach the Mini App;
- package amount/credits are server-owned;
- payment ownership is checked on history/detail routes;
- `Idempotency-Key` is not proof of payment and never causes local crediting;
- provider webhooks/status APIs and the payment worker remain settlement truth;
- wallet/payment records are not persisted as browser financial truth.

## Follow-up

The next user-product epic after Wallet checkout is the full partner cabinet/withdrawal workflow inside Profile. Wallet should remain the single user entrypoint for balance, top-up, payment state and ledger rather than spawning separate floating payment screens.

Official Telegram Mini Apps reference used for link-opening behavior: `https://core.telegram.org/bots/webapps`.
