# Primary hosted card checkout

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

Endpoints:

```text
GET  /api/v1/payments/card/packages
POST /api/v1/payments/card/checkout
GET  /api/v1/payments/card/{payment_id}
POST /api/v1/payments/card/{payment_id}/reconcile
POST /webhooks/payments/card
```

Checkout requires a UUID `Idempotency-Key`, package id, explicit currency and billing email. The email is used for the hosted payment flow and is not inferred from Telegram identity.

## Pricing

Foreign exchange is never invented by KSU. Each package can have explicit RUB, USD and EUR prices:

```text
CARD_PACKAGES_JSON={"starter":{"credits":"30","prices":{"RUB":"300","USD":"4.00","EUR":"3.70"}}}
```

When `CARD_PACKAGES_JSON` is empty, legacy `ROX_PACKAGES_JSON` is exposed to this checkout only as RUB pricing. USD/EUR are unavailable until explicitly configured.

Internal credits keep their configured RUB accounting value. Referral rewards on USD/EUR purchases therefore use `credits × INTERNAL_CREDIT_RUB` as the RUB reward basis rather than pretending that the foreign-currency numeric payment amount is RUB.

## Provider routing

The adapter implements every payment route documented by the official SDK:

```text
RUB     BANK131
USD     UNLIMINT | PAYPAL | STRIPE
EUR     UNLIMINT | PAYPAL | STRIPE
```

`STRIPE` is documented for products only.

Routes are internal implementation details and must not become customer-facing provider names. Optional pinning is configured with:

```text
CARD_PAYMENT_ROUTE_BY_CURRENCY_JSON={"RUB":"BANK131","USD":"UNLIMINT","EUR":"PAYPAL"}
```

If a currency has no pinned route, `paymentProvider` is omitted and the hosted checkout can use the methods enabled for the merchant account.

## Invoice lifecycle

The adapter creates a custom-price invoice with the provider's v3 invoice endpoint using:

```text
email
offerId
currency
amount
paymentProvider  # optional
```

The local `Payment` and `PaymentRequest` intent is committed before the remote create call. A network ambiguity after create becomes `creation_unknown`; reconciliation deliberately does not create another invoice because the create API has no merchant idempotency key in our verified contract.

Successful create stores the external invoice id and HTTPS payment URL. Mini App requires two direct user actions:

1. `Создать оплату` creates the server-side intent;
2. `Открыть оплату` opens the returned HTTPS URL.

This preserves the existing direct-user-activation payment link guard.

## Webhook security and reconciliation

The public webhook URL is neutral:

```text
/webhooks/payments/card
```

Configure the same inbound secret in the provider webhook settings and `CARD_WEBHOOK_KEY`. Current webhook authentication uses `X-Api-Key` and is constant-time compared.

One-time payment events handled:

```text
payment.success
payment.failed
```

The webhook is only a signal. Before wallet mutation KSU fetches the authoritative invoice and validates invoice id, amount and currency. Wallet credit is idempotent.

Background payment reconciliation also routes local `provider=card` payments through the same authoritative invoice lookup so a lost webhook does not strand a paid invoice.

## Refunds

The provider documentation states that refund webhooks are not sent. KSU therefore detects refund state during authoritative invoice reconciliation.

If the invoice exposes cumulative refunded amount, KSU computes only the unseen delta and reuses the existing payment reversal ledger, including proportional credit and referral-reward reversal.

If the remote invoice says refunded but no authoritative refund amount is available, KSU uses `refund_review` instead of guessing how many credits to debit.

Merchant-initiated refunds for this provider are intentionally not exposed until an exact official refund endpoint/contract is verified. Existing T-Bank and YooKassa refund implementations remain unchanged.
