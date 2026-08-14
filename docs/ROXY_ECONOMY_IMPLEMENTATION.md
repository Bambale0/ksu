# ROXY economy implementation

This document is the deployment/runbook companion to `ROXY_BRAND.md`.

## Approved product rules

- 1 ROX = 1 RUB.
- Welcome: 50 internal ROX.
- Invited friend: +30 internal ROX to the inviter.
- Prompt repeat/remix: +5 internal ROX to the original author; self-repeats do not pay.
- Level 1 real top-up: 30% withdrawable ROX.
- Level 2 real top-up: 5% withdrawable ROX.
- Minimum partner withdrawal: 3,000 ROX.

Internal ROX live in `wallets.balance`. Withdrawable ROX are derived from referral reward accounting and are never merged into the spend wallet.

## Denomination migration

Migration `0023_roxy_one_ruble_denomination` converts persisted legacy 10-RUB credit values to 1-RUB ROX by multiplying credit-denominated amounts by 10. This preserves the real RUB value of existing balances, generation history, payment credits, promo rewards, prompt-tool costs and batch charges.

Built-in generation catalog defaults are likewise redenominated at runtime. Explicit `GENERATION_PRICING_JSON` overrides are interpreted as public ROX and must already use the new 1-RUB unit.

Published prompt-tool tariff `prompt_costs` values are converted by migration 0023.

## Production environment

Before deployment, update any explicit production overrides to the values in `.env.example`. In particular, old `START_BALANCE_ROX=0`, `INTERNAL_CREDIT_RUB=10` or `PARTNER_MIN_WITHDRAWAL_RUB=0` values will override the new code defaults and must not remain.

If `ROX_PACKAGES_JSON` or `CARD_PACKAGES_JSON` are explicitly configured, their credit/ROX amounts must be expressed in public ROX. For RUB packages the expected product relationship is 1 ROX per 1 RUB.

If `GENERATION_DAILY_SPEND_LIMIT_CREDITS` is non-zero, convert the old value by multiplying it by 10.

## Release verification

After migration:

1. `/api/v1/generations/models` reports `internal_credit_rub = 1.00` and public ROX prices.
2. `/api/v1/referrals/stats` reports both `bonus_rox` and `withdrawable_rox`.
3. New registration receives 50 ROX.
4. A referred registration credits the inviter 30 ROX once.
5. A paid prompt remix by another user credits the original author 5 ROX once.
6. Referral rewards from real paid top-ups remain separate and withdrawable at 3,000 ROX.
7. Telegram and Mini App primary menus show only: Create, Prompts, My ROX, Earn, Profile.
