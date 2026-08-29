# Primary hosted card checkout

**Status:** synchronized with current runtime/provider contract on 2026-08-20.

The user-facing payment method is always named:

```text
Оплата картой · USD / EUR / RUB / СБП
```

Do not expose the upstream payment platform brand in bot messages, Mini App labels, public payment API responses, payment history labels or public webhook paths.

## Public contract

Provider code stored locally and exposed by our API:

```text
card
```

The current upstream implementation is Lava Top (`CARD_API_BASE_URL=https://gate.lava.top`).
This is an internal provider route: the Mini App and public API copy keep using
the neutral card checkout name.

Endpoints:

```text
GET  /api/v1/payments/card/packages
POST /api/v1/payments/card/checkout
GET  /api/v1/payments/card/{payment_id}
POST /api/v1/payments/card/{payment_id}/reconcile
POST /webhooks/payments/card
```

Checkout requires a UUID `Idempotency-Key`, package id, explicit currency and billing email. The email is used for the hosted payment flow and is not inferred from Telegram identity.
ROXY accepts RFC-style ASCII checkout emails before forwarding them to Lava Top, including common local-part characters such as `+`, `-`, `_`, `.`, and `%`. The local validator rejects spaces, non-ASCII characters, emoji, malformed domains, leading/trailing dots, and repeated dots in the local part.

## Pricing

Foreign exchange is never invented by KSU. Each package can have explicit RUB, USD and EUR prices:

```text
CARD_PACKAGES_JSON={"starter":{"credits":"300","prices":{"RUB":"300","USD":"6.00","EUR":"5.70"}}}
```

The current official custom-price limits are validated by KSU before a local payment intent is committed:

```text
RUB  50 .. 1_000_000
USD   5 ..    10_000
EUR   5 ..    10_000
```

`amount` is transmitted to the provider **only for price-on-request offers**. The current Lava Top
contract rejects an explicit amount for fixed-price offers (`HTTP 400 "is not dynamic price"`), which
previously failed every card checkout with `502` upstream when every package was treated as dynamic.
Mark a package with `"dynamic_amount": true` only when its offer really supports custom prices:

```text
CARD_PACKAGES_JSON={"offers": {...}}                    # fixed-price offers, no amount is sent
CARD_PACKAGES_JSON={"my-dyn": {"credits":"300","prices":{"RUB":"300"},"dynamic_amount":true}}
```

When a package does not pin an `offer_id` and resolution picks a single dynamic offer from the
provider catalog, `amount` is still sent automatically.

When `CARD_PACKAGES_JSON` is empty, legacy `ROX_PACKAGES_JSON` is exposed to this checkout only as RUB pricing. USD/EUR are unavailable until explicitly configured.

Referral rewards on USD/EUR purchases use the purchased ROX accounting value as the RUB reward basis (`1 ROX = 1 RUB`) rather than pretending that the foreign-currency numeric payment amount is RUB.

## Payment methods and provider routing

The public product does not ask users to choose an upstream technical provider. By default the provider route is omitted and the hosted checkout may expose every payment method enabled for the merchant and selected currency.

Optional route pinning is configured with:

```text
CARD_PAYMENT_ROUTE_BY_CURRENCY_JSON={"RUB":"BANK131","USD":"UNLIMINT","EUR":"PAYPAL"}
```

Leave `CARD_PAYMENT_ROUTE_BY_CURRENCY_JSON={}` in the normal production setup unless there is a deliberate reason to restrict a currency to one route. Routes remain internal implementation details and must not become customer-facing provider names.

## Current provider API routes

ROXY follows the current callable provider API contract, not historical SDK examples:

```text
POST /api/v3/invoice          create invoice
GET  /api/v1/invoices/{id}    authoritative single-contract lookup
```

The authoritative lookup route is used for webhook reconciliation, refund inspection and recovery of a lost create response.

