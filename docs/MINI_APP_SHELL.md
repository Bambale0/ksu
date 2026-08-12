# Telegram Mini App product shell

**Status:** shell/navigation contract current on 2026-08-12.

The Mini App at `/mini-app/` is no longer a single long generation form. The existing schema-driven generator remains the creation engine, but it is mounted inside a Telegram-first product shell with stable top-level navigation.

## Navigation model

Top-level tabs:

```text
Create
History
Wallet
Profile
```

Top-level tab changes do **not** show Telegram `BackButton`. Nested product states do:

```text
Create home
  ├─ model builder
  └─ generation detail / active task
```

`BackButton` returns from a nested state to the current top-level shell state. Browser `history.pushState` mirrors the nested state so Telegram Web/Desktop and ordinary browser navigation behave consistently.

The legacy Results & History module is not duplicated. Its history overlay is remounted into `History` as a normal shell view. When an existing History action opens a result or restores a recreate payload, `shell-integration.js` bridges that action into the visible Create builder so the backend/server-quote/reuse contract remains unchanged.

## Create home

Create opens on a lightweight discovery screen rather than the full form.

It loads the existing public model catalog:

```text
GET /api/v1/generations/models
```

and derives model-family cards from runtime data. The shell does not hardcode a provider model list.

When Telegram authentication is available, Create also loads:

```text
GET /api/v1/generations?limit=6
GET /api/v1/me
```

and shows:

- one active generation when present;
- recent completed/failed work;
- current credit balance in the persistent header.

Selecting a family opens the existing schema-driven builder and selects the first model in that family. The builder continues to own model drafts, field rendering, upload state, validation, live quote and final generation submission.

## History

The existing history module remains authoritative for:

- cursor pagination;
- open result;
- recreate/reuse with sanitized server payload;
- history soft-hide semantics;
- owned media/result rendering.

The shell only changes presentation/navigation: the module is mounted into `#historyMount` instead of behaving as a floating product entrypoint.

## Wallet/Payments

Wallet now contains the complete user top-up flow while keeping backend payment state authoritative.

It loads:

```text
GET /api/v1/me
GET /api/v1/me/transactions
GET /api/v1/payments/packages
GET /api/v1/payments?limit=12
```

The UI provides:

- current internal-credit balance;
- server-defined package cards;
- Crypto Pay / T-Bank / YooKassa provider selection;
- idempotent checkout with one UUID `Idempotency-Key` per package/provider intent;
- current nonterminal payment card with reopen/refresh actions;
- polling of `GET /api/v1/payments/{payment_id}` until terminal state;
- recent server payment history;
- authoritative wallet ledger refresh after success.

Wallet never submits arbitrary RUB/credit amounts and never persists payment success locally. On a Mini App reload/reopen it discovers the newest nonterminal payment from `GET /api/v1/payments` and resumes polling from server state.

Detailed payment UX/recovery contract: `docs/WALLET_PAYMENTS.md`.

## Profile shell

Profile loads:

```text
GET /api/v1/me
GET /api/v1/referrals/stats
```

and provides a product-level account/referral summary. The full partner cabinet, withdrawals and support UX remain separate feature epics.

## Telegram integration

The shell follows current Telegram Mini Apps APIs and design guidance.

It uses:

```text
Telegram.WebApp.ready()
Telegram.WebApp.expand()
Telegram.WebApp.BackButton
Telegram.WebApp.viewportStableHeight
Telegram.WebApp.themeChanged
Telegram.WebApp.viewportChanged
Telegram.WebApp.safeAreaChanged
Telegram.WebApp.contentSafeAreaChanged
Telegram.WebApp.openLink
Telegram.WebApp.openTelegramLink
```

Layout uses Telegram safe-area CSS variables with browser `env(safe-area-inset-*)` fallback:

```text
--tg-safe-area-inset-*
--tg-content-safe-area-inset-*
--tg-viewport-stable-height
```

