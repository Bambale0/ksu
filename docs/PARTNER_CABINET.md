# Partner cabinet and withdrawal workflow

**Status:** synchronized with current runtime on 2026-08-26.

The partner cabinet lives inside the existing Profile shell. Referral reward percentages remain server settings (30% first line / 5% second line by default); the browser never computes partner earnings, decides referral admission or determines withdrawal eligibility.

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

The cabinet shows:

- total earned partner income;
- available-to-withdraw balance;
- pending rewards;
- pending/processing withdrawal amount;
- first- and second-line counts;
- referral payload/link;
- invitations;
- accrual history;
- withdrawal request history.

## Registration-time referral admission

Referral attachment happens only while a **new Telegram user** is created. Existing accounts are not re-parented by a later `/start` or Mini App launch payload.

The server serializes admission for one inviter with `SELECT ... FOR UPDATE` on the inviter row, then evaluates the current accepted `ReferralRelation` count. This prevents concurrent registrations from each seeing the same pre-limit count and both earning a bonus.

Current defaults:

```dotenv
REFERRAL_ANTIFRAUD_MAX_PER_HOUR=30
REFERRAL_ANTIFRAUD_MAX_PER_DAY=120
REFERRAL_ANTIFRAUD_BURST_WINDOW_SECONDS=10
REFERRAL_ANTIFRAUD_BURST_MAX=6
REFERRAL_ANTIFRAUD_BURST_AUTOBAN=true
```

Semantics:

- hour/day limits reject the new referral relation and inviter bonus, but **do not** deactivate the inviter account;
- burst threshold counts the current attempted registration, so with `BURST_MAX=6` the sixth registration inside the 10-second window is rejected;
- when burst autoban is enabled, that burst attempt also sets the referrer account `is_active=false`; the ordinary Mini App account-restriction path then applies;
- when burst autoban is disabled, the same attempt is rejected with `burst_limit` but the account remains active;
- self-referrals, missing inviters and already-restricted inviters never create a relation or invitation bonus;
- the +30 invite bonus is credited only **after** successful relation admission and remains idempotent per referred user.

Every evaluated referral attempt is written to the durable `referral_events` audit table. Current reasons include:

```text
attached
self_ref
inviter_not_found
blocked_referrer
hourly_limit
daily_limit
burst_limit
burst_autoban
```

The database column is named `metadata`; the SQLAlchemy model intentionally exposes it as Python attribute `details` because Declarative reserves `metadata`.

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

The user may cancel only a `pending` request. Once admin moves it to `processing`, all further transitions remain inside the privileged admin contour with MFA step-up through `/api/v1/admin/withdrawals/{id}/status`.

## Minimum withdrawal

Current approved default:

```dotenv
PARTNER_MIN_WITHDRAWAL_RUB=3000
```

With the public denomination `1 ROX = 1 RUB`, this is the approved 3,000-RUB/ROX partner withdrawal threshold. The API returns the configured threshold in `/referrals/stats`; the Mini App validates it for UX and the backend repeats validation authoritatively.

If business configuration intentionally changes the threshold, deployment config and maintained economy/partner documentation must change together.

## Requisites privacy

The user submits a generic `requisites` string because the current product does not constrain the payout rail. It is stored inside the existing JSON requisites field.

Security boundary:

- user withdrawal list does **not** echo requisites;
- referral/invitation APIs do not expose Telegram numeric IDs;
- ordinary admin withdrawal readers receive `[restricted]` requisites;
- only admins with `withdrawals.manage` may see requisites in the existing admin API;
- changing withdrawal status requires the existing privileged step-up contour.

If payout rails are later fixed to a concrete scheme, replace the generic string with a typed provider-specific schema/migration instead of browser-only validation.

## Referral link — tanyapi parity

ROXY uses the same Main Mini App contract as `banano_kling:tanyapi`:

```text
https://t.me/<actual_bot_username>?startapp=ref_<telegram_id>
```

There is **no Direct Mini App short-name path** in the referral URL. `TELEGRAM_MINI_APP_SHORT_NAME` is not used to build referral/feed/profile/remix links.

The backend synchronizes `BOT_USERNAME` with Telegram `getMe()` at startup so a stale environment value cannot produce links for the wrong bot.

Telegram must also have the bot's **Main Mini App enabled in @BotFather**:

```text
/mybots
→ select the production bot
→ Bot Settings
→ Configure Mini App
→ Enable Mini App
→ URL: <PUBLIC_BASE_URL>/mini-app/
```

Without this BotFather setting Telegram does not set `bot_has_main_app`; `https://t.me/<bot>?startapp=...` cannot open the Main Mini App and Telegram clients may return `BOT_INVALID`.

### Launch payload recovery

The Mini App follows the proven `tanyapi` flow:

1. before `telegram-web-app.js` loads, ROXY snapshots the initial URL hash/search;
2. it reads `initDataUnsafe.start_param`, `tgWebAppStartParam`, the early snapshot, current launch params and signed `initData`;
3. the recovered value is sent as `X-Telegram-Start-Param` together with signed `X-Telegram-Init-Data`;
4. the backend prefers Telegram's signed `start_param` and uses the recovered fallback only when the signed field is absent;
5. referral attribution is resolved before `UserService.get_or_create`, so a new user is attached atomically on the first authenticated Mini App request.

Copy uses `navigator.clipboard` with the legacy hidden-textarea fallback. Share uses Telegram's `https://t.me/share/url` route from a direct user click.

## Mini App

The partner surface lives inside the existing ROXY profile/account UI. It does not add another bottom-navigation tab.

The browser:

- loads all accounting from server endpoints;
- validates minimum/available amount before submit for immediate UX feedback;
- submits only requested amount and requisites;
- refreshes all partner server state after create/cancel;
- never stores earnings, withdrawal state or requisites in local/session storage;
- never decides whether a referral is admitted or whether an inviter should be restricted.

The server remains authoritative for referral admission, monetary checks and status transitions.
