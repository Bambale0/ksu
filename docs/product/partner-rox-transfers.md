# ROX transfers

## Product contract

A ROXY user can transfer ROX from their normal ROX wallet to any other active ROXY user.

This is intentionally different from the partner `wallet-transfers` flow, which converts withdrawable partner RUB earnings into the same user's ROX.

## Customer flow

1. Open **Партнёрам → Кабинет автора**.
2. In **Перевести ROX**, enter the recipient's numeric `ID` shown in their ROXY profile.
3. Enter a whole-number ROX amount, for example `5500`.
4. Confirm the irreversible transfer.
5. The sender sees the new available ROX balance; the recipient can spend the credited ROX on normal generations immediately.

The recipient does not need to be a referral. The backend resolves the entered Telegram user ID to an internal user and verifies that the account exists and is active. Self-transfers are rejected.

## API

`POST /api/v1/referrals/rox-transfers`

```json
{
  "recipient_telegram_id": 123456789,
  "amount_rox": 5500,
  "idempotency_key": "<unique intent key>"
}
```

Success (`201`) returns the transfer id, recipient internal id, recipient Telegram id, amount and sender's remaining balance. The response never exposes the recipient's wallet balance.

For rollout compatibility, the endpoint temporarily still accepts the old `recipient_user_id` UUID field, but the customer Mini App no longer uses or exposes internal UUIDs.

## Accounting and safety invariants

- Transfer amount is a positive integer ROX value.
- Sender cannot transfer to themselves.
- Recipient must exist in ROXY and be active.
- Missing and restricted recipients share the same generic unavailable response.
- Sender wallet uses the normal non-negative `WalletService.debit` path.
- Recipient uses the normal `WalletService.credit` path.
- Debit and credit are committed in one database transaction.
- Both ledger entries share one deterministic transfer reference.
- A client retry with the same idempotency key and identical intent returns the existing debit/credit instead of transferring twice.
- Reusing the same idempotency key for a different amount or recipient is rejected as a conflict.

Ledger kinds:

- sender: `partner_rox_transfer_out`
- recipient: `partner_rox_transfer_in`
- reference type: `partner_rox_transfer`

## Pricing

Receiving ROX does **not** copy the sender's billing privileges, admin-free mode, discounts, roles, or price overrides.
