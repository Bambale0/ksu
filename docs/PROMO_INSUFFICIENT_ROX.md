# Promo code and insufficient-credit recovery

This module completes product FSM sections 2.2–2.4 around insufficient internal credits and promo-code redemption.

## Insufficient credits

Generation pricing remains server-owned. The Mini App never decides whether a generation is affordable from cached balance data.

`WalletService.debit()` raises `InsufficientBalanceError` with authoritative values captured under the wallet row lock:

- current balance;
- required amount;
- shortage.

`InsufficientBalanceError` is deliberately not a `ValueError`. Generation request validation errors use `422`, while an otherwise valid generation that cannot be funded reaches the existing `409 Insufficient credits` admission branch.

The Mini App recovery module observes that exact server response and then requests fresh server state:

```text
GET  /api/v1/me
POST /api/v1/generations/quote
```

The modal displays the FSM fields:

- current balance;
- action cost;
- credits missing;
- `Пополнить`;
- `Отмена`.

`Пополнить` routes to the existing Wallet checkout. The current generator draft is not cleared; the existing generator already persists sanitized non-secret draft convenience data.

The recovery banner is enabled only after a later authoritative `/me` response shows enough balance. The user must press `Вернуться к генерации`, then explicitly press `Создать` again. The recovery module never submits a replacement generation automatically, so a payment cannot cause an implicit second charge.

## Promo-code bonuses

Promo codes are a payment-bound marketing instrument. A code never credits ROX merely because the user entered it.

Validation endpoints:

```text
POST /api/v1/promocodes/validate
POST /api/v1/promocodes/redeem   # compatibility alias; validates only
```

Stable error categories:

```text
invalid
expired
usage_limit_reached
already_used
already_reserved
```

The API converts these to user-facing Russian messages while preserving a stable machine-readable category in validation errors.

A valid code exposes a fixed ROX reward, but the reward is only **reserved** when a payment intent is created with `promo_code`. The final bonus settlement happens only after the payment provider confirms success:

1. the paid package credits exactly its base ROX;
2. the reserved promo reward is credited as a separate `promo_bonus` wallet transaction;
3. the promo successful-use counter increments;
4. the reservation becomes `applied`.

Failed, canceled or expired payments release their promo reservation. Active reservations count against `max_uses`, preventing concurrent checkouts from oversubscribing a limited campaign. One user can successfully use a given promo code only once.

Promo campaign controls are server-owned:

- fixed reward in ROX;
- active/inactive state;
- successful activation limit (`max_uses`);
- expiration timestamp;
- immediate operator shutdown.

This supports partner campaigns such as `KSENIA50` with 1,000 successful activations for one month or 5,000 activations for a three-month campaign. The counter tracks paid activations, not code-entry attempts.

Automatic package bonuses are disabled. Package catalogs return `bonus_credits=0` and `total_credits=credits`; extra ROX can only originate from a valid promo attached to a successful payment.

Full and partial payment refunds also reverse the applied promo bonus proportionally through the wallet accounting ledger.

## Transaction-history empty state

The Wallet presentation now enforces the product copy:

> Операций пока нет. Пополните баланс или создайте первый контент.

This is presentation only; ledger data remains server-authoritative.

## Mini App integration

Files:

```text
app/web/mini_app/promo-recovery.js
app/web/mini_app/promo-recovery.css
```

The module is mounted through the existing shell integration after the generation, payment and social modules.

It uses raw signed `Telegram.WebApp.initData` in `X-Telegram-Init-Data`, stores no balance/promo/payment truth in localStorage/sessionStorage, and does not use `initDataUnsafe` for authentication.

## CI contract

CI validates the new JavaScript entrypoint and regression tests cover:

- insufficient wallet exception amounts;
- the formerly unreachable generation `409` insufficient-credit branch;
- promo wallet credit + ledger transaction + notification;
- invalid/expired/already-used stable error codes;
- exact FSM modal controls and server `/me` + `/quote` recovery;
- no automatic replacement generation submission;
- shell mount and Wallet empty-state copy.
