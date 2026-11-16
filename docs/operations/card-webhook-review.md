# KSU Card webhook manual review (Lava Top)

Scope: [#622](https://github.com/Bambale0/ksu/issues/622), [#616](https://github.com/Bambale0/ksu/issues/616).

The verified `X-Api-Key` endpoint `/webhooks/payments/card` supports the existing
`payment.success` and `payment.failed` reconciliation. When separately
subscribed in the Lava Top dashboard, `refund.success` and
`chargeback.initiated` use a **different** `event_id` / `event_type` /
`data` envelope. The documented `data` object contains buyer and product
metadata but **no required invoice ID**. Never join these events to local
payments using email, amount, product or timestamp alone.

For these two event types KSU now acknowledges a valid authenticated
notification with 2xx **only after** its SHA-256 event UUID and event type
are durably recorded in `card_webhook_event_reviews` with
`status=manual_review`. Duplicate deliveries use `ON CONFLICT DO NOTHING`.
Neither raw event IDs nor customer emails, prices, payloads or provider
secrets are stored in that table. An invalid or missing event UUID returns
400; a database failure returns non-2xx and the provider may retry. Other
unknown event types continue to be acknowledged without financial effects.

No automatic refund, chargeback reversal or customer ROX mutation is
performed by the new handler. Published webhook payloads cannot authorize
these operations without a verified link to an authoritative provider invoice.
**Do not enable the new webhook event subscriptions until the merchant's
actual payload, auth, retry policy and operator review procedure are verified.**

## Operator report (read-only)

Run using the deployed image after migration:

```sh
docker compose exec -T app python -m scripts.audit_card_webhook_reviews
```

The report aggregates event counts by allowed type and review status only.
It does not reveal event IDs or customer information.

To process a pending event, a privileged operator must inspect the
authenticated Lava Top webhook history, capture source evidence in an
access-controlled case system, verify the exact provider invoice identity
and cumulative refund amounts, and independently approve any financial
adjustment. Do not post provider payloads, IDs or customer data to GitHub.

The event-audit schema upgrade is additive. A downgrade deliberately refuses
to drop the review table after it contains events, preventing accidental loss
of evidence. Code rollback can leave the harmless table in place.
