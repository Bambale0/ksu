# Partner ROX transfers

## Product contract

A user can sponsor a creator from their own referral first line by transferring ROX from the sender's normal ROX wallet to the recipient's normal ROX wallet.

This is intentionally different from the existing partner `wallet-transfers` flow, which converts withdrawable partner RUB earnings into the same user's ROX.

## Customer flow

1. Open **Партнёрам → Кабинет автора**.
2. In **Перевести ROX**, select a user from the first referral line.
3. Enter a whole-number ROX amount, for example `5500`.
4. Confirm the irreversible transfer.
5. The sender sees the new available ROX balance; the recipient can spend the credited ROX on normal generations immediately.

Only direct first-line referrals are eligible. The client sends the recipient's internal user UUID; the backend independently verifies the referral relationship.

## API

`POST /api/v1/referrals/rox-transfers`

```json
{
  "recipient_user_id": "<uuid>",
  "amount_rox": 5500,
  "idempotency_key": "<unique intent key>"
}
```

Success (`201`):

```json
{
  "id": "<transfer uuid>",
  "recipient_user_id": "<uuid>",
  "amount_rox": "5500",
  "balance_rox": "1500.00"
}
```

## Accounting and safety invariants

- Transfer amount is a positive integer ROX value.
- Sender cannot transfer to themselves.
- Recipient must be an active direct first-line referral of the sender.
- Sender wallet uses the normal non-negative `WalletService.debit` path.
- Recipient uses the normal `WalletService.credit` path.
- Debit and credit are committed in one database transaction.
- Both ledger entries share one deterministic transfer reference.
- A client retry with the same idempotency key and identical intent returns the existing debit/credit instead of transferring twice.
- Reusing the same idempotency key for a different amount or recipient is rejected as a conflict.
- The response never exposes the recipient's wallet balance.

Ledger kinds:

- sender: `partner_rox_transfer_out`
- recipient: `partner_rox_transfer_in`
- reference type: `partner_rox_transfer`

## Pricing

Receiving ROX does **not** copy the sponsor's billing privileges, admin-free mode, discounts, roles, or price overrides. Sponsored/partner pricing, if introduced, must be a separate explicit entitlement with its own audit and expiry rules.