The persistent bottom navigation therefore stays clear of device/Telegram chrome instead of assuming a fixed viewport.

## Theme behavior

Visual tokens are based on Telegram theme CSS variables:

```text
--tg-theme-bg-color
--tg-theme-text-color
--tg-theme-hint-color
--tg-theme-link-color
--tg-theme-button-color
--tg-theme-button-text-color
--tg-theme-secondary-bg-color
--tg-theme-section-bg-color
--tg-theme-header-bg-color
--tg-theme-bottom-bar-bg-color
```

The shell also reacts to `themeChanged` and updates Telegram header/background/bottom-bar chrome where the client API supports it.

## Authentication boundary

The browser never authenticates the user with `initDataUnsafe`.

Authenticated shell requests send only raw:

```text
Telegram.WebApp.initData
```

as:

```http
X-Telegram-Init-Data: <signed raw initData>
```

The backend continues to validate the Telegram signature. Model catalog/quote and payment package catalog remain public according to the existing API contract; wallet history/payment status/profile/history are authenticated.

## Client persistence

The shell does not persist wallet balances, generation statuses, payment state, referral accounting or media ownership locally.

The existing generation engine still uses versioned browser `localStorage` only for non-secret generation draft convenience and selected model. Those drafts are sanitized against the latest backend `ui_schema` before reuse.

Wallet payment intent UUID exists only in memory for transient retry safety. Full reload recovery uses authenticated server payment history, not browser financial state.

## Loading / offline / error states

The shell includes explicit states instead of leaving empty layout blocks:

- model-family skeletons;
- recent-generation skeletons/empty state;
- wallet/profile skeletons;
- payment package empty/loading state;
- payment provider uncertainty/reconciliation state;
- payment rate-limit retry messaging;
- API failure cards;
- browser offline banner;
- Telegram-context explanation when opened as a normal webpage without signed init data.

`online`/`activated` events refresh visible server state. Failed background refreshes do not overwrite already rendered business state with fabricated local values.

## Accessibility

The shell keeps semantic headings and named navigation, uses actual buttons/links for interactions, preserves focus indication and focuses the new view heading after navigation. Wallet package/provider choices use radio semantics. `prefers-reduced-motion` disables transition/animation behavior.

## Files

```text
app/web/mini_app/index.html             semantic product shell + generator + Wallet surfaces
app/web/mini_app/styles.css             shell, builder, responsive and safe-area presentation
app/web/mini_app/wallet.css             Wallet/package/provider/payment presentation
app/web/mini_app/app.js                 existing schema-driven generation/results engine
app/web/mini_app/shell.js               shell routing/data/loading/detail controller
app/web/mini_app/shell-integration.js   bridge between existing History actions and shell builder
app/web/mini_app/payment-link-guard.js  direct-activation HTTPS payment navigation guard
app/web/mini_app/wallet.js              idempotent checkout/recovery/payment polling controller
```

## CI contract

Every shipped JavaScript entrypoint must pass Node syntax validation:

```text
node --check app/web/mini_app/app.js
node --check app/web/mini_app/shell.js
node --check app/web/mini_app/shell-integration.js
node --check app/web/mini_app/payment-link-guard.js
node --check app/web/mini_app/wallet.js
```

Python contract tests additionally assert the stable shell DOM IDs, top-level tabs, Telegram safe-area/back/theme integration, payment idempotency/recovery boundaries and absence of browser-persisted financial truth.

## Follow-up feature boundaries

Remaining feature epics should extend the existing targets rather than adding new floating entrypoints:

1. Partner cabinet/withdrawals inside Profile.
2. Support/notifications/profile management inside Profile/More.
3. Likes/subscriptions where content discovery/history surfaces need them.
4. Visual admin remains outside the user Mini App.

Official Telegram Mini Apps reference used for this contract: `https://core.telegram.org/bots/webapps`.
