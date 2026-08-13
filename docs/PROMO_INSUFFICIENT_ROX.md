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

## Promo-code redemption

Existing endpoint:

```text
POST /api/v1/promocodes/redeem
```

The service now exposes stable error categories:

```text
invalid
expired
usage_limit_reached
already_used
```

The API converts these to user-facing Russian messages while preserving the machine-readable code in `detail.code`.

A successful redemption is one database transaction containing:

1. promo redemption record;
2. promo use-count update;
3. wallet credit through the immutable wallet ledger;
4. success notification.

The response includes the credited amount and authoritative new wallet balance. The Profile promo form updates displayed balance only from that server response.

The current promo schema supports global activation, expiration and usage limits plus one redemption per user. The product document mentions a possible "unavailable for this account" state but does not define account-targeting criteria; no invented targeting business rule was added. Inactive/nonexistent codes use the safe `invalid`/unavailable state.

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
