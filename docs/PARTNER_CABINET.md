# Partner cabinet and withdrawal workflow

**Status:** user partner-cabinet contract introduced on 2026-08-12.

This feature implements the product FSM partner cabinet inside the existing Profile shell. Referral reward percentages remain server settings (30% first line / 5% second line by default); the browser never computes partner earnings or decides withdrawal eligibility.

## Cabinet data

Authenticated endpoints:

```text
GET  /api/v1/referrals/stats
GET  /api/v1/referrals/invitations?line=1|2&limit=&offset=
GET  /api/v1/referrals/rewards?status=&limit=&offset=
GET  /api/v1/referrals/withdrawals?limit=&offset=
POST /api/v1/referrals/withdrawals
POST /api/v1/referrals/withdrawals/{id}/cancel
```

The cabinet shows the product-spec fields:

- total earned partner income;
- available-to-withdraw balance;
- pending rewards;
- pending/processing withdrawal amount;
- first- and second-line counts;
- referral payload/link;
- invitations;
- accrual history;
- withdrawal request history.

## Withdrawal accounting

`PartnerWithdrawal` is a reservation against partner income, not a wallet debit.

Server calculation:

```text
net_earned = available/reversed rewards - reward reversals
reserved_or_paid = withdrawals with pending | processing | paid
available_to_withdraw = max(0, net_earned - reserved_or_paid)
```

Therefore:

- `pending` reserves the requested amount immediately;
- `processing` keeps it reserved;
- `paid` remains permanently consumed from available partner income;
- `rejected` and `canceled` are excluded from the reservation total and release the amount automatically.

Creation locks the partner `users` row with `SELECT ... FOR UPDATE`, calculates available income under that lock, and inserts the pending request before commit. Two concurrent requests for the same partner cannot both pass against the same available balance.

The user may cancel only a `pending` request. Once admin moves it to `processing`, all further transitions remain inside the privileged admin contour with MFA step-up as already implemented by `/api/v1/admin/withdrawals/{id}/status`.

## Minimum withdrawal

The product specification requires a minimum withdrawal threshold but does not define a concrete amount. It is therefore deployment configuration rather than a hardcoded product guess:

```dotenv
PARTNER_MIN_WITHDRAWAL_RUB=0
```

`0` disables a separate minimum while retaining `amount > 0`. When a business value is approved, set it in production without a code change. The API returns the configured threshold in `/referrals/stats`, and the Mini App validates it before submit; the backend repeats the validation authoritatively.

## Requisites privacy

The user submits a generic `requisites` string because the supplied product FSM does not constrain the payout rail. It is stored inside the existing JSON requisites field.

Security boundary:

- user withdrawal list does **not** echo requisites;
- referral/invitation APIs do not expose Telegram numeric IDs;
- ordinary admin withdrawal readers receive `[restricted]` requisites;
- only admins with `withdrawals.manage` may see requisites in the existing admin API;
- changing withdrawal status requires the existing privileged step-up contour.

If the business later fixes payout rails (for example one bank/SBP/crypto scheme), replace the generic string with a typed provider-specific schema and migration rather than relying on browser-only validation.

## Referral link

Configure:

```dotenv
BOT_USERNAME=KsuBot
```

The API then returns:

```text
https://t.me/KsuBot?start=ref_<telegram_id>
```

When `BOT_USERNAME` is absent the server still returns the existing `ref_<telegram_id>` payload and `referral_link=null`; the Mini App falls back to copy behavior instead of inventing a bot URL.

Copy uses `navigator.clipboard` with the legacy hidden-textarea fallback. Share uses Telegram's `https://t.me/share/url` route from a direct user click.

## Mini App

`partner.js` mounts into the existing `#partnerPreview` target inside Profile. It does not add another bottom-navigation tab.

The browser:

- loads all accounting from server endpoints;
- validates minimum/available amount before submit for immediate UX feedback;
- submits only requested amount and requisites;
- refreshes all partner server state after create/cancel;
- never stores earnings, withdrawal state or requisites in local/session storage.

The server remains authoritative for all monetary checks and status transitions.