`clientUtm` is **not** used as a ROXY merchant correlation channel. The current public schema defines it as ordinary UTM attribution data and webhook examples do not promise it will be returned. Do not add arbitrary `payment_id`/`order_id` keys there unless the provider publishes and tests a dedicated merchant-correlation contract.

## Invoice lifecycle

The local `Payment` and `PaymentRequest` are committed before the remote create call, after currency, email, package and provider amount limits pass validation.
If Lava Top still rejects the buyer email with `Incorrect email to purchase`, ROXY marks the local attempt as `failed` and returns a user-correctable `422` instead of a provider `502`.

Normal lifecycle:

```text
local creating intent committed
  ↓
POST /api/v3/invoice
  ↓
provider contract id + HTTPS payment URL
  ↓
local external_id stored, status=pending
```

A transport/response ambiguity after the provider may have created the contract becomes:

```text
Payment.status = creation_unknown
PaymentRequest.status = unknown
```

ROXY deliberately does **not** issue a second invoice during reconciliation because a second remote create could produce a duplicate payable contract.

Successful create stores the external invoice id and HTTPS payment URL. Mini App requires two direct user actions:

1. `Создать оплату` creates the server-side intent;
2. `Открыть оплату` opens the returned HTTPS URL.

This preserves the direct-user-activation payment link guard.

## Lost create-response recovery

If a verified provider webhook arrives with a `contractId` that is not yet known locally, ROXY may recover the missing `external_id` without creating a second invoice.

Recovery is fail-closed:

1. fetch `GET /api/v1/invoices/{contractId}`;
2. require authoritative contract id, amount, currency and buyer email;
3. find local `card` intents with no `external_id`, recoverable status, exact amount and exact currency;
4. normalize and compare the stored checkout billing email with the authoritative buyer email;
5. bind only when **exactly one** unresolved local intent matches;
6. acquire a row lock and re-check the same identity before writing;
7. set `external_id`, move the payment to `pending`, and mark its `PaymentRequest` completed;
8. continue through the ordinary authoritative reconciliation path.

Recovery never guesses:

- zero candidates → no bind;
- two or more candidates → ambiguous, no bind;
- missing provider identity fields → no bind;
- mismatched amount/currency/email → no bind;
- provider lookup failure → no bind.

Ambiguous/provider-error webhook recovery returns non-success so provider delivery can be retried after state changes. ROX are never credited from webhook body data alone.

## Webhook security and reconciliation

The public webhook URL is neutral:

```text
/webhooks/payments/card
```

Configure the same inbound secret in the provider webhook settings and `CARD_WEBHOOK_KEY`. Webhook authentication uses `X-Api-Key` and constant-time comparison.

One-time payment events handled:

```text
payment.success
payment.failed
```

The webhook is a signal, not settlement truth. Before wallet mutation ROXY fetches the authoritative invoice and validates provider contract identity, amount and currency. Wallet credit is idempotent.

Duplicate webhook deliveries are expected and safe. Background payment reconciliation routes known `provider=card` payments through the same authoritative invoice lookup so a lost webhook does not strand a paid invoice.

## Refunds

Provider refund state is detected through authoritative invoice reconciliation.

If the invoice exposes cumulative refunded amount, ROXY computes only the unseen delta and reuses the existing payment reversal ledger, including proportional ROX and referral-reward reversal.

If the remote invoice says refunded but no authoritative refund amount is available, ROXY uses `refund_review` instead of guessing how many ROX to debit.

Merchant-initiated refunds for this provider remain intentionally unexposed until an exact current refund endpoint/contract is verified. Existing T-Bank and YooKassa refund implementations remain unchanged.

## Release invariants

A card checkout release must preserve all of these:

- local intent exists before remote create side effect;
- create response ambiguity never triggers blind duplicate create;
- authoritative lookup uses the current single-contract route;
- webhook body alone never credits ROX;
- unknown-contract recovery binds only one exact amount/currency/email match;
- ambiguous recovery performs no bind and no wallet mutation;
- duplicate success credits the wallet exactly once;
- direct user activation remains required before opening the hosted payment URL.
