# Primary hosted card checkout

**Status:** synchronized with current runtime/provider contract on 2026-09-10.

YooKassa is the primary RUB checkout. The hosted card provider is exposed in
the Mini App only as a deliberately secondary fallback named:

```text
Lava Top · резерв
```

This is an intentional product-label exception. The provider code, API routes,
webhook route, storage values and public API `label` remain neutral and must not
be renamed from `card` / `Оплата картой` to a Lava-specific technical contract.
The Lava brand is allowed only in customer-facing Mini App copy that clearly
marks it as the reserve checkout.

## Public contract

Provider code stored locally and exposed by our API:

```text
card
```

The current upstream implementation is Lava Top (`CARD_API_BASE_URL=https://gate.lava.top`).
The implementation remains behind the neutral `card` API contract even though
the Mini App identifies the reserve option by brand for user clarity.

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

For a fixed-price offer, any prices returned by the catalog must include the requested currency
and exactly match the configured package price before ROXY creates a payable invoice. A mismatch
rejects checkout with `422`; operators must align the offer and published package through the
existing pricing controls. ROXY never rounds a provider price or accepts a small difference.
When catalog prices are unavailable, the returned invoice still undergoes the integrity check below.

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

The create response's `amountTotal.amount` / `amountTotal.currency` and the authoritative lookup's
`receipt.amount` / `receipt.currency` are both recognized by invoice validation. Any returned
identity, amount or currency must match the local intent. If a remote invoice was created with
different values, its id and original response remain stored, but the local attempt becomes
`failed` with integrity evidence and no exposed payment link. Replaying the checkout key does not
create another invoice or return the rejected link.
Malformed or non-finite returned amounts also retain the known remote identity with no payable
link; diagnostics store `invalid` rather than copying an arbitrary raw monetary value.
If the same response supplies multiple money representations, every supplied amount and currency
must agree with the intent; a matching `amountTotal` cannot hide a different `receipt` value.

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

A deterministic invoice identity, amount or currency mismatch records `invoice_integrity_error`
and the existing `reconciliation_terminal_error` on the payment, then removes the unresolved
attempt from automatic polling by marking it locally `failed`. The metadata includes the exact
expected/actual value and normalized authoritative status; local failure does not assert that the
provider rejected or refunded the payment. No wallet credit, reversal or expected-price rewrite is
performed. A verified webhook with a mismatch still receives a non-success response. Transient
lookup failures remain retryable. A concurrent completed/refunded payment is refreshed under its
row lock and cannot be overwritten by an older mismatched poll.

Operators should inspect these records through the existing admin payment detail before any
explicit recheck. Align prices for future checkouts first. A paid mismatched invoice requires
authoritative investigation; do not mark it paid or refund it with manual SQL. Diagnostics emit
`card_offer_price_mismatch` / `card_invoice_integrity_mismatch` without buyer emails, checkout
URLs, credentials or full provider payloads.

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
