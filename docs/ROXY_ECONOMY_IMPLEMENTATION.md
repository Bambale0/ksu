# ROXY economy implementation

**Status:** synchronized with shipped runtime on 2026-08-20.

This document is the deployment/runbook companion to `ROXY_BRAND.md`.

## Approved product rules

- 1 ROX = 1 RUB.
- Welcome: 50 internal ROX.
- Invited friend: +30 internal ROX to the inviter after successful anti-fraud admission.
- Paid prompt repeat/remix: +5 internal ROX to the original author; self-repeats do not pay.
- Level 1 real top-up: 30% withdrawable ROX.
- Level 2 real top-up: 5% withdrawable ROX.
- Minimum partner withdrawal: 3,000 ROX.

Internal spend ROX live in the wallet/accounting domain. Withdrawable partner earnings are derived from referral reward accounting and are not merged into the spend wallet.

## Public denomination migration

Migration `0023_roxy_one_ruble_denomination` converted persisted legacy 10-RUB credit values to public 1-RUB ROX while preserving real monetary value.

Current production overrides must use public ROX units:

```dotenv
INTERNAL_CREDIT_RUB=1
START_BALANCE_ROX=50
INVITE_BONUS_ROX=30
PROMPT_REPEAT_BONUS_ROX=5
REFERRAL_FIRST_PERCENT=30
REFERRAL_SECOND_PERCENT=5
PARTNER_MIN_WITHDRAWAL_RUB=3000
```

## Referral admission anti-fraud

The invitation bonus is not issued directly from `/start` parsing. A new user first passes the server-side referral admission gate under a row lock on the inviter.

Current defaults:

```dotenv
REFERRAL_ANTIFRAUD_MAX_PER_HOUR=30
REFERRAL_ANTIFRAUD_MAX_PER_DAY=120
REFERRAL_ANTIFRAUD_BURST_WINDOW_SECONDS=10
REFERRAL_ANTIFRAUD_BURST_MAX=6
REFERRAL_ANTIFRAUD_BURST_AUTOBAN=true
```

Rules:

- accepted relations are counted from durable `referral_relations`;
- the +30 invite bonus is credited only after the relation is accepted;
- the wallet credit remains idempotent by referred user;
- hour/day limits reject the attempted attachment but do not deactivate the inviter;
- with the default burst settings, the sixth registration within 10 seconds is rejected and the referrer account is restricted when autoban is enabled;
- all evaluated attempts are persisted to `referral_events` with a reason and context;
- existing users cannot change inviter by presenting another referral payload later.

This protects the spend-wallet bonus from registration floods without mixing it with withdrawable 30%/5% referral rewards.

## Generation billing

Flat generation:

```text
cost_rox = flat_price_rox
```

Per-second generation:

```text
cost_rox = resolved_unit_price_rox × billing_seconds
```

The server resolves model/parameter pricing and repeats that calculation on create before wallet debit.

### Approved generation baseline

```text
Nano Banana PRO            25 ROX
WAN 2.7 photo              20 ROX
GPT Image 2                20 ROX
Nano Banana 2              25 ROX
Nano Banana 2 Lite         25 ROX
Seedream 4.5               20 ROX
Seedream 5 Pro             20 ROX
Seedance 2.0               40 ROX/s
Seedance 2.5               60 ROX/s
Kling 3.0                  30 ROX/s
Veo 3.1                    35 ROX/s
Grok                        15 ROX/s
Grok Imagine 1.5           30 ROX/s
Gemini Omni                from 30 ROX/s
Kling Motion 2.6 720p      20 ROX/s
Kling Motion 2.6 1080p     30 ROX/s
Kling Motion 3.0 720p      60 ROX/s
Kling Motion 3.0 1080p     80 ROX/s
```

This is the approved default baseline. The live runtime tariff can differ after an authorized admin publish.

## Admin Tariffs and runtime pricing

Generation pricing is not a frontend constant.

- the backend catalog contains default price definitions;
- environment pricing overrides may exist;
- the latest published Admin Tariffs `generation_pricing` version is applied as a runtime override;
- publish requires the privileged pricing permission and high-impact confirmation/MFA policy;
- invalid model IDs, price-mode mismatches and unsupported parameter tiers are rejected;
- quote and actual debit share the same resolver;
- the latest published tariff is restored from PostgreSQL after restart.

Operationally, a price change is complete only after catalog/quote verification and a controlled debit check. See `ADMIN_RUNBOOK.md` and `ROXY_RELEASE_ACCEPTANCE.md`.

## Package/payment units

If `ROX_PACKAGES_JSON` or `CARD_PACKAGES_JSON` are explicitly configured, amounts are expressed in public ROX. For RUB packages the product relationship is 1 ROX per 1 RUB unless a separately documented promotion changes what the customer receives.

A non-zero `GENERATION_DAILY_SPEND_LIMIT_CREDITS` is also interpreted in current public ROX units despite the legacy config field name.

## Release verification

After deploy/migration/restart:

1. `/api/v1/generations/models` reports the current public ROX denomination/prices.
2. Generation quote values match the active tariff.
3. A controlled generation debit equals its quote.
4. Kling Motion 2.6/3.0 resolve different 720p and 1080p rates correctly.
5. Restart preserves the latest published Admin Tariff.
6. `/api/v1/referrals/stats` keeps bonus/internal and withdrawable balances separate.
7. New registration receives 50 ROX.
8. An admitted referred registration credits the inviter 30 ROX once.
9. Hour/day rejected referrals create no relation/bonus and leave the inviter active.
10. Burst threshold blocks the triggering registration and, when configured, restricts the referrer account.
11. Concurrent registration attempts for one inviter cannot exceed the configured limit through a race.
12. Paid remix by another user credits the original author 5 ROX once.
13. Partner rewards remain separately withdrawable subject to the 3,000 ROX threshold.
